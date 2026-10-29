"""Conservatively verify that the destination is on a different local device."""

import json
import os
import socket
import subprocess
from pathlib import Path


def evaluate(records, source_drives, target_drive):
    indexed = {row["drive"]: row for row in records}
    if not set(source_drives) | {target_drive} <= indexed.keys():
        return {"confirmed": False}
    target = indexed[target_drive]
    independent = all(target["disk"] != indexed[drive]["disk"] for drive in source_drives)
    supported = target["bus"] in {"USB", "SATA", "NVMe", "SAS", "iSCSI", "SD", "MMC"}
    return {"confirmed": independent and supported, "destination_bus": target["bus"],
            "separate_from_source_disks": independent}


def probe(cursor, source_root, destination):
    if os.name != "nt":
        return {"confirmed": False}
    machine = cursor.execute("SELECT CAST(SERVERPROPERTY('MachineName') AS nvarchar(200))").fetchval()
    if str(machine).split(".")[0].casefold() != socket.gethostname().split(".")[0].casefold():
        return {"confirmed": False}
    paths = [Path(row[0]) for row in cursor.execute("SELECT physical_name FROM sys.database_files").fetchall()]
    sources = {Path(source_root).drive.upper(), *(path.drive.upper() for path in paths)}
    target = Path(destination).drive.upper()
    if any(len(drive) != 2 or drive[1] != ":" or not drive[0].isalpha() for drive in sources | {target}):
        return {"confirmed": False}
    letters = {drive[0] for drive in sources}
    script = '''
$ErrorActionPreference='Stop'
$records=foreach($letter in ($env:CHAMCONG_STORAGE_DRIVES.Split(',')|Sort-Object -Unique)){
    $partition=Get-Partition -DriveLetter $letter
    $disk=Get-Disk -Number $partition.DiskNumber
    @{drive=$letter;disk=[int]$disk.Number;bus=[string]$disk.BusType}
}
@($records)|ConvertTo-Json -Compress
'''
    try:
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                                env=dict(os.environ, CHAMCONG_STORAGE_DRIVES=",".join(sorted(letters | {target[0]}))),
                                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
                                creationflags=subprocess.CREATE_NO_WINDOW, check=True)
        records = json.loads(result.stdout)
        return evaluate(records if isinstance(records, list) else [records], letters, target[0])
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        return {"confirmed": False}
