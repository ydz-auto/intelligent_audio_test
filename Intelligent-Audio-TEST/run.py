from backend.app import create_app, socketio
from backend.services.execution.execution_engine import execution_engine
import os
import sys
import signal
import time
from flask import request

config_name = os.getenv('FLASK_CONFIG') or 'default'
app = create_app(config_name)

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
    
    print("[OK] 所有任务已停止，程序即将退出")

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

if sys.platform == 'win32':
    signal.signal(signal.SIGBREAK, signal_handler)

if __name__ == '__main__':
    try:
        socketio.run(
            app, 
            host='0.0.0.0', 
            port=5000,
            debug=app.config.get('DEBUG', False),
            allow_unsafe_werkzeug=True,
            use_reloader=False
        )
    except KeyboardInterrupt:
        print("\n🛑 用户中断，程序退出")
