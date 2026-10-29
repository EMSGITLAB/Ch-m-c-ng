"""Setup-only download of pinned experimental PAD models; inference stays offline."""

import hashlib
import json
import urllib.request
from pathlib import Path

DIRECTORY = Path(__file__).resolve().parents[1] / "models/pad"


def main():
    manifest = json.loads((DIRECTORY / "manifest.json").read_text(encoding="utf-8"))
    for item in manifest["models"]:
        path = DIRECTORY / item["filename"]
        if not path.resolve().is_relative_to(DIRECTORY.resolve()):
            raise ValueError("Invalid model destination")
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]:
            print(f"Already verified: {item['filename']}")
            continue
        request = urllib.request.Request(item["source"], headers={"User-Agent": "ChamCongLocalSetup/0.1"})
        with urllib.request.urlopen(request, timeout=90) as response:
            data = response.read(item["bytes"] + 1)
        if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError("PAD model checksum mismatch")
        temporary = path.with_suffix(".part")
        temporary.write_bytes(data)
        temporary.replace(path)
        print(f"Verified: {item['filename']}")
    for item in manifest["licenses"]:
        path = DIRECTORY / item["filename"]
        if not path.resolve().is_relative_to(DIRECTORY.resolve()):
            raise ValueError("Invalid license destination")
        if not path.exists():
            with urllib.request.urlopen(item["source"], timeout=30) as response:
                data = response.read(50000)
            if b"Apache License" not in data:
                raise ValueError("Unexpected license content")
            path.write_bytes(data)
    print("PAD models available for testing only; no attendance policy enabled.")


if __name__ == "__main__":
    main()
