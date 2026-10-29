param([switch]$Remove,[switch]$WithDailyBackup)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
$hasher=[System.Security.Cryptography.SHA256]::Create()
try{$hash=$hasher.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($projectRoot.ToLowerInvariant()))}finally{$hasher.Dispose()}
$taskName='ChamCongLocal-'+[BitConverter]::ToString($hash).Replace('-','').Substring(0,12).ToLowerInvariant()
$runner=Join-Path $projectRoot 'scripts/run_service.py'
$existing=Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if($existing -and -not (($existing.Actions.Arguments -join ' ') -like ('*'+$runner+'*'))){
    throw 'Task name is owned by another command; refusing to replace it'
}
if($Remove){
    if($existing){Unregister-ScheduledTask -TaskName $taskName -Confirm:$false}
    $backupExisting=Get-ScheduledTask -TaskName ($taskName+'-Backup') -ErrorAction SilentlyContinue
    $backupRunner=Join-Path $projectRoot 'scripts/backup_local.py'
    if($backupExisting){
        if(-not (($backupExisting.Actions.Arguments -join ' ') -like ('*'+$backupRunner+'*'))){throw 'Backup task is not owned by this project'}
        Unregister-ScheduledTask -TaskName ($taskName+'-Backup') -Confirm:$false
    }
    Write-Output 'Project autostart removed; current server is not stopped'
    exit 0
}
$python=Join-Path $projectRoot '.venv/Scripts/pythonw.exe'
if(-not (Test-Path -LiteralPath $python)){throw 'Project Python venv is missing'}
$user=[System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action=New-ScheduledTaskAction -Execute $python -Argument ('"'+$runner+'"') -WorkingDirectory $projectRoot
$trigger=New-ScheduledTaskTrigger -AtLogOn -User $user
$principal=New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$settings=New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
if(-not $existing){
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Local attendance native supervisor; no credentials embedded' | Out-Null
}
$check=Get-ScheduledTask -TaskName $taskName
if($check.Actions.Execute -ne $python -or $check.Principal.LogonType -ne 'Interactive'){throw 'Autostart registration mismatch'}
New-Item -ItemType Directory -Path (Join-Path $projectRoot '.runtime/service') -Force | Out-Null
$record=@{task_name=$taskName;trigger='current_user_logon';installed_at=[DateTime]::UtcNow.ToString('o')}
if($WithDailyBackup){
    $backupRunner=Join-Path $projectRoot 'scripts/backup_local.py'
    $backupName=$taskName+'-Backup'
    $backupExisting=Get-ScheduledTask -TaskName $backupName -ErrorAction SilentlyContinue
    if($backupExisting -and -not (($backupExisting.Actions.Arguments -join ' ') -like ('*'+$backupRunner+'*'))){throw 'Backup task name belongs to another command'}
    $backupAction=New-ScheduledTaskAction -Execute $python -Argument ('"'+$backupRunner+'" create') -WorkingDirectory $projectRoot
    $backupTrigger=New-ScheduledTaskTrigger -Daily -At '03:00'
    $backupSettings=New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 5) -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
    Register-ScheduledTask -TaskName $backupName -Action $backupAction -Trigger $backupTrigger -Principal $principal -Settings $backupSettings -Description 'Local encrypted attendance backup; no credentials embedded' -Force | Out-Null
    $record.backup_task_name=$backupName
    $record.backup_schedule='03:00 local time; current user logged on; catch up when available'
}
$record | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $projectRoot '.runtime/service/autostart.json') -Encoding utf8
Write-Output 'Native backend autostart registered for current Windows user logon; no password stored'
