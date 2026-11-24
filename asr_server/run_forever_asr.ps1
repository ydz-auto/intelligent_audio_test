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

function Write-Log([string]$Message) {
  $line = '{0} {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
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
    # Let the child inherit this console so uvicorn / business logs and crash
    # tracebacks stream straight into the window.
    Write-Log "starting $Python $Entry"
    $proc = Start-Process -FilePath $Python -ArgumentList @($Entry) `
      -WorkingDirectory $WorkDir -NoNewWindow -PassThru
    $proc.WaitForExit()
    $rc = $proc.ExitCode
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
