# -*- coding: utf-8 -*-
"""独立沙箱 runner/sidecar（方案 doc/agent化/07 §7，INT-2455）。

为什么单独一个进程
------------------
生产 ``agent_service`` 不得挂载 ``/var/run/docker.sock``（负责人红线）。
Docker 访问权集中在本 runner：只有它运行在持有 Docker 的宿主/容器里（compose
接线由 INT-2456 负责），``agent_service`` 通过 ``HttpRunnerDockerExecutor``
把容器规格 POST 给 ``/v1/sandbox/execute``，``/work`` 产物仍由应用层按路径回收。

鉴权
----
共享令牌 ``AGENT_SANDBOX_RUNNER_TOKEN``（请求头 ``X-Sandbox-Runner-Token``）。
未配置令牌时 runner **拒绝启动**（fail closed）：一个能跑容器的无鉴权端点等于
把宿主 Docker 交出去。

启动：
    python -m agent_service.infrastructure.sandbox.runner_service
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from http import server as http_server

from shared.config.service_ports import AGENT_SANDBOX_RUNNER_PORT

from agent_service.application.sandbox_runner import SandboxConfigurationError
from agent_service.infrastructure.sandbox.docker_runner import (
    RUNNER_API_PATH,
    RUNNER_HEALTH_PATH,
    HostCliDockerExecutor,
    SandboxContainerReaper,
    execution_to_dict,
    invocation_from_dict,
)

logger = logging.getLogger(__name__)

RUNNER_TOKEN_ENV = 'AGENT_SANDBOX_RUNNER_TOKEN'
RUNNER_TOKEN_HEADER = 'X-Sandbox-Runner-Token'
#: 请求体上限：一次容器规格 + 参数，远小于此。
MAX_REQUEST_BYTES = 256 * 1024


class SandboxRunnerRequestHandler(http_server.BaseHTTPRequestHandler):
    """极简 JSON 端点：执行一次容器，回传结果。"""

    server_version = 'AgentSandboxRunner/1'

    # 由 SandboxRunnerServer 注入
    executor: HostCliDockerExecutor
    token: str

    def do_GET(self) -> None:  # noqa: N802 - http.server 约定
        if self.path.rstrip('/') == RUNNER_HEALTH_PATH:
            self._respond(200, {'status': 'ok'})
            return
        self._respond(404, {'error': 'not_found'})

    def do_POST(self) -> None:  # noqa: N802 - http.server 约定
        if self.path.rstrip('/') != RUNNER_API_PATH:
            self._respond(404, {'error': 'not_found'})
            return
        if not self._authorized():
            self._respond(401, {'error': 'unauthorized'})
            return
        try:
            payload = self._read_json()
            invocation = invocation_from_dict(payload.get('invocation') or {})
            # 按 runner 自己的白名单复核调用方送来的规格（镜像 / 解释器 /
            # 非 root 身份 / 脚本路径 / 资源限额上限），不合规一律 400。
            self.executor.validate(invocation)
        except (SandboxConfigurationError, KeyError, TypeError, ValueError) as exc:
            logger.warning('拒绝非法沙箱请求：%s', exc)
            self._respond(400, {'error': str(exc)})
            return

        execution = self.executor.run(invocation)
        self._respond(200, {'execution': execution_to_dict(execution)})

    # ── 内部 ──────────────────────────────────────────────────
    def _authorized(self) -> bool:
        provided = self.headers.get(RUNNER_TOKEN_HEADER, '')
        return bool(self.token) and provided == self.token

    def _read_json(self) -> dict:
        length = int(self.headers.get('Content-Length') or 0)
        if length <= 0 or length > MAX_REQUEST_BYTES:
            raise ValueError(f'请求体长度非法：{length}')
        raw = self.rfile.read(length)
        data = json.loads(raw.decode('utf-8'))
        if not isinstance(data, dict):
            raise ValueError('请求体必须是 JSON 对象')
        return data

    def _respond(self, status: int, body: dict) -> None:
        raw = json.dumps(body, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt: str, *args) -> None:  # 走统一日志，不写 stderr
        logger.info('sandbox-runner %s - %s', self.address_string(), fmt % args)


class SandboxRunnerServer:
    """把 handler 与执行器/令牌绑定的 HTTP 服务封装（可被测试在进程内启动）。"""

    def __init__(
        self,
        executor: HostCliDockerExecutor,
        token: str,
        bind_host: str = '127.0.0.1',
        port: int = AGENT_SANDBOX_RUNNER_PORT,
    ) -> None:
        if not token:
            raise SandboxConfigurationError(
                f'{RUNNER_TOKEN_ENV} 未配置：拒绝启动无鉴权的沙箱 runner'
            )
        handler = type(
            'BoundSandboxRunnerHandler',
            (SandboxRunnerRequestHandler,),
            {'executor': executor, 'token': token},
        )
        self._server = http_server.ThreadingHTTPServer((bind_host, port), handler)
        self._thread: threading.Thread | None = None
        self._token = token

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    @property
    def url(self) -> str:
        host, port = self._server.server_address[0], self._server.server_address[1]
        return f'http://{host}:{port}'

    def start_background(self) -> 'SandboxRunnerServer':
        self._thread = threading.Thread(
            target=self._server.serve_forever, name='sandbox-runner', daemon=True
        )
        self._thread.start()
        return self

    def serve_forever(self) -> None:
        """前台常驻（生产 runner 进程用）。"""
        self._server.serve_forever()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=10)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )
    token = (os.environ.get(RUNNER_TOKEN_ENV) or '').strip()
    bind_host = os.environ.get('AGENT_SANDBOX_RUNNER_BIND', '0.0.0.0')
    port = int(os.environ.get('AGENT_SANDBOX_RUNNER_PORT', str(AGENT_SANDBOX_RUNNER_PORT)))
    docker_binary = os.environ.get('AGENT_SANDBOX_DOCKER_BIN', 'docker')
    try:
        server = SandboxRunnerServer(
            executor=HostCliDockerExecutor(docker_binary=docker_binary),
            token=token,
            bind_host=bind_host,
            port=port,
        )
    except SandboxConfigurationError as exc:
        logger.error('沙箱 runner 启动失败：%s', exc)
        return 2
    # P1-1：runner 崩溃 / 重启后遗留的容器没人回收。启动先同步扫一次，之后后台定时扫。
    reaper = SandboxContainerReaper(docker_binary=docker_binary)
    try:
        reaped = reaper.reap_once()
        if reaped:
            logger.warning('启动回收孤儿沙箱容器 %s 个：%s', len(reaped), reaped)
    except Exception:  # noqa: BLE001 - 回收失败不阻断 runner 提供执行能力
        logger.exception('启动回收孤儿沙箱容器失败')
    reaper.start_background()
    logger.info(
        '沙箱运行器回收策略：阈值=%ss（timeout+宽限） 间隔=%ss',
        reaper.threshold_seconds, reaper.interval_seconds,
    )
    logger.info('沙箱 runner 已启动：%s:%s', bind_host, server.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info('沙箱 runner 收到中断，退出')
    finally:
        reaper.stop()
        server.stop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
