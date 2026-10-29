"""CPU-only feature extraction. No attendance decisions until local calibration."""
import hashlib
import json
import threading
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np

from .config import get_settings
from .quality import QualityPolicy, assess_quality


class FaceInputError(ValueError):
    def __init__(self, code: str, details: dict | None = None):
        self.code = code
        self.details = details or {}
        super().__init__(code)


class FaceEngine:
    def __init__(self, models_dir: Path):
        # A bounded CPU pool avoids the machine's automatic 14-thread setting
        # contending with two kiosk requests and local SQL on the laptop.
        cv2.setNumThreads(get_settings().opencv_threads)
        manifest = json.loads((models_dir / "manifest.json").read_text(encoding="utf-8"))
        files = {}
        for model in manifest["models"]:
            file = models_dir / model["filename"]
            if not file.resolve().is_relative_to(models_dir.resolve()):
                raise ValueError("Invalid model path")
            with file.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != model["sha256"]:
                    raise ValueError("Invalid model checksum")
            files[model["kind"]] = np.frombuffer(file.read_bytes(), dtype=np.uint8)
        self.model_id = manifest["model_id"]
        self.dimensions = manifest["embedding_dimensions"]
        empty_config = np.empty(0, dtype=np.uint8)
        # Buffer constructors also work with Unicode project paths on Windows.
        self.detector = cv2.FaceDetectorYN.create("onnx", files["detector"], empty_config, (320, 320), 0.9, 0.3, 5000)
        self.recognizer = cv2.FaceRecognizerSF.create("onnx", files["recognizer"], empty_config)
        self.lock = threading.Lock()
        # Warm both networks before reporting model readiness.
        with self.lock:
            self.detector.detect(np.zeros((320, 320, 3), dtype=np.uint8))
            self.recognizer.feature(np.zeros((112, 112, 3), dtype=np.uint8))

    def detect(self, image: np.ndarray) -> np.ndarray:
        with self.lock:
            self.detector.setInputSize((image.shape[1], image.shape[0]))
            _, faces = self.detector.detect(image)
        return faces if faces is not None else np.empty((0, 15), dtype=np.float32)

    def extract(self, image: np.ndarray, face: np.ndarray) -> tuple[np.ndarray, dict]:
        started = perf_counter()
        with self.lock:
            aligned = self.recognizer.alignCrop(image, face)
            vector = self.recognizer.feature(aligned).reshape(-1).astype(np.float32)
        norm = float(np.linalg.norm(vector))
        if vector.size != self.dimensions or not np.isfinite(vector).all() or norm < 1e-8:
            raise FaceInputError("invalid_embedding")
        return vector / norm, {"embedding_ms": round((perf_counter()-started)*1000, 2), "dimensions": self.dimensions}

    def inspect(self, content: bytes, max_bytes: int = 2_000_000):
        image = self.decode(content, max_bytes)
        started = perf_counter()
        faces = self.detect(image)
        detection_ms = round((perf_counter()-started)*1000, 2)
        quality = assess_quality(image, faces)
        if not quality["accepted"]:
            raise FaceInputError(quality["reason"], quality)
        return image, faces[0], {"quality": quality, "detection_ms": detection_ms, "model_id": self.model_id}

    def analyze(self, content: bytes, max_bytes: int = 2_000_000) -> tuple[np.ndarray, dict]:
        image, face, metadata = self.inspect(content, max_bytes)
        vector, timing = self.extract(image, face)
        return vector, {**metadata, **timing}

    def analyze_reference(self, content: bytes, max_bytes: int = 2_000_000):
        """One original profile image; a lower size gate never applies to live frames."""
        image = self.decode(content, max_bytes)
        started = perf_counter()
        faces = self.detect(image)
        detection_ms = round((perf_counter()-started)*1000, 2)
        quality = assess_quality(image, faces, QualityPolicy(minimum_face_pixels=64))
        quality |= {"reference_only": True, "minimum_face_pixels": 64}
        if not quality["accepted"]:
            raise FaceInputError(quality["reason"], quality)
        vector, timing = self.extract(image, faces[0])
        return vector, {"quality": quality, "detection_ms": detection_ms,
                        "model_id": self.model_id, **timing}

    @staticmethod
    def decode(content: bytes, max_bytes: int = 2_000_000) -> np.ndarray:
        if not content or len(content) > max_bytes:
            raise FaceInputError("invalid_file_size")
        # Read image dimensions before allocating a decoded bitmap.
        from io import BytesIO

        from PIL import Image, UnidentifiedImageError

        try:
            with Image.open(BytesIO(content)) as image:
                if image.format not in {"JPEG", "PNG", "WEBP"}:
                    raise FaceInputError("unsupported_image")
                if image.width < 80 or image.height < 80 or image.width*image.height > 4_000_000:
                    raise FaceInputError("invalid_image_dimensions")
                image.verify()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
            raise FaceInputError("invalid_image") from error
        decoded = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR)
        if decoded is None:
            raise FaceInputError("invalid_image")
        return decoded

