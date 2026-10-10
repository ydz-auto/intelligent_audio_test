@echo off
rem INT-108: audio_service shimmed launcher.
rem OS audio stack wedged (Audiosrv StartPending, real Pa_Initialize hangs forever):
rem inject INT-95 shadow pyaudio fixture as FIRST entry of PYTHONPATH so PyAudio()
rem construction raises instantly and server.py absorbs it (see tests\fixtures\pyaudio_shim\pyaudio.py).
rem Detached via WMI by the INT-108 unblock run; survives agent run exit.
rem For E2E physical-chain acceptance (real device I/O), stop this instance and
rem launch WITHOUT the shim dir in PYTHONPATH after Windows Audio is repaired.
setlocal
set "REPO=D:\00_code\V9.7.31\Intelligent-Audio-TEST"
set "PY=D:\00_env\conda_envs\intelligent_audio_test\python.exe"
set "PATH=D:\00_env\conda_envs\intelligent_audio_test;D:\00_env\conda_envs\intelligent_audio_test\Library\bin;%PATH%"
set "PYTHONPATH=%REPO%\tests\fixtures\pyaudio_shim;%REPO%;%REPO%\shared\proto"
set "SERVICE_NAME=audio_service"
set "GRPC_PORT=50052"
set "PYTHONUTF8=1"
cd /d "%REPO%"
"%PY%" "%REPO%\tests\fixtures\pyaudio_shim\_run_audio_service_shimmed.py" > "%REPO%\_audio_shimmed.out.log" 2>&1
endlocal
