# -*- coding: utf-8 -*-
"""T2 不可信代码沙箱策略（方案 doc/agent化/07 §7，INT-2489）。

所有硬限**配置化**，代码里不散落阈值：

- 默认值：``agent_service/config/sandbox.yaml``（部署时只读挂载，INT-2456）；
- 覆盖：``AGENT_SANDBOX_T2_*`` 环境变量（优先级最高）；
- 配置文件缺失/损坏不阻断启动：仍以本模块的安全默认值运行。

默认网段/资源口径按 §7 固定：``--network=none``、无宿主挂载、``--cap-drop=ALL``、
``--security-opt=no-new-privileges``、非 root、只读根、pids/CPU/内存/时长硬限。
T2 的超时比 T1 宽（导入/编译 + 单测 + 契约测试），默认单阶段 120s、整份计划 300s。
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

import yaml

from agent_service.application.sandbox_runner import (
    ContainerLimits,
    SandboxConfigurationError,
    T2RunnerOptions,
)
from agent_service.domain.enums import SandboxRuntime

logger = logging.getLogger(__name__)

#: 配置文件路径（可用 ``AGENT_SANDBOX_T2_CONFIG`` 覆盖）。
CONFIG_PATH_ENV = 'AGENT_SANDBOX_T2_CONFIG'
DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / 'config' / 'sandbox.yaml'
)

#: 运行时取值：唯一事实源是 ``domain/enums.py`` 的 ``SandboxRuntime``（不另造魔法值）。
RUNTIME_GVISOR = SandboxRuntime.GVISOR.value
RUNTIME_FIRECRACKER = SandboxRuntime.FIRECRACKER.value

_RUNTIME_NAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$')


@dataclass(frozen=True)
class T2ArtifactLimits:
    """``/work`` 产物回收上限（方案 §7 硬规则 3）。"""

    max_artifacts: int = 32
    max_artifact_bytes: int = 8 * 1024 * 1024
    max_total_bytes: int = 32 * 1024 * 1024

    def __post_init__(self) -> None:
        for name, value in (
            ('max_artifacts', self.max_artifacts),
            ('max_artifact_bytes', self.max_artifact_bytes),
            ('max_total_bytes', self.max_total_bytes),
        ):
            if value <= 0:
                raise SandboxConfigurationError(f'{name} 必须为正数')


@dataclass(frozen=True)
class T2InputLimits:
    """输入代码包上限（请求本身也是攻击面）。"""

    max_files: int = 200
    max_file_bytes: int = 1024 * 1024
    max_total_bytes: int = 2 * 1024 * 1024

    def __post_init__(self) -> None:
        for name, value in (
            ('max_files', self.max_files),
            ('max_file_bytes', self.max_file_bytes),
            ('max_total_bytes', self.max_total_bytes),
        ):
            if value <= 0:
                raise SandboxConfigurationError(f'{name} 必须为正数')


@dataclass(frozen=True)
class T2EgressPolicy:
    """出口代理白名单（§7 硬规则 6；默认关闭 = 完全禁网）。

    开启后容器只挂 ``network``（必须是 internal 网络，只有代理可达），凭据由
    代理持有；代码来源与 hash 在每次执行结果与产物 metadata 里记录。
    """

    enabled: bool = False
    network: str = ''
    proxy_url: str = ''
    allowed_hosts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.enabled:
            if not self.network or not _RUNTIME_NAME_RE.match(self.network):
                raise SandboxConfigurationError(
                    f'T2 出口网络名非法：{self.network!r}（需 internal 网络名）'
                )
            if not self.proxy_url.lower().startswith(('http://', 'https://')):
                raise SandboxConfigurationError(
                    f'T2 出口代理地址必须是 http(s)：{self.proxy_url!r}'
                )
            if not self.allowed_hosts:
                raise SandboxConfigurationError(
                    'T2 出口白名单启用时必须配置 allowed_hosts（默认全禁网）'
                )


@dataclass(frozen=True)
class T2Policy:
    """T2 完整策略（运行时 + 硬限 + 产物/输入上限 + 出口白名单）。"""

    runtime: str = RUNTIME_GVISOR
    #: docker 的 ``--runtime`` 名（gVisor 安装后通常注册为 ``runsc``）。
    runtime_name: str = 'runsc'
    runsc_binary: str = 'runsc'
    firecracker_enabled: bool = False
    firecracker_binary: str = '/usr/local/bin/firecracker'
    docker_binary: str = 'docker'
    container_limits: ContainerLimits = field(
        default_factory=lambda: ContainerLimits(timeout_seconds=120)
    )
    #: 整份阶段计划的总时长硬限（第二道闸，防止多阶段叠加挤爆 run 预算）。
    total_timeout_seconds: int = 300
    artifacts: T2ArtifactLimits = field(default_factory=T2ArtifactLimits)
    input: T2InputLimits = field(default_factory=T2InputLimits)
    egress: T2EgressPolicy = field(default_factory=T2EgressPolicy)

    def __post_init__(self) -> None:
        if self.runtime not in {item.value for item in SandboxRuntime}:
            raise SandboxConfigurationError(
                f'T2 运行时非法：{self.runtime!r}（可选 {RUNTIME_GVISOR}/'
                f'{RUNTIME_FIRECRACKER}）'
            )
        if self.runtime == RUNTIME_GVISOR and not _RUNTIME_NAME_RE.match(self.runtime_name):
            raise SandboxConfigurationError(
                f'T2 运行时名非法：{self.runtime_name!r}'
            )
        if self.total_timeout_seconds <= 0:
            raise SandboxConfigurationError('total_timeout_seconds 必须为正数')
        if self.total_timeout_seconds < self.container_limits.timeout_seconds:
            raise SandboxConfigurationError(
                'total_timeout_seconds 不得小于单阶段 timeout_seconds'
            )
        if self.container_limits.container_user in ('0', '0:0', 'root'):
            raise SandboxConfigurationError('T2 沙箱容器禁止以 root 运行')

    def to_runner_options(self) -> T2RunnerOptions:
        """转成应用层编排策略（infrastructure 不反向依赖应用层策略对象）。"""
        return T2RunnerOptions(
            max_input_files=self.input.max_files,
            max_input_file_bytes=self.input.max_file_bytes,
            max_input_total_bytes=self.input.max_total_bytes,
            # 产物上限同样从 yaml/env 进编排策略（否则 t2.artifact.* 是死配置）。
            max_artifacts=self.artifacts.max_artifacts,
            max_artifact_bytes=self.artifacts.max_artifact_bytes,
            max_total_bytes=self.artifacts.max_total_bytes,
            total_timeout_seconds=self.total_timeout_seconds,
            require_code_provenance=True,
            egress_enabled=self.egress.enabled,
            egress_network=self.egress.network,
            egress_proxy_url=self.egress.proxy_url,
            egress_allowed_hosts=self.egress.allowed_hosts,
        )


# ── 配置加载（yaml + env）──────────────────────────────────────


def _env(environ: Mapping[str, str], key: str, default: str) -> str:
    value = environ.get(key)
    return value if value is not None and value != '' else default


def _env_int(environ: Mapping[str, str], key: str, default: int) -> int:
    raw = environ.get(key)
    if raw is None or raw == '':
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise SandboxConfigurationError(f'{key} 必须是整数：{raw!r}') from exc


def _env_float(environ: Mapping[str, str], key: str, default: float) -> float:
    raw = environ.get(key)
    if raw is None or raw == '':
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise SandboxConfigurationError(f'{key} 必须是数字：{raw!r}') from exc


def _env_bool(environ: Mapping[str, str], key: str, default: bool) -> bool:
    raw = environ.get(key)
    if raw is None or raw == '':
        return default
    return raw.strip().lower() in ('1', 'true', 'yes', 'on')


def _load_yaml(path: Path) -> dict:
    try:
        with path.open(encoding='utf-8') as handle:
            data = yaml.safe_load(handle) or {}
    except FileNotFoundError:
        logger.info('T2 沙箱配置缺失，使用安全默认值：%s', path)
        return {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning('T2 沙箱配置不可读，使用安全默认值：%s（%s）', path, exc)
        return {}
    if not isinstance(data, dict):
        logger.warning('T2 沙箱配置格式非法（需 mapping）：%s', path)
        return {}
    return data


def load_t2_policy(
    path: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> T2Policy:
    """加载 T2 策略：yaml（``t2:`` 段）+ ``AGENT_SANDBOX_T2_*`` 环境变量覆盖。"""
    env = os.environ if environ is None else environ
    config_path = Path(
        path or env.get(CONFIG_PATH_ENV) or DEFAULT_CONFIG_PATH
    )
    data = (_load_yaml(config_path).get('t2') or {}) if config_path else {}
    if not isinstance(data, dict):
        data = {}

    artifact_cfg = data.get('artifact') or {}
    input_cfg = data.get('input') or {}
    egress_cfg = data.get('egress') or {}

    cpus = _env_float(env, 'AGENT_SANDBOX_T2_CPUS', float(data.get('cpus', 1)))
    timeout_seconds = _env_int(
        env, 'AGENT_SANDBOX_T2_TIMEOUT_SECONDS',
        int(data.get('timeout_seconds', 120)),
    )
    container_limits = ContainerLimits(
        image=_env(env, 'AGENT_SANDBOX_T2_IMAGE', str(data.get('image', 'python:3.11-slim'))),
        memory=_env(env, 'AGENT_SANDBOX_T2_MEMORY', str(data.get('memory', '512m'))),
        memory_swap=_env(
            env, 'AGENT_SANDBOX_T2_MEMORY_SWAP', str(data.get('memory_swap', '512m'))
        ),
        cpus=cpus,
        pids_limit=_env_int(
            env, 'AGENT_SANDBOX_T2_PIDS_LIMIT', int(data.get('pids_limit', 128))
        ),
        tmpfs_size=_env(
            env, 'AGENT_SANDBOX_T2_TMPFS_SIZE', str(data.get('tmpfs_size', '64m'))
        ),
        timeout_seconds=timeout_seconds,
        output_limit_bytes=_env_int(
            env, 'AGENT_SANDBOX_T2_OUTPUT_LIMIT_BYTES',
            int(data.get('output_limit_bytes', 1024 * 1024)),
        ),
        container_user=_env(
            env, 'AGENT_SANDBOX_T2_CONTAINER_USER',
            str(data.get('container_user', '65534:65534')),
        ),
        interpreter=_env(
            env, 'AGENT_SANDBOX_T2_INTERPRETER', str(data.get('interpreter', 'python3'))
        ),
    )

    raw_hosts = _env(
        env, 'AGENT_SANDBOX_T2_EGRESS_ALLOWED_HOSTS',
        ','.join(str(h) for h in (egress_cfg.get('allowed_hosts') or [])),
    )
    allowed_hosts = tuple(h.strip() for h in raw_hosts.split(',') if h.strip())
    egress = T2EgressPolicy(
        enabled=_env_bool(
            env, 'AGENT_SANDBOX_T2_EGRESS_ENABLED', bool(egress_cfg.get('enabled', False))
        ),
        network=_env(
            env, 'AGENT_SANDBOX_T2_EGRESS_NETWORK', str(egress_cfg.get('network', ''))
        ),
        proxy_url=_env(
            env, 'AGENT_SANDBOX_T2_EGRESS_PROXY_URL', str(egress_cfg.get('proxy_url', ''))
        ),
        allowed_hosts=allowed_hosts,
    )

    return T2Policy(
        runtime=_env(env, 'AGENT_SANDBOX_T2_RUNTIME', str(data.get('runtime', RUNTIME_GVISOR))),
        runtime_name=_env(
            env, 'AGENT_SANDBOX_T2_RUNTIME_NAME', str(data.get('runtime_name', 'runsc'))
        ),
        runsc_binary=_env(
            env, 'AGENT_SANDBOX_T2_RUNSC_BIN', str(data.get('runsc_binary', 'runsc'))
        ),
        firecracker_enabled=_env_bool(
            env, 'AGENT_SANDBOX_T2_FIRECRACKER_ENABLED',
            bool(data.get('firecracker_enabled', False)),
        ),
        firecracker_binary=_env(
            env, 'AGENT_SANDBOX_T2_FIRECRACKER_BIN',
            str(data.get('firecracker_binary', '/usr/local/bin/firecracker')),
        ),
        docker_binary=_env(
            env, 'AGENT_SANDBOX_T2_DOCKER_BIN', str(data.get('docker_binary', 'docker'))
        ),
        container_limits=container_limits,
        total_timeout_seconds=_env_int(
            env, 'AGENT_SANDBOX_T2_TOTAL_TIMEOUT_SECONDS',
            int(data.get('total_timeout_seconds', 300)),
        ),
        artifacts=T2ArtifactLimits(
            max_artifacts=_env_int(
                env, 'AGENT_SANDBOX_T2_MAX_ARTIFACTS',
                int(artifact_cfg.get('max_artifacts', 32)),
            ),
            max_artifact_bytes=_env_int(
                env, 'AGENT_SANDBOX_T2_MAX_ARTIFACT_BYTES',
                int(artifact_cfg.get('max_artifact_bytes', 8 * 1024 * 1024)),
            ),
            max_total_bytes=_env_int(
                env, 'AGENT_SANDBOX_T2_MAX_TOTAL_ARTIFACT_BYTES',
                int(artifact_cfg.get('max_total_bytes', 32 * 1024 * 1024)),
            ),
        ),
        input=T2InputLimits(
            max_files=_env_int(
                env, 'AGENT_SANDBOX_T2_MAX_INPUT_FILES',
                int(input_cfg.get('max_files', 200)),
            ),
            max_file_bytes=_env_int(
                env, 'AGENT_SANDBOX_T2_MAX_INPUT_FILE_BYTES',
                int(input_cfg.get('max_file_bytes', 1024 * 1024)),
            ),
            max_total_bytes=_env_int(
                env, 'AGENT_SANDBOX_T2_MAX_INPUT_TOTAL_BYTES',
                int(input_cfg.get('max_total_bytes', 2 * 1024 * 1024)),
            ),
        ),
        egress=egress,
    )
