# Logon autostart for host services (e2e / audio / device).
# Flow: start SSH tunnel -> wait for DB(5433) and Redis(6379) -> stack.py up --no-docker.
# Keep this file ASCII-only (Windows PowerShell 5.1 reads non-BOM .ps1 as ANSI).
# Manual stop is respected: this runs once per logon, there is no periodic watchdog.
$ErrorActionPreference = 'Continue'

$Repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$LogDir = Join-Path $Repo 'logs\host_services'
$Log = Join-Path $LogDir 'autostart.log'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-Log([string]$Message) {
  $line = '{0} {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
  $line | Out-File -Append -Encoding utf8 $Log
}

function Test-Port([int]$Port, [int]$TimeoutMs = 1000) {
  $client = New-Object System.Net.Sockets.TcpClient
  try {
    $task = $client.ConnectAsync('127.0.0.1', $Port)
    return ($task.Wait($TimeoutMs) -and $client.Connected)
  } catch {
    return $false
  } finally {
    $client.Close()
  }
}

function Resolve-HostPython {
  if ($env:HOST_SERVICE_PYTHON -and (Test-Path $env:HOST_SERVICE_PYTHON)) {
    return $env:HOST_SERVICE_PYTHON
  }
  $envFile = Join-Path $Repo '.env'
  if (Test-Path $envFile) {
    $line = Get-Content $envFile |
      Where-Object { $_ -match '^\s*HOST_SERVICE_PYTHON\s*=' } |
      Select-Object -First 1
    if ($line) {
      $value = ($line -split '=', 2)[1].Trim().Trim('"').Trim("'")
      if ($value -and (Test-Path $value)) { return $value }
    }
  }
  $default = 'D:\00_env\conda_envs\intelligent_audio_test\python.exe'
  if (Test-Path $default) { return $default }
  $cmd = Get-Command python -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  return $null
}

Write-Log '=== logon autostart begin ==='

# 1) SSH tunnel (idempotent: ssh_tunnels.ps1 start skips when already up)
$tunnel = Join-Path $Repo 'ssh_tunnels.ps1'
if (Test-Path $tunnel) {
  & powershell -NoProfile -ExecutionPolicy Bypass -File $tunnel start | Out-Null
  Write-Log "tunnel start requested (rc=$LASTEXITCODE)"
} else {
  Write-Log "WARN tunnel script missing: $tunnel"
}

# 2) Wait for forwarded DB / Redis ports (local 5433 / 6379 from ssh_tunnels.ps1)
$deadline = (Get-Date).AddSeconds(180)
while ((Get-Date) -lt $deadline) {
  if ((Test-Port 5433) -and (Test-Port 6379)) { break }
  Start-Sleep -Seconds 3
}
$dbUp = Test-Port 5433
$redisUp = Test-Port 6379
Write-Log "dependency ports: 5433=$dbUp 6379=$redisUp"

# 3) Start host services (real audio mode)
$python = Resolve-HostPython
if (-not $python) {
  Write-Log 'ERROR no python interpreter found, abort'
  exit 1
}
Write-Log "python: $python"
Set-Location $Repo
& $python (Join-Path $Repo 'stack.py') up --no-docker --audio-mode real 2>&1 |
  Out-File -Append -Encoding utf8 $Log
Write-Log "=== logon autostart done rc=$LASTEXITCODE ==="
