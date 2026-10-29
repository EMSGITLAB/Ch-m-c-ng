import json

import pytest
from app.recovery_key import unwrap_key, wrap_key
from cryptography.fernet import Fernet

PASSWORD = "Test-only recovery passphrase 2026"


def test_portable_key_can_decrypt_backup_without_original_key_file():
    key = Fernet.generate_key()
    ciphertext = Fernet(key).encrypt(b"synthetic recovery payload")
    wrapped = wrap_key(key, PASSWORD)
    assert key not in wrapped and PASSWORD.encode() not in wrapped
    assert Fernet(unwrap_key(wrapped, PASSWORD)).decrypt(ciphertext) == b"synthetic recovery payload"


def test_wrong_password_tampered_token_and_changed_kdf_are_rejected():
    wrapped = wrap_key(Fernet.generate_key(), PASSWORD)
    with pytest.raises(ValueError, match="Mật khẩu"):
        unwrap_key(wrapped, PASSWORD + "wrong")
    data = json.loads(wrapped)
    data["token"] = data["token"][:-3] + "aaa"
    with pytest.raises(ValueError):
        unwrap_key(json.dumps(data).encode(), PASSWORD)
    data["kdf"] = "attacker-controlled-memory-cost"
    with pytest.raises(ValueError, match="Unsupported"):
        unwrap_key(json.dumps(data).encode(), PASSWORD)


def test_password_and_file_limits_fail_before_expensive_work():
    key = Fernet.generate_key()
    for password in ("short", "x" * 513):
        with pytest.raises(ValueError):
            wrap_key(key, password)
    with pytest.raises(ValueError, match="too large"):
        unwrap_key(b"x" * 8193, PASSWORD)
