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


class AuthoredProjectTests(unittest.TestCase):
    def test_credential_issuer_is_the_canonical_solmara_cra(self) -> None:
        environment = runner.yaml.safe_load(
            (runner.AUTHORED_PROJECT / "environments" / "local.yaml").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            environment["issuance"],
            {
                "issuer": runner.CREDENTIAL_ISSUER,
                "signing_kid": runner.ISSUER_KID,
                "signing_key": {"secret": "OPENCRVS_DEMO_ISSUER_JWK"},
                "generation": 1,
            },
        )


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

    def test_binds_evidence_to_the_running_relay_container(self) -> None:
        commit = "b" * 40
        image_id = f"sha256:{'1' * 64}"
        expected = {
            "version": "registry-relay 0.15.2",
            "source_commit": commit,
            "relay_image": "registry-relay:candidate",
            "relay_image_id": image_id,
            "development_override": True,
        }
        results = [
            subprocess.CompletedProcess(
                ["docker", "compose", "ps"],
                0,
                stdout=f"{'c' * 64}\n",
                stderr="",
            ),
            subprocess.CompletedProcess(
                ["docker", "container", "inspect"],
                0,
                stdout=(
                    f"{image_id}|registry-relay:candidate|{commit}|"
                    "attribute-release,crosswalk-runtime\n"
                ),
                stderr="",
            ),
        ]
        with mock.patch.object(runner, "run", side_effect=results):
            self.assertEqual(
                runner.running_relay_runtime_identity(expected, {}),
                {
                    **expected,
                    "running_container_verified": True,
                },
            )

    def test_rejects_running_relay_that_differs_from_declared_identity(self) -> None:
        expected = {
            "source_commit": "a" * 40,
            "relay_image": "relay@sha256:released",
            "development_override": False,
        }
        results = [
            subprocess.CompletedProcess(
                ["docker", "compose", "ps"],
                0,
                stdout=f"{'c' * 64}\n",
                stderr="",
            ),
            subprocess.CompletedProcess(
                ["docker", "container", "inspect"],
                0,
                stdout=(
                    f"sha256:{'1' * 64}|registry-relay:candidate|{'b' * 40}|"
                    "attribute-release,crosswalk-runtime\n"
                ),
                stderr="",
            ),
        ]
        with (
            mock.patch.object(runner, "run", side_effect=results),
            self.assertRaises(runner.DemoFailure),
        ):
            runner.running_relay_runtime_identity(expected, {})

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
                expected_status=403,
                expected_code="purpose.not_allowed",
            )

    def test_negative_requires_expected_status_and_code(self) -> None:
        for unexpected in (
            runner.HttpResult(500, {"code": "internal.error"}, {}),
            runner.HttpResult(429, {"code": "rate_limited"}, {}),
            runner.HttpResult(403, {"code": "purpose.denied"}, {}),
        ):
            with (
                self.subTest(unexpected=unexpected),
                mock.patch.object(
                    runner,
                    "relay_activity",
                    side_effect=[
                        runner.RelayActivity(0, 0, 0),
                        runner.RelayActivity(0, 0, 0),
                    ],
                ),
                mock.patch.object(runner, "http_json", return_value=unexpected),
                self.assertRaises(runner.DemoFailure),
            ):
                runner.live_negative(
                    "http://127.0.0.1:4391",
                    {},
                    {},
                    {},
                    expected_status=403,
                    expected_code="purpose.not_allowed",
                )

    def test_no_match_requires_every_dependent_predicate_to_be_null(self) -> None:
        runner.require_no_match_contract({"results": dict(runner.NO_MATCH_RESULTS)})
        for unexpected in (True, False):
            results = dict(runner.NO_MATCH_RESULTS)
            results[runner.CLAIMS[1]] = unexpected
            with (
                self.subTest(unexpected=unexpected),
                self.assertRaises(runner.DemoFailure),
            ):
                runner.require_no_match_contract({"results": results})


class CredentialVerificationTests(unittest.TestCase):
    def make_credential(
        self,
        disclosed_claims: list[tuple[str, object]] | None = None,
        *,
        issuer: str = runner.CREDENTIAL_ISSUER,
        vct: str = runner.CREDENTIAL_VCT,
        kid: str = runner.ISSUER_KID,
        embedded_claim_ids: dict[str, str] | None = None,
        issued_at: int | None = None,
        expires_at: int | None = None,
    ) -> tuple[str, str, str, dict[str, str], str]:
        issuer_jwk = json.loads(runner.generate_private_jwk(kid))
        issuer_private = Ed25519PrivateKey.from_private_bytes(
            runner.b64url_decode(issuer_jwk["d"])
        )
        holder_id, _, holder_public = runner.holder_material()
        requested = disclosed_claims
        if requested is None:
            requested = [(claim, True) for claim in runner.CLAIMS]
        if issued_at is None:
            issued_at = int(runner.time.time())
        if expires_at is None:
            expires_at = issued_at + runner.CREDENTIAL_VALIDITY_SECONDS
        disclosures = [
            runner.b64url(
                json.dumps(
                    [
                        f"salt-{index}",
                        claim,
                        {
                            "claim_id": (embedded_claim_ids or {}).get(claim, claim),
                            "version": "1",
                            "value": value,
                            "satisfied": value,
                            "subject_type": "Person",
                            "issued_at": "2026-01-01T00:00:00Z",
                        },
                    ],
                    separators=(",", ":"),
                ).encode("utf-8")
            )
            for index, (claim, value) in enumerate(requested)
        ]
        payload = {
            "_sd": [
                runner.b64url(hashlib.sha256(disclosure.encode("ascii")).digest())
                for disclosure in disclosures
            ],
            "_sd_alg": "sha-256",
            "cnf": {"kid": holder_id, "jwk": holder_public},
            "exp": expires_at,
            "iat": issued_at,
            "iss": issuer,
            "vct": vct,
        }
        header = {"alg": "EdDSA", "kid": kid}
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
            f"{compact}~{'~'.join(disclosures)}~",
            json.dumps(issuer_jwk),
            holder_id,
            holder_public,
            disclosures[0] if disclosures else "",
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
        self.assertTrue(summary["disclosed_claims_verified"])
        self.assertTrue(summary["cnf_matches_ephemeral_holder"])
        self.assertTrue(summary["currently_valid"])
        self.assertTrue(summary["authored_lifetime_verified"])
        self.assertEqual(summary["disclosure_count"], len(runner.CLAIMS))
        self.assertEqual(summary["issuer"], runner.CREDENTIAL_ISSUER)
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

    def test_rejects_missing_unrelated_false_or_duplicate_predicates(self) -> None:
        invalid_sets = [
            [],
            [("unrelated-claim", True)],
            [
                (runner.CLAIMS[0], False),
                *[(claim, True) for claim in runner.CLAIMS[1:]],
            ],
            [
                (runner.CLAIMS[0], True),
                (runner.CLAIMS[0], True),
                *[(claim, True) for claim in runner.CLAIMS[1:]],
            ],
        ]
        for disclosed_claims in invalid_sets:
            with self.subTest(disclosed_claims=disclosed_claims):
                credential, issuer_jwk, holder_id, holder_public, _ = (
                    self.make_credential(disclosed_claims)
                )
                with self.assertRaises(runner.DemoFailure):
                    runner.verify_sd_jwt(
                        credential,
                        issuer_jwk,
                        holder_id,
                        holder_public,
                    )

    def test_rejects_noncanonical_credential_identity(self) -> None:
        for identity in (
            {"issuer": "did:web:opencrvs-demo.invalid"},
            {"vct": "https://id.registrystack.org/solmara/credential/unrelated/v1"},
            {"kid": "did:web:id.registrystack.org:solmara:authority:cra#unrelated"},
        ):
            with self.subTest(identity=identity):
                credential, issuer_jwk, holder_id, holder_public, _ = (
                    self.make_credential(**identity)
                )
                with self.assertRaises(runner.DemoFailure):
                    runner.verify_sd_jwt(
                        credential,
                        issuer_jwk,
                        holder_id,
                        holder_public,
                    )

    def test_rejects_mismatched_embedded_claim_id(self) -> None:
        credential, issuer_jwk, holder_id, holder_public, _ = self.make_credential(
            embedded_claim_ids={runner.CLAIMS[0]: "unrelated-claim"}
        )
        with self.assertRaises(runner.DemoFailure):
            runner.verify_sd_jwt(
                credential,
                issuer_jwk,
                holder_id,
                holder_public,
            )

    def test_rejects_expired_future_or_wrong_lifetime(self) -> None:
        now = int(runner.time.time())
        invalid_lifetimes = (
            {
                "issued_at": now - 700,
                "expires_at": now - 100,
            },
            {
                "issued_at": now + runner.CREDENTIAL_CLOCK_SKEW_SECONDS + 1,
                "expires_at": (
                    now
                    + runner.CREDENTIAL_CLOCK_SKEW_SECONDS
                    + 1
                    + runner.CREDENTIAL_VALIDITY_SECONDS
                ),
            },
            {
                "issued_at": now,
                "expires_at": now + runner.CREDENTIAL_VALIDITY_SECONDS + 1,
            },
        )
        for lifetime in invalid_lifetimes:
            with self.subTest(lifetime=lifetime):
                credential, issuer_jwk, holder_id, holder_public, _ = (
                    self.make_credential(**lifetime)
                )
                with self.assertRaises(runner.DemoFailure):
                    runner.verify_sd_jwt(
                        credential,
                        issuer_jwk,
                        holder_id,
                        holder_public,
                    )


class CleanupTests(unittest.TestCase):
    def test_down_ignores_incomplete_operator_and_runtime_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            demo = Path(temporary) / "opencrvs-v2"
            runtime = demo / ".runtime"
            runtime.mkdir(parents=True)
            external = Path(temporary) / "operator.env"
            external.write_text(
                "OPENCRVS_CLIENT_ID=rotated-client-only\n",
                encoding="utf-8",
            )
            runtime_env = runtime / "local.env"
            runtime_env.write_text("incomplete runtime file\n", encoding="utf-8")
            with (
                mock.patch.object(runner, "DEMO", demo),
                mock.patch.object(runner, "RUNTIME", runtime),
                mock.patch.object(runner, "RUNTIME_PROJECT", runtime / "project"),
                mock.patch.object(runner, "RUNTIME_ENV", runtime_env),
                mock.patch.object(runner, "EXTERNAL_ENV", external),
                mock.patch.object(runner, "run") as run_mock,
            ):
                runner.down()

            self.assertFalse(runtime.exists())
            command = run_mock.call_args.args[0]
            self.assertIn("down", command)
            self.assertIn("--remove-orphans", command)


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
