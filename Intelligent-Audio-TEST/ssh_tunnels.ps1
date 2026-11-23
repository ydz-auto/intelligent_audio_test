# SSH tunnels: local <-> server (106.54.49.79 / ubuntu)
#
# Forward -L (local 127.0.0.1 -> server):
#   5433 -> 127.0.0.1:5432    PostgreSQL
#   6379 -> 127.0.0.1:6379    Redis
#   53061/53067/53068/53069/53091 -> server gRPC
#
# Reverse -R (server 10.0.0.9 -> local):
#   10.0.0.9:50051 -> 127.0.0.1:50051  e2e gRPC
#   10.0.0.9:50052 -> 127.0.0.1:50052  audio
#   10.0.0.9:50053 -> 127.0.0.1:50053  device
#
# NOTE: keep this file ASCII-only (Windows PowerShell 5.1 reads .ps1 as ANSI).
#
# Usage:
#   pwsh -File ssh_tunnels.ps1 start
#   pwsh -File ssh_tunnels.ps1 stop
#   pwsh -File ssh_tunnels.ps1 status
param([Parameter(Mandatory=$true)][ValidateSet('start','stop','status')][string]$Action)

$SshHost = '106.54.49.79'
$SshUser = 'ubuntu'
$ReverseBind = '10.0.0.9'   # server LAN IP (GatewayPorts clientspecified enabled)

$Forwards = @(
    '-L', '5433:127.0.0.1:5432',
    '-L', '6379:127.0.0.1:6379',
    '-L', '53061:127.0.0.1:53061',
    '-L', '53067:127.0.0.1:53067',
    '-L', '53068:127.0.0.1:53068',
    '-L', '53069:127.0.0.1:53069',
    '-L', '53091:127.0.0.1:53091'
)
$Reverses = @(
    '-R', "${ReverseBind}:50051:127.0.0.1:50051",
    '-R', "${ReverseBind}:50052:127.0.0.1:50052",
    '-R', "${ReverseBind}:50053:127.0.0.1:50053"
)

$ProbePorts = @(5433, 6379, 53061)

function Test-TunnelUp {
    foreach ($p in $ProbePorts) {
        $t = Test-NetConnection -ComputerName 127.0.0.1 -Port $p -WarningAction SilentlyContinue -InformationLevel Quiet
        if ($t) { return $true }
    }
    return $false
}

function Start-Tunnel {
    if (Test-TunnelUp) {
        Write-Host '[tunnel] already running'
        return
    }
    $sshArgs = @('-N', '-T',
        '-o', 'ServerAliveInterval=30',
        '-o', 'ServerAliveCountMax=3',
        '-o', 'ExitOnForwardFailure=yes',
        '-o', 'ConnectTimeout=15') + $Forwards + $Reverses + @("${SshUser}@${SshHost}")
    $argStr = $sshArgs -join ' '
    $log = Join-Path $PSScriptRoot 'logs\ssh_tunnels.log'
    $errLog = Join-Path $PSScriptRoot 'logs\ssh_tunnels.err.log'
    New-Item -ItemType Directory -Force (Split-Path $log) | Out-Null
    $p = Start-Process ssh -ArgumentList $argStr -WindowStyle Hidden `
        -RedirectStandardOutput $log -RedirectStandardError $errLog -PassThru
    Start-Sleep -Seconds 6
    if (Test-TunnelUp) {
        Write-Host "[tunnel] started pid=$($p.Id)"
    } else {
        Write-Host '[tunnel] local ports not open yet, log: ' $errLog
        Get-Content $errLog -Tail 10 -ErrorAction SilentlyContinue
    }
}

function Stop-Tunnel {
    Get-CimInstance Win32_Process -Filter "Name='ssh.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match '106\.54\.49\.79' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Write-Host '[tunnel] stopped'
}

function Show-Status {
    foreach ($p in $ProbePorts) {
        $t = Test-NetConnection -ComputerName 127.0.0.1 -Port $p -WarningAction SilentlyContinue -InformationLevel Quiet
        $state = if ($t) { 'OPEN' } else { 'closed' }
        Write-Host ("  127.0.0.1:{0}  {1}" -f $p, $state)
    }
    Get-CimInstance Win32_Process -Filter "Name='ssh.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match '106\.54\.49\.79' } |
        Select-Object ProcessId, @{n='cmd'; e={$_.CommandLine.Substring(0, [Math]::Min(80, $_.CommandLine.Length))}} | Format-Table -AutoSize
}

switch ($Action) {
    'start'  { Start-Tunnel }
    'stop'   { Stop-Tunnel }
    'status' { Show-Status }
}
