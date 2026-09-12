from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

import yaml


SCRIPT = Path(__file__).with_name("dev.py")
SPEC = importlib.util.spec_from_file_location("solmara_breg_dev", SCRIPT)
dev = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(dev)


class DevFixtureTests(unittest.TestCase):
    def args(self) -> SimpleNamespace:
        return SimpleNamespace(
            bregctl="candidate-bregctl", breg_port=18190, issuer_port=18191,
            database_port=55449, provider_host="host.docker.internal",
        )

    def test_ready_uses_issuer_port(self) -> None:
        with mock.patch.object(dev, "command", return_value='{"ok":true}') as command:
            self.assertTrue(dev.ready(self.args())["ok"])
        arguments = command.call_args.args
        self.assertIn("--issuer-port", arguments)
        self.assertNotIn("--mint-port", arguments)

    def test_candidate_check_rejects_mint_era_cli(self) -> None:
        old_help = "  --mint-port <MINT_PORT>\nCommands:\n  export-client\n"
        with mock.patch.object(dev, "command", return_value=old_help):
            with self.assertRaisesRegex(RuntimeError, "Mint-era.*--issuer-port"):
                dev.require_candidate_bregctl(self.args())

    def test_candidate_check_requires_dev_token(self) -> None:
        partial_help = "Commands:\n  export-client\nOptions:\n  --issuer-port <ISSUER_PORT>\n"
        with mock.patch.object(dev, "command", return_value=partial_help):
            with self.assertRaisesRegex(RuntimeError, "dev token command is required"):
                dev.require_candidate_bregctl(self.args())

    def test_candidate_check_accepts_issuer_and_token_contract(self) -> None:
        candidate_help = "Commands:\n  token  Acquire token\nOptions:\n  --issuer-port <ISSUER_PORT>\n"
        with mock.patch.object(dev, "command", return_value=candidate_help):
            dev.require_candidate_bregctl(self.args())

    def test_citizen_self_service_is_bound_to_governed_person_reference(self) -> None:
        registry = yaml.safe_load((dev.PROJECT / "registry.yaml").read_text())
        profile = next(
            profile
            for profile in registry["accessProfiles"]
            if profile["id"] == "citizen-self-service"
        )
        self.assertEqual(profile["requiredScopes"], ["registry:population:self-service"])
        self.assertEqual(profile["principalClaim"], "sub")
        self.assertEqual(profile["requiredPurposes"], ["citizen-self-service"])
        self.assertEqual(profile["actorKind"], "agent")
        self.assertEqual(profile["requesterClients"], ["citizen-self-service-agent"])
        self.assertEqual(len(profile["permissions"]), 1)
        permission = profile["permissions"][0]
        self.assertEqual(permission["operations"], ["lookup"])
        self.assertEqual(permission["readableFields"], ["person-reference", "status"])
        self.assertEqual(permission["lookups"], [{
            "selector": "by-person-reference", "valueOrigin": "request",
        }])
        self.assertEqual(permission["rowBoundaries"], [
            {
                "field": "person-reference",
                "claim": "registry_subject_person_reference",
                "operator": "equals",
            },
            {
                "field": "status",
                "claim": "registry_identity_status",
                "operator": "equals",
            },
        ])

        journeys = yaml.safe_load((dev.PROJECT / "tests/journeys.yaml").read_text())["journeys"]
        refusal = next(
            step
            for journey in journeys
            for step in journey["steps"]
            if step["id"] == "citizen-self-service-refuses-other-person"
        )
        self.assertNotEqual(
            refusal["request"]["values"]["person-reference"],
            refusal["claims"]["directClaims"]["registry_subject_person_reference"],
        )
        self.assertEqual(refusal["expect"], {
            "outcome": "refusal", "status": 404, "problemCode": "lookup.unresolved",
        })
        self.assertTrue(all(
            candidate["principalClaim"] == "sub"
            for candidate in registry["accessProfiles"]
        ))

    def test_export_writes_complete_issuer_neutral_token_client(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            secrets = Path(directory)

            def command(*arguments: str) -> str:
                Path(arguments[arguments.index("--client-id-file") + 1]).write_text("esignet")
                Path(arguments[arguments.index("--assertion-key-file") + 1]).write_text(
                    json.dumps({"kty": "EC", "kid": "esignet-key"})
                )
                return json.dumps({
                    "ok": True,
                    "tokenEndpoint": "http://127.0.0.1:18191/oauth2/token",
                    "clientAssertionAudience": "http://127.0.0.1:18191",
                    "resource": "urn:breg:dev:solmara-esignet-v2",
                    "scopes": ["registry:population:lookup"],
                })

            with mock.patch.object(dev, "SECRETS", secrets), mock.patch.object(dev, "command", command):
                dev.export_provider(self.args())
            config = yaml.safe_load((secrets / "registry.yaml").read_text())
            self.assertNotIn("mint", config)
            self.assertEqual(config["token_client"], {
                "token_endpoint": "http://host.docker.internal:18191/oauth2/token",
                "assertion_audience": "http://127.0.0.1:18191",
                "client_id": "esignet",
                "private_key_file": "/etc/registry-esignet/token-client-private.jwk",
                "key_id": "esignet-key",
                "resource": "urn:breg:dev:solmara-esignet-v2",
                "scopes": ["registry:population:lookup"],
            })
            self.assertEqual(config["claim_map"]["sub"], "$psut")
            self.assertEqual(config["claim_map"]["person_reference"], "personReference")
            self.assertNotIn("individual_id", config["claim_map"])

    def test_token_uses_native_dev_token_header(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            header = Path(directory) / "esignet.header"
            header.write_text("Authorization: Bearer short-lived-token\n")
            response = json.dumps({"ok": True, "headerFile": str(header)})
            with mock.patch.object(dev, "command", return_value=response) as command:
                self.assertEqual(dev.token(self.args(), "esignet"), "short-lived-token")
        self.assertEqual(command.call_args.args[:4], (
            "candidate-bregctl", "dev", "token", "esignet",
        ))


if __name__ == "__main__":
    unittest.main()
