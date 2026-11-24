# Supervisor for the ASR service: restart the child 5s after it exits.
# Same loop shape as scripts/host_services/run_forever.ps1.
# Keep this file ASCII-only (Windows PowerShell 5.1 reads non-BOM .ps1 as ANSI).
param(
  [Parameter(Mandatory = $true)][string]$Python,
  [Parameter(Mandatory = $true)][string]$Entry,
  [Parameter(Mandatory = $true)][string]$LogPath,
  [Parameter(Mandatory = $true)][string]$StopFlag,
  [Parameter(Mandatory = $true)][string]$PidFile,
  [string]$EnvFile = ''
)
$ErrorActionPreference = 'Continue'
$WorkDir = Split-Path -Parent $Entry
$ChildLog = Join-Path (Split-Path -Parent $LogPath) 'asr_server.stdout.log'

# Decode the child's UTF-8 output correctly (python runs with PYTHONUTF8=1).
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# pythonw.exe is a GUI-subsystem binary: sys.stdout and sys.stderr are None, so
# uvicorn aborts during startup with exit code 1 and no traceback. Always use the
# console python.exe from the same folder.
if ((Split-Path -Leaf $Python) -ieq 'pythonw.exe') {
  $consolePy = Join-Path (Split-Path -Parent $Python) 'python.exe'
  if (Test-Path $consolePy) { $Python = $consolePy }
}
# Window title so the taskbar entry is identifiable (no-op when hidden).
try { $Host.UI.RawUI.WindowTitle = 'IAT ASR' } catch { }

# WMI-created processes get the provider's minimal environment, so the caller
# dumps its full environment to JSON and we apply it here before spawning.
if ($EnvFile -and (Test-Path $EnvFile)) {
  $cfg = Get-Content -Raw -Encoding utf8 $EnvFile | ConvertFrom-Json
  foreach ($p in $cfg.PSObject.Properties) {
    Set-Item -Path ("Env:" + $p.Name) -Value ([string]$p.Value)
  }
}

# Daily log files: keep writing <name>.log, and when the date changes rename the
# previous content to <name>.log.YYYY-MM-DD so each day has its own file.
$script:logDay = (Get-Date).Date

function Switch-DailyLog([string]$Path, [datetime]$PrevDay) {
  if (-not (Test-Path $Path)) { return }
  $target = '{0}.{1}' -f $Path, $PrevDay.ToString('yyyy-MM-dd')
  try {
    if (Test-Path $target) {
      # Already archived today (restart within the same day): merge, do not lose.
      Get-Content -Raw -Encoding utf8 $Path | Out-File -Append -Encoding utf8 $target
      Remove-Item $Path -Force
    } else {
      Move-Item -Path $Path -Destination $target -Force
    }
  } catch { }
}

function Roll-DailyLogs {
  Switch-DailyLog $LogPath $script:logDay
  Switch-DailyLog $ChildLog $script:logDay
  $script:logDay = (Get-Date).Date
}

function Write-Log([string]$Message) {
  $now = Get-Date
  if ($now.Date -ne $script:logDay) { Roll-DailyLogs }
  $line = '{0} {1}' -f $now.ToString('yyyy-MM-dd HH:mm:ss'), $Message
  $line | Out-File -Append -Encoding utf8 $LogPath
  Write-Host $line
}

if (Test-Path $StopFlag) { Remove-Item $StopFlag -Force }
$PID | Out-File -Encoding ascii $PidFile
Write-Log "supervisor start pid=$PID python=$Python entry=$Entry"

while ($true) {
  if (Test-Path $StopFlag) { Write-Log 'stop flag found, exit'; break }
  $started = Get-Date
  try {
    Write-Log "starting $Python $Entry"
    # Tee the child output: it streams into this window and is appended to
    # asr_server.stdout.log on disk (uvicorn access lines, print(), tracebacks).
    Push-Location $WorkDir
    $env:PYTHONUNBUFFERED = '1'
    & $Python $Entry 2>&1 | ForEach-Object {
      $now = Get-Date
      if ($now.Date -ne $script:logDay) { Roll-DailyLogs }
      $line = [string]$_
      Write-Host $line
      $line | Out-File -Append -Encoding utf8 $ChildLog
    }
    $rc = $LASTEXITCODE
    Pop-Location
  } catch {
    $rc = -1
    Write-Log "spawn failed: $($_.Exception.Message)"
  }
  $elapsed = [int]((Get-Date) - $started).TotalSeconds
  Write-Log "child exited rc=$rc uptime=${elapsed}s"
  if (Test-Path $StopFlag) { Write-Log 'stop flag found, exit'; break }
  Write-Log 'restart in 5s'
  Start-Sleep -Seconds 5
}

Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
Write-Log "supervisor exit pid=$PID"
