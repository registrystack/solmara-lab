from __future__ import annotations

import base64
import contextlib
import importlib.util
import io
import json
import os
import stat
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "relay_workload_identity_agent.py"
SPEC = importlib.util.spec_from_file_location("relay_workload_identity_agent", SCRIPT)
assert SPEC and SPEC.loader
agent = importlib.util.module_from_spec(SPEC)
sys.modules["relay_workload_identity_agent"] = agent
SPEC.loader.exec_module(agent)


def b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def decode_segment(value: str) -> dict[str, object]:
    raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    document = json.loads(raw)
    assert isinstance(document, dict)
    return document


def private_jwk(
    *, kid: str = "test-workload-key"
) -> tuple[dict[str, str], Ed25519PrivateKey]:
    private_key = Ed25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(
        Encoding.Raw, PrivateFormat.Raw, NoEncryption()
    )
    public_bytes = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return (
        {
            "alg": "EdDSA",
            "crv": "Ed25519",
            "d": b64url(private_bytes),
            "kid": kid,
            "kty": "OKP",
            "x": b64url(public_bytes),
        },
        private_key,
    )


def identity_document(
    directory: Path,
    *,
    azp: str = "cra-notary",
    subject: str | None = None,
    kid_env: str = "TEST_WORKLOAD_PRIVATE_JWK",
    token_name: str = "relay-token",
    scopes: list[str] | None = None,
    token_uid: int | None = None,
    token_gid: int | None = None,
) -> dict[str, object]:
    document: dict[str, object] = {
        "audience": "registry-relay",
        "azp": azp,
        "subject": subject or azp,
        "scopes": scopes
        or [
            "registry:consult:cra-child-benefit",
            "registry:consult:cra-citizen-record",
        ],
        "token_file": str(directory / token_name),
        "private_jwk_env": kid_env,
    }
    if token_uid is not None:
        document["token_uid"] = token_uid
    if token_gid is not None:
        document["token_gid"] = token_gid
    return document


def valid_environment(directory: Path) -> tuple[dict[str, str], Ed25519PrivateKey]:
    jwk, private_key = private_jwk()
    environment = {
        "WORKLOAD_ISSUER": "http://127.0.0.1:8090",
        "WORKLOAD_IDENTITIES_JSON": json.dumps([identity_document(directory)]),
        "TEST_WORKLOAD_PRIVATE_JWK": json.dumps(jwk),
        "WORKLOAD_TOKEN_UID": str(os.getuid()),
        "WORKLOAD_TOKEN_GID": str(os.getgid()),
    }
    return environment, private_key


def add_esignet_identity(
    environment: dict[str, str], directory: Path
) -> Ed25519PrivateKey:
    jwk, private_key = private_jwk(kid="test-esignet-key")
    environment["TEST_ESIGNET_PRIVATE_JWK"] = json.dumps(jwk)
    identities = json.loads(environment["WORKLOAD_IDENTITIES_JSON"])
    identities.append(
        identity_document(
            directory,
            azp="solmara-esignet",
            kid_env="TEST_ESIGNET_PRIVATE_JWK",
            token_name="esignet-relay-token",
            scopes=["population:identity_release"],
            token_uid=os.getuid(),
            token_gid=os.getgid(),
        )
    )
    environment["WORKLOAD_IDENTITIES_JSON"] = json.dumps(identities)
    return private_key


class FakeClock:
    def __init__(self, value: int) -> None:
        self.value = value

    def __call__(self) -> float:
        return float(self.value)


class WorkloadIdentityAgentTests(unittest.TestCase):
    def test_each_identity_gets_exact_claims_and_its_own_signature(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            environment, notary_key = valid_environment(directory)
            esignet_key = add_esignet_identity(environment, directory)
            config = agent.Config.from_environ(environment)

            tokens = [
                agent._mint_token(config, identity, 1_700_000_000)[0]
                for identity in config.identities
            ]
            claims = []
            for token, expected_key in zip(
                tokens, (notary_key, esignet_key), strict=True
            ):
                encoded_header, encoded_claims, encoded_signature = token.split(".")
                signature = base64.urlsafe_b64decode(
                    encoded_signature + "=" * (-len(encoded_signature) % 4)
                )
                expected_key.public_key().verify(
                    signature, f"{encoded_header}.{encoded_claims}".encode("ascii")
                )
                claims.append(decode_segment(encoded_claims))

            self.assertEqual(claims[0]["azp"], "cra-notary")
            self.assertEqual(claims[0]["sub"], "cra-notary")
            self.assertEqual(
                claims[0]["scope"],
                "registry:consult:cra-child-benefit registry:consult:cra-citizen-record",
            )
            self.assertEqual(claims[1]["azp"], "solmara-esignet")
            self.assertEqual(claims[1]["sub"], "solmara-esignet")
            self.assertEqual(claims[1]["scope"], "population:identity_release")
            self.assertNotEqual(claims[0]["jti"], claims[1]["jti"])
            for token_claims in claims:
                self.assertEqual(token_claims["iss"], environment["WORKLOAD_ISSUER"])
                self.assertEqual(token_claims["aud"], "registry-relay")
                self.assertEqual(token_claims["iat"], 1_700_000_000)
                self.assertEqual(token_claims["nbf"], 1_700_000_000)
                self.assertEqual(token_claims["exp"], 1_700_000_300)

    def test_public_jwks_contains_every_distinct_public_key_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            environment, _ = valid_environment(directory)
            add_esignet_identity(environment, directory)
            config = agent.Config.from_environ(environment)

            document = agent.IdentityState(config).jwks_document()

            self.assertEqual(
                {key["kid"] for key in document["keys"]},
                {"test-workload-key", "test-esignet-key"},
            )
            for key in document["keys"]:
                self.assertEqual(set(key), {"alg", "crv", "kid", "kty", "x"})

    def test_atomic_rotation_publishes_mode_and_ownership_together(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            environment, _ = valid_environment(directory)
            config = agent.Config.from_environ(environment)
            identity = config.identities[0]
            identity.token_file.write_text("previous-token\n", encoding="ascii")
            os.chmod(identity.token_file, 0o644)
            state = agent.IdentityState(config, clock=FakeClock(1_700_000_000))
            original_replace = os.replace
            replace_observed = False

            def inspect_then_replace(source: str, destination: Path) -> None:
                nonlocal replace_observed
                replace_observed = True
                source_status = os.stat(source)
                self.assertEqual(stat.S_IMODE(source_status.st_mode), 0o600)
                self.assertEqual(source_status.st_uid, os.getuid())
                self.assertEqual(source_status.st_gid, os.getgid())
                self.assertEqual(
                    identity.token_file.read_text(encoding="ascii"), "previous-token\n"
                )
                original_replace(source, destination)

            with mock.patch.object(
                agent.os, "replace", side_effect=inspect_then_replace
            ):
                state.rotate()

            self.assertTrue(replace_observed)
            file_status = identity.token_file.stat()
            self.assertEqual(stat.S_IMODE(file_status.st_mode), 0o600)
            self.assertEqual(file_status.st_uid, os.getuid())
            self.assertEqual(file_status.st_gid, os.getgid())
            self.assertEqual(
                len(identity.token_file.read_text(encoding="ascii").split(".")), 3
            )
            self.assertTrue(state.ready())

    def test_readiness_requires_every_current_regular_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            environment, _ = valid_environment(directory)
            add_esignet_identity(environment, directory)
            clock = FakeClock(1_700_000_000)
            config = agent.Config.from_environ(environment)
            state = agent.IdentityState(config, clock=clock)
            state.rotate()
            self.assertTrue(state.ready())

            config.identities[1].token_file.write_text(
                "not-the-current-token\n", encoding="ascii"
            )
            self.assertFalse(state.ready())
            state.rotate()
            self.assertTrue(state.ready())

            config.identities[1].token_file.write_bytes(b"")
            self.assertFalse(state.ready())
            state.rotate()
            self.assertTrue(state.ready())

            config.identities[1].token_file.unlink()
            config.identities[1].token_file.symlink_to(config.identities[0].token_file)
            self.assertFalse(state.ready())

            config.identities[1].token_file.unlink()
            state.rotate()
            clock.value += config.token_ttl_seconds
            self.assertFalse(state.ready())

    def test_rotation_occurs_only_inside_the_configured_expiry_window(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment, _ = valid_environment(Path(temporary_directory))
            environment["WORKLOAD_TOKEN_TTL_SECONDS"] = "120"
            environment["WORKLOAD_ROTATE_BEFORE_SECONDS"] = "30"
            environment["WORKLOAD_ROTATION_INTERVAL_SECONDS"] = "5"
            config = agent.Config.from_environ(environment)
            identity = config.identities[0]
            clock = FakeClock(1_700_000_000)
            state = agent.IdentityState(config, clock=clock)
            state.rotate()
            first_claims = decode_segment(
                identity.token_file.read_text(encoding="ascii").strip().split(".")[1]
            )

            clock.value += 89
            self.assertFalse(state.rotate_if_due())
            clock.value += 1
            self.assertTrue(state.rotate_if_due())
            rotated_claims = decode_segment(
                identity.token_file.read_text(encoding="ascii").strip().split(".")[1]
            )

            self.assertNotEqual(first_claims["jti"], rotated_claims["jti"])
            self.assertEqual(rotated_claims["iat"], 1_700_000_090)
            self.assertEqual(rotated_claims["exp"], 1_700_000_210)

    def test_health_and_jwks_reflect_all_published_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            environment, _ = valid_environment(directory)
            add_esignet_identity(environment, directory)
            config = agent.Config.from_environ(environment)
            state = agent.IdentityState(config, clock=FakeClock(1_700_000_000))
            server = agent.AgentHTTPServer(("127.0.0.1", 0), state)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                status, health = self._get_json(f"{base_url}/health")
                self.assertEqual(status, 503)
                self.assertEqual(health, {"status": "not_ready"})

                status, jwks = self._get_json(f"{base_url}/.well-known/jwks.json")
                self.assertEqual(status, 200)
                self.assertEqual(len(jwks["keys"]), 2)
                self.assertTrue(all("d" not in key for key in jwks["keys"]))

                state.rotate()
                status, health = self._get_json(f"{base_url}/health")
                self.assertEqual(status, 200)
                self.assertEqual(health, {"status": "ready"})

                config.identities[1].token_file.write_bytes(b"")
                status, health = self._get_json(f"{base_url}/health")
                self.assertEqual(status, 503)
                self.assertEqual(health, {"status": "not_ready"})

                status, missing = self._get_json(f"{base_url}/other")
                self.assertEqual(status, 404)
                self.assertEqual(missing, {"error": "not_found"})
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def test_configuration_defaults_and_per_identity_ownership_override(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            environment, _ = valid_environment(directory)
            del environment["WORKLOAD_TOKEN_UID"]
            del environment["WORKLOAD_TOKEN_GID"]
            add_esignet_identity(environment, directory)
            identities = json.loads(environment["WORKLOAD_IDENTITIES_JSON"])
            identities[1]["token_uid"] = 1001
            identities[1]["token_gid"] = 1001
            environment["WORKLOAD_IDENTITIES_JSON"] = json.dumps(identities)

            config = agent.Config.from_environ(environment)

            self.assertEqual(config.identities[0].token_uid, 65534)
            self.assertEqual(config.identities[0].token_gid, 65534)
            self.assertEqual(config.identities[1].token_uid, 1001)
            self.assertEqual(config.identities[1].token_gid, 1001)

    @unittest.skipUnless(os.geteuid() == 0, "requires root to verify distinct owners")
    def test_rotation_applies_distinct_configured_owners(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            environment, _ = valid_environment(directory)
            add_esignet_identity(environment, directory)
            identities = json.loads(environment["WORKLOAD_IDENTITIES_JSON"])
            identities[0]["token_uid"] = 65534
            identities[0]["token_gid"] = 65534
            identities[1]["token_uid"] = 1001
            identities[1]["token_gid"] = 1001
            environment["WORKLOAD_IDENTITIES_JSON"] = json.dumps(identities)
            config = agent.Config.from_environ(environment)

            state = agent.IdentityState(config, clock=FakeClock(1_700_000_000))
            state.rotate()

            self.assertEqual(
                (
                    config.identities[0].token_file.stat().st_uid,
                    config.identities[0].token_file.stat().st_gid,
                ),
                (65534, 65534),
            )
            self.assertEqual(
                (
                    config.identities[1].token_file.stat().st_uid,
                    config.identities[1].token_file.stat().st_gid,
                ),
                (1001, 1001),
            )
            self.assertTrue(state.ready())

    def test_configuration_rejects_unsafe_or_ambiguous_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            baseline, _ = valid_environment(directory)
            jwk = json.loads(baseline["TEST_WORKLOAD_PRIVATE_JWK"])
            mismatched_jwk, _ = private_jwk()

            def identities(change: dict[str, object]) -> str:
                document = identity_document(directory)
                document.update(change)
                return json.dumps([document])

            cases: dict[str, dict[str, str | None]] = {
                "non_loopback_bind": {"WORKLOAD_BIND_HOST": "0.0.0.0"},
                "non_loopback_issuer": {"WORKLOAD_ISSUER": "http://localhost:8090"},
                "https_issuer": {"WORKLOAD_ISSUER": "https://127.0.0.1:8090"},
                "malformed_issuer": {"WORKLOAD_ISSUER": "http://["},
                "issuer_path": {"WORKLOAD_ISSUER": "http://127.0.0.1:8090/issuer"},
                "issuer_port_mismatch": {"WORKLOAD_PORT": "8091"},
                "blank_audience": {
                    "WORKLOAD_IDENTITIES_JSON": identities({"audience": ""})
                },
                "spaced_azp": {
                    "WORKLOAD_IDENTITIES_JSON": identities({"azp": "cra notary"})
                },
                "duplicate_scope": {
                    "WORKLOAD_IDENTITIES_JSON": identities(
                        {"scopes": ["registry:read", "registry:read"]}
                    )
                },
                "empty_scope_entry": {
                    "WORKLOAD_IDENTITIES_JSON": identities(
                        {"scopes": ["registry:read", ""]}
                    )
                },
                "relative_token_file": {
                    "WORKLOAD_IDENTITIES_JSON": identities(
                        {"token_file": "relay-token"}
                    )
                },
                "missing_token_parent": {
                    "WORKLOAD_IDENTITIES_JSON": identities(
                        {"token_file": str(directory / "missing" / "relay-token")}
                    )
                },
                "ttl_too_long": {"WORKLOAD_TOKEN_TTL_SECONDS": "901"},
                "rotation_too_late": {
                    "WORKLOAD_TOKEN_TTL_SECONDS": "30",
                    "WORKLOAD_ROTATE_BEFORE_SECONDS": "26",
                },
                "rotation_poll_too_slow": {
                    "WORKLOAD_ROTATE_BEFORE_SECONDS": "10",
                    "WORKLOAD_ROTATION_INTERVAL_SECONDS": "11",
                },
                "negative_uid": {
                    "WORKLOAD_IDENTITIES_JSON": identities({"token_uid": -1})
                },
                "boolean_gid": {
                    "WORKLOAD_IDENTITIES_JSON": identities({"token_gid": True})
                },
                "bad_key_environment_name": {
                    "WORKLOAD_IDENTITIES_JSON": identities(
                        {"private_jwk_env": "bad-name"}
                    )
                },
                "missing_key_environment": {"TEST_WORKLOAD_PRIVATE_JWK": None},
                "wrong_curve": {
                    "TEST_WORKLOAD_PRIVATE_JWK": json.dumps({**jwk, "crv": "X25519"})
                },
                "unsupported_key_field": {
                    "TEST_WORKLOAD_PRIVATE_JWK": json.dumps(
                        {**jwk, "key_ops": ["sign"]}
                    )
                },
                "mismatched_public_key": {
                    "TEST_WORKLOAD_PRIVATE_JWK": json.dumps(
                        {**jwk, "x": mismatched_jwk["x"]}
                    )
                },
                "duplicate_key_field": {
                    "TEST_WORKLOAD_PRIVATE_JWK": (
                        '{"kty":"OKP","kty":"OKP","crv":"Ed25519",'
                        '"alg":"EdDSA","kid":"key","x":"a","d":"a"}'
                    )
                },
                "empty_identity_list": {"WORKLOAD_IDENTITIES_JSON": "[]"},
                "too_many_identities": {
                    "WORKLOAD_IDENTITIES_JSON": json.dumps(
                        [identity_document(directory)] * (agent.MAX_IDENTITIES + 1)
                    )
                },
                "unsupported_identity_field": {
                    "WORKLOAD_IDENTITIES_JSON": identities({"name": "notary"})
                },
                "duplicate_identity_field": {
                    "WORKLOAD_IDENTITIES_JSON": (
                        '[{"audience":"registry-relay","audience":"other"}]'
                    )
                },
            }
            for name, changes in cases.items():
                with self.subTest(name=name):
                    environment = dict(baseline)
                    for key, value in changes.items():
                        if value is None:
                            environment.pop(key, None)
                        else:
                            environment[key] = value
                    with self.assertRaises(agent.ConfigurationError):
                        agent.Config.from_environ(environment)

    def test_configuration_rejects_duplicate_identity_bindings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            baseline, _ = valid_environment(directory)
            second_jwk, _ = private_jwk(kid="second-key")
            baseline["SECOND_PRIVATE_JWK"] = json.dumps(second_jwk)
            cloned_key = json.loads(baseline["TEST_WORKLOAD_PRIVATE_JWK"])
            cloned_key["kid"] = "cloned-key-id"
            baseline["CLONED_PRIVATE_JWK"] = json.dumps(cloned_key)
            base = identity_document(directory)
            independent = identity_document(
                directory,
                azp="second-client",
                kid_env="SECOND_PRIVATE_JWK",
                token_name="second-token",
            )
            duplicate_cases = {
                "azp": {**independent, "azp": base["azp"]},
                "subject": {**independent, "subject": base["subject"]},
                "kid": {**independent, "private_jwk_env": "TEST_WORKLOAD_PRIVATE_JWK"},
                "public key": {
                    **independent,
                    "private_jwk_env": "CLONED_PRIVATE_JWK",
                },
                "token_file": {**independent, "token_file": base["token_file"]},
            }
            for field, duplicate in duplicate_cases.items():
                with self.subTest(field=field):
                    environment = dict(baseline)
                    environment["WORKLOAD_IDENTITIES_JSON"] = json.dumps(
                        [base, duplicate]
                    )
                    with self.assertRaisesRegex(
                        agent.ConfigurationError, rf"{field} values must be unique"
                    ):
                        agent.Config.from_environ(environment)

    def test_main_does_not_echo_rejected_key_material(self) -> None:
        marker = "private-key-material-must-not-appear"
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment, _ = valid_environment(Path(temporary_directory))
            environment["TEST_WORKLOAD_PRIVATE_JWK"] = marker
            stderr = io.StringIO()
            with mock.patch.dict(os.environ, environment, clear=True):
                with contextlib.redirect_stderr(stderr):
                    exit_code = agent.main()

            self.assertEqual(exit_code, 2)
            self.assertNotIn(marker, stderr.getvalue())
            self.assertEqual(
                stderr.getvalue(),
                "workload identity agent configuration rejected: "
                "private JWK is not valid JSON\n",
            )

    def _get_json(self, url: str) -> tuple[int, dict[str, object]]:
        try:
            response = urllib.request.urlopen(url, timeout=2)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            document = json.loads(response.read())
            return response.status, document


if __name__ == "__main__":
    unittest.main()
