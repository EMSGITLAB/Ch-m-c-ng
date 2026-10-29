"""Trace only the disposable kiosk load server; never enable this on the live application."""

import argparse
import functools
import hashlib
import json
import re
import sys
import threading
import time
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine, make_url

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import get_settings  # noqa: E402


def main(port):
    settings = get_settings()
    runtime = settings.runtime_dir.resolve()
    connection = make_url(settings.database_url).query.get("odbc_connect", "")
    match = re.search(r"(?:^|;)DATABASE=(ChamCong_LoadCheck_[0-9a-f]{8})(?:;|$)", connection, re.I)
    if (not match or runtime.name.lower() != match[1].lower()
            or runtime.parent != (ROOT / ".runtime/load").resolve()):
        raise ValueError("Diagnostics require the disposable load database and its private runtime")
    lock = threading.Lock()
    with (runtime / "stages.jsonl").open("a", encoding="utf-8", buffering=1) as stages:

        def record(stage, action, **values):
            with lock:
                stages.write(json.dumps({"at": time.time(), "thread": threading.get_native_id(),
                                         "stage": stage, "action": action, **values}) + "\n")

        def trace(stage, function):
            @functools.wraps(function)
            def wrapped(*args, **kwargs):
                label = stage + (":" + args[1].__name__ if stage == "database_call" else "")
                begin = time.perf_counter()
                record(label, "start")
                try:
                    return function(*args, **kwargs)
                finally:
                    record(label, "finish", seconds=round(time.perf_counter()-begin, 6))
            return wrapped

        @event.listens_for(Engine, "before_cursor_execute")
        def before(connection, cursor, statement, parameters, context, executemany):
            context.load_started = time.perf_counter()
            context.load_query = hashlib.sha256(statement.encode()).hexdigest()[:12]
            record("sql", "start", query=context.load_query, operation=statement.lstrip().split()[0])

        @event.listens_for(Engine, "after_cursor_execute")
        def after(connection, cursor, statement, parameters, context, executemany):
            record("sql", "finish", query=context.load_query,
                   seconds=round(time.perf_counter()-context.load_started, 6))

        from app import attendance_api, recognition_api

        recognition_api.context = trace("context", recognition_api.context)
        recognition_api.database_call = trace("database_call", recognition_api.database_call)
        attendance_api.selected_policy = trace("commit_policy", attendance_api.selected_policy)
        attendance_api.commit_recognition = trace("commit", attendance_api.commit_recognition)
        original_pool = recognition_api.run_in_threadpool

        async def pool(function, *args, **kwargs):
            begin = time.perf_counter()
            label = "worker:" + function.__name__
            record(label, "start")
            try:
                return await original_pool(function, *args, **kwargs)
            finally:
                record(label, "finish", seconds=round(time.perf_counter()-begin, 6))

        recognition_api.run_in_threadpool = pool
        import uvicorn

        uvicorn.run("app.main:app", host="127.0.0.1", port=port, access_log=False, use_colors=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, type=int)
    main(parser.parse_args().port)
