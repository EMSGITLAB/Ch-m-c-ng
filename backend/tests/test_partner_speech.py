"""Offline speech transport/draft/lifetime checks, not name accuracy validation."""

import io
import json
import wave
from datetime import timedelta
from types import SimpleNamespace

import numpy as np
import pytest
from app.main import app
from app.models import PartnerWorker
from app.partner_speech import PartnerSpeech, SpeechError, clean_draft, decode_bounded, validate_model
from test_partner_admin import partner_setup as partner_setup
from test_partner_attendance import ROOT
from test_partner_attendance import partner_kiosk as partner_kiosk


def wav_audio(seconds, *, silent=False):
    sound = np.zeros(int(seconds*16_000), dtype=np.int16) if silent else (
        np.sin(np.arange(int(seconds*16_000))*(2*np.pi*200/16_000))*2000).astype(np.int16)
    output = io.BytesIO()
    with wave.open(output, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16_000)
        stream.writeframes(sound.tobytes())
    return output.getvalue()


def test_audio_decode_is_bounded_and_does_not_accept_silence():
    assert decode_bounded(wav_audio(.4)).shape == (6400,)
    for content, expected in [(wav_audio(.5, silent=True), "audio_silent"),
        (wav_audio(.05), "audio_too_short"), (wav_audio(9), "audio_too_long"),
        (b"invalid"*20, "audio_invalid"), (b"a"*2_000_001, "audio_invalid")]:
        with pytest.raises(SpeechError, match=expected):
            decode_bounded(content)


def test_local_model_requires_manifest_and_complete_matching_files(tmp_path):
    with pytest.raises(SpeechError, match="model_unavailable"):
        validate_model(tmp_path)
    (tmp_path/"manifest.json").write_text(json.dumps({"schema": 1, "files": {}}))
    with pytest.raises(SpeechError, match="model_unavailable"):
        validate_model(tmp_path)
    assert clean_draft("  Nguyễn   Văn An. ") == "Nguyễn Văn An"
    with pytest.raises(SpeechError):
        clean_draft("000083")


def test_speech_busy_never_starts_a_second_job():
    engine = PartnerSpeech("nonexistent")
    assert engine.lock.acquire(blocking=False)
    try:
        with pytest.raises(SpeechError, match="speech_busy"):
            engine.transcribe(b"a"*64)
        assert engine.process is None
    finally:
        engine.lock.release()


def test_preload_receives_model_ready_without_audio_and_reuses_the_worker(monkeypatch, tmp_path):
    import app.partner_speech as speech
    monkeypatch.setattr(speech, "validate_model", lambda _: str(tmp_path))
    for name in speech.MODEL_FILES:
        (tmp_path/name).write_bytes(b"fixture")
    engine = PartnerSpeech(tmp_path)
    engine.process = SimpleNamespace(is_alive=lambda: True)
    engine.signature = tuple((name, (tmp_path/name).stat().st_mtime_ns) for name in sorted(speech.MODEL_FILES))
    responses = iter([{"ready": True}, {"draft": "Nguyễn Văn Thử"}])
    sent = []
    engine.connection = SimpleNamespace(poll=lambda _: True, recv=lambda: next(responses), send_bytes=sent.append)
    engine.warmup()
    assert engine.ready and not engine.warming and sent == []
    assert engine.transcribe(b"a"*64) == "Nguyễn Văn Thử"
    assert sent == [b"a"*64]


def test_first_request_waits_for_startup_preload_instead_of_reporting_busy(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    engine = PartnerSpeech("unused-in-isolated-test", timeout=3)
    started, release = Event(), Event()
    def ensure(deadline):
        if engine.warming:
            started.set()
            assert release.wait(2)
    monkeypatch.setattr(engine, "_ensure_worker", ensure)
    monkeypatch.setattr(engine, "_receive", lambda _: {"draft": "Nguyễn Văn Thử"})
    engine.connection = SimpleNamespace(send_bytes=lambda _: None)
    with ThreadPoolExecutor(max_workers=2) as pool:
        warm = pool.submit(engine.warmup)
        assert started.wait(1)
        request = pool.submit(engine.transcribe, b"a"*64)
        release.set()
        warm.result()
        assert request.result() == "Nguyễn Văn Thử"
    assert not engine.lock.locked()


def test_speech_timeout_terminates_worker_without_storing_audio(monkeypatch, tmp_path):
    import app.partner_speech as speech
    monkeypatch.setattr(speech, "validate_model", lambda _: str(tmp_path))
    for name in speech.MODEL_FILES:
        (tmp_path/name).write_bytes(b"fixture")
    terminated = []
    class Process:
        alive = True
        def is_alive(self): return self.alive
        def terminate(self):
            self.alive = False
            terminated.append(True)
        def join(self, timeout): pass
        def close(self): pass
    engine = PartnerSpeech(tmp_path, timeout=0)
    engine.process = Process()
    engine.signature = tuple((name, (tmp_path/name).stat().st_mtime_ns) for name in sorted(speech.MODEL_FILES))
    engine.connection = SimpleNamespace(send_bytes=lambda _: None, poll=lambda _: False, close=lambda: None)
    with pytest.raises(SpeechError, match="speech_timeout"):
        engine.transcribe(b"a"*64)
    assert terminated == [True] and engine.process is None and engine.connection is None
    assert not engine.lock.locked()


def test_voice_returns_draft_only_and_requires_intent_owner_and_current_revision(partner_kiosk, monkeypatch):
    k = partner_kiosk
    _, state = k["capture"]()
    worker = state["worker"]
    seen = []
    def transcribe(content):
        seen.append(content)
        return "Nguyễn Văn Thử"
    monkeypatch.setattr(app.state.partner_speech, "transcribe", transcribe)
    url = ROOT+f"/workers/{worker['id']}/speech?expected_revision=0"
    headers = {"Content-Type": "audio/webm", "X-Kiosk-Intent": "transcribe-partner-name"}
    assert k["browser"].post(url, content=b"audio", headers={"Content-Type": "audio/webm"}).status_code == 403
    response = k["browser"].post(url, content=b"audio", headers=headers)
    assert response.status_code == 200 and response.json()["requires_confirmation"]
    assert not response.json()["name_saved"] and not response.json()["audio_stored"]
    with k["factory"]() as db:
        stored = db.get(PartnerWorker, worker["id"])
        assert stored.declared_name is None and stored.name_revision == 0 and stored.admitted_at is None
    assert k["browser"].post(url, content=b"a"*2_000_001, headers=headers).status_code == 413
    k["actor"](1)
    assert k["browser"].post(url, content=b"audio", headers=headers).status_code == 409
    assert len(seen) == 1


def test_late_voice_draft_after_manual_confirmation_or_expiry_is_discarded(partner_kiosk, monkeypatch):
    k = partner_kiosk
    proof, state = k["capture"]()
    worker = state["worker"]
    headers = {"Content-Type": "audio/webm", "X-Kiosk-Intent": "transcribe-partner-name"}
    url = ROOT+f"/workers/{worker['id']}/speech?expected_revision=0"
    def change_name(_):
        with k["factory"]() as db:
            row = db.get(PartnerWorker, worker["id"])
            row.declared_name, row.name_revision = "Tên nhập tay", 1
            row.name_confirmed_at = k["clock"][0]
            db.commit()
        return "Tên giọng nói cũ"
    monkeypatch.setattr(app.state.partner_speech, "transcribe", change_name)
    assert k["browser"].post(url, content=b"audio", headers=headers).status_code == 409
    with k["factory"]() as db:
        assert db.get(PartnerWorker, worker["id"]).declared_name == "Tên nhập tay"
    def expire(_):
        from app.partner_attendance import PENDING_TTL
        k["clock"][0] += timedelta(seconds=PENDING_TTL+1)
        return "Tên quá hạn"
    monkeypatch.setattr(app.state.partner_speech, "transcribe", expire)
    assert k["browser"].post(url.replace("revision=0", "revision=1"), content=b"audio", headers=headers).status_code == 410
