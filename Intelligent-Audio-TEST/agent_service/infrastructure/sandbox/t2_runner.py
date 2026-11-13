# -*- coding: utf-8 -*-
"""T2 不可信代码执行器：gVisor ``runsc``（方案 doc/agent化/07 §7，INT-2489）。

定位
----
模型生成的代码（驱动、适配器、分析脚本）在 gVisor 里执行：禁网、无宿主挂载、
无凭证、非 root、只读根 + ``/work`` 输出卷、pids/CPU/内存/时长硬限、用完即毁。

运行时可用性
------------
只有 ``docker info`` 的 runtime 列表里注册了 ``runsc`` 才可用；否则
``availability()`` 返回不可用，应用层映射为 ``T2_RUNTIME_UNAVAILABLE`` 并
**明确失败**——本模块没有任何回落到 runc/T1 的分支。选择 Firecracker 时同理：
本期只保留配置开关，未实现即显式不可用（卡内注明，生产运维归 INT-2456）。

Docker 访问方式与 T1 相同：由宿主/独立 runner 调用 docker CLI；agent_service
本身不挂 docker.sock。

容器加固（逐条对应方案 §7「T2」行）
-----------------------------------
``--runtime runsc``、``--network none``（白名单出口例外：只挂 internal 网络 +
代理环境变量）、``--read-only``、``/tmp`` tmpfs、``--user 65534:65534``、
``--cap-drop ALL``、``--security-opt no-new-privileges``、pids/CPU/内存硬限、
只读输入卷 ``/input`` + 可写 ``/work``；唯一例外是白名单出口代理，且执行结果
会记录代码来源与 sha256。
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Mapping
from urllib import error as urlerror
from urllib import request as urlrequest

from agent_service.application.sandbox_runner import (
    INPUT_MOUNT_PATH,
    WORK_MOUNT_PATH,
    ContainerExecution,
    ContainerLimits,
    SandboxConfigurationError,
    SandboxRuntimeAvailability,
    T2ContainerInvocation,
    UntrustedCodeExecutor,
    assert_env_is_credential_free,
    assert_no_docker_socket,
)
from agent_service.infrastructure.sandbox.docker_runner import (
    DOCKER_START_FAILURE_EXIT_CODE,
    DockerRunnerMode,
    execute_docker_container,
    execution_from_dict,
    run_docker_admin,
    validate_runner_url,
)
from agent_service.infrastructure.sandbox.policy import (
    RUNTIME_FIRECRACKER,
    RUNTIME_GVISOR,
    T2Policy,
    load_t2_policy,
)

logger = logging.getLogger(__name__)

#: 容器标签（遗留容器清理 / 证据采集）。
T2_CONTAINER_LABEL = 'agent-sandbox=t2'
#: 运行时不可用的原因码（与 ``SandboxFailureReason`` 同值，跨进程/HTTP 也认）。
T2_RUNTIME_UNAVAILABLE = 'T2_RUNTIME_UNAVAILABLE'
#: 运行时探测超时：``docker info`` 在部分 Windows 宿主上偶发很慢。
RUNTIME_PROBE_TIMEOUT_SECONDS = 90
#: runner/sidecar 的 T2 契约路径（一次阶段 = 一次请求）。
T2_RUNNER_API_PATH = '/v1/sandbox/t2/execute'
T2_RUNTIME_API_PATH = '/v1/sandbox/t2/runtime'
#: HTTP 通道在阶段超时之外多给的等待余量（秒）：传输 + runner 清理容器。
RUNNER_HTTP_GRACE_SECONDS = 30

#: T2 容器内固定环境（不含任何宿主/业务配置）。
_T2_BASE_ENV: Mapping[str, str] = {
    'PYTHONUNBUFFERED': '1',
    'PYTHONDONTWRITEBYTECODE': '1',
    # 字节码写 /work（/input 只读）；compileall 因此不会因只读根失败。
    'PYTHONPYCACHEPREFIX': '/work/.pycache',
    'PYTHONPATH': '/input',
    'HOME': '/tmp',
    'TMPDIR': '/tmp',
}


# ── 运行时探测 ─────────────────────────────────────────────────


@dataclass(frozen=True)
class DockerRuntimeProbe:
    """``docker info`` 的 runtime 探测结果。"""

    ok: bool
    runtimes: Mapping[str, str]
    error: str = ''


def probe_docker_runtimes(docker_binary: str = 'docker') -> DockerRuntimeProbe:
    result = run_docker_admin(
        ['info', '--format', '{{json .Runtimes}}'],
        docker_binary,
        timeout=RUNTIME_PROBE_TIMEOUT_SECONDS,
    )
    if result is None:
        return DockerRuntimeProbe(False, {}, f'docker CLI 探测失败：{docker_binary}')
    if result.returncode != 0:
        return DockerRuntimeProbe(
            False, {}, f'docker daemon 不可用：{(result.stderr or "").strip()[:300]}'
        )
    try:
        data = json.loads((result.stdout or '{}').strip() or '{}')
    except ValueError as exc:
        return DockerRuntimeProbe(False, {}, f'docker info 返回非法 JSON：{exc}')
    if not isinstance(data, dict):
        return DockerRuntimeProbe(False, {}, 'docker info 返回非对象')
    return DockerRuntimeProbe(True, {str(k): str(v) for k, v in data.items()})


def probe_t2_runtime(
    policy: T2Policy,
    docker_binary: str | None = None,
) -> SandboxRuntimeAvailability:
    """探测 T2 运行时；不可用时给出可操作的说明（不静默、不降级）。"""
    binary = docker_binary or policy.docker_binary
    if policy.runtime == RUNTIME_FIRECRACKER:
        reason = (
            'Firecracker 通道本期未实现（本卡只交付 gVisor 路径）'
            if policy.firecracker_enabled
            else 'Firecracker 未启用（AGENT_SANDBOX_T2_FIRECRACKER_ENABLED=false）'
        )
        return SandboxRuntimeAvailability(
            available=False,
            runtime=RUNTIME_FIRECRACKER,
            runtime_name='firecracker',
            detail=f'{T2_RUNTIME_UNAVAILABLE}: {reason}',
        )

    probe = probe_docker_runtimes(binary)
    if not probe.ok:
        return SandboxRuntimeAvailability(
            available=False,
            runtime=RUNTIME_GVISOR,
            runtime_name=policy.runtime_name,
            detail=f'{T2_RUNTIME_UNAVAILABLE}: {probe.error}',
        )
    if policy.runtime_name not in probe.runtimes:
        return SandboxRuntimeAvailability(
            available=False,
            runtime=RUNTIME_GVISOR,
            runtime_name=policy.runtime_name,
            detail=(
                f'{T2_RUNTIME_UNAVAILABLE}: docker 未注册 runtime '
                f'{policy.runtime_name!r}（现有：{sorted(probe.runtimes)}）；'
                f'需在宿主安装 gVisor 并注册 {policy.runsc_binary}（生产等价环境）'
            ),
        )
    return SandboxRuntimeAvailability(
        available=True,
        runtime=RUNTIME_GVISOR,
        runtime_name=policy.runtime_name,
        detail=f'gVisor runtime {policy.runtime_name!r} 已注册（{probe.runtimes[policy.runtime_name]}）',
    )


# ── 请求校验与命令行构造 ───────────────────────────────────────


def _normalize_mount_path(raw: str, label: str) -> str:
    if not raw:
        raise SandboxConfigurationError(f'{label} 不能为空')
    path = Path(raw)
    if not path.is_absolute():
        raise SandboxConfigurationError(f'{label} 必须是绝对路径：{raw}')
    if not path.is_dir():
        raise SandboxConfigurationError(f'{label} 不存在或不是目录：{raw}')
    if ',' in raw or '\n' in raw or '\r' in raw:
        raise SandboxConfigurationError(f'{label} 含非法字符（逗号/换行）：{raw}')
    assert_no_docker_socket(path, label)
    return str(path.resolve()).replace('\\', '/')


def validate_t2_invocation(
    invocation: T2ContainerInvocation,
    policy: T2Policy,
) -> None:
    """执行前硬校验：任何一条不满足都拒绝进容器（含防降级）。"""
    input_root = Path(_normalize_mount_path(invocation.input_root, 'input_root'))
    work_dir = Path(_normalize_mount_path(invocation.work_dir, 'work_dir'))
    if (
        input_root == work_dir
        or input_root in work_dir.parents
        or work_dir in input_root.parents
    ):
        raise SandboxConfigurationError('T2 输入卷与 /work 不得重叠')
    if not invocation.runtime or invocation.runtime != policy.runtime_name:
        # 防降级：不允许用任意 --runtime（尤其 runc）冒充 T2。
        raise SandboxConfigurationError(
            f'T2 运行时必须是已注册的 {policy.runtime_name!r}，收到 '
            f'{invocation.runtime!r}（禁止降级到 runc/T1）'
        )
    if not invocation.name or any(ch.isspace() for ch in invocation.name):
        raise SandboxConfigurationError('T2 容器名非法')
    if not invocation.command:
        raise SandboxConfigurationError('T2 命令不能为空')
    if any('\x00' in arg for arg in invocation.command):
        raise SandboxConfigurationError('T2 命令参数含 NUL 字节')
    if not invocation.limits.image:
        raise SandboxConfigurationError('T2 沙箱镜像未配置')
    if invocation.limits.container_user in ('0', '0:0', 'root'):
        raise SandboxConfigurationError('T2 沙箱容器禁止以 root 运行')
    if invocation.network != 'none':
        if not (policy.egress.enabled and invocation.network == policy.egress.network):
            raise SandboxConfigurationError(
                f'T2 默认禁网；网络 {invocation.network!r} 未在出口白名单配置内'
            )
    assert_env_is_credential_free(invocation.env)


def build_t2_run_argv(
    invocation: T2ContainerInvocation,
    docker_binary: str = 'docker',
) -> list[str]:
    """构造 ``docker run`` 参数 — T2 加固参数集中在这里，测试逐条断言。"""
    limits = invocation.limits
    input_source = str(Path(invocation.input_root).resolve()).replace('\\', '/')
    work_source = str(Path(invocation.work_dir).resolve()).replace('\\', '/')

    argv: list[str] = [
        docker_binary, 'run',
        '--name', invocation.name,
        '--label', T2_CONTAINER_LABEL,
        # 运行时：gVisor（缺失时 docker 返回 125，执行器映射为运行时不可用）。
        '--runtime', invocation.runtime,
        # 网络：默认完全断网；白名单出口只挂 internal 网络。
        '--network', invocation.network,
        # 文件系统：只读根 + 受限额 tmpfs；只有 /work 可写。
        '--read-only',
        '--tmpfs', f'/tmp:rw,noexec,nosuid,size={limits.tmpfs_size}',
        # 权限：非 root、丢弃全部 capability、禁止提权。
        '--user', limits.container_user,
        '--cap-drop', 'ALL',
        '--security-opt', 'no-new-privileges',
        # 资源硬限。
        '--pids-limit', str(limits.pids_limit),
        '--memory', limits.memory,
        '--memory-swap', limits.memory_swap,
        '--cpus', str(limits.cpus),
        # 挂载：只有只读输入卷 + 可写产物卷（无宿主目录挂载）。
        '--mount', f'type=bind,source={input_source},target={INPUT_MOUNT_PATH},readonly',
        '--mount', f'type=bind,source={work_source},target={WORK_MOUNT_PATH}',
        '--workdir', WORK_MOUNT_PATH,
    ]
    for key, value in _T2_BASE_ENV.items():
        argv.extend(['--env', f'{key}={value}'])
    for key, value in invocation.env.items():
        argv.extend(['--env', f'{key}={value}'])

    argv.append(limits.image)
    argv.extend(invocation.command)
    return argv


# ── 执行器 ─────────────────────────────────────────────────────


def _runtime_failure_hint(text: str) -> bool:
    """docker 125 的报错是否指向运行时缺失（而非镜像/参数问题）。"""
    lowered = (text or '').lower()
    return 'unknown or invalid runtime name' in lowered or (
        'runtime' in lowered and 'runsc' in lowered
    )


class T2DockerExecutor(UntrustedCodeExecutor):
    """T2 一次性容器执行器（宿主 docker CLI 通道，需宿主注册 ``runsc``）。"""

    def __init__(
        self,
        policy: T2Policy | None = None,
        *,
        availability: SandboxRuntimeAvailability | None = None,
    ) -> None:
        self._policy = policy or load_t2_policy()
        self._injected_availability = availability
        self._cached_availability: SandboxRuntimeAvailability | None = None

    @property
    def policy(self) -> T2Policy:
        return self._policy

    @property
    def limits(self) -> ContainerLimits:
        return self._policy.container_limits

    @property
    def runtime(self) -> str:
        return self._policy.runtime

    @property
    def runtime_name(self) -> str:
        return self._policy.runtime_name

    def availability(self) -> SandboxRuntimeAvailability:
        if self._injected_availability is not None:
            return self._injected_availability
        if self._cached_availability is None:
            self._cached_availability = probe_t2_runtime(self._policy)
            if not self._cached_availability.available:
                logger.warning('T2 运行时不可用：%s', self._cached_availability.detail)
        return self._cached_availability

    def run(self, invocation: T2ContainerInvocation) -> ContainerExecution:
        availability = self.availability()
        if not availability.available:
            # 明确失败：绝不回落到 runc/T1。
            return ContainerExecution(
                exit_code=-1,
                error=availability.detail,
                runtime=self.runtime,
                runtime_unavailable=True,
            )
        try:
            validate_t2_invocation(invocation, self._policy)
            argv = build_t2_run_argv(invocation, self._policy.docker_binary)
        except SandboxConfigurationError as exc:
            return ContainerExecution(
                exit_code=-1, error=str(exc), runtime=self.runtime
            )

        execution = execute_docker_container(
            argv,
            invocation.name,
            invocation.limits,
            self._policy.docker_binary,
            timeout_seconds=invocation.timeout_seconds or self.limits.timeout_seconds,
            runtime=self.runtime,
        )
        # 极端情况下 runtime 注册后仍可能启动失败（二进制缺失/内核不支持）：
        # 125 + 运行时字样同样按运行时不可用上报，避免被误解成代码失败。
        if (
            execution.exit_code == DOCKER_START_FAILURE_EXIT_CODE
            and _runtime_failure_hint(execution.error or execution.stderr)
        ):
            return replace(
                execution,
                runtime_unavailable=True,
                error=f'{T2_RUNTIME_UNAVAILABLE}: {execution.error or execution.stderr}',
            )
        return execution


# ── runner HTTP 契约（客户端与服务端共用序列化） ────────────────


def t2_invocation_to_dict(invocation: T2ContainerInvocation) -> dict:
    limits = invocation.limits
    return {
        'name': invocation.name,
        'input_root': invocation.input_root,
        'work_dir': invocation.work_dir,
        'command': list(invocation.command),
        'runtime': invocation.runtime,
        'env': dict(invocation.env),
        'network': invocation.network,
        'timeout_seconds': invocation.timeout_seconds,
        'limits': {
            'image': limits.image,
            'memory': limits.memory,
            'memory_swap': limits.memory_swap,
            'cpus': limits.cpus,
            'pids_limit': limits.pids_limit,
            'tmpfs_size': limits.tmpfs_size,
            'timeout_seconds': limits.timeout_seconds,
            'output_limit_bytes': limits.output_limit_bytes,
            'container_user': limits.container_user,
            'interpreter': limits.interpreter,
        },
    }


def t2_invocation_from_dict(data: Mapping) -> T2ContainerInvocation:
    limits = ContainerLimits(**dict(data.get('limits') or {}))
    return T2ContainerInvocation(
        name=str(data['name']),
        input_root=str(data['input_root']),
        work_dir=str(data['work_dir']),
        command=tuple(str(arg) for arg in (data.get('command') or ())),
        runtime=str(data.get('runtime') or ''),
        limits=limits,
        env={str(k): str(v) for k, v in (data.get('env') or {}).items()},
        network=str(data.get('network') or 'none'),
        timeout_seconds=int(data.get('timeout_seconds') or 0),
    )


def availability_to_dict(availability: SandboxRuntimeAvailability) -> dict:
    return {
        'available': availability.available,
        'runtime': availability.runtime,
        'runtime_name': availability.runtime_name,
        'detail': availability.detail,
    }


def availability_from_dict(data: Mapping) -> SandboxRuntimeAvailability:
    return SandboxRuntimeAvailability(
        available=bool(data.get('available')),
        runtime=str(data.get('runtime') or ''),
        runtime_name=str(data.get('runtime_name') or ''),
        detail=str(data.get('detail') or ''),
    )


class HttpRunnerT2Executor(UntrustedCodeExecutor):
    """生产通道：agent_service 只发 HTTP，不接触 Docker（runner 持有 runsc）。"""

    def __init__(
        self,
        runner_url: str,
        policy: T2Policy | None = None,
        runner_token: str = '',
    ) -> None:
        self._runner_url = validate_runner_url(runner_url)
        self._policy = policy or load_t2_policy()
        self._runner_token = (runner_token or os.environ.get(
            'AGENT_SANDBOX_RUNNER_TOKEN', '')).strip()
        self._cached_availability: SandboxRuntimeAvailability | None = None

    @property
    def limits(self) -> ContainerLimits:
        return self._policy.container_limits

    @property
    def runtime(self) -> str:
        return self._policy.runtime

    @property
    def runtime_name(self) -> str:
        return self._policy.runtime_name

    def availability(self) -> SandboxRuntimeAvailability:
        if self._cached_availability is None:
            self._cached_availability = self._probe_availability()
            if not self._cached_availability.available:
                logger.warning('T2 runner 报告运行时不可用：%s', self._cached_availability.detail)
        return self._cached_availability

    def _probe_availability(self) -> SandboxRuntimeAvailability:
        request = urlrequest.Request(
            self._runner_url + T2_RUNTIME_API_PATH,
            headers={'X-Sandbox-Runner-Token': self._runner_token},
            method='GET',
        )
        try:
            with urlrequest.urlopen(request, timeout=RUNNER_HTTP_GRACE_SECONDS) as response:
                data = json.loads(response.read().decode('utf-8'))
        except urlerror.HTTPError as exc:
            return SandboxRuntimeAvailability(
                False, self.runtime, self.runtime_name,
                f'{T2_RUNTIME_UNAVAILABLE}: runner 返回 HTTP {exc.code}（{exc.reason}）',
            )
        except (urlerror.URLError, TimeoutError, OSError, ValueError) as exc:
            return SandboxRuntimeAvailability(
                False, self.runtime, self.runtime_name,
                f'{T2_RUNTIME_UNAVAILABLE}: runner 不可达/响应非法（{exc}）',
            )
        return availability_from_dict(data.get('availability') or {})

    def run(self, invocation: T2ContainerInvocation) -> ContainerExecution:
        availability = self.availability()
        if not availability.available:
            return ContainerExecution(
                exit_code=-1,
                error=availability.detail,
                runtime=self.runtime,
                runtime_unavailable=True,
            )
        payload = json.dumps(
            {'protocol_version': 1, 'invocation': t2_invocation_to_dict(invocation)},
            ensure_ascii=False,
        ).encode('utf-8')
        request = urlrequest.Request(
            self._runner_url + T2_RUNNER_API_PATH,
            data=payload,
            headers={
                'Content-Type': 'application/json',
                'X-Sandbox-Runner-Token': self._runner_token,
            },
            method='POST',
        )
        timeout = (
            invocation.timeout_seconds or self.limits.timeout_seconds
        ) + RUNNER_HTTP_GRACE_SECONDS
        try:
            with urlrequest.urlopen(request, timeout=timeout) as response:
                body = response.read()
        except urlerror.HTTPError as exc:
            return ContainerExecution(
                exit_code=-1,
                error=f'runner 返回 HTTP {exc.code}：{exc.reason}',
                runtime=self.runtime,
            )
        except (urlerror.URLError, TimeoutError, OSError) as exc:
            return ContainerExecution(
                exit_code=-1, error=f'runner 不可达：{exc}', runtime=self.runtime
            )
        try:
            data = json.loads(body.decode('utf-8'))
        except (ValueError, UnicodeDecodeError) as exc:
            return ContainerExecution(
                exit_code=-1, error=f'runner 响应非法：{exc}', runtime=self.runtime
            )
        try:
            return execution_from_dict(data.get('execution') or {})
        except (KeyError, TypeError, ValueError) as exc:
            return ContainerExecution(
                exit_code=-1, error=f'runner 响应字段非法：{exc}', runtime=self.runtime
            )


def build_t2_executor(
    policy: T2Policy | None = None,
    *,
    mode: str | None = None,
    runner_url: str | None = None,
    runner_token: str | None = None,
) -> UntrustedCodeExecutor:
    """组合根：按 ``AGENT_SANDBOX_EXECUTOR_MODE`` 选通道（与 T1 同口径）。

    - ``runner_http``（生产默认）：只发 HTTP，runner 侧持有 Docker/gVisor；
    - ``host_cli``：宿主 runner 进程或显式配置的开发机。

    生产默认下 ``AGENT_SANDBOX_RUNNER_URL`` 缺失即构造失败（fail closed），
    绝不回落到本地 docker CLI。
    """
    resolved_mode = (
        mode or os.environ.get('AGENT_SANDBOX_EXECUTOR_MODE') or 'runner_http'
    ).strip().lower()
    resolved_policy = policy or load_t2_policy()
    if resolved_mode == DockerRunnerMode.HOST_CLI.value:
        return T2DockerExecutor(resolved_policy)
    if resolved_mode != DockerRunnerMode.RUNNER_HTTP.value:
        raise SandboxConfigurationError(
            f'AGENT_SANDBOX_EXECUTOR_MODE 非法：{resolved_mode!r}'
        )
    url = runner_url if runner_url is not None else os.environ.get(
        'AGENT_SANDBOX_RUNNER_URL', '')
    token = runner_token if runner_token is not None else os.environ.get(
        'AGENT_SANDBOX_RUNNER_TOKEN', '')
    return HttpRunnerT2Executor(url, resolved_policy, token)
