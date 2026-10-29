"""Build a fresh local gallery from currently active, current-revision templates."""
from collections import defaultdict

import numpy as np
from sqlalchemy import select

from .matching import Gallery
from .models import Employee, FaceTemplate


def load_gallery(db, model_id, dimensions=128):
    rows = db.scalars(select(FaceTemplate).join(Employee)
                      .where(Employee.active == True, FaceTemplate.model_id == model_id,  # noqa: E712
                             FaceTemplate.biometric_revision == Employee.biometric_revision)).all()
    samples = defaultdict(list)
    for row in rows:
        if row.dimensions != dimensions or len(row.vector) != dimensions * 4:
            raise ValueError("invalid_template_dimensions")
        samples[row.employee_id].append(np.frombuffer(row.vector, dtype="<f4").copy())
    # No persistent recognition cache. Recognition sequences hold calendar_gate
    # while ranking; attendance additionally rechecks revision/active at commit.
    return Gallery(model_id, samples, dimensions)
