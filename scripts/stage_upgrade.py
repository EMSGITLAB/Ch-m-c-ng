"""Prepare and verify a candidate on a new recovered database; never switch the live service."""

import argparse
import getpass
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.upgrade import stage  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--archive", type=Path, required=True)
parser.add_argument("--release", type=Path, required=True)
parser.add_argument("--key-file", type=Path)
parser.add_argument("--rollback-wheels", type=Path)
args = parser.parse_args()
password = None
if args.key_file and args.key_file.suffix.lower() == ".cckey":
    if sys.stdin is None or not sys.stdin.isatty():
        raise ValueError("Use a local interactive terminal for the recovery password")
    password = getpass.getpass("Mật khẩu khóa khôi phục: ")
result = stage(args.archive, args.release, key_path=args.key_file, key_password=password, rollback_wheels=args.rollback_wheels)
print(json.dumps(result))
raise SystemExit(0 if result["staged"] else 1)
