#!/usr/bin/env python3
"""Render hosted-only Relay and Notary configs.

Local development keeps Compose-private service URLs in `ministries/` and
`notaries/`. Hosted Coolify apps are split by authority, so cross-entity calls
must use the public TLS endpoints instead of private Compose DNS.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
HOSTED_ROOT = ROOT / "hosted"

RELAY_BASE_URLS = {
    "ministries/interior-civil/config/relay.yaml": "https://cra-relay.solmara.registrystack.org",
    "ministries/interior-population/config/relay.yaml": "https://nia-relay.solmara.registrystack.org",
    "ministries/social-development/config/sro-relay.yaml": "https://sro-relay.solmara.registrystack.org",
    "ministries/social-development/config/programme-mis-relay.yaml": "https://mosd-programme-relay.solmara.registrystack.org",
    "ministries/labour-pensions/config/relay.yaml": "https://sipf-relay.solmara.registrystack.org",
    "ministries/agriculture-nagdi/config/relay.yaml": "https://nagdi-relay.solmara.registrystack.org",
}

RELAY_PUBLIC_URLS = {
    "civil": "https://cra-relay.solmara.registrystack.org",
    "population": "https://nia-relay.solmara.registrystack.org",
    "social": "https://sro-relay.solmara.registrystack.org",
    "programme": "https://mosd-programme-relay.solmara.registrystack.org",
    "pensions": "https://sipf-relay.solmara.registrystack.org",
    "agriculture": "https://nagdi-relay.solmara.registrystack.org",
}


@dataclass(frozen=True)
class NotaryRender:
    public_url: str
    source_urls: dict[str, str]


NOTARY_CONFIGS = {
    "notaries/child-benefit.yaml": NotaryRender(
        public_url="https://child-benefit-notary.solmara.registrystack.org",
        source_urls={
            "civil": RELAY_PUBLIC_URLS["civil"],
            "population": RELAY_PUBLIC_URLS["population"],
            "social": RELAY_PUBLIC_URLS["social"],
            "programme": RELAY_PUBLIC_URLS["programme"],
        },
    ),
    "notaries/pension.yaml": NotaryRender(
        public_url="https://pension-notary.solmara.registrystack.org",
        source_urls={
            "civil": RELAY_PUBLIC_URLS["civil"],
            "population": RELAY_PUBLIC_URLS["population"],
            "pensions": RELAY_PUBLIC_URLS["pensions"],
            "programme": RELAY_PUBLIC_URLS["programme"],
        },
    ),
    "notaries/nagdi.yaml": NotaryRender(
        public_url="https://nagdi-notary.solmara.registrystack.org",
        source_urls={
            "agriculture": RELAY_PUBLIC_URLS["agriculture"],
        },
    ),
    "notaries/citizen.yaml": NotaryRender(
        public_url="https://citizen-notary.solmara.registrystack.org",
        source_urls={
            "civil": RELAY_PUBLIC_URLS["civil"],
            "population": RELAY_PUBLIC_URLS["population"],
            "social": RELAY_PUBLIC_URLS["social"],
            "programme": RELAY_PUBLIC_URLS["programme"],
            "pensions": RELAY_PUBLIC_URLS["pensions"],
            "agriculture": RELAY_PUBLIC_URLS["agriculture"],
        },
    ),
}


def read_yaml(relative: str) -> object:
    return yaml.safe_load((ROOT / relative).read_text(encoding="utf-8"))


def dump_yaml(value: object) -> str:
    return yaml.safe_dump(
        value,
        allow_unicode=False,
        default_flow_style=False,
        sort_keys=False,
        width=1000,
    )


def render_relay(relative: str, public_url: str) -> str:
    data = read_yaml(relative)
    data["catalog"]["base_url"] = public_url
    return dump_yaml(data)


def render_notary(relative: str, render: NotaryRender) -> str:
    data = read_yaml(relative)
    evidence = data["evidence"]
    evidence["api_base_url"] = render.public_url
    source_connections = evidence["source_connections"]
    for source_name, public_url in render.source_urls.items():
        source = source_connections[source_name]
        source["base_url"] = public_url
        source.pop("allow_insecure_private_network", None)
    return dump_yaml(data)


def expected_files() -> dict[Path, str]:
    rendered: dict[Path, str] = {}
    for relative, public_url in RELAY_BASE_URLS.items():
        rendered[HOSTED_ROOT / relative] = render_relay(relative, public_url)
    for relative, config in NOTARY_CONFIGS.items():
        rendered[HOSTED_ROOT / relative] = render_notary(relative, config)
    return rendered


def validate_rendered(path: Path, text: str) -> list[str]:
    failures: list[str] = []
    relative = path.relative_to(ROOT)
    if "http://" in text:
        failures.append(f"{relative}: hosted configs must not contain plaintext HTTP URLs")
    if "allow_insecure_private_network" in text:
        failures.append(f"{relative}: hosted configs must not enable private-network source escapes")
    return failures


def write_files(rendered: dict[Path, str]) -> None:
    for path, text in rendered.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def check_files(rendered: dict[Path, str]) -> list[str]:
    failures: list[str] = []
    for path, expected in rendered.items():
        if not path.exists():
            failures.append(f"{path.relative_to(ROOT)}: missing; run scripts/render-hosted-configs.py")
            continue
        actual = path.read_text(encoding="utf-8")
        if actual != expected:
            failures.append(f"{path.relative_to(ROOT)}: not up to date; run scripts/render-hosted-configs.py")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if generated hosted configs are stale")
    args = parser.parse_args()

    rendered = expected_files()
    failures: list[str] = []
    for path, text in rendered.items():
        failures.extend(validate_rendered(path, text))
    if args.check:
        failures.extend(check_files(rendered))
    else:
        write_files(rendered)

    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
