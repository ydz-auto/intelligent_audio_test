import os
import sys
import signal
import time
import subprocess


# VEGA-35 / VEGA-42：本进程是真正的后端服务入口，两个"服务进程专属启动副作用"
# 只由本入口打开，且必须在导入 backend.app 之前设置——配置类在导入时求值：
#   * RECOVERY_SWEEP_ON_STARTUP：重启后把遗留 pending/queued/running 收尾为 failed；
#   * TASK_SCHEDULER_ON_STARTUP：3s 轮询的调度器守护线程，自行拾取并推进 pending 任务。
# 测试/迁移脚本/临时脚本不设置它们，因此它们的 create_app() 既不改写共享库状态，
# 也不会对着共享库起调度线程。
def _force_service_startup_switch(name):
    """把服务启动开关强制打开，并把被覆盖的外部取值显式打出来（VEGA-60 / O4）。

    这两个开关原用 ``os.environ.setdefault`` 打开，前提是"外部不会传这个变量"。
    但调用 shell 里遗留一个 ``false/0`` 时 setdefault **不会覆盖**：真实服务起来后
    调度器静默不启，没人拾取 pending 任务（违反 VEGA-42 红线），恢复扫描同样静默失效。
    本入口就是这两个副作用的唯一权威，故直接赋值强制打开。

    取舍（O4 二选一）：选"强制打开"而不是"识别到关闭值就拒绝启动"。拒绝启动会把
    "外部遗留了一个开关变量"升级成"服务完全起不来"，而调用方的真实意图几乎总是
    "把服务跑起来"；开关本身要拦的是测试/脚本进程，那由 backend.app 的
    _service_startup_switch_enabled（含 _is_test_process 判据）负责，与外部环境变量无关。

    覆盖前的外部取值原样打印：用户显式传了 false 却看到服务照常启用，是另一种静默，
    必须留痕（本函数不判断该取值"算不算关闭"——on 值判据只有 backend/config/config.py
    一份，避免这里再写一套）。
    """
    external = os.environ.get(name)
    if external is not None:
        print(f"[WARN] 外部已设置 {name}={external!r}，服务入口强制覆盖为 'true'："
              f"该开关是服务进程专属的启动副作用，关闭会让真实服务静默丢失该语义")
    os.environ[name] = 'true'


# 两个开关用同一个函数打开，口径一致（VEGA-60：不得一个用 setdefault、另一个用赋值）。
_force_service_startup_switch('RECOVERY_SWEEP_ON_STARTUP')
_force_service_startup_switch('TASK_SCHEDULER_ON_STARTUP')

from backend.app import create_app, socketio
from backend.services.execution.execution_engine import execution_engine
from flask import request

config_name = os.getenv('FLASK_CONFIG') or 'default'
app = create_app(config_name)

# 前端服务进程
frontend_process = None

def start_frontend():
    """启动前端 Vite 开发服务器"""
    global frontend_process
    frontend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'frontend')
    if not os.path.isdir(frontend_dir):
        print("[WARN] 未找到 frontend 目录，跳过前端服务启动")
        return

    print("[INFO] 正在启动前端 Vite 开发服务器...")
    try:
        # Windows 上 npm 实际是 npm.cmd，需要 shell=True 才能找到
        kwargs = {}
        if sys.platform == 'win32':
            kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
            npm_cmd = 'npm.cmd'
        else:
            kwargs['start_new_session'] = True
            npm_cmd = 'npm'

        frontend_process = subprocess.Popen(
            [npm_cmd, 'run', 'dev'],
            cwd=frontend_dir,
            **kwargs
        )
        print(f"[OK] 前端服务已启动 (PID: {frontend_process.pid})")
        print("     前端访问地址: http://localhost:5173")
    except Exception as e:
        print(f"[ERROR] 启动前端服务失败: {e}")

def stop_frontend():
    """停止前端 Vite 开发服务器"""
    global frontend_process
    if frontend_process is None:
        return

    print("   正在停止前端 Vite 开发服务器...")
    try:
        if sys.platform == 'win32':
            # Windows 下 taskkill 终止整个进程树
            subprocess.run(
                ['taskkill', '/PID', str(frontend_process.pid), '/T', '/F'],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        else:
            import signal as sig
            os.killpg(os.getpgid(frontend_process.pid), sig.SIGTERM)
        print("   前端服务已停止")
    except Exception as e:
        print(f"   停止前端服务时出错: {e}")
    finally:
        frontend_process = None

shutdown_requested = False

def signal_handler(signum, frame):
    global shutdown_requested
    if shutdown_requested:
        print("\n[WARN] 正在强制退出...")
        os._exit(1)

    shutdown_requested = True
    print(f"\n[INFO] 收到信号 {signum}，正在关闭所有正在运行的任务...")
    
    stopped_count = 0
    
    if hasattr(execution_engine, 'workers') and execution_engine.workers:
        print(f"   发现 {len(execution_engine.workers)} 个运行中的任务，正在停止...")
        
        for task_id in list(execution_engine.workers.keys()):
            try:
                stop_event = execution_engine.stop_flags.get(task_id)
                if stop_event:
                    print(f"   正在停止任务 {task_id}...")
                    stop_event.set()
                    stopped_count += 1
            except Exception as e:
                print(f"   停止任务 {task_id} 时出错: {e}")
    
    if hasattr(execution_engine, 'api_executors') and execution_engine.api_executors:
        print(f"   发现 {len(execution_engine.api_executors)} 个线程池，正在关闭...")
        for task_id in list(execution_engine.api_executors.keys()):
            try:
                executor = execution_engine.api_executors.get(task_id)
                if executor:
                    print(f"   正在关闭线程池 {task_id}...")
                    executor.shutdown(wait=False, cancel_futures=True)
            except Exception as e:
                print(f"   关闭线程池 {task_id} 时出错: {e}")
        execution_engine.api_executors.clear()
    
    if hasattr(execution_engine, 'task_queue') and execution_engine.task_queue:
        print(f"   清空任务队列 ({len(execution_engine.task_queue)} 个任务)...")
        execution_engine.task_queue.clear()
    
    print(f"   已停止 {stopped_count} 个任务")
    
    print("   正在停止 SocketIO 服务器...")
    try:
        socketio.stop()
    except Exception as e:
        print(f"   停止 SocketIO 服务器时出错: {e}")
    
    print("   正在停止 Flask 服务器...")
    try:
        func = request.environ.get('werkzeug.server.shutdown')
        if func is not None:
            func()
    except Exception:
        pass
    
    # 停止前端服务
    stop_frontend()

    print("[OK] 所有任务已停止，程序即将退出")

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

if sys.platform == 'win32':
    signal.signal(signal.SIGBREAK, signal_handler)

if __name__ == '__main__':
    # 启动前端 Vite 开发服务器
    start_frontend()

    try:
        socketio.run(
            app,
            host='0.0.0.0',
            port=int(os.environ.get('FLASK_PORT', '5000')),
            debug=app.config.get('DEBUG', False),
            allow_unsafe_werkzeug=True,
            use_reloader=False
        )
    except KeyboardInterrupt:
        print("\n🛑 用户中断，程序退出")
        stop_frontend()
