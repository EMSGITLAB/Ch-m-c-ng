"""Private local key storage and authenticated encryption for recovery files."""

import os
import re
import subprocess
from pathlib import Path

from cryptography.fernet import Fernet

from .runtime_supervisor import FileLease

MAX_PLAINTEXT = 256 * 1024 * 1024


def protect_directory(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        path.chmod(0o700)
        return
    identity = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True,
                              text=True, encoding="utf-8", errors="replace", check=True)
    match = re.search(r"S-1-[0-9-]+", identity.stdout)
    if not match:
        raise RuntimeError("Cannot determine local key owner")
    result = subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r",
                             "*" + match.group() + ":(OI)(CI)F", "*S-1-5-18:(OI)(CI)F",
                             "*S-1-5-32-544:(OI)(CI)F"], capture_output=True)
    if result.returncode:
        raise RuntimeError("Cannot restrict local recovery-key directory")


def recovery_key(runtime, *, create=False):
    directory = Path(runtime) / "keys"
    path = directory / "backup.key"
    if not path.is_file() and not create:
        raise ValueError("Recovery key is required")
    if not directory.exists():
        protect_directory(directory)
    lease = FileLease(directory / "key.lock")
    try:
        if not path.exists():
            with path.open("xb") as output:
                output.write(Fernet.generate_key())
            if os.name != "nt":
                path.chmod(0o600)
        value = path.read_bytes()
        Fernet(value)  # Validate without printing key material.
        return value
    finally:
        lease.close()


def seal(content, key):
    if len(content) > MAX_PLAINTEXT:
        raise ValueError("Recovery payload exceeds the supported 256 MiB limit")
    return Fernet(key).encrypt(content)


def unseal(content, key):
    if len(content) > MAX_PLAINTEXT * 4 // 3 + 1024:
        raise ValueError("Encrypted recovery file is too large")
    result = Fernet(key).decrypt(content)
    if len(result) > MAX_PLAINTEXT:
        raise ValueError("Recovery payload exceeds the supported size")
    return result
