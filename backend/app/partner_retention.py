"""Filesystem-only biometric expiry; never alters names or attendance history."""

from pathlib import Path

from .partner_face_store import PartnerFaceStore


def expire_partner_faces(runtime, now=None):
    root = Path(runtime) / "partner-biometrics"
    if not root.is_dir():
        return {"ready": True, "expired_removed": 0, "invalid_records": 0}
    try:
        result = PartnerFaceStore(runtime).purge_expired(now)
        return {"ready": result["invalid_records"] == 0, **result}
    except (ValueError, OSError, RuntimeError):
        return {"ready": False, "error": "temporary_biometric_cleanup_failed"}
