"""Resolve an administrator-published pilot revision, with the old explicit trial as fallback."""

from sqlalchemy import select

from .models import RecognitionPolicy

PILOT_SCOPE = "local-functional-pilot-v1"
PILOT_PREFIX = "trial-pilot-"


def selected_policy(db, fallback=None):
    rows = db.scalars(select(RecognitionPolicy.id).where(
        RecognitionPolicy.enabled == True,  # noqa: E712
        RecognitionPolicy.mode == "functional_trial",
        RecognitionPolicy.id.startswith(PILOT_PREFIX))).all()
    if len(rows) > 1:
        return None
    return rows[0] if rows else fallback
