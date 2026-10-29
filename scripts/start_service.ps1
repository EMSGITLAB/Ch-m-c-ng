$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
$python=Join-Path $projectRoot '.venv/Scripts/python.exe'
$runner=Join-Path $projectRoot 'scripts/run_service.py'
$status=& $python $runner --status | ConvertFrom-Json
if($status.running){Write-Output 'Native supervisor already running';exit 0}
$arguments='"'+$runner+'"'
$process=Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru
Start-Sleep -Milliseconds 700
$status=& $python $runner --status | ConvertFrom-Json
if(-not $status.running){throw 'Supervisor did not start. Check .runtime/service/service.log; port 8000 may already be in use.'}
Write-Output 'Native supervisor running; webapp http://localhost:8000'
