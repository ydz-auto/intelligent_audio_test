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
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime
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
    parse_container_identity,
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

#: 镜像引用白名单正则（不允许以 ``-`` 开头，杜绝 ``--privileged`` 这类参数注入）。
IMAGE_REFERENCE_PATTERN = re.compile(
    r'^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}(:[A-Za-z0-9._-]{1,128})?(@sha256:[a-f0-9]{64})?$'
)
#: 容器名与 docker 允许的字符集一致：首字符不能是 ``-``。
CONTAINER_NAME_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$')
#: T1 脚本在 skill 内的固定子目录（应用层同样校验，这里是纵深防御）。
SCRIPTS_DIR_NAME = 'scripts'

#: 容器入口自限：``timeout -k <grace> <timeout> <interpreter> ...``。
TIMEOUT_BINARY = 'timeout'
DEFAULT_CONTAINER_KILL_GRACE_SECONDS = 5
#: 运行中巡检 ``/work`` 容量的间隔（秒）。
WORK_DIR_CHECK_INTERVAL_SECONDS = 1.0
DEFAULT_WORK_LIMIT_BYTES = 32 * 1024 * 1024
#: 孤儿容器回收：创建时间超过 timeout + 宽限即回收，默认每 30s 扫一次。
DEFAULT_ORPHAN_GRACE_SECONDS = 30
DEFAULT_REAPER_INTERVAL_SECONDS = 30
#: runner HTTP 响应读取上限（防止返回体撑爆 agent_service 内存）。
DEFAULT_RUNNER_RESPONSE_LIMIT_BYTES = 8 * 1024 * 1024

#: 默认 Skill 根目录 = ``<项目根>/skills``，与 ``agent_service.config.Config.SKILLS_ROOT``
#: 同源。这里按本文件位置本地计算，**禁止 import ``agent_service.config``**：
#: ``shared`` 的 ``BaseConfig`` 在类定义期就要求 ``DATABASE_URL`` / ``OSS_*``，而独立
#: runner 是只带沙箱 env 的 sidecar，导入业务配置会让裸 runner 启动即崩（INT-2494）。
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SKILLS_ROOT = str(_PROJECT_ROOT / 'skills')

_MEMORY_UNITS = {
    '': 1, 'b': 1,
    'k': 1024, 'kb': 1024, 'kib': 1024,
    'm': 1024 ** 2, 'mb': 1024 ** 2, 'mib': 1024 ** 2,
    'g': 1024 ** 3, 'gb': 1024 ** 3, 'gib': 1024 ** 3,
}
_MEMORY_PATTERN = re.compile(r'^([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]*)$')


class DockerRunnerMode(str, Enum):
    """Docker 访问通道。"""

    RUNNER_HTTP = 'runner_http'
    HOST_CLI = 'host_cli'


@dataclass(frozen=True)
class SandboxPolicy:
    """容器规格白名单与 runner 侧唯一限额口径（方案 §7，INT-2494）。

    调用方送来的 ``ContainerLimits`` 一律按本策略复核：镜像、解释器、脚本路径、
    非 root 身份、资源限额都只允许在白名单 / runner 配置范围内。
    """

    limits: ContainerLimits
    allowed_images: frozenset[str]
    allowed_interpreters: frozenset[str]
    skills_root: str = DEFAULT_SKILLS_ROOT
    work_limit_bytes: int = DEFAULT_WORK_LIMIT_BYTES
    container_kill_grace_seconds: int = DEFAULT_CONTAINER_KILL_GRACE_SECONDS
    orphan_grace_seconds: int = DEFAULT_ORPHAN_GRACE_SECONDS
    reaper_interval_seconds: int = DEFAULT_REAPER_INTERVAL_SECONDS

    def __post_init__(self) -> None:
        # fail closed：允许根确定不了就不放行，绝不能退化成「不校验 skill_root」。
        root = str(self.skills_root or '').strip()
        if not root or not Path(root).is_absolute():
            raise SandboxConfigurationError(
                f'沙箱 Skill 根目录未配置或不是绝对路径：{self.skills_root!r}'
            )

    @classmethod
    def from_env(cls) -> 'SandboxPolicy':
        limits = build_limits_from_env()
        images = _split_csv(os.environ.get('AGENT_SANDBOX_ALLOWED_IMAGES')) or {limits.image}
        interpreters = (
            _split_csv(os.environ.get('AGENT_SANDBOX_ALLOWED_INTERPRETERS'))
            or {limits.interpreter}
        )
        return cls(
            limits=limits,
            allowed_images=frozenset(images),
            allowed_interpreters=frozenset(interpreters),
            skills_root=_configured_skills_root(),
            work_limit_bytes=int(
                os.environ.get('AGENT_SANDBOX_WORK_LIMIT_BYTES', str(DEFAULT_WORK_LIMIT_BYTES))
            ),
            container_kill_grace_seconds=int(
                os.environ.get('AGENT_SANDBOX_CONTAINER_KILL_GRACE_SECONDS',
                               str(DEFAULT_CONTAINER_KILL_GRACE_SECONDS))
            ),
            orphan_grace_seconds=int(
                os.environ.get('AGENT_SANDBOX_ORPHAN_GRACE_SECONDS',
                               str(DEFAULT_ORPHAN_GRACE_SECONDS))
            ),
            reaper_interval_seconds=int(
                os.environ.get('AGENT_SANDBOX_REAPER_INTERVAL_SECONDS',
                               str(DEFAULT_REAPER_INTERVAL_SECONDS))
            ),
        )


def _split_csv(raw: str | None) -> set[str]:
    return {item.strip() for item in (raw or '').split(',') if item.strip()}


def _configured_skills_root() -> str:
    """允许被只读挂进容器的 Skill 根目录（fail closed，绝不返回 None）。

    未配置 ``AGENT_SKILLS_ROOT`` 时用本地可计算的默认 ``<项目根>/skills``，与
    ``agent_service.config.Config.SKILLS_ROOT`` 同源，但**不 import 业务配置**
    （独立 runner 不需要 DB / OSS 凭据也应能启动）。环境变量给了相对路径等无法
    确定的值时抛 ``SandboxConfigurationError``，让 runner 明确启动失败，而不是
    跳过白名单校验。
    """
    raw = (os.environ.get('AGENT_SKILLS_ROOT') or '').strip()
    if not raw:
        return DEFAULT_SKILLS_ROOT
    path = Path(raw)
    if not path.is_absolute():
        raise SandboxConfigurationError(
            f'AGENT_SKILLS_ROOT 必须是绝对路径：{raw!r}'
        )
    return str(path.resolve())


def parse_memory_bytes(text: str) -> int:
    """把 docker 风格容量（``512m`` / ``2g`` / ``1024``）解析成字节数。"""
    match = _MEMORY_PATTERN.match(str(text).strip())
    if match is None:
        raise SandboxConfigurationError(f'容量格式非法：{text!r}')
    number = float(match.group(1))
    unit = match.group(2).lower()
    if unit not in _MEMORY_UNITS:
        raise SandboxConfigurationError(f'容量单位非法：{text!r}')
    return int(number * _MEMORY_UNITS[unit])


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


@dataclass(frozen=True)
class DockerRunnerConfig:
    """执行器配置（全部来自环境变量，禁止在代码里散落阈值）。"""

    mode: DockerRunnerMode = DockerRunnerMode.RUNNER_HTTP
    docker_binary: str = 'docker'
    runner_url: str = ''
    runner_token: str = ''
    limits: ContainerLimits = ContainerLimits()
    policy: SandboxPolicy | None = None

    @classmethod
    def from_env(cls) -> 'DockerRunnerConfig':
        raw_mode = (os.environ.get('AGENT_SANDBOX_EXECUTOR_MODE') or 'runner_http').strip().lower()
        try:
            mode = DockerRunnerMode(raw_mode)
        except ValueError as exc:
            raise SandboxConfigurationError(
                f'AGENT_SANDBOX_EXECUTOR_MODE 非法：{raw_mode!r}'
            ) from exc
        policy = SandboxPolicy.from_env()
        return cls(
            mode=mode,
            docker_binary=os.environ.get('AGENT_SANDBOX_DOCKER_BIN', 'docker'),
            runner_url=(os.environ.get('AGENT_SANDBOX_RUNNER_URL') or '').strip().rstrip('/'),
            runner_token=(os.environ.get('AGENT_SANDBOX_RUNNER_TOKEN') or '').strip(),
            limits=policy.limits,
            policy=policy,
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


def validate_script_relative_path(raw: str) -> str:
    """T1 脚本路径：必须落在 ``scripts/`` 下，禁绝对路径 / 盘符 / ``..`` / NUL。

    ``build_docker_run_argv`` 会再调一次（纵深防御）：应用层校验被绕过时，
    这里仍不允许把 ``../../bin/sh`` 拼进容器命令。
    """
    text = str(raw or '').replace('\\', '/').strip()
    if not text:
        raise SandboxConfigurationError('script_relative_path 不能为空')
    if '\x00' in text:
        raise SandboxConfigurationError('script_relative_path 含 NUL 字节')
    if text.startswith('/') or re.match(r'^[A-Za-z]:', text):
        raise SandboxConfigurationError(f'script_relative_path 必须是相对路径：{raw!r}')
    parts = [part for part in text.split('/') if part not in ('', '.')]
    if not parts or any(part == '..' for part in parts):
        raise SandboxConfigurationError(f'script_relative_path 禁止路径穿越：{raw!r}')
    if parts[0] != SCRIPTS_DIR_NAME or len(parts) < 2:
        raise SandboxConfigurationError(
            f'T1 只执行 {SCRIPTS_DIR_NAME}/ 下的脚本：{raw!r}'
        )
    return '/'.join(parts)


def validate_image(image: str, policy: SandboxPolicy | None) -> None:
    text = str(image or '').strip()
    if not text:
        raise SandboxConfigurationError('沙箱镜像未配置')
    if text.startswith('-'):
        raise SandboxConfigurationError(f'沙箱镜像不得以 - 开头：{image!r}')
    if IMAGE_REFERENCE_PATTERN.match(text) is None:
        raise SandboxConfigurationError(f'沙箱镜像引用非法：{image!r}')
    if policy is not None and text not in policy.allowed_images:
        raise SandboxConfigurationError(
            f'沙箱镜像不在允许集合内：{text!r}（允许：{sorted(policy.allowed_images)}）'
        )


def validate_interpreter(interpreter: str, policy: SandboxPolicy | None) -> None:
    text = str(interpreter or '').strip()
    if not text:
        raise SandboxConfigurationError('沙箱解释器未配置')
    if text.startswith('-') or any(ch.isspace() for ch in text):
        raise SandboxConfigurationError(f'沙箱解释器非法：{interpreter!r}')
    if policy is not None and text not in policy.allowed_interpreters:
        raise SandboxConfigurationError(
            f'沙箱解释器不在允许集合内：{text!r}（允许：{sorted(policy.allowed_interpreters)}）'
        )


#: payload 限额字段 → (比较口径, 人类可读名)。上限一律取 runner 自身配置。
def validate_limits_within(runner_limits: ContainerLimits, requested: ContainerLimits) -> None:
    """payload 只允许比 runner 配置更严格；超出直接拒绝，不静默 clamp。"""
    checks = (
        ('memory', parse_memory_bytes(requested.memory), parse_memory_bytes(runner_limits.memory)),
        ('memory_swap', parse_memory_bytes(requested.memory_swap),
         parse_memory_bytes(runner_limits.memory_swap)),
        ('tmpfs_size', parse_memory_bytes(requested.tmpfs_size),
         parse_memory_bytes(runner_limits.tmpfs_size)),
        ('cpus', requested.cpus, runner_limits.cpus),
        ('pids_limit', requested.pids_limit, runner_limits.pids_limit),
        ('timeout_seconds', requested.timeout_seconds, runner_limits.timeout_seconds),
        ('output_limit_bytes', requested.output_limit_bytes, runner_limits.output_limit_bytes),
    )
    for name, requested_value, limit_value in checks:
        if requested_value > limit_value:
            raise SandboxConfigurationError(
                f'{name}={requested_value} 超过 runner 配置上限 {limit_value}'
            )


def validate_invocation(
    invocation: ContainerInvocation,
    policy: SandboxPolicy | None = None,
) -> None:
    """执行前的硬校验：任何一条不满足都拒绝进容器。

    ``policy`` 由 **runner 自己**从环境构造（不是 payload 透传）：镜像 / 解释器
    白名单、Skill 根目录、资源限额上限都按它复核。客户端（agent_service）只做
    结构校验，传 ``policy=None``。
    """
    skill_root = Path(_normalize_host_path(invocation.skill_root, 'skill_root')).resolve()
    work_dir = Path(_normalize_host_path(invocation.work_dir, 'work_dir')).resolve()
    if skill_root == work_dir or skill_root in work_dir.parents or work_dir in skill_root.parents:
        raise SandboxConfigurationError('Skill 挂载与 /work 挂载不得重叠')
    if not invocation.name or CONTAINER_NAME_PATTERN.match(invocation.name) is None:
        raise SandboxConfigurationError(f'容器名非法：{invocation.name!r}')
    validate_image(invocation.limits.image, policy)
    validate_interpreter(invocation.limits.interpreter, policy)
    validate_script_relative_path(invocation.script_relative_path)
    # 按数值判定非 root：``000`` / ``0:65534`` / ``root`` 全部拒绝。
    parse_container_identity(invocation.limits.container_user)
    assert_env_is_credential_free(invocation.env)
    for arg in invocation.args:
        if '\x00' in arg:
            raise SandboxConfigurationError('参数含 NUL 字节')

    if policy is None:
        return
    # P2-2：允许根由 SandboxPolicy 保证非空（构造期 fail closed），这里无条件校验，
    # 不存在「根目录解析不出来就跳过白名单」的放宽分支。
    allowed_root = Path(policy.skills_root).resolve()
    if skill_root != allowed_root and allowed_root not in skill_root.parents:
        raise SandboxConfigurationError(
            f'skill_root 必须在允许的 Skills 根目录 {allowed_root} 下：{skill_root}'
        )
    validate_limits_within(policy.limits, invocation.limits)


def build_docker_run_argv(
    invocation: ContainerInvocation,
    docker_binary: str,
    container_kill_grace_seconds: int = DEFAULT_CONTAINER_KILL_GRACE_SECONDS,
) -> list[str]:
    """构造 ``docker run`` 参数 — 安全参数集中在这里，测试逐条断言。"""
    limits = invocation.limits
    relative_script = validate_script_relative_path(invocation.script_relative_path)
    skill_source = str(Path(invocation.skill_root).resolve()).replace('\\', '/')
    work_source = str(Path(invocation.work_dir).resolve()).replace('\\', '/')
    script_in_container = f'{SKILL_MOUNT_PATH}/{relative_script}'

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
    # 容器内自限：宿主计时器（runner 进程）消失时，容器到点自己结束；
    # 该退出在宿主存活时由应用层按 SANDBOX_TIMEOUT_EXIT_CODE 判超时。
    argv.extend([
        TIMEOUT_BINARY,
        '--kill-after', str(int(container_kill_grace_seconds)),
        str(int(limits.timeout_seconds)),
    ])
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


def _docker_cli_env() -> dict[str, str]:
    """docker CLI 自己的环境（不是容器环境）：只保留 CLI 运行必需的键。"""
    keep = ('PATH', 'SystemRoot', 'SYSTEMROOT', 'COMSPEC', 'PATHEXT', 'TEMP', 'TMP',
            'HOME', 'USERPROFILE', 'DOCKER_HOST', 'DOCKER_CONFIG', 'DOCKER_TLS_VERIFY',
            'DOCKER_CERT_PATH', 'DOCKER_CONTEXT')
    return {k: v for k, v in os.environ.items() if k in keep}


def run_docker_admin(
    docker_binary: str,
    args: Sequence[str],
    *,
    timeout: int = DOCKER_ADMIN_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess | None:
    """执行一次 docker 管理子命令；失败只记日志、返回 None（调用方自行降级）。

    ``timeout`` 默认取管理子命令口径；``docker info`` 这类偶发很慢的探测
    （INT-2489 运行时探测）可显式放大。
    """
    try:
        return subprocess.run(
            [docker_binary, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_docker_cli_env(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning('docker %s 失败：%s', ' '.join(args), exc)
        return None


def remove_container(name: str, docker_binary: str = 'docker') -> None:
    run_docker_admin(docker_binary, ['rm', '--force', name])


def inspect_container_state(
    name: str, docker_binary: str = 'docker'
) -> dict | None:
    result = run_docker_admin(
        docker_binary,
        ['inspect', '--format', '{{.State.OOMKilled}}|{{.State.ExitCode}}|{{.Id}}', name],
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


def execute_docker_container(
    argv: Sequence[str],
    container_name: str,
    limits: ContainerLimits,
    docker_binary: str = 'docker',
    *,
    timeout_seconds: int | None = None,
    runtime: str = '',
) -> ContainerExecution:
    """跑一次一次性容器并回收结果（T1/T2 共用，不含镜像/加固参数构造）。

    超时或输出超限时**先杀附着的 docker CLI、再 ``docker rm -f``**，保证不留
    遗留容器；结束后统一 inspect（取 OOM 状态）并删除容器。
    """
    started = time.monotonic()
    timeout = timeout_seconds or limits.timeout_seconds
    output = _BoundedOutput(limits.output_limit_bytes)
    limit_reached = threading.Event()

    def _mark_limit() -> None:
        # 只置位，由主线程统一终止：读线程直接调 docker 会与主线程的
        # inspect/等待竞态，且 Windows 上 docker CLI 在管道写满时无法自解。
        limit_reached.set()

    try:
        process = subprocess.Popen(
            list(argv),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_docker_cli_env(),
        )
    except FileNotFoundError:
        return ContainerExecution(
            exit_code=-1,
            error=f'docker CLI 不可用：{docker_binary}',
            runtime=runtime,
        )
    except OSError as exc:
        return ContainerExecution(
            exit_code=-1, error=f'docker CLI 启动失败：{exc}', runtime=runtime
        )

    stdout_reader = threading.Thread(
        target=_pump, args=(process.stdout, output, 'stdout', _mark_limit), daemon=True
    )
    stderr_reader = threading.Thread(
        target=_pump, args=(process.stderr, output, 'stderr', _mark_limit), daemon=True
    )
    stdout_reader.start()
    stderr_reader.start()

    timed_out = False
    deadline = time.monotonic() + timeout
    while process.poll() is None:
        if limit_reached.is_set():
            _terminate(process, container_name, docker_binary)
            break
        if time.monotonic() >= deadline:
            timed_out = True
            _terminate(process, container_name, docker_binary)
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

    state = inspect_container_state(container_name, docker_binary)
    remove_container(container_name, docker_binary)

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
        runtime=runtime,
    )


def _terminate(process: subprocess.Popen, name: str, docker_binary: str = 'docker') -> None:
    """终止容器：先杀附着的 docker CLI（解除管道阻塞），再 ``docker rm -f``。

    实测（Docker Desktop / Windows）：管道写满时 ``docker kill`` 会长时间挂住，
    而 ``docker rm -f``（= kill + 删除）0.4s 内返回；故统一走 rm -f。
    """
    try:
        process.kill()
    except OSError:
        pass
    remove_container(name, docker_binary)


# ── 宿主 docker CLI 执行器 ─────────────────────────────────────


class HostCliDockerExecutor(SandboxExecutor):
    """宿主 runner：直接调用 docker CLI 执行一次性容器（开发机 / sidecar 内部）。"""

    def __init__(
        self,
        limits: ContainerLimits | None = None,
        docker_binary: str = 'docker',
        policy: SandboxPolicy | None = None,
    ) -> None:
        self._policy = policy or SandboxPolicy.from_env()
        self._limits = limits or self._policy.limits
        self._docker_binary = docker_binary

    @property
    def limits(self) -> ContainerLimits:
        return self._limits

    @property
    def policy(self) -> SandboxPolicy:
        return self._policy

    def validate(self, invocation: ContainerInvocation) -> None:
        """按 runner 自己的白名单复核调用方送来的规格（HTTP 侧 400 的判据）。"""
        validate_invocation(invocation, self._policy)

    def run(self, invocation: ContainerInvocation) -> ContainerExecution:
        started = time.monotonic()
        try:
            self.validate(invocation)
            argv = build_docker_run_argv(
                invocation,
                self._docker_binary,
                container_kill_grace_seconds=self._policy.container_kill_grace_seconds,
            )
        except SandboxConfigurationError as exc:
            return ContainerExecution(exit_code=-1, error=str(exc))

        # 单一口径：payload 限额已按 runner 配置复核（只允许更严格），此处直接取
        # invocation 的生效值，避免「更严格的请求被静默放宽回 runner 默认」。
        output = _BoundedOutput(invocation.limits.output_limit_bytes)
        limit_reached = threading.Event()
        work_limit_exceeded = threading.Event()
        logger.info(
            '沙箱容器启动：name=%s image=%s user=%s memory=%s cpus=%s pids=%s '
            'tmpfs=%s timeout=%ss 输出上限=%sB work 上限=%sB',
            invocation.name, invocation.limits.image, invocation.limits.container_user,
            invocation.limits.memory, invocation.limits.cpus, invocation.limits.pids_limit,
            invocation.limits.tmpfs_size, invocation.limits.timeout_seconds,
            invocation.limits.output_limit_bytes, self._policy.work_limit_bytes,
        )

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
        state: dict | None = None
        # P1-1：Popen 之后的任何路径（含异常）都必须在 finally 里回收容器。
        try:
            deadline = time.monotonic() + invocation.limits.timeout_seconds
            next_work_check = time.monotonic() + WORK_DIR_CHECK_INTERVAL_SECONDS
            while process.poll() is None:
                if limit_reached.is_set():
                    self._kill_cli(process)
                    break
                now = time.monotonic()
                if now >= deadline:
                    timed_out = True
                    self._kill_cli(process)
                    break
                if now >= next_work_check:
                    next_work_check = now + WORK_DIR_CHECK_INTERVAL_SECONDS
                    if self._work_dir_exceeds(invocation.work_dir):
                        work_limit_exceeded.set()
                        self._kill_cli(process)
                        break
                time.sleep(0.05)
            self._drain(process, stdout_reader, stderr_reader)
            # inspect 必须在 rm 之前取：超时 / 输出超限路径也要有 container_id。
            state = self._inspect_state(invocation.name)
        finally:
            # P1-1：任何异常路径都无条件回收容器；这里每一步单独兜底，
            # 确保 inspect / 收尾异常都不会跳过最后的 ``docker rm -f``。
            self._kill_cli(process)
            try:
                self._drain(process, stdout_reader, stderr_reader)
            except Exception:  # noqa: BLE001 - 收尾不得阻止容器回收
                logger.exception('沙箱输出读取线程收尾异常：%s', invocation.name)
            if state is None:
                try:
                    state = self._inspect_state(invocation.name)
                except Exception:  # noqa: BLE001 - inspect 失败只影响审计字段
                    logger.exception('沙箱容器 inspect 失败：%s', invocation.name)
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
            killed_by_runner=timed_out or output.truncated or work_limit_exceeded.is_set(),
            start_failed=start_failed,
            work_limit_exceeded=work_limit_exceeded.is_set(),
            # 启动失败（125）走 error，供应用层判 FAILED/CONTAINER_START_FAILED。
            error=stderr_text[:1000] if start_failed else '',
        )

    # ── docker 子命令 ────────────────────────────────────────
    def _kill_cli(self, process: subprocess.Popen) -> None:
        """只杀掉附着的 docker CLI（解除管道阻塞），容器由 ``_remove_container`` 回收。

        实测（Docker Desktop / Windows）：管道写满时 ``docker kill`` 会长时间挂住，
        而 ``docker rm -f``（= kill + 删除）0.4s 内返回；故统一走 rm -f。
        """
        if process.poll() is not None:
            return
        try:
            process.kill()
        except OSError:
            pass

    @staticmethod
    def _drain(process: subprocess.Popen, *readers: threading.Thread) -> None:
        try:
            process.wait(timeout=DOCKER_ADMIN_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
                process.wait(timeout=DOCKER_ADMIN_TIMEOUT_SECONDS)
            except (OSError, subprocess.TimeoutExpired):
                pass
        # 读线程可能仍阻塞在被杀进程的管道上，关闭后再 join，避免挂住。
        for stream in (process.stdout, process.stderr):
            try:
                if stream is not None:
                    stream.close()
            except OSError:
                pass
        for reader in readers:
            reader.join(timeout=DOCKER_ADMIN_TIMEOUT_SECONDS)

    def _work_dir_exceeds(self, work_dir: str) -> bool:
        """运行中巡检 ``/work`` 占用量；超限即终止（不等容器结束再校验）。"""
        limit = self._policy.work_limit_bytes
        total = 0
        try:
            for root, _dirs, files in os.walk(work_dir):
                for name in files:
                    try:
                        total += os.path.getsize(os.path.join(root, name))
                    except OSError:
                        continue
                    if total > limit:
                        logger.warning(
                            '沙箱 /work 超过容量上限：%s > %sB（work_dir=%s）',
                            total, limit, work_dir,
                        )
                        return True
        except OSError:
            return False
        return False

    def _docker_cli_env(self) -> dict[str, str]:
        return _docker_cli_env()

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
        return run_docker_admin(self._docker_binary, args)


# ── 孤儿容器回收（P1-1：runner 崩溃 / 重启后无人回收） ──────────


def parse_docker_timestamp(raw: str) -> float | None:
    """解析 docker inspect 的 ISO 时间戳（纳秒精度要截到微秒）。"""
    text = (raw or '').strip()
    if not text:
        return None
    match = re.match(
        r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d+)?(Z|[+-]\d{2}:\d{2})?$', text
    )
    if match is None:
        return None
    base, fraction, timezone = match.groups()
    fraction = (fraction or '')[:7]
    timezone = '+00:00' if timezone in (None, 'Z') else timezone
    try:
        return datetime.fromisoformat(base + fraction + timezone).timestamp()
    except ValueError:
        return None


@dataclass(frozen=True)
class OrphanContainer:
    container_id: str
    name: str
    created_at: float
    status: str


class SandboxContainerReaper:
    """按 label 回收「创建时间已超 timeout + 宽限」的孤儿沙箱容器。

    runner 启动时先同步扫一次（上次崩溃 / 重启遗留的容器），之后后台定时扫。
    回收日志带容器名 / id / 存活时长，便于审计追溯。
    """

    def __init__(
        self,
        docker_binary: str = 'docker',
        timeout_seconds: int | None = None,
        grace_seconds: int | None = None,
        interval_seconds: int | None = None,
        label_selector: str = SANDBOX_CONTAINER_LABEL,
    ) -> None:
        self._docker_binary = docker_binary
        self._label_selector = label_selector or SANDBOX_CONTAINER_LABEL
        limits = build_limits_from_env()
        self._timeout_seconds = (
            limits.timeout_seconds if timeout_seconds is None else int(timeout_seconds)
        )
        self._grace_seconds = int(
            os.environ.get('AGENT_SANDBOX_ORPHAN_GRACE_SECONDS',
                           str(DEFAULT_ORPHAN_GRACE_SECONDS))
            if grace_seconds is None else grace_seconds
        )
        self._interval_seconds = int(
            os.environ.get('AGENT_SANDBOX_REAPER_INTERVAL_SECONDS',
                           str(DEFAULT_REAPER_INTERVAL_SECONDS))
            if interval_seconds is None else interval_seconds
        )
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def threshold_seconds(self) -> float:
        return self._timeout_seconds + self._grace_seconds

    @property
    def interval_seconds(self) -> int:
        return self._interval_seconds

    @property
    def label_selector(self) -> str:
        return self._label_selector

    def list_containers(self) -> list[OrphanContainer]:
        listing = run_docker_admin(
            self._docker_binary,
            ['ps', '--all', '--filter', f'label={self._label_selector}', '--format', '{{.ID}}'],
        )
        if listing is None or listing.returncode != 0:
            return []
        ids = [line.strip() for line in (listing.stdout or '').splitlines() if line.strip()]
        if not ids:
            return []
        inspect = run_docker_admin(
            self._docker_binary,
            ['inspect', '--format', '{{.Id}}|{{.Name}}|{{.Created}}|{{.State.Status}}', *ids],
        )
        if inspect is None or inspect.returncode != 0:
            return []
        containers: list[OrphanContainer] = []
        for line in (inspect.stdout or '').splitlines():
            parts = line.strip().split('|')
            if len(parts) != 4:
                continue
            created_at = parse_docker_timestamp(parts[2])
            if created_at is None:
                continue
            containers.append(OrphanContainer(
                container_id=parts[0].strip(),
                name=parts[1].strip().lstrip('/'),
                created_at=created_at,
                status=parts[3].strip(),
            ))
        return containers

    def reap_once(self, now: float | None = None) -> list[str]:
        """回收一次，返回被回收的容器名列表（便于测试与日志）。"""
        current = time.time() if now is None else now
        reaped: list[str] = []
        for container in self.list_containers():
            age = current - container.created_at
            if age < self.threshold_seconds:
                continue
            result = run_docker_admin(
                self._docker_binary, ['rm', '--force', container.container_id]
            )
            if result is None or result.returncode != 0:
                logger.warning(
                    '孤儿沙箱容器回收失败：name=%s id=%s age=%.0fs',
                    container.name, container.container_id[:12], age,
                )
                continue
            logger.warning(
                '回收孤儿沙箱容器：name=%s id=%s age=%.0fs status=%s',
                container.name, container.container_id[:12], age, container.status,
            )
            reaped.append(container.name)
        return reaped

    def start_background(self) -> 'SandboxContainerReaper':
        self._thread = threading.Thread(
            target=self._loop, name='sandbox-container-reaper', daemon=True
        )
        self._thread.start()
        return self

    def _loop(self) -> None:
        while not self._stop.wait(self._interval_seconds):
            try:
                self.reap_once()
            except Exception:  # noqa: BLE001 - 后台巡检不得让 runner 退出
                logger.exception('孤儿沙箱容器回收巡检异常')

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
            self._thread = None


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
        response_limit = int(
            os.environ.get('AGENT_SANDBOX_RUNNER_RESPONSE_LIMIT_BYTES',
                           str(DEFAULT_RUNNER_RESPONSE_LIMIT_BYTES))
        )
        try:
            with urlrequest.urlopen(request, timeout=timeout) as response:
                # 有上限读取：恶意 / 故障 runner 不能用返回体撑爆 agent_service 内存。
                body = response.read(response_limit + 1)
        except urlerror.HTTPError as exc:
            return ContainerExecution(
                exit_code=-1,
                error=f'runner 返回 HTTP {exc.code}：{exc.reason}',
            )
        except (urlerror.URLError, TimeoutError, OSError) as exc:
            return ContainerExecution(exit_code=-1, error=f'runner 不可达：{exc}')

        if len(body) > response_limit:
            return ContainerExecution(
                exit_code=-1,
                error=f'runner 响应超过上限 {response_limit}B，已丢弃',
            )

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
        return HostCliDockerExecutor(
            limits=cfg.limits, docker_binary=cfg.docker_binary, policy=cfg.policy
        )
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
        'work_limit_exceeded': execution.work_limit_exceeded,
        'error': execution.error,
        'runtime': execution.runtime,
        'runtime_unavailable': execution.runtime_unavailable,
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
        work_limit_exceeded=bool(data.get('work_limit_exceeded')),
        error=str(data.get('error') or ''),
        runtime=str(data.get('runtime') or ''),
        runtime_unavailable=bool(data.get('runtime_unavailable')),
    )
