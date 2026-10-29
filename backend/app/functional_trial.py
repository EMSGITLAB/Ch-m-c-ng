"""Explicit, revocable single-person functional trial; no claim of PAD/accuracy."""

import hashlib

import numpy as np
from fastapi import HTTPException
from sqlalchemy import select

from .config import get_settings
from .matching import Gallery
from .models import Employee, FaceTemplate

MODE = "functional_trial"
SCOPE = "single-person-functional-v1"


def authorize_trial(db, policy):
    from .pilot_gallery import authorize_pilot
    from .policy_selection import PILOT_SCOPE

    if policy.evidence.get("scope") == PILOT_SCOPE:
        authorize_pilot(db, policy)
        return
    settings = get_settings()
    evidence = policy.evidence
    if (
        policy.mode != MODE
        or not settings.functional_trial_enabled
        or settings.functional_trial_policy_id != policy.id
        or not policy.id.startswith("trial-")
        or evidence.get("scope") != SCOPE
        or policy.pad_verified
    ):
        raise HTTPException(503, "Chế độ thử luồng chưa được cấu hình đúng.")


def trial_gallery(db, policy, dimensions=128):
    from .pilot_gallery import pilot_gallery
    from .policy_selection import PILOT_SCOPE

    if policy.evidence.get("scope") == PILOT_SCOPE:
        return pilot_gallery(db, policy, dimensions)
    authorize_trial(db, policy)
    evidence = policy.evidence
    template = db.get(FaceTemplate, evidence.get("template_id"), populate_existing=True)
    person = db.scalar(select(Employee).where(Employee.id == evidence.get("participant_id"))
                       .execution_options(populate_existing=True))
    if (
        not template or not person or not person.active
        or template.employee_id != person.id
        or template.biometric_revision != person.biometric_revision
        or evidence.get("biometric_revision") != person.biometric_revision
        or template.model_id != policy.model_id
        or template.dimensions != dimensions or len(template.vector) != dimensions * 4
        or hashlib.sha256(template.vector).hexdigest() != evidence.get("template_sha256")
    ):
        raise HTTPException(503, "Mẫu thử đã đổi/xóa hoặc hồ sơ bị vô hiệu. Cần thiết lập lại phiên thử.")
    return Gallery(policy.model_id, {person.id: [np.frombuffer(template.vector, dtype="<f4")]}, dimensions)
