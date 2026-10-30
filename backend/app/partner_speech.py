"""Bounded offline speech drafts. Audio exists only in request/worker memory."""

import hashlib
import io
import json
import multiprocessing
import os
import threading
import time
import unicodedata
from functools import lru_cache
from pathlib import Path

MAX_AUDIO_BYTES = 2_000_000
MAX_AUDIO_SECONDS = 8.5
MODEL_REVISION = "536b0662742c02347bc0e980a01041f333bce120"
MODEL_FILES = {"config.json", "model.bin", "tokenizer.json", "vocabulary.txt"}


class SpeechError(ValueError):
    pass


def validate_model(directory):
    root = Path(directory)
    try:
        manifest_path = root / "manifest.json"
        if manifest_path.stat().st_size > 16_000:
            raise ValueError()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (manifest.get("revision") != MODEL_REVISION or manifest.get("schema") != 1
                or set(manifest.get("files", {})) != MODEL_FILES):
            raise ValueError()
        signature = []
        for name in sorted(MODEL_FILES):
            item = root / name
            stat = item.stat()
            record = manifest["files"][name]
            if not item.is_file() or stat.st_size != record["bytes"]:
                raise ValueError()
            signature.append((name, stat.st_mtime_ns, stat.st_size, record["sha256"]))
        _verify_files(str(root.resolve()), tuple(signature))
        return str(root.resolve())
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SpeechError("model_unavailable") from error


@lru_cache(maxsize=4)
def _verify_files(directory, signature):
    for name, _, _, expected in signature:
        with (Path(directory) / name).open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                raise SpeechError("model_unavailable")


def decode_bounded(content):
    import av
    import numpy as np

    if not isinstance(content, bytes) or not 32 <= len(content) <= MAX_AUDIO_BYTES:
        raise SpeechError("audio_invalid")
    arrays, samples = [], 0
    try:
        with av.open(io.BytesIO(content)) as container:
            streams = list(container.streams.audio)
            if len(streams) != 1:
                raise SpeechError("audio_invalid")
            stream = streams[0]
            if stream.codec_context.channels > 8 or stream.codec_context.sample_rate > 192_000:
                raise SpeechError("audio_invalid")
            resampler = av.AudioResampler(format="fltp", layout="mono", rate=16_000)

            def append(frame):
                nonlocal samples
                samples += frame.samples
                if samples > int(MAX_AUDIO_SECONDS*16_000):
                    raise SpeechError("audio_too_long")
                arrays.append(frame.to_ndarray().reshape(-1))

            for frame in container.decode(stream):
                for output in resampler.resample(frame):
                    append(output)
            for output in resampler.resample(None):
                append(output)
    except SpeechError:
        raise
    except (ValueError, OSError, av.error.FFmpegError) as error:
        raise SpeechError("audio_invalid") from error
    if samples < 4000:
        raise SpeechError("audio_too_short")
    waveform = np.concatenate(arrays).astype(np.float32)
    if not np.isfinite(waveform).all():
        raise SpeechError("audio_invalid")
    if float(np.sqrt(np.mean(waveform**2))) < .001 or float(np.max(np.abs(waveform))) < .01:
        raise SpeechError("audio_silent")
    return waveform


def clean_draft(text):
    value = " ".join(unicodedata.normalize("NFC", text).strip(" .,!?\n\r").split())
    if (not value or len(value) > 160 or len(value.split()) > 12
            or any(not (char.isalpha() or char in " '-.") for char in value)):
        raise SpeechError("speech_unclear")
    return value


def _offline_worker(connection, directory, threads):
    # Defense in depth: even a library fallback cannot reach a cloud endpoint.
    os.environ.update(HF_HUB_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1", DO_NOT_TRACK="1",
                      TRANSFORMERS_OFFLINE="1", OMP_NUM_THREADS=str(threads))
    import socket

    def forbidden(*args, **kwargs):
        raise OSError("speech_worker_network_disabled")

    socket.socket.connect = forbidden
    socket.socket.connect_ex = forbidden
    socket.create_connection = forbidden
    try:
        import onnxruntime
        from faster_whisper import WhisperModel
        from faster_whisper.vad import get_vad_model
        onnxruntime.disable_telemetry_events()
        model = WhisperModel(validate_model(directory), device="cpu", compute_type="int8",
                             cpu_threads=threads, num_workers=1, local_files_only=True)
        get_vad_model()
        connection.send({"ready": True})
        while True:
            content = connection.recv_bytes(MAX_AUDIO_BYTES)
            try:
                waveform = decode_bounded(content)
                segments, _ = model.transcribe(waveform, language="vi", task="transcribe", beam_size=3,
                    condition_on_previous_text=False, vad_filter=True,
                    vad_parameters={"min_silence_duration_ms": 150}, without_timestamps=True)
                draft = clean_draft(" ".join(segment.text for segment in segments))
                connection.send({"draft": draft})
            except SpeechError as error:
                connection.send({"error": str(error)})
            except Exception:
                connection.send({"error": "speech_unavailable"})
    except Exception:
        try:
            connection.send({"error": "speech_unavailable"})
        except (OSError, EOFError):
            pass
    finally:
        connection.close()


class PartnerSpeech:
    def __init__(self, directory, *, threads=2, timeout=30):
        self.directory = str(directory)
        self.threads, self.timeout = threads, timeout
        self.lock = threading.Lock()
        self.process = self.connection = None
        self.signature = None
        self.ready = False
        self.warming = False

    def _stop(self):
        self.ready = False
        if self.connection:
            self.connection.close()
            self.connection = None
        if self.process:
            if self.process.is_alive():
                self.process.terminate()
            self.process.join(timeout=3)
            if self.process.is_alive():
                self.process.kill()
                self.process.join(timeout=2)
            self.process.close()
            self.process = None

    def _receive(self, deadline):
        while not self.connection.poll(.1):
            if time.monotonic() >= deadline:
                self._stop()
                raise SpeechError("speech_timeout")
            if not self.process.is_alive():
                self._stop()
                raise SpeechError("speech_unavailable")
        return self.connection.recv()

    def _ensure_worker(self, deadline):
        directory = validate_model(self.directory)
        signature = tuple((name, (Path(directory)/name).stat().st_mtime_ns) for name in sorted(MODEL_FILES))
        if self.process and (not self.process.is_alive() or self.signature != signature):
            self._stop()
        if self.process is None:
            ctx = multiprocessing.get_context("spawn")
            self.connection, child = ctx.Pipe()
            self.process = ctx.Process(target=_offline_worker, args=(child, directory, self.threads), daemon=True)
            self.process.start()
            child.close()
            self.signature = signature
        if not self.ready:
            response = self._receive(deadline)
            if response != {"ready": True}:
                self._stop()
                raise SpeechError("speech_unavailable")
            self.ready = True

    def warmup(self):
        # No audio is collected, decoded or stored by preload. Requests may
        # wait for this single startup load instead of reporting speech_busy.
        with self.lock:
            self.warming = True
            try:
                self._ensure_worker(time.monotonic()+self.timeout)
            except (OSError, EOFError, BrokenPipeError) as error:
                self._stop()
                raise SpeechError("speech_unavailable") from error
            finally:
                self.warming = False

    def transcribe(self, content):
        if not isinstance(content, bytes) or not 32 <= len(content) <= MAX_AUDIO_BYTES:
            raise SpeechError("audio_invalid")
        deadline = time.monotonic()+self.timeout
        if not self.lock.acquire(blocking=False):
            if not self.warming or not self.lock.acquire(timeout=self.timeout):
                raise SpeechError("speech_busy")
        try:
            self._ensure_worker(deadline)
            self.connection.send_bytes(content)
            response = self._receive(deadline)
            if response.get("error"):
                raise SpeechError(response["error"])
            return clean_draft(response["draft"])
        except (OSError, EOFError, BrokenPipeError) as error:
            self._stop()
            raise SpeechError("speech_unavailable") from error
        finally:
            self.lock.release()

    def close(self):
        with self.lock:
            self._stop()
