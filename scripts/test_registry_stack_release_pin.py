from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("check-registry-stack-release-pin.py")
SPEC = importlib.util.spec_from_file_location("release_pin", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def authenticator_values() -> dict[str, str]:
    base = "https://github.com/jeremi/esignet-relay-authenticator/releases/download/v0.2.0/"
    return {
        "ESIGNET_AUTHENTICATOR_VERSION": "0.2.0",
        "ESIGNET_AUTHENTICATOR_RELEASE_URL": "https://github.com/jeremi/esignet-relay-authenticator/releases/tag/v0.2.0",
        "ESIGNET_AUTHENTICATOR_JAR_URL": base + "esignet-relay-authenticator-0.2.0.jar",
        "ESIGNET_AUTHENTICATOR_JAR_SHA256": "e" * 64,
        "ESIGNET_AUTHENTICATOR_CHECKSUM_URL": base + "esignet-relay-authenticator-0.2.0.jar.sha256",
    }


class ReleasePinTests(unittest.TestCase):
    def test_older_release_is_rejected_in_favour_of_coherent_release(self) -> None:
        values = {"REGISTRY_STACK_REQUIRED_VERSION": "0.20.1", **authenticator_values()}
        self.assertIn("must be 0.21.0", MODULE.validate(values, require_public=False)[0])

    def test_missing_public_digest_is_an_explicit_blocker(self) -> None:
        values = {
            "REGISTRY_STACK_REQUIRED_VERSION": "0.21.0",
            "REGISTRY_STACK_SOURCE_REF": "v0.21.0",
            **authenticator_values(),
        }
        self.assertEqual(MODULE.validate(values, require_public=False), [])
        self.assertIn("promotion is blocked", MODULE.validate(values, require_public=True)[0])

    def test_digest_must_be_exact(self) -> None:
        values = {
            "REGISTRY_STACK_REQUIRED_VERSION": "0.21.0",
            "REGISTRY_STACK_SOURCE_REF": "v0.21.0",
            "REGISTRY_STACK_SOURCE_COMMIT": "f" * 40,
            "REGISTRY_STACK_RELEASE_RELAY_DIGEST": "a" * 64,
            "REGISTRY_STACK_RELEASE_RELAYCTL_ASSET_URL": "https://github.com/registrystack/registry-stack/releases/download/v0.21.0/relayctl-v0.21.0-linux-amd64",
            "REGISTRY_STACK_RELEASE_RELAYCTL_ASSET_SHA256": "d" * 64,
            **authenticator_values(),
        }
        self.assertEqual(MODULE.validate(values, require_public=True), [])
        values["REGISTRY_STACK_RELEASE_RELAY_DIGEST"] = "sha256:" + "a" * 64
        self.assertTrue(MODULE.validate(values, require_public=True))

    def test_public_source_ref_must_bind_the_release_tag(self) -> None:
        values = {
            "REGISTRY_STACK_REQUIRED_VERSION": "0.21.0",
            "REGISTRY_STACK_SOURCE_REF": "main",
            **authenticator_values(),
        }
        self.assertIn(
            "REGISTRY_STACK_SOURCE_REF must be v0.21.0",
            MODULE.validate(values, require_public=False),
        )


if __name__ == "__main__":
    unittest.main()
