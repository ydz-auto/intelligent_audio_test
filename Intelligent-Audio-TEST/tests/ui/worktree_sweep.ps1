# requires -version 5.1
# INT-522 Multica worktree residual sweep.
#
# Background: Multica task worktrees under the two workspace roots are torn down
# after a run finalizes, but `frontend/node_modules` is a junction into the main
# repo (D:\00_code\V9.7.31\Intelligent-Audio-TEST\frontend\node_modules), and on
# Windows a recursive rmdir over a junction returns success while leaving the
# worktree directory behind. This has caused several batches of leftovers
# (INT-501 -> INT-519 -> INT-520 -> INT-522).
#
# The bug signature is an *unregistered* physical leftover: `git worktree remove`
# succeeded (the worktree was removed from `git worktree list`) but the physical
# task directory remained on disk. So this sweep ONLY deletes dirs whose worktree
# subdirectory is NOT registered with git. Registered worktrees are legitimate
# (active runs, locked, or awaiting teardown) and are always skipped.
#
# Cross-checks before deleting an unregistered candidate:
#   (a) active runs via the multica CLI (per issue family),
#   (b) `.task_lock` lock state (daemon holds it on in-flight runs),
#   (c) `.gc_meta` presence (daemon GC in progress),
#   (d) git worktree registration (must be absent).
# Junction links (frontend/node_modules -> main repo) are removed first, and the
# main repo node_modules integrity is verified before/after.
#
# Canonical source: repo `tests/ui/worktree_sweep.ps1`.
# Installed copy  : `C:\Users\public.DESKTOP-3SNNDSS\docker-watchdog\worktree-sweep.ps1`
# Scheduled task  : `MulticaWorktreeSweep` (see INT-522 comment for registration).
#
# Usage:
#   pwsh -NoProfile -File worktree_sweep.ps1            # dry-run (report only)
#   pwsh -NoProfile -File worktree_sweep.ps1 -Apply     # actually delete

param(
    [switch]$Apply,          # actually delete; default is a dry-run report
    [switch]$VerboseOutput,  # print per-dir decisions to stdout as well as log
    [int]$MinAgeMinutes = 60 # skip dirs newer than this (avoid racing a just-created workdir)
)

$ErrorActionPreference = 'Continue'

# Multica CLI emits UTF-8 JSON; force PowerShell to decode child stdout as UTF-8
# so issue titles with CJK characters do not corrupt the JSON parse.
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$LogDir   = 'C:\Users\public.DESKTOP-3SNNDSS\docker-watchdog\logs'
$Multica  = 'C:\Users\public.DESKTOP-3SNNDSS\.multica\bin\multica.exe'
$GitExe   = 'D:\00_env\PortableGit\cmd\git.exe'
$MainRepo = 'D:\00_code\V9.7.31'
$MainNodeModules = 'D:\00_code\V9.7.31\Intelligent-Audio-TEST\frontend\node_modules'

# Both workspace roots (desktop-api workspace plus the plain workspace).
$Roots = @(
    'C:\Users\public.DESKTOP-3SNNDSS\multica_workspaces\intelligent-95ba6a12369f',
    'C:\Users\public.DESKTOP-3SNNDSS\multica_workspaces_desktop-api.multica.ai\intelligent-95ba6a12369f'
)

$CycleStamp = Get-Date -Format 'yyyyMMdd'
$LogFile    = Join-Path $LogDir "sweep-$CycleStamp.log"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null }

function Write-Log {
    param([string]$Level, [string]$Message)
    $line = "{0} [sweep pid={1}] [{2}] {3}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss.fff'), $PID, $Level, $Message
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
    if ($VerboseOutput) { Write-Host "[$Level] $Message" }
}

$script:activeCache = @{}
function Get-ActiveTaskIds {
    # Query active runs for an issue family and return the set of active task_ids.
    # Returns $null on failure so callers can SKIP (fail-safe). Cached per issue_id.
    #
    # The CLI emits UTF-8 JSON whose issue titles contain CJK. PowerShell's native
    # pipeline decodes child stdout with the console codepage, which corrupts the
    # JSON. So we capture raw bytes through cmd.exe redirection to a temp file and
    # read it back as UTF-8 explicitly.
    param([string]$IssueId)
    if ($script:activeCache.ContainsKey($IssueId)) { return $script:activeCache[$IssueId] }
    $ids = $null
    $tmpFile = Join-Path $env:TEMP ("sweep_active_{0}.json" -f [guid]::NewGuid().ToString('N'))
    try {
        & cmd.exe /c "`"$Multica`" issue runs $IssueId --active --siblings --output json > `"$tmpFile`" 2>nul"
        if (Test-Path -LiteralPath $tmpFile) {
            $raw = [System.IO.File]::ReadAllText($tmpFile, [System.Text.Encoding]::UTF8)
            $parsed = $raw | ConvertFrom-Json
            $ids = @($parsed | ForEach-Object { $_.task_id })
        }
    } catch {
        Write-Log 'WARN' "active-run query failed for issue ${IssueId}: $($_.Exception.Message)"
        $ids = $null
    } finally {
        if (Test-Path -LiteralPath $tmpFile) { Remove-Item -LiteralPath $tmpFile -Force -ErrorAction SilentlyContinue }
    }
    $script:activeCache[$IssueId] = $ids
    return $ids
}

function Test-LockedFile {
    # Try to open with exclusive access. True = another process holds it open
    # (daemon holds .task_lock on an in-flight run) -> treat as busy/locked.
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    try {
        $fs = [System.IO.File]::Open($Path, 'Open', 'ReadWrite', 'None')
        $fs.Close()
        return $false
    } catch {
        return $true
    }
}

function Get-JunctionTargets {
    # Enumerate every reparse point under a task dir WITHOUT descending into
    # junctions (a plain -Recurse would follow the node_modules junction into
    # the main repo, which is exactly what we must never do).
    param([string]$Root)
    $found = @()
    $stack = [System.Collections.Generic.Stack[string]]::new()
    $stack.Push($Root)
    while ($stack.Count -gt 0) {
        $dir = $stack.Pop()
        $children = try { [System.IO.Directory]::EnumerateFileSystemEntries($dir) } catch { @() }
        foreach ($c in $children) {
            $item = Get-Item -LiteralPath $c -Force -ErrorAction SilentlyContinue
            if (-not $item) { continue }
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                $found += [pscustomobject]@{ Path = $item.FullName; IsDirectory = [bool]($item.Attributes -band [IO.FileAttributes]::Directory) }
                continue   # never descend into a reparse point
            }
            if ($item.Attributes -band [IO.FileAttributes]::Directory) { $stack.Push($item.FullName) }
        }
    }
    return $found
}

function Remove-JunctionLink {
    # Remove ONLY the junction link (reparse point), never its target.
    # `cmd /c rmdir` on a junction deletes the link, leaving the target intact.
    param([string]$Path)
    $before = (Get-ChildItem -LiteralPath $MainNodeModules -ErrorAction SilentlyContinue | Measure-Object).Count
    & cmd.exe /c rmdir "$Path" 2>$null | Out-Null
    $ok = -not (Test-Path -LiteralPath $Path)
    $after = (Get-ChildItem -LiteralPath $MainNodeModules -ErrorAction SilentlyContinue | Measure-Object).Count
    if ($ok -and $before -eq $after) {
        Write-Log 'INFO' "junction removed: $Path (main node_modules $before -> $after, intact)"
        return $true
    }
    Write-Log 'WARN' "junction removal incomplete: $Path (main node_modules $before -> $after)"
    return $false
}

# ---- gather registered worktrees from the main repo ----
$registered = @()
try {
    $wtOut = & $GitExe -C $MainRepo worktree list 2>$null
    foreach ($line in $wtOut) {
        if ($line -match '^(\S+)') {
            # git prints forward slashes on Windows; normalize to backslash, case-insensitive
            $registered += ($Matches[1].Trim() -replace '/', '\').ToLowerInvariant()
        }
    }
} catch { Write-Log 'WARN' "git worktree list failed: $($_.Exception.Message)" }

Write-Log 'INFO' "sweep cycle start (Apply=$Apply), registered worktrees=$($registered.Count)"

$found = 0; $deleted = 0; $skipped = 0

foreach ($root in $Roots) {
    if (-not (Test-Path -LiteralPath $root)) { continue }
    $dirs = Get-ChildItem -LiteralPath $root -Directory -Force -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match '^int-\d+-[0-9a-f]{8,}$' }
    foreach ($d in $dirs) {
        $found++
        $taskDir  = $d.FullName
        $worktreeDir = Join-Path $taskDir 'worktree'
        $wtKey = $worktreeDir.ToLowerInvariant()

        # ---- 0. git registration: registered worktrees are legitimate, skip ----
        $registeredHere = $false
        foreach ($r in $registered) {
            if ($r -eq $wtKey) { $registeredHere = $true; break }
        }
        if ($registeredHere) {
            Write-Log 'INFO' "$($d.Name): registered git worktree -> skip (legitimate)"
            $skipped++; continue
        }

        # ---- 1. task owner + issue ----
        $ownerFile = Join-Path $taskDir '.task_owner'
        $envFile   = Join-Path $taskDir '.managed_env.json'
        $taskId = $null; $issueId = $null
        if (Test-Path -LiteralPath $ownerFile) {
            try { $taskId = (Get-Content -LiteralPath $ownerFile -Raw | ConvertFrom-Json).task_id } catch {}
        }
        if (Test-Path -LiteralPath $envFile) {
            try { $issueId = (Get-Content -LiteralPath $envFile -Raw | ConvertFrom-Json).issue_id } catch {}
        }

        # ---- 2. active-run cross-check (fail-safe: skip on query failure) ----
        if ($issueId -and $taskId) {
            $active = Get-ActiveTaskIds $issueId
            if ($null -eq $active) {
                Write-Log 'WARN' "$($d.Name): active-run query unavailable -> skip (fail-safe)"
                $skipped++; continue
            }
            if ($active -contains $taskId) {
                Write-Log 'INFO' "$($d.Name): task $taskId is ACTIVE -> skip"
                $skipped++; continue
            }
        } else {
            # No task_owner/managed_env: cannot prove terminal -> conservative skip.
            Write-Log 'WARN' "$($d.Name): missing .task_owner/.managed_env -> skip"
            $skipped++; continue
        }

        # ---- 3. lock / gc / age cross-check ----
        if (Test-LockedFile (Join-Path $taskDir '.task_lock')) {
            Write-Log 'INFO' "$($d.Name): .task_lock held -> skip"
            $skipped++; continue
        }
        if (Test-Path -LiteralPath (Join-Path $taskDir '.gc_meta')) {
            Write-Log 'INFO' "$($d.Name): .gc_meta present (daemon GC) -> skip"
            $skipped++; continue
        }
        $ageMinutes = [int]((Get-Date) - $d.LastWriteTime).TotalMinutes
        if ($ageMinutes -lt $MinAgeMinutes) {
            Write-Log 'INFO' "$($d.Name): only $ageMinutes min old (< $MinAgeMinutes) -> skip"
            $skipped++; continue
        }

        # ---- 4. remove junction links FIRST (before any recursive delete) ----
        # Root cause of the leftover: a recursive rmdir over the node_modules
        # junction returns success while leaving the worktree behind.
        $destructiveOk = $true
        if ($Apply) {
            $junctions = Get-JunctionTargets $taskDir
            foreach ($j in $junctions) {
                if ($j.Path -like "*\frontend\node_modules" -or $j.Path -like "*\node_modules") {
                    if (-not (Remove-JunctionLink $j.Path)) { $destructiveOk = $false }
                } else {
                    # Unexpected reparse point: only rmdir a directory link; report others.
                    if ($j.IsDirectory) { if (-not (Remove-JunctionLink $j.Path)) { $destructiveOk = $false } }
                    else { Write-Log 'WARN' "$($d.Name): unexpected symlink file $($j.Path) -> skip dir"; $destructiveOk = $false }
                }
            }
            if (-not $destructiveOk) {
                Write-Log 'WARN' "$($d.Name): junction handling failed -> skip"
                $skipped++; continue
            }
        } else {
            $junctions = Get-JunctionTargets $taskDir
            if ($junctions.Count -gt 0) {
                Write-Log 'INFO' "$($d.Name): [DRY-RUN] would remove $($junctions.Count) junction(s): $(( $junctions.Path -join '; ' ))"
            }
        }

        # ---- 5. delete ----
        if ($Apply) {
            try {
                Remove-Item -LiteralPath $taskDir -Recurse -Force -ErrorAction Stop
                if (-not (Test-Path -LiteralPath $taskDir)) {
                    $deleted++
                    Write-Log 'INFO' "$($d.Name): deleted"
                } else {
                    Write-Log 'WARN' "$($d.Name): Remove-Item reported success but dir remains -> skip"
                    $skipped++
                }
            } catch {
                Write-Log 'WARN' "$($d.Name): delete failed: $($_.Exception.Message) -> skip"
                $skipped++
            }
        } else {
            Write-Log 'INFO' "$($d.Name): WOULD DELETE (dry-run)"
            if ($VerboseOutput) { Write-Host "$($d.Name): [DRY-RUN] would delete" }
        }
    }
}

Write-Log 'INFO' "sweep cycle end: found=$found deleted=$deleted skipped=$skipped"
