# -*- coding: utf-8 -*-
"""T1 可信脚本沙箱 — 应用层编排（方案 doc/agent化/07 §7，INT-2455）。

职责边界
--------
本模块只做**编排与判定**，不碰 Docker：

1. 只接受 ``T1_TRUSTED_SCRIPT``（Skill 自带 ``scripts/``）；``T0_NONE`` /
   ``T2_UNTRUSTED_CODE`` 一律拒绝（T2 首期不执行，只产出提案）。
2. 校验脚本必须落在 ``<skill_root>/scripts/`` 内，禁止 ``../`` 穿越与绝对路径。
3. 把执行交给 ``SandboxExecutor`` 端口（infrastructure/sandbox/docker_runner.py
   的 Docker 一次性容器实现）。
4. 产物**只**从容器 ``/work`` 回收，逐项校验（常规文件、非符号链接、单文件与
   总量上限），校验失败即判 ``FAILED``。
5. 失败不得静默成功：超时/输出超限/内存超限 → ``BUDGET_EXCEEDED``；非零退出/
   容器起不来/产物非法 → ``FAILED``，并记录原因码。

Docker 访问方式（负责人红线）：agent_service 进程**不持有 docker.sock**，
只通过独立的 runner/sidecar（HTTP）或宿主 runner 访问 Docker；两种方式都由
infrastructure 层实现，见 ``DockerRunnerMode``。
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

#: 容器内 ``timeout`` 自限到点时的退出码（GNU coreutils 约定）。
#: 宿主侧计时器消失时容器由它自己结束；判 BUDGET_EXCEEDED，不是 FAILED。
SANDBOX_TIMEOUT_EXIT_CODE = 124

#: 容器内固定挂载点（Skill 只读、/work 可写）。
SKILL_MOUNT_PATH = '/skill'
WORK_MOUNT_PATH = '/work'
SCRIPTS_DIR_NAME = 'scripts'

#: 允许出现在容器内的环境变量名白名单前缀之外的凭据特征（出现即拒绝）。
CREDENTIAL_ENV_MARKERS = (
    'PASSWORD', 'PASSWD', 'SECRET', 'TOKEN', 'API_KEY', 'APIKEY',
    'ACCESS_KEY', 'ACCESSKEY', 'PRIVATE_KEY', 'CREDENTIAL', 'AUTH',
    'DATABASE_URL', 'DB_URL', 'DB_HOST', 'DB_PASSWORD', 'DB_USER',
    'OSS_', 'S3_', 'MINIO', 'LLM_', 'OPENAI', 'DEEPSEEK', 'ANTHROPIC',
    'CLAUDE', 'MODEL_API', 'REDIS_URL', 'REDIS_PASSWORD', 'DOCKER_HOST',
)

_SCRIPT_RELATIVE_FORBIDDEN = ('..',)


class SandboxOutcome(str, Enum):
    """run 层面的沙箱结果（对齐 RunStatus 的失败口径）。"""

    SUCCEEDED = 'SUCCEEDED'
    FAILED = 'FAILED'
    BUDGET_EXCEEDED = 'BUDGET_EXCEEDED'


class SandboxFailureReason(str, Enum):
    """失败原因码 — 禁止魔法字符串，失败必须能回答「为什么」。"""

    NONE = 'NONE'
    UNSUPPORTED_TIER = 'UNSUPPORTED_TIER'
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


class SandboxConfigurationError(RuntimeError):
    """沙箱配置/请求非法（凭证、路径、层级等）— 拒绝执行，不进入容器。"""


class SandboxArtifactError(SandboxConfigurationError):
    """``/work`` 产物校验失败。"""


class SandboxArtifactTooLargeError(SandboxArtifactError):
    """产物超出单文件大小 / 总量 / 数量上限。"""


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

    @property
    def engine_failed(self) -> bool:
        return bool(self.error)


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

    @property
    def succeeded(self) -> bool:
        return self.outcome is SandboxOutcome.SUCCEEDED


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


class SandboxRunner:
    """T1 可信脚本执行器（应用服务）。

    每次调用 = 一个一次性容器 + 一个独立 ``/work`` 临时目录；容器名带 uuid，
    执行结束无论成败都销毁，两次执行之间零共享状态。
    """

    def __init__(
        self,
        executor: SandboxExecutor,
        artifact_policy: SandboxArtifactPolicy | None = None,
        work_root: Path | None = None,
    ) -> None:
        self._executor = executor
        self._artifact_policy = artifact_policy or SandboxArtifactPolicy.from_env()
        self._work_root = Path(work_root) if work_root is not None else None

    # ── 公开入口 ────────────────────────────────────────────────
    def run_trusted_script(self, request: SandboxRequest) -> SandboxResult:
        started = time.monotonic()
        if request.tier is not SandboxTier.T1_TRUSTED_SCRIPT:
            return self._rejected(
                SandboxFailureReason.UNSUPPORTED_TIER,
                f'仅支持 {SandboxTier.T1_TRUSTED_SCRIPT.value}，收到 {request.tier!r}（T2 首期不执行）',
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

    def _collect_artifacts(self, work_dir: Path) -> Tuple[SandboxArtifact, ...]:
        if not work_dir.exists():
            return ()
        policy = self._artifact_policy
        entries: list[Path] = sorted(work_dir.rglob('*'))
        files: list[Path] = []
        for entry in entries:
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
            raise SandboxArtifactTooLargeError(
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
            if not resolved.is_relative_to(work_dir.resolve()):
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
                    sha256=self._sha256(path),
                )
            )
        return tuple(artifacts)

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open('rb') as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _rejected(reason: SandboxFailureReason, detail: str) -> SandboxResult:
        logger.warning('沙箱请求被拒绝：%s — %s', reason.value, detail)
        return SandboxResult(
            outcome=SandboxOutcome.FAILED,
            reason=reason,
            exit_code=-1,
            detail=detail,
        )
