# -*- coding: utf-8 -*-
"""沙箱编排与判定 — T1 可信脚本（INT-2455）+ T2 不可信代码（INT-2489）。

方案依据 ``doc/agent化/07_单Agent_Skills落地方案.md`` §7。

职责边界
--------
本模块只做**编排与判定**，不碰 Docker：

1. 按 ``SandboxTier`` 选择通道（``run_by_tier``）：
   - ``T1_TRUSTED_SCRIPT``：Skill 自带 ``scripts/``，执行器见
     ``infrastructure/sandbox/docker_runner.py``；
   - ``T2_UNTRUSTED_CODE``：模型生成的驱动/适配器/分析脚本，执行器见
     ``infrastructure/sandbox/t2_runner.py``（gVisor ``runsc``）。
   - ``T0_NONE`` 一律拒绝（不执行代码）。
2. T1 校验脚本必须落在 ``<skill_root>/scripts/`` 内，禁止 ``../`` 穿越与绝对路径。
3. T2 只接受**代码文件副本**（不挂宿主目录）：调用方给出相对路径→内容，本层
   写入一次性输入目录，只读挂载到 ``/input``；计算代码来源 hash（调用方给的
   hash 必须与重算值一致）。
4. 产物**只**从容器 ``/work`` 回收，逐项校验（常规文件、非符号链接、单文件与
   总量上限），并按需写入 ``agent_artifact``（含 sha256）。
5. 失败不得静默成功：超时/输出超限/内存超限/资源上限 → ``BUDGET_EXCEEDED``；
   非零退出/容器起不来/产物非法/T2 运行时不可用 → ``FAILED``，并记录原因码。
6. T2 运行时不可用（无 ``runsc``）明确返回 ``T2_RUNTIME_UNAVAILABLE``，**绝不**
   静默降级到 T1（既有 T1 行为不变，T1 通道仍拒绝 T2 请求）。

Docker 访问方式（负责人红线）：agent_service 进程**不持有 docker.sock**，
只通过独立的 runner/sidecar（HTTP）或宿主 runner 访问 Docker；两种方式都由
infrastructure 层实现，见 ``DockerRunnerMode`` / T2 的 ``T2DockerExecutor``。
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import stat as stat_module
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Mapping, Protocol, Tuple

from agent_service.domain.enums import SandboxTier

logger = logging.getLogger(__name__)

#: 方案 §7 的沙箱层级取值（唯一事实源：domain/enums.py 的 ``SandboxTier``）。
SANDBOX_TIER_T1 = SandboxTier.T1_TRUSTED_SCRIPT.value
SANDBOX_TIER_T2 = SandboxTier.T2_UNTRUSTED_CODE.value

#: 容器内 ``timeout`` 自限到点时的退出码（GNU coreutils 约定）。
#: 宿主侧计时器消失时容器由它自己结束；判 BUDGET_EXCEEDED，不是 FAILED。
SANDBOX_TIMEOUT_EXIT_CODE = 124

#: 容器内固定挂载点（T1：Skill 只读、/work 可写；T2：输入只读、/work 可写）。
SKILL_MOUNT_PATH = '/skill'
INPUT_MOUNT_PATH = '/input'
WORK_MOUNT_PATH = '/work'
SCRIPTS_DIR_NAME = 'scripts'

#: T2 单次代码包/阶段数量硬上限（防止请求本身撑爆 runner）。
T2_MAX_PHASES = 16

#: 允许出现在容器内的环境变量名白名单前缀之外的凭据特征（出现即拒绝）。
CREDENTIAL_ENV_MARKERS = (
    'PASSWORD', 'PASSWD', 'SECRET', 'TOKEN', 'API_KEY', 'APIKEY',
    'ACCESS_KEY', 'ACCESSKEY', 'PRIVATE_KEY', 'CREDENTIAL', 'AUTH',
    'DATABASE_URL', 'DB_URL', 'DB_HOST', 'DB_PASSWORD', 'DB_USER',
    'OSS_', 'S3_', 'MINIO', 'LLM_', 'OPENAI', 'DEEPSEEK', 'ANTHROPIC',
    'CLAUDE', 'MODEL_API', 'REDIS_URL', 'REDIS_PASSWORD', 'DOCKER_HOST',
)

_SCRIPT_RELATIVE_FORBIDDEN = ('..',)

#: T2 阶段名 / run_id 落盘路径分量：只允许安全字符集，且不得为 ``.`` / ``..``
#: （与 ``policy._RUNTIME_NAME_RE`` 同口径，防止路径穿越/Windows 目录归一化）。
_SAFE_PHASE_NAME_RE = re.compile(r'^[A-Za-z0-9_.-]{1,64}$')
_SAFE_RUN_ID_RE = re.compile(r'^[A-Za-z0-9_.-]{1,128}$')
_UNSAFE_PATH_SEGMENTS = ('.', '..')

#: Python 字节码缓存：不属于交付产物（T2 一律跳过回收，避免 .pyc 脏化产物）。
_BYTECODE_DIR_NAMES = ('__pycache__', '.pycache')
_BYTECODE_SUFFIXES = ('.pyc', '.pyo')


class SandboxOutcome(str, Enum):
    """run 层面的沙箱结果（对齐 RunStatus 的失败口径）。"""

    SUCCEEDED = 'SUCCEEDED'
    FAILED = 'FAILED'
    BUDGET_EXCEEDED = 'BUDGET_EXCEEDED'


class SandboxFailureReason(str, Enum):
    """失败原因码 — 禁止魔法字符串，失败必须能回答「为什么」。

    T1 与 T2 共用本枚举（INT-2455 落地，INT-2489 按需补充 T2 取值）；落库/
    事件里统一写 ``reason.value``。
    """

    NONE = 'NONE'
    UNSUPPORTED_TIER = 'UNSUPPORTED_TIER'
    #: T2 强隔离运行时（runsc / firecracker）不可用（INT-2456 拍板#2）。
    #: 与 UNSUPPORTED_TIER 分开：前者是「运行时没装」，后者是「层级不支持」。
    T2_RUNTIME_UNAVAILABLE = 'T2_RUNTIME_UNAVAILABLE'
    SCRIPT_NOT_FOUND = 'SCRIPT_NOT_FOUND'
    SCRIPT_OUTSIDE_SKILL = 'SCRIPT_OUTSIDE_SKILL'
    INVALID_INVOCATION = 'INVALID_INVOCATION'
    EXIT_CODE_NONZERO = 'EXIT_CODE_NONZERO'
    TIMEOUT = 'TIMEOUT'
    OUTPUT_LIMIT_EXCEEDED = 'OUTPUT_LIMIT_EXCEEDED'
    MEMORY_LIMIT_EXCEEDED = 'MEMORY_LIMIT_EXCEEDED'
    RESOURCE_LIMIT_EXCEEDED = 'RESOURCE_LIMIT_EXCEEDED'
    CONTAINER_START_FAILED = 'CONTAINER_START_FAILED'
    RUNNER_ERROR = 'RUNNER_ERROR'
    ARTIFACT_INVALID = 'ARTIFACT_INVALID'
    ARTIFACT_TOO_LARGE = 'ARTIFACT_TOO_LARGE'
    ARTIFACT_TOO_MANY = 'ARTIFACT_TOO_MANY'
    # ── T2（INT-2489）────────────────────────────────────────
    #: gVisor ``runsc`` / Firecracker 不可用：明确失败，绝不降级到 T1。
    T2_RUNTIME_UNAVAILABLE = 'T2_RUNTIME_UNAVAILABLE'
    #: 代码来源不可确认（缺少 code_source，或 hash 与重算不一致）。
    CODE_PROVENANCE_MISSING = 'CODE_PROVENANCE_MISSING'
    CODE_PROVENANCE_MISMATCH = 'CODE_PROVENANCE_MISMATCH'
    #: 请求了非白名单联网；在进入容器前拒绝。
    EGRESS_DENIED = 'EGRESS_DENIED'
    #: T2 输入代码包非法（绝对路径/穿越/超数量或体积）。
    INPUT_INVALID = 'INPUT_INVALID'


class SandboxConfigurationError(RuntimeError):
    """沙箱配置/请求非法（凭证、路径、层级等）— 拒绝执行，不进入容器。"""


class SandboxArtifactError(SandboxConfigurationError):
    """``/work`` 产物校验失败。"""


class SandboxArtifactTooLargeError(SandboxArtifactError):
    """产物超出单文件大小 / 总量 / 数量上限。"""


class SandboxArtifactTooManyError(SandboxArtifactTooLargeError):
    """产物数量超上限（T2 需要与体积超限区分停止原因）。"""


class T2EgressDeniedError(SandboxConfigurationError):
    """T2 请求了非白名单联网（进容器前拒绝）。"""


#: ``--user`` 只接受数值 ``uid[:gid]``；字面量比对会被 ``000`` / ``0:65534`` 绕过。
_CONTAINER_USER_PATTERN = re.compile(r'^([0-9]{1,10})(?::([0-9]{1,10}))?$')
_MAX_CONTAINER_UID = 2**32 - 1


def parse_container_identity(raw: str) -> tuple[int, int]:
    """解析容器运行身份 ``uid[:gid]``，按数值判定非 root（方案 §7 硬规则）。

    ``0`` / ``000`` / ``0:0`` / ``0:65534`` / ``root`` 一律拒绝：``000`` 与
    ``0:65534`` 是字面量比对的漏网写法，``root`` 不是数值身份。调用方（runner）
    必须用它做白名单校验，不能只信 ``ContainerLimits`` 的构造期检查。
    """
    text = str(raw or '').strip()
    match = _CONTAINER_USER_PATTERN.match(text)
    if match is None:
        raise SandboxConfigurationError(f'容器用户必须是数值 uid[:gid]：{raw!r}')
    uid = int(match.group(1))
    gid = int(match.group(2)) if match.group(2) else uid
    if uid == 0:
        raise SandboxConfigurationError('沙箱容器禁止以 root 运行（uid=0）')
    if uid > _MAX_CONTAINER_UID or gid > _MAX_CONTAINER_UID:
        raise SandboxConfigurationError(f'容器用户超出 uid/gid 取值范围：{raw!r}')
    return uid, gid


@dataclass(frozen=True)
class ContainerLimits:
    """容器级资源上限（方案 §7）。由 infrastructure 从环境变量构造。"""

    image: str = 'python:3.11-slim'
    memory: str = '512m'
    memory_swap: str = '512m'
    cpus: float = 1.0
    pids_limit: int = 128
    tmpfs_size: str = '64m'
    timeout_seconds: int = 60
    output_limit_bytes: int = 1024 * 1024
    container_user: str = '65534:65534'
    interpreter: str = 'python3'

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise SandboxConfigurationError('timeout_seconds 必须为正数')
        if self.output_limit_bytes <= 0:
            raise SandboxConfigurationError('output_limit_bytes 必须为正数')
        if self.pids_limit <= 0:
            raise SandboxConfigurationError('pids_limit 必须为正数')
        if self.cpus <= 0:
            raise SandboxConfigurationError('cpus 必须为正数')
        # 按数值判定，不按字面量：``000`` / ``0:65534`` 同样是 uid 0。
        parse_container_identity(self.container_user)


@dataclass(frozen=True)
class ContainerInvocation:
    """一次容器执行请求（infrastructure 端口入参）。

    ``skill_root`` / ``work_dir`` 是**宿主**绝对路径，由 infrastructure 以
    ``--mount type=bind`` 只读 / 可写挂载到容器内固定路径。
    """

    name: str
    skill_root: str
    work_dir: str
    script_relative_path: str
    args: Tuple[str, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict)
    limits: ContainerLimits = field(default_factory=ContainerLimits)


@dataclass(frozen=True)
class ContainerExecution:
    """容器执行结果（infrastructure 端口出参）。"""

    exit_code: int
    stdout: str = ''
    stderr: str = ''
    timed_out: bool = False
    oom_killed: bool = False
    output_truncated: bool = False
    duration_ms: int = 0
    container_id: str = ''
    killed_by_runner: bool = False
    start_failed: bool = False
    work_limit_exceeded: bool = False
    error: str = ''
    #: 实际使用的容器运行时（gVisor ``runsc`` / Firecracker）；证据与审计用。
    runtime: str = ''
    #: True = T2 运行时不可用（缺 ``runsc`` 等），应用层必须映射为
    #: ``T2_RUNTIME_UNAVAILABLE`` 且**不得**回落到 T1。
    runtime_unavailable: bool = False

    @property
    def engine_failed(self) -> bool:
        return bool(self.error) or self.runtime_unavailable


class SandboxExecutor(Protocol):
    """基础设施端口：执行一次性容器。实现见 infrastructure/sandbox/docker_runner.py。"""

    @property
    def limits(self) -> ContainerLimits:  # pragma: no cover - 协议声明
        ...

    def run(self, invocation: ContainerInvocation) -> ContainerExecution:  # pragma: no cover
        ...


@dataclass(frozen=True)
class SandboxArtifactPolicy:
    """``/work`` 产物回收策略（方案 §7 硬规则 3：校验类型与大小）。"""

    max_artifacts: int = 32
    max_artifact_bytes: int = 8 * 1024 * 1024
    max_total_bytes: int = 32 * 1024 * 1024

    @classmethod
    def from_env(cls) -> 'SandboxArtifactPolicy':
        return cls(
            max_artifacts=int(os.environ.get('AGENT_SANDBOX_MAX_ARTIFACTS', '32')),
            max_artifact_bytes=int(
                os.environ.get('AGENT_SANDBOX_MAX_ARTIFACT_BYTES', str(8 * 1024 * 1024))
            ),
            max_total_bytes=int(
                os.environ.get('AGENT_SANDBOX_MAX_TOTAL_ARTIFACT_BYTES', str(32 * 1024 * 1024))
            ),
        )


@dataclass(frozen=True)
class SandboxArtifact:
    relative_path: str
    size_bytes: int
    sha256: str
    #: T2：产物来自哪个阶段（T1 为空串）。
    phase: str = ''


@dataclass(frozen=True)
class SandboxRequest:
    """调用方（单 loop 的 step 执行钩子）传入的 T1 脚本请求。

    ``tier`` 用领域枚举 ``SandboxTier``（§5.3 禁魔法值）；JSON 边界按 value
    传入的字符串在这里一次性转换，未知取值保留原样并由编排层判
    ``UNSUPPORTED_TIER``。
    """

    skill_name: str
    skill_root: Path
    script: str
    args: Tuple[str, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict)
    tier: SandboxTier = SandboxTier.T1_TRUSTED_SCRIPT

    def __post_init__(self) -> None:
        if isinstance(self.tier, SandboxTier):
            return
        try:
            object.__setattr__(self, 'tier', SandboxTier(str(self.tier)))
        except ValueError:
            # 未知层级不在这里抛：交给 run_trusted_script 记 UNSUPPORTED_TIER。
            pass


# ── T2 不可信代码（INT-2489）端口与请求类型 ─────────────────────


@dataclass(frozen=True)
class SandboxRuntimeAvailability:
    """T2 运行时探测结果。不可用时 ``detail`` 必须给出原因（不静默、不降级）。"""

    available: bool
    runtime: str
    runtime_name: str = ''
    detail: str = ''


@dataclass(frozen=True)
class T2Phase:
    """T2 的一个执行阶段（导入/编译、单测、mock 契约、注册表 resolve…）。

    每个阶段一个全新的一次性容器：同一份只读输入 + 独立的 ``/work``。阶段
    ``argv`` 直接作为容器命令执行（不经过宿主 shell），首个非零阶段即终止。
    """

    name: str
    argv: Tuple[str, ...]
    timeout_seconds: int = 0  # 0 = 用执行器默认值

    def __post_init__(self) -> None:
        if not self.name or any(ch.isspace() for ch in self.name):
            raise SandboxConfigurationError('阶段名非法（不能为空/含空白）')
        if (
            not _SAFE_PHASE_NAME_RE.match(self.name)
            or self.name in _UNSAFE_PATH_SEGMENTS
        ):
            raise SandboxConfigurationError(
                f'阶段名非法（只允许 [A-Za-z0-9_.-]，且不得为 . / ..）：{self.name!r}'
            )
        if not self.argv:
            raise SandboxConfigurationError(f'阶段 {self.name} 的命令不能为空')
        if any(not isinstance(arg, str) or '\x00' in arg for arg in self.argv):
            raise SandboxConfigurationError(f'阶段 {self.name} 的命令含非法参数')
        if self.timeout_seconds < 0:
            raise SandboxConfigurationError('阶段超时不能为负数')


@dataclass(frozen=True)
class T2PhaseResult:
    """单个阶段的执行结果（供事件/审计逐阶段落库）。"""

    name: str
    outcome: SandboxOutcome
    reason: SandboxFailureReason = SandboxFailureReason.NONE
    exit_code: int = 0
    duration_ms: int = 0
    stdout: str = ''
    stderr: str = ''
    detail: str = ''

    @property
    def succeeded(self) -> bool:
        return self.outcome is SandboxOutcome.SUCCEEDED


@dataclass(frozen=True)
class T2SandboxRequest:
    """T2 请求：**代码内容副本** + 阶段计划 + 来源标记。

    ``files`` 是相对路径 → 文本内容（驱动/适配器/测试源码）。本层把内容写入
    一次性输入目录并只读挂载到 ``/input``，**不挂载任何宿主目录**。
    """

    code_source: str
    files: Mapping[str, str]
    phases: Tuple[T2Phase, ...]
    env: Mapping[str, str] = field(default_factory=dict)
    #: 需要联网的出口主机（空 = 完全禁网）。非白名单在进容器前拒绝。
    egress_hosts: Tuple[str, ...] = ()
    #: 调用方声明的代码 hash（可选）：必须与本层重算的 sha256 一致。
    code_sha256: str = ''
    #: 产物落 ``agent_artifact`` 用的 run id（可选；空 = 不落库）。
    run_id: str = ''
    tier: str = SANDBOX_TIER_T2


@dataclass(frozen=True)
class T2ContainerInvocation:
    """一次 T2 容器执行请求（infrastructure 端口入参）。"""

    name: str
    input_root: str
    work_dir: str
    command: Tuple[str, ...]
    runtime: str
    limits: ContainerLimits
    env: Mapping[str, str] = field(default_factory=dict)
    #: ``none`` = 完全禁网；白名单出口走 internal 网络（只有代理可达）。
    network: str = 'none'
    timeout_seconds: int = 0


@dataclass(frozen=True)
class T2RunnerOptions:
    """T2 编排策略（与 infrastructure 的 yaml/env 配置解耦，便于单测注入）。"""

    #: 输入代码包上限（防止请求本身成为攻击面）。
    max_input_files: int = 200
    max_input_file_bytes: int = 1024 * 1024
    max_input_total_bytes: int = 2 * 1024 * 1024
    #: ``/work`` 产物回收上限（T2 独立口径：``sandbox.yaml`` 的 ``t2.artifact``
    #: 或 ``AGENT_SANDBOX_T2_MAX_*``；T1 仍走 ``AGENT_SANDBOX_MAX_*``）。
    max_artifacts: int = 32
    max_artifact_bytes: int = 8 * 1024 * 1024
    max_total_bytes: int = 32 * 1024 * 1024
    #: 整份计划的总时长硬限（各阶段超时之外的第二道闸）。
    total_timeout_seconds: int = 300
    #: 是否强制要求代码来源标记（生产 True）。
    require_code_provenance: bool = True
    #: 出口代理白名单：默认全禁网；开启后只允许 ``egress_allowed_hosts``，
    #: 且容器只能挂到 ``egress_network``（internal 网络 + 代理 sidecar）。
    egress_enabled: bool = False
    egress_network: str = ''
    egress_proxy_url: str = ''
    egress_allowed_hosts: Tuple[str, ...] = ()

    def artifact_policy(self) -> SandboxArtifactPolicy:
        """T2 产物回收策略 —— 配置即判定（yaml/env 的 knob 必须真的生效）。"""
        return SandboxArtifactPolicy(
            max_artifacts=self.max_artifacts,
            max_artifact_bytes=self.max_artifact_bytes,
            max_total_bytes=self.max_total_bytes,
        )

    def assert_egress_allowed(self, hosts: Tuple[str, ...]) -> None:
        if not hosts:
            return
        if not self.egress_enabled:
            raise T2EgressDeniedError(
                'T2 默认禁网（方案 §7 硬规则 6）：本请求要求联网但白名单未启用'
            )
        if not self.egress_proxy_url or not self.egress_network:
            raise T2EgressDeniedError(
                'T2 出口代理白名单配置不完整（缺 proxy_url / network）'
            )
        unknown = [host for host in hosts if host not in self.egress_allowed_hosts]
        if unknown:
            raise T2EgressDeniedError(
                f'出口主机不在白名单：{unknown}（允许：{list(self.egress_allowed_hosts)}）'
            )


class UntrustedCodeExecutor(Protocol):
    """基础设施端口：执行 T2 一次性容器。见 infrastructure/sandbox/t2_runner.py。"""

    @property
    def limits(self) -> ContainerLimits:  # pragma: no cover - 协议声明
        ...

    @property
    def runtime(self) -> str:  # pragma: no cover - 协议声明
        ...

    @property
    def runtime_name(self) -> str:  # pragma: no cover - 协议声明
        """docker ``--runtime`` 名（gVisor 通常为 ``runsc``）。"""
        ...

    def availability(self) -> SandboxRuntimeAvailability:  # pragma: no cover
        ...

    def run(self, invocation: T2ContainerInvocation) -> ContainerExecution:  # pragma: no cover
        ...


def canonical_code_sha256(files: Mapping[str, str]) -> str:
    """代码包内容 hash（路径 + 内容，按路径排序，带分隔符防拼接歧义）。"""
    digest = hashlib.sha256()
    for relative in sorted(files):
        content = files[relative]
        digest.update(relative.encode('utf-8'))
        digest.update(b'\x00')
        digest.update(content.encode('utf-8'))
        digest.update(b'\x00')
    return digest.hexdigest()


def default_validation_phases(
    *,
    compile_target: str = '/input',
    interpreter: str = 'python3',
) -> Tuple[T2Phase, ...]:
    """driver_propose 验证链的标准阶段（§6.5 第 5 步）。

    覆盖：导入/编译、单测、mock 厂商契约测试、注册表 resolve 测试。未生成对应
    测试时对应阶段可以省略；本函数给出 4 阶段的默认命令，供 INT-2467 直接消费。
    """
    return (
        T2Phase('import_compile', (interpreter, '-m', 'compileall', '-q', compile_target)),
        T2Phase('unit_test', (interpreter, '-m', 'unittest', 'discover', '-s', '/input/tests')),
        T2Phase(
            'mock_contract',
            (interpreter, '-m', 'unittest', 'discover', '-s', '/input/tests', '-p', 'test_contract*.py'),
        ),
        T2Phase('registry_resolve', (interpreter, '/input/tests/registry_resolve.py')),
    )


@dataclass(frozen=True)
class SandboxResult:
    outcome: SandboxOutcome
    reason: SandboxFailureReason = SandboxFailureReason.NONE
    exit_code: int = 0
    stdout: str = ''
    stderr: str = ''
    artifacts: Tuple[SandboxArtifact, ...] = ()
    duration_ms: int = 0
    container_id: str = ''
    timed_out: bool = False
    output_truncated: bool = False
    detail: str = ''
    #: 所属通道 / 实际运行时 / 代码来源与 hash（T2 审计口径）。
    tier: str = SANDBOX_TIER_T1
    runtime: str = ''
    code_source: str = ''
    code_sha256: str = ''
    phases: Tuple[T2PhaseResult, ...] = ()

    @property
    def succeeded(self) -> bool:
        return self.outcome is SandboxOutcome.SUCCEEDED

    def to_sandbox_event(self) -> dict:
        """``sandbox_*`` 事件载荷（由编排层落库/下发；失败原因必须可追溯）。"""
        return {
            'event': 'sandbox_succeeded' if self.succeeded else 'sandbox_failed',
            'tier': self.tier,
            'runtime': self.runtime,
            'outcome': self.outcome.value,
            'reason': self.reason.value,
            'detail': self.detail,
            'code_source': self.code_source,
            'code_sha256': self.code_sha256,
            'duration_ms': self.duration_ms,
            'phases': [
                {
                    'name': phase.name,
                    'outcome': phase.outcome.value,
                    'reason': phase.reason.value,
                    'exit_code': phase.exit_code,
                    'duration_ms': phase.duration_ms,
                }
                for phase in self.phases
            ],
        }


def looks_like_credential(key: str) -> bool:
    upper = key.upper()
    return any(marker in upper for marker in CREDENTIAL_ENV_MARKERS)


def assert_env_is_credential_free(env: Mapping[str, str]) -> None:
    for key in env:
        if looks_like_credential(key):
            # 只说变量名，不回显值，避免把密钥写进日志。
            raise SandboxConfigurationError(
                f'沙箱环境变量禁止携带凭据：{key}（方案 §7 硬规则 1）'
            )


def assert_no_docker_socket(path: Path, label: str) -> None:
    text = str(path).replace('\\', '/').lower()
    if 'docker.sock' in text:
        raise SandboxConfigurationError(
            f'{label} 命中 docker.sock，生产 agent_service 不得挂载 Docker socket'
        )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _is_bytecode_cache(entry: Path, work_dir: Path) -> bool:
    """``.pyc`` / ``__pycache__`` 等 Python 字节码缓存（不是交付产物）。"""
    try:
        # 用未 resolve 的 work_dir 求相对路径：Windows 上 TEMP 可能是跨盘 junction，
        # resolve() 会把盘符改写掉，导致相对路径求值失败。
        relative = entry.relative_to(work_dir)
    except ValueError:  # 理论上不会发生（entry 均来自 work_dir.rglob）
        return False
    if relative.suffix.lower() in _BYTECODE_SUFFIXES:
        return True
    return any(part in _BYTECODE_DIR_NAMES for part in relative.parts[:-1])


def collect_artifacts(
    work_dir: Path,
    policy: SandboxArtifactPolicy,
    *,
    phase: str = '',
    ignore_bytecode: bool = False,
) -> Tuple[SandboxArtifact, ...]:
    """从 ``/work`` 回收产物并逐项校验（T1/T2 共用）。

    规则：只收常规文件、拒绝符号链接、拒绝逃出 ``/work``、数量/单文件/总量
    上限。任一不满足即抛 ``SandboxArtifactError``，调用方判失败。

    ``ignore_bytecode=True``（T2）跳过 ``.pyc``/``__pycache__``：编译阶段的字节码
    缓存既不是交付产物，也不该占用产物数量/体积上限。
    """
    if not work_dir.exists():
        return ()
    root = work_dir.resolve()
    entries: list[Path] = sorted(work_dir.rglob('*'))
    files: list[Path] = []
    for entry in entries:
        if ignore_bytecode and _is_bytecode_cache(entry, work_dir):
            continue
        # 容器内创建的 Linux 符号链接在 Windows 宿主上表现为不可 stat 的条目：
        # 一律按「无法确认类型」拒绝回收，宁可不给产物也不放行未知类型。
        try:
            entry_lstat = entry.lstat()
        except OSError as exc:
            raise SandboxArtifactError(f'产物无法识别，拒绝回收：{entry.name}') from exc
        if stat_module.S_ISLNK(entry_lstat.st_mode) or entry.is_symlink():
            raise SandboxArtifactError(f'产物禁止符号链接：{entry.name}')
        if stat_module.S_ISDIR(entry_lstat.st_mode):
            continue
        if not stat_module.S_ISREG(entry_lstat.st_mode):
            raise SandboxArtifactError(f'产物必须是常规文件：{entry.name}')
        files.append(entry)

    if len(files) > policy.max_artifacts:
        raise SandboxArtifactTooManyError(
            f'产物数量 {len(files)} 超过上限 {policy.max_artifacts}'
        )

    artifacts: list[SandboxArtifact] = []
    total = 0
    for path in files:
        try:
            resolved = path.resolve()
            size = path.stat().st_size
        except OSError as exc:
            raise SandboxArtifactError(f'产物无法读取，拒绝回收：{path.name}') from exc
        if not resolved.is_relative_to(root):
            raise SandboxArtifactError(f'产物逃出 /work：{path.name}')
        if size > policy.max_artifact_bytes:
            raise SandboxArtifactTooLargeError(
                f'产物 {path.name} 大小 {size}B 超过单文件上限 {policy.max_artifact_bytes}B'
            )
        total += size
        if total > policy.max_total_bytes:
            raise SandboxArtifactTooLargeError(
                f'产物总量 {total}B 超过上限 {policy.max_total_bytes}B'
            )
        artifacts.append(
            SandboxArtifact(
                relative_path=path.relative_to(work_dir).as_posix(),
                size_bytes=size,
                sha256=sha256_file(path),
                phase=phase,
            )
        )
    return tuple(artifacts)


class SandboxRunner:
    """沙箱应用服务：按层级选通道（T1 可信脚本 / T2 不可信代码）。

    每次调用 = 一个或多个一次性容器 + 独立临时目录；容器名带 uuid，执行结束
    无论成败都销毁，两次执行之间零共享状态。T1 行为与 INT-2455 保持一致。
    """

    def __init__(
        self,
        executor: SandboxExecutor | None = None,
        artifact_policy: SandboxArtifactPolicy | None = None,
        work_root: Path | None = None,
        *,
        untrusted_executor: UntrustedCodeExecutor | None = None,
        t2_options: T2RunnerOptions | None = None,
        artifact_repository=None,
        artifact_root: Path | None = None,
        t2_runtime_probe: Callable[[], Tuple[bool, str]] | None = None,
    ) -> None:
        self._executor = executor
        self._artifact_policy = artifact_policy or SandboxArtifactPolicy.from_env()
        self._work_root = Path(work_root) if work_root is not None else None
        self._untrusted_executor = untrusted_executor
        self._t2_options = t2_options or T2RunnerOptions()
        self._artifact_repository = artifact_repository
        self._artifact_root = Path(artifact_root) if artifact_root is not None else None
        # T2 强隔离运行时的可见性探测（返回 (可用, 说明)）。默认不注入 =
        # 无法证明 runsc/firecracker 可用，按 fail-closed 报 T2_RUNTIME_UNAVAILABLE。
        # 装配点见 infrastructure/sandbox/t2_runtime.py:probe_t2_runtime。
        self._t2_runtime_probe = t2_runtime_probe

    # ── 公开入口 ────────────────────────────────────────────────
    def run_by_tier(self, request) -> SandboxResult:
        """按 ``SandboxTier`` 选择 T1/T2 通道；T0/未知层级拒绝执行。"""
        tier = getattr(request, 'tier', '')
        if tier == SANDBOX_TIER_T2:
            return self.run_untrusted_code(request)
        if tier == SANDBOX_TIER_T1:
            return self.run_trusted_script(request)
        return self._rejected(
            SandboxFailureReason.UNSUPPORTED_TIER,
            f'T0_NONE/未知层级不执行代码：{tier!r}（方案 §7）',
            tier=str(tier or ''),
        )

    def run_trusted_script(self, request: SandboxRequest) -> SandboxResult:
        started = time.monotonic()
        if request.tier is SandboxTier.T2_UNTRUSTED_CODE:
            # 拍板#2：T2 缺失强隔离运行时必须明确失败，不得静默降级 T1。
            available, detail = self._probe_t2_runtime()
            if not available:
                return self._rejected(
                    SandboxFailureReason.T2_RUNTIME_UNAVAILABLE,
                    detail or 'T2 强隔离运行时（runsc/firecracker）不可用',
                )
            # 运行时在位但 T2 执行器属后续里程碑：仍按层级不支持拒绝，
            # 不使用 T1 容器冒充 T2。
            return self._rejected(
                SandboxFailureReason.UNSUPPORTED_TIER,
                f'{SandboxTier.T2_UNTRUSTED_CODE.value} 执行器未纳入 M0，'
                f'仅执行 {SandboxTier.T1_TRUSTED_SCRIPT.value}',
            )
        if request.tier is not SandboxTier.T1_TRUSTED_SCRIPT:
            return self._rejected(
                SandboxFailureReason.UNSUPPORTED_TIER,
                f'仅支持 {SandboxTier.T1_TRUSTED_SCRIPT.value}，收到 {request.tier!r}'
                '（T2 请求走 run_untrusted_code）',
                tier=str(request.tier or ''),
            )
        if self._executor is None:
            return self._rejected(
                SandboxFailureReason.RUNNER_ERROR,
                '未装配 T1 沙箱执行器（组合根缺少 executor）',
                tier=SANDBOX_TIER_T1,
            )
        try:
            _, script_relative = self._resolve_script(request)
        except SandboxConfigurationError as exc:
            return self._rejected(SandboxFailureReason.SCRIPT_OUTSIDE_SKILL, str(exc))
        except FileNotFoundError as exc:
            return self._rejected(SandboxFailureReason.SCRIPT_NOT_FOUND, str(exc))

        try:
            assert_env_is_credential_free(request.env)
            skill_root = Path(request.skill_root).resolve()
            assert_no_docker_socket(skill_root, 'skill_root')
        except SandboxConfigurationError as exc:
            return self._rejected(SandboxFailureReason.INVALID_INVOCATION, str(exc))

        work_dir = self._create_work_dir()
        limits = self._executor.limits
        invocation = ContainerInvocation(
            name=self._container_name(request.skill_name),
            skill_root=str(skill_root),
            work_dir=str(work_dir),
            script_relative_path=script_relative,
            args=tuple(request.args),
            env=dict(request.env),
            # 限额唯一口径 = 执行器（runner）配置，应用层不再另行构造。
            limits=limits,
        )
        logger.info(
            '沙箱执行 effective limits：skill=%s image=%s user=%s memory=%s cpus=%s '
            'pids=%s tmpfs=%s timeout=%ss output=%sB',
            request.skill_name, limits.image, limits.container_user, limits.memory,
            limits.cpus, limits.pids_limit, limits.tmpfs_size, limits.timeout_seconds,
            limits.output_limit_bytes,
        )
        try:
            execution = self._executor.run(invocation)
            result = self._map_execution(
                execution,
                work_dir=work_dir,
                duration_fallback_ms=int((time.monotonic() - started) * 1000),
            )
            return result
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    # ── T2：不可信代码（§7 / §6.5 第 5 步）─────────────────────
    def run_untrusted_code(self, request: T2SandboxRequest) -> SandboxResult:
        """在 gVisor 沙箱里执行模型生成代码；运行时不可用即明确失败。

        失败语义见卡面：超时/超资源 → ``BUDGET_EXCEEDED``；运行时/编译失败 →
        ``FAILED``；运行时缺失 → ``T2_RUNTIME_UNAVAILABLE``（绝不回落 T1）。
        """
        started = time.monotonic()
        if request.tier != SANDBOX_TIER_T2:
            return self._rejected(
                SandboxFailureReason.UNSUPPORTED_TIER,
                f'run_untrusted_code 只接受 {SANDBOX_TIER_T2}，收到 {request.tier!r}',
                tier=str(request.tier or ''),
            )
        executor = self._untrusted_executor
        if executor is None:
            return self._t2_failed(
                SandboxFailureReason.T2_RUNTIME_UNAVAILABLE,
                '未装配 T2 执行器：需要 gVisor runsc（方案 §7，不降级到 T1）',
                code_source=request.code_source,
            )
        runtime = executor.runtime
        runtime_name = executor.runtime_name
        availability = executor.availability()
        if not availability.available:
            return self._t2_failed(
                SandboxFailureReason.T2_RUNTIME_UNAVAILABLE,
                f'T2 运行时不可用：{availability.detail or availability.runtime}',
                runtime=runtime,
                code_source=request.code_source,
            )

        options = self._t2_options
        if options.require_code_provenance and not str(request.code_source).strip():
            return self._t2_failed(
                SandboxFailureReason.CODE_PROVENANCE_MISSING,
                'T2 请求必须带代码来源标记（方案 §7 硬规则 6）',
                runtime=runtime,
            )

        code_sha256 = ''
        try:
            self._validate_t2_phases(request.phases)
            self._validate_t2_files(request.files, options)
            self._validate_t2_run_id(request.run_id)
            assert_env_is_credential_free(request.env)
            options.assert_egress_allowed(tuple(request.egress_hosts))
        except T2EgressDeniedError as exc:
            return self._t2_failed(
                SandboxFailureReason.EGRESS_DENIED, str(exc),
                runtime=runtime, code_source=request.code_source,
            )
        except SandboxConfigurationError as exc:
            return self._t2_failed(
                SandboxFailureReason.INPUT_INVALID, str(exc),
                runtime=runtime, code_source=request.code_source,
            )

        code_sha256 = canonical_code_sha256(request.files)
        if request.code_sha256 and request.code_sha256.lower() != code_sha256:
            return self._t2_failed(
                SandboxFailureReason.CODE_PROVENANCE_MISMATCH,
                f'代码 hash 与重算值不一致：声明 {request.code_sha256!r} / 实际 {code_sha256}',
                runtime=runtime,
                code_source=request.code_source,
            )

        run_root = self._create_t2_run_root()
        input_dir = run_root / 'input'
        phase_results: list[T2PhaseResult] = []
        artifacts: list[SandboxArtifact] = []
        artifact_sources: list[tuple[SandboxArtifact, Path]] = []
        stdout_parts: list[str] = []
        stderr_parts: list[str] = []
        outcome = SandboxOutcome.SUCCEEDED
        reason = SandboxFailureReason.NONE
        exit_code = 0
        detail = ''
        container_id = ''
        timed_out = False
        output_truncated = False
        try:
            try:
                self._write_t2_input_tree(input_dir, request.files)
            except SandboxConfigurationError as exc:
                return self._t2_failed(
                    SandboxFailureReason.INPUT_INVALID, str(exc),
                    runtime=runtime, code_source=request.code_source,
                    code_sha256=code_sha256,
                )
            network = 'none'
            env = dict(request.env)
            if request.egress_hosts:
                network = options.egress_network
                env.update({
                    'HTTP_PROXY': options.egress_proxy_url,
                    'HTTPS_PROXY': options.egress_proxy_url,
                    'NO_PROXY': '',
                })
            # T2 产物口径来自 T2RunnerOptions（yaml/env 配置即判定）。
            artifact_policy = options.artifact_policy()
            deadline = time.monotonic() + options.total_timeout_seconds
            for index, phase in enumerate(request.phases):
                remaining = int(deadline - time.monotonic())
                if remaining <= 0:
                    phase_results.append(T2PhaseResult(
                        name=phase.name,
                        outcome=SandboxOutcome.BUDGET_EXCEEDED,
                        reason=SandboxFailureReason.TIMEOUT,
                        detail=f'T2 总时长超限（{options.total_timeout_seconds}s）',
                    ))
                    outcome, reason = SandboxOutcome.BUDGET_EXCEEDED, SandboxFailureReason.TIMEOUT
                    detail = f'阶段 {phase.name} 未执行：总时长超限'
                    timed_out = True
                    break

                work_dir = self._create_t2_work_dir(run_root, index, phase.name)
                timeout = min(
                    phase.timeout_seconds or executor.limits.timeout_seconds,
                    remaining,
                )
                invocation = T2ContainerInvocation(
                    name=self._t2_container_name(phase.name),
                    input_root=str(input_dir),
                    work_dir=str(work_dir),
                    command=tuple(phase.argv),
                    runtime=runtime_name,
                    limits=executor.limits,
                    env=env,
                    network=network,
                    timeout_seconds=timeout,
                )
                try:
                    execution = executor.run(invocation)
                except Exception as exc:  # noqa: BLE001 - 执行器异常不得让 run 抛异常
                    logger.exception('T2 执行器异常（%s）', phase.name)
                    execution = ContainerExecution(
                        exit_code=-1,
                        error=f'执行器异常：{exc}',
                        runtime=runtime,
                    )
                container_id = execution.container_id or container_id
                mapped = self._map_t2_execution(
                    phase,
                    execution,
                    limits=executor.limits,
                    timeout_seconds=timeout,
                    duration_fallback_ms=int((time.monotonic() - started) * 1000),
                )
                if mapped.succeeded:
                    try:
                        phase_artifacts = collect_artifacts(
                            work_dir,
                            artifact_policy,
                            phase=phase.name,
                            ignore_bytecode=True,
                        )
                    except SandboxArtifactTooManyError as exc:
                        mapped = T2PhaseResult(
                            name=phase.name,
                            outcome=SandboxOutcome.BUDGET_EXCEEDED,
                            reason=SandboxFailureReason.ARTIFACT_TOO_MANY,
                            exit_code=execution.exit_code,
                            duration_ms=mapped.duration_ms,
                            stdout=mapped.stdout,
                            stderr=mapped.stderr,
                            detail=str(exc),
                        )
                    except SandboxArtifactTooLargeError as exc:
                        mapped = T2PhaseResult(
                            name=phase.name,
                            outcome=SandboxOutcome.BUDGET_EXCEEDED,
                            reason=SandboxFailureReason.ARTIFACT_TOO_LARGE,
                            exit_code=execution.exit_code,
                            duration_ms=mapped.duration_ms,
                            stdout=mapped.stdout,
                            stderr=mapped.stderr,
                            detail=str(exc),
                        )
                    except SandboxArtifactError as exc:
                        mapped = T2PhaseResult(
                            name=phase.name,
                            outcome=SandboxOutcome.FAILED,
                            reason=SandboxFailureReason.ARTIFACT_INVALID,
                            exit_code=execution.exit_code,
                            duration_ms=mapped.duration_ms,
                            stdout=mapped.stdout,
                            stderr=mapped.stderr,
                            detail=str(exc),
                        )
                    else:
                        artifacts.extend(phase_artifacts)
                        artifact_sources.extend(
                            (artifact, work_dir) for artifact in phase_artifacts
                        )

                phase_results.append(mapped)
                stdout_parts.append(f'[{mapped.name}] {mapped.stdout}')
                stderr_parts.append(f'[{mapped.name}] {mapped.stderr}')
                timed_out = timed_out or execution.timed_out
                output_truncated = output_truncated or execution.output_truncated
                if not mapped.succeeded:
                    outcome, reason, exit_code = (
                        mapped.outcome, mapped.reason, mapped.exit_code
                    )
                    detail = mapped.detail or f'阶段 {phase.name} 失败（{mapped.reason.value}）'
                    break

            self._record_t2_artifacts(
                artifacts, artifact_sources, request=request,
                code_sha256=code_sha256, runtime=runtime,
            )
            return SandboxResult(
                outcome=outcome,
                reason=reason,
                exit_code=exit_code,
                stdout='\n'.join(part for part in stdout_parts if part),
                stderr='\n'.join(part for part in stderr_parts if part),
                artifacts=tuple(artifacts),
                duration_ms=int((time.monotonic() - started) * 1000),
                container_id=container_id,
                timed_out=timed_out,
                output_truncated=output_truncated,
                detail=detail,
                tier=SANDBOX_TIER_T2,
                runtime=runtime,
                code_source=request.code_source,
                code_sha256=code_sha256,
                phases=tuple(phase_results),
            )
        finally:
            shutil.rmtree(run_root, ignore_errors=True)

    # ── T2 内部 ────────────────────────────────────────────────
    @staticmethod
    def _validate_t2_phases(phases: Tuple[T2Phase, ...]) -> None:
        if not phases:
            raise SandboxConfigurationError('T2 至少需要一个执行阶段')
        if len(phases) > T2_MAX_PHASES:
            raise SandboxConfigurationError(
                f'T2 阶段数 {len(phases)} 超过上限 {T2_MAX_PHASES}'
            )
        names = [phase.name for phase in phases]
        if len(set(names)) != len(names):
            raise SandboxConfigurationError(f'T2 阶段名重复：{names}')

    @staticmethod
    def _validate_t2_run_id(run_id: str) -> None:
        """``run_id`` 会成为产物落盘路径分量，进容器前先收口字符集。"""
        if not run_id:
            return
        raw = str(run_id)
        if (
            not _SAFE_RUN_ID_RE.match(raw)
            or raw in _UNSAFE_PATH_SEGMENTS
        ):
            raise SandboxConfigurationError(
                f'run_id 非法（只允许 [A-Za-z0-9_.-]，且不得为 . / ..）：{raw!r}'
            )

    @staticmethod
    def _validate_t2_files(
        files: Mapping[str, str],
        options: T2RunnerOptions,
    ) -> None:
        if not isinstance(files, Mapping):
            raise SandboxConfigurationError('T2 代码包必须是 相对路径→内容 的映射')
        if not files:
            raise SandboxConfigurationError('T2 代码包为空：files 不能为空')
        if len(files) > options.max_input_files:
            raise SandboxConfigurationError(
                f'T2 代码文件数 {len(files)} 超过上限 {options.max_input_files}'
            )
        total = 0
        for relative, content in files.items():
            if not isinstance(relative, str) or not relative.strip():
                raise SandboxConfigurationError('T2 文件路径不能为空')
            if not isinstance(content, str):
                raise SandboxConfigurationError(f'T2 文件内容必须是文本：{relative}')
            raw = relative.replace('\\', '/').strip()
            if raw.startswith('/') or re.match(r'^[A-Za-z]:', raw):
                raise SandboxConfigurationError(f'T2 文件必须是相对路径：{relative}')
            parts = raw.split('/')
            if any(part in ('', '.', '..') for part in parts):
                raise SandboxConfigurationError(f'T2 文件路径非法/穿越：{relative}')
            if '\x00' in raw:
                raise SandboxConfigurationError(f'T2 文件路径含 NUL：{relative}')
            size = len(content.encode('utf-8'))
            if size > options.max_input_file_bytes:
                raise SandboxConfigurationError(
                    f'T2 文件 {raw} 大小 {size}B 超过单文件上限 '
                    f'{options.max_input_file_bytes}B'
                )
            total += size
            if total > options.max_input_total_bytes:
                raise SandboxConfigurationError(
                    f'T2 代码包总量超过上限 {options.max_input_total_bytes}B'
                )

    def _write_t2_input_tree(self, input_dir: Path, files: Mapping[str, str]) -> None:
        input_dir.mkdir(parents=True, exist_ok=True)
        root = input_dir.resolve()
        for relative, content in files.items():
            target = (input_dir / relative.replace('\\', '/')).resolve()
            # 二次防线：解析后仍必须落在输入目录内（符号链接/大小写等）。
            if not target.is_relative_to(root):
                raise SandboxConfigurationError(f'T2 文件逃出输入目录：{relative}')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding='utf-8')
        self._chmod_tree(input_dir)

    def _create_t2_run_root(self) -> Path:
        root = str(self._work_root) if self._work_root is not None else None
        if self._work_root is not None:
            self._work_root.mkdir(parents=True, exist_ok=True)
        run_root = Path(tempfile.mkdtemp(prefix='agent_t2_', dir=root))
        try:
            run_root.chmod(0o777)
        except OSError:
            logger.debug('T2 run_root chmod 不受支持：%s', run_root)
        return run_root

    @staticmethod
    def _chmod_tree(root: Path) -> None:
        """输入卷对容器内非 root（65534）可读；Windows 上由 Docker Desktop 处理。"""
        try:
            root.chmod(0o755)
            for entry in root.rglob('*'):
                entry.chmod(0o755 if entry.is_dir() else 0o644)
        except OSError:
            logger.debug('T2 输入目录 chmod 不受支持：%s', root)

    def _create_t2_work_dir(self, run_root: Path, index: int, phase_name: str) -> Path:
        safe = re.sub(r'[^a-zA-Z0-9_.-]', '-', phase_name)[:24]
        work_dir = run_root / f'work-{index:02d}-{safe}'
        work_dir.mkdir(parents=True, exist_ok=True)
        try:
            work_dir.chmod(0o777)
        except OSError:
            logger.debug('T2 work_dir chmod 不受支持：%s', work_dir)
        return work_dir

    @staticmethod
    def _t2_container_name(phase_name: str) -> str:
        safe = re.sub(r'[^a-zA-Z0-9_.-]', '-', phase_name or 'phase')[:32]
        return f'agent-sandbox-t2-{safe}-{uuid.uuid4().hex[:12]}'

    def _map_t2_execution(
        self,
        phase: T2Phase,
        execution: ContainerExecution,
        *,
        limits: ContainerLimits,
        timeout_seconds: int,
        duration_fallback_ms: int,
    ) -> T2PhaseResult:
        duration = execution.duration_ms or duration_fallback_ms
        base = dict(
            name=phase.name,
            exit_code=execution.exit_code,
            duration_ms=duration,
            stdout=execution.stdout,
            stderr=execution.stderr,
        )
        if execution.runtime_unavailable:
            logger.warning('T2 运行时不可用（%s）：%s', phase.name, execution.error)
            return T2PhaseResult(
                outcome=SandboxOutcome.FAILED,
                reason=SandboxFailureReason.T2_RUNTIME_UNAVAILABLE,
                detail=execution.error,
                **base,
            )
        if execution.engine_failed:
            logger.warning('T2 执行器错误（%s）：%s', phase.name, execution.error)
            return T2PhaseResult(
                outcome=SandboxOutcome.FAILED,
                reason=SandboxFailureReason.CONTAINER_START_FAILED
                if execution.start_failed else SandboxFailureReason.RUNNER_ERROR,
                detail=execution.error,
                **base,
            )
        if execution.timed_out:
            return T2PhaseResult(
                outcome=SandboxOutcome.BUDGET_EXCEEDED,
                reason=SandboxFailureReason.TIMEOUT,
                detail=f'超时终止（{timeout_seconds}s）',
                **base,
            )
        if execution.output_truncated:
            return T2PhaseResult(
                outcome=SandboxOutcome.BUDGET_EXCEEDED,
                reason=SandboxFailureReason.OUTPUT_LIMIT_EXCEEDED,
                detail=f'输出超过上限（{limits.output_limit_bytes}B）',
                **base,
            )
        if execution.oom_killed:
            return T2PhaseResult(
                outcome=SandboxOutcome.BUDGET_EXCEEDED,
                reason=SandboxFailureReason.MEMORY_LIMIT_EXCEEDED,
                detail=f'内存超限终止（{limits.memory}）',
                **base,
            )
        if execution.exit_code == 137:
            return T2PhaseResult(
                outcome=SandboxOutcome.BUDGET_EXCEEDED,
                reason=SandboxFailureReason.RESOURCE_LIMIT_EXCEEDED,
                detail='容器被 SIGKILL（资源上限）',
                **base,
            )
        if execution.exit_code != 0:
            return T2PhaseResult(
                outcome=SandboxOutcome.FAILED,
                reason=SandboxFailureReason.EXIT_CODE_NONZERO,
                detail=f'阶段 {phase.name} 退出码 {execution.exit_code}',
                **base,
            )
        return T2PhaseResult(outcome=SandboxOutcome.SUCCEEDED, **base)

    def _record_t2_artifacts(
        self,
        artifacts: list[SandboxArtifact],
        sources: list[tuple[SandboxArtifact, Path]],
        *,
        request: T2SandboxRequest,
        code_sha256: str,
        runtime: str,
    ) -> None:
        """把 ``/work`` 产物落 ``agent_artifact``（含 sha256 与代码来源）。

        未注入 repository / 无 run_id / 未配置产物根目录时只回传结果（不落库）。
        """
        repository = self._artifact_repository
        if repository is None or not request.run_id or not artifacts:
            return
        if self._artifact_root is None:
            logger.warning(
                'T2 配置了 artifact_repository 但未配置 artifact_root：'
                '产物内容无处落盘，跳过 agent_artifact 写入（%d 个）',
                len(artifacts),
            )
            return
        from agent_service.domain.model.entities import AgentArtifact

        artifact_root = self._artifact_root.resolve()
        for artifact, work_dir in sources:
            try:
                dest = (
                    artifact_root / request.run_id / artifact.phase
                    / artifact.relative_path
                ).resolve()
                # 二次防线：run_id/阶段名/相对路径都收口过，解析后仍必须落在
                # 产物根目录内（符号链接、大小写、Windows 归一化）。
                if not dest.is_relative_to(artifact_root):
                    logger.warning(
                        'T2 产物目标逃出产物根目录，跳过落库：%s/%s',
                        artifact.phase, artifact.relative_path,
                    )
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(work_dir / artifact.relative_path, dest)
                repository.add(AgentArtifact(
                    id=uuid.uuid4().hex,
                    run_id=request.run_id,
                    kind='sandbox_artifact',
                    uri=str(dest),
                    size=artifact.size_bytes,
                    metadata={
                        'sha256': artifact.sha256,
                        'sandbox_tier': SANDBOX_TIER_T2,
                        'runtime': runtime,
                        'phase': artifact.phase,
                        'code_source': request.code_source,
                        'code_sha256': code_sha256,
                    },
                ))
            except Exception as exc:  # noqa: BLE001 - 落库失败不掩盖沙箱结论
                logger.warning('T2 产物落库失败（%s）：%s', artifact.relative_path, exc)

    @staticmethod
    def _t2_failed(
        reason: SandboxFailureReason,
        detail: str,
        *,
        runtime: str = '',
        code_source: str = '',
        code_sha256: str = '',
    ) -> SandboxResult:
        logger.warning('T2 请求失败：%s — %s', reason.value, detail)
        return SandboxResult(
            outcome=SandboxOutcome.FAILED,
            reason=reason,
            exit_code=-1,
            detail=detail,
            tier=SANDBOX_TIER_T2,
            runtime=runtime,
            code_source=code_source,
            code_sha256=code_sha256,
        )

    # ── 内部 ───────────────────────────────────────────────────
    def _resolve_script(self, request: SandboxRequest) -> tuple[Path, str]:
        skill_root = Path(request.skill_root).resolve()
        if not skill_root.is_dir():
            raise SandboxConfigurationError(f'skill_root 不存在：{skill_root}')

        raw = str(request.script).replace('\\', '/').strip()
        if not raw:
            raise SandboxConfigurationError('script 不能为空')
        if raw.startswith('/') or re.match(r'^[A-Za-z]:', raw):
            raise SandboxConfigurationError(f'script 必须是相对路径：{request.script}')
        if any(part in _SCRIPT_RELATIVE_FORBIDDEN for part in Path(raw).parts):
            raise SandboxConfigurationError(f'script 禁止路径穿越：{request.script}')

        candidate = (skill_root / raw).resolve()
        if not candidate.is_relative_to(skill_root):
            raise SandboxConfigurationError(f'script 逃出 skill 目录：{request.script}')
        scripts_dir = (skill_root / SCRIPTS_DIR_NAME).resolve()
        if not candidate.is_relative_to(scripts_dir):
            raise SandboxConfigurationError(
                f'T1 只执行 {SCRIPTS_DIR_NAME}/ 下的脚本：{request.script}'
            )
        if not candidate.is_file():
            raise FileNotFoundError(f'脚本不存在：{request.script}')

        relative = candidate.relative_to(skill_root).as_posix()
        return candidate, relative

    def _create_work_dir(self) -> Path:
        root = str(self._work_root) if self._work_root is not None else None
        if self._work_root is not None:
            self._work_root.mkdir(parents=True, exist_ok=True)
        work_dir = Path(tempfile.mkdtemp(prefix='agent_sandbox_', dir=root))
        # 容器以非 root 运行（65534），一次性临时目录需可写；目录用后即删。
        try:
            work_dir.chmod(0o777)
        except OSError:  # Windows 上 chmod 语义受限，目录 ACL 由 Docker Desktop 处理
            logger.debug('work_dir chmod 不受支持：%s', work_dir)
        return work_dir

    @staticmethod
    def _container_name(skill_name: str) -> str:
        safe = re.sub(r'[^a-zA-Z0-9_.-]', '-', skill_name or 'skill')[:40]
        return f'agent-sandbox-t1-{safe}-{uuid.uuid4().hex[:12]}'

    def _map_execution(
        self,
        execution: ContainerExecution,
        work_dir: Path,
        duration_fallback_ms: int,
    ) -> SandboxResult:
        duration = execution.duration_ms or duration_fallback_ms

        if execution.engine_failed:
            logger.warning('沙箱执行器错误：%s', execution.error)
            return SandboxResult(
                outcome=SandboxOutcome.FAILED,
                reason=SandboxFailureReason.CONTAINER_START_FAILED
                if execution.start_failed else SandboxFailureReason.RUNNER_ERROR,
                exit_code=execution.exit_code,
                stdout=execution.stdout,
                stderr=execution.stderr,
                duration_ms=duration,
                container_id=execution.container_id,
                detail=execution.error,
            )

        if execution.timed_out:
            return self._budget(
                execution, SandboxFailureReason.TIMEOUT, duration,
                detail=f'超时终止（{self._executor.limits.timeout_seconds}s）',
            )
        if execution.work_limit_exceeded:
            return self._budget(
                execution, SandboxFailureReason.RESOURCE_LIMIT_EXCEEDED, duration,
                detail='执行中 /work 写入超过容量上限，容器被终止',
            )
        if execution.output_truncated:
            return self._budget(
                execution, SandboxFailureReason.OUTPUT_LIMIT_EXCEEDED, duration,
                detail=f'输出超过上限（{self._executor.limits.output_limit_bytes}B）',
            )
        if execution.oom_killed:
            return self._budget(
                execution, SandboxFailureReason.MEMORY_LIMIT_EXCEEDED, duration,
                detail=f'内存超限终止（{self._executor.limits.memory}）',
            )
        if execution.exit_code == SANDBOX_TIMEOUT_EXIT_CODE:
            # 容器内 ``timeout`` 自限到点（宿主计时器在此前已消失时的兜底）：
            # 这是超时，不是脚本非零退出，必须判 BUDGET_EXCEEDED。
            return self._budget(
                execution, SandboxFailureReason.TIMEOUT, duration,
                detail=f'容器内 timeout 自限终止（{self._executor.limits.timeout_seconds}s）',
            )
        if execution.exit_code == 137:
            return self._budget(
                execution, SandboxFailureReason.RESOURCE_LIMIT_EXCEEDED, duration,
                detail='容器被 SIGKILL（资源上限）',
            )
        if execution.exit_code != 0:
            return SandboxResult(
                outcome=SandboxOutcome.FAILED,
                reason=SandboxFailureReason.EXIT_CODE_NONZERO,
                exit_code=execution.exit_code,
                stdout=execution.stdout,
                stderr=execution.stderr,
                duration_ms=duration,
                container_id=execution.container_id,
            )

        try:
            artifacts = self._collect_artifacts(work_dir)
        except SandboxArtifactTooLargeError as exc:
            return SandboxResult(
                outcome=SandboxOutcome.FAILED,
                reason=SandboxFailureReason.ARTIFACT_TOO_LARGE,
                exit_code=execution.exit_code,
                stdout=execution.stdout,
                stderr=execution.stderr,
                duration_ms=duration,
                container_id=execution.container_id,
                detail=str(exc),
            )
        except SandboxArtifactError as exc:
            return SandboxResult(
                outcome=SandboxOutcome.FAILED,
                reason=SandboxFailureReason.ARTIFACT_INVALID,
                exit_code=execution.exit_code,
                stdout=execution.stdout,
                stderr=execution.stderr,
                duration_ms=duration,
                container_id=execution.container_id,
                detail=str(exc),
            )

        return SandboxResult(
            outcome=SandboxOutcome.SUCCEEDED,
            reason=SandboxFailureReason.NONE,
            exit_code=0,
            stdout=execution.stdout,
            stderr=execution.stderr,
            artifacts=artifacts,
            duration_ms=duration,
            container_id=execution.container_id,
        )

    def _budget(
        self,
        execution: ContainerExecution,
        reason: SandboxFailureReason,
        duration: int,
        detail: str,
    ) -> SandboxResult:
        return SandboxResult(
            outcome=SandboxOutcome.BUDGET_EXCEEDED,
            reason=reason,
            exit_code=execution.exit_code,
            stdout=execution.stdout,
            stderr=execution.stderr,
            duration_ms=duration,
            container_id=execution.container_id,
            timed_out=execution.timed_out or reason is SandboxFailureReason.TIMEOUT,
            output_truncated=execution.output_truncated,
            detail=detail,
        )

    def _collect_artifacts(
        self, work_dir: Path, phase: str = ''
    ) -> Tuple[SandboxArtifact, ...]:
        return collect_artifacts(work_dir, self._artifact_policy, phase=phase)

    @staticmethod
    def _sha256(path: Path) -> str:
        return sha256_file(path)

    def _probe_t2_runtime(self) -> Tuple[bool, str]:
        """T2 运行时可见性（fail-closed：未注入即视为不可用）。"""
        if self._t2_runtime_probe is None:
            return False, ('未注入 T2 运行时探测：无法证明 runsc/firecracker '
                           '可用，T2_UNTRUSTED_CODE 拒绝执行')
        try:
            available, detail = self._t2_runtime_probe()
        except Exception as exc:  # noqa: BLE001 - 探测异常同样按不可用处理
            return False, f'T2 运行时探测异常：{exc}'
        return bool(available), str(detail or '')

    @staticmethod
    def _rejected(
        reason: SandboxFailureReason,
        detail: str,
        *,
        tier: str = SANDBOX_TIER_T1,
    ) -> SandboxResult:
        logger.warning('沙箱请求被拒绝：%s — %s', reason.value, detail)
        return SandboxResult(
            outcome=SandboxOutcome.FAILED,
            reason=reason,
            exit_code=-1,
            detail=detail,
            tier=tier,
        )
