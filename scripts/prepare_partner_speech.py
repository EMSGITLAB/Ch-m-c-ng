"""Explicit setup step only; the running application never downloads speech models."""

import hashlib
import json
import os
import sys
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "Systran/faster-whisper-small"
REVISION = "536b0662742c02347bc0e980a01041f333bce120"
FILES = ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt")


def main():
    target = ROOT / "models" / "speech" / "faster-whisper-small"
    target.mkdir(parents=True, exist_ok=True)
    info = HfApi(token=False).model_info(REPOSITORY, revision=REVISION, files_metadata=True)
    if info.sha != REVISION:
        raise ValueError("Unexpected speech model revision")
    metadata = {item.rfilename: item for item in info.siblings}
    records = {}
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    for name in FILES:
        path = Path(hf_hub_download(REPOSITORY, name, revision=REVISION, token=False, local_dir=target))
        digest = hashlib.file_digest(path.open("rb"), "sha256").hexdigest()
        entry = metadata[name]
        if path.stat().st_size != entry.size:
            raise ValueError("Unexpected model size: "+name)
        if entry.lfs and digest != entry.lfs.sha256:
            raise ValueError("Unexpected model checksum: "+name)
        records[name] = {"sha256": digest, "bytes": path.stat().st_size}
        print("Verified "+name, flush=True)
    manifest = {"schema": 1, "repository": REPOSITORY, "revision": REVISION,
                "license": "MIT", "language": "vi", "files": records}
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    print("Local Vietnamese speech model ready; no runtime network required.", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
