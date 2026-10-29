import importlib.util
from pathlib import Path
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location(
    "kiosk_load_support_script", Path(__file__).resolve().parents[2] / "scripts/kiosk_load_support.py")
support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(support)


def test_progress_recovers_transient_windows_reader_and_keeps_old_checkpoint_if_locked(tmp_path, monkeypatch):
    path = tmp_path / "progress.json"
    path.write_text("old")
    original = Path.replace
    attempts = []

    def replace(self, target):
        attempts.append(1)
        if len(attempts) < 3:
            raise PermissionError("Windows read handle")
        return original(self, target)

    monkeypatch.setattr(Path, "replace", replace)
    monkeypatch.setattr(support.time, "sleep", lambda _: None)
    assert support.write_progress(path, {"pairs_completed": 2})
    assert len(attempts) == 3
    previous = path.read_bytes()

    def locked(self, target):
        raise PermissionError("locked")

    monkeypatch.setattr(Path, "replace", locked)
    assert support.write_progress(path, {"pairs_completed": 3}) is False
    assert path.read_bytes() == previous


def test_error_allowance_does_not_require_failed_uncommitted_session_to_be_used():
    rows = [SimpleNamespace(request_id="ok", state="used", receipt={"event_id": "event"}),
            SimpleNamespace(request_id="expired", state="pending", receipt=None)]
    result = support.reconcile_sessions(rows, [{"request_id": "ok", "event_id": "event"}],
                                        [{"request_id": "expired"}])
    assert all(result.values())
    rows[1].state, rows[1].receipt = "used", {"event_id": "unobserved"}
    assert not support.reconcile_sessions(rows, [{"request_id": "ok", "event_id": "event"}],
                                          [{"request_id": "expired"}])["failed_sessions_without_committed_receipt"]
    rows.append(SimpleNamespace(request_id="unknown", state="pending", receipt=None))
    assert not support.reconcile_sessions(rows, [{"request_id": "ok", "event_id": "event"}],
                                          [{"request_id": "expired"}])["all_sessions_accounted_for"]
