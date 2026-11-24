# Host service supervisor: keep e2e / audio / device alive.
# Same pattern as asr_server/ssh_tunnel_asr.ps1: infinite loop, restart 5s after exit.
# Stopped by control.py: it writes StopFlag, kills this process tree, then clears the flag.
# NOTE: keep this file ASCII-only (Windows PowerShell 5.1 reads non-BOM .ps1 as ANSI).
param(
  [Parameter(Mandatory=$true)][string]$Tag,
  [Parameter(Mandatory=$true)][string]$Python,
  [Parameter(Mandatory=$true)][string]$Entry,
  [Parameter(Mandatory=$true)][string]$Mode,
  [Parameter(Mandatory=$true)][string]$EnvFile,
  [Parameter(Mandatory=$true)][string]$Log,
  [Parameter(Mandatory=$true)][string]$StopFlag,
  [Parameter(Mandatory=$true)][string]$PidFile
)

$ErrorActionPreference = 'Continue'

function Write-Log([string]$Message) {
  $line = '{0} [{1}] {2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Tag, $Message
  $line | Out-File -Append -Encoding utf8 $Log
}

Set-Content -Path $PidFile -Value $PID -Encoding ascii
Write-Log "supervisor started pid=$PID"

while ($true) {
  if (Test-Path $StopFlag) {
    Write-Log 'stop flag present, exit'
    break
  }
  if ((Test-Path $Log) -and ((Get-Item $Log).Length -gt 5MB)) {
    Move-Item -Force $Log "$Log.1"
  }
  Write-Log "starting: $Python $Entry --service $Tag --mode $Mode"
  # pythonw.exe is a GUI-subsystem app: "&" returns immediately and leaves $LASTEXITCODE
  # unset. Use Start-Process -Wait so the loop actually tracks the child's lifetime.
  $procArgs = @(
    "`"$Entry`"",
    '--service', $Tag,
    '--mode', $Mode,
    '--env-file', "`"$EnvFile`""
  )
  $proc = Start-Process -FilePath $Python -ArgumentList $procArgs -Wait -PassThru -NoNewWindow
  $code = $proc.ExitCode
  if (Test-Path $StopFlag) {
    Write-Log "exited rc=$code (stop requested), exit"
    break
  }
  Write-Log "exited rc=$code, restart in 5s"
  Start-Sleep -Seconds 5
}

Remove-Item -Path $PidFile -ErrorAction SilentlyContinue
