$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
& "$projectRoot/.venv/Scripts/python.exe" "$PSScriptRoot/run_service.py" --stop
if($LASTEXITCODE -ne 0){throw 'Native supervisor has not stopped; refusing a second backend'}
$pidFile=Join-Path $projectRoot '.runtime\processes.json'
if(Test-Path -LiteralPath $pidFile){
    $processMap=Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json -AsHashtable
    if($processMap.ContainsKey('backend')){
        $ownedBackend=Get-Process -Id $processMap['backend'] -ErrorAction SilentlyContinue
        $expectedPath=Join-Path $projectRoot '.venv\Scripts\python.exe'
        if($ownedBackend){
            if($ownedBackend.Path -ne $expectedPath){throw 'Stored PID does not match this project backend'}
            Stop-Process -Id $ownedBackend.Id
        }
        $processMap.Remove('backend')
        $processMap | ConvertTo-Json | Set-Content -LiteralPath $pidFile -Encoding utf8
    }
}
& "$PSScriptRoot\start_local.ps1"
