@echo off
rem ============================================================================
rem Host-side audio_service (gRPC) stop launcher — INT-2086 防楔死。
rem 仓库规范版：scripts/host_audio_service/；宿主运行副本 D:\00_env\host_audio_service\。
rem
rem 停止顺序（对应负责人口径 1/2/3）:
rem   1) 定位 50052 监听 PID；
rem   2) 优雅停止：gRPC AudioService.Shutdown（服务端停全部播放 → 等流关闭 →
rem      pa.terminate() → 停 server → 进程退出）。旧代码无此 RPC（UNIMPLEMENTED）
rem      或调用超时 → 回退 taskkill /F 并打印楔死风险警告（最后手段）；
rem   3) 等待 TCP 50052 完全释放（监听 socket 消失，默认 60s）；
rem   4) 冷却 COOLDOWN 秒（默认 8s，负责人拍板 5~10s）——确认旧 WASAPI 会话释放，
rem      下一次 Pa_Initialize 才不会撞锁。
rem
rem 用法:  stop_audio_service.cmd [--cooldown 8] [--graceful-timeout 15]
rem 环境变量可覆盖: AUDIO_COOLDOWN / AUDIO_GRACEFUL_TIMEOUT / AUDIO_RELEASE_TIMEOUT
rem ============================================================================
setlocal
set "PORT=50052"

set "REPO=D:\00_code\V9.7.31\Intelligent-Audio-TEST"
set "PY=D:\00_env\conda_envs\intelligent_audio_test\python.exe"
set "HERE=%~dp0"
set "PYTHONUTF8=1"
set "PYTHONPATH=%REPO%;%REPO%\shared\proto"
set "PATH=D:\00_env\conda_envs\intelligent_audio_test;D:\00_env\conda_envs\intelligent_audio_test\Library\bin;D:\00_env\ffmpeg-8.0.1-full_build\bin;%PATH%"
rem stop_audio_service.py 经此定位主 clone（宿主副本兜底已内置）。
set "AUDIO_SERVICE_REPO=%REPO%"

if defined AUDIO_COOLDOWN (
  set "COOLDOWN=%AUDIO_COOLDOWN%"
) else (
  set "COOLDOWN=8"
)
if defined AUDIO_GRACEFUL_TIMEOUT (
  set "GRACEFUL_TIMEOUT=%AUDIO_GRACEFUL_TIMEOUT%"
) else (
  set "GRACEFUL_TIMEOUT=15"
)
if defined AUDIO_RELEASE_TIMEOUT (
  set "RELEASE_TIMEOUT=%AUDIO_RELEASE_TIMEOUT%"
) else (
  set "RELEASE_TIMEOUT=60"
)

"%PY%" "%HERE%stop_audio_service.py" --port %PORT% --cooldown %COOLDOWN% --graceful-timeout %GRACEFUL_TIMEOUT% --release-timeout %RELEASE_TIMEOUT% --log "%HERE%audio_service_%PORT%.stop.log"
if errorlevel 1 (
  echo [FATAL] audio_service 停止未完全成功，见 audio_service_%PORT%.stop.log
  exit /b 1
)
endlocal
