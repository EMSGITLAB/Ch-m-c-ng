"""Import a user-authorized local manifest, without printing identities or vectors."""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import get_settings  # noqa: E402
from app.database import session_factory  # noqa: E402
from app.face_engine import FaceEngine  # noqa: E402
from app.photo_import import prepare_import, save_import  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("manifest", type=Path)
parser.add_argument("--apply", action="store_true")
parser.add_argument("--reason", default="Nhập bộ ảnh nhân viên do người dùng cung cấp để thử nghiệm local")
args = parser.parse_args()
engine = FaceEngine(get_settings().models_dir)
records = prepare_import(args.manifest, engine)
summary = {"record_count": len(records), "quality_counts": dict(Counter(item["quality"]["reason"] for item in records)),
           "applied": args.apply, "model_id": engine.model_id, "accuracy_validated": False, "remote_urls_accessed": False}
if args.apply:
    with session_factory()() as db:
        summary["import"] = save_import(db, records, engine, args.reason)
private = ROOT / ".runtime/photo-import"
private.mkdir(parents=True, exist_ok=True)
(private / "last-import.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary))
