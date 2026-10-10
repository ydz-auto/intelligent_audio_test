@echo off
rem INT-125 standard full-stack payload. Start ONLY via stack_ctl.ps1 (WMI launch),
rem NEVER directly inside an agent run: the platform reaps the run's whole process
rem tree at run exit (outages 21:41 and 23:12 on 2026-10-10 were both caused by this).
rem AUDIO_PYAUDIO_SHIM=1: OS audio stack is wedged (Audiosrv StartPending, real
rem Pa_Initialize hangs forever, see stuck PID 6276 since 19:12) -> audio_service
rem runs with the INT-95 shadow pyaudio fixture. Remove this switch after the
rem machine owner fixes the Windows audio service.
setlocal
set "REPO=D:\00_code\V9.7.31\Intelligent-Audio-TEST"
set "PY=D:\00_env\conda_envs\intelligent_audio_test\python.exe"
set "AUDIO_PYAUDIO_SHIM=1"
set "PATH=D:\00_env\conda_envs\intelligent_audio_test;D:\00_env\conda_envs\intelligent_audio_test\Library\mingw-w64\bin;D:\00_env\conda_envs\intelligent_audio_test\Library\usr\bin;D:\00_env\conda_envs\intelligent_audio_test\Library\bin;D:\00_env\conda_envs\intelligent_audio_test\Scripts;D:\00_env\node-v22.21.1-win-x64;D:\00_env\platform-tools;%PATH%"
cd /d "%REPO%"
"%PY%" run_all.py > "%REPO%\logs\_run_all_stack.log" 2>&1
endlocal
