"""Experimental local PAD scoring. A score is not a validated liveness decision.

Preprocessing adapted from yakhyo/face-anti-spoofing (Apache-2.0), commit
01a38903f4f2680bb59d32a994a6c7b5ae56f49b, onnx_inference.py.
Model architecture/weights originate from minivision-ai/Silent-Face-Anti-Spoofing.
Retain models/pad/LICENSE_*.txt and models/pad/NOTICE.md when distributing.
"""

import hashlib
import json
import threading
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np

PREPROCESSING = "yakhyo-clipped-crop-raw-bgr-nchw80-v1"


def prepare(image, box, scale):
    if (not isinstance(image, np.ndarray) or image.ndim != 3 or image.shape[2] != 3
            or image.dtype != np.uint8 or min(image.shape[:2]) < 80 or image.shape[0] * image.shape[1] > 4_000_000):
        raise ValueError("invalid_pad_image")
    coordinates = np.asarray(box, dtype=np.float64)
    if coordinates.shape != (4,) or not np.isfinite(coordinates).all() or not np.isfinite(scale) or scale <= 0:
        raise ValueError("invalid_pad_box")
    x, y, width, height = coordinates
    src_h, src_w = image.shape[:2]
    if min(width, height) < 1 or x < 0 or y < 0 or x + width > src_w or y + height > src_h:
        raise ValueError("invalid_pad_box")
    # Match the ONNX publisher's integer xywh crop, BGR order and raw 0..255 pixels.
    x, y, width, height = map(int, coordinates)
    effective_scale = min((src_h - 1) / height, (src_w - 1) / width, scale)
    half_w, half_h = width * effective_scale / 2, height * effective_scale / 2
    cx, cy = x + width / 2, y + height / 2
    requested = (cx - half_w, cy - half_h, cx + half_w, cy + half_h)
    x1, y1 = max(0, int(requested[0])), max(0, int(requested[1]))
    x2, y2 = min(src_w - 1, int(requested[2])), min(src_h - 1, int(requested[3]))
    crop = cv2.resize(image[y1:y2 + 1, x1:x2 + 1], (80, 80), interpolation=cv2.INTER_LINEAR)
    clipped = (effective_scale < scale or requested[0] < 0 or requested[1] < 0
               or requested[2] > src_w - 1 or requested[3] > src_h - 1)
    tensor = np.ascontiguousarray(crop.transpose(2, 0, 1)[None], dtype=np.float32)
    return tensor, bool(clipped)


def probabilities(logits):
    values = np.asarray(logits, dtype=np.float64)
    if values.shape != (1, 3) or not np.isfinite(values).all():
        raise ValueError("invalid_pad_output")
    exponents = np.exp(values - values.max(axis=1, keepdims=True))
    return (exponents / exponents.sum(axis=1, keepdims=True))[0]


class PadEngine:
    def __init__(self, directory: Path):
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        if (manifest.get("preprocessing") != PREPROCESSING
                or manifest.get("input") != {"shape": [1, 3, 80, 80], "dtype": "float32", "color": "BGR", "pixel_range": [0, 255]}
                or manifest.get("output", {}).get("live_class_index") != 1
                or {row.get("crop_scale") for row in manifest.get("models", [])} != {2.7, 4.0}
                or len(manifest.get("models", [])) != 2):
            raise ValueError("invalid_pad_contract")
        self.model_id = manifest["model_id"]
        self.networks = []
        self.lock = threading.Lock()
        for item in manifest["models"]:
            path = directory / item["filename"]
            if not path.resolve().is_relative_to(directory.resolve()):
                raise ValueError("invalid_pad_path")
            content = path.read_bytes()
            if len(content) != item["bytes"] or hashlib.sha256(content).hexdigest() != item["sha256"]:
                raise ValueError("invalid_pad_checksum")
            network = cv2.dnn.readNetFromONNX(np.frombuffer(content, dtype=np.uint8))
            network.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            network.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
            network.setInput(np.zeros((1, 3, 80, 80), dtype=np.float32))
            probabilities(network.forward())
            self.networks.append((item["filename"], float(item["crop_scale"]), network))

    def score(self, image, box):
        started, individual = perf_counter(), []
        with self.lock:
            for filename, scale, network in self.networks:
                tensor, clipped = prepare(image, box, scale)
                network.setInput(tensor)
                output = probabilities(network.forward())
                individual.append({"model": filename, "crop_scale": scale, "live_score": float(output[1]),
                                   "probabilities": output.tolist(), "context_clipped": clipped})
        return {"model_id": self.model_id, "preprocessing": PREPROCESSING,
                "ensemble_live_score": float(np.mean([item["live_score"] for item in individual])),
                "models": individual, "pad_ms": round((perf_counter() - started) * 1000, 2),
                "status": "experimental_not_validated", "decision": "not_evaluated",
                "validated_for_attendance": False}
