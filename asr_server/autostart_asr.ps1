# Logon autostart for the ASR service and its reverse tunnel.
# Install with: python asr_server/asr_control.py install-autostart
# Keep this file ASCII-only (Windows PowerShell 5.1 reads non-BOM .ps1 as ANSI).
$ErrorActionPreference = 'Continue'
$Root = $PSScriptRoot
$LogDir = Join-Path $Root 'logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir 'autostart_asr.log'

function Write-Log([string]$Message) {
  $line = '{0} {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
  $line | Out-File -Append -Encoding utf8 $Log
}

function Resolve-AsrPython {
  if ($env:ASR_PYTHON -and (Test-Path $env:ASR_PYTHON)) { return $env:ASR_PYTHON }
  $envFile = Join-Path (Split-Path -Parent $Root) '.env'
  if (Test-Path $envFile) {
    $line = Get-Content $envFile |
      Where-Object { $_ -match '^\s*ASR_PYTHON\s*=' } |
      Select-Object -First 1
    if ($line) {
      $value = ($line -split '=', 2)[1].Trim().Trim('"').Trim("'")
      if ($value -and (Test-Path $value)) { return $value }
    }
  }
  $cmd = Get-Command python -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  return $null
}

Write-Log '=== logon autostart begin ==='
$python = Resolve-AsrPython
if (-not $python) {
  Write-Log 'ERROR no python interpreter found (set ASR_PYTHON), abort'
  exit 1
}
Write-Log "python: $python"
# control 内部据此选择守护子进程的解释器（不能用运行 control 的 Python 去猜）
$env:ASR_PYTHON = $python
& $python (Join-Path $Root 'asr_control.py') start --with-tunnel 2>&1 |
  Out-File -Append -Encoding utf8 $Log
Write-Log "=== logon autostart done rc=$LASTEXITCODE ==="
