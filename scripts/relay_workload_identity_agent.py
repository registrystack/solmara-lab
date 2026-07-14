#!/usr/bin/env python3
"""Issue a Relay workload token for a co-located Notary.

The agent binds only to IPv4 loopback. It publishes the public half of one
Ed25519 JWK and atomically maintains a short-lived access token in a shared
file. The private JWK is read indirectly: WORKLOAD_PRIVATE_JWK_ENV names the
environment variable that contains the JWK JSON.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import re
import secrets
import signal
import stat
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Never, cast
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


LOOPBACK_HOST = "127.0.0.1"
DEFAULT_PORT = 8090
DEFAULT_TOKEN_TTL_SECONDS = 300
DEFAULT_ROTATE_BEFORE_SECONDS = 60
DEFAULT_ROTATION_INTERVAL_SECONDS = 5
DEFAULT_TOKEN_UID = 65534
DEFAULT_TOKEN_GID = 65534

MAX_JWK_BYTES = 16 * 1024
MAX_TEXT_LENGTH = 256
MAX_PATH_LENGTH = 4096
MAX_SCOPE_COUNT = 32
MAX_SCOPE_LENGTH = 256
MAX_TOKEN_TTL_SECONDS = 900
MAX_ROTATION_INTERVAL_SECONDS = 60
MAX_ID = 2_147_483_647

ENV_NAME_PATTERN = re.compile(r"[A-Z][A-Z0-9_]{0,127}\Z")
TOKEN_VALUE_PATTERN = re.compile(r"[\x21-\x7e]+\Z")
BASE64URL_PATTERN = re.compile(r"[A-Za-z0-9_-]+\Z")


class ConfigurationError(ValueError):
    """Raised when workload identity configuration is unsafe or incomplete."""


def _reject_constant(_value: str) -> Never:
    raise ConfigurationError("JWK JSON contains a non-finite number")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ConfigurationError("JWK JSON contains a duplicate field")
        result[key] = value
    return result


def _required_text(
    environ: Mapping[str, str],
    name: str,
    *,
    maximum: int = MAX_TEXT_LENGTH,
) -> str:
    value = environ.get(name)
    if value is None or not value or len(value) > maximum:
        raise ConfigurationError(f"{name} is missing or outside its size bound")
    return value


def _bounded_integer(
    environ: Mapping[str, str],
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    raw = environ.get(name, str(default))
    if not raw or len(raw) > 10 or not raw.isascii() or not raw.isdecimal():
        raise ConfigurationError(f"{name} must be a bounded decimal integer")
    value = int(raw)
    if value < minimum or value > maximum:
        raise ConfigurationError(f"{name} is outside its allowed range")
    return value


def _token_value(environ: Mapping[str, str], name: str) -> str:
    value = _required_text(environ, name)
    if TOKEN_VALUE_PATTERN.fullmatch(value) is None:
        raise ConfigurationError(f"{name} must contain visible ASCII without spaces")
    return value


def _decode_base64url(value: object, field: str) -> bytes:
    if not isinstance(value, str) or BASE64URL_PATTERN.fullmatch(value) is None:
        raise ConfigurationError(f"private JWK {field} is not base64url")
    try:
        raw = base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
        )
    except (binascii.Error, ValueError) as error:
        raise ConfigurationError(f"private JWK {field} is not base64url") from error
    if _base64url(raw) != value:
        raise ConfigurationError(f"private JWK {field} is not canonical base64url")
    return raw


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


@dataclass(frozen=True)
class KeyMaterial:
    private_key: Ed25519PrivateKey
    public_jwk: dict[str, str]

    @classmethod
    def from_json(cls, encoded: str) -> KeyMaterial:
        if not encoded or len(encoded.encode("utf-8")) > MAX_JWK_BYTES:
            raise ConfigurationError("private JWK is missing or outside its size bound")
        try:
            document = json.loads(
                encoded,
                object_pairs_hook=_unique_object,
                parse_constant=_reject_constant,
            )
        except (json.JSONDecodeError, UnicodeError) as error:
            raise ConfigurationError("private JWK is not valid JSON") from error
        if not isinstance(document, dict):
            raise ConfigurationError("private JWK must be a JSON object")

        allowed_fields = {"alg", "crv", "d", "kid", "kty", "use", "x"}
        if set(document) - allowed_fields:
            raise ConfigurationError("private JWK contains unsupported fields")
        if document.get("kty") != "OKP":
            raise ConfigurationError("private JWK kty must be OKP")
        if document.get("crv") != "Ed25519":
            raise ConfigurationError("private JWK crv must be Ed25519")
        if document.get("alg") != "EdDSA":
            raise ConfigurationError("private JWK alg must be EdDSA")
        if document.get("use") not in (None, "sig"):
            raise ConfigurationError("private JWK use must be sig when present")

        kid = document.get("kid")
        if (
            not isinstance(kid, str)
            or not kid
            or len(kid) > MAX_TEXT_LENGTH
            or TOKEN_VALUE_PATTERN.fullmatch(kid) is None
        ):
            raise ConfigurationError("private JWK kid is invalid")

        private_bytes = _decode_base64url(document.get("d"), "d")
        public_bytes = _decode_base64url(document.get("x"), "x")
        if len(private_bytes) != 32 or len(public_bytes) != 32:
            raise ConfigurationError("private JWK key material must be 32 bytes")
        private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
        derived_public = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        if not secrets.compare_digest(derived_public, public_bytes):
            raise ConfigurationError("private JWK public and private values do not match")

        public_jwk = {
            "alg": "EdDSA",
            "crv": "Ed25519",
            "kid": kid,
            "kty": "OKP",
            "x": document["x"],
        }
        if document.get("use") == "sig":
            public_jwk["use"] = "sig"
        return cls(private_key=private_key, public_jwk=public_jwk)


@dataclass(frozen=True)
class Config:
    bind_host: str
    port: int
    issuer: str
    audience: str
    azp: str
    subject: str
    scope: str
    token_file: Path
    token_ttl_seconds: int
    rotate_before_seconds: int
    rotation_interval_seconds: int
    token_uid: int
    token_gid: int
    key_material: KeyMaterial

    @classmethod
    def from_environ(cls, environ: Mapping[str, str]) -> Config:
        bind_host = environ.get("WORKLOAD_BIND_HOST", LOOPBACK_HOST)
        if bind_host != LOOPBACK_HOST:
            raise ConfigurationError("WORKLOAD_BIND_HOST must be IPv4 loopback")
        port = _bounded_integer(
            environ, "WORKLOAD_PORT", DEFAULT_PORT, minimum=1, maximum=65535
        )

        try:
            issuer = _required_text(environ, "WORKLOAD_ISSUER")
            parsed_issuer = urlsplit(issuer)
            issuer_port = parsed_issuer.port
        except ValueError as error:
            raise ConfigurationError("WORKLOAD_ISSUER is not a valid URL") from error
        if (
            parsed_issuer.scheme != "http"
            or parsed_issuer.hostname != bind_host
            or issuer_port != port
            or parsed_issuer.netloc != f"{bind_host}:{port}"
            or parsed_issuer.path
            or parsed_issuer.query
            or parsed_issuer.fragment
            or parsed_issuer.username is not None
            or parsed_issuer.password is not None
        ):
            raise ConfigurationError(
                "WORKLOAD_ISSUER must exactly match the configured loopback listener"
            )

        audience = _token_value(environ, "WORKLOAD_AUDIENCE")
        azp = _token_value(environ, "WORKLOAD_AZP")
        subject = _token_value(environ, "WORKLOAD_SUB")
        scope = _required_text(
            environ,
            "WORKLOAD_SCOPE",
            maximum=MAX_SCOPE_COUNT * (MAX_SCOPE_LENGTH + 1),
        )
        scopes = scope.split(" ")
        if (
            not scopes
            or len(scopes) > MAX_SCOPE_COUNT
            or " ".join(scopes) != scope
            or len(set(scopes)) != len(scopes)
            or any(
                not item
                or len(item) > MAX_SCOPE_LENGTH
                or TOKEN_VALUE_PATTERN.fullmatch(item) is None
                for item in scopes
            )
        ):
            raise ConfigurationError("WORKLOAD_SCOPE is not a bounded scope list")

        token_file_raw = _required_text(
            environ, "WORKLOAD_TOKEN_FILE", maximum=MAX_PATH_LENGTH
        )
        token_file = Path(token_file_raw)
        if (
            not token_file.is_absolute()
            or ".." in token_file.parts
            or os.path.normpath(token_file_raw) != token_file_raw
            or not token_file.name
            or not token_file.parent.is_dir()
        ):
            raise ConfigurationError("WORKLOAD_TOKEN_FILE is not a safe writable target")

        token_ttl_seconds = _bounded_integer(
            environ,
            "WORKLOAD_TOKEN_TTL_SECONDS",
            DEFAULT_TOKEN_TTL_SECONDS,
            minimum=30,
            maximum=MAX_TOKEN_TTL_SECONDS,
        )
        rotate_before_seconds = _bounded_integer(
            environ,
            "WORKLOAD_ROTATE_BEFORE_SECONDS",
            DEFAULT_ROTATE_BEFORE_SECONDS,
            minimum=5,
            maximum=token_ttl_seconds - 5,
        )
        rotation_interval_seconds = _bounded_integer(
            environ,
            "WORKLOAD_ROTATION_INTERVAL_SECONDS",
            DEFAULT_ROTATION_INTERVAL_SECONDS,
            minimum=1,
            maximum=min(MAX_ROTATION_INTERVAL_SECONDS, rotate_before_seconds),
        )
        token_uid = _bounded_integer(
            environ,
            "WORKLOAD_TOKEN_UID",
            DEFAULT_TOKEN_UID,
            minimum=0,
            maximum=MAX_ID,
        )
        token_gid = _bounded_integer(
            environ,
            "WORKLOAD_TOKEN_GID",
            DEFAULT_TOKEN_GID,
            minimum=0,
            maximum=MAX_ID,
        )

        key_environment_name = _required_text(
            environ, "WORKLOAD_PRIVATE_JWK_ENV", maximum=128
        )
        if ENV_NAME_PATTERN.fullmatch(key_environment_name) is None:
            raise ConfigurationError("WORKLOAD_PRIVATE_JWK_ENV is not a valid variable name")
        key_material = KeyMaterial.from_json(
            _required_text(environ, key_environment_name, maximum=MAX_JWK_BYTES)
        )

        return cls(
            bind_host=bind_host,
            port=port,
            issuer=issuer,
            audience=audience,
            azp=azp,
            subject=subject,
            scope=scope,
            token_file=token_file,
            token_ttl_seconds=token_ttl_seconds,
            rotate_before_seconds=rotate_before_seconds,
            rotation_interval_seconds=rotation_interval_seconds,
            token_uid=token_uid,
            token_gid=token_gid,
            key_material=key_material,
        )


def _encode_json(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _mint_token(config: Config, issued_at: int) -> tuple[str, int]:
    expires_at = issued_at + config.token_ttl_seconds
    header = {
        "alg": "EdDSA",
        "kid": config.key_material.public_jwk["kid"],
        "typ": "at+jwt",
    }
    claims = {
        "aud": config.audience,
        "azp": config.azp,
        "exp": expires_at,
        "iat": issued_at,
        "iss": config.issuer,
        "jti": secrets.token_urlsafe(18),
        "nbf": issued_at,
        "scope": config.scope,
        "sub": config.subject,
    }
    signing_input = b".".join(
        (
            _base64url(_encode_json(header)).encode(),
            _base64url(_encode_json(claims)).encode(),
        )
    )
    signature = config.key_material.private_key.sign(signing_input)
    return f"{signing_input.decode('ascii')}.{_base64url(signature)}", expires_at


def _atomic_write_token(path: Path, token: str, *, uid: int, gid: int) -> None:
    target_directory = str(path.parent)
    descriptor, temporary_path = tempfile.mkstemp(
        dir=target_directory, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        os.fchmod(descriptor, 0o600)
        os.fchown(descriptor, uid, gid)
        with os.fdopen(descriptor, "wb", closefd=True) as output:
            descriptor = -1
            output.write(token.encode("ascii"))
            output.write(b"\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, path)
        temporary_path = ""
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        directory_descriptor = os.open(target_directory, directory_flags)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_path:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass


class IdentityState:
    def __init__(self, config: Config, *, clock: Callable[[], float] = time.time) -> None:
        self.config = config
        self._clock = clock
        self._expires_at = 0
        self._lock = threading.RLock()

    def jwks_document(self) -> dict[str, list[dict[str, str]]]:
        return {"keys": [dict(self.config.key_material.public_jwk)]}

    def rotate(self) -> None:
        with self._lock:
            issued_at = int(self._clock())
            token, expires_at = _mint_token(self.config, issued_at)
            _atomic_write_token(
                self.config.token_file,
                token,
                uid=self.config.token_uid,
                gid=self.config.token_gid,
            )
            self._expires_at = expires_at

    def rotate_if_due(self) -> bool:
        with self._lock:
            if int(self._clock()) < self._expires_at - self.config.rotate_before_seconds:
                return False
            self.rotate()
            return True

    def ready(self) -> bool:
        with self._lock:
            if (
                not self.config.key_material.public_jwk
                or self._expires_at <= int(self._clock())
            ):
                return False
            try:
                file_status = os.lstat(self.config.token_file)
            except OSError:
                return False
            return (
                stat.S_ISREG(file_status.st_mode)
                and stat.S_IMODE(file_status.st_mode) == 0o600
                and file_status.st_size > 0
                and file_status.st_uid == self.config.token_uid
                and file_status.st_gid == self.config.token_gid
            )


class AgentHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        state: IdentityState,
    ) -> None:
        self.identity_state = state
        super().__init__(server_address, AgentRequestHandler)


class AgentRequestHandler(BaseHTTPRequestHandler):
    server_version = "solmara-workload-identity"
    sys_version = ""

    def do_GET(self) -> None:  # noqa: N802
        server = cast(AgentHTTPServer, self.server)
        if self.path == "/.well-known/jwks.json":
            self._send_json(HTTPStatus.OK, server.identity_state.jwks_document())
            return
        if self.path == "/health":
            ready = server.identity_state.ready()
            self._send_json(
                HTTPStatus.OK if ready else HTTPStatus.SERVICE_UNAVAILABLE,
                {"status": "ready" if ready else "not_ready"},
            )
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def _send_json(self, status_code: HTTPStatus, document: object) -> None:
        body = _encode_json(document)
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *args: object) -> None:
        return


def _rotation_loop(state: IdentityState, stop_event: threading.Event) -> None:
    while not stop_event.wait(state.config.rotation_interval_seconds):
        try:
            state.rotate_if_due()
        except Exception:
            # Health becomes not ready when the last published token expires or
            # is no longer a correctly owned, nonempty regular file.
            continue


def serve(config: Config) -> None:
    state = IdentityState(config)
    state.rotate()
    stop_event = threading.Event()
    server = AgentHTTPServer((config.bind_host, config.port), state)
    rotation_thread = threading.Thread(
        target=_rotation_loop,
        args=(state, stop_event),
        name="token-rotation",
        daemon=True,
    )
    rotation_thread.start()

    def request_stop(_signal_number: int, _frame: object) -> None:
        stop_event.set()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        stop_event.set()
        server.server_close()
        rotation_thread.join(timeout=config.rotation_interval_seconds + 1)


def main() -> int:
    try:
        config = Config.from_environ(os.environ)
        serve(config)
    except ConfigurationError as error:
        print(f"workload identity agent configuration rejected: {error}", file=sys.stderr)
        return 2
    except Exception:
        print("workload identity agent stopped after an operational failure", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
