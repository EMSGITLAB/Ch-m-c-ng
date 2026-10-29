param(
    [switch]$Apply,
    [switch]$Remove,
    [ValidatePattern('^SQLTELEMETRY(\$[A-Za-z0-9_]+)?$')]
    [string]$ServiceName='SQLTELEMETRY'
)
$ErrorActionPreference='Stop'
if($Apply -and $Remove){throw 'Choose Apply or Remove'}
$projectRoot=Split-Path -Parent $PSScriptRoot
$prefix='SQLTELEMETRY'
$ruleName='ChamCongLocal-Block-'+($ServiceName -replace '[^A-Za-z0-9_-]','_')+'-Egress-v1'
$ruleGroup='ChamCongLocal-SqlTelemetry'
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$principal=New-Object Security.Principal.WindowsPrincipal($identity)
$isAdministrator=$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if(($Apply -or $Remove) -and -not $isAdministrator){
    throw 'Windows Administrator rights are required to change firewall rules. No service or network setting was changed.'
}
$service=Get-CimInstance Win32_Service -Filter "Name='$ServiceName'"
if(-not $service){throw 'The specified SQL CEIP service is not installed'}
if($service.PathName -notmatch '^\s*"(?<executable>[^"]+)"(?:\s|$)'){
    throw 'Cannot safely identify the installed CEIP executable'
}
$executable=(Resolve-Path -LiteralPath $Matches.executable).Path
if([IO.Path]::GetFileName($executable) -ine 'sqlceip.exe'){throw 'Refusing to target a non-CEIP executable'}
$existing=Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
if($existing -and $existing.Group -ne $ruleGroup){throw 'Firewall rule name is owned by a different configuration'}
if($Remove){
    if($existing){$existing | Remove-NetFirewallRule}
} elseif($Apply){
    $parameters=@{Name=$ruleName;DisplayName="ChamCong local - block $ServiceName egress";
        Description='Block outbound reporting by the SQL CEIP service only; leave database service running.';
        Group=$ruleGroup;Direction='Outbound';Action='Block';Profile='Any';Enabled='True';
        Program=$executable;Service=$ServiceName}
    if($existing){
        $updates=$parameters.Clone()
        $updates.Remove('Name');$updates.Remove('DisplayName');$updates.Remove('Group')
        $updates.NewDisplayName=$parameters.DisplayName
        $existing | Set-NetFirewallRule @updates | Out-Null
    }else{New-NetFirewallRule @parameters | Out-Null}
}
$active=Get-NetFirewallRule -PolicyStore ActiveStore -Name $ruleName -ErrorAction SilentlyContinue
$profiles=@(Get-NetFirewallProfile -PolicyStore ActiveStore)
$programFilter=if($active){$active | Get-NetFirewallApplicationFilter}else{$null}
$serviceFilter=if($active){$active | Get-NetFirewallServiceFilter}else{$null}
$profileProtection=($profiles.Count -eq 3 -and @($profiles | Where-Object {-not $_.Enabled}).Count -eq 0)
$effective=([bool]$active -and $active.Enabled -eq 'True' -and $active.Action -eq 'Block' -and $active.Profile -eq 'Any' -and
    $active.Direction -eq 'Outbound' -and $programFilter.Program -ieq $executable -and
    $serviceFilter.Service -eq $ServiceName -and $profileProtection)
$suffix=$ServiceName.Substring($prefix.Length)
$databaseServiceName=if($suffix){'MSSQL'+$suffix}else{'MSSQLSERVER'}
$databaseService=Get-Service -Name $databaseServiceName -ErrorAction SilentlyContinue
$report=[ordered]@{checked_at_utc=[DateTime]::UtcNow.ToString('o');service=$ServiceName;
    telemetry_service_state=$service.State;administrator=$isAdministrator;
    rule_exists=[bool]$active;all_firewall_profiles_enabled=$profileProtection;
    effective_outbound_block=$effective;service_disabled_or_removed=$false;
    database_service_status=if($databaseService){[string]$databaseService.Status}else{'not_found'};
    applied=[bool]$Apply;removed=[bool]$Remove;machine_wan_disconnected=$false}
$directory=Join-Path $projectRoot '.runtime/network'
New-Item -ItemType Directory -Path $directory -Force | Out-Null
$report | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $directory 'sql-telemetry-egress.json') -Encoding utf8
$report | ConvertTo-Json -Compress
if($Apply -and -not $effective){throw 'The rule was requested but active firewall protection is not fully verified'}
