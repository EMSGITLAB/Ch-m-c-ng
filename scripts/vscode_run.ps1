param([switch]$Restart,[switch]$OpenBrowser)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
$python=Join-Path $projectRoot '.venv/Scripts/python.exe'
if($Restart){
    & $python (Join-Path $PSScriptRoot 'run_service.py') --stop
    if($LASTEXITCODE -ne 0){throw 'Project service has not stopped; refusing a duplicate server'}
}
& (Join-Path $PSScriptRoot 'start_service.ps1')
if($LASTEXITCODE -ne 0){throw 'Project service could not start'}
$deadline=[DateTime]::UtcNow.AddSeconds(120)
$ready=$false
while([DateTime]::UtcNow -lt $deadline){
    try{
        $response=Invoke-WebRequest -Uri 'http://localhost:8000/health/live' -UseBasicParsing -TimeoutSec 3
        if($response.StatusCode -eq 200){$ready=$true;break}
    }catch{Start-Sleep -Milliseconds 500}
}
if(-not $ready){throw 'Backend did not become available; inspect .runtime/service/service.log'}
Write-Output 'Webapp ready: http://localhost:8000'
if($OpenBrowser){Start-Process 'http://localhost:8000'}
