import numpy as np
import pytest
from app.matching import Gallery, Ranking, decide


def test_top_two_are_distinct_people_and_spurious_template_does_not_dominate():
    query = np.array([1, 0, 0])
    gallery = Gallery("m", {"true": [[.8, .6, 0]] * 3,
                            "outlier": [[1, 0, 0], [0, 1, 0], [0, 1, 0]]}, dimensions=3)
    ranking = gallery.rank(query, "m")
    assert ranking.first_id == "true"
    assert ranking.first_score == pytest.approx(.8)
    assert ranking.second_score == pytest.approx(1/3)
    assert decide(ranking, .7, .1) == "matched"


def test_normalization_template_order_and_person_order_do_not_change_scores():
    samples = {"a": [[5, 0], [2, 0], [9, 0], [0, 1]], "b": [[0, 8]] * 3}
    expected = Gallery("m", samples, 2).rank([12, 0], "m")
    reordered = {person: list(reversed(vectors)) for person, vectors in reversed(list(samples.items()))}
    assert Gallery("m", reordered, 2).rank([1, 0], "m") == expected


@pytest.mark.parametrize("ranking,threshold,gap,result", [
    (Ranking(None, None, None), .4, .1, "empty_gallery"),
    (Ranking("a", .9, None), .4, .1, "insufficient_gallery"),
    (Ranking("a", .5, .1), .5, .1, "unknown"),
    (Ranking("a", .8, .8), .5, 0, "ambiguous"),
    (Ranking("a", .75, .5), .5, .25, "ambiguous"),
    (Ranking("a", .9, .5), .5, .1, "matched"),
])
def test_decision_boundaries_and_ambiguous_or_single_person_gallery(ranking, threshold, gap, result):
    assert decide(ranking, threshold, gap) == result


def test_model_corruption_and_invalid_parameters_fail_closed():
    gallery = Gallery("m", {"a": [[1, 0]] * 3}, 2)
    with pytest.raises(ValueError, match="model_mismatch"):
        gallery.rank([1, 0], "other")
    for vector in ([0, 0], [float("nan"), 1], [1, 2, 3]):
        with pytest.raises(ValueError, match="invalid_vector"):
            gallery.rank(vector, "m")
    with pytest.raises(ValueError, match="insufficient_templates"):
        Gallery("m", {"a": []}, 2)
    with pytest.raises(ValueError, match="invalid_threshold"):
        decide(Ranking("a", 1, 0), float("nan"), 0)


def test_one_reference_is_supported_without_fabricating_extra_templates():
    gallery = Gallery("m", {"a": [[1, 0]], "b": [[0, 1]]}, 2)
    assert gallery.samples["a"].shape == (1, 2)
    ranking = gallery.rank([.8, .6], "m")
    assert ranking.first_id == "a"
    assert ranking.first_score == pytest.approx(.8)
    assert ranking.second_score == pytest.approx(.6)


def test_two_references_average_available_scores_and_three_reference_behavior_is_preserved():
    ranking = Gallery("m", {"a": [[1, 0], [0, 1]], "b": [[0, 1]] * 3}, 2).rank([1, 0], "m")
    assert ranking.first_id == "a" and ranking.first_score == pytest.approx(.5)
    assert ranking.second_score == pytest.approx(0)
