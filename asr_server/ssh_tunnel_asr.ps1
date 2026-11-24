# ASR 反向隧道（常驻）：本机 ASR 127.0.0.1:10095 -> 服务器 106.54.49.79 的 10.0.0.9:10095
# 服务器 eval_server 通过 http://10.0.0.9:10095 访问本机 ASR。
# 用法：
#   手动运行:  powershell -ExecutionPolicy Bypass -File .\ssh_tunnel_asr.ps1
#   注册自启:  见下方 Register-ScheduledTask 注释段
$ErrorActionPreference = 'Continue'
try { $Host.UI.RawUI.WindowTitle = 'IAT ASR Tunnel' } catch { }

$sshArgs = @(
  '-N',
  '-v',                                 # 打印握手/转发日志，窗口里能实时看到隧道状态
  '-o', 'BatchMode=yes',                # 免密（公钥登录），避免卡密码输入
  '-o', 'ExitOnForwardFailure=yes',     # 远端绑定失败立即退出，避免假隧道
  '-o', 'ServerAliveInterval=30',       # 30s 心跳，断线后由循环重启
  '-o', 'ServerAliveCountMax=3',
  '-R', '10.0.0.9:10095:127.0.0.1:10095',
  'ubuntu@106.54.49.79'
)

while ($true) {
  Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] starting ssh reverse tunnel ..."
  # 直接在当前（headless）控制台启动 ssh，不新建窗口
  & ssh @sshArgs 2>&1 | ForEach-Object { Write-Host $_ }
  Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] tunnel exited, restart in 5s ..."
  Start-Sleep -Seconds 5
}

# ─── 注册计划任务（conhost --headless，彻底无窗口）─────────────────────
# Windows 默认终端是 Windows Terminal 时，-WindowStyle Hidden 无效（会被 WT 托管弹窗），
# 因此用 conhost --headless 启 powershell，控制台完全无窗口。
# $task = New-ScheduledTaskAction -Execute 'conhost.exe' `
#   -Argument '--headless powershell.exe -NoProfile -ExecutionPolicy Bypass -File "E:\w60085971\intelligent_audio_test\asr_server\ssh_tunnel_asr.ps1"'
# $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
# $settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
# Register-ScheduledTask -TaskName 'ASR-SSH-Tunnel' -Action $task -Trigger $trigger -Settings $settings -Force
