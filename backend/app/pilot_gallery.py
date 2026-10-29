"""Pinned multi-person functional gallery; never a claim of validated accuracy or PAD."""

import hashlib
from collections import defaultdict

import numpy as np
from fastapi import HTTPException
from sqlalchemy import select

from .matching import Gallery
from .models import Employee, FaceTemplate
from .policy_selection import PILOT_PREFIX, PILOT_SCOPE, selected_policy


def pin(template):
    return {"participant_id": template.employee_id, "biometric_revision": template.biometric_revision,
            "template_id": template.id, "template_sha256": hashlib.sha256(template.vector).hexdigest()}


def gallery_from_pins(db, pins, model_id, dimensions):
    if not isinstance(pins, list) or not pins or len(pins) > 15000:
        raise ValueError("invalid_pilot_membership")
    if any(not isinstance(item, dict) for item in pins):
        raise ValueError("invalid_pilot_pin")
    if any(not isinstance(item.get("participant_id"), str) or not isinstance(item.get("template_id"), str)
           for item in pins):
        raise ValueError("invalid_pilot_identity")
    identities = {item.get("participant_id") for item in pins}
    # SQL Server has a 2100-parameter limit. Load current rows once rather than a huge IN list.
    rows = db.execute(select(FaceTemplate, Employee).join(Employee)
        .where(Employee.active == True, FaceTemplate.model_id == model_id,  # noqa: E712
               FaceTemplate.biometric_revision == Employee.biometric_revision)).all()
    people = {person.id: person for _, person in rows if person.id in identities}
    templates = {template.id: template for template, person in rows if person.id in identities}
    samples, excluded = defaultdict(list), set()
    for item in pins:
        identity = item.get("participant_id")
        person, template = people.get(identity), templates.get(item.get("template_id"))
        if (not person or not template or template.employee_id != identity
                or template.biometric_revision != person.biometric_revision
                or item.get("biometric_revision") != person.biometric_revision
                or template.dimensions != dimensions or len(template.vector) != dimensions * 4
                or item.get("template_sha256") != hashlib.sha256(template.vector).hexdigest()):
            excluded.add(identity)
            continue
        samples[identity].append(np.frombuffer(template.vector, dtype="<f4"))
    for identity in excluded:
        samples.pop(identity, None)
    return Gallery(model_id, samples, dimensions)


def authorize_pilot(db, policy):
    if (policy.mode != "functional_trial" or not policy.id.startswith(PILOT_PREFIX)
            or policy.evidence.get("scope") != PILOT_SCOPE or policy.pad_verified
            or selected_policy(db) != policy.id):
        raise HTTPException(503, "Cấu hình nhận diện thử chưa hợp lệ hoặc đã thay đổi.")


def pilot_gallery(db, policy, dimensions=128):
    authorize_pilot(db, policy)
    try:
        gallery = gallery_from_pins(db, policy.evidence.get("templates"), policy.model_id, dimensions)
        if not gallery.samples:
            raise ValueError("empty_pilot_gallery")
        return gallery
    except ValueError as error:
        raise HTTPException(503, "Chưa có mẫu đang hoạt động hợp lệ trong cấu hình thử.") from error
