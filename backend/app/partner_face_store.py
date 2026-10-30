"""Encrypted, expiring partner vectors outside SQL and backup allowlists.

This store deliberately has its own non-recovery key. Missing/corrupt data
fails closed; a SQL backup cannot recreate expired partner biometrics.
"""

import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import numpy as np
from cryptography.fernet import Fernet, InvalidToken

from .devices import aware
from .matching import normalized
from .private_storage import protect_directory
from .runtime_supervisor import FileLease

MAX_RECORD_BYTES = 128_000


class PartnerFaceStore:
    def __init__(self, runtime, dimensions=128):
        self.root = Path(runtime).resolve() / "partner-biometrics"
        if self.root.is_symlink() or self.root.is_junction():
            raise ValueError("partner_store_link_forbidden")
        self.dimensions = dimensions
        self.lock = threading.RLock()
        if not self.root.exists():
            protect_directory(self.root)
        key_path = self.root / "ephemeral.key"
        lease = FileLease(self.root / "key.lock")
        try:
            if not key_path.exists():
                if any(self.root.glob("*.face")):
                    raise ValueError("partner_store_key_missing")
                with key_path.open("xb") as stream:
                    stream.write(Fernet.generate_key())
                if os.name != "nt":
                    key_path.chmod(0o600)
            self.cipher = Fernet(key_path.read_bytes())
        finally:
            lease.close()

    def path(self, reference):
        reference = str(UUID(str(reference)))
        target = self.root / (reference+".face")
        if target.is_symlink() or not target.resolve().is_relative_to(self.root.resolve()):
            raise ValueError("partner_store_link_forbidden")
        return target

    def write(self, reference, *, batch_id, subject_id, model_id, vectors, expires_at, now=None):
        now = aware(now or datetime.now(UTC))
        expiry = aware(expires_at)
        if expiry <= now or not 1 <= len(vectors) <= 12 or not model_id or len(model_id) > 100:
            raise ValueError("partner_store_invalid_record")
        values = [normalized(value, self.dimensions).tolist() for value in vectors]
        record = {"schema": 1, "reference": str(UUID(str(reference))), "batch_id": str(UUID(str(batch_id))),
                  "subject_id": str(UUID(str(subject_id))), "model_id": model_id,
                  "dimensions": self.dimensions, "expires_at": expiry.isoformat(), "vectors": values}
        encoded = json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        if len(encoded) > MAX_RECORD_BYTES:
            raise ValueError("partner_store_record_too_large")
        path = self.path(reference)
        with self.lock:
            lease = FileLease(self.root / "write.lock")
            temporary = self.root / (uuid4().hex+".tmp")
            try:
                if path.exists():
                    old = self._decode(path)
                    if old != record:
                        raise ValueError("partner_store_record_immutable")
                    return
                with temporary.open("xb") as stream:
                    stream.write(self.cipher.encrypt(encoded))
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
                lease.close()

    def _decode(self, path):
        if not path.is_file() or path.stat().st_size > MAX_RECORD_BYTES*2:
            raise ValueError("partner_store_missing_or_oversize")
        try:
            record = json.loads(self.cipher.decrypt(path.read_bytes()))
        except (InvalidToken, ValueError, TypeError) as error:
            raise ValueError("partner_store_authentication_failed") from error
        if not isinstance(record, dict) or record.get("schema") != 1:
            raise ValueError("partner_store_invalid_record")
        return record

    def read(self, reference, *, batch_id, subject_id, model_id, now=None):
        now = aware(now or datetime.now(UTC))
        record = self._decode(self.path(reference))
        expected = (str(UUID(str(reference))), str(UUID(str(batch_id))), str(UUID(str(subject_id))), model_id, self.dimensions)
        actual = tuple(record.get(key) for key in ("reference", "batch_id", "subject_id", "model_id", "dimensions"))
        if actual != expected:
            raise ValueError("partner_store_scope_mismatch")
        try:
            expired = datetime.fromisoformat(record["expires_at"]) <= now
        except (ValueError, TypeError, KeyError) as error:
            raise ValueError("partner_store_invalid_expiry") from error
        if expired:
            raise ValueError("partner_store_expired")
        vectors = record.get("vectors")
        if not isinstance(vectors, list) or not 1 <= len(vectors) <= 12:
            raise ValueError("partner_store_invalid_vectors")
        return [normalized(np.asarray(value, dtype=np.float32), self.dimensions) for value in vectors]

    def remove(self, reference):
        self.path(reference).unlink(missing_ok=True)

    def purge_expired(self, now=None):
        now = aware(now or datetime.now(UTC))
        removed = invalid = 0
        for path in self.root.glob("*.face"):
            try:
                checked = self.path(path.stem)
                record = self._decode(checked)
                if datetime.fromisoformat(record["expires_at"]) <= now:
                    checked.unlink(missing_ok=True)
                    removed += 1
            except (ValueError, TypeError, KeyError):
                # Do not destroy evidence of corruption as though it were a
                # validated expiry. Such records can never be used to match.
                invalid += 1
        return {"expired_removed": removed, "invalid_records": invalid}
