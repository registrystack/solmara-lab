from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils

SCRIPT = Path(__file__).with_name("local-transit-proxy.py")
SPEC = importlib.util.spec_from_file_location("local_transit_proxy", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def private_jwk(private_key: ec.EllipticCurvePrivateKey) -> dict[str, str]:
    private = private_key.private_numbers()
    public = private.public_numbers
    return {
        "alg": "ES256",
        "crv": "P-256",
        "d": b64url(private.private_value.to_bytes(32, "big")),
        "kid": "solmara-test-key",
        "kty": "EC",
        "x": b64url(public.x.to_bytes(32, "big")),
        "y": b64url(public.y.to_bytes(32, "big")),
    }


class LocalTransitProxyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(dir="/tmp", prefix="stp-")
        self.root = Path(self.temporary.name)
        self.private_key = ec.generate_private_key(ec.SECP256R1())
        self.jwk = private_jwk(self.private_key)
        self.key_path = self.root / "signing.jwk"
        self.key_path.write_text(
            json.dumps(self.jwk, separators=(",", ":"), sort_keys=True),
            encoding="utf-8",
        )
        self.key_path.chmod(0o600)
        self.socket_path = self.root / "transit.sock"
        self.server = None
        self.thread = None

    def tearDown(self) -> None:
        if self.server is not None:
            if self.thread is not None and self.thread.is_alive():
                self.server.shutdown()
                self.thread.join(timeout=2)
            self.server.server_close()
        self.temporary.cleanup()

    def start(self) -> None:
        self.server = MODULE.build_server(
            self.key_path, self.socket_path, "solmara-test-key"
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes = b"",
        vault_header: str | None = "true",
        content_type: str | None = None,
        extra_headers: list[tuple[str, str]] | None = None,
        declared_length: int | None = None,
    ) -> tuple[int, bytes, bytes]:
        headers = [("Host", "localhost"), ("Connection", "close")]
        if vault_header is not None:
            headers.append(("X-Vault-Request", vault_header))
        if content_type is not None:
            headers.append(("Content-Type", content_type))
        if body or declared_length is not None:
            headers.append(
                (
                    "Content-Length",
                    str(len(body) if declared_length is None else declared_length),
                )
            )
        headers.extend(extra_headers or [])
        request = (
            f"{method} {path} HTTP/1.1\r\n"
            + "".join(f"{name}: {value}\r\n" for name, value in headers)
            + "\r\n"
        ).encode("ascii") + body
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(2)
            client.connect(str(self.socket_path))
            client.sendall(request)
            try:
                client.shutdown(socket.SHUT_WR)
            except OSError:
                # A small refusal can be written and closed before shutdown.
                pass
            chunks = bytearray()
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    break
                chunks.extend(chunk)
        head, response_body = bytes(chunks).split(b"\r\n\r\n", 1)
        status = int(head.split(b" ", 2)[1])
        return status, head, response_body

    def sign_body(self, payload: bytes, **updates: object) -> bytes:
        document: dict[str, object] = {
            "input": base64.b64encode(hashlib.sha256(payload).digest()).decode("ascii"),
            "key_version": 1,
            "marshaling_algorithm": "jws",
            "prehashed": True,
        }
        document.update(updates)
        return json.dumps(document, separators=(",", ":")).encode("utf-8")

    def test_metadata_and_prehashed_signature_match_the_transit_contract(self) -> None:
        self.start()
        status, _, body = self.request("GET", "/v1/transit/keys/solmara-test-key")
        self.assertEqual(status, 200)
        data = json.loads(body)["data"]
        self.assertEqual(data["type"], "ecdsa-p256")
        self.assertIs(data["supports_signing"], True)
        for field in ("derived", "exportable", "allow_plaintext_backup"):
            self.assertIs(data[field], False)
        self.assertEqual(data["latest_version"], 1)
        self.assertEqual(data["min_encryption_version"], 1)
        public_from_metadata = serialization.load_pem_public_key(
            data["keys"]["1"]["public_key"].encode("ascii")
        )
        self.assertEqual(
            public_from_metadata.public_numbers(),
            self.private_key.public_key().public_numbers(),
        )

        payload = b"Solmara authority-owned Evidence"
        sign_body = self.sign_body(payload)
        status, _, body = self.request(
            "POST",
            "/v1/transit/sign/solmara-test-key/sha2-256",
            body=sign_body,
            content_type="application/json",
        )
        self.assertEqual(status, 200)
        signature_text = json.loads(body)["data"]["signature"]
        self.assertTrue(signature_text.startswith("vault:v1:"))
        raw = base64.urlsafe_b64decode(signature_text.removeprefix("vault:v1:") + "==")
        self.assertEqual(len(raw), 64)
        der = utils.encode_dss_signature(
            int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big")
        )
        self.private_key.public_key().verify(
            der,
            hashlib.sha256(payload).digest(),
            ec.ECDSA(utils.Prehashed(hashes.SHA256())),
        )

    def test_wrong_path_header_and_key_are_generically_refused(self) -> None:
        self.start()
        cases = [
            self.request("GET", "/v1/transit/keys/another-key"),
            self.request("GET", "/v1/other/keys/solmara-test-key"),
            self.request(
                "GET", "/v1/transit/keys/solmara-test-key", vault_header=None
            ),
            self.request(
                "GET", "/v1/transit/keys/solmara-test-key", vault_header="false"
            ),
        ]
        self.assertEqual([status for status, _, _ in cases], [404, 404, 403, 403])
        self.assertTrue(all(body == MODULE.ERROR_DOCUMENT for _, _, body in cases))

    def test_wrong_version_and_every_nonexact_body_are_refused(self) -> None:
        self.start()
        path = "/v1/transit/sign/solmara-test-key/sha2-256"
        bodies = [
            self.sign_body(b"payload", key_version=2),
            self.sign_body(b"payload", prehashed=False),
            self.sign_body(b"payload", marshaling_algorithm="asn1"),
            self.sign_body(b"payload", input=base64.b64encode(b"short").decode()),
            self.sign_body(b"payload", unexpected=True),
            b'{"input":"one","input":"two","key_version":1,"marshaling_algorithm":"jws","prehashed":true}',
            b"not-json",
        ]
        for body in bodies:
            with self.subTest(body=body[:40]):
                status, _, response = self.request(
                    "POST", path, body=body, content_type="application/json"
                )
                self.assertEqual(status, 400)
                self.assertEqual(response, MODULE.ERROR_DOCUMENT)
        status, _, response = self.request("POST", path, body=self.sign_body(b"payload"))
        self.assertEqual((status, response), (400, MODULE.ERROR_DOCUMENT))

    def test_request_and_header_bounds_fail_closed(self) -> None:
        self.start()
        path = "/v1/transit/sign/solmara-test-key/sha2-256"
        status, _, response = self.request(
            "POST",
            path,
            content_type="application/json",
            declared_length=MODULE.MAX_REQUEST_BODY_BYTES + 1,
        )
        self.assertEqual((status, response), (400, MODULE.ERROR_DOCUMENT))
        status, _, response = self.request(
            "GET",
            "/v1/transit/keys/solmara-test-key",
            extra_headers=[("X-Fill", "a" * MODULE.MAX_HEADER_LINE_BYTES)],
        )
        self.assertEqual((status, response), (400, MODULE.ERROR_DOCUMENT))

    def test_key_and_socket_permissions_are_enforced(self) -> None:
        self.key_path.chmod(0o644)
        with self.assertRaisesRegex(MODULE.ProxyError, "invalid key"):
            MODULE.build_server(self.key_path, self.socket_path, "solmara-test-key")
        self.key_path.chmod(0o600)
        self.start()
        metadata = self.socket_path.stat()
        self.assertTrue(stat.S_ISSOCK(metadata.st_mode))
        self.assertEqual(stat.S_IMODE(metadata.st_mode), 0o600)

    def test_symlinked_key_and_writable_socket_directory_are_refused(self) -> None:
        link = self.root / "link.jwk"
        link.symlink_to(self.key_path)
        with self.assertRaisesRegex(MODULE.ProxyError, "invalid key"):
            MODULE.build_server(link, self.socket_path, "solmara-test-key")
        self.root.chmod(0o777)
        try:
            with self.assertRaisesRegex(MODULE.ProxyError, "invalid socket"):
                MODULE.build_server(self.key_path, self.socket_path, "solmara-test-key")
        finally:
            self.root.chmod(0o700)

    def test_responses_and_errors_never_expose_private_material(self) -> None:
        self.start()
        private_canary = self.jwk["d"].encode("ascii")
        responses = [
            self.request("GET", "/v1/transit/keys/solmara-test-key")[2],
            self.request("GET", "/v1/transit/keys/private-canary")[2],
            self.request(
                "POST",
                "/v1/transit/sign/solmara-test-key/sha2-256",
                body=b'{"input":"private-canary"}',
                content_type="application/json",
            )[2],
        ]
        self.assertTrue(all(private_canary not in response for response in responses))
        metadata = json.loads(responses[0])
        self.assertNotIn("d", metadata["data"]["keys"]["1"])
        application = self.server.application

        class FailingKey:
            def sign(self, _digest: bytes, _algorithm: object) -> bytes:
                raise ValueError("private-canary")

        application._private_key = FailingKey()
        failure = self.request(
            "POST",
            "/v1/transit/sign/solmara-test-key/sha2-256",
            body=self.sign_body(b"payload"),
            content_type="application/json",
        )
        self.assertEqual((failure[0], failure[2]), (500, MODULE.ERROR_DOCUMENT))
        self.assertNotIn(b"private-canary", failure[2])
        malformed = dict(self.jwk)
        malformed["d"] = "private-canary"
        self.key_path.write_text(json.dumps(malformed), encoding="utf-8")
        self.key_path.chmod(0o600)
        with self.assertRaises(MODULE.ProxyError) as context:
            MODULE.TransitApplication(self.key_path, "solmara-test-key")
        self.assertNotIn("private-canary", str(context.exception))

    def test_cli_sigterm_stops_cleanly_and_removes_its_socket(self) -> None:
        process = subprocess.Popen(
            [
                sys.executable,
                str(SCRIPT),
                "--private-jwk",
                str(self.key_path),
                "--socket",
                str(self.socket_path),
                "--key-name",
                "solmara-test-key",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            for _ in range(100):
                if self.socket_path.exists():
                    break
                self.assertIsNone(process.poll())
                time.sleep(0.01)
            else:
                self.fail("proxy socket did not become ready")
            process.terminate()
            stdout, stderr = process.communicate(timeout=2)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=2)
        self.assertEqual(process.returncode, 0)
        self.assertEqual((stdout, stderr), (b"", b""))
        self.assertFalse(self.socket_path.exists())


if __name__ == "__main__":
    unittest.main()
