from __future__ import annotations

import ipaddress
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PROVISION_PATH = ROOT / "compose.coolify.provision.yaml"
RUNTIME_PATHS = {
    "core": ROOT / "compose.coolify.yaml",
    "interior": ROOT / "compose.coolify.interior.yaml",
    "social": ROOT / "compose.coolify.social-development.yaml",
    "pensions": ROOT / "compose.coolify.labour-pensions.yaml",
    "agriculture": ROOT / "compose.coolify.agriculture.yaml",
}
EXPECTED_SUBNETS = {
    "core": "172.29.1.0/24",
    "interior": "172.29.2.0/24",
    "social": "172.29.3.0/24",
    "pensions": "172.29.4.0/24",
    "agriculture": "172.29.5.0/24",
}
# Every provisioned service listens on all interfaces. Its Compose application
# also joins a Coolify-managed network that carries the ingress proxy, and a
# listener bound to the private runtime address alone refuses that proxy.
# Isolation comes from network membership rather than from the bind address: no
# application's networks contain another application's containers, so binding
# every interface reaches only the owning application and the proxy.
BIND_HOST = "0.0.0.0"
# Coolify exports the application uuid into the environment it runs Compose in,
# and names the network that carries the ingress proxy after it.
INGRESS_NETWORK = "${COOLIFY_RESOURCE_UUID:?set by Coolify for every deployment}"
PROVISIONED_SERVICES = {
    "mint-provisioner": ("core", "mint", "172.29.1.20"),
    "cra-evidence-provisioner": ("interior", "cra_evidence", "172.29.2.21"),
    "nia-evidence-provisioner": ("interior", "nia_evidence", "172.29.2.22"),
    "sro-evidence-provisioner": ("social", "sro_evidence", "172.29.3.23"),
    "mosd-evidence-provisioner": (
        "social",
        "mosd_programme_evidence",
        "172.29.3.24",
    ),
    "sipf-evidence-provisioner": ("pensions", "sipf_evidence", "172.29.4.25"),
    "nagdi-evidence-provisioner": (
        "agriculture",
        "nagdi_evidence",
        "172.29.5.26",
    ),
}


class HostedNetworkIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.provision = yaml.safe_load(PROVISION_PATH.read_text(encoding="utf-8"))
        cls.runtime = {
            name: yaml.safe_load(path.read_text(encoding="utf-8"))
            for name, path in RUNTIME_PATHS.items()
        }

    def test_runtime_apps_use_distinct_expected_private_subnets(self) -> None:
        networks = {}
        for name, compose in self.runtime.items():
            subnet_text = compose["networks"]["runtime"]["ipam"]["config"][0]["subnet"]
            self.assertEqual(subnet_text, EXPECTED_SUBNETS[name])
            network = ipaddress.ip_network(subnet_text)
            self.assertTrue(network.is_private)
            networks[name] = network

        for name, network in networks.items():
            for other_name, other_network in networks.items():
                if name >= other_name:
                    continue
                self.assertFalse(
                    network.overlaps(other_network),
                    f"{name} {network} overlaps {other_name} {other_network}",
                )

    def test_every_provisioner_binds_all_interfaces(self) -> None:
        services_with_bind_hosts = {
            name
            for name, service in self.provision["services"].items()
            if "--bind-host" in service.get("command", [])
        }
        self.assertEqual(services_with_bind_hosts, set(PROVISIONED_SERVICES))

        for provisioner_name in PROVISIONED_SERVICES:
            command = self.provision["services"][provisioner_name]["command"]
            bind_host = command[command.index("--bind-host") + 1]
            self.assertEqual(bind_host, BIND_HOST, provisioner_name)

    def test_provisioned_services_keep_distinct_addresses_in_their_subnet(self) -> None:
        addresses = {}
        for app, service_name, expected_address in PROVISIONED_SERVICES.values():
            runtime_address = self.runtime[app]["services"][service_name]["networks"][
                "runtime"
            ]["ipv4_address"]
            self.assertEqual(runtime_address, expected_address, service_name)
            self.assertIn(
                ipaddress.ip_address(expected_address),
                ipaddress.ip_network(EXPECTED_SUBNETS[app]),
            )
            self.assertNotIn(
                expected_address,
                addresses,
                f"{service_name} reuses the address of {addresses.get(expected_address)}",
            )
            addresses[expected_address] = service_name

    def test_routed_services_on_the_runtime_network_name_the_ingress_network(
        self,
    ) -> None:
        """Traefik reads a container's address from the first network it iterates
        when no network is named, and that order is randomised, so a service that
        joins both the runtime network and the ingress network is routed to its
        private runtime address on roughly half of every proxy configuration
        rebuild and then answers nothing. Naming the ingress network removes the
        choice. A service that joins the ingress network alone has no choice to
        remove, so it carries no label."""
        pinned = 0
        for app, compose in self.runtime.items():
            for service_name, service in compose["services"].items():
                labels = service.get("labels") or {}
                if "solmara.lab.host" not in labels:
                    continue
                where = f"{app}/{service_name}"
                if "runtime" not in (service.get("networks") or {}):
                    self.assertNotIn("traefik.docker.network", labels, where)
                    continue
                self.assertEqual(
                    labels.get("traefik.docker.network"), INGRESS_NETWORK, where
                )
                pinned += 1
        self.assertEqual(pinned, 12)

    def test_provisioning_services_remain_networkless(self) -> None:
        self.assertNotIn("networks", self.provision)
        for service_name, service in self.provision["services"].items():
            self.assertEqual(service.get("network_mode"), "none", service_name)


if __name__ == "__main__":
    unittest.main()
