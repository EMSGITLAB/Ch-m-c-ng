$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
& "$projectRoot\.venv\Scripts\python.exe" -m uvicorn app.main:app --app-dir "$projectRoot\backend" --host 127.0.0.1 --port 8000 --workers 1
exit $LASTEXITCODE

