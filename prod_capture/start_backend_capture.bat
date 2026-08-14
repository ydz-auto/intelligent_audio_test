@echo off
REM 带捕获环境启动 backend，环境变量仅在本脚本内生效，退出后自动恢复
REM 用法: 先启动 run_capture.py，再运行本脚本

setlocal

set PYTHONPATH=%~dp0;%PYTHONPATH%
set IAT_HTTP_LOG=%~dp0run_%1\http_requests.jsonl
set IAT_SERVICE=backend
set PYTHONUNBUFFERED=1

if "%IAT_HTTP_LOG%"=="%\~dp0run_\http_requests.jsonl" (
    echo !! 请传入 run 目录的时间戳后缀，例如: start_backend_capture 20260813_144924
    echo !! 或先启动 run_capture.py 查看提示的 RUN_DIR
    exit /b 1
)

echo [%time%] 捕获模式启动 backend
echo [%time%] IAT_HTTP_LOG=%IAT_HTTP_LOG%

cd /d %~dp0..\Intelligent-Audio-TEST
python run.py

endlocal
