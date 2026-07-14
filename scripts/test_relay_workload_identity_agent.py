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


def private_jwk(*, kid: str = "test-workload-key") -> tuple[dict[str, str], Ed25519PrivateKey]:
    private_key = Ed25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
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


def valid_environment(directory: Path) -> tuple[dict[str, str], Ed25519PrivateKey]:
    jwk, private_key = private_jwk()
    environment = {
        "WORKLOAD_ISSUER": "http://127.0.0.1:8090",
        "WORKLOAD_AUDIENCE": "registry-relay",
        "WORKLOAD_AZP": "cra-notary",
        "WORKLOAD_SUB": "cra-notary",
        "WORKLOAD_SCOPE": (
            "registry:consult:cra-child-benefit registry:consult:cra-citizen-record"
        ),
        "WORKLOAD_TOKEN_FILE": str(directory / "relay-token"),
        "WORKLOAD_PRIVATE_JWK_ENV": "TEST_WORKLOAD_PRIVATE_JWK",
        "TEST_WORKLOAD_PRIVATE_JWK": json.dumps(jwk),
        "WORKLOAD_TOKEN_UID": str(os.getuid()),
        "WORKLOAD_TOKEN_GID": str(os.getgid()),
    }
    return environment, private_key


class FakeClock:
    def __init__(self, value: int) -> None:
        self.value = value

    def __call__(self) -> float:
        return float(self.value)


class WorkloadIdentityAgentTests(unittest.TestCase):
    def test_minted_token_has_exact_claims_and_valid_ed25519_signature(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment, private_key = valid_environment(Path(temporary_directory))
            config = agent.Config.from_environ(environment)
            token, expires_at = agent._mint_token(config, 1_700_000_000)

            encoded_header, encoded_claims, encoded_signature = token.split(".")
            header = decode_segment(encoded_header)
            claims = decode_segment(encoded_claims)
            signature = base64.urlsafe_b64decode(
                encoded_signature + "=" * (-len(encoded_signature) % 4)
            )
            private_key.public_key().verify(
                signature, f"{encoded_header}.{encoded_claims}".encode("ascii")
            )

            self.assertEqual(
                header,
                {"alg": "EdDSA", "kid": "test-workload-key", "typ": "at+jwt"},
            )
            self.assertEqual(claims["iss"], environment["WORKLOAD_ISSUER"])
            self.assertEqual(claims["aud"], environment["WORKLOAD_AUDIENCE"])
            self.assertEqual(claims["azp"], environment["WORKLOAD_AZP"])
            self.assertEqual(claims["sub"], environment["WORKLOAD_SUB"])
            self.assertEqual(claims["scope"], environment["WORKLOAD_SCOPE"])
            self.assertEqual(claims["iat"], 1_700_000_000)
            self.assertEqual(claims["nbf"], 1_700_000_000)
            self.assertEqual(claims["exp"], 1_700_000_300)
            self.assertEqual(expires_at, 1_700_000_300)
            self.assertIsInstance(claims["jti"], str)
            self.assertGreater(len(str(claims["jti"])), 16)

    def test_public_jwks_excludes_private_key_material(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment, _ = valid_environment(Path(temporary_directory))
            config = agent.Config.from_environ(environment)

            document = agent.IdentityState(config).jwks_document()

            self.assertEqual(len(document["keys"]), 1)
            self.assertEqual(
                set(document["keys"][0]), {"alg", "crv", "kid", "kty", "x"}
            )
            self.assertEqual(document["keys"][0]["kty"], "OKP")
            self.assertEqual(document["keys"][0]["crv"], "Ed25519")

    def test_atomic_rotation_publishes_mode_and_ownership_together(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            environment, _ = valid_environment(directory)
            config = agent.Config.from_environ(environment)
            config.token_file.write_text("previous-token\n", encoding="ascii")
            os.chmod(config.token_file, 0o644)
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
                    config.token_file.read_text(encoding="ascii"), "previous-token\n"
                )
                original_replace(source, destination)

            with mock.patch.object(agent.os, "replace", side_effect=inspect_then_replace):
                state.rotate()

            self.assertTrue(replace_observed)
            file_status = config.token_file.stat()
            self.assertEqual(stat.S_IMODE(file_status.st_mode), 0o600)
            self.assertEqual(file_status.st_uid, os.getuid())
            self.assertEqual(file_status.st_gid, os.getgid())
            self.assertEqual(len(config.token_file.read_text(encoding="ascii").split(".")), 3)
            self.assertTrue(state.ready())

    def test_rotation_occurs_only_inside_the_configured_expiry_window(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment, _ = valid_environment(Path(temporary_directory))
            environment["WORKLOAD_TOKEN_TTL_SECONDS"] = "120"
            environment["WORKLOAD_ROTATE_BEFORE_SECONDS"] = "30"
            environment["WORKLOAD_ROTATION_INTERVAL_SECONDS"] = "5"
            config = agent.Config.from_environ(environment)
            clock = FakeClock(1_700_000_000)
            state = agent.IdentityState(config, clock=clock)
            state.rotate()
            first_claims = decode_segment(
                config.token_file.read_text(encoding="ascii").strip().split(".")[1]
            )

            clock.value += 89
            self.assertFalse(state.rotate_if_due())
            clock.value += 1
            self.assertTrue(state.rotate_if_due())
            rotated_claims = decode_segment(
                config.token_file.read_text(encoding="ascii").strip().split(".")[1]
            )

            self.assertNotEqual(first_claims["jti"], rotated_claims["jti"])
            self.assertEqual(rotated_claims["iat"], 1_700_000_090)
            self.assertEqual(rotated_claims["exp"], 1_700_000_210)

    def test_health_and_jwks_reflect_published_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment, _ = valid_environment(Path(temporary_directory))
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
                self.assertEqual(len(jwks["keys"]), 1)
                self.assertNotIn("d", jwks["keys"][0])

                state.rotate()
                status, health = self._get_json(f"{base_url}/health")
                self.assertEqual(status, 200)
                self.assertEqual(health, {"status": "ready"})

                config.token_file.write_bytes(b"")
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

    def test_configuration_defaults_token_to_nobody_ownership(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment, _ = valid_environment(Path(temporary_directory))
            del environment["WORKLOAD_TOKEN_UID"]
            del environment["WORKLOAD_TOKEN_GID"]

            config = agent.Config.from_environ(environment)

            self.assertEqual(config.token_uid, 65534)
            self.assertEqual(config.token_gid, 65534)

    def test_configuration_rejects_unsafe_or_ambiguous_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            baseline, _ = valid_environment(directory)
            jwk = json.loads(baseline["TEST_WORKLOAD_PRIVATE_JWK"])
            mismatched_jwk, _ = private_jwk()
            cases: dict[str, dict[str, str | None]] = {
                "non_loopback_bind": {"WORKLOAD_BIND_HOST": "0.0.0.0"},
                "non_loopback_issuer": {"WORKLOAD_ISSUER": "http://localhost:8090"},
                "https_issuer": {"WORKLOAD_ISSUER": "https://127.0.0.1:8090"},
                "malformed_issuer": {"WORKLOAD_ISSUER": "http://["},
                "issuer_path": {"WORKLOAD_ISSUER": "http://127.0.0.1:8090/issuer"},
                "issuer_port_mismatch": {"WORKLOAD_PORT": "8091"},
                "blank_audience": {"WORKLOAD_AUDIENCE": ""},
                "spaced_azp": {"WORKLOAD_AZP": "cra notary"},
                "duplicate_scope": {"WORKLOAD_SCOPE": "registry:read registry:read"},
                "empty_scope_entry": {"WORKLOAD_SCOPE": "registry:read  registry:write"},
                "relative_token_file": {"WORKLOAD_TOKEN_FILE": "relay-token"},
                "missing_token_parent": {
                    "WORKLOAD_TOKEN_FILE": str(directory / "missing" / "relay-token")
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
                "negative_uid": {"WORKLOAD_TOKEN_UID": "-1"},
                "oversized_gid": {"WORKLOAD_TOKEN_GID": str(agent.MAX_ID + 1)},
                "bad_key_environment_name": {"WORKLOAD_PRIVATE_JWK_ENV": "bad-name"},
                "missing_key_environment": {"TEST_WORKLOAD_PRIVATE_JWK": None},
                "wrong_curve": {
                    "TEST_WORKLOAD_PRIVATE_JWK": json.dumps({**jwk, "crv": "X25519"})
                },
                "unsupported_key_field": {
                    "TEST_WORKLOAD_PRIVATE_JWK": json.dumps({**jwk, "key_ops": ["sign"]})
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
