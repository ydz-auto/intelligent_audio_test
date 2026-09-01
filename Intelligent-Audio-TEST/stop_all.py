"""
停止所有前后端微服务，保留基础设施（redis / postgres / minio）。

- 停止 11 个后端微服务（FastAPI HTTP + gRPC-only）
- 停止前端 Vite dev server
- 不停止 redis(:6379) / postgres(:5432) / minio(:9000)

用法：
    python stop_all.py
"""
import os
import sys
import time
import socket
import logging
import subprocess

# 从端口注册表集中引入所有端口常量，避免散落硬编码
from shared.config.service_ports import (
    API_GATEWAY_PORT,
    TASK_SERVICE_HTTP_PORT,
    TASK_SERVICE_GRPC_PORT,
    E2E_TEST_HTTP_PORT,
    E2E_TEST_GRPC_PORT,
    API_TEST_HTTP_PORT,
    API_TEST_SERVICE_GRPC_PORT,
    EVALUATION_SERVICE_HTTP_PORT,
    EVALUATION_SERVICE_GRPC_PORT,
    ALGORITHM_SERVICE_HTTP_PORT,
    ALGORITHM_SERVICE_GRPC_PORT,
    REPORT_SERVICE_HTTP_PORT,
    REPORT_SERVICE_GRPC_PORT,
    AUTH_SERVICE_HTTP_PORT,
    AUTH_SERVICE_GRPC_PORT,
    API_ADAPTER_SERVICE_HTTP_PORT,
    API_ADAPTER_SERVICE_GRPC_PORT,
    AUDIO_SERVICE_GRPC_PORT,
    DEVICE_SERVICE_GRPC_PORT,
    REDIS_PORT,
    POSTGRESQL_PORT,
    MINIO_PORT,
    MINIO_CONSOLE_PORT,
    FRONTEND_DEV_PORT,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s %(name)s: %(message)s')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 11 个后端微服务 + 前端的端口配置（与 run_all.py 保持一致）
# 停止时只需端口即可定位进程，不需要 dir/http 等启动参数
SERVICES_TO_STOP = [
    {'name': 'api_gateway',        'port': API_GATEWAY_PORT,               'grpc_port': None},
    {'name': 'task_service',       'port': TASK_SERVICE_HTTP_PORT,         'grpc_port': TASK_SERVICE_GRPC_PORT},
    {'name': 'e2e_test_service',   'port': E2E_TEST_HTTP_PORT,             'grpc_port': E2E_TEST_GRPC_PORT},
    {'name': 'api_test_service',   'port': API_TEST_HTTP_PORT,             'grpc_port': API_TEST_SERVICE_GRPC_PORT},
    {'name': 'evaluation_service', 'port': EVALUATION_SERVICE_HTTP_PORT,   'grpc_port': EVALUATION_SERVICE_GRPC_PORT},
    {'name': 'algorithm_service',  'port': ALGORITHM_SERVICE_HTTP_PORT,    'grpc_port': ALGORITHM_SERVICE_GRPC_PORT},
    {'name': 'report_service',     'port': REPORT_SERVICE_HTTP_PORT,      'grpc_port': REPORT_SERVICE_GRPC_PORT},
    {'name': 'auth_service',       'port': AUTH_SERVICE_HTTP_PORT,         'grpc_port': AUTH_SERVICE_GRPC_PORT},
    {'name': 'api_adapter_service','port': API_ADAPTER_SERVICE_HTTP_PORT,   'grpc_port': API_ADAPTER_SERVICE_GRPC_PORT},
    {'name': 'audio_service',      'port': None,                           'grpc_port': AUDIO_SERVICE_GRPC_PORT},
    {'name': 'device_service',     'port': None,                           'grpc_port': DEVICE_SERVICE_GRPC_PORT},
    {'name': 'frontend',           'port': FRONTEND_DEV_PORT,              'grpc_port': None},
]

# 基础设施端口——明确排除，绝不触碰
INFRA_PORTS = {REDIS_PORT, POSTGRESQL_PORT, MINIO_PORT, MINIO_CONSOLE_PORT}


def _is_port_open(host, port):
    """探测端口是否可连接。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False


def _find_pids_on_port(port):
    """查找占用指定端口的进程 PID 集合。"""
    pids = set()
    # 优先用 psutil（跨平台）
    try:
        import psutil
        for conn in psutil.net_connections(kind='inet'):
            if (conn.status == psutil.CONN_LISTEN
                    and conn.laddr.port == port
                    and conn.pid):
                pids.add(conn.pid)
        if pids:
            return pids
    except Exception:
        logger.debug("psutil 查询占用端口 %s 的进程失败", port, exc_info=True)
    # 回退：Windows netstat
    if os.name == 'nt':
        try:
            result = subprocess.run(
                ['netstat', '-ano'], capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                if f':{port} ' in line and 'LISTEN' in line.upper():
                    parts = line.split()
                    if parts and parts[-1].isdigit():
                        pids.add(int(parts[-1]))
        except Exception:
            logger.debug("netstat 查询占用端口 %s 的进程失败", port, exc_info=True)
    return pids


def _kill_pid(pid):
    """杀掉指定 PID 的进程，返回是否成功。"""
    try:
        if os.name == 'nt':
            r = subprocess.run(
                ['taskkill', '/F', '/PID', str(pid)],
                capture_output=True, text=True, timeout=5
            )
            return r.returncode == 0
        else:
            import signal as _sig
            os.kill(pid, _sig.SIGKILL)
            return True
    except Exception:
        return False


def _get_proc_name(pid):
    """获取进程名称。"""
    try:
        import psutil
        return psutil.Process(pid).name()
    except Exception:
        return ''


def stop_all():
    """停止所有前后端微服务，保留基础设施。"""
    print("[INFO] Stopping frontend + 11 backend services (keeping redis/postgres/minio)...",
          flush=True)

    # 收集需要停止的端口
    ports_to_stop = set()
    for svc in SERVICES_TO_STOP:
        if svc.get('port'):
            ports_to_stop.add(svc['port'])
        if svc.get('grpc_port'):
            ports_to_stop.add(svc['grpc_port'])

    # 安全检查：确认没有混入基础设施端口
    leaked = ports_to_stop & INFRA_PORTS
    if leaked:
        print(f"[ERROR] safety check failed: infra ports leaked into stop list: {leaked}",
              flush=True)
        print("[ERROR] aborting to protect infrastructure. Please check SERVICES_TO_STOP.",
              flush=True)
        sys.exit(1)

    killed_any = False
    for port in sorted(ports_to_stop):
        pids = _find_pids_on_port(port)
        if not pids:
            continue
        for pid in pids:
            proc_name = _get_proc_name(pid)
            print(f"[STOP] port {port} -> PID {pid} ({proc_name}), killing...", flush=True)
            if _kill_pid(pid):
                killed_any = True

    if killed_any:
        time.sleep(1)  # 等端口释放

    # 汇总结果
    print("", flush=True)
    for svc in SERVICES_TO_STOP:
        ports = [p for p in [svc.get('port'), svc.get('grpc_port')] if p]
        still_open = [p for p in ports if _is_port_open('localhost', p)]
        if still_open:
            print(f"[WARN] {svc['name']} still listening on {still_open}", flush=True)
        else:
            print(f"[OK] {svc['name']} stopped", flush=True)

    # 确认基础设施仍在运行
    print("", flush=True)
    infra_check = [
        ('redis', REDIS_PORT),
        ('postgres', POSTGRESQL_PORT),
        ('minio', MINIO_PORT),
    ]
    for name, port in infra_check:
        if _is_port_open('localhost', port):
            print(f"[OK] {name} still running on :{port}", flush=True)
        else:
            print(f"[INFO] {name} not running on :{port} (was it started?)", flush=True)

    print("\n[OK] Stop complete.", flush=True)


if __name__ == '__main__':
    stop_all()
