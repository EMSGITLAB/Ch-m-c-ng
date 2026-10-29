param([string]$PythonCommand='py')
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if(-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')){
    if([System.IO.Path]::GetFileNameWithoutExtension($PythonCommand) -eq 'py'){
        & $PythonCommand -3.12 -m venv .venv
    } else {
        & $PythonCommand -m venv .venv
    }
    if($LASTEXITCODE -ne 0){throw 'Python 3.12 x64 is required'}
}
$python=Join-Path $projectRoot '.venv/Scripts/python.exe'
if(-not (Test-Path -LiteralPath 'wheels')){throw 'Offline wheels directory missing'}
& $python -m pip install --no-index --find-links wheels --requirement backend/requirements.lock --disable-pip-version-check
if($LASTEXITCODE -ne 0){throw 'Offline dependency installation failed'}
New-Item -ItemType Directory -Path '.runtime','logs','evidence/m3' -Force | Out-Null
if(-not (Test-Path -LiteralPath '.env')){
    throw 'Create private .env from config/server.env.example with this server SQL connection and a new session secret. Then rerun setup.'
}
& $python -m alembic -c backend/alembic.ini upgrade head
if($LASTEXITCODE -ne 0){throw 'Database migration failed'}
Write-Output 'Offline setup complete. Run scripts/start_backend.ps1; open http://localhost:8000'
