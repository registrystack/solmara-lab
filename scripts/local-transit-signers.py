#!/usr/bin/env python3
"""Start and stop the seven PID-tracked local Transit signer proxies."""

from __future__ import annotations

import argparse
import hashlib
import os
import signal
import socket
import stat
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = ("mint", "cra", "nia", "sro", "mosd-programme", "sipf", "nagdi")
STATE = ROOT / "runtime/local-transit-signers"
PROXY = ROOT / "scripts/local-transit-proxy.py"
ALIAS_ROOT = Path("/tmp") / f"solmara-transit-{hashlib.sha256(str(ROOT).encode()).hexdigest()[:12]}"


def key_name(provider: str) -> str:
    return "solmara-mint" if provider == "mint" else f"solmara-evidence-{provider}"


def paths(provider: str) -> tuple[Path, Path, Path]:
    base = ROOT / "config/evidence/local/cells" / provider
    return base / "secrets/signing.jwk", base / "transit/transit-proxy.sock", STATE / f"{provider}.pid"


def bind_path(provider: str, socket_path: Path) -> Path:
    ALIAS_ROOT.mkdir(mode=0o700, exist_ok=True)
    ALIAS_ROOT.chmod(0o700)
    alias = ALIAS_ROOT / provider
    expected = socket_path.parent.resolve()
    if alias.is_symlink():
        if alias.resolve() != expected:
            raise OSError("unexpected Transit alias")
    elif alias.exists():
        raise OSError("unexpected Transit alias")
    else:
        alias.symlink_to(expected, target_is_directory=True)
    return alias / socket_path.name


def owned_process(pid_file: Path) -> int | None:
    try:
        value = pid_file.read_text(encoding="ascii").strip()
        pid = int(value)
        os.kill(pid, 0)
    except (FileNotFoundError, ProcessLookupError, PermissionError, ValueError):
        return None
    command = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    ).stdout
    if str(PROXY) not in command:
        return None
    return pid


def wait_for_socket(path: Path, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if stat.S_ISSOCK(path.stat().st_mode):
                with socket.socket(socket.AF_UNIX) as client:
                    client.settimeout(0.25)
                    client.connect(str(path))
                return True
        except (FileNotFoundError, OSError):
            pass
        time.sleep(0.05)
    return False


def start() -> int:
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    STATE.chmod(0o700)
    started: list[str] = []
    for provider in PROVIDERS:
        private_jwk, socket_path, pid_file = paths(provider)
        existing = owned_process(pid_file)
        socket_bind_path = bind_path(provider, socket_path)
        if existing is not None and wait_for_socket(socket_bind_path, timeout=0.1):
            continue
        pid_file.unlink(missing_ok=True)
        if socket_path.exists() or socket_path.is_symlink():
            print(f"{provider}: refusing an unowned Transit socket", file=sys.stderr)
            stop(started)
            return 1
        socket_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        socket_path.parent.chmod(0o700)
        if not private_jwk.is_file():
            print(f"{provider}: signing key is missing; run just generate", file=sys.stderr)
            stop(started)
            return 1
        process = subprocess.Popen(
            [sys.executable, str(PROXY), "--private-jwk", str(private_jwk), "--socket", str(socket_bind_path), "--key-name", key_name(provider)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        pid_file.write_text(f"{process.pid}\n", encoding="ascii")
        pid_file.chmod(0o600)
        started.append(provider)
        if not wait_for_socket(socket_bind_path):
            print(f"{provider}: Transit proxy did not become ready", file=sys.stderr)
            stop(started)
            return 1
    return 0


def stop(providers: list[str] | tuple[str, ...] = PROVIDERS) -> int:
    for provider in reversed(providers):
        _, socket_path, pid_file = paths(provider)
        pid = owned_process(pid_file)
        if pid is None:
            pid_file.unlink(missing_ok=True)
            continue
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        pid_file.unlink(missing_ok=True)
        if socket_path.exists() and not stat.S_ISSOCK(socket_path.lstat().st_mode):
            print(f"{provider}: signer stopped but socket path was replaced", file=sys.stderr)
            return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("up", "down"))
    args = parser.parse_args()
    return start() if args.action == "up" else stop()


if __name__ == "__main__":
    raise SystemExit(main())
