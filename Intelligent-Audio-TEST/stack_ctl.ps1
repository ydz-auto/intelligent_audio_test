# INT-125 standard full-stack start/stop entry point.
# The stack MUST NOT be started directly inside an agent run: the platform reaps
# the run's whole process tree when the run exits (the 2026-10-10 21:41 and 23:12
# outages were both caused by run_all running attached to an agent run).
# This script starts run_all.py via WMI Win32_Process.Create so the stack's
# parent is WmiPrvSE (a system service, outside every run's job object and
# process tree) - the stack therefore survives run exit.
#
# Start:  powershell -NoProfile -ExecutionPolicy Bypass -File stack_ctl.ps1 start
# Stop:   powershell -NoProfile -ExecutionPolicy Bypass -File stack_ctl.ps1 stop
# Status: powershell -NoProfile -ExecutionPolicy Bypass -File stack_ctl.ps1 status
param([Parameter(Mandatory=$true)][ValidateSet('start','stop','status')][string]$Action)

$repo    = 'D:\00_code\V9.7.31\Intelligent-Audio-TEST'
$payload = Join-Path $repo '_stack_start.cmd'
$pidFile = Join-Path $repo '_stack.pid'
$logFile = Join-Path $repo 'logs\_run_all_stack.log'

function Get-LiveStackPid {
    if (-not (Test-Path $pidFile)) { return $null }
    $p = (Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if (-not $p) { return $null }
    $proc = Get-Process -Id ([int]$p) -ErrorAction SilentlyContinue
    if ($proc) { return [int]$p } else { return $null }
}

switch ($Action) {
    'start' {
        $alive = Get-LiveStackPid
        if ($alive) {
            Write-Output "[SKIP] stack already running (pid $alive). Refusing to double-start."
            exit 1
        }
        $r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
            CommandLine      = "cmd.exe /c `"$payload`""
            CurrentDirectory = $repo
        }
        if ($r.ReturnValue -ne 0) {
            Write-Output "[FAIL] WMI Win32_Process.Create returned $($r.ReturnValue)"
            exit 1
        }
        Set-Content -Path $pidFile -Value $r.ProcessId -Encoding ASCII
        Write-Output "[OK] stack launched detached: pid $($r.ProcessId) (parent WmiPrvSE, outside any agent run)."
        Write-Output "     pid file: _stack.pid | log: logs\_run_all_stack.log"
    }
    'stop' {
        $alive = Get-LiveStackPid
        if (-not $alive) {
            Write-Output "[INFO] no live stack pid recorded - nothing to stop."
            exit 0
        }
        & taskkill /F /T /PID $alive
        Remove-Item $pidFile -ErrorAction SilentlyContinue
        Write-Output "[OK] stack stopped (killed tree from pid $alive)."
    }
    'status' {
        $alive = Get-LiveStackPid
        if ($alive) { Write-Output "[RUNNING] stack cmd pid $alive" }
        else        { Write-Output "[DOWN] no live stack pid" }
    }
}
