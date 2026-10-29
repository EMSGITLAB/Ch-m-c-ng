"""Collect dependency license metadata without logging private environment values."""
import json
from importlib.metadata import distributions
from pathlib import Path

root = Path(__file__).resolve().parents[1]
records = []
for distribution in distributions():
    metadata = distribution.metadata
    license_name = metadata.get("License-Expression") or metadata.get("License") or "; ".join(metadata.get_all("Classifier", []) or [])
    records.append({"name": metadata["Name"], "version": distribution.version, "license": license_name[:600], "home_page": metadata.get("Home-page", "")})
(root / "evidence/m0/python-licenses.json").write_text(json.dumps(sorted(records, key=lambda x:x["name"].lower()), ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Collected license metadata for {len(records)} Python packages")
