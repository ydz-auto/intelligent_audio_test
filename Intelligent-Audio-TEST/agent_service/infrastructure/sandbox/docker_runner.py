# -*- coding: utf-8 -*-
"""T1 一次性 Docker 容器执行器（方案 doc/agent化/07 §7，INT-2455）。

Docker 访问方式（负责人红线，不得走捷径）
--------------------------------------------
生产 ``agent_service`` 容器**不得挂载 ``/var/run/docker.sock``**。本模块提供两
种合法通道，由 ``AGENT_SANDBOX_EXECUTOR_MODE`` 选择：

- ``RUNNER_HTTP``（生产默认）：把容器规格 POST 给独立 runner/sidecar
  （``runner_service.py``，只有它持有 Docker 访问权），本进程只走 HTTP。
- ``HOST_CLI``（开发机 / 宿主 runner）：直接调用宿主 docker CLI。仅用于
  Windows 开发机（Docker Desktop 的 Linux 容器）与 runner 进程内部。

两条通道共用同一份 ``--mount``/加固参数构造，行为一致。

容器加固（与方案 §7 逐条对应）
------------------------------
非 root（``--user``）、``--network=none``、``--read-only``、``--cap-drop=ALL``、
``--security-opt no-new-privileges``、``--pids-limit=128``、``--memory=512m``、
``--cpus=1``、``/tmp`` tmpfs 64m；Skill 只读挂载、仅 ``/work`` 可写；超时 60s；
输出限 1MB（超限即杀容器并记录 ``output_truncated``）。
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping, Sequence
from urllib import error as urlerror
from urllib import request as urlrequest

from agent_service.application.sandbox_runner import (
    SKILL_MOUNT_PATH,
    WORK_MOUNT_PATH,
    ContainerExecution,
    ContainerInvocation,
    ContainerLimits,
    SandboxConfigurationError,
    SandboxExecutor,
    assert_env_is_credential_free,
    assert_no_docker_socket,
)

logger = logging.getLogger(__name__)

#: runner/sidecar 的 HTTP 契约版本（一次容器 = 一次请求）。
RUNNER_API_PATH = '/v1/sandbox/execute'
RUNNER_HEALTH_PATH = '/healthz'
#: HTTP 通道在容器超时之外多给的等待余量（秒）：传输 + runner 清理容器。
RUNNER_HTTP_GRACE_SECONDS = 30
#: 清理/探测类 docker 子命令超时（秒）。
DOCKER_ADMIN_TIMEOUT_SECONDS = 30
#: 容器标签（清理遗留容器、审计定位用）。
SANDBOX_CONTAINER_LABEL = 'agent-sandbox=t1'

#: docker run 的退出码 125 = docker 自身无法启动容器（镜像不存在、参数非法）。
DOCKER_START_FAILURE_EXIT_CODE = 125


class DockerRunnerMode(str, Enum):
    """Docker 访问通道。"""

    RUNNER_HTTP = 'runner_http'
    HOST_CLI = 'host_cli'


@dataclass(frozen=True)
class DockerRunnerConfig:
    """执行器配置（全部来自环境变量，禁止在代码里散落阈值）。"""

    mode: DockerRunnerMode = DockerRunnerMode.RUNNER_HTTP
    docker_binary: str = 'docker'
    runner_url: str = ''
    runner_token: str = ''
    limits: ContainerLimits = ContainerLimits()

    @classmethod
    def from_env(cls) -> 'DockerRunnerConfig':
        raw_mode = (os.environ.get('AGENT_SANDBOX_EXECUTOR_MODE') or 'runner_http').strip().lower()
        try:
            mode = DockerRunnerMode(raw_mode)
        except ValueError as exc:
            raise SandboxConfigurationError(
                f'AGENT_SANDBOX_EXECUTOR_MODE 非法：{raw_mode!r}'
            ) from exc
        return cls(
            mode=mode,
            docker_binary=os.environ.get('AGENT_SANDBOX_DOCKER_BIN', 'docker'),
            runner_url=(os.environ.get('AGENT_SANDBOX_RUNNER_URL') or '').strip().rstrip('/'),
            runner_token=(os.environ.get('AGENT_SANDBOX_RUNNER_TOKEN') or '').strip(),
            limits=build_limits_from_env(),
        )


def build_limits_from_env() -> ContainerLimits:
    """从环境变量构造容器上限；缺省值 = 方案 §7 的固定口径。"""
    return ContainerLimits(
        image=os.environ.get('AGENT_SANDBOX_IMAGE', 'python:3.11-slim'),
        memory=os.environ.get('AGENT_SANDBOX_MEMORY', '512m'),
        memory_swap=os.environ.get('AGENT_SANDBOX_MEMORY_SWAP', '512m'),
        cpus=float(os.environ.get('AGENT_SANDBOX_CPUS', '1')),
        pids_limit=int(os.environ.get('AGENT_SANDBOX_PIDS_LIMIT', '128')),
        tmpfs_size=os.environ.get('AGENT_SANDBOX_TMPFS_SIZE', '64m'),
        timeout_seconds=int(os.environ.get('AGENT_SANDBOX_TIMEOUT_SECONDS', '60')),
        output_limit_bytes=int(os.environ.get('AGENT_SANDBOX_OUTPUT_LIMIT_BYTES', str(1024 * 1024))),
        container_user=os.environ.get('AGENT_SANDBOX_CONTAINER_USER', '65534:65534'),
        interpreter=os.environ.get('AGENT_SANDBOX_INTERPRETER', 'python3'),
    )


# ── 容器规格校验与命令行构造 ────────────────────────────────────


def _normalize_host_path(raw: str, label: str) -> str:
    if not raw:
        raise SandboxConfigurationError(f'{label} 不能为空')
    path = Path(raw)
    if not path.is_absolute():
        raise SandboxConfigurationError(f'{label} 必须是绝对路径：{raw}')
    if not path.is_dir():
        raise SandboxConfigurationError(f'{label} 不存在或不是目录：{raw}')
    if ',' in raw or '\n' in raw:
        # --mount 以逗号分字段：路径里带逗号/换行会破坏挂载定义。
        raise SandboxConfigurationError(f'{label} 含非法字符（逗号/换行）：{raw}')
    assert_no_docker_socket(path, label)
    return str(path).replace('\\', '/')


def validate_invocation(invocation: ContainerInvocation) -> None:
    """执行前的硬校验：任何一条不满足都拒绝进容器。"""
    skill_root = Path(_normalize_host_path(invocation.skill_root, 'skill_root')).resolve()
    work_dir = Path(_normalize_host_path(invocation.work_dir, 'work_dir')).resolve()
    if skill_root == work_dir or skill_root in work_dir.parents or work_dir in skill_root.parents:
        raise SandboxConfigurationError('Skill 挂载与 /work 挂载不得重叠')
    if not invocation.name or any(ch.isspace() for ch in invocation.name):
        raise SandboxConfigurationError('容器名非法')
    if not invocation.limits.image:
        raise SandboxConfigurationError('沙箱镜像未配置')
    assert_env_is_credential_free(invocation.env)
    for arg in invocation.args:
        if '\x00' in arg:
            raise SandboxConfigurationError('参数含 NUL 字节')


def build_docker_run_argv(
    invocation: ContainerInvocation,
    docker_binary: str,
) -> list[str]:
    """构造 ``docker run`` 参数 — 安全参数集中在这里，测试逐条断言。"""
    limits = invocation.limits
    skill_source = str(Path(invocation.skill_root).resolve()).replace('\\', '/')
    work_source = str(Path(invocation.work_dir).resolve()).replace('\\', '/')
    script_in_container = f'{SKILL_MOUNT_PATH}/{invocation.script_relative_path}'

    argv: list[str] = [
        docker_binary, 'run',
        # 生命周期：容器名唯一，执行后由执行器显式 `docker rm -f`（需要 inspect 判定 OOM）。
        '--name', invocation.name,
        '--label', SANDBOX_CONTAINER_LABEL,
        # 网络：完全断网（DNS / 出站 / 宿主回环全部不可达）。
        '--network', 'none',
        # 文件系统：根只读；/tmp 是受限额的 tmpfs；只有 /work 是写挂载。
        '--read-only',
        '--tmpfs', f'/tmp:rw,noexec,nosuid,size={limits.tmpfs_size}',
        # 权限：非 root、丢弃全部 capability、禁止提权。
        '--user', limits.container_user,
        '--cap-drop', 'ALL',
        '--security-opt', 'no-new-privileges',
        # 资源上限。
        '--pids-limit', str(limits.pids_limit),
        '--memory', limits.memory,
        '--memory-swap', limits.memory_swap,
        '--cpus', str(limits.cpus),
        # 挂载：Skill 只读，/work 唯一可写产出卷。
        '--mount', f'type=bind,source={skill_source},target={SKILL_MOUNT_PATH},readonly',
        '--mount', f'type=bind,source={work_source},target={WORK_MOUNT_PATH}',
        '--workdir', WORK_MOUNT_PATH,
    ]
    # 容器内固定环境（不含任何宿主/业务配置）：
    for key, value in _container_base_env().items():
        argv.extend(['--env', f'{key}={value}'])
    for key, value in invocation.env.items():
        argv.extend(['--env', f'{key}={value}'])

    argv.append(limits.image)
    argv.append(limits.interpreter)
    argv.append(script_in_container)
    argv.extend(invocation.args)
    return argv


def _container_base_env() -> Mapping[str, str]:
    """只放运行 Python 脚本必需的非敏值；宿主环境变量一律不继承。"""
    return {
        'PYTHONUNBUFFERED': '1',
        'PYTHONDONTWRITEBYTECODE': '1',
        'HOME': '/tmp',
        'TMPDIR': '/tmp',
    }


# ── 输出采集（合计限 1MB，超限杀容器） ─────────────────────────


class _BoundedOutput:
    """线程安全的有界输出收集器：stdout+stderr 合计超限即标记截断并通知杀容器。"""

    def __init__(self, limit_bytes: int) -> None:
        self._limit = limit_bytes
        self._lock = threading.Lock()
        self._stdout: list[bytes] = []
        self._stderr: list[bytes] = []
        self._total = 0
        self.truncated = False

    def append(self, stream: str, data: bytes) -> bool:
        """写入一段输出；返回 False 表示已达上限（调用方应杀容器）。"""
        with self._lock:
            if self.truncated:
                return False
            remaining = self._limit - self._total
            if len(data) >= remaining:
                data = data[:remaining]
                self.truncated = True
            self._total += len(data)
            (self._stdout if stream == 'stdout' else self._stderr).append(data)
            return not self.truncated

    def _decode(self, chunks: list[bytes]) -> str:
        with self._lock:
            return b''.join(chunks).decode('utf-8', errors='replace')

    @property
    def stdout_text(self) -> str:
        return self._decode(self._stdout)

    @property
    def stderr_text(self) -> str:
        return self._decode(self._stderr)


def _pump(stream, out: _BoundedOutput, channel: str, on_limit) -> None:
    try:
        while True:
            chunk = stream.read(64 * 1024)
            if not chunk:
                return
            if not out.append(channel, chunk):
                on_limit()
                return
    except (ValueError, OSError):  # 流被主线程关闭
        return


# ── 宿主 docker CLI 执行器 ─────────────────────────────────────


class HostCliDockerExecutor(SandboxExecutor):
    """宿主 runner：直接调用 docker CLI 执行一次性容器（开发机 / sidecar 内部）。"""

    def __init__(
        self,
        limits: ContainerLimits | None = None,
        docker_binary: str = 'docker',
    ) -> None:
        self._limits = limits or build_limits_from_env()
        self._docker_binary = docker_binary

    @property
    def limits(self) -> ContainerLimits:
        return self._limits

    def run(self, invocation: ContainerInvocation) -> ContainerExecution:
        started = time.monotonic()
        try:
            validate_invocation(invocation)
            argv = build_docker_run_argv(invocation, self._docker_binary)
        except SandboxConfigurationError as exc:
            return ContainerExecution(exit_code=-1, error=str(exc))

        output = _BoundedOutput(self._limits.output_limit_bytes)
        limit_reached = threading.Event()

        def _mark_limit() -> None:
            # 只置位，由主线程统一终止：读线程直接调 docker 会与主线程的
            # inspect/等待竞态，且 Windows 上 docker CLI 在管道写满时无法自解。
            limit_reached.set()

        try:
            process = subprocess.Popen(
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self._docker_cli_env(),
            )
        except FileNotFoundError:
            return ContainerExecution(
                exit_code=-1,
                error=f'docker CLI 不可用：{self._docker_binary}',
            )
        except OSError as exc:
            return ContainerExecution(exit_code=-1, error=f'docker CLI 启动失败：{exc}')

        stdout_reader = threading.Thread(
            target=_pump, args=(process.stdout, output, 'stdout', _mark_limit), daemon=True
        )
        stderr_reader = threading.Thread(
            target=_pump, args=(process.stderr, output, 'stderr', _mark_limit), daemon=True
        )
        stdout_reader.start()
        stderr_reader.start()

        timed_out = False
        deadline = time.monotonic() + self._limits.timeout_seconds
        while process.poll() is None:
            if limit_reached.is_set():
                self._terminate(process, invocation.name)
                break
            if time.monotonic() >= deadline:
                timed_out = True
                self._terminate(process, invocation.name)
                break
            time.sleep(0.05)

        try:
            process.wait(timeout=DOCKER_ADMIN_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

        # 读线程可能仍阻塞在被杀进程的管道上，关闭后再 join，避免挂住。
        for stream in (process.stdout, process.stderr):
            try:
                stream.close()
            except OSError:
                pass
        stdout_reader.join(timeout=DOCKER_ADMIN_TIMEOUT_SECONDS)
        stderr_reader.join(timeout=DOCKER_ADMIN_TIMEOUT_SECONDS)

        state = self._inspect_state(invocation.name)
        self._remove_container(invocation.name)

        duration_ms = int((time.monotonic() - started) * 1000)
        exit_code = process.returncode if process.returncode is not None else -1
        stderr_text = output.stderr_text
        start_failed = exit_code == DOCKER_START_FAILURE_EXIT_CODE
        if start_failed:
            logger.warning('沙箱容器启动失败：%s', stderr_text[:500])
        return ContainerExecution(
            exit_code=exit_code,
            stdout=output.stdout_text,
            stderr=stderr_text,
            timed_out=timed_out,
            oom_killed=bool(state and state.get('oom_killed')),
            output_truncated=output.truncated,
            duration_ms=duration_ms,
            container_id=str((state or {}).get('container_id') or ''),
            killed_by_runner=timed_out or output.truncated,
            start_failed=start_failed,
            # 启动失败（125）走 error，供应用层判 FAILED/CONTAINER_START_FAILED。
            error=stderr_text[:1000] if start_failed else '',
        )

    # ── docker 子命令 ────────────────────────────────────────
    def _terminate(self, process: subprocess.Popen, name: str) -> None:
        """终止容器：先杀附着的 docker CLI（解除管道阻塞），再 ``docker rm -f``。

        实测（Docker Desktop / Windows）：管道写满时 ``docker kill`` 会长时间挂住，
        而 ``docker rm -f``（= kill + 删除）0.4s 内返回；故统一走 rm -f。
        """
        try:
            process.kill()
        except OSError:
            pass
        self._remove_container(name)

    def _docker_cli_env(self) -> dict[str, str]:
        """docker CLI 自己的环境（不是容器环境）：只保留 CLI 运行必需的键。"""
        keep = ('PATH', 'SystemRoot', 'SYSTEMROOT', 'COMSPEC', 'PATHEXT', 'TEMP', 'TMP',
                'HOME', 'USERPROFILE', 'DOCKER_HOST', 'DOCKER_CONFIG', 'DOCKER_TLS_VERIFY',
                'DOCKER_CERT_PATH', 'DOCKER_CONTEXT')
        return {k: v for k, v in os.environ.items() if k in keep}

    def _remove_container(self, name: str) -> None:
        self._run_admin(['rm', '--force', name])

    def _inspect_state(self, name: str) -> dict | None:
        result = self._run_admin(
            ['inspect', '--format',
             '{{.State.OOMKilled}}|{{.State.ExitCode}}|{{.Id}}', name]
        )
        if result is None or result.returncode != 0:
            return None
        parts = (result.stdout or '').strip().split('|')
        if len(parts) != 3:
            return None
        return {
            'oom_killed': parts[0].strip().lower() == 'true',
            'exit_code': parts[1].strip(),
            'container_id': parts[2].strip(),
        }

    def _run_admin(self, args: Sequence[str]) -> subprocess.CompletedProcess | None:
        try:
            return subprocess.run(
                [self._docker_binary, *args],
                capture_output=True,
                text=True,
                timeout=DOCKER_ADMIN_TIMEOUT_SECONDS,
                env=self._docker_cli_env(),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning('docker %s 失败：%s', ' '.join(args), exc)
            return None


# ── 独立 runner（HTTP 通道）执行器 ────────────────────────────


def validate_runner_url(url: str) -> str:
    """runner 地址必须是 HTTP(S)；禁止 unix socket / docker.sock 直连。"""
    cleaned = (url or '').strip().rstrip('/')
    if not cleaned:
        raise SandboxConfigurationError('AGENT_SANDBOX_RUNNER_URL 未配置')
    lowered = cleaned.lower()
    if not (lowered.startswith('http://') or lowered.startswith('https://')):
        raise SandboxConfigurationError(f'runner 地址必须是 http(s)：{url}')
    if 'docker.sock' in lowered:
        raise SandboxConfigurationError('runner 地址不得指向 docker.sock')
    return cleaned


class HttpRunnerDockerExecutor(SandboxExecutor):
    """生产通道：agent_service 只发 HTTP，不接触 Docker。"""

    def __init__(
        self,
        runner_url: str,
        limits: ContainerLimits | None = None,
        runner_token: str = '',
    ) -> None:
        self._runner_url = validate_runner_url(runner_url)
        self._limits = limits or build_limits_from_env()
        self._runner_token = (runner_token or '').strip()

    @property
    def limits(self) -> ContainerLimits:
        return self._limits

    def run(self, invocation: ContainerInvocation) -> ContainerExecution:
        try:
            validate_invocation(invocation)
        except SandboxConfigurationError as exc:
            return ContainerExecution(exit_code=-1, error=str(exc))

        payload = json.dumps(
            {'protocol_version': 1, 'invocation': invocation_to_dict(invocation)},
            ensure_ascii=False,
        ).encode('utf-8')
        request = urlrequest.Request(
            self._runner_url + RUNNER_API_PATH,
            data=payload,
            headers={
                'Content-Type': 'application/json',
                'X-Sandbox-Runner-Token': self._runner_token,
            },
            method='POST',
        )
        timeout = self._limits.timeout_seconds + RUNNER_HTTP_GRACE_SECONDS
        try:
            with urlrequest.urlopen(request, timeout=timeout) as response:
                body = response.read()
        except urlerror.HTTPError as exc:
            return ContainerExecution(
                exit_code=-1,
                error=f'runner 返回 HTTP {exc.code}：{exc.reason}',
            )
        except (urlerror.URLError, TimeoutError, OSError) as exc:
            return ContainerExecution(exit_code=-1, error=f'runner 不可达：{exc}')

        try:
            data = json.loads(body.decode('utf-8'))
        except (ValueError, UnicodeDecodeError) as exc:
            return ContainerExecution(exit_code=-1, error=f'runner 响应非法：{exc}')
        try:
            return execution_from_dict(data.get('execution') or {})
        except (KeyError, TypeError, ValueError) as exc:
            return ContainerExecution(exit_code=-1, error=f'runner 响应字段非法：{exc}')


def build_sandbox_executor(config: DockerRunnerConfig | None = None) -> SandboxExecutor:
    """组合根：按配置选通道。生产默认 HTTP（没有 URL 直接失败，不回落 socket）。"""
    cfg = config or DockerRunnerConfig.from_env()
    if cfg.mode is DockerRunnerMode.HOST_CLI:
        return HostCliDockerExecutor(limits=cfg.limits, docker_binary=cfg.docker_binary)
    return HttpRunnerDockerExecutor(
        cfg.runner_url, limits=cfg.limits, runner_token=cfg.runner_token
    )


# ── runner HTTP 契约序列化（客户端与服务端共用） ───────────────


def invocation_to_dict(invocation: ContainerInvocation) -> dict:
    return {
        'name': invocation.name,
        'skill_root': invocation.skill_root,
        'work_dir': invocation.work_dir,
        'script_relative_path': invocation.script_relative_path,
        'args': list(invocation.args),
        'env': dict(invocation.env),
        'limits': {
            'image': invocation.limits.image,
            'memory': invocation.limits.memory,
            'memory_swap': invocation.limits.memory_swap,
            'cpus': invocation.limits.cpus,
            'pids_limit': invocation.limits.pids_limit,
            'tmpfs_size': invocation.limits.tmpfs_size,
            'timeout_seconds': invocation.limits.timeout_seconds,
            'output_limit_bytes': invocation.limits.output_limit_bytes,
            'container_user': invocation.limits.container_user,
            'interpreter': invocation.limits.interpreter,
        },
    }


def invocation_from_dict(data: Mapping) -> ContainerInvocation:
    limits = ContainerLimits(**dict(data.get('limits') or {}))
    return ContainerInvocation(
        name=str(data['name']),
        skill_root=str(data['skill_root']),
        work_dir=str(data['work_dir']),
        script_relative_path=str(data['script_relative_path']),
        args=tuple(data.get('args') or ()),
        env={str(k): str(v) for k, v in (data.get('env') or {}).items()},
        limits=limits,
    )


def execution_to_dict(execution: ContainerExecution) -> dict:
    return {
        'exit_code': execution.exit_code,
        'stdout': execution.stdout,
        'stderr': execution.stderr,
        'timed_out': execution.timed_out,
        'oom_killed': execution.oom_killed,
        'output_truncated': execution.output_truncated,
        'duration_ms': execution.duration_ms,
        'container_id': execution.container_id,
        'killed_by_runner': execution.killed_by_runner,
        'start_failed': execution.start_failed,
        'error': execution.error,
    }


def execution_from_dict(data: Mapping) -> ContainerExecution:
    return ContainerExecution(
        exit_code=int(data.get('exit_code', -1)),
        stdout=str(data.get('stdout') or ''),
        stderr=str(data.get('stderr') or ''),
        timed_out=bool(data.get('timed_out')),
        oom_killed=bool(data.get('oom_killed')),
        output_truncated=bool(data.get('output_truncated')),
        duration_ms=int(data.get('duration_ms') or 0),
        container_id=str(data.get('container_id') or ''),
        killed_by_runner=bool(data.get('killed_by_runner')),
        start_failed=bool(data.get('start_failed')),
        error=str(data.get('error') or ''),
    )
