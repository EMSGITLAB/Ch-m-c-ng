"""Diagnostic checkpoints and receipt accounting for the isolated HTTP load runner."""

import json
import time
from pathlib import Path


def write_progress(path, state):
    path = Path(path)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state), encoding="utf-8")
    # Windows readers/indexers may briefly hold the previous JSON without delete
    # sharing. Losing a diagnostic checkpoint must not cancel the load itself.
    for delay in (0.01, 0.03, 0.06, 0.1, 0.2):
        try:
            temporary.replace(path)
            return True
        except PermissionError:
            time.sleep(delay)
    try:
        temporary.unlink(missing_ok=True)
    except PermissionError:
        pass
    return False


def reconcile_sessions(rows, successes, failures):
    actual = {row.request_id: row for row in rows}
    expected = {item["request_id"]: item for item in successes}
    failed_ids = {item["request_id"] for item in failures}
    return {
        "all_successful_sessions_used": len(expected) == len(successes) and all(
            key in actual and actual[key].state == "used" and actual[key].receipt
            and actual[key].receipt.get("event_id") == item["event_id"]
            for key, item in expected.items()),
        "failed_sessions_without_committed_receipt": all(
            key not in actual or (actual[key].state != "used" and not actual[key].receipt)
            for key in failed_ids),
        "all_sessions_accounted_for": not (set(expected) & failed_ids)
        and set(actual) <= set(expected) | failed_ids,
    }
