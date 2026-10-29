"""Native background server with restart, exclusive ownership and local stop control."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.runtime_supervisor import AlreadyRunning, Supervisor, request_stop, service_status  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--port", type=int, default=8000)
parser.add_argument("--runtime-dir", type=Path, default=ROOT / ".runtime/service")
parser.add_argument("--status", action="store_true")
parser.add_argument("--stop", action="store_true")
args = parser.parse_args()
runtime = args.runtime_dir.resolve()
if not runtime.is_relative_to((ROOT / ".runtime").resolve()):
    raise ValueError("Runtime state must stay inside this project's .runtime")
if args.status:
    print(json.dumps({k: v for k, v in service_status(runtime).items() if k != "instance_nonce"}))
elif args.stop:
    stopped = request_stop(runtime)
    print(json.dumps({"stopped": stopped}))
    raise SystemExit(0 if stopped else 4)
else:
    try:
        raise SystemExit(Supervisor(ROOT, runtime, args.port).run())
    except AlreadyRunning:
        raise SystemExit(0) from None
