"""Write an aggregate local calibration report; never activate a threshold."""
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.calibration import calibrate, load_samples  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.database import session_factory  # noqa: E402


def main():
    manifest = json.loads((get_settings().models_dir / "manifest.json").read_text(encoding="utf-8"))
    with session_factory()() as db:
        samples = load_samples(db, manifest["model_id"], manifest["embedding_dimensions"])
    report = calibrate(samples, manifest["model_id"], manifest["embedding_dimensions"])
    report["generated_at"] = datetime.now(UTC).isoformat()
    target = ROOT / ".runtime" / "calibration" / "report.json"
    target.parent.mkdir(exist_ok=True, parents=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)
    print(json.dumps(report, ensure_ascii=True))


if __name__ == "__main__":
    main()
