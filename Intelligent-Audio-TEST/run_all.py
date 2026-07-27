"""
一键启动所有微服务（开发模式）
"""
import subprocess
import sys
import os
import time
import signal

services = [
    {'name': 'api_gateway', 'port': 5000, 'dir': 'api_gateway'},
    {'name': 'task_service', 'port': 5001, 'dir': 'task_service'},
    {'name': 'e2e_test_service', 'port': 5002, 'dir': 'e2e_test_service'},
    {'name': 'api_test_service', 'port': 5003, 'dir': 'api_test_service'},
    {'name': 'evaluation_service', 'port': 5004, 'dir': 'evaluation_service'},
]

processes = []

def start_all():
    for svc in services:
        print(f"[START] {svc['name']} on port {svc['port']}...")
        proc = subprocess.Popen(
            [sys.executable, os.path.join(svc['dir'], 'app.py')],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        processes.append({'name': svc['name'], 'proc': proc})
        time.sleep(2)
    print(f"\n[OK] Started {len(processes)} services. Ctrl+C to stop all.")

def stop_all():
    for p in reversed(processes):
        print(f"[STOP] {p['name']}...")
        p['proc'].terminate()
        try:
            p['proc'].wait(timeout=5)
        except subprocess.TimeoutExpired:
            p['proc'].kill()
    print("[OK] All services stopped.")

if __name__ == '__main__':
    try:
        start_all()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[INFO] Stopping all services...")
        stop_all()
