@echo off
rem ============================================================================
rem Host-side audio_service (gRPC) launcher WITHOUT the pyaudio shim.
rem 仓库规范版：scripts/host_audio_service/；宿主运行副本 D:\00_env\host_audio_service\，
rem 两者内容一致（部署后以宿主副本为准）。
rem
rem ONLY use this after Windows Audio is healthy:
rem     sc query Audiosrv   ->  STATE : 4  RUNNING
rem If Audiosrv is START_PENDING, real pyaudio's Pa_Initialize hangs forever and
rem this script will hang before binding 50052 — use start_audio_service.cmd
rem (with the shim) instead.
rem
rem INT-2086 防楔死（负责人口径，本脚本三个核心改动）:
rem   1) 冷却间隔：停止必须先走 stop_audio_service.cmd（优雅停止 + 等 50052 释放
rem      + 冷却 8s）后再跑本脚本；直接 taskkill /F 强停有楔死 Windows 音频栈的风险。
rem   2) 挂死禁连试：下面 Pa_Initialize 自检由 check_pyaudio_health.py 加超时执行
rem      （默认 60s，可用环境变量 AUDIO_CHECK_TIMEOUT 调小触发失败路径）；超时一次
rem      即失败退出，绝不自动重试——每次重试=多一个卡在全局音频锁里的进程，越重启越死。
rem      失败日志（audio_service_%PORT%.noshim.log）含「重启 Audiosrv / 重启机器」指引。
rem   3) 优雅停止通道：服务端新增 gRPC AudioService.Shutdown RPC（停全部播放 →
rem      等流关闭 → pa.terminate() → 停 server），停止优先调它，taskkill /F 只作最后手段。
rem
rem Recovery order (管理员修好 Audiosrv 之后):
rem   1) stop_audio_service.cmd     <- 优雅停止 + 端口释放等待 + 冷却（新）
rem   2) run this script (via WMI Win32_Process.Create so it survives the run)
rem   3) verify: POST /api/v1/audios/{id}/preview -> 2xx
rem              GET  /api/v1/playback-devices   -> status online
rem
rem Everything else (ports, env, repo, interpreter) is identical to
rem start_audio_service.cmd; the ONLY difference is that
rem tests\fixtures\pyaudio_shim is NOT on PYTHONPATH, so the real
rem pyaudio / portaudio module is imported and hardware I/O works.
rem ============================================================================
setlocal
set "PORT=50052"

set "REPO=D:\00_code\V9.7.31\Intelligent-Audio-TEST"
set "PY=D:\00_env\conda_envs\intelligent_audio_test\python.exe"
set "HERE=%~dp0"
set "PYTHONUTF8=1"
set "PYTHONPATH=%REPO%;%REPO%\shared\proto"
set "PATH=D:\00_env\conda_envs\intelligent_audio_test;D:\00_env\conda_envs\intelligent_audio_test\Library\bin;D:\00_env\ffmpeg-8.0.1-full_build\bin;%PATH%"
set "SERVICE_NAME=audio_service"
set "SERVICE_HOST=0.0.0.0"
set "GRPC_PORT=%PORT%"
rem INT-2086：run_audio_service_noshim.py 经此定位主 clone（宿主副本兜底已内置）。
set "AUDIO_SERVICE_REPO=%REPO%"

rem --- docker stack infra (host-mapped ports) ---
set "DATABASE_URL=postgresql://intelligent_audio_test:intelligent_audio_test666@127.0.0.1:15432/intelligent_audio_test"
set "REDIS_URL=redis://127.0.0.1:16379"
set "OSS_ENDPOINT=http://127.0.0.1:9000"
set "OSS_ACCESS_KEY=intelligent_audio_test"
set "OSS_SECRET_KEY=intelligent_audio_test666"
set "OSS_BUCKET_NAME=intelligent-audio-test"
set "OSS_KEY_PREFIX=intelligent_audio_test"
set "AUTH_MODE=off"

rem --- cross-service discovery: docker/.env 53xxx host mappings ---
set "AUDIO_SERVICE_HOST=127.0.0.1"
set "AUDIO_SERVICE_GRPC_PORT=%PORT%"
set "DEVICE_SERVICE_HOST=127.0.0.1"
set "DEVICE_SERVICE_GRPC_PORT=50053"
set "TASK_SERVICE_HOST=127.0.0.1"
set "TASK_SERVICE_GRPC_PORT=53061"
set "ALGORITHM_SERVICE_HOST=127.0.0.1"
set "ALGORITHM_SERVICE_GRPC_PORT=53067"
set "REPORT_SERVICE_HOST=127.0.0.1"
set "REPORT_SERVICE_GRPC_PORT=53068"
set "AUTH_SERVICE_HOST=127.0.0.1"
set "AUTH_SERVICE_GRPC_PORT=53069"
set "EVALUATION_SERVICE_HOST=127.0.0.1"
set "EVALUATION_SERVICE_GRPC_PORT=53091"
set "API_TEST_SERVICE_HOST=127.0.0.1"
set "API_TEST_SERVICE_GRPC_PORT=53071"
set "API_TEST_SERVICE_PORT=15003"
set "E2E_TEST_SERVICE_HOST=127.0.0.1"
set "E2E_TEST_SERVICE_GRPC_PORT=53051"

cd /d "%REPO%"
rem INT-2086 真实 pyaudio 自检：带超时（默认 60s，AUDIO_CHECK_TIMEOUT 可调小触发
rem 失败路径验证），单次自检，超时即失败退出、不重试；失败日志含恢复指引。
if not defined AUDIO_CHECK_TIMEOUT set "AUDIO_CHECK_TIMEOUT=60"
"%PY%" "%HERE%check_pyaudio_health.py" --timeout %AUDIO_CHECK_TIMEOUT% --python "%PY%" >> "%HERE%audio_service_%PORT%.noshim.log" 2>&1
if errorlevel 1 (
  echo [FATAL] real pyaudio unavailable - Audiosrv still wedged? 详见 audio_service_%PORT%.noshim.log
  echo [FATAL] 恢复指引：管理员重启 Audiosrv 或重启机器后重试；禁止连续重试。
  exit /b 1
)
rem 入口必须在影子目录之外：tests\fixtures\pyaudio_shim\ 下的脚本会让 Python 把
rem 该目录放进 sys.path[0]，import pyaudio 照样命中影子模块（2026-10-26 实测踩到）。
"%PY%" "%HERE%run_audio_service_noshim.py" >> "%HERE%audio_service_%PORT%.log" 2>&1
endlocal
