@echo off
rem ============================================================================
rem Host-side audio_service (gRPC) launcher for the docker stack.
rem 仓库规范版：scripts/host_audio_service/；宿主运行副本 D:\00_env\host_audio_service\。
rem
rem Why this file exists: the original INT-1531 launcher lived inside a task
rem worktree that has since been deleted, so the only copy of the start command
rem was gone while the process itself kept running. This copy lives outside any
rem git worktree so it survives task cleanup.
rem
rem Usage:  start_audio_service.cmd
rem Stop:   run stop_audio_service.cmd  —— INT-2086 优雅停止（gRPC Shutdown →
rem         停播放 → 等流关闭 → pa.terminate()）+ 等 50052 释放 + 冷却 8s。
rem         taskkill /PID <pid> /T /F 只作最后手段（强停带流的 noshim 服务会楔死
rem         Windows 音频栈，见 INT-2073）。
rem Note:   the listen port is NOT parameterised. audio_service/interfaces/grpc/
rem          server.py takes it from shared/config/service_ports.py, which
rem          hardcodes AUDIO_SERVICE_GRPC_PORT = 50052 (env cannot override it),
rem          so this must run where 50052 is free.
rem
rem Deployment contract (负责人口径): device_service and audio_service always run
rem on the HOST, not in docker compose. The docker stack reaches them through
rem host.docker.internal:<port>. Docker-side gRPC ports are the 53xxx host
rem mappings from docker/.env (container 51xxx -> host 53xxx).
rem
rem PyAudio shim (INT-95) MUST stay first on PYTHONPATH: the Windows audio stack
rem is wedged (Audiosrv stuck in StartPending), so the real pyaudio Pa_Initialize
rem hangs forever and 50052 would never bind. Consequence: file-level work
rem (tagging, conversion, URL import, mixing/rendering) is fully functional,
rem but hardware playback (POST /audios/{id}/preview) returns a business error.
rem To restore real device I/O an administrator must repair Windows Audio
rem (or reboot), then restart this service WITHOUT the shim on PYTHONPATH
rem (start_audio_service_noshim.cmd).
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
"%PY%" "%REPO%\tests\fixtures\pyaudio_shim\_run_audio_service_shimmed.py" >> "%HERE%audio_service_%PORT%.log" 2>&1
endlocal
