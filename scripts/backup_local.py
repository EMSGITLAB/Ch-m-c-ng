"""Create an encrypted local recovery bundle; never print keys or SQL connection strings."""

import argparse
import getpass
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import get_settings  # noqa: E402
from app.native_backup import create_backup, restore_new_database  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__)
subparsers = parser.add_subparsers(dest="command", required=True)
backup = subparsers.add_parser("create")
backup.add_argument("--destination", type=Path)
restore = subparsers.add_parser("restore-new")
restore.add_argument("archive", type=Path)
restore.add_argument("--key-file", type=Path)
restore.add_argument("--database-name")
args = parser.parse_args()
runtime = get_settings().runtime_dir
def output(value):
    if sys.stdout is not None:
        print(json.dumps(value))


try:
    if args.command == "create":
        result = create_backup(args.destination)
        output({key: value for key, value in result.items() if key not in {"archive_path", "cipher_sha256"}})
    else:
        password = None
        if args.key_file and args.key_file.suffix.lower() == ".cckey":
            if sys.stdin is None or not sys.stdin.isatty():
                raise ValueError("Use an interactive local terminal to enter the recovery-key password")
            password = getpass.getpass("Mật khẩu khóa khôi phục: ")
        result = restore_new_database(args.archive, key_path=args.key_file, key_password=password,
                                      target_name=args.database_name)
        private = runtime / "backups/last-restore.json"
        private.parent.mkdir(parents=True, exist_ok=True)
        private.write_text(json.dumps(result, indent=2), encoding="utf-8")
        output({key: value for key, value in result.items() if key != "app_root"})
except Exception as error:
    from datetime import UTC, datetime

    metadata = {"failed_at": datetime.now(UTC).isoformat(), "operation": args.command,
                "error_type": type(error).__name__}
    target = runtime / "backups" / ("last-backup-error.json" if args.command == "create" else "last-restore-error.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(metadata), encoding="utf-8")
    output(metadata)
    raise SystemExit(1) from None
