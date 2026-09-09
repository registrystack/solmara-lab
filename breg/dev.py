#!/usr/bin/env python3
"""Drive the native, retained synthetic BREG identity fixture without printing secrets."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import uuid

import yaml


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "breg/population"
SECRETS = ROOT / "config/evidence/local/esignet-v2"
FIELDS = ["uin", "status", "givenName", "familyName", "birthdate", "gender"]


def command(*args):
    result = subprocess.run(args, text=True, capture_output=True, check=False)
    if result.returncode:
        # Native failures can include paths to private diagnostic files. Do not
        # forward subprocess output, which may be a token on partial failure.
        raise RuntimeError(f"{args[0]} {args[1]} failed; inspect native private diagnostics")
    return result.stdout


def ready(args):
    return json.loads(command(
        args.bregctl, "dev", str(PROJECT), "--breg-port", str(args.breg_port),
        "--mint-port", str(args.mint_port), "--database-port", str(args.database_port),
        "--format", "json",
    ))


def export_provider(args, report):
    SECRETS.mkdir(parents=True, exist_ok=True, mode=0o700)
    if SECRETS.is_symlink() or SECRETS.stat().st_mode & 0o077:
        raise RuntimeError("provider secret directory must be an owner-only ordinary directory")
    exported = json.loads(command(
        args.bregctl, "dev", "export-client", str(PROJECT), "--client", "esignet",
        "--client-id-file", str(SECRETS / "mint-client-id"),
        "--assertion-key-file", str(SECRETS / "mint-private.jwk"), "--format", "json",
    ))
    if not exported.get("ok"):
        raise RuntimeError("native client export failed")
    container_root = "/etc/registry-esignet"
    config = {
        "subject_id_type": "uin", "psut_secret_file": f"{container_root}/psut-secret",
        "breg": {"base_url": f"http://{args.provider_host}:{args.breg_port}",
                 "route": "population", "selector": "by-uin", "selector_field": "uin",
                 "access_profile": "esignet-source", "provisioned_fields": FIELDS,
                 "account_check_fields": ["uin", "status"]},
        "mint": {"token_endpoint": f"http://{args.provider_host}:{args.mint_port}/token",
                 "assertion_audience": report["tokenEndpoint"],
                 "client_id": (SECRETS / "mint-client-id").read_text().strip(),
                 "private_key_file": f"{container_root}/mint-private.jwk"},
        "claim_map": {"sub": "$psut", "individual_id": "uin", "given_name": "givenName", "family_name": "familyName",
                      "birthdate": "birthdate", "gender": "gender"},
        "http": {"allow_insecure_http": True, "timeout_seconds": 10,
                 "max_response_bytes": 1048576},
        "demo": {"static_otp_enabled": True, "static_otp_file": f"{container_root}/static-otp"},
    }
    path = SECRETS / "registry.yaml"
    if path.is_symlink():
        raise RuntimeError("provider config must be an ordinary file")
    fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as output:
        yaml.safe_dump(config, output, sort_keys=False)
    print(f"Native registry ready; provider configuration: {path}")


def token(args, report, client):
    identity = next(item for item in report["clients"] if item["id"] == client)
    return command(args.mint, "token", "--url", report["tokenEndpoint"], "--client-id",
                   Path(identity["clientIdFile"]).read_text().strip(), "--key",
                   identity["assertionKeyFile"]).strip()


def request(base, credential, method, suffix, body=None):
    headers = {"Accept": "application/json"}
    if credential:
        headers["Authorization"] = "Bearer " + credential
    if body is not None:
        headers["Content-Type"] = "application/json"
    if method == "POST" and ":lookup" not in suffix:
        headers["Idempotency-Key"] = str(uuid.uuid4())
    req = urllib.request.Request(base + suffix, method=method, headers=headers,
                                 data=None if body is None else json.dumps(body).encode())
    # Match the native loop's direct, no-proxy HTTP behavior.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        response = opener.open(req, timeout=10)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        return response.status, json.load(response)


def verify(args, report):
    source = token(args, report, "esignet")
    base = report["bregUrl"]
    checks = 0

    def lookup(uin, fields, credential=source, selector="by-uin"):
        query = urllib.parse.urlencode({"accessProfile": "esignet-source", "$select": fields})
        return request(base, credential, "POST", "/v1/records/population:lookup?" + query,
                       {"selector": selector, "values": {"uin": uin}})

    status, document = lookup("2300010248", "uin,status")
    assert status == 200 and document["data"]["domainData"] == {
        "uin": "2300010248", "status": "active"}, "minimal account projection failed"
    record_id = document["data"]["recordIdentifier"]
    checks += 1
    status, document = lookup("2300010248", "givenName,familyName")
    assert status == 200 and document["data"]["domainData"] == {
        "givenName": "Mateo", "familyName": "Santos"}, "consented projection failed"
    checks += 1
    status, document = lookup("2300010248", "uin")
    assert status == 200 and document["data"]["domainData"] == {
        "uin": "2300010248"}, "consented business identifier projection failed"
    checks += 1
    for identity, selector in [("2399999998", "by-uin"), ("2399999999", "by-uin"),
                               ("2300010248", "unknown-selector")]:
        status, document = lookup(identity, "uin,status", selector=selector)
        assert status == 404 and document["code"] == "lookup.unresolved", "concealment failed"
        checks += 1
    status, document = lookup("2300010248", "operatorNote")
    assert status == 404 and document["code"] == "resource.not_found", "hidden field disclosed"
    checks += 1
    for method, suffix, body in [
        ("GET", "", None), ("GET", "/" + urllib.parse.quote(record_id, safe=""), None),
        ("POST", "", {"uin": "2300010248"}),
    ]:
        status, document = request(base, source, method,
            "/v1/records/population" + suffix + "?accessProfile=esignet-source", body)
        assert status == 404 and document["code"] == "resource.not_found", "source grant exceeded"
        checks += 1
    status, document = lookup("2300010248", "uin,status", credential="")
    assert status == 404 and document["code"] == "resource.not_found", "anonymous lookup allowed"
    checks += 1
    status, document = lookup("2300010248", "uin,status", credential="invalid")
    assert status == 401 and document["code"] == "authentication.refused", "invalid bearer allowed"
    checks += 1
    operator = token(args, report, "operator")
    first = yaml.safe_load((PROJECT / "dev-clients.yaml").read_text())["seed"][0]["data"]
    status, document = request(base, operator, "POST",
                              "/v1/records/population?accessProfile=operator", {"data": first})
    assert status == 409 and document["code"] == "mutation.conflict", "unique UIN not enforced"
    checks += 1
    print(f"PASS: {checks} real Mint/BREG/PostgreSQL boundary checks; no subject data or tokens logged")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "verify", "stop"])
    parser.add_argument("--bregctl", default="bregctl")
    parser.add_argument("--mint", default="mint")
    parser.add_argument("--breg-port", type=int, default=18190)
    parser.add_argument("--mint-port", type=int, default=18191)
    parser.add_argument("--database-port", type=int, default=55449)
    parser.add_argument("--provider-host", default="host.docker.internal")
    args = parser.parse_args()
    if args.action == "stop":
        command(args.bregctl, "dev", "stop", str(PROJECT), "--format", "json")
        print("Stopped fixture services; retained database and credentials preserved")
        return
    report = ready(args)
    if args.action == "start":
        export_provider(args, report)
    else:
        verify(args, report)


if __name__ == "__main__":
    main()
