from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "hosted-image-manifest.py"
DIGESTS = {
    "REGISTRY_RELAY_IMAGE": "1" * 64,
    "SOLMARA_EVIDENCE_IMAGE": "2" * 64,
    "SOLMARA_MINT_IMAGE": "3" * 64,
    "SOLMARA_AUTHORITY_PROVISIONER_IMAGE": "4" * 64,
    "SOLMARA_TRANSIT_SIGNER_IMAGE": "5" * 64,
    "SOLMARA_STATIC_METADATA_IMAGE": "6" * 64,
    "SOLMARA_SCENARIO_RUNNER_IMAGE": "7" * 64,
    "SOLMARA_HOME_IMAGE": "8" * 64,
    "SOLMARA_PORTAL_IMAGE": "9" * 64,
    "SOLMARA_ESIGNET_RELAY_IMAGE": "a" * 64,
    "SOLMARA_ESIGNET_POSTGRES_IMAGE": "b" * 64,
    "SOLMARA_ESIGNET_UI_IMAGE": "c" * 64,
    "SOLMARA_ESIGNET_SEED_IMAGE": "d" * 64,
}


def load_module():
    spec = importlib.util.spec_from_file_location("hosted_image_manifest", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HostedImageManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module()
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.manifest = self.root / "release" / "solmara-hosted-images.env"
        self.environment = {
            key: self.module.expected_reference(key, digest)
            for key, digest in DIGESTS.items()
        }
        core = [
            key
            for key in self.module.EXPECTED_KEYS
            if not key.startswith("SOLMARA_ESIGNET_")
        ]
        esignet = [
            key
            for key in self.module.EXPECTED_KEYS
            if key.startswith("SOLMARA_ESIGNET_")
        ]
        (self.root / "compose.hosted.yaml").write_text(
            "services:\n"
            + "".join(
                f"  {index}:\n    image: ${{" + key + ":?required}\n"
                for index, key in enumerate(core)
            ),
            encoding="utf-8",
        )
        (self.root / "compose.coolify.esignet.yaml").write_text(
            "services:\n"
            + "".join(
                f"  {index}:\n    image: ${{" + key + ":?required}\n"
                for index, key in enumerate(esignet)
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.directory.cleanup()

    def invoke(
        self, *arguments: str, environment: dict[str, str] | None = None
    ) -> tuple[int, str]:
        stderr = io.StringIO()
        with (
            mock.patch.dict(os.environ, environment or {}, clear=True),
            contextlib.redirect_stderr(stderr),
        ):
            result = self.module.main(["--compose-root", str(self.root), *arguments])
        return result, stderr.getvalue()

    def test_write_is_canonical_deterministic_and_sanitized(self) -> None:
        supplied = {**self.environment, "COOLIFY_API_TOKEN": "must-not-leave-process"}
        result, stderr = self.invoke(
            "write", "--output", str(self.manifest), environment=supplied
        )
        self.assertEqual(result, 0, stderr)

        expected = "".join(
            f"{key}={self.environment[key]}\n" for key in self.module.EXPECTED_KEYS
        )
        self.assertEqual(self.manifest.read_text(encoding="utf-8"), expected)
        self.assertNotIn("must-not-leave-process", expected)
        self.assertEqual(self.manifest.stat().st_mode & 0o777, 0o644)

        result, stderr = self.invoke(
            "write", "--output", str(self.manifest), environment=supplied
        )
        self.assertEqual(result, 0, stderr)
        self.assertEqual(self.manifest.read_text(encoding="utf-8"), expected)

    def test_every_image_must_use_its_exact_ghcr_repository_and_digest(self) -> None:
        invalid_values = (
            "ghcr.io/registrystack/evidence:candidate",
            f"docker.io/registrystack/evidence@sha256:{'b' * 64}",
            f"ghcr.io/registrystack/mint@sha256:{'b' * 64}",
            f"ghcr.io/registrystack/solmara-lab-evidence@sha256:{'b' * 64}",
            f"ghcr.io/registrystack/evidence@sha256:{'B' * 64}",
            f"ghcr.io/registrystack/evidence@sha256:{'b' * 63}",
        )
        for invalid in invalid_values:
            with self.subTest(invalid=invalid):
                environment = {**self.environment, "SOLMARA_EVIDENCE_IMAGE": invalid}
                result, stderr = self.invoke(
                    "write", "--output", str(self.manifest), environment=environment
                )
                self.assertEqual(result, 1)
                self.assertIn("SOLMARA_EVIDENCE_IMAGE must", stderr)

    def test_relay_must_use_the_canonical_official_reference(self) -> None:
        invalid = (
            "ghcr.io/registrystack/relay:v0.22.0",
            f"ghcr.io/registrystack/solmara-lab-relay@sha256:{'1' * 64}",
            f"ghcr.io/registrystack/relay@sha256:{'A' * 64}",
        )
        for value in invalid:
            with self.subTest(value=value):
                environment = {**self.environment, "REGISTRY_RELAY_IMAGE": value}
                result, stderr = self.invoke(
                    "write", "--output", str(self.manifest), environment=environment
                )
                self.assertEqual(result, 1)
                self.assertIn("REGISTRY_RELAY_IMAGE must", stderr)

    def test_missing_image_fails_without_writing_a_partial_manifest(self) -> None:
        environment = dict(self.environment)
        del environment["SOLMARA_PORTAL_IMAGE"]
        result, stderr = self.invoke(
            "write", "--output", str(self.manifest), environment=environment
        )
        self.assertEqual(result, 1)
        self.assertIn("environment is missing SOLMARA_PORTAL_IMAGE", stderr)
        self.assertFalse(self.manifest.exists())

    def test_validator_refuses_extra_keys_and_noncanonical_order(self) -> None:
        canonical = self.module.render_manifest(self.environment)
        cases = (
            canonical + f"SOLMARA_DATABASE_PASSWORD={'b' * 64}\n",
            "\n".join(reversed(canonical.rstrip("\n").splitlines())) + "\n",
        )
        for index, content in enumerate(cases):
            with self.subTest(index=index):
                self.manifest.parent.mkdir(parents=True, exist_ok=True)
                self.manifest.write_text(content, encoding="utf-8")
                result, stderr = self.invoke(
                    "validate", "--manifest", str(self.manifest)
                )
                self.assertEqual(result, 1)
                self.assertTrue(
                    "unexpected key" in stderr or "canonical order" in stderr,
                    stderr,
                )

    def test_validator_refuses_crlf_and_missing_final_newline(self) -> None:
        canonical = self.module.render_manifest(self.environment)
        cases = (
            canonical.replace("\n", "\r\n").encode("utf-8"),
            canonical.rstrip("\n").encode("utf-8"),
        )
        for index, content in enumerate(cases):
            with self.subTest(index=index):
                self.manifest.parent.mkdir(parents=True, exist_ok=True)
                self.manifest.write_bytes(content)
                result, stderr = self.invoke(
                    "validate", "--manifest", str(self.manifest)
                )
                self.assertEqual(result, 1)
                self.assertIn("manifest must", stderr)

    def test_compose_inventory_is_closed_and_requires_variables(self) -> None:
        hosted = self.root / "compose.hosted.yaml"
        hosted.write_text(
            hosted.read_text(encoding="utf-8")
            + "  unexpected:\n    image: ${SOLMARA_OTHER_IMAGE:?required}\n",
            encoding="utf-8",
        )
        result, stderr = self.invoke("inventory")
        self.assertEqual(result, 1)
        self.assertIn("unexpected SOLMARA_OTHER_IMAGE", stderr)

        hosted.write_text(
            hosted.read_text(encoding="utf-8").replace(
                "${SOLMARA_OTHER_IMAGE:?required}", "${SOLMARA_OTHER_IMAGE:-latest}"
            ),
            encoding="utf-8",
        )
        result, stderr = self.invoke("inventory")
        self.assertEqual(result, 1)
        self.assertIn("must be required variables", stderr)

    def test_release_workflow_generates_validates_and_uploads_the_manifest(
        self,
    ) -> None:
        workflow_path = ROOT / ".github" / "workflows" / "release-candidate.yml"
        workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        steps = workflow["jobs"]["verify-and-publish"]["steps"]
        names = [step.get("name") for step in steps]
        self.assertNotIn("Build and push verified Evidence release binary", names)
        self.assertNotIn("Build and push verified Mint release binary", names)
        self.assertNotIn("Verify Solmara Evidence and Mint image source labels", names)
        read_pins = next(
            step
            for step in steps
            if step.get("name") == "Read immutable Registry Stack source identity"
        )["run"]
        self.assertIn("SOLMARA_EVIDENCE_IMAGE SOLMARA_MINT_IMAGE", read_pins)
        runtime_verification = next(
            step
            for step in steps
            if step.get("name")
            == "Verify official Registry Stack runtime images and Relayctl"
        )["run"]
        self.assertIn("for component in relay evidence mint", runtime_verification)
        self.assertIn(
            "REGISTRY_STACK_RELEASE_RELAYCTL_ASSET_SHA256", runtime_verification
        )
        self.assertNotIn("REGISTRY_STACK_RELEASE_EVIDENCE_ASSET", runtime_verification)
        self.assertNotIn("REGISTRY_STACK_RELEASE_MINT_ASSET", runtime_verification)
        provisioner_index = names.index("Build and push authority provisioner")
        signer_index = names.index("Build and push Transit signer")
        generate_index = names.index("Generate Coolify image manifest")
        upload_index = names.index("Upload Coolify image manifest")
        self.assertLess(provisioner_index, generate_index)
        self.assertLess(signer_index, generate_index)
        self.assertGreater(
            generate_index, names.index("Build and push eSignet seed image")
        )
        self.assertGreater(upload_index, generate_index)

        provisioner = steps[provisioner_index]
        self.assertEqual(provisioner["id"], "authority_provisioner")
        self.assertEqual(
            provisioner["with"]["file"],
            "docker/hosted-authority-provisioner/Dockerfile",
        )
        self.assertIn(
            "/solmara-lab-authority-provisioner:",
            provisioner["with"]["tags"],
        )
        self.assertIn(
            "REGISTRY_STACK_RELEASE_RELAYCTL_ASSET_URL=${{ env.REGISTRY_STACK_RELEASE_RELAYCTL_ASSET_URL }}",
            provisioner["with"]["build-args"],
        )
        self.assertIn(
            "REGISTRY_STACK_RELEASE_RELAYCTL_ASSET_SHA256=${{ env.REGISTRY_STACK_RELEASE_RELAYCTL_ASSET_SHA256 }}",
            provisioner["with"]["build-args"],
        )
        signer = steps[signer_index]
        self.assertEqual(signer["id"], "transit_signer")
        self.assertEqual(
            signer["with"]["file"], "docker/hosted-transit-signer/Dockerfile"
        )
        self.assertIn("/solmara-lab-transit-signer:", signer["with"]["tags"])
        for step in (provisioner, signer):
            self.assertIn(
                "org.opencontainers.image.revision=${{ github.sha }}",
                step["with"]["labels"],
            )
            self.assertIn(
                "org.opencontainers.image.source=https://github.com/registrystack/solmara-lab",
                step["with"]["labels"],
            )

        label_verification = next(
            step
            for step in steps
            if step.get("name") == "Verify hosted authority image source labels"
        )["run"]
        self.assertIn("steps.authority_provisioner.outputs.digest", label_verification)
        self.assertIn("steps.transit_signer.outputs.digest", label_verification)
        self.assertIn("org.opencontainers.image.revision", label_verification)

        provisioner_smoke = next(
            step
            for step in steps
            if step.get("name") == "Smoke hosted authority provisioner image"
        )["run"]
        self.assertEqual(provisioner_smoke.count("--platform linux/amd64"), 3)
        self.assertEqual(provisioner_smoke.count("--user 0:0"), 3)
        expected_capability_uses = {"CHOWN": 2, "DAC_OVERRIDE": 3, "FOWNER": 3}
        for capability, uses in expected_capability_uses.items():
            self.assertEqual(provisioner_smoke.count(f"--cap-add {capability}"), uses)
        self.assertIn("org.registrystack.release.revision", label_verification)

        provisioner_smoke = next(
            step
            for step in steps
            if step.get("name") == "Smoke hosted authority provisioner image"
        )["run"]
        self.assertIn("steps.authority_provisioner.outputs.digest", provisioner_smoke)
        self.assertIn("--network none --read-only", provisioner_smoke)
        self.assertNotIn("--secrets", provisioner_smoke)
        self.assertIn('test "$status" -eq 1', provisioner_smoke)
        self.assertIn("hosted target provisioning failed", provisioner_smoke)
        self.assertNotIn('chmod u+w "$state/runtime/runtime.yaml"', provisioner_smoke)
        self.assertIn("--entrypoint python", provisioner_smoke)
        self.assertIn("--cap-add DAC_OVERRIDE --cap-add FOWNER", provisioner_smoke)
        self.assertEqual(
            provisioner_smoke.count(
                "--mint-origin https://mint-authority-cells.solmara.registrystack.org"
            ),
            2,
        )

        signer_smoke = next(
            step
            for step in steps
            if step.get("name") == "Smoke hosted Transit signer image"
        )["run"]
        self.assertIn("steps.transit_signer.outputs.digest", signer_smoke)
        self.assertIn("--network none --read-only --entrypoint python", signer_smoke)
        self.assertIn("import cryptography", signer_smoke)
        self.assertIn("--public-jwk, /tmp/solmara-signing-public.jwk", signer_smoke)
        self.assertIn("v1/transit/keys/solmara-evidence-cra", signer_smoke)
        self.assertIn(
            "signing-private: {environment: SIGNING_PRIVATE_JWK}", signer_smoke
        )
        self.assertIn("target: /tmp/solmara-signing.jwk", signer_smoke)
        self.assertIn(
            "transit-init: {condition: service_completed_successfully}", signer_smoke
        )
        self.assertIn('docker compose -p "$project"', signer_smoke)
        self.assertIn("up -d --wait --wait-timeout 60", signer_smoke)
        self.assertIn('not Path("/tmp/solmara-signing.jwk").exists()', signer_smoke)
        self.assertIn('not glob.glob("/tmp/solmara-transit-*")', signer_smoke)
        self.assertIn('client.connect("/transit/transit-proxy.sock")', signer_smoke)
        self.assertNotIn("--unix-socket", signer_smoke)
        self.assertNotIn("$state/transit", signer_smoke)
        self.assertNotIn("type=bind", signer_smoke)

        packages = next(
            step
            for step in steps
            if step.get("name") == "Require pre-provisioned public Solmara packages"
        )["run"]
        self.assertIn("solmara-lab-authority-provisioner", packages)
        self.assertIn("solmara-lab-transit-signer", packages)
        self.assertNotIn("solmara-lab-evidence", packages)
        self.assertNotIn("solmara-lab-mint", packages)

        generate = steps[generate_index]
        self.assertIn("hosted-image-manifest.py write", generate["run"])
        self.assertIn("hosted-image-manifest.py validate", generate["run"])
        self.assertEqual(set(generate["env"]), set(self.module.EXPECTED_KEYS))
        self.assertEqual(
            generate["env"]["REGISTRY_RELAY_IMAGE"],
            "${{ env.REGISTRY_RELAY_IMAGE }}",
        )
        self.assertEqual(
            generate["env"]["SOLMARA_EVIDENCE_IMAGE"],
            "${{ env.SOLMARA_EVIDENCE_IMAGE }}",
        )
        self.assertEqual(
            generate["env"]["SOLMARA_MINT_IMAGE"],
            "${{ env.SOLMARA_MINT_IMAGE }}",
        )
        self.assertEqual(
            generate["env"]["SOLMARA_AUTHORITY_PROVISIONER_IMAGE"],
            "${{ env.SOLMARA_IMAGE_REGISTRY }}/solmara-lab-authority-provisioner@${{ steps.authority_provisioner.outputs.digest }}",
        )
        self.assertEqual(
            generate["env"]["SOLMARA_TRANSIT_SIGNER_IMAGE"],
            "${{ env.SOLMARA_IMAGE_REGISTRY }}/solmara-lab-transit-signer@${{ steps.transit_signer.outputs.digest }}",
        )

        upload = steps[upload_index]
        self.assertEqual(
            upload["uses"],
            "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02",
        )
        self.assertEqual(upload["with"]["if-no-files-found"], "error")
        self.assertIn("solmara-hosted-images.env", upload["with"]["path"])


if __name__ == "__main__":
    unittest.main()
