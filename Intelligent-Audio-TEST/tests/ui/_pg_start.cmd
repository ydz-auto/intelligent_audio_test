@echo off
rem INT-260 UI 并行栈的 Postgres 拉起 payload（WMI 专用，经 parallel_stack.py 调起）。
rem 与 INT-125 _stack_start.cmd 同因：postgres.exe 若从 agent run 内直接启动
rem （Start-Process 等）会加入 run 进程树，run 退出时被平台整树收割——2026-10-13
rem 16:43:57 实证（pg 随上轮 run 结束精确死亡）。必须经 WMI 脱离，parent=WmiPrvSE。
setlocal
set "PGBIN=D:\00_env\postgresql-16.8-1-windows-x64-binaries\pgsql\bin"
set "PGDATA=D:\00_env\postgresql-16.8-1-windows-x64-binaries\pgsql\data"
set "PGLOG=D:\00_env\postgresql-16.8-1-windows-x64-binaries\pgsql\log"
if not exist "%PGLOG%" mkdir "%PGLOG%"
"%PGBIN%\postgres.exe" -D "%PGDATA%" >> "%PGLOG%\pg_wmi.log" 2>&1
endlocal
