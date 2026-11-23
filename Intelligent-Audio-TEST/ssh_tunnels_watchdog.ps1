# Watchdog: keep the SSH tunnel alive. ASCII-only file.
# Loops forever (hidden), probes local 5433, restarts tunnel if down.
$probePort = 5433
$tunnelScript = Join-Path $PSScriptRoot 'ssh_tunnels.ps1'

function Test-TunnelAlive {
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $ok = $client.ConnectAsync('127.0.0.1', $probePort).Wait(3000)
        $client.Close()
        return [bool]$ok
    } catch {
        return $false
    }
}

while ($true) {
    if (-not (Test-TunnelAlive)) {
        powershell -NoProfile -ExecutionPolicy Bypass -File $tunnelScript start | Out-Null
    }
    Start-Sleep -Seconds 20
}
