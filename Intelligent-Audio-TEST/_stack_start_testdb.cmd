@echo off
rem INT-956: test-db variant of the INT-125 standard full-stack payload.
rem Start ONLY via WMI Win32_Process.Create (stack_ctl.ps1 pattern), NEVER
rem directly inside an agent run: the platform reaps the run's whole process
rem tree at run exit. --test-db switches the whole stack to the isolated test
rem DB (intelligent_audio_test_test); without it run_all.py refuses startup
rem (INT-453 guard, shared business DB).
rem AUDIO_PYAUDIO_SHIM=1: OS audio stack is wedged (Audiosrv StartPending, real
rem Pa_Initialize hangs forever) -> audio_service runs with the INT-95 shadow
rem pyaudio fixture. Remove this switch after the machine owner fixes the
rem Windows audio service.
setlocal
set "REPO=D:\00_code\V9.7.31\Intelligent-Audio-TEST"
set "PY=D:\00_env\conda_envs\intelligent_audio_test\python.exe"
set "AUDIO_PYAUDIO_SHIM=1"
set "PATH=D:\00_env\conda_envs\intelligent_audio_test;D:\00_env\conda_envs\intelligent_audio_test\Library\mingw-w64\bin;D:\00_env\conda_envs\intelligent_audio_test\Library\usr\bin;D:\00_env\conda_envs\intelligent_audio_test\Library\bin;D:\00_env\conda_envs\intelligent_audio_test\Scripts;D:\00_env\node-v22.21.1-win-x64;D:\00_env\platform-tools;%PATH%"
cd /d "%REPO%"
"%PY%" run_all.py --test-db > "%REPO%\logs\_run_all_stack.log" 2>&1
endlocal
