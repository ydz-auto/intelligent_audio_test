# SSH tunnel for data plane (bypass Tailscale DERP relay).
#   forward: local 127.0.0.1:15432 -> server postgres:5432, 127.0.0.1:16379 -> redis:6379,
#            127.0.0.1:15052 -> server audio_service data plane (127.0.0.1:50052)
#   reverse: server 172.18.0.1:50052/50053 -> local audio_agent/device gRPC
# Launched at logon from Startup folder; reconnects after 5s on failure.
# NOTE: keep this file ASCII-only (Windows PowerShell 5.1 reads non-BOM files as ANSI).
$sshExe = 'C:\Windows\System32\OpenSSH\ssh.exe'
$log = Join-Path $PSScriptRoot '..\..\logs\host_services\ssh_tunnel.log'
$sshArgs = @(
  '-N',
  '-o', 'ExitOnForwardFailure=yes',
  '-o', 'ServerAliveInterval=30',
  '-o', 'ServerAliveCountMax=3',
  '-o', 'BatchMode=yes',
  '-L', '127.0.0.1:15432:127.0.0.1:5432',
  '-L', '127.0.0.1:16379:127.0.0.1:6379',
  '-L', '127.0.0.1:15443:127.0.0.1:15000',
  '-L', '127.0.0.1:15052:127.0.0.1:50052',
  '-L', '127.0.0.1:15361:127.0.0.1:53061',
  '-L', '127.0.0.1:15367:127.0.0.1:53067',
  '-L', '127.0.0.1:15368:127.0.0.1:53068',
  '-L', '127.0.0.1:15369:127.0.0.1:53069',
  '-L', '127.0.0.1:15391:127.0.0.1:53091',
  '-R', '172.18.0.1:50052:127.0.0.1:50052',
  '-R', '172.18.0.1:50053:127.0.0.1:50053',
  'ubuntu@106.54.49.79'
)
while ($true) {
  "$(Get-Date -Format s) tunnel start: $sshExe $($sshArgs -join ' ')" |
    Out-File -Append -Encoding utf8 $log
  try {
    & $sshExe @sshArgs 2>&1 | Out-File -Append -Encoding utf8 $log
  } catch {
    "$(Get-Date -Format s) tunnel error: $_" | Out-File -Append -Encoding utf8 $log
  }
  "$(Get-Date -Format s) tunnel exit, retry in 5s" | Out-File -Append -Encoding utf8 $log
  Start-Sleep -Seconds 5
}
