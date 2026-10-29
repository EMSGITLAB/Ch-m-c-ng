"""Save a password-protected recovery key, never a plaintext key beside backups."""

import hashlib
import hmac
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .private_storage import recovery_key
from .recovery_key import MAX_FILE_BYTES, unwrap_key, wrap_key


def preserved_key(runtime):
    try:
        marker = json.loads((Path(runtime) / "backups/recovery-key-export.json").read_text(encoding="utf-8"))
        path = Path(marker["wrapped_file"])
        if path.suffix != ".cckey" or path.stat().st_size > MAX_FILE_BYTES:
            return False
        return (hmac.compare_digest(marker["key_sha256"], hashlib.sha256(recovery_key(runtime)).hexdigest())
                and hmac.compare_digest(marker["wrapped_sha256"], hashlib.sha256(path.read_bytes()).hexdigest()))
    except (OSError, ValueError, TypeError, KeyError, RuntimeError):
        return False


def save_key(runtime, destination, password, *, publish=True):
    runtime, destination = Path(runtime), Path(destination)
    # Do not create a missing external-drive directory and silently change its meaning.
    if not destination.is_dir():
        raise ValueError("Thư mục backup chưa sẵn sàng. Kiểm tra ổ USB trước.")
    key = recovery_key(runtime)
    content = wrap_key(key, password)
    if not hmac.compare_digest(unwrap_key(content, password), key):
        raise ValueError("Chưa kiểm chứng được khóa bảo quản.")
    path = destination / ("chamcong_key_" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ_") + uuid4().hex[:8] + ".cckey")
    with path.open("xb") as output:
        output.write(content)
        output.flush()
        os.fsync(output.fileno())
    # Verify the bytes read from the external device before recording completion.
    if path.read_bytes() != content:
        raise OSError("Recovery-key file read-back mismatch")
    marker = {"completed_at": datetime.now(UTC).isoformat(), "wrapped_file": str(path.resolve()),
              "key_sha256": hashlib.sha256(key).hexdigest(),
              "wrapped_sha256": hashlib.sha256(content).hexdigest()}
    result = {"saved": True, "filename": path.name, "plaintext_key_exported": False}
    if publish:
        record_key_export(runtime, marker)
        return result
    return result | {"_marker": marker}


def record_key_export(runtime, marker):
    directory = Path(runtime) / "backups"
    directory.mkdir(parents=True, exist_ok=True)
    temporary = directory / "recovery-key-export.tmp"
    temporary.write_text(json.dumps(marker), encoding="utf-8")
    temporary.replace(directory / "recovery-key-export.json")
