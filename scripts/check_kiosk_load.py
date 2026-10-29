"""Two HTTP kiosks, real CPU inference and disposable SQL; technical load, not accuracy/PAD."""

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import cv2
import httpx
import numpy as np
import pyodbc
from kiosk_fault_proxy import KioskFaultProxy
from kiosk_load_support import reconcile_sessions, write_progress
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]


def source_digest():
    digest = hashlib.sha256()
    files = list((ROOT / "backend/app").glob("*.py")) + [ROOT / "frontend/src/kioskFlow.ts",
        ROOT / "frontend/src/KioskCapture.tsx", ROOT / "scripts/kiosk_frontend_load.mjs",
        ROOT / "scripts/check_kiosk_load.py", ROOT / "scripts/kiosk_load_support.py",
        ROOT / "scripts/kiosk_fault_proxy.py", ROOT / "models/manifest.json", ROOT / "config/business.json"]
    for file in sorted(files):
        digest.update(file.relative_to(ROOT).as_posix().encode())
        digest.update(file.read_bytes())
    return digest.hexdigest()


source_before = source_digest()
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--minutes", type=float, default=30)
parser.add_argument("--sessions-per-minute", type=int, default=20)
parser.add_argument("--port", type=int, default=8019)
parser.add_argument("--catalog-size", type=int, default=100)
parser.add_argument("--cpu-threads", type=int, default=4)
parser.add_argument("--frame-width", type=int, default=1280)
parser.add_argument("--frame-height", type=int, default=720)
parser.add_argument("--diagnostics", action="store_true", help="Record stage timings in the isolated server")
parser.add_argument("--frontend-flow", action="store_true", help="Use the actual frontend controller at its 500 ms cadence")
parser.add_argument("--check-recovery", choices=("before_start", "after_commit", "after_frame", "standing"),
                    help="Short functional fault/continuous-face check, separate from the latency gate")
args = parser.parse_args()
if not 0 < args.minutes <= 60 or not 2 <= args.sessions_per_minute <= 60:
    raise ValueError("Use 0–60 minutes and 2–60 sessions/minute")
if not 1 <= args.catalog_size <= 1000:
    raise ValueError("Use a technical catalog of 1–1000 entries")
if not 1 <= args.cpu_threads <= 32:
    raise ValueError("Use 1–32 CPU threads in the isolated backend")
if not 480 <= min(args.frame_width, args.frame_height) or max(args.frame_width, args.frame_height) > 1600:
    raise ValueError("Use 480–1600 pixel frame edges, matching the client capture limit")
if args.check_recovery and (not args.frontend_flow or args.minutes > .5):
    raise ValueError("Recovery checks require --frontend-flow and a duration of at most 0.5 minutes")
name = "ChamCong_LoadCheck_" + secrets.token_hex(4)
assert re.fullmatch(r"ChamCong_LoadCheck_[0-9a-f]{8}", name)
runtime = ROOT / ".runtime/load" / name
runtime.mkdir(parents=True)
base = ("DRIVER={ODBC Driver 18 for SQL Server};SERVER=localhost;DATABASE=master;"
        "Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=yes;Connection Timeout=5")
url = URL.create("mssql+pyodbc", query={"odbc_connect": base.replace("DATABASE=master", "DATABASE=" + name)})
policy_id = "trial-pilot-" + uuid4().hex
env = {key: value for key, value in os.environ.items() if not key.startswith("CHAMCONG_")}
env.update(CHAMCONG_DATABASE_URL=url.render_as_string(hide_password=False),
           CHAMCONG_SESSION_SECRET=secrets.token_urlsafe(48), CHAMCONG_RUNTIME_DIR=str(runtime),
           CHAMCONG_FUNCTIONAL_TRIAL_ENABLED="true", CHAMCONG_FUNCTIONAL_TRIAL_POLICY_ID=policy_id,
           CHAMCONG_OPENCV_THREADS=str(args.cpu_threads),
           PYTHONIOENCODING="utf-8")
if args.check_recovery:
    business = json.loads((ROOT / "config/business.json").read_text(encoding="utf-8"))
    business["cooldown_seconds"] = 1  # Disposable DB only: each measured commit must create a new event.
    (runtime / "business.json").write_text(json.dumps(business), encoding="utf-8")
    env["CHAMCONG_BUSINESS_CONFIG_PATH"] = str(runtime / "business.json")
os.environ.update({key: value for key, value in env.items() if key.startswith("CHAMCONG_")})
sys.path.insert(0, str(ROOT / "backend"))
from app.face_engine import FaceEngine  # noqa: E402
from app.matching import SCORING_RULE  # noqa: E402
from app.models import AttendanceEvent, Device, Employee, FaceTemplate, RecognitionPolicy, RecognitionSession  # noqa: E402
from app.pilot_gallery import pin  # noqa: E402
from app.policy_selection import PILOT_SCOPE  # noqa: E402
from app.runtime_supervisor import FileLease, ProcessJob  # noqa: E402

lease = FileLease(ROOT / ".runtime/load/check.lock")
created, child, engine, job = False, None, None, None
frontend, frontend_job, frontend_log = None, None, None
fault_proxy = None
tokens = [secrets.token_urlsafe(32) for _ in range(2)]
failures, samples, receipts = [], [], []
checkpoint_warnings = 0
started = time.monotonic()


def checked(response, expected=200):
    if response.status_code != expected:
        raise RuntimeError(f"HTTP {response.status_code}")
    return response.json()


def run_session(worker, photo):
    begin = time.monotonic()
    request_id = str(uuid4())
    phase = "start"
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{args.port}", timeout=25, trust_env=False,
                          cookies={"chamcong_kiosk": tokens[worker]}) as client:
            row = checked(client.post("/api/kiosk/recognition/sessions", json={"request_id": request_id},
                                      headers={"X-Kiosk-Intent": "start-recognition"}), 201)
            first_frame = time.monotonic()
            for index in range(1, 4):
                phase = f"frame_{index}"
                # Identical licensed fixture with a unique trailing test identifier. This is
                # protocol/load traffic, never independent camera samples or PAD evidence.
                content = photo + (row["request_id"] + str(index)).encode()
                frame = checked(client.post(f"/api/kiosk/recognition/sessions/{row['request_id']}/frames/{index}",
                                            content=content, headers={"Content-Type": "image/jpeg",
                                            "X-Kiosk-Intent": "capture-recognition",
                                            "X-Capture-Nonce": row["capture_nonce"]}))
                if index < 3:
                    time.sleep(0.46)
            if frame["state"] != "verified":
                raise RuntimeError("chain_not_verified")
            endpoint = f"/api/kiosk/attendance/{row['request_id']}/commit"
            phase = "commit"
            receipt = checked(client.post(endpoint, json={}, headers={"X-Kiosk-Intent": "record-attendance"}))
            elapsed = time.monotonic() - first_frame
            if receipt["status"] not in {"recorded", "duplicate"}:
                raise RuntimeError("receipt_not_recorded")
            for _ in range(10):
                phase = "retry_commit"
                retry = checked(client.post(endpoint, json={}, headers={"X-Kiosk-Intent": "record-attendance"}))
                if retry != receipt:
                    raise RuntimeError("retry_receipt_changed")
            return {"request_id": request_id, "seconds": elapsed, "event_id": receipt["event_id"], "status": receipt["status"],
                    "wall_seconds": time.monotonic() - begin}
    except (httpx.HTTPError, RuntimeError, KeyError) as error:
        return {"request_id": request_id, "worker": worker, "phase": phase,
                "error_type": type(error).__name__, "error_message": str(error)[:200],
                "wall_seconds": time.monotonic() - begin}


try:
    with socket.socket() as port:
        port.bind(("127.0.0.1", args.port))
    face_engine = FaceEngine(ROOT / "models")
    image = cv2.imdecode(np.frombuffer((ROOT / ".runtime/fixtures/sface_demo.jpg").read_bytes(), np.uint8), cv2.IMREAD_COLOR)
    face = face_engine.detect(image)[0]
    x, y, width, height = face[:4]
    crop = image[max(0, int(y-height*.15)):min(image.shape[0], int(y+height*1.15)),
                 max(0, int(x-width*.15)):min(image.shape[1], int(x+width*1.15))]
    scene = np.full((args.frame_height, args.frame_width, 3), 140, dtype=np.uint8)
    top, left = (args.frame_height-480)//2, (args.frame_width-480)//2
    scene[top:top+480, left:left+480] = cv2.resize(crop, (480, 480))
    valid, encoded = cv2.imencode(".jpg", scene, [cv2.IMWRITE_JPEG_QUALITY, 88])
    assert valid
    photo = encoded.tobytes()
    vector, metadata = face_engine.analyze(photo)
    assert metadata["quality"]["accepted"]
    model = face_engine.model_id
    del face_engine
    with pyodbc.connect(base, autocommit=True) as admin:
        admin.execute(f"CREATE DATABASE [{name}]")
        created = True
    migration = subprocess.run([sys.executable, "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", "head"],
                               cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
    (runtime / "migration.log").write_text(migration.stdout + migration.stderr, encoding="utf-8")
    if migration.returncode:
        raise RuntimeError("Isolated database migration failed")
    engine = create_engine(url, hide_parameters=True)
    with Session(engine) as db:
        now = datetime.now(UTC)
        person = Employee(code="LOAD-FIXTURE", name="Licensed technical load fixture")
        db.add(person)
        db.flush()
        template = FaceTemplate(employee_id=person.id, model_id=model, dimensions=128,
                                vector=np.asarray(vector, dtype="<f4").tobytes(), quality={"technical_load_only": True})
        db.add(template)
        db.flush()
        pins = [pin(template)]
        random = np.random.default_rng(20261029)
        for index in range(1, args.catalog_size):
            distractor = Employee(code=f"SYNTHETIC-{index}", name=f"Synthetic load fixture {index}")
            db.add(distractor)
            db.flush()
            value = random.normal(size=128).astype("<f4")
            value /= np.linalg.norm(value)
            reference = FaceTemplate(employee_id=distractor.id, model_id=model, dimensions=128,
                                     vector=value.tobytes(), quality={"synthetic_load_only": True})
            db.add(reference)
            db.flush()
            pins.append(pin(reference))
        db.add(RecognitionPolicy(id=policy_id, model_id=model, scoring_rule=SCORING_RULE,
                                 threshold=0.5, minimum_margin=0, enabled=True, mode="functional_trial",
                                 pad_verified=False, validated_at=now, evidence={"scope": PILOT_SCOPE,
                                 "sequence_protocol": "stable-three-v1", "templates": pins,
                                 "technical_load_only": True}))
        for index in range(2):
            db.add(Device(name=f"Load kiosk {index}", direction="in" if index == 0 else "out", active=True,
                          token_hash=hashlib.sha256(tokens[index].encode()).hexdigest(),
                          token_expires_at=now+timedelta(hours=3)))
        db.commit()
    with (runtime / "server.log").open("w", encoding="utf-8") as log:
        server = ([sys.executable, "scripts/profile_kiosk_server.py", "--port", str(args.port)] if args.diagnostics
                  else [sys.executable, "-m", "uvicorn", "app.main:app", "--app-dir", "backend",
                        "--host", "127.0.0.1", "--port", str(args.port), "--no-access-log"])
        child = subprocess.Popen(server,
                                 cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        job = ProcessJob(child)
        (ROOT / ".runtime/load/latest-run.json").write_text(json.dumps({
            "runner_pid": os.getpid(), "backend_pid": child.pid, "runtime": str(runtime),
            "requested_minutes": args.minutes}), encoding="utf-8")
        for _ in range(90):
            if child.poll() is not None:
                raise RuntimeError("Isolated backend exited during startup")
            try:
                if httpx.get(f"http://127.0.0.1:{args.port}/health/ready", timeout=2, trust_env=False).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)
        else:
            raise RuntimeError("Isolated backend did not become ready")
        if args.frontend_flow:
            node = shutil.which("node")
            if not node:
                raise RuntimeError("Node 24 is required for the frontend development check")
            probe = runtime / "public-probe.jpg"
            probe.write_bytes(photo)
            if args.check_recovery and args.check_recovery != "standing":
                fault_proxy = KioskFaultProxy(args.port)
            frontend_log = (runtime / "frontend.log").open("w", encoding="utf-8")
            frontend = subprocess.Popen([node, "scripts/kiosk_frontend_load.mjs"], cwd=ROOT,
                env=env | {"CHAMCONG_LOAD_PORT": str(fault_proxy.port if fault_proxy else args.port), "CHAMCONG_LOAD_TOKENS": json.dumps(tokens),
                           "CHAMCONG_LOAD_PHOTO": str(probe)}, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=frontend_log, text=True, encoding="utf-8",
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            frontend_job = ProcessJob(frontend)
        with ThreadPoolExecutor(max_workers=2) as pool:
            def run_pair(measured=False):
                if frontend is None:
                    return list(pool.map(lambda n: run_session(n, photo), range(2)))
                frontend.stdin.write(json.dumps({"command": "pair",
                    "standing": measured and args.check_recovery == "standing"})+"\n")
                frontend.stdin.flush()
                line = frontend.stdout.readline()
                if not line:
                    raise RuntimeError("Frontend load controller exited; inspect its private log")
                return json.loads(line)

            warmup = run_pair()
            if any("error_type" in item for item in warmup):
                raise RuntimeError("Real-model kiosk load warmup failed")
            if fault_proxy:
                fault_proxy.arm(args.check_recovery)
            measured_start = time.monotonic()
            pairs = max(1, round(args.minutes * args.sessions_per_minute / 2))
            interval = 120 / args.sessions_per_minute
            for pair in range(pairs):
                due = measured_start + pair * interval
                while time.monotonic() < due:
                    time.sleep(min(1, due-time.monotonic()))
                results = run_pair(measured=True)
                with (runtime / "session-results.jsonl").open("a", encoding="utf-8") as log:
                    for item in results:
                        log.write(json.dumps(item) + "\n")
                for item in results:
                    if "error_type" in item:
                        failures.append(item)
                    else:
                        samples.append(item["seconds"])
                        receipts.append(item)
                state = {"pairs_completed": pair+1, "pairs_total": pairs, "sessions_ok": len(samples),
                         "sessions_failed": len(failures), "elapsed_seconds": round(time.monotonic()-measured_start, 1)}
                marker = runtime / "progress.json"
                if not write_progress(marker, state):
                    checkpoint_warnings += 1
            finish = measured_start + args.minutes * 60
            while time.monotonic() < finish:
                time.sleep(min(1, finish-time.monotonic()))
        with Session(engine) as db:
            events = db.scalar(select(func.count()).select_from(AttendanceEvent))
            sessions = db.scalar(select(func.count()).select_from(RecognitionSession))
            used = db.scalar(select(func.count()).select_from(RecognitionSession).where(RecognitionSession.state == "used"))
            accounting = reconcile_sessions(db.scalars(select(RecognitionSession)).all(), warmup + receipts, failures)
        all_receipts = warmup + receipts
        unique_events = len({item["event_id"] for item in all_receipts})
        recorded = sum(item["status"] == "recorded" for item in all_receipts)
        p95 = float(np.percentile(samples, 95)) if samples else None
        report = {"two_http_kiosks": True, "real_cpu_detection_embedding_and_matching": True,
                  "sqlserver_isolated": True, "requested_minutes": args.minutes,
                  "target_sessions_per_minute": args.sessions_per_minute, "measured_sessions": len(samples)+len(failures),
                  "successful_sessions": len(samples), "failed_sessions": len(failures),
                  "valid_first_frame_to_commit_p95_seconds": round(p95, 4) if p95 is not None else None,
                  "p95_includes_stability_pause": True, "ten_identical_commit_retries_per_session": True,
                  "events": events, "recorded_receipts_including_warmup": recorded,
                  "events_match_unique_receipts": events == recorded == unique_events,
                  "all_sessions_used": sessions == used == len(all_receipts),
                  **accounting,
                  "checkpoint_write_warnings": checkpoint_warnings,
                  "diagnostic_instrumentation": args.diagnostics,
                  "actual_frontend_controller": args.frontend_flow,
                  "latency_origin": "first quality-accepted full-scene preview" if args.frontend_flow else "first recognition frame",
                  "frontend_poll_interval_ms": 500 if args.frontend_flow else None,
                  "failure_details": [{key: item[key] for key in ("error_type", "phase", "error_message", "wall_seconds")}
                                      for item in failures],
                  "technical_error_rate": len(failures)/max(1, len(samples)+len(failures)),
                  "elapsed_seconds": round(time.monotonic()-measured_start, 2),
                  "fixture": "OpenCV Zoo SFace demo Apache-2.0; repeated licensed fixture only",
                  "live_database_modified": False, "real_camera_or_accuracy_or_pad_validation": False,
                  "production_threshold_modified": False, "runtime_source_sha256": source_before,
                  "technical_gallery_size": args.catalog_size, "real_public_probe_identities": 1,
                  "opencv_cpu_threads": args.cpu_threads,
                  "technical_frame_pixels": [args.frame_width, args.frame_height],
                  "technical_jpeg_quality": 88, "technical_frame_bytes": len(photo),
                  "synthetic_distractor_templates": args.catalog_size-1,
                  "runtime_source_unchanged_during_measurement": source_before == source_digest()}
        report["source_digest_includes_frontend_controller"] = True
        report["source_digest_includes_test_harness"] = True
        report["technical_base_frame_sha256"] = hashlib.sha256(photo).hexdigest()
        report["passed"] = bool(p95 is not None and p95 <= 2 and report["technical_error_rate"] <= .01
                                and report["events_match_unique_receipts"] and all(accounting.values())
                                and report["runtime_source_unchanged_during_measurement"])
        report["performance_gate_passed"] = report["passed"]
        report["is_performance_gate"] = not bool(args.check_recovery)
        if args.check_recovery:
            proof = fault_proxy.snapshot() if fault_proxy else {"mode": "standing"}
            steady = args.check_recovery != "standing" or all(
                item["face_remained_after_success_seconds"] >= 8 and item["request_ids_issued"] == 1
                for item in receipts)
            injected = not fault_proxy or proof["connections_dropped"] == 2
            durable = args.check_recovery != "after_commit" or proof["new_events_confirmed_before_drop"] == 2
            report.update(functional_scenario=args.check_recovery, fault_injection=proof,
                          isolated_test_cooldown_seconds=1, operational_business_config_changed=False,
                          no_replacement_request_ids=all(item["request_ids_issued"] == 1 for item in receipts),
                          continuous_face_did_not_open_new_request=steady if args.check_recovery == "standing" else None)
            report["passed"] = bool(not failures and len(receipts) >= 2 and all(accounting.values())
                and report["events_match_unique_receipts"] and report["runtime_source_unchanged_during_measurement"]
                and injected and durable and steady and report["no_replacement_request_ids"])
        target = ROOT / "evidence/m5" / ("kiosk-load-check.json" if args.minutes >= 30 else "kiosk-load-smoke.json")
        if args.check_recovery:
            target = ROOT / "evidence/m5" / ("kiosk-recovery-"+args.check_recovery+".json")
        target.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report))
        if not report["passed"]:
            raise SystemExit(1)
finally:
    if frontend and frontend.poll() is None:
        frontend.terminate()
        try:
            frontend.wait(timeout=5)
        except subprocess.TimeoutExpired:
            frontend.kill()
            frontend.wait(timeout=5)
    if frontend_job:
        frontend_job.close()
    if frontend_log:
        frontend_log.close()
    if fault_proxy:
        fault_proxy.close()
    if child and child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)
    if engine:
        engine.dispose()
    if job:
        job.close()
    if created:
        assert re.fullmatch(r"ChamCong_LoadCheck_[0-9a-f]{8}", name)
        with pyodbc.connect(base, autocommit=True) as admin:
            admin.execute(f"ALTER DATABASE [{name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE")
            admin.execute(f"DROP DATABASE [{name}]")
    lease.close()
