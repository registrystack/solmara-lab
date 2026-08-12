#!/usr/bin/env python3
"""Serve one local ES256 key through a narrow Transit-compatible Unix socket.

The proxy is deliberately one process, one key, and one socket. Registry
processes receive only the socket. The operator-owned private JWK stays outside
their containers and is never rendered in responses or diagnostics.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import re
import signal
import socket
import socketserver
import stat
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils

MAX_KEY_BYTES = 16 * 1024
MAX_REQUEST_LINE_BYTES = 2 * 1024
MAX_HEADER_BYTES = 8 * 1024
MAX_HEADER_LINE_BYTES = 2 * 1024
MAX_REQUEST_BODY_BYTES = 2 * 1024
MAX_RESPONSE_BODY_BYTES = 64 * 1024
SOCKET_TIMEOUT_SECONDS = 3
ERROR_DOCUMENT = b'{"errors":["request refused"]}'
KEY_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
HEADER_NAME = re.compile(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+\Z")
JWK_MEMBERS = {"alg", "crv", "d", "kid", "kty", "x", "y"}


class ProxyError(Exception):
    """Value-free configuration or request refusal."""


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProxyError("invalid document")
        result[key] = value
    return result


def _decode_base64url(value: Any) -> bytes:
    if not isinstance(value, str) or not value or "=" in value:
        raise ProxyError("invalid key")
    try:
        decoded = base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
        )
    except (binascii.Error, ValueError) as error:
        raise ProxyError("invalid key") from error
    if base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii") != value:
        raise ProxyError("invalid key")
    return decoded


def _read_private_jwk(path: Path) -> tuple[ec.EllipticCurvePrivateKey, str]:
    if not path.is_absolute():
        raise ProxyError("invalid key")
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ProxyError("invalid key") from error
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or metadata.st_mode & 0o077
            or metadata.st_size <= 0
            or metadata.st_size > MAX_KEY_BYTES
        ):
            raise ProxyError("invalid key")
        chunks = bytearray()
        while len(chunks) <= MAX_KEY_BYTES:
            chunk = os.read(descriptor, min(4096, MAX_KEY_BYTES + 1 - len(chunks)))
            if not chunk:
                break
            chunks.extend(chunk)
        if len(chunks) > MAX_KEY_BYTES:
            raise ProxyError("invalid key")
    finally:
        os.close(descriptor)

    try:
        document = json.loads(chunks, object_pairs_hook=_strict_object)
    except (json.JSONDecodeError, UnicodeDecodeError, ProxyError) as error:
        raise ProxyError("invalid key") from error
    if not isinstance(document, dict) or set(document) != JWK_MEMBERS:
        raise ProxyError("invalid key")
    if (
        document["kty"] != "EC"
        or document["crv"] != "P-256"
        or document["alg"] != "ES256"
        or not isinstance(document["kid"], str)
        or not document["kid"].strip()
        or len(document["kid"]) > 256
        or any(
            ord(character) < 0x20 or ord(character) == 0x7F
            for character in document["kid"]
        )
    ):
        raise ProxyError("invalid key")

    x_bytes = _decode_base64url(document["x"])
    y_bytes = _decode_base64url(document["y"])
    scalar_bytes = _decode_base64url(document["d"])
    if len(x_bytes) != 32 or len(y_bytes) != 32 or len(scalar_bytes) != 32:
        raise ProxyError("invalid key")
    try:
        private_key = ec.derive_private_key(
            int.from_bytes(scalar_bytes, "big"), ec.SECP256R1()
        )
    except ValueError as error:
        raise ProxyError("invalid key") from error
    public = private_key.public_key().public_numbers()
    if (
        public.x.to_bytes(32, "big") != x_bytes
        or public.y.to_bytes(32, "big") != y_bytes
    ):
        raise ProxyError("invalid key")
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    return private_key, public_pem


def _validate_socket_path(path: Path) -> None:
    if not path.is_absolute() or path.exists() or path.is_symlink():
        raise ProxyError("invalid socket")
    try:
        parent = path.parent.stat()
    except OSError as error:
        raise ProxyError("invalid socket") from error
    if (
        not stat.S_ISDIR(parent.st_mode)
        or parent.st_uid != os.geteuid()
        or parent.st_mode & 0o022
    ):
        raise ProxyError("invalid socket")


class TransitApplication:
    def __init__(self, private_jwk: Path, key_name: str) -> None:
        if not KEY_NAME.fullmatch(key_name):
            raise ProxyError("invalid key")
        self._private_key, public_pem = _read_private_jwk(private_jwk)
        self._metadata = json.dumps(
            {
                "data": {
                    "allow_plaintext_backup": False,
                    "deletion_allowed": False,
                    "derived": False,
                    "exportable": False,
                    "imported": True,
                    "keys": {"1": {"public_key": public_pem}},
                    "latest_version": 1,
                    "min_decryption_version": 1,
                    "min_encryption_version": 1,
                    "name": key_name,
                    "supports_decryption": False,
                    "supports_derivation": False,
                    "supports_encryption": False,
                    "supports_signing": True,
                    "type": "ecdsa-p256",
                }
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        self.metadata_path = f"/v1/transit/keys/{key_name}"
        self.sign_path = f"/v1/transit/sign/{key_name}/sha2-256"

    def dispatch(
        self, method: str, path: str, headers: dict[str, str], body: bytes
    ) -> tuple[int, bytes]:
        if headers.get("x-vault-request") != "true":
            return 403, ERROR_DOCUMENT
        if method == "GET" and path == self.metadata_path:
            if body:
                return 400, ERROR_DOCUMENT
            return 200, self._metadata
        if method == "POST" and path == self.sign_path:
            if headers.get("content-type") != "application/json":
                return 400, ERROR_DOCUMENT
            try:
                document = json.loads(body, object_pairs_hook=_strict_object)
            except (json.JSONDecodeError, UnicodeDecodeError, ProxyError):
                return 400, ERROR_DOCUMENT
            if (
                not isinstance(document, dict)
                or set(document) != {
                    "input",
                    "key_version",
                    "marshaling_algorithm",
                    "prehashed",
                }
                or type(document["key_version"]) is not int
                or document["key_version"] != 1
                or document["marshaling_algorithm"] != "jws"
                or document["prehashed"] is not True
                or not isinstance(document["input"], str)
            ):
                return 400, ERROR_DOCUMENT
            try:
                digest = base64.b64decode(document["input"], validate=True)
            except (binascii.Error, ValueError):
                return 400, ERROR_DOCUMENT
            if len(digest) != 32 or base64.b64encode(digest).decode("ascii") != document["input"]:
                return 400, ERROR_DOCUMENT
            der_signature = self._private_key.sign(
                digest, ec.ECDSA(utils.Prehashed(hashes.SHA256()))
            )
            r_value, s_value = utils.decode_dss_signature(der_signature)
            raw_signature = r_value.to_bytes(32, "big") + s_value.to_bytes(32, "big")
            encoded = base64.urlsafe_b64encode(raw_signature).rstrip(b"=").decode("ascii")
            response = json.dumps(
                {"data": {"signature": f"vault:v1:{encoded}"}},
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            return 200, response
        return 404, ERROR_DOCUMENT


class TransitRequestHandler(socketserver.StreamRequestHandler):
    server: "TransitServer"

    def handle(self) -> None:
        self.connection.settimeout(SOCKET_TIMEOUT_SECONDS)
        try:
            method, path, headers, body = self._read_request()
            status, response = self.server.application.dispatch(method, path, headers, body)
        except ProxyError:
            status, response = 400, ERROR_DOCUMENT
        except (OSError, TimeoutError):
            return
        except Exception:
            status, response = 500, ERROR_DOCUMENT
        try:
            self._write_response(status, response)
        except OSError:
            pass

    def _read_request(self) -> tuple[str, str, dict[str, str], bytes]:
        request_line = self.rfile.readline(MAX_REQUEST_LINE_BYTES + 1)
        if (
            not request_line.endswith(b"\r\n")
            or len(request_line) > MAX_REQUEST_LINE_BYTES
        ):
            raise ProxyError("invalid request")
        try:
            method, path, version = request_line[:-2].decode("ascii").split(" ")
        except (UnicodeDecodeError, ValueError) as error:
            raise ProxyError("invalid request") from error
        if (
            method not in {"GET", "POST"}
            or version != "HTTP/1.1"
            or not path.startswith("/")
        ):
            raise ProxyError("invalid request")

        headers: dict[str, str] = {}
        total_header_bytes = 0
        while True:
            line = self.rfile.readline(MAX_HEADER_LINE_BYTES + 1)
            total_header_bytes += len(line)
            if (
                not line
                or len(line) > MAX_HEADER_LINE_BYTES
                or total_header_bytes > MAX_HEADER_BYTES
                or not line.endswith(b"\r\n")
            ):
                raise ProxyError("invalid request")
            if line == b"\r\n":
                break
            if line[:1] in {b" ", b"\t"} or b":" not in line:
                raise ProxyError("invalid request")
            name, value = line[:-2].split(b":", 1)
            if not HEADER_NAME.fullmatch(name):
                raise ProxyError("invalid request")
            normalized = name.decode("ascii").lower()
            if normalized in headers:
                raise ProxyError("invalid request")
            try:
                decoded = value.strip(b" \t").decode("ascii")
            except UnicodeDecodeError as error:
                raise ProxyError("invalid request") from error
            if any(
                ord(character) < 0x20 or ord(character) == 0x7F
                for character in decoded
            ):
                raise ProxyError("invalid request")
            headers[normalized] = decoded

        if "transfer-encoding" in headers:
            raise ProxyError("invalid request")
        length_text = headers.get("content-length")
        if length_text is None:
            content_length = 0
        elif not length_text.isascii() or not length_text.isdecimal():
            raise ProxyError("invalid request")
        else:
            content_length = int(length_text)
        if content_length > MAX_REQUEST_BODY_BYTES:
            raise ProxyError("invalid request")
        body = self.rfile.read(content_length)
        if len(body) != content_length:
            raise ProxyError("invalid request")
        return method, path, headers, body

    def _write_response(self, status: int, body: bytes) -> None:
        if len(body) > MAX_RESPONSE_BODY_BYTES:
            status, body = 500, ERROR_DOCUMENT
        reason = {
            200: "OK",
            400: "Bad Request",
            403: "Forbidden",
            404: "Not Found",
            500: "Internal Server Error",
        }[status]
        head = (
            f"HTTP/1.1 {status} {reason}\r\n"
            "Content-Type: application/json\r\n"
            "Cache-Control: no-store\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n\r\n"
        ).encode("ascii")
        self.wfile.write(head + body)


class TransitServer(socketserver.UnixStreamServer):
    allow_reuse_address = False

    def __init__(self, socket_path: Path, application: TransitApplication) -> None:
        _validate_socket_path(socket_path)
        self.application = application
        self._socket_path = socket_path
        self._socket_identity: tuple[int, int] | None = None
        previous_umask = os.umask(0o077)
        try:
            super().__init__(str(socket_path), TransitRequestHandler)
            socket_path.chmod(0o600)
            metadata = socket_path.stat()
            if not stat.S_ISSOCK(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600:
                raise ProxyError("invalid socket")
            self._socket_identity = (metadata.st_dev, metadata.st_ino)
        except Exception:
            try:
                socket_path.unlink()
            except OSError:
                pass
            raise
        finally:
            os.umask(previous_umask)

    def handle_error(self, request: socket.socket, client_address: object) -> None:
        # Deliberately suppress value-bearing exception diagnostics.
        del request, client_address

    def server_close(self) -> None:
        super().server_close()
        try:
            metadata = self._socket_path.lstat()
        except FileNotFoundError:
            return
        identity = (metadata.st_dev, metadata.st_ino)
        if stat.S_ISSOCK(metadata.st_mode) and identity == self._socket_identity:
            self._socket_path.unlink()


def build_server(private_jwk: Path, socket_path: Path, key_name: str) -> TransitServer:
    return TransitServer(socket_path, TransitApplication(private_jwk, key_name))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Expose one operator-owned ES256 JWK on one local Transit Unix socket."
    )
    parser.add_argument("--private-jwk", required=True, type=Path)
    parser.add_argument("--socket", required=True, type=Path)
    parser.add_argument("--key-name", required=True)
    arguments = parser.parse_args()
    try:
        server = build_server(arguments.private_jwk, arguments.socket, arguments.key_name)
    except (OSError, ProxyError, ValueError):
        print("local Transit proxy could not start", file=os.sys.stderr)
        return 1

    def stop(_signum: int, _frame: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        server.serve_forever(poll_interval=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
