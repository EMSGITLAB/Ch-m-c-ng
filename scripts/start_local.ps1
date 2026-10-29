$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
New-Item -ItemType Directory -Path "$projectRoot\logs" -Force | Out-Null
$envPath=Join-Path $projectRoot '.env'
if(-not (Test-Path -LiteralPath $envPath) -or -not (Select-String -LiteralPath $envPath -Pattern '^CHAMCONG_DATABASE_URL=' -Quiet)){
    & "$projectRoot\.venv\Scripts\python.exe" "$PSScriptRoot\start_sqlserver.py"
    if($LASTEXITCODE -ne 0){throw 'Database startup failed'}
}
$ownedProcesses=@{}
$pidFile="$projectRoot\.runtime\processes.json"
if(Test-Path -LiteralPath $pidFile){$ownedProcesses=Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json -AsHashtable}
function Start-OwnedProcess($key,$executable,$processArguments){
    if($ownedProcesses.ContainsKey($key) -and (Get-Process -Id $ownedProcesses[$key] -ErrorAction SilentlyContinue)){return}
    $process=Start-Process -FilePath $executable -ArgumentList $processArguments -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput "$projectRoot\logs\$key.out.log" -RedirectStandardError "$projectRoot\logs\$key.err.log" -PassThru
    $ownedProcesses[$key]=$process.Id
}
$python=Join-Path $projectRoot '.venv/Scripts/python.exe'
# Transition the old direct backend to the owned native supervisor.
if($ownedProcesses.ContainsKey('backend')){
    $legacy=Get-Process -Id $ownedProcesses['backend'] -ErrorAction SilentlyContinue
    if($legacy){
        if($legacy.Path -ne $python){throw 'Stored backend PID does not belong to this project venv'}
        Stop-Process -Id $legacy.Id
        $legacy.WaitForExit(5000) | Out-Null
    }
    $ownedProcesses.Remove('backend')
}
& "$PSScriptRoot\start_service.ps1"
if($LASTEXITCODE -ne 0){throw 'Native supervisor startup failed'}
$node=Get-Command node.exe -ErrorAction SilentlyContinue
if($node -and (Test-Path -LiteralPath "$projectRoot/frontend/node_modules/vite/bin/vite.js")){
    Start-OwnedProcess 'preview' $node.Source @('frontend/node_modules/vite/bin/vite.js','--config','frontend/vite.config.ts','--host','127.0.0.1','frontend')
}
$ownedProcesses | ConvertTo-Json | Set-Content -LiteralPath $pidFile -Encoding utf8
Write-Output 'Local webapp http://localhost:8000 ; development preview http://localhost:5173 when Node is available'
