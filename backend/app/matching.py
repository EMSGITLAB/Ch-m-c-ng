"""Local cosine matching, shared by calibration and later attendance decisions."""
from dataclasses import dataclass

import numpy as np

SCORING_RULE = "mean-top3-available-per-person-v2"


def normalized(vector, dimensions):
    value = np.asarray(vector, dtype=np.float32)
    if value.shape != (dimensions,) or not np.isfinite(value).all():
        raise ValueError("invalid_vector")
    norm = float(np.linalg.norm(value))
    if not np.isfinite(norm) or norm < 1e-8:
        raise ValueError("invalid_vector")
    return value / norm


@dataclass(frozen=True)
class Ranking:
    first_id: str | None
    first_score: float | None
    second_score: float | None

    @property
    def margin(self):
        if self.first_score is None or self.second_score is None:
            return None
        return self.first_score - self.second_score


class Gallery:
    def __init__(self, model_id, samples, dimensions=128):
        self.model_id = model_id
        self.dimensions = dimensions
        self.samples = {}
        for person, vectors in samples.items():
            if len(vectors) < 1:
                raise ValueError("insufficient_templates")
            self.samples[person] = np.stack([normalized(vector, dimensions) for vector in vectors])

    def rank(self, vector, model_id):
        if model_id != self.model_id:
            raise ValueError("model_mismatch")
        query = normalized(vector, self.dimensions)
        scores = []
        for person, templates in self.samples.items():
            cosines = np.clip(templates @ query, -1, 1)
            score = float(np.sort(cosines)[-3:].mean())
            scores.append((person, score))
        scores.sort(key=lambda item: (-item[1], item[0]))
        if not scores:
            return Ranking(None, None, None)
        return Ranking(scores[0][0], scores[0][1], scores[1][1] if len(scores) > 1 else None)


def decide(ranking, threshold, minimum_margin):
    if not np.isfinite(threshold) or not -1 <= threshold <= 1 or not np.isfinite(minimum_margin) or not 0 <= minimum_margin <= 2:
        raise ValueError("invalid_threshold")
    if ranking.first_score is None:
        return "empty_gallery"
    if ranking.second_score is None:
        return "insufficient_gallery"
    if ranking.first_score <= threshold:
        return "unknown"
    if ranking.margin <= minimum_margin:
        return "ambiguous"
    return "matched"
