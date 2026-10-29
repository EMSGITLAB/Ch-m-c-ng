"""Download native tools into this project, without installing Windows services."""
import hashlib
import json
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"
RUNTIME.mkdir(exist_ok=True)


def download(url, destination):
    if destination.exists():
        return
    request = urllib.request.Request(url, headers={"User-Agent": "ChamCongLocalSetup/0.1"})
    temporary = destination.with_suffix(".download")
    with urllib.request.urlopen(request, timeout=90) as response, temporary.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
    temporary.replace(destination)


def extract(archive_path, destination, prefixes=None):
    destination.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            normalized = member.filename.replace("\\", "/")
            if prefixes and not normalized.startswith(prefixes):
                continue
            target = (destination / normalized).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise ValueError("Unsafe archive entry")
            archive.extract(member, destination)


records = []
pg_url = "https://sbp.enterprisedb.com/getfile.jsp?fileid=1260616"
pg_zip = RUNTIME / "postgresql-17-windows-x64.zip"
download(pg_url, pg_zip)
extract(pg_zip, RUNTIME / "postgresql", ("pgsql/bin/", "pgsql/lib/", "pgsql/share/", "pgsql/doc/"))
records.append({"tool": "postgresql", "version": "17.11 (provider archive)", "source": pg_url,
                "sha256": hashlib.file_digest(pg_zip.open("rb"), "sha256").hexdigest(), "vendor_checksum_verified": False})
(ROOT / "evidence" / "m0" / "native-downloads.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
print("PostgreSQL prepared", flush=True)

