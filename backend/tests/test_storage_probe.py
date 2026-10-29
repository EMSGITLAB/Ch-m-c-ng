from app.storage_probe import evaluate


def test_different_drive_letters_on_same_device_are_not_independent():
    records = [{"drive": drive, "disk": 0, "bus": "NVMe"} for drive in ("C", "D", "E")]
    assert evaluate(records, {"C", "D"}, "E")["confirmed"] is False


def test_usb_device_must_differ_from_both_database_and_key_device():
    records = [{"drive": "C", "disk": 0, "bus": "NVMe"}, {"drive": "D", "disk": 0, "bus": "NVMe"},
               {"drive": "E", "disk": 1, "bus": "USB"}]
    assert evaluate(records, {"C", "D"}, "E")["confirmed"] is True
    assert evaluate(records, {"C", "E"}, "E")["confirmed"] is False


def test_virtual_or_missing_device_is_not_claimed_independent():
    assert evaluate([], {"C"}, "E")["confirmed"] is False
    records = [{"drive": "C", "disk": 0, "bus": "NVMe"}, {"drive": "E", "disk": 1, "bus": "File Backed Virtual"}]
    assert evaluate(records, {"C"}, "E")["confirmed"] is False
