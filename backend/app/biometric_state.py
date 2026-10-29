"""Subject lock: after any calendar/gallery gate, before capture-session locks."""
from fastapi import HTTPException
from sqlalchemy import update

from .models import Employee


def lock_employee(db, employee_id, expected_revision=None, active_only=False):
    filters = [Employee.id == employee_id]
    if expected_revision is not None:
        filters.append(Employee.biometric_revision == expected_revision)
    if active_only:
        filters.append(Employee.active == True)  # noqa: E712
    # UPDATE holds the row lock until commit, including on SQL Server. A read
    # before expensive image analysis alone cannot prevent a late vector insert.
    row = db.execute(update(Employee).where(*filters)
                     .values(biometric_revision=Employee.biometric_revision, updated_at=Employee.updated_at)
                     .returning(Employee.biometric_revision)
                     .execution_options(synchronize_session=False)).scalar_one_or_none()
    if row is None:
        raise HTTPException(409, "Hồ sơ đã ngừng hoạt động, bị xóa mẫu hoặc thay đổi. Hãy tải lại trạng thái.")
    return row
