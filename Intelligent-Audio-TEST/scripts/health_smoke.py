# -*- coding: utf-8 -*-
"""INT-108 健康冒烟口径：HTTP /health + 全部 gRPC 端口 + 前端 + infra 一次全检。

背景：INT-101 收尾的冒烟口径只查「10 服务 HTTP /health + 前端」，gRPC-only 的
audio_service(50052)/device_service(50053) 不在口径内——audio_service 未启动被
漏检（HTTP 面全绿掩盖 gRPC 缺席）。本脚本把 gRPC 端口探测纳入标准口径，供
run_all 启动后自检与集成回归前置检查使用。

用法（项目环境 python，仓库任意位置）：
    python scripts/health_smoke.py [--json]

退出码：0 全部 PASS；1 存在 FAIL（可直接做 CI/回归门禁）。

注意：gRPC 探测为 TCP 连通口径（端口可连即算 PASS）。audio_service 的
GetPhysicalDevices 在 INT-95 影子夹具模式下返回 success=False 属预期，
不作为健康判据——链路可响应即健康。
"""

import argparse
import json
import socket
import sys
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from shared.config.service_ports import (  # noqa: E402
    ALGORITHM_SERVICE_GRPC_PORT, ALGORITHM_SERVICE_HTTP_PORT,
    API_ADAPTER_SERVICE_HTTP_PORT,
    API_GATEWAY_PORT, API_TEST_SERVICE_GRPC_PORT, API_TEST_HTTP_PORT,
    AUDIO_SERVICE_GRPC_PORT, AUTH_SERVICE_GRPC_PORT, AUTH_SERVICE_HTTP_PORT,
    DEVICE_SERVICE_GRPC_PORT, E2E_TEST_GRPC_PORT, E2E_TEST_HTTP_PORT,
    EVALUATION_SERVICE_GRPC_PORT, EVALUATION_SERVICE_HTTP_PORT,
    FRONTEND_DEV_PORT, POSTGRESQL_PORT, REDIS_PORT, REPORT_SERVICE_GRPC_PORT,
    REPORT_SERVICE_HTTP_PORT, RUSTFS_PORT, TASK_SERVICE_GRPC_PORT,
    TASK_SERVICE_HTTP_PORT, TRANSFER_AGENT_GRPC_PORT, TRANSFER_AGENT_HTTP_PORT,
)

HOST = '127.0.0.1'

# HTTP 服务：/health 口径（与 INT-101 冒烟口径一致）
HTTP_SERVICES = [
    ('api_gateway', API_GATEWAY_PORT),
    ('task_service', TASK_SERVICE_HTTP_PORT),
    ('e2e_test_service', E2E_TEST_HTTP_PORT),
    ('api_test_service', API_TEST_HTTP_PORT),
    ('evaluation_service', EVALUATION_SERVICE_HTTP_PORT),
    ('report_service', REPORT_SERVICE_HTTP_PORT),
    ('algorithm_service', ALGORITHM_SERVICE_HTTP_PORT),
    ('auth_service', AUTH_SERVICE_HTTP_PORT),
    ('api_adapter_service', API_ADAPTER_SERVICE_HTTP_PORT),
    ('transfer_agent', TRANSFER_AGENT_HTTP_PORT),
]

# gRPC 服务端口：INT-108 口径新增（TCP 可连即健康；audio/device 为 gRPC-only，
# 此前不在 HTTP 冒烟口径内，漏检即本卡故障模式）。
# 注：api_adapter_service 的 gRPC(50081) 仅其独立入口 run.py 会启动，run_all 的
# uvicorn 模式下 lifespan 不拉起 gRPC，故不纳入默认口径。
GRPC_SERVICES = [
    ('e2e_test_service gRPC', E2E_TEST_GRPC_PORT),
    ('audio_service gRPC', AUDIO_SERVICE_GRPC_PORT),
    ('device_service gRPC', DEVICE_SERVICE_GRPC_PORT),
    ('task_service gRPC', TASK_SERVICE_GRPC_PORT),
    ('algorithm_service gRPC', ALGORITHM_SERVICE_GRPC_PORT),
    ('report_service gRPC', REPORT_SERVICE_GRPC_PORT),
    ('auth_service gRPC', AUTH_SERVICE_GRPC_PORT),
    ('api_test_service gRPC', API_TEST_SERVICE_GRPC_PORT),
    ('evaluation_service gRPC', EVALUATION_SERVICE_GRPC_PORT),
    ('transfer_agent gRPC', TRANSFER_AGENT_GRPC_PORT),
]

INFRA = [
    ('redis', REDIS_PORT),
    ('postgres', POSTGRESQL_PORT),
    ('rustfs', RUSTFS_PORT),
]

FRONTEND = ('frontend', FRONTEND_DEV_PORT)


def tcp_open(port, timeout=2):
    try:
        with socket.create_connection((HOST, port), timeout=timeout):
            return True
    except OSError:
        return False


def http_ok(port, timeout=3):
    try:
        req = urllib.request.Request(f'http://{HOST}:{port}/health')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--json', action='store_true', help='输出 JSON（供脚本消费）')
    args = parser.parse_args()

    results = []
    for name, port in HTTP_SERVICES:
        results.append({'name': name, 'probe': f'http://{HOST}:{port}/health', 'ok': http_ok(port)})
    for name, port in GRPC_SERVICES:
        results.append({'name': name, 'probe': f'tcp {HOST}:{port}', 'ok': tcp_open(port)})
    for name, port in INFRA:
        results.append({'name': name, 'probe': f'tcp {HOST}:{port}', 'ok': tcp_open(port)})
    name, port = FRONTEND
    results.append({'name': name, 'probe': f'tcp {HOST}:{port}', 'ok': tcp_open(port)})

    failed = [r for r in results if not r['ok']]
    if args.json:
        print(json.dumps({'pass': not failed, 'total': len(results), 'failed': failed,
                          'results': results}, ensure_ascii=False, indent=2))
    else:
        width = max(len(r['name']) for r in results)
        for r in results:
            print(f"[{'PASS' if r['ok'] else 'FAIL'}] {r['name'].ljust(width)}  {r['probe']}")
        print(f"\n{len(results) - len(failed)}/{len(results)} PASS"
              + (f"，FAIL: {', '.join(r['name'] for r in failed)}" if failed else ''))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
