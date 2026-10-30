"""Use the supplied short audio to test offline execution, not person/name accuracy."""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def main():
    from app.partner_speech import PartnerSpeech, decode_bounded
    path = ROOT / "frontend/public/audio/hop-le-user-fast-135.wav"
    content = path.read_bytes()
    waveform = decode_bounded(content)
    engine = PartnerSpeech(ROOT / "models/speech/faster-whisper-small", timeout=40)
    started = time.monotonic()
    try:
        draft = engine.transcribe(content)
        result = {"schema": 1, "offline_worker": True, "network_disabled_in_worker": True,
            "audio_duration_seconds": round(len(waveform)/16_000, 3),
            "draft_nonempty": bool(draft), "draft_characters": len(draft),
            "elapsed_seconds": round(time.monotonic()-started, 3),
            "audio_or_transcript_stored": False, "name_accuracy_validation": False}
    finally:
        engine.close()
    (ROOT / "evidence/m5/partner-speech-pipeline.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
