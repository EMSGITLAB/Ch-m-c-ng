import pytest
from app.employee_dataset import canonical_roster


def test_roster_keeps_leading_zeros_null_photo_and_nfc_optional_department():
    rows, conflicts = canonical_roster([{"code": "000001", "name": " Hồ sơ thử ", "department": None,
                                        "localFile": None, "imageUrl": "https://unused.invalid/photo"}])
    assert rows == [{"code": "000001", "name": "Hồ sơ thử", "department": "", "localFile": None}]
    assert conflicts == []


def test_duplicate_same_identity_retains_department_conflict_without_choosing_one():
    rows, conflicts = canonical_roster([
        {"code": "0001", "name": "Hồ sơ thử", "department": "A", "localFile": "a.png", "idStaff": 1},
        {"code": "0001", "name": "Hồ sơ thử", "department": "B", "localFile": "a.png", "idStaff": 2}])
    assert len(rows) == 1 and rows[0]["department"] == ""
    assert conflicts[0]["source_values"] == ["A", "B"] and conflicts[0]["source_ids"] == [1, 2]


@pytest.mark.parametrize("change", [{"name": "Hồ sơ khác"}, {"localFile": "b.png"}])
def test_duplicate_code_cannot_silently_merge_conflicting_identity_or_photo(change):
    base = {"code": "0001", "name": "Hồ sơ thử", "localFile": "a.png"}
    with pytest.raises(ValueError, match="conflicting"):
        canonical_roster([base, base | change])


def test_roster_supports_more_than_one_daily_batch_without_unbounded_input():
    rows = [{"code": f"{index:06}", "name": f"Fixture {index}", "localFile": None} for index in range(373)]
    assert len(canonical_roster(rows)[0]) == 373
    with pytest.raises(ValueError):
        canonical_roster(rows*3)
