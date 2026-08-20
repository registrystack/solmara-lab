from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import yaml
from cryptography.hazmat.primitives.asymmetric import ec, rsa


ROOT = Path(__file__).resolve().parents[2]
CELLS = ("cra", "nia", "sro", "mosd-programme", "sipf", "nagdi")
EXPECTED_REQUIREMENTS = {
    "https://id.registrystack.org/solmara/requirement/cra-child-benefit/v1": ("https://id.registrystack.org/solmara/evidence-type/cra-child-benefit/v1", "child-benefit-review", 3600),
    "https://id.registrystack.org/solmara/requirement/cra-pension-death/v1": ("https://id.registrystack.org/solmara/evidence-type/cra-death-status/v1", "pension-payment-review", 300),
    "https://id.registrystack.org/solmara/requirement/cra-citizen-record/v1": ("https://id.registrystack.org/solmara/evidence-type/civil-record-linked/v1", "citizen-self-service", 300),
    "https://id.registrystack.org/solmara/requirement/nia-child-benefit/v1": ("https://id.registrystack.org/solmara/evidence-type/population-active/v1", "child-benefit-review", 3600),
    "https://id.registrystack.org/solmara/requirement/nia-citizen-status/v1": ("https://id.registrystack.org/solmara/evidence-type/citizen-population-active/v1", "citizen-self-service", 3600),
    "https://id.registrystack.org/solmara/requirement/sro-child-benefit/v1": ("https://id.registrystack.org/solmara/evidence-type/poverty-priority/v1", "child-benefit-review", 3600),
    "https://id.registrystack.org/solmara/requirement/mosd-child-benefit/v1": ("https://id.registrystack.org/solmara/evidence-type/not-enrolled/v1", "child-benefit-review", 300),
    "https://id.registrystack.org/solmara/requirement/sipf-pension-payment/v1": ("https://id.registrystack.org/solmara/evidence-type/pension-payment-active/v1", "pension-payment-review", 300),
    "https://id.registrystack.org/solmara/requirement/sipf-survivor-benefit/v1": ("https://id.registrystack.org/solmara/evidence-type/survivor-benefit/v1", "survivor-benefit-determination", 300),
    "https://id.registrystack.org/solmara/requirement/nagdi-voucher/v1": ("https://id.registrystack.org/solmara/evidence-type/climate-smart-voucher/v1", "voucher-eligibility-review", 300),
    "https://id.registrystack.org/solmara/requirement/nagdi-livestock/v1": ("https://id.registrystack.org/solmara/evidence-type/livestock-movement/v1", "livestock-movement-control", 300),
}
ISSUERS = {
    "cra": "did:web:id.registrystack.org:solmara:authority:cra",
    "nia": "did:web:id.registrystack.org:solmara:authority:nia",
    "sro": "did:web:id.registrystack.org:solmara:authority:sro",
    "mosd-programme": "did:web:id.registrystack.org:solmara:authority:mosd-programme-mis",
    "sipf": "did:web:id.registrystack.org:solmara:authority:sipf",
    "nagdi": "did:web:id.registrystack.org:solmara:authority:nagdi",
}


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def private_jwk() -> dict[str, str]:
    key = ec.generate_private_key(ec.SECP256R1()).private_numbers()

    def encode(value: int) -> str:
        return base64.urlsafe_b64encode(value.to_bytes(32, "big")).rstrip(b"=").decode()

    public = {"kty": "EC", "crv": "P-256", "x": encode(key.public_numbers.x), "y": encode(key.public_numbers.y)}
    thumbprint = {member: public[member] for member in ("crv", "kty", "x", "y")}
    public["alg"] = "ES256"
    public["kid"] = base64.urlsafe_b64encode(
        hashlib.sha256(json.dumps(thumbprint, separators=(",", ":"), sort_keys=True).encode()).digest()
    ).rstrip(b"=").decode()
    public["d"] = encode(key.private_value)
    return public


def rsa_private_jwk() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_numbers()

    def encode(value: int) -> str:
        return base64.urlsafe_b64encode(value.to_bytes((value.bit_length() + 7) // 8, "big")).rstrip(b"=").decode()

    value = {
        "kty": "RSA", "alg": "RS256", "n": encode(key.public_numbers.n), "e": encode(key.public_numbers.e),
        "d": encode(key.d), "p": encode(key.p), "q": encode(key.q), "dp": encode(key.dmp1),
        "dq": encode(key.dmq1), "qi": encode(key.iqmp),
    }
    thumbprint = {member: value[member] for member in ("e", "kty", "n")}
    value["kid"] = base64.urlsafe_b64encode(hashlib.sha256(json.dumps(thumbprint, separators=(",", ":"), sort_keys=True).encode()).digest()).rstrip(b"=").decode()
    return json.dumps(value)


class CellContractsTest(unittest.TestCase):
    def configs(self):
        return {cell: load_yaml(ROOT / "evidence" / "cells" / cell / "bundle" / "evidence.yaml") for cell in CELLS}

    def test_six_independent_authority_identities_and_runtime_boundaries(self):
        configs = self.configs()
        self.assertEqual(set(configs), set(CELLS))
        for offset, cell in enumerate(CELLS, 21):
            config = configs[cell]
            runtime = load_yaml(ROOT / "evidence" / "cells" / cell / "runtime.yaml")
            self.assertEqual(config["service"]["providerId"], f"https://id.registrystack.org/solmara/evidence/{cell}")
            # RFC 9728 discovery answers on the cell's own routed origin, which is
            # the one origin a relying party may treat as this resource's identity.
            self.assertEqual(config["service"]["publicOrigin"], f"https://{cell}-evidence.solmara.registrystack.org")
            self.assertEqual(config["issuer"]["id"], ISSUERS[cell])
            self.assertEqual(config["signing"]["algorithm"], "ES256")
            self.assertEqual(config["signing"]["activePublicJwkFile"], f"public-keys/{cell}.jwk.json")
            self.assertFalse((ROOT / "evidence" / "cells" / cell / "bundle" / f"public-keys/{cell}.jwk.json").exists())
            self.assertEqual(runtime["listener"]["bindHost"], f"172.29.1.{offset}")
            self.assertEqual(runtime["signer"]["keyName"], f"solmara-evidence-{cell}")
            self.assertNotEqual(runtime["auditStorage"]["path"], "/var/lib/registry-evidence/audit/evidence.jsonl")

    def test_every_requirement_and_concept_carries_its_own_stable_handle(self):
        """A handle is the key a client reads a result under, so it is authored to
        the last segment of the identifier it names rather than invented."""
        for cell, config in self.configs().items():
            handles = []
            for requirement in config["requirements"]:
                with self.subTest(cell=cell, requirement=requirement["id"]):
                    self.assertEqual(requirement["handle"], requirement["id"].rsplit("/", 2)[-2])
                handles.append(requirement["handle"])
                concepts = [concept["handle"] for concept in requirement["concepts"]]
                for concept in requirement["concepts"]:
                    with self.subTest(cell=cell, concept=concept["id"]):
                        self.assertEqual(concept["handle"], concept["id"].rsplit("/", 1)[-1])
                self.assertCountEqual(concepts, set(concepts))
            self.assertCountEqual(handles, set(handles))

    def test_exact_requirement_evidence_type_purpose_and_validity_set(self):
        actual = {}
        for config in self.configs().values():
            for requirement in config["requirements"]:
                actual[requirement["id"]] = (requirement["evidenceType"], requirement["purposes"][0], requirement["validitySeconds"])
        self.assertEqual(actual, EXPECTED_REQUIREMENTS)

    def test_direct_extracts_are_fixed_bounded_and_version_bound(self):
        configs = self.configs()
        direct = [configs["cra"]["sources"]["cra-child-benefit"], configs["nia"]["sources"]["population-extract"], configs["sro"]["sources"]["poverty-extract"]]
        self.assertEqual([source["maximumExtractAgeSeconds"] for source in direct], [86400, 86400, 86400])
        for source in direct:
            self.assertEqual(source["transport"], "sqlite-extract")
            self.assertEqual(source["request"]["maximumRows"], 2)
            self.assertNotIn("authentication", source)
        runtime_paths = {
            cell: next(iter(load_yaml(ROOT / "evidence" / "cells" / cell / "runtime.yaml")["sourceExtracts"].values()))["path"]
            for cell in ("cra", "nia", "sro")
        }
        self.assertEqual(runtime_paths, {
            "cra": "/var/lib/registry-evidence/cra/extracts/cra-birth-20260704T090000Z.sqlite",
            "nia": "/var/lib/registry-evidence/nia/extracts/nia-population-20260704T090000Z.sqlite",
            "sro": "/var/lib/registry-evidence/sro/extracts/sro-poverty-20260704T090000Z.sqlite",
        })

    def test_relay_sources_use_only_named_v2_lookups_and_declared_unresolved_problem(self):
        relay_sources = []
        for config in self.configs().values():
            relay_sources.extend(source for source in config["sources"].values() if source["transport"] == "http-json")
        self.assertEqual(len(relay_sources), 7)
        for source in relay_sources:
            self.assertEqual(source["request"]["method"], "POST")
            self.assertRegex(source["request"]["path"], r"^/v2/resources/[^/]+/lookups/[^/]+$")
            self.assertEqual(source["request"]["projection"][0].split("/")[1:3], ["data", "domainData"])
            self.assertEqual(source["unresolvedProblem"], {"status": 404, "type": "https://id.registrystack.org/problems/registry-relay/consultation/unresolved", "code": "consultation.unresolved"})
            auth = source["authentication"]
            self.assertEqual(auth["kind"], "oauth2-client-credentials")
            self.assertEqual(auth["tokenEndpoint"], "https://mint.solmara.registrystack.org/token")
            self.assertEqual(auth["clientAssertionAudience"], auth["tokenEndpoint"])
            self.assertEqual(auth["audience"], "solmara-runtime")
            self.assertNotIn("clientSecretRef", auth)

        actual = {(source["request"]["path"], source["authentication"]["scope"]) for source in relay_sources}
        self.assertEqual(actual, {
            ("/v2/resources/civil-person/lookups/death-by-uin", "solmara:relay:cra:death-by-uin"),
            ("/v2/resources/civil-person/lookups/citizen-link-by-uin", "solmara:relay:cra:citizen-link-by-uin"),
            ("/v2/resources/beneficiary-enrolment/lookups/by-uin", "solmara:relay:mosd:by-uin"),
            ("/v2/resources/pension-payment/lookups/by-pensioner-uin", "solmara:relay:sipf:by-pensioner-uin"),
            ("/v2/resources/survivor-case/lookups/by-spouse-uin", "solmara:relay:sipf:by-spouse-uin"),
            ("/v2/resources/farmer/lookups/voucher-by-farmer-id", "solmara:relay:nagdi:voucher-by-farmer-id"),
            ("/v2/resources/livestock-herd/lookups/movement-by-farmer-id", "solmara:relay:nagdi:movement-by-farmer-id"),
        })

    def test_no_retired_v1_or_caller_controlled_purpose_shapes(self):
        authored = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "evidence" / "cells").rglob("*.*") if path.is_file())
        for prohibited in ("/v1/datasets/", "Data-Purpose", "static-bearer", "static-authorization"):
            self.assertNotIn(prohibited, authored)

    def test_relay_prepare_scripts_emit_only_the_approved_nested_selectors(self):
        cra = (ROOT / "evidence/cells/cra/bundle/adapters/relay-prepare.rhai").read_text()
        mosd = (ROOT / "evidence/cells/mosd-programme/bundle/adapters/relay-prepare.rhai").read_text()
        sipf = (ROOT / "evidence/cells/sipf/bundle/adapters/relay-prepare.rhai").read_text()
        nagdi = (ROOT / "evidence/cells/nagdi/bundle/adapters/relay-prepare.rhai").read_text()
        self.assertIn('body: #{selectors: #{uin:', cra)
        self.assertNotIn('deceased: true', cra)
        self.assertIn('body: #{selectors: #{uin:', mosd)
        self.assertIn('relay_selectors["pensionerUin"] = subject["uin"]', sipf)
        self.assertIn('relay_selectors["spouseUin"] = subject["uin"]', sipf)
        self.assertIn('body: #{selectors: #{farmerId:', nagdi)
        self.assertNotIn("target", cra + mosd + sipf + nagdi)

    def test_builder_injects_public_halves_and_closed_mint_registrations(self):
        spec = importlib.util.spec_from_file_location("build_cells", ROOT / "evidence" / "scripts" / "build-cells.py")
        module = importlib.util.module_from_spec(spec)
        assert spec.loader
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            private_root = temp / "private"
            for cell in CELLS:
                path = private_root / cell / "secrets" / "signing.jwk"
                path.parent.mkdir(parents=True)
                path.write_text(json.dumps(private_jwk()), encoding="utf-8")
            mint_signing = private_root / "mint" / "secrets" / "signing.jwk"
            mint_signing.parent.mkdir(parents=True)
            mint_signing.write_text(json.dumps(private_jwk()), encoding="utf-8")
            for client in module.RELAY_CLIENTS:
                path = (private_root / module.CLIENT_CELLS[client] / "secrets" / f"{client}-client-key" if client in module.CLIENT_CELLS else private_root / "mint" / "clients" / "nia-esignet-rsa-client-key")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(rsa_private_jwk() if client == "nia-esignet" else json.dumps(private_jwk()), encoding="utf-8")
            application_key = private_root / "mint" / "clients" / "solmara-demo-client-key"
            application_key.write_text(json.dumps(private_jwk()), encoding="utf-8")
            output = temp / "output"
            module.build(private_root, output, None)
            public_documents = list(output.rglob("*.jwk.json"))
            self.assertEqual(len(public_documents), 7)
            for path in public_documents:
                value = json.loads(path.read_text(encoding="utf-8"))
                self.assertNotIn("d", value)
                self.assertEqual(len(value["kid"]), 43)
                self.assertEqual(path.name, f"{value['kid']}.jwk.json")
            registrations = {path.stem: load_yaml(path) for path in (output / "mint" / "clients").glob("*.yaml")}
            self.assertEqual(set(registrations), set(module.RELAY_CLIENTS) | {"solmara-demo"})
            application = registrations.pop("solmara-demo")
            self.assertEqual(application["evidenceAudience"], "https://id.registrystack.org/solmara/audience/demo-client")
            self.assertEqual(application["requesterTags"], ["solmara-demo"])
            for client, registration in registrations.items():
                scope, purpose = module.RELAY_CLIENTS[client]
                self.assertEqual(registration["authorization"], {"scopes": [scope], "claims": {"purpose": purpose}})

            nia_registration = registrations["nia-esignet"]
            self.assertEqual(nia_registration["keys"][0]["kty"], "RSA")
            self.assertEqual(nia_registration["keys"][0]["alg"], "RS256")
            self.assertNotIn("d", nia_registration["keys"][0])
            nia_relay = load_yaml(ROOT / "relays" / "nia" / "registry.yaml")
            nia_profile = nia_relay["resources"][0]["operations"]["lookups"][0]["accessProfiles"]["esignet"]
            self.assertEqual(
                nia_registration["authorization"]["claims"]["purpose"],
                nia_profile["access"]["purpose"]["allowed"][0],
            )


if __name__ == "__main__":
    unittest.main()
