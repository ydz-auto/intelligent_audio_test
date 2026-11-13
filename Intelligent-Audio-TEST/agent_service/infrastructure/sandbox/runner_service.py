# -*- coding: utf-8 -*-
"""独立沙箱 runner/sidecar（方案 doc/agent化/07 §7，INT-2455 / INT-2489）。

为什么单独一个进程
------------------
生产 ``agent_service`` 不得挂载 ``/var/run/docker.sock``（负责人红线）。
Docker 访问权集中在本 runner：只有它运行在持有 Docker（与 gVisor ``runsc``）的
宿主/容器里（compose 接线由 INT-2456 负责），``agent_service`` 通过
``HttpRunnerDockerExecutor``（T1）/ ``HttpRunnerT2Executor``（T2）把容器规格
POST 给 runner，``/work`` 产物仍由应用层按路径回收。

端点
----
- ``POST /v1/sandbox/execute``：T1 一次性容器；
- ``POST /v1/sandbox/t2/execute``：T2（gVisor）一次性容器；
- ``GET  /v1/sandbox/t2/runtime``：T2 运行时可用性（无 runsc 即明确不可用）；
- ``GET  /healthz``：存活探针。

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

from agent_service.application.sandbox_runner import (
    SandboxConfigurationError,
    SandboxRuntimeAvailability,
)
from agent_service.infrastructure.sandbox.docker_runner import (
    RUNNER_API_PATH,
    RUNNER_HEALTH_PATH,
    HostCliDockerExecutor,
    execution_to_dict,
    invocation_from_dict,
    validate_invocation,
)
from agent_service.infrastructure.sandbox.policy import T2Policy, load_t2_policy
from agent_service.infrastructure.sandbox.t2_runner import (
    T2_RUNTIME_API_PATH,
    T2_RUNNER_API_PATH,
    T2DockerExecutor,
    availability_to_dict,
    t2_invocation_from_dict,
    validate_t2_invocation,
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
    t2_executor: T2DockerExecutor | None
    token: str

    def do_GET(self) -> None:  # noqa: N802 - http.server 约定
        path = self.path.rstrip('/')
        if path == RUNNER_HEALTH_PATH:
            self._respond(200, {'status': 'ok'})
            return
        if path == T2_RUNTIME_API_PATH:
            if not self._authorized():
                self._respond(401, {'error': 'unauthorized'})
                return
            self._respond(200, {'availability': self._t2_availability()})
            return
        self._respond(404, {'error': 'not_found'})

    def do_POST(self) -> None:  # noqa: N802 - http.server 约定
        path = self.path.rstrip('/')
        if path == RUNNER_API_PATH:
            self._handle_t1()
            return
        if path == T2_RUNNER_API_PATH:
            self._handle_t2()
            return
        self._respond(404, {'error': 'not_found'})

    # ── 内部 ──────────────────────────────────────────────────
    def _handle_t1(self) -> None:
        if not self._authorized():
            self._respond(401, {'error': 'unauthorized'})
            return
        try:
            payload = self._read_json()
            invocation = invocation_from_dict(payload.get('invocation') or {})
            validate_invocation(invocation)
        except (SandboxConfigurationError, KeyError, TypeError, ValueError) as exc:
            logger.warning('拒绝非法 T1 沙箱请求：%s', exc)
            self._respond(400, {'error': str(exc)})
            return

        execution = self.executor.run(invocation)
        self._respond(200, {'execution': execution_to_dict(execution)})

    def _handle_t2(self) -> None:
        if not self._authorized():
            self._respond(401, {'error': 'unauthorized'})
            return
        if self.t2_executor is None:
            # 不静默降级：runner 未装配 T2 时明确拒绝。
            self._respond(503, {'error': 'T2_RUNTIME_UNAVAILABLE: t2 runner 未装配'})
            return
        try:
            payload = self._read_json()
            invocation = t2_invocation_from_dict(payload.get('invocation') or {})
            validate_t2_invocation(invocation, self.t2_executor.policy)
        except (SandboxConfigurationError, KeyError, TypeError, ValueError) as exc:
            logger.warning('拒绝非法 T2 沙箱请求：%s', exc)
            self._respond(400, {'error': str(exc)})
            return

        execution = self.t2_executor.run(invocation)
        self._respond(200, {'execution': execution_to_dict(execution)})

    def _t2_availability(self) -> dict:
        if self.t2_executor is None:
            return availability_to_dict(SandboxRuntimeAvailability(
                available=False,
                runtime='gvisor',
                runtime_name='',
                detail='T2_RUNTIME_UNAVAILABLE: t2 runner 未装配（缺 gVisor/runsc 安装）',
            ))
        return availability_to_dict(self.t2_executor.availability())

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
        t2_executor: T2DockerExecutor | None = None,
    ) -> None:
        if not token:
            raise SandboxConfigurationError(
                f'{RUNNER_TOKEN_ENV} 未配置：拒绝启动无鉴权的沙箱 runner'
            )
        handler = type(
            'BoundSandboxRunnerHandler',
            (SandboxRunnerRequestHandler,),
            {'executor': executor, 't2_executor': t2_executor, 'token': token},
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


def _build_t2_executor() -> T2DockerExecutor | None:
    """装配 T2 执行器；失败不阻断 T1 runner，但 T2 端点会明确报不可用。"""
    try:
        policy: T2Policy = load_t2_policy()
        return T2DockerExecutor(policy)
    except SandboxConfigurationError as exc:
        logger.error('T2 执行器装配失败（T2 端点将返回 T2_RUNTIME_UNAVAILABLE）：%s', exc)
        return None


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )
    token = (os.environ.get(RUNNER_TOKEN_ENV) or '').strip()
    bind_host = os.environ.get('AGENT_SANDBOX_RUNNER_BIND', '0.0.0.0')
    port = int(os.environ.get('AGENT_SANDBOX_RUNNER_PORT', str(AGENT_SANDBOX_RUNNER_PORT)))
    t2_executor = _build_t2_executor()
    try:
        server = SandboxRunnerServer(
            executor=HostCliDockerExecutor(
                docker_binary=os.environ.get('AGENT_SANDBOX_DOCKER_BIN', 'docker'),
            ),
            token=token,
            bind_host=bind_host,
            port=port,
            t2_executor=t2_executor,
        )
    except SandboxConfigurationError as exc:
        logger.error('沙箱 runner 启动失败：%s', exc)
        return 2
    if t2_executor is not None:
        # 不在启动路径上探测 docker info（部分宿主上偶发很慢）：首次 T2 请求时探测，
        # 不可用会以 T2_RUNTIME_UNAVAILABLE 明确失败。
        logger.info('T2 执行器已装配：runtime=%s（首次请求时探测可用性）',
                    t2_executor.policy.runtime_name)
    logger.info('沙箱 runner 已启动：%s:%s', bind_host, server.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info('沙箱 runner 收到中断，退出')
    finally:
        server.stop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
