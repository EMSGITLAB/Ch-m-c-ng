from datetime import UTC, datetime, timedelta
from uuid import uuid4

import numpy as np
import pytest
from app.native_backup import source_files
from app.partner_face_store import PartnerFaceStore


def specimen():
    return {"reference": str(uuid4()), "batch_id": str(uuid4()), "subject_id": str(uuid4()),
            "model_id": "model-test", "vectors": [np.ones(128, dtype=np.float32)],
            "expires_at": datetime.now(UTC)+timedelta(hours=1)}


def test_vectors_encrypted_survive_restart_and_fail_scope_or_expiry(tmp_path):
    store = PartnerFaceStore(tmp_path)
    data = specimen()
    reference = data.pop("reference")
    store.write(reference, **data)
    raw = store.path(reference).read_bytes()
    assert b'vectors' not in raw and data["model_id"].encode() not in raw
    restarted = PartnerFaceStore(tmp_path)
    scope = {key: data[key] for key in ("batch_id", "subject_id", "model_id")}
    result = restarted.read(reference, **scope)
    assert len(result) == 1 and np.isclose(np.linalg.norm(result[0]), 1)
    for key in scope:
        with pytest.raises(ValueError, match="scope_mismatch"):
            restarted.read(reference, **(scope | {key: str(uuid4())}))
    with pytest.raises(ValueError, match="expired"):
        restarted.read(reference, **scope, now=data["expires_at"])


def test_reference_cannot_be_overwritten_and_corruption_fails_closed(tmp_path):
    store = PartnerFaceStore(tmp_path)
    data = specimen()
    reference = data.pop("reference")
    store.write(reference, **data)
    store.write(reference, **data)
    with pytest.raises(ValueError, match="immutable"):
        store.write(reference, **(data | {"subject_id": str(uuid4())}))
    path = store.path(reference)
    path.write_bytes(b'not-an-authentic-record')
    scope = {key: data[key] for key in ("batch_id", "subject_id", "model_id")}
    with pytest.raises(ValueError, match="authentication_failed"):
        store.read(reference, **scope)
    assert store.purge_expired()["invalid_records"] == 1


def test_purge_at_exact_expiry_leaves_no_face_record(tmp_path):
    store = PartnerFaceStore(tmp_path)
    data = specimen()
    reference = data.pop("reference")
    store.write(reference, **data)
    assert store.purge_expired(data["expires_at"]-timedelta(seconds=1))["expired_removed"] == 0
    assert store.purge_expired(data["expires_at"])["expired_removed"] == 1
    assert not store.path(reference).exists()
    assert (store.root / "ephemeral.key").exists()


def test_missing_key_never_silently_rekeys_existing_records(tmp_path):
    store = PartnerFaceStore(tmp_path)
    data = specimen()
    reference = data.pop("reference")
    store.write(reference, **data)
    (store.root / "ephemeral.key").unlink()
    with pytest.raises(ValueError, match="key_missing"):
        PartnerFaceStore(tmp_path)


def test_ids_vectors_are_bounded(tmp_path):
    store = PartnerFaceStore(tmp_path)
    with pytest.raises(ValueError):
        store.path("../elsewhere")
    data = specimen()
    reference = data.pop("reference")
    with pytest.raises(ValueError):
        store.write(reference, **(data | {"vectors": [np.full(128, np.nan)]}))
    with pytest.raises(ValueError):
        store.write(reference, **(data | {"expires_at": datetime.now(UTC)-timedelta(seconds=1)}))
    assert store.root.parent == tmp_path.resolve()


def test_backup_allowlist_excludes_actual_private_face_files_and_key(tmp_path):
    project = tmp_path / "project"
    public = project / "frontend/public"
    public.mkdir(parents=True)
    (public / "logo.svg").write_text("<svg/>", encoding="utf-8")
    (project / ".env").write_text("# Isolated test configuration, no secret", encoding="utf-8")
    speech = project / "models/speech/faster-whisper-small"
    speech.mkdir(parents=True)
    (speech/"model.bin").write_bytes(b"Reinstallable public weights are outside data backups")
    store = PartnerFaceStore(project / ".runtime")
    data = specimen()
    reference = data.pop("reference")
    store.write(reference, **data)
    selected = source_files(project)
    assert selected["frontend/public/logo.svg"].is_file()
    assert "server.env" in selected
    assert store.path(reference) not in selected.values()
    assert store.root / "ephemeral.key" not in selected.values()
    assert all(not path.resolve().is_relative_to(store.root) for path in selected.values())
    assert speech/"model.bin" not in selected.values()


def test_periodic_expiry_after_restart_never_creates_a_missing_store_or_recovery_key(tmp_path):
    from app.partner_retention import expire_partner_faces
    assert expire_partner_faces(tmp_path)["ready"]
    assert not (tmp_path/"partner-biometrics").exists()
    store = PartnerFaceStore(tmp_path)
    data = specimen()
    reference = data.pop("reference")
    store.write(reference, **data)
    assert expire_partner_faces(tmp_path)["expired_removed"] == 0
    result = expire_partner_faces(tmp_path, data["expires_at"]+timedelta(seconds=1))
    assert result == {"ready": True, "expired_removed": 1, "invalid_records": 0}
    assert not store.path(reference).exists()
    assert (store.root/"ephemeral.key").is_file()


def test_retention_surfaces_corruption_without_silently_reinitializing(tmp_path):
    from app.partner_retention import expire_partner_faces
    store = PartnerFaceStore(tmp_path)
    data = specimen()
    reference = data.pop("reference")
    store.write(reference, **data)
    store.path(reference).write_bytes(b"damaged-encrypted-record")
    assert expire_partner_faces(tmp_path)["ready"] is False
    (store.root/"ephemeral.key").unlink()
    assert expire_partner_faces(tmp_path)["ready"] is False
    assert not (store.root/"ephemeral.key").exists()
