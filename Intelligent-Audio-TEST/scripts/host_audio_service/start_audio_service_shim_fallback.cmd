@echo off
rem ============================================================================
rem Host-side audio_service (gRPC) launcher for the docker stack — SHIM FALLBACK.
rem 仓库规范版：scripts/host_audio_service/；宿主运行副本 D:\00_env\host_audio_service\。
rem
rem 与 start_audio_service.cmd 唯一区别：日志写 audio_service_%PORT%_shim_fallback.log，
rem 用于旧日志被残留进程锁住时的绕行（INT-2073：强停后 695MB 日志被卡驱动 python
rem 进程锁住，重定向失败 cmd 秒退）。
rem
rem INT-2086 防楔死口径（与 start_audio_service.cmd 相同）:
rem   - 停止优先走 stop_audio_service.cmd（gRPC Shutdown 优雅停止 + 等 50052 释放
rem     + 冷却 8s）；taskkill /F 只作最后手段，有楔死 Windows 音频栈风险。
rem   - 真实放音恢复前（Audiosrv 仍楔死）只能影子兜底：GetPhysicalDevices 会返回
rem     影子报错、playback scan 0 通道；管理员修好 Audiosrv 后改跑 noshim 版。
rem Usage:  start_audio_service_shim_fallback.cmd
rem ============================================================================
setlocal
set "PORT=50052"

set "REPO=D:\00_code\V9.7.31\Intelligent-Audio-TEST"
set "PY=D:\00_env\conda_envs\intelligent_audio_test\python.exe"
set "HERE=%~dp0"
set "PYTHONUTF8=1"
set "PYTHONPATH=%REPO%\tests\fixtures\pyaudio_shim;%REPO%;%REPO%\shared\proto"
set "PATH=D:\00_env\conda_envs\intelligent_audio_test;D:\00_env\conda_envs\intelligent_audio_test\Library\bin;D:\00_env\ffmpeg-8.0.1-full_build\bin;%PATH%"
set "SERVICE_NAME=audio_service"
set "SERVICE_HOST=0.0.0.0"
set "GRPC_PORT=%PORT%"
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
"%PY%" "%REPO%\tests\fixtures\pyaudio_shim\_run_audio_service_shimmed.py" >> "%HERE%audio_service_%PORT%_shim_fallback.log" 2>&1
endlocal
