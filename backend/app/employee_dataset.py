"""Normalize an operator-provided roster without guessing conflicting identity metadata."""

from collections import defaultdict

from .employees import EmployeeInput


def canonical_roster(rows):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 1000:
        raise ValueError("A roster must have 1–1000 records")
    grouped = defaultdict(list)
    for row in rows:
        person = EmployeeInput(code=row["code"], name=row["name"], department=row.get("department") or "")
        local = row.get("localFile")
        if local is not None and not isinstance(local, str):
            raise ValueError("localFile must be a relative string or null")
        grouped[person.code].append((person, local or None, row.get("idStaff")))
    roster, conflicts = [], []
    for code, variants in grouped.items():
        names = {person.name for person, _, _ in variants}
        files = {local for _, local, _ in variants if local}
        if len(names) != 1 or len(files) > 1:
            raise ValueError("Duplicate employee code has conflicting identity or photo metadata")
        departments = {person.department for person, _, _ in variants if person.department}
        department = next(iter(departments)) if len(departments) == 1 else ""
        person = EmployeeInput(code=code, name=next(iter(names)), department=department)
        if len(departments) > 1:
            conflicts.append({"code": code, "field": "department", "source_values": sorted(departments),
                              "source_ids": [identity for _, _, identity in variants], "stored_value": ""})
        roster.append({**person.model_dump(exclude={"active"}), "localFile": next(iter(files)) if files else None})
    return roster, conflicts
