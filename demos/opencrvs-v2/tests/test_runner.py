from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


RUNNER_PATH = Path(__file__).resolve().parents[1] / "runner.py"
SPEC = importlib.util.spec_from_file_location("opencrvs_v2_runner", RUNNER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("could not load the OpenCRVS demo runner")
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


class DotenvTests(unittest.TestCase):
    def test_reads_only_supported_assignments(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "operator.env"
            path.write_text(
                "# ignored\nexport FIRST='one'\nSECOND=\"two\"\n",
                encoding="utf-8",
            )
            self.assertEqual(
                runner.read_dotenv(path),
                {"FIRST": "one", "SECOND": "two"},
            )

    def test_rejects_invalid_environment_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "operator.env"
            path.write_text("lowercase=value\n", encoding="utf-8")
            with self.assertRaises(runner.DemoFailure):
                runner.read_dotenv(path)

    def test_explicit_process_selectors_override_comment_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "operator.env"
            path.write_text(
                "OPENCRVS_CLIENT_ID=client\n"
                "OPENCRVS_SECRET=secret\n"
                "OPENCRVS_URL=country.example\n"
                "# child called Example Person: Tracking ID: ABC123, "
                "Registration Number: AAAAAAAAAAAA, National ID: 1111111111\n",
                encoding="utf-8",
            )
            environment = {
                "OPENCRVS_DEMO_REGISTRATION_NUMBER": "BBBBBBBBBBBB",
                "OPENCRVS_DEMO_CHILD_NATIONAL_ID": "2222222222",
                "OPENCRVS_DEMO_TRACKING_ID": "XYZ789",
            }
            with (
                mock.patch.object(runner, "EXTERNAL_ENV", path),
                mock.patch.dict(os.environ, environment, clear=False),
            ):
                _, selectors = runner.required_external_env()
            self.assertEqual(selectors.registration_number, "BBBBBBBBBBBB")
            self.assertEqual(selectors.child_national_id, "2222222222")
            self.assertEqual(selectors.tracking_id, "XYZ789")
            self.assertEqual(selectors.child_name, "Example Person")


class OriginTests(unittest.TestCase):
    def test_accepts_only_path_free_https_dns_hosts(self) -> None:
        self.assertEqual(
            runner.opencrvs_host("https://country.example"),
            "country.example",
        )
        for invalid in (
            "http://country.example",
            "https://country.example/path",
            "https://user@country.example",
            "https://country.example:444",
            "https://UPPER.example",
            "127.0.0.1",
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(runner.DemoFailure):
                    runner.opencrvs_host(invalid)


class RegistryctlIdentityTests(unittest.TestCase):
    def test_requires_exact_commit_for_development_override(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "registry-stack"
            executable = repository / "target" / "debug" / "registryctl"
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"synthetic registryctl")
            versions = {
                "REGISTRY_STACK_SOURCE_REF": "v0.15.2",
                "REGISTRY_STACK_SOURCE_COMMIT": "a" * 40,
            }
            environment = {
                "OPENCRVS_DEMO_REGISTRYCTL": str(executable),
                "OPENCRVS_DEMO_REGISTRYCTL_SOURCE_COMMIT": "b" * 40,
            }
            results = [
                subprocess.CompletedProcess(
                    [str(executable), "--version"],
                    0,
                    stdout="registryctl 0.16.0-dev\n",
                    stderr="",
                ),
                subprocess.CompletedProcess(
                    ["git", "rev-parse"],
                    0,
                    stdout=f"{repository}\n",
                    stderr="",
                ),
                subprocess.CompletedProcess(
                    ["git", "rev-parse", "HEAD"],
                    0,
                    stdout=f"{'b' * 40}\n",
                    stderr="",
                ),
                subprocess.CompletedProcess(
                    ["git", "status"],
                    0,
                    stdout="",
                    stderr="",
                ),
            ]
            with (
                mock.patch.object(
                    runner,
                    "registryctl",
                    return_value=str(executable),
                ),
                mock.patch.object(runner, "run", side_effect=results),
                mock.patch.dict(os.environ, environment, clear=False),
            ):
                self.assertEqual(
                    runner.registryctl_identity(versions),
                    {
                        "version": "registryctl 0.16.0-dev",
                        "source_commit": "b" * 40,
                        "executable_sha256": hashlib.sha256(
                            b"synthetic registryctl"
                        ).hexdigest(),
                        "development_override": True,
                    },
                )

            environment["OPENCRVS_DEMO_REGISTRYCTL_SOURCE_COMMIT"] = "main"
            with (
                mock.patch.object(
                    runner,
                    "registryctl",
                    return_value=str(executable),
                ),
                mock.patch.object(runner, "run", return_value=results[0]),
                mock.patch.dict(os.environ, environment, clear=False),
                self.assertRaises(runner.DemoFailure),
            ):
                runner.registryctl_identity(versions)


class RelayRuntimeIdentityTests(unittest.TestCase):
    def test_requires_the_same_labeled_candidate_commit(self) -> None:
        commit = "b" * 40
        versions = {
            "REGISTRYCTL_VERSION": "0.15.2",
            "REGISTRY_STACK_SOURCE_REF": "v0.15.2",
            "REGISTRY_STACK_SOURCE_COMMIT": "a" * 40,
            "REGISTRY_RELAY_IMAGE": "relay@sha256:released",
            "REGISTRY_NOTARY_IMAGE": "notary@sha256:released",
        }
        compiler = {
            "source_commit": commit,
            "development_override": True,
        }
        environment = {
            "OPENCRVS_DEMO_RELAY_IMAGE": "registry-relay:candidate",
            "OPENCRVS_DEMO_RELAY_SOURCE_COMMIT": commit,
            "OPENCRVS_DEMO_RELAY_PLATFORM": "linux/arm64",
        }
        results = [
            subprocess.CompletedProcess(
                ["docker", "image", "inspect"],
                0,
                stdout=(
                    f"sha256:{'1' * 64}|arm64|{commit}|"
                    "attribute-release,crosswalk-runtime\n"
                ),
                stderr="",
            ),
            subprocess.CompletedProcess(
                ["docker", "run"],
                0,
                stdout="registry-relay 0.15.2\n",
                stderr="",
            ),
        ]
        with (
            mock.patch.object(runner, "run", side_effect=results) as run_mock,
            mock.patch.dict(os.environ, environment, clear=False),
        ):
            self.assertEqual(
                runner.relay_runtime_identity(versions, compiler),
                {
                    "version": "registry-relay 0.15.2",
                    "source_commit": commit,
                    "relay_image": "registry-relay:candidate",
                    "relay_image_id": f"sha256:{'1' * 64}",
                    "relay_platform": "linux/arm64",
                    "notary_image": "notary@sha256:released",
                    "development_override": True,
                },
            )
            run_command = run_mock.call_args_list[1].args[0]
            self.assertEqual(
                run_command[run_command.index("--platform") + 1],
                "linux/arm64",
            )

    def test_rejects_an_unlabeled_or_cross_commit_candidate(self) -> None:
        commit = "b" * 40
        versions = {
            "REGISTRYCTL_VERSION": "0.15.2",
            "REGISTRY_STACK_SOURCE_REF": "v0.15.2",
            "REGISTRY_STACK_SOURCE_COMMIT": "a" * 40,
            "REGISTRY_RELAY_IMAGE": "relay@sha256:released",
            "REGISTRY_NOTARY_IMAGE": "notary@sha256:released",
        }
        compiler = {
            "source_commit": commit,
            "development_override": True,
        }
        environment = {
            "OPENCRVS_DEMO_RELAY_IMAGE": "registry-relay:candidate",
            "OPENCRVS_DEMO_RELAY_SOURCE_COMMIT": "c" * 40,
            "OPENCRVS_DEMO_RELAY_PLATFORM": "linux/amd64",
        }
        with (
            mock.patch.dict(os.environ, environment, clear=False),
            self.assertRaises(runner.DemoFailure),
        ):
            runner.relay_runtime_identity(versions, compiler)

    def test_rejects_a_candidate_from_another_platform(self) -> None:
        commit = "b" * 40
        versions = {
            "REGISTRYCTL_VERSION": "0.15.2",
            "REGISTRY_STACK_SOURCE_REF": "v0.15.2",
            "REGISTRY_STACK_SOURCE_COMMIT": "a" * 40,
            "REGISTRY_RELAY_IMAGE": "relay@sha256:released",
            "REGISTRY_NOTARY_IMAGE": "notary@sha256:released",
        }
        compiler = {
            "source_commit": commit,
            "development_override": True,
        }
        environment = {
            "OPENCRVS_DEMO_RELAY_IMAGE": "registry-relay:candidate",
            "OPENCRVS_DEMO_RELAY_SOURCE_COMMIT": commit,
            "OPENCRVS_DEMO_RELAY_PLATFORM": "linux/arm64",
        }
        inspected = subprocess.CompletedProcess(
            ["docker", "image", "inspect"],
            0,
            stdout=(
                f"sha256:{'1' * 64}|amd64|{commit}|"
                "attribute-release,crosswalk-runtime\n"
            ),
            stderr="",
        )
        with (
            mock.patch.object(runner, "run", return_value=inspected),
            mock.patch.dict(os.environ, environment, clear=False),
            self.assertRaises(runner.DemoFailure),
        ):
            runner.relay_runtime_identity(versions, compiler)

    def test_rejects_dirty_or_mismatched_development_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "registry-stack"
            executable = repository / "target" / "debug" / "registryctl"
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"synthetic registryctl")
            versions = {
                "REGISTRY_STACK_SOURCE_REF": "v0.15.2",
                "REGISTRY_STACK_SOURCE_COMMIT": "a" * 40,
            }
            environment = {
                "OPENCRVS_DEMO_REGISTRYCTL": str(executable),
                "OPENCRVS_DEMO_REGISTRYCTL_SOURCE_COMMIT": "b" * 40,
            }
            results = [
                subprocess.CompletedProcess(
                    [str(executable), "--version"],
                    0,
                    stdout="registryctl 0.16.0-dev\n",
                    stderr="",
                ),
                subprocess.CompletedProcess(
                    ["git", "rev-parse"],
                    0,
                    stdout=f"{repository}\n",
                    stderr="",
                ),
                subprocess.CompletedProcess(
                    ["git", "rev-parse", "HEAD"],
                    0,
                    stdout=f"{'c' * 40}\n",
                    stderr="",
                ),
                subprocess.CompletedProcess(
                    ["git", "status"],
                    0,
                    stdout=" M crates/registryctl/src/main.rs\n",
                    stderr="",
                ),
            ]
            with (
                mock.patch.object(
                    runner,
                    "registryctl",
                    return_value=str(executable),
                ),
                mock.patch.object(runner, "run", side_effect=results),
                mock.patch.dict(os.environ, environment, clear=False),
                self.assertRaises(runner.DemoFailure),
            ):
                runner.registryctl_identity(versions)


class OAuthProbeTests(unittest.TestCase):
    def token(self, audience: str) -> str:
        header = runner.b64url(b'{"alg":"EdDSA"}')
        payload = runner.b64url(
            json.dumps(
                {
                    "aud": audience,
                    "exp": 1_600,
                    "iat": 1_000,
                    "iss": "https://issuer.example",
                    "scope": "record.search",
                },
                separators=(",", ":"),
            ).encode("utf-8")
        )
        return f"{header}.{payload}.{runner.b64url(b'signature')}"

    def test_accepts_exact_shape_and_redacts_client_id_from_claims(self) -> None:
        client_id = "operator-client-id"
        response = runner.HttpResult(
            200,
            {
                "access_token": self.token(client_id),
                "token_type": "Bearer",
            },
            {},
        )
        external = {
            "OPENCRVS_CLIENT_ID": client_id,
            "OPENCRVS_SECRET": "secret",
            "OPENCRVS_URL": "country.example",
        }
        with mock.patch.object(runner, "http_json", return_value=response):
            metadata, token = runner.oauth_probe(external)
        self.assertEqual(metadata["audience"], "[client-id-redacted]")
        self.assertEqual(metadata["lifetime_seconds"], 600)
        self.assertNotIn(client_id, json.dumps(metadata))
        self.assertEqual(token, response.body["access_token"])

    def test_rejects_an_expiry_member_in_the_no_expiry_profile(self) -> None:
        response = runner.HttpResult(
            200,
            {
                "access_token": self.token("audience"),
                "token_type": "Bearer",
                "expires_in": 600,
            },
            {},
        )
        external = {
            "OPENCRVS_CLIENT_ID": "client",
            "OPENCRVS_SECRET": "secret",
            "OPENCRVS_URL": "country.example",
        }
        with (
            mock.patch.object(runner, "http_json", return_value=response),
            self.assertRaises(runner.DemoFailure),
        ):
            runner.oauth_probe(external)


class RelayActivityTests(unittest.TestCase):
    def test_counts_credential_and_data_dispatches_separately(self) -> None:
        completed = subprocess.CompletedProcess(
            ["docker"],
            0,
            stdout=" 5|3|2\n",
            stderr="",
        )
        with mock.patch.object(runner, "run", return_value=completed) as invoked:
            activity = runner.relay_activity({})
        self.assertEqual(
            activity,
            runner.RelayActivity(
                completion_intents=5,
                credential_dispatches=3,
                data_dispatches=2,
            ),
        )
        command = invoked.call_args.args[0]
        query = command[command.index("--command") + 1]
        self.assertIn("kind = 'credential'", query)
        self.assertIn("kind = 'data'", query)

    def test_exact_consultation_dispatch_requires_fresh_oauth_and_source_calls(
        self,
    ) -> None:
        before = runner.RelayActivity(1, 1, 1)
        after = runner.RelayActivity(2, 2, 2)
        self.assertEqual(
            runner.exact_consultation_dispatch(before, after, "known-record"),
            {
                "credential_dispatch_delta": 1,
                "source_data_dispatch_delta": 1,
            },
        )

        with self.assertRaises(runner.DemoFailure):
            runner.exact_consultation_dispatch(
                before,
                runner.RelayActivity(2, 1, 2),
                "cached-token",
            )

    def test_rate_bound_evidence_separates_public_and_effective_limits(self) -> None:
        public = {"quota_per_minute": 60, "quota_burst": 8}
        effective = {"quota_per_minute": 4, "quota_burst": 2}
        self.assertEqual(
            runner.relay_rate_bound_evidence(public, effective),
            {
                "public_bounds": public,
                "effective_runtime_limits": effective,
            },
        )

        for invalid in (
            {"quota_per_minute": 4, "quota_burst": 1},
            {"quota_per_minute": 61, "quota_burst": 2},
            {"quota_per_minute": 4, "quota_burst": 9},
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(runner.DemoFailure):
                    runner.relay_rate_bound_evidence(public, invalid)

    def test_negative_rejects_any_source_boundary_dispatch(self) -> None:
        activities = [
            runner.RelayActivity(0, 0, 0),
            runner.RelayActivity(0, 1, 0),
        ]
        rejected = runner.HttpResult(403, {"code": "purpose.denied"}, {})
        with (
            mock.patch.object(runner, "relay_activity", side_effect=activities),
            mock.patch.object(runner, "http_json", return_value=rejected),
            self.assertRaises(runner.DemoFailure),
        ):
            runner.live_negative(
                "http://127.0.0.1:4391",
                {},
                {},
                {},
            )


class CredentialVerificationTests(unittest.TestCase):
    def make_credential(
        self,
    ) -> tuple[str, str, str, dict[str, str], str]:
        issuer_jwk = json.loads(runner.generate_private_jwk("issuer-key-1"))
        issuer_private = Ed25519PrivateKey.from_private_bytes(
            runner.b64url_decode(issuer_jwk["d"])
        )
        holder_id, _, holder_public = runner.holder_material()
        disclosure = runner.b64url(
            json.dumps(
                ["salt", "birth-record-exists", True],
                separators=(",", ":"),
            ).encode("utf-8")
        )
        payload = {
            "_sd": [runner.b64url(hashlib.sha256(disclosure.encode("ascii")).digest())],
            "_sd_alg": "sha-256",
            "cnf": {"kid": holder_id, "jwk": holder_public},
            "exp": 1_030,
            "iat": 1_000,
            "iss": "did:web:issuer.example",
            "vct": "https://id.example/credential/v1",
        }
        header = {"alg": "EdDSA", "kid": "issuer-key-1"}
        header_segment = runner.b64url(
            json.dumps(header, separators=(",", ":")).encode("utf-8")
        )
        payload_segment = runner.b64url(
            json.dumps(payload, separators=(",", ":")).encode("utf-8")
        )
        signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
        compact = (
            f"{signing_input.decode('ascii')}."
            f"{runner.b64url(issuer_private.sign(signing_input))}"
        )
        return (
            f"{compact}~{disclosure}~",
            json.dumps(issuer_jwk),
            holder_id,
            holder_public,
            disclosure,
        )

    def test_verifies_signature_disclosures_and_holder_binding(self) -> None:
        credential, issuer_jwk, holder_id, holder_public, _ = self.make_credential()
        summary = runner.verify_sd_jwt(
            credential,
            issuer_jwk,
            holder_id,
            holder_public,
        )
        self.assertTrue(summary["issuer_signature_valid"])
        self.assertTrue(summary["disclosures_match_digests"])
        self.assertTrue(summary["cnf_matches_ephemeral_holder"])
        self.assertEqual(summary["disclosure_count"], 1)
        self.assertNotIn(credential, json.dumps(summary))

    def test_rejects_a_disclosure_not_bound_by_the_sd_jwt(self) -> None:
        credential, issuer_jwk, holder_id, holder_public, disclosure = (
            self.make_credential()
        )
        credential = credential.replace(disclosure, runner.b64url(b"tampered"))
        with self.assertRaises(runner.DemoFailure):
            runner.verify_sd_jwt(
                credential,
                issuer_jwk,
                holder_id,
                holder_public,
            )


class SanitizationTests(unittest.TestCase):
    def test_scan_rejects_exact_sensitive_values(self) -> None:
        with self.assertRaises(runner.DemoFailure):
            runner.scan_bytes(
                [],
                [b"prefix super-sensitive-value suffix"],
                {"test secret": b"super-sensitive-value"},
            )

    def test_scan_rejects_bearer_shaped_tokens(self) -> None:
        with self.assertRaises(runner.DemoFailure):
            runner.scan_bytes(
                [],
                [b"Authorization: Bearer abcdefghijklmnopqrstuvwxyz"],
                {},
            )


if __name__ == "__main__":
    unittest.main()
