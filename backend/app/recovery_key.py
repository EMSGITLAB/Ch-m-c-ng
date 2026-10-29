"""Portable password-protected recovery key; passwords are never persisted."""

import base64
import json
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

FORMAT = "chamcong-recovery-key-v1"
KDF = "scrypt-n131072-r8-p1"
MAX_FILE_BYTES = 8192


def password_key(password, salt):
    if not isinstance(password, str) or not 12 <= len(password) <= 512:
        raise ValueError("Mật khẩu khôi phục cần từ 12 đến 512 ký tự.")
    if len(salt) != 16:
        raise ValueError("Invalid recovery-key salt")
    raw = Scrypt(salt=salt, length=32, n=2**17, r=8, p=1).derive(password.encode("utf-8"))
    return base64.urlsafe_b64encode(raw)


def wrap_key(key, password):
    Fernet(key)
    salt = os.urandom(16)
    token = Fernet(password_key(password, salt)).encrypt(key)
    return json.dumps({"format": FORMAT, "kdf": KDF, "salt": base64.urlsafe_b64encode(salt).decode("ascii"),
                       "token": token.decode("ascii")}, sort_keys=True).encode("utf-8")


def unwrap_key(content, password):
    if len(content) > MAX_FILE_BYTES:
        raise ValueError("Recovery-key file is too large")
    try:
        value = json.loads(content)
        if (not isinstance(value, dict) or set(value) != {"format", "kdf", "salt", "token"}
                or value["format"] != FORMAT or value["kdf"] != KDF):
            raise ValueError("Unsupported recovery-key format")
        salt = base64.b64decode(value["salt"], altchars=b"-_", validate=True)
        key = Fernet(password_key(password, salt)).decrypt(value["token"].encode("ascii"))
        Fernet(key)
        return key
    except InvalidToken as error:
        raise ValueError("Mật khẩu không đúng hoặc tệp khóa đã thay đổi.") from error
    except (TypeError, UnicodeError, KeyError) as error:
        raise ValueError("Tệp khóa khôi phục không hợp lệ.") from error
