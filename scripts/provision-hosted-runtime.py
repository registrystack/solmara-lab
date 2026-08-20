#!/usr/bin/env python3
"""Materialize one authority-owned hosted runtime from immutable public assets."""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import stat
import sys
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import yaml
from cryptography.hazmat.primitives.asymmetric import ec, rsa

GENERIC_ERROR = "hosted target provisioning failed"
SUCCESS = "hosted target ready"
MAX_SECRET_BYTES = 16 * 1024
RELAYS = ("cra", "nia", "mosd", "sipf", "nagdi")
CELLS = ("cra", "nia", "sro", "mosd-programme", "sipf", "nagdi")
MINT_ORIGIN = "https://mint-authority-cells.solmara.registrystack.org"
RELAY_ORIGINS = {
    "cra": "https://cra-relay-authority-cells.solmara.registrystack.org",
    "mosd-programme": (
        "https://mosd-programme-relay-authority-cells.solmara.registrystack.org"
    ),
    "sipf": "https://sipf-relay-authority-cells.solmara.registrystack.org",
    "nagdi": "https://nagdi-relay-authority-cells.solmara.registrystack.org",
}
DIRECT = {
    "cra": ("cra-birth-extract", "cra-birth"),
    "nia": ("nia-population-extract", "nia-population"),
    "sro": ("sro-poverty-extract", "sro-poverty"),
}
# Every application also joins a Coolify-managed network that carries the ingress
# proxy, so a listener bound only to its private runtime address refuses that
# proxy and never answers a public route. Isolation comes from network
# membership instead: an application's networks hold only its own containers and
# the proxy. The value stays an explicit argument, and anything else is refused,
# so a deployment cannot quietly move a listener off the interfaces it needs.
EXPECTED_BIND_HOST = "0.0.0.0"
CELL_CLIENTS = {
    "cra": ("cra-pension-evidence", "cra-citizen-evidence"),
    "nia": (),
    "sro": (),
    "mosd-programme": ("mosd-child-benefit-evidence",),
    "sipf": ("sipf-pension-evidence", "sipf-survivor-evidence"),
    "nagdi": ("nagdi-voucher-evidence", "nagdi-livestock-evidence"),
}
MINT_CLIENTS = {
    "cra-pension-evidence": (
        "solmara:relay:cra:death-by-uin",
        "https://id.registrystack.org/solmara/purpose/pension-payment-review",
    ),
    "cra-citizen-evidence": (
        "solmara:relay:cra:citizen-link-by-uin",
        "https://id.registrystack.org/solmara/purpose/citizen-self-service",
    ),
    "mosd-child-benefit-evidence": (
        "solmara:relay:mosd:by-uin",
        "https://id.registrystack.org/solmara/purpose/child-benefit-review",
    ),
    "sipf-pension-evidence": (
        "solmara:relay:sipf:by-pensioner-uin",
        "https://id.registrystack.org/solmara/purpose/pension-payment-review",
    ),
    "sipf-survivor-evidence": (
        "solmara:relay:sipf:by-spouse-uin",
        "https://id.registrystack.org/solmara/purpose/survivor-benefit-determination",
    ),
    "nagdi-voucher-evidence": (
        "solmara:relay:nagdi:voucher-by-farmer-id",
        "https://id.registrystack.org/solmara/purpose/voucher-eligibility-review",
    ),
    "nagdi-livestock-evidence": (
        "solmara:relay:nagdi:movement-by-farmer-id",
        "https://id.registrystack.org/solmara/purpose/livestock-movement-control",
    ),
    "nia-esignet": (
        "solmara:relay:nia:esignet-userinfo",
        "https://id.registrystack.org/solmara/purpose/esignet-identity-verification",
    ),
}
# Re-adopting an extract this provisioner already published imposes no freshness
# ceiling. `maximumExtractAgeSeconds` is a serving policy the Evidence cell
# applies to live requests; enforcing it again here only makes the provision
# application refuse to redeploy a day after it last ran. Publishing a newer
# checkpoint stays the deliberate, separate `publish-extract` operation. The
# ceiling is lifted rather than removed so a future-dated extract is still
# refused.
REUSE_MAX_EXTRACT_AGE_SECONDS = 100 * 365 * 24 * 60 * 60
ROLLBACK_RUNTIME = re.compile(
    r"^runtime\.rollback-(?:cra-birth|nia-population|sro-poverty)-"
    r"[0-9]{8}T[0-9]{6}(?:[0-9]{6})?Z\.yaml$"
)


class ProvisionError(RuntimeError):
    """A value-free provisioning refusal."""


class QuietParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        del message
        raise ProvisionError("invalid arguments")


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def verify_assets(root: Path) -> None:
    try:
        module_path = Path(__file__).with_name("hosted-runtime-assets.py")
        spec = importlib.util.spec_from_file_location(
            "hosted_runtime_assets", module_path
        )
        if spec is None or spec.loader is None:
            raise ProvisionError("invalid assets")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.verify_manifest(root)
    except Exception:  # noqa: BLE001 - public boundary is deliberately value-free.
        raise ProvisionError("invalid assets") from None


def _read_secret(root: Path, name: str) -> bytes:
    path = root / name
    try:
        if path.parent.resolve() != root.resolve() or path.is_symlink():
            raise ProvisionError("invalid secret")
        metadata = path.stat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_mode & 0o022
            or metadata.st_size < 1
            or metadata.st_size > MAX_SECRET_BYTES
        ):
            raise ProvisionError("invalid secret")
        value = path.read_bytes()
        if len(value) != metadata.st_size:
            raise ProvisionError("invalid secret")
        return value.rstrip(b"\n")
    except ProvisionError:
        raise
    except OSError:
        raise ProvisionError("invalid secret") from None


def _hmac_secret(root: Path, name: str) -> bytes:
    value = _read_secret(root, name)
    if (
        len(value) < 32
        or len(value) > 128
        or any(byte < 0x21 or byte > 0x7E for byte in value)
    ):
        raise ProvisionError("invalid secret")
    return value


def _validate_secret_inventory(root: Path, expected: set[str]) -> None:
    try:
        root_metadata = root.lstat()
        if (
            not stat.S_ISDIR(root_metadata.st_mode)
            or stat.S_IMODE(root_metadata.st_mode) != 0o700
            or root_metadata.st_uid != os.geteuid()
            or root_metadata.st_gid != os.getegid()
        ):
            raise ProvisionError("invalid secret inventory")
        observed: set[str] = set()
        with os.scandir(root) as entries:
            for entry in entries:
                metadata = entry.stat(follow_symlinks=False)
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or stat.S_IMODE(metadata.st_mode) != 0o400
                    or metadata.st_uid != os.geteuid()
                    or metadata.st_gid != os.getegid()
                    or entry.name not in expected
                ):
                    raise ProvisionError("invalid secret inventory")
                observed.add(entry.name)
        if observed != expected:
            raise ProvisionError("invalid secret inventory")
        for name in sorted(expected):
            _read_secret(root, name)
    except ProvisionError:
        raise
    except OSError:
        raise ProvisionError("invalid secret inventory") from None


def _confine_secret_inventory(root: Path) -> None:
    descriptor: int | None = None
    try:
        descriptor = os.open(
            root,
            os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
        )
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o755
            or metadata.st_uid != os.geteuid()
            or metadata.st_gid != os.getegid()
        ):
            raise ProvisionError("invalid secret inventory")
        os.fchmod(descriptor, 0o700)
    except ProvisionError:
        raise
    except OSError:
        raise ProvisionError("invalid secret inventory") from None
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                raise ProvisionError("invalid secret inventory") from None


def _provision_secret_inventory(target: str) -> set[str] | None:
    if target.endswith("-relay") and target.removesuffix("-relay") in RELAYS:
        return None
    if target == "mint":
        return {
            "signing-public.jwk",
            "audit-hmac-key",
            "solmara-demo-client-public.jwk",
            *(f"{client}-public.jwk" for client in MINT_CLIENTS),
        }
    if target.endswith("-evidence"):
        cell = target.removesuffix("-evidence")
        if cell in CELLS:
            return {
                "signing-public.jwk",
                "audit-hmac-key",
                "subject-binding-hmac-key",
                *(f"{client}-client-key" for client in CELL_CLIENTS[cell]),
            }
    raise ProvisionError("invalid target")


def _consume_secret_inventory(root: Path, expected: set[str]) -> None:
    """Remove only the closed injected input inventory, never output material."""
    descriptor: int | None = None
    valid = True
    observed: set[str] = set()
    try:
        descriptor = os.open(
            root,
            os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
        )
        root_metadata = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(root_metadata.st_mode)
            or stat.S_IMODE(root_metadata.st_mode) != 0o700
            or root_metadata.st_uid != os.geteuid()
            or root_metadata.st_gid != os.getegid()
        ):
            valid = False
        observed = set(os.listdir(descriptor))
        if observed != expected:
            valid = False
        for name in sorted(observed & expected):
            try:
                metadata = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or stat.S_IMODE(metadata.st_mode) != 0o400
                    or metadata.st_uid != os.geteuid()
                    or metadata.st_gid != os.getegid()
                ):
                    valid = False
                os.unlink(name, dir_fd=descriptor)
            except OSError:
                valid = False
        if observed - expected:
            valid = False
    except OSError:
        valid = False
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                valid = False
    if not observed - expected:
        try:
            root.rmdir()
        except OSError:
            valid = False
    if not valid:
        raise ProvisionError("secret cleanup failed")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _public_jwk(data: bytes, *, allow_rsa: bool = True) -> dict[str, str]:
    try:
        value = json.loads(data.decode("utf-8"))
        if not isinstance(value, dict) or "d" in value:
            raise ProvisionError("invalid public key")
        if value.get("kty") == "EC":
            if (
                set(value) != {"kty", "crv", "alg", "x", "y", "kid"}
                or value.get("crv") != "P-256"
                or value.get("alg") != "ES256"
            ):
                raise ProvisionError("invalid public key")
            x, y = (
                int.from_bytes(_b64decode(value["x"]), "big"),
                int.from_bytes(_b64decode(value["y"]), "big"),
            )
            ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1()).public_key()
            thumb = {key: value[key] for key in ("crv", "kty", "x", "y")}
        elif allow_rsa and value.get("kty") == "RSA":
            if (
                set(value) != {"kty", "alg", "n", "e", "kid"}
                or value.get("alg") != "RS256"
            ):
                raise ProvisionError("invalid public key")
            rsa.RSAPublicNumbers(
                int.from_bytes(_b64decode(value["e"]), "big"),
                int.from_bytes(_b64decode(value["n"]), "big"),
            ).public_key()
            thumb = {key: value[key] for key in ("e", "kty", "n")}
        else:
            raise ProvisionError("invalid public key")
        kid = (
            base64.urlsafe_b64encode(
                hashlib.sha256(
                    json.dumps(thumb, separators=(",", ":"), sort_keys=True).encode()
                ).digest()
            )
            .rstrip(b"=")
            .decode()
        )
        if value["kid"] != kid:
            raise ProvisionError("invalid public key")
        return value
    except ProvisionError:
        raise
    except (UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        raise ProvisionError("invalid public key") from None


def _private_client_jwk(data: bytes) -> None:
    try:
        value = json.loads(data.decode("utf-8"))
        if (
            not isinstance(value, dict)
            or not isinstance(value.get("d"), str)
            or not isinstance(value.get("kid"), str)
        ):
            raise ProvisionError("invalid client key")
        if value.get("kty") == "EC":
            required = {"kty", "crv", "alg", "x", "y", "d", "kid"}
            if (
                set(value) != required
                or value.get("crv") != "P-256"
                or value.get("alg") != "ES256"
            ):
                raise ProvisionError("invalid client key")
            scalar = int.from_bytes(_b64decode(value["d"]), "big")
            public = (
                ec.derive_private_key(scalar, ec.SECP256R1())
                .public_key()
                .public_numbers()
            )
            if (
                int.from_bytes(_b64decode(value["x"]), "big") != public.x
                or int.from_bytes(_b64decode(value["y"]), "big") != public.y
            ):
                raise ProvisionError("invalid client key")
            public_value = {
                key: value[key] for key in ("kty", "crv", "alg", "x", "y", "kid")
            }
        elif value.get("kty") == "RSA":
            required = {"kty", "alg", "n", "e", "d", "p", "q", "dp", "dq", "qi", "kid"}
            if set(value) != required or value.get("alg") != "RS256":
                raise ProvisionError("invalid client key")
            numbers = {
                name: int.from_bytes(_b64decode(value[name]), "big")
                for name in ("n", "e", "d", "p", "q", "dp", "dq", "qi")
            }
            rsa.RSAPrivateNumbers(
                p=numbers["p"],
                q=numbers["q"],
                d=numbers["d"],
                dmp1=numbers["dp"],
                dmq1=numbers["dq"],
                iqmp=numbers["qi"],
                public_numbers=rsa.RSAPublicNumbers(numbers["e"], numbers["n"]),
            ).private_key()
            public_value = {key: value[key] for key in ("kty", "alg", "n", "e", "kid")}
        else:
            raise ProvisionError("invalid client key")
        _public_jwk(json.dumps(public_value).encode())
    except ProvisionError:
        raise
    except (UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        raise ProvisionError("invalid client key") from None


def _tree_digest(root: Path) -> dict[str, tuple[str, int]]:
    if not root.exists():
        return {}
    result: dict[str, tuple[str, int]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ProvisionError("invalid existing output")
        if path.is_dir():
            result[path.relative_to(root).as_posix()] = (
                "directory",
                stat.S_IMODE(path.stat().st_mode),
            )
        elif path.is_file():
            result[path.relative_to(root).as_posix()] = (
                _digest(path),
                stat.S_IMODE(path.stat().st_mode),
            )
        else:
            raise ProvisionError("invalid existing output")
    return result


def _check_install_tree(
    staged: Path,
    destination: Path,
    *,
    preserve: Callable[[str, tuple[str, int]], bool] | None = None,
) -> None:
    if destination.is_symlink():
        raise ProvisionError("invalid existing output")
    expected = _tree_digest(staged)
    current = _tree_digest(destination)
    active = {
        relative: value
        for relative, value in current.items()
        if preserve is None or not preserve(relative, value)
    }
    if active and active != expected:
        raise ProvisionError("existing output mismatch")


def _legacy_secret_tree(staged: Path, destination: Path) -> bool:
    if destination.is_symlink():
        raise ProvisionError("invalid existing output")
    expected = _tree_digest(staged)
    current = _tree_digest(destination)
    if current:
        for path in destination.rglob("*"):
            metadata = path.lstat()
            if path.is_file() and (
                not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
            ):
                raise ProvisionError("invalid existing output")
    if not current or current == expected:
        return False
    legacy = {
        relative: (digest, 0o400 if digest != "directory" and mode == 0o600 else mode)
        for relative, (digest, mode) in expected.items()
    }
    if current != legacy:
        raise ProvisionError("existing output mismatch")
    return True


def _check_secret_install_tree(staged: Path, destination: Path) -> None:
    _legacy_secret_tree(staged, destination)


def _install_tree(
    staged: Path,
    destination: Path,
    *,
    root_mode: int,
    owner: tuple[int, int] | None = None,
    preserve: Callable[[str, tuple[str, int]], bool] | None = None,
) -> None:
    _check_install_tree(staged, destination, preserve=preserve)
    expected = _tree_digest(staged)
    destination.mkdir(parents=True, exist_ok=True)
    for source in sorted(staged.rglob("*")):
        relative = source.relative_to(staged)
        target = destination / relative
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            target.chmod(0o755)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.parent.chmod(0o755)
            if target.exists():
                continue
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            descriptor = os.open(target, flags, stat.S_IMODE(source.stat().st_mode))
            with os.fdopen(descriptor, "wb") as output:
                output.write(source.read_bytes())
            target.chmod(stat.S_IMODE(source.stat().st_mode))
    for source in sorted(
        (path for path in staged.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        (destination / source.relative_to(staged)).chmod(
            stat.S_IMODE(source.stat().st_mode)
        )
    destination.chmod(root_mode)
    if owner is not None:
        uid, gid = owner
        for target in sorted(destination.rglob("*"), reverse=True):
            os.chown(target, uid, gid, follow_symlinks=False)
        os.chown(destination, uid, gid, follow_symlinks=False)
    observed = {
        relative: value
        for relative, value in _tree_digest(destination).items()
        if preserve is None or not preserve(relative, value)
    }
    if observed != expected:
        raise ProvisionError("output verification failed")


def _install_secret_tree(staged: Path, destination: Path) -> None:
    if _legacy_secret_tree(staged, destination):
        for path in destination.rglob("*"):
            if path.is_file():
                path.chmod(0o600)
    _install_tree(
        staged,
        destination,
        root_mode=0o700,
        owner=(65532, 65532),
    )


def _preserve_extract_rollback(relative: str, value: tuple[str, int]) -> bool:
    return (
        "/" not in relative
        and ROLLBACK_RUNTIME.fullmatch(relative) is not None
        and value[0] != "directory"
        and value[1] == 0o444
    )


def _copy_tree(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination)


def _freeze_tree(destination: Path) -> None:
    for path in sorted(destination.rglob("*"), reverse=True):
        path.chmod(0o555 if path.is_dir() else 0o444)
    destination.chmod(0o555)


def _write(path: Path, value: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)
    path.chmod(mode)


def _validated_origin(value: str | None, expected: str) -> str:
    try:
        if value is None or value != expected:
            raise ProvisionError("invalid origin")
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or parsed.netloc != parsed.hostname
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
            or value != f"https://{parsed.hostname}"
        ):
            raise ProvisionError("invalid origin")
        return value
    except (TypeError, ValueError):
        raise ProvisionError("invalid origin") from None


def _patch_mint_origin(config: dict, mint_origin: str) -> None:
    mint_origin = _validated_origin(mint_origin, MINT_ORIGIN)
    config["issuer"] = mint_origin
    config["clientAssertion"]["audience"] = f"{mint_origin}/token"


def _patch_relay_origin(config: dict, mint_origin: str) -> None:
    mint_origin = _validated_origin(mint_origin, MINT_ORIGIN)
    config["authentication"]["issuer"]["discoveryUrl"] = (
        f"{mint_origin}/.well-known/openid-configuration"
    )


def _patch_evidence_origins(
    config: dict, cell: str, mint_origin: str, relay_origin: str | None
) -> None:
    mint_origin = _validated_origin(mint_origin, MINT_ORIGIN)
    expected_relay_origin = RELAY_ORIGINS.get(cell)
    if (expected_relay_origin is None) != (relay_origin is None):
        raise ProvisionError("invalid source origin")
    if expected_relay_origin is not None:
        relay_origin = _validated_origin(relay_origin, expected_relay_origin)
    config["authentication"]["issuer"] = mint_origin
    config["authentication"]["jwksUri"] = f"{mint_origin}/.well-known/jwks.json"
    relay_sources = [
        source_config
        for source_config in config["sources"].values()
        if source_config["transport"] == "http-json"
    ]
    if (cell in RELAY_ORIGINS) != bool(relay_sources) or (relay_origin is None) != (
        cell not in RELAY_ORIGINS
    ):
        raise ProvisionError("invalid source origin")
    for source_config in relay_sources:
        source_config["baseUrl"] = relay_origin
        authentication = source_config["authentication"]
        authentication["tokenEndpoint"] = f"{mint_origin}/token"
        authentication["clientAssertionAudience"] = f"{mint_origin}/token"


def _patch_runtime(path: Path, bind_host: str, extract_name: str | None = None) -> None:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    config["listener"]["bindHost"] = bind_host
    if extract_name is not None:
        profile = next(iter(config["sourceExtracts"]))
        old_path = Path(config["sourceExtracts"][profile]["path"])
        config["sourceExtracts"][profile]["path"] = str(
            old_path.with_name(extract_name)
        )
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


def _stage_relay(
    assets: Path,
    authority: str,
    runtime: Path,
    source: Path,
    mint_origin: str,
) -> None:
    relay = assets / "relays" / authority
    config = yaml.safe_load((relay / "runtime.yaml").read_text(encoding="utf-8"))
    _patch_relay_origin(config, mint_origin)
    _write(
        runtime / "runtime.yaml",
        yaml.safe_dump(config, sort_keys=False).encode(),
        0o444,
    )
    _copy_tree(relay / "package", runtime / "package")
    _write(
        source / f"{authority}.sqlite",
        (relay / "source" / f"{authority}.sqlite").read_bytes(),
        0o444,
    )
    _freeze_tree(source)
    _freeze_tree(runtime)


def _load_publisher(assets: Path):
    sys.path.insert(0, str(assets / "generator"))
    return importlib.import_module("solmara_lab.publisher")


def _stage_extract(
    assets: Path, cell: str, destination: Path, published_at: str, observed_at: str
) -> str:
    publisher = _load_publisher(assets)
    extract_id = publisher.timestamped_extract_id(cell, published_at)
    with tempfile.TemporaryDirectory(prefix="solmara-extract-") as temporary:
        generated = publisher.publish_extract(
            Path(temporary), cell, published_at, extract_id
        )
        # Regenerating a reused publication carries its original published_at,
        # so the serving age is lifted here for the same reason it is lifted
        # when the binding is read back. This validates deterministic output
        # against an exact expected identity; freshness is not the question.
        publisher.validate_extract(
            generated,
            cell,
            observed_at=observed_at,
            expected_extract_id=extract_id,
            expected_published_at=published_at,
            maximum_age_seconds=REUSE_MAX_EXTRACT_AGE_SECONDS,
        )
        target = destination / generated.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(generated, target)
        target.chmod(0o444)
    return f"{extract_id}.sqlite"


def _publication_time(
    assets: Path,
    cell: str,
    runtime_output: Path,
    extract_output: Path,
    observed_at: str,
) -> str:
    runtime_file = runtime_output / "runtime.yaml"
    if not runtime_file.exists():
        existing = sorted(extract_output.glob("*.sqlite"))
        if not existing:
            return observed_at
        if len(existing) != 1:
            raise ProvisionError("invalid existing extract")
        try:
            publisher = _load_publisher(assets)
            metadata = publisher.validate_extract(
                existing[0],
                cell,
                observed_at=observed_at,
                maximum_age_seconds=REUSE_MAX_EXTRACT_AGE_SECONDS,
            )
            if existing[0].name != f"{metadata.extract_id}.sqlite":
                raise ProvisionError("invalid existing extract")
            return metadata.published_at
        except ProvisionError:
            raise
        except Exception:  # noqa: BLE001 - dependency errors become one refusal.
            raise ProvisionError("invalid existing extract") from None
    try:
        if runtime_file.is_symlink() or not runtime_file.is_file():
            raise ProvisionError("invalid existing extract")
        config = yaml.safe_load(runtime_file.read_text(encoding="utf-8"))
        profile = DIRECT[cell][0]
        if set(config["sourceExtracts"]) != {profile}:
            raise ProvisionError("invalid existing extract")
        bound_path = Path(config["sourceExtracts"][profile]["path"])
        if bound_path.parent != Path(f"/var/lib/registry-evidence/{cell}/extracts"):
            raise ProvisionError("invalid existing extract")
        extract_name = bound_path.name
        existing = extract_output / extract_name
        with sqlite3.connect(f"file:{existing}?mode=ro", uri=True) as connection:
            rows = connection.execute(
                "SELECT published_at, extract_id FROM evidence_extract"
            ).fetchall()
        if len(rows) != 1:
            raise ProvisionError("invalid existing extract")
        published_at, extract_id = rows[0]
        publisher = _load_publisher(assets)
        publisher.validate_extract(
            existing,
            cell,
            observed_at=observed_at,
            expected_extract_id=extract_id,
            expected_published_at=published_at,
            maximum_age_seconds=REUSE_MAX_EXTRACT_AGE_SECONDS,
        )
        if extract_name != f"{extract_id}.sqlite":
            raise ProvisionError("invalid existing extract")
        return published_at
    except ProvisionError:
        raise
    except Exception:  # noqa: BLE001 - dependency errors become one refusal.
        raise ProvisionError("invalid existing extract") from None


def _append_file(staged: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    destination.chmod(0o755)
    try:
        target = destination / staged.name
        if target.exists():
            if target.is_symlink() or _digest(target) != _digest(staged):
                raise ProvisionError("existing output mismatch")
            return
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
        with os.fdopen(descriptor, "wb") as output:
            output.write(staged.read_bytes())
            output.flush()
            os.fsync(output.fileno())
        target.chmod(0o444)
    finally:
        destination.chmod(0o555)


def _replace_extract_binding(
    runtime_output: Path,
    cell: str,
    previous_name: str,
    replacement_name: str,
) -> None:
    runtime_file = runtime_output / "runtime.yaml"
    try:
        if runtime_file.is_symlink() or not runtime_file.is_file():
            raise ProvisionError("invalid existing runtime")
        original = runtime_file.read_bytes()
        config = yaml.safe_load(original.decode("utf-8"))
        if config["listener"]["bindHost"] != EXPECTED_BIND_HOST:
            raise ProvisionError("invalid existing runtime")
        if set(config["sourceExtracts"]) != {DIRECT[cell][0]}:
            raise ProvisionError("invalid existing runtime")
        binding = config["sourceExtracts"][DIRECT[cell][0]]
        current = Path(binding["path"])
        if current.name != previous_name or current.parent != Path(
            f"/var/lib/registry-evidence/{cell}/extracts"
        ):
            raise ProvisionError("invalid existing runtime")
        binding["path"] = str(current.with_name(replacement_name))
        rendered = yaml.safe_dump(config, sort_keys=False).encode()
        runtime_output.chmod(0o755)
        rollback = runtime_output / f"runtime.rollback-{Path(previous_name).stem}.yaml"
        if rollback.exists():
            if (
                rollback.is_symlink()
                or not rollback.is_file()
                or rollback.read_bytes() != original
                or stat.S_IMODE(rollback.stat().st_mode) != 0o444
            ):
                raise ProvisionError("invalid existing runtime")
        else:
            rollback_descriptor = os.open(
                rollback, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444
            )
            with os.fdopen(rollback_descriptor, "wb") as output:
                output.write(original)
                output.flush()
                os.fsync(output.fileno())
            rollback.chmod(0o444)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".runtime-", suffix=".yaml", dir=runtime_output
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(rendered)
                output.flush()
                os.fsync(output.fileno())
            temporary.chmod(0o444)
            os.replace(temporary, runtime_file)
            directory_descriptor = os.open(runtime_output, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        finally:
            temporary.unlink(missing_ok=True)
    except ProvisionError:
        raise
    except (OSError, TypeError, KeyError, yaml.YAMLError):
        raise ProvisionError("invalid existing runtime") from None
    finally:
        try:
            runtime_output.chmod(0o555)
        except OSError:
            pass


def publish_extract(args: argparse.Namespace) -> None:
    assets = args.assets.resolve()
    verify_assets(assets)
    if not args.target.endswith("-evidence"):
        raise ProvisionError("invalid target")
    cell = args.target.removesuffix("-evidence")
    if cell not in DIRECT:
        raise ProvisionError("invalid target")
    runtime_output = args.runtime_output.resolve()
    extract_output = args.extract_output.resolve()
    now = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    previous_publication = _publication_time(
        assets,
        cell,
        runtime_output,
        extract_output,
        now,
    )
    previous_name = f"{_load_publisher(assets).timestamped_extract_id(cell, previous_publication)}.sqlite"
    with tempfile.TemporaryDirectory(
        prefix="solmara-extract-publication-"
    ) as temporary:
        staging = Path(temporary)
        replacement_name = _stage_extract(assets, cell, staging, now, now)
        if replacement_name == previous_name:
            raise ProvisionError("extract publication is not newer")
        _append_file(staging / replacement_name, extract_output)
    _replace_extract_binding(runtime_output, cell, previous_name, replacement_name)


def _stage_evidence(
    assets: Path,
    cell: str,
    secrets: Path,
    runtime: Path,
    secret_output: Path,
    extract_output: Path | None,
    bind_host: str,
    published_at: str,
    observed_at: str,
    mint_origin: str,
    relay_origin: str | None,
) -> None:
    source = assets / "evidence" / "cells" / cell
    _copy_tree(source, runtime)
    public = _public_jwk(_read_secret(secrets, "signing-public.jwk"), allow_rsa=False)
    bundle_config = runtime / "bundle" / "evidence.yaml"
    config = yaml.safe_load(bundle_config.read_text(encoding="utf-8"))
    config["signing"]["activePublicJwkFile"] = f"public-keys/{public['kid']}.jwk.json"
    _patch_evidence_origins(config, cell, mint_origin, relay_origin)
    bundle_config.chmod(0o644)
    bundle_config.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    bundle_config.chmod(0o444)
    _write(
        runtime / "bundle" / "public-keys" / f"{public['kid']}.jwk.json",
        json.dumps(public, indent=2, sort_keys=True).encode(),
        0o444,
    )
    extract_name = (
        _stage_extract(assets, cell, extract_output, published_at, observed_at)
        if extract_output is not None
        else None
    )
    runtime_file = runtime / "runtime.yaml"
    runtime_file.chmod(0o644)
    _patch_runtime(runtime_file, bind_host, extract_name)
    runtime_file.chmod(0o444)
    _write(
        secret_output / "audit-hmac-key", _hmac_secret(secrets, "audit-hmac-key"), 0o600
    )
    _write(
        secret_output / "subject-binding-hmac-key",
        _hmac_secret(secrets, "subject-binding-hmac-key"),
        0o600,
    )
    for client in CELL_CLIENTS[cell]:
        value = _read_secret(secrets, f"{client}-client-key")
        _private_client_jwk(value)
        _write(secret_output / f"{client}-client-key", value, 0o600)
        _write(secret_output / f"{client}-client-id", client.encode(), 0o600)
    _freeze_tree(runtime)
    for directory in [secret_output, *secret_output.rglob("*")]:
        if directory.is_dir():
            directory.chmod(0o700)


def _stage_mint(
    assets: Path,
    secrets: Path,
    runtime: Path,
    secret_output: Path,
    bind_host: str,
    mint_origin: str,
) -> None:
    public = _public_jwk(_read_secret(secrets, "signing-public.jwk"), allow_rsa=False)
    config = yaml.safe_load((assets / "mint" / "mint.yaml").read_text(encoding="utf-8"))
    _patch_mint_origin(config, mint_origin)
    config["listener"]["address"] = bind_host
    config["signing"]["activePublicJwkFile"] = f"public-keys/{public['kid']}.jwk.json"
    _write(
        runtime / "mint.yaml", yaml.safe_dump(config, sort_keys=False).encode(), 0o444
    )
    _write(
        runtime / "public-keys" / f"{public['kid']}.jwk.json",
        json.dumps(public, indent=2, sort_keys=True).encode(),
        0o444,
    )
    for client, (scope, purpose) in MINT_CLIENTS.items():
        key = _public_jwk(_read_secret(secrets, f"{client}-public.jwk"))
        registration = {
            "clientId": client,
            "principal": f"https://id.registrystack.org/solmara/client/{client}",
            "authorization": {"scopes": [scope], "claims": {"purpose": purpose}},
            "keys": [key],
        }
        _write(
            runtime / "clients" / f"{client}.yaml",
            yaml.safe_dump(registration, sort_keys=False).encode(),
            0o444,
        )
    demo = _public_jwk(
        _read_secret(secrets, "solmara-demo-client-public.jwk"), allow_rsa=False
    )
    registration = {
        "clientId": "solmara-demo",
        "principal": "https://id.registrystack.org/solmara/client/solmara-demo",
        "evidenceAudience": "https://id.registrystack.org/solmara/audience/demo-client",
        "requesterTags": ["solmara-demo"],
        "keys": [demo],
    }
    _write(
        runtime / "clients" / "solmara-demo.yaml",
        yaml.safe_dump(registration, sort_keys=False).encode(),
        0o444,
    )
    _write(
        secret_output / "audit-hmac-key", _hmac_secret(secrets, "audit-hmac-key"), 0o600
    )
    _freeze_tree(runtime)
    for directory in [secret_output, *secret_output.rglob("*")]:
        if directory.is_dir():
            directory.chmod(0o700)


def _provision_target(args: argparse.Namespace) -> None:
    assets, target = args.assets.resolve(), args.target
    verify_assets(assets)
    mint_origin = _validated_origin(args.mint_origin, MINT_ORIGIN)
    now = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    with tempfile.TemporaryDirectory(prefix="solmara-provision-") as temporary:
        root = Path(temporary)
        runtime = root / "runtime"
        source = root / "source"
        secret_output = root / "secrets"
        extracts = root / "extracts"
        if target.endswith("-relay"):
            authority = target.removesuffix("-relay")
            if (
                authority not in RELAYS
                or args.source_output is None
                or args.secret_output
                or args.extract_output
                or args.bind_host
                or args.relay_origin
            ):
                raise ProvisionError("invalid target")
            _stage_relay(assets, authority, runtime, source, mint_origin)
            _check_install_tree(source, args.source_output.resolve())
            _check_install_tree(runtime, args.runtime_output.resolve())
            _install_tree(source, args.source_output.resolve(), root_mode=0o555)
        elif target == "mint":
            if (
                args.secret_output is None
                or not args.bind_host
                or args.source_output
                or args.extract_output
                or args.relay_origin
            ):
                raise ProvisionError("invalid target")
            if args.bind_host != EXPECTED_BIND_HOST:
                raise ProvisionError("invalid bind host")
            mint_secrets = _provision_secret_inventory(target)
            if mint_secrets is None:
                raise ProvisionError("invalid target")
            _validate_secret_inventory(args.secrets.absolute(), mint_secrets)
            _stage_mint(
                assets,
                args.secrets.absolute(),
                runtime,
                secret_output,
                args.bind_host,
                mint_origin,
            )
            _check_secret_install_tree(secret_output, args.secret_output.resolve())
            _check_install_tree(runtime, args.runtime_output.resolve())
            _install_secret_tree(secret_output, args.secret_output.resolve())
        elif target.endswith("-evidence"):
            cell = target.removesuffix("-evidence")
            if (
                cell not in CELLS
                or args.secret_output is None
                or not args.bind_host
                or args.source_output
            ):
                raise ProvisionError("invalid target")
            if (cell in DIRECT) != (args.extract_output is not None):
                raise ProvisionError("invalid target")
            expected_relay_origin = RELAY_ORIGINS.get(cell)
            if (expected_relay_origin is None) != (args.relay_origin is None):
                raise ProvisionError("invalid origin")
            relay_origin = (
                _validated_origin(args.relay_origin, expected_relay_origin)
                if expected_relay_origin is not None
                else None
            )
            if args.bind_host != EXPECTED_BIND_HOST:
                raise ProvisionError("invalid bind host")
            cell_secrets = _provision_secret_inventory(target)
            if cell_secrets is None:
                raise ProvisionError("invalid target")
            _validate_secret_inventory(args.secrets.absolute(), cell_secrets)
            published_at = (
                _publication_time(
                    assets,
                    cell,
                    args.runtime_output.resolve(),
                    args.extract_output.resolve(),
                    now,
                )
                if cell in DIRECT
                else now
            )
            _stage_evidence(
                assets,
                cell,
                args.secrets.absolute(),
                runtime,
                secret_output,
                extracts if cell in DIRECT else None,
                args.bind_host,
                published_at,
                now,
                mint_origin,
                relay_origin,
            )
            runtime_preserve = _preserve_extract_rollback if cell in DIRECT else None
            _check_secret_install_tree(secret_output, args.secret_output.resolve())
            if cell in DIRECT:
                _check_install_tree(extracts, args.extract_output.resolve())
            _check_install_tree(
                runtime, args.runtime_output.resolve(), preserve=runtime_preserve
            )
            _install_secret_tree(secret_output, args.secret_output.resolve())
            if cell in DIRECT:
                _install_tree(extracts, args.extract_output.resolve(), root_mode=0o555)
        else:
            raise ProvisionError("invalid target")
        _install_tree(
            runtime,
            args.runtime_output.resolve(),
            root_mode=0o555,
            preserve=(
                _preserve_extract_rollback
                if target.endswith("-evidence")
                and target.removesuffix("-evidence") in DIRECT
                else None
            ),
        )


def provision(args: argparse.Namespace) -> None:
    expected = _provision_secret_inventory(args.target)
    if expected is None:
        if args.secrets is not None:
            raise ProvisionError("invalid target")
        _provision_target(args)
        return
    if args.secrets is None:
        raise ProvisionError("invalid target")
    secret_root = args.secrets.absolute()
    try:
        _confine_secret_inventory(secret_root)
        _provision_target(args)
    finally:
        _consume_secret_inventory(secret_root, expected)


def init_audit(destinations: list[Path], uid: int, gid: int) -> None:
    if not destinations or uid != 65532 or gid != 65532:
        raise ProvisionError("invalid audit target")
    for destination in destinations:
        metadata = destination.lstat()
        if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            raise ProvisionError("invalid audit target")
    for destination in destinations:
        os.chown(destination, uid, gid)
        os.chmod(destination, 0o700)


def parser() -> argparse.ArgumentParser:
    result = QuietParser(add_help=False)
    sub = result.add_subparsers(dest="command", required=True)
    ready = sub.add_parser("provision", add_help=False)
    ready.add_argument("--target", required=True)
    ready.add_argument("--assets", required=True, type=Path)
    ready.add_argument("--secrets", type=Path)
    ready.add_argument("--runtime-output", required=True, type=Path)
    ready.add_argument("--source-output", type=Path)
    ready.add_argument("--secret-output", type=Path)
    ready.add_argument("--extract-output", type=Path)
    ready.add_argument("--bind-host")
    ready.add_argument("--mint-origin", required=True)
    ready.add_argument("--relay-origin")
    publication = sub.add_parser("publish-extract", add_help=False)
    publication.add_argument("--target", required=True)
    publication.add_argument("--assets", required=True, type=Path)
    publication.add_argument("--runtime-output", required=True, type=Path)
    publication.add_argument("--extract-output", required=True, type=Path)
    audit = sub.add_parser("init-audit", add_help=False)
    audit.add_argument("--destination", action="append", required=True, type=Path)
    audit.add_argument("--uid", required=True, type=int)
    audit.add_argument("--gid", required=True, type=int)
    sub.add_parser("ready", add_help=False)
    return result


def main(argv: list[str] | None = None) -> int:
    os.umask(0o077)
    try:
        args = parser().parse_args(argv)
        if args.command == "provision":
            provision(args)
        elif args.command == "publish-extract":
            publish_extract(args)
        elif args.command == "init-audit":
            init_audit(args.destination, args.uid, args.gid)
    except Exception:  # noqa: BLE001 - the command boundary is deliberately value-free.
        print(GENERIC_ERROR, file=sys.stderr)
        return 1
    print(SUCCESS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
