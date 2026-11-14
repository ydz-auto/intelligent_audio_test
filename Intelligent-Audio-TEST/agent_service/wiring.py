# -*- coding: utf-8 -*-
"""组合根（composition root）：装配 domain 端口 → infrastructure 适配器。

不放在 application 里，避免应用层反向依赖具体实现；接口层（app.py）调用。
测试可直接传入自定义 session_factory / provider_resolver / tool_gateway / wakeup。
"""
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from agent_service.application.approval_service import (
    ApprovalService, ApprovalSettings,
)
from agent_service.application.cancel_registry import CancelRegistry
from agent_service.application.context_assembler import (
    CompactionSettings, ContextAssembler,
)
from agent_service.application.driver_proposal_service import (
    DriverProposalService, DriverProposalSettings,
)
from agent_service.application.event_stream import EventStreamService
from agent_service.application.exploration_service import ExplorationService
from agent_service.application.memory_service import (
    MemoryService, MemoryServiceSettings,
)
from agent_service.application.provider_service import ProviderService
from agent_service.application.recovery_service import RecoveryService
from agent_service.application.run_orchestrator import (
    OrchestratorSettings, RunOrchestrator,
)
from agent_service.application.run_service import RunService
from agent_service.application.run_worker import (
    RunExecutor, ThreadPoolRunExecutor,
)
from agent_service.application.sandbox_dispatch import (
    SandboxScriptDispatcher, SandboxToolExecutor, SkillScripts,
)
from agent_service.application.sandbox_runner import (
    SandboxArtifactPolicy, SandboxConfigurationError, SandboxRunner,
)
from agent_service.application.skill_registry import SkillRegistry
from agent_service.application.skill_guard import SkillGuard
from agent_service.application.skill_review_service import SkillReviewService
from agent_service.application.skill_service import SkillService
from agent_service.application.tool_gateway import SharedToolGateway
from agent_service.config.config import Config
from agent_service.domain.model.context_budget import SectionRatios
from agent_service.domain.ports.artifact_store import ArtifactStore
from agent_service.domain.ports.llm_provider import (
    LlmProviderResolver, ProviderVerifier,
)
from agent_service.domain.ports.run_wakeup import RunWakeup
from agent_service.domain.ports.side_effects import ReadOnlySideEffectChecker
from agent_service.domain.ports.tool_gateway import ToolGateway
from agent_service.domain.services.context_budget_policy import (
    ContextBudgetPolicy,
)
from agent_service.domain.services.context_window_resolver import (
    ContextWindowResolver,
)
from agent_service.infrastructure.artifacts.oss_artifact_store import (
    OssArtifactStore,
)
from agent_service.infrastructure.llm.credential_store import CredentialStore
from agent_service.infrastructure.llm.provider_registry import ProviderRegistry
from agent_service.infrastructure.llm.verifier import HttpProviderVerifier
from agent_service.infrastructure.memory import (
    FileMemoryStore, MemoryStoreSettings, load_sensitive_rules,
)
from agent_service.infrastructure.memory.paths import AUDIT_DIR
from agent_service.infrastructure.persistence.repositories import (
    SqlApprovalRepository, SqlArtifactRepository, SqlContextSnapshotRepository,
    SqlEventRepository, SqlLlmProviderRepository, SqlRunRepository,
    SqlSessionRepository, SqlStepRepository, SqlToolCallRepository,
)
from agent_service.infrastructure.sandbox.policy import load_t2_policy
from agent_service.infrastructure.sandbox.t2_runner import build_t2_executor
from agent_service.infrastructure.skill.fs_skill_repository import (
    FsSkillRepository,
)
from agent_service.infrastructure.skill.composite_skill_repository import (
    CompositeSkillRepository,
)
from agent_service.infrastructure.skill.json_golden_task_provider import (
    JsonGoldenTaskProvider,
)
from agent_service.infrastructure.skill.oss_resource_store import (
    OssSkillResourceStore,
)
from agent_service.infrastructure.skill.platform_resources import (
    load_platform_resources,
)
from agent_service.infrastructure.persistence.skill_repositories import (
    SqlAgentRunSkillRepository, SqlAgentSkillRepository,
    SqlSkillReviewRepository,
)
from agent_service.infrastructure.sandbox.docker_runner import (
    DockerRunnerConfig, DockerRunnerMode, SandboxPolicy, build_sandbox_executor,
)
from agent_service.infrastructure.tools.device_lease import (
    PhysicalDeviceLeaseAdapter,
)
from agent_service.infrastructure.tools.registry_bridge import (
    RestToolClient, RunCredentialRegistry, SharedToolRegistryBridge,
)
from agent_service.infrastructure.wakeup import LocalRunWakeup, RedisRunWakeup
from shared.agent_tools.ui_exploration import ExplorationBudget

logger = logging.getLogger(__name__)


@dataclass
class AgentContainer:
    run_service: RunService
    event_stream: EventStreamService
    recovery: RecoveryService
    executor: RunExecutor
    wakeup: RunWakeup
    orchestrator: RunOrchestrator
    assembler: ContextAssembler
    skill_registry: SkillRegistry
    provider_service: ProviderService = None
    provider_registry: LlmProviderResolver = None
    tool_gateway: ToolGateway = None
    credentials: RunCredentialRegistry = None
    sandbox: SandboxToolExecutor = None
    budget_policy: Optional[ContextBudgetPolicy] = None
    compaction_settings: Optional[CompactionSettings] = None
    memory_service: Optional[MemoryService] = None
    approval_service: Optional[ApprovalService] = None
    skill_service: Optional[SkillService] = None
    skill_review_service: Optional[SkillReviewService] = None
    repositories: dict = field(default_factory=dict)

    def shutdown(self) -> None:
        try:
            self.executor.shutdown()
        finally:
            self.wakeup.close()


def _build_window_resolver() -> ContextWindowResolver:
    return ContextWindowResolver.from_file(Config.MODEL_CATALOG_PATH or None)


def _build_provider_registry(session_factory, *,
                             credentials: CredentialStore,
                             windows: ContextWindowResolver,
                             http_transport=None) -> ProviderRegistry:
    registry = ProviderRegistry(
        providers=SqlLlmProviderRepository(session_factory),
        credentials=credentials,
        windows=windows,
        timeout_seconds=Config.LLM_TIMEOUT_SECONDS,
        temperature=Config.LLM_TEMPERATURE,
        include_usage=Config.LLM_STREAM_INCLUDE_USAGE,
        output_token_cap=Config.OUTPUT_TOKEN_CAP,
        output_token_ratio=Config.OUTPUT_TOKEN_RATIO,
        http_transport=http_transport,
    )
    return registry


def build_wakeup(wakeup: Optional[RunWakeup] = None) -> RunWakeup:
    if wakeup is not None:
        return wakeup
    if Config.EVENT_WAKEUP_BACKEND == 'redis':
        redis_wakeup = RedisRunWakeup(Config.REDIS_URL, Config.EVENT_CHANNEL)
        redis_wakeup.start()
        return redis_wakeup
    return LocalRunWakeup()


def build_skill_registry(tool_gateway: ToolGateway,
                         skills_root: Optional[str] = None,
                         strict: Optional[bool] = None,
                         custom=None) -> SkillRegistry:
    """装配 SkillRegistry 并装载 skills 目录（§4）。

    allowed-tools 的事实源是工具注册表：当前取自 ToolGateway.all_tools()；
    INT-2453 把注册表抽到 shared/agent_tools 后，这里换成同一份 Schema 即可，
    不为两套口径写兼容分支。

    INT-2549：``custom`` 为自定义 Skill 仓储时走 ``CompositeSkillRepository``，
    平台只读层 + 自定义层合并去重（USER > TENANT > PLATFORM）。
    """
    platform = FsSkillRepository(skills_root or Config.SKILLS_ROOT)
    repository = (CompositeSkillRepository(platform, custom)
                  if custom is not None else platform)
    registry = SkillRegistry(
        repository,
        known_tools=lambda: [d.name for d in tool_gateway.all_tools()],
        max_body_lines=Config.SKILL_BODY_MAX_LINES,
        strict=(Config.SKILL_VALIDATION_STRICT if strict is None else strict),
        l1_budget_tokens=Config.skill_l1_budget_tokens(),
    )
    return registry.load()


def build_skill_service(gateway: ToolGateway,
                        skills: SkillRegistry,
                        skill_repository,
                        run_skill_repository,
                        resource_store=None,
                        golden_tasks=None,
                        guard=None,
                        settings=None,
                        reviews=None) -> SkillService:
    """装配自定义 Skill 应用服务（INT-2549 / INT-2551）。"""

    def known_tools():
        from shared.agent_tools.intent_tools import INTENT_TOOL_BY_NAME
        names = set(INTENT_TOOL_BY_NAME)
        names.update(d.name for d in gateway.all_tools())
        return sorted(names)

    return SkillService(
        repository=skill_repository,
        run_skills=run_skill_repository,
        registry=skills,
        resource_store=resource_store or OssSkillResourceStore(),
        golden_tasks=golden_tasks or JsonGoldenTaskProvider(
            Config.SKILL_GOLDEN_TASKS_PATH),
        guard=guard or SkillGuard(rules_path=Config.SKILL_GUARD_RULES_PATH),
        known_tools=known_tools,
        settings=settings or Config.skill_settings(),
        platform_resources=load_platform_resources,
        reviews=reviews,
    )


def _skill_script_locator(skills: Optional[SkillRegistry]):
    """Skill 名 → 已登记的 ``scripts/`` 清单（T1 只执行登记过的脚本）。"""

    def locate(name: str) -> Optional[SkillScripts]:
        skill = skills.get(name) if skills is not None else None
        if skill is None:
            return None
        return SkillScripts(skill_name=skill.name, root=Path(skill.path),
                            scripts=tuple(skill.scripts))

    return locate


def build_memory_service() -> MemoryService:
    """装配文件式长期记忆（INT-2490，§8.6 / §8.6.1）。

    敏感信息规则缺失 / 非法即启动失败：没有扫描规则就绝不放行
    ``memory_write``（防静默无扫描写入）。
    """
    rules = load_sensitive_rules(Config.MEMORY_SENSITIVE_RULES_PATH)
    store = FileMemoryStore(MemoryStoreSettings(
        root=Config.MEMORY_ROOT,
        skills_root=Config.SKILLS_ROOT,
        rg_binary=Config.MEMORY_RG_BIN,
        rg_timeout_seconds=Config.MEMORY_RG_TIMEOUT_SECONDS,
        search_default_limit=Config.MEMORY_SEARCH_DEFAULT_LIMIT,
        search_max_limit=Config.MEMORY_SEARCH_MAX_LIMIT,
        max_query_chars=Config.MEMORY_SEARCH_MAX_QUERY_CHARS,
        snippet_chars=Config.MEMORY_SNIPPET_CHARS,
        summary_max_tokens=Config.MEMORY_INJECT_MAX_TOKENS,
        summary_max_projects=Config.MEMORY_SUMMARY_MAX_PROJECTS,
        summary_lines_per_file=Config.MEMORY_SUMMARY_LINES_PER_FILE,
        user_quota_bytes=Config.MEMORY_USER_QUOTA_BYTES,
        sensitive_rules=rules,
    ))
    return MemoryService(
        store,
        settings=MemoryServiceSettings(
            inject_max_tokens=Config.MEMORY_INJECT_MAX_TOKENS,
            search_default_limit=Config.MEMORY_SEARCH_DEFAULT_LIMIT),
        audit_path=str(Path(Config.MEMORY_ROOT) / AUDIT_DIR))


def build_sandbox_tool_executor(        skills: Optional[SkillRegistry] = None,
        *, runner: Optional[SandboxRunner] = None,
        output_summary_chars: Optional[int] = None,
        max_result_chars: Optional[int] = None) -> SandboxScriptDispatcher:
    """按配置装配 T1 沙箱执行链（INT-2495）。

    - ``runner_http``（生产默认）：只向 runner/sidecar 发 HTTP；``host_cli``
      供开发机 / 宿主 runner 进程内执行。执行器由 ``AGENT_SANDBOX_*`` 配置。
    - 配置不完整（例如还没部署 runner）**不阻断 agent_service 启动**：T1 调用
      按 ``RUNNER_ERROR`` 显式失败，绝不降级成 T0 静默执行。
    """
    options = dict(
        output_summary_chars=(
            Config.SANDBOX_OUTPUT_SUMMARY_CHARS
            if output_summary_chars is None else output_summary_chars),
        max_result_chars=(
            Config.TOOL_RESULT_MAX_CHARS
            if max_result_chars is None else max_result_chars),
    )
    locate = _skill_script_locator(skills)
    if runner is not None:
        return SandboxScriptDispatcher(runner, locate, **options)
    try:
        policy = SandboxPolicy.from_env()
        config = DockerRunnerConfig(
            mode=DockerRunnerMode(Config.SANDBOX_EXECUTOR_MODE),
            docker_binary=Config.SANDBOX_DOCKER_BIN,
            runner_url=Config.SANDBOX_RUNNER_URL.rstrip('/'),
            runner_token=Config.SANDBOX_RUNNER_TOKEN,
            limits=policy.limits,
            policy=policy,
        )
        sandbox_runner = SandboxRunner(
            build_sandbox_executor(config),
            SandboxArtifactPolicy.from_env(),
            work_root=Path(Config.SANDBOX_WORK_ROOT) if Config.SANDBOX_WORK_ROOT else None,
        )
    except (SandboxConfigurationError, ValueError) as exc:
        logger.warning(
            '沙箱执行器未就绪（T1 工具调用将按 RUNNER_ERROR 失败）：%s', exc)
        return SandboxScriptDispatcher.unavailable(
            configuration_error=str(exc), **options)
    logger.info('沙箱执行器已装配：mode=%s', config.mode.value)
    return SandboxScriptDispatcher(sandbox_runner, locate, **options)


def build_driver_proposal_runner() -> Optional[SandboxRunner]:
    """装配 T2 沙箱执行器（驱动提案验证用；INT-2467）。

    与 T1 同一组合口径：``runner_http`` 只发 HTTP、``host_cli`` 供宿主 runner。
    运行时装不上就返回 ``None`` —— 提案服务按 ``T2_RUNTIME_UNAVAILABLE`` 显式
    失败，绝不降级到 T1 执行模型生成的代码（方案 §7）。
    """
    try:
        policy = load_t2_policy()
        executor = build_t2_executor(policy)
        return SandboxRunner(
            untrusted_executor=executor,
            work_root=(Path(Config.SANDBOX_WORK_ROOT)
                       if Config.SANDBOX_WORK_ROOT else None),
            t2_options=policy.to_runner_options(),
        )
    except (SandboxConfigurationError, ValueError) as exc:
        logger.warning('T2 沙箱执行器未就绪（driver_propose 将显式失败）：%s', exc)
        return None


def build_container(session_factory,
                    provider_resolver: Optional[LlmProviderResolver] = None,
                    tool_gateway: Optional[ToolGateway] = None,
                    wakeup: Optional[RunWakeup] = None,
                    executor_factory: Optional[Callable] = None,
                    budget_defaults: Optional[dict] = None,
                    terminal_grace_seconds: Optional[float] = None,
                    skill_registry: Optional[SkillRegistry] = None,
                    skills_root: Optional[str] = None,
                    credential_store: Optional[CredentialStore] = None,
                    window_resolver: Optional[ContextWindowResolver] = None,
                    provider_verifier: Optional[ProviderVerifier] = None,
                    sandbox: Optional[SandboxToolExecutor] = None,
                    http_transport=None,
                    context_max_runs: Optional[int] = None,
                    context_max_messages: Optional[int] = None,
                    artifact_store: Optional[ArtifactStore] = None,
                    compaction_settings: Optional[CompactionSettings] = None,
                    budget_ratios: Optional[SectionRatios] = None,
                    context_debug: Optional[bool] = None,
                    memory_service: Optional[MemoryService] = None,
                    skill_resource_store=None,
                    golden_tasks=None,
                    skill_guard=None,
                    skill_settings=None,
                    ) -> AgentContainer:
    """组合根。``budget_defaults`` / ``terminal_grace_seconds`` /
    ``skill_registry`` / ``skills_root`` 与 ``provider_resolver`` /
    ``credential_store`` / ``window_resolver`` / ``provider_verifier`` /
    ``sandbox`` / ``http_transport`` 仅供测试注入替身；生产一律取 Config + 环境。
    ``context_max_runs`` / ``context_max_messages`` / ``artifact_store`` /
    ``compaction_settings`` / ``budget_ratios`` / ``context_debug`` 同样仅供
    测试（如 50 轮压缩评测）覆盖配置。"""
    budgets = budget_defaults or Config.budget_defaults()
    sessions = SqlSessionRepository(session_factory)
    runs = SqlRunRepository(session_factory)
    events = SqlEventRepository(session_factory)
    steps = SqlStepRepository(session_factory)
    tool_calls = SqlToolCallRepository(session_factory)
    approvals = SqlApprovalRepository(session_factory)
    artifacts = SqlArtifactRepository(session_factory)
    snapshots = SqlContextSnapshotRepository(session_factory)
    provider_repository = SqlLlmProviderRepository(session_factory)
    # INT-2549：自定义 Skill 当前行 / 版本 / run 快照
    skill_repository = SqlAgentSkillRepository(session_factory)
    run_skill_repository = SqlAgentRunSkillRepository(session_factory)
    # INT-2551：审核链审计（只追加）
    skill_review_repository = SqlSkillReviewRepository(session_factory)

    credentials = credential_store or CredentialStore.from_env()
    windows = window_resolver or _build_window_resolver()
    verifier = provider_verifier or HttpProviderVerifier(
        timeout_seconds=Config.PROVIDER_VERIFY_TIMEOUT_SECONDS,
        http_transport=http_transport)
    registry = provider_resolver or _build_provider_registry(
        session_factory, credentials=credentials, windows=windows,
        http_transport=http_transport)
    provider_service = ProviderService(
        providers=provider_repository, credentials=credentials,
        windows=windows, verifier=verifier)

    wakeup = build_wakeup(wakeup)
    cancel_registry = CancelRegistry()
    side_effects = ReadOnlySideEffectChecker()
    tool_credentials = RunCredentialRegistry(Config.TOOL_CREDENTIAL_TTL_SECONDS)
    memory = memory_service or build_memory_service()
    driver_proposals = DriverProposalService(
        sandbox_runner=build_driver_proposal_runner(),
        settings=DriverProposalSettings(
            publish_enabled=Config.DRIVER_PUBLISH_ENABLED,
            max_result_chars=Config.DRIVER_PROPOSAL_MAX_RESULT_CHARS,
            max_diff_chars=Config.DRIVER_PROPOSAL_MAX_DIFF_CHARS))
    tool_rest = RestToolClient(
        Config.TOOL_GATEWAY_BASE_URL,
        timeout_seconds=Config.TOOL_HTTP_TIMEOUT_SECONDS)
    # 探索-生成层（INT-2492）：设备租约复用任务派发的物理设备互斥锁；
    # 设备侧 UI 通道（ui_tree / ui_action 的端口实现）尚未接入设备服务，
    # 端口传 None → 工具返回 EXPLORATION_UNAVAILABLE，不伪造树。
    exploration = ExplorationService(
        devices=None,
        leases=PhysicalDeviceLeaseAdapter(
            rest=tool_rest, credentials=tool_credentials,
            ttl_seconds=Config.EXPLORATION_LEASE_TTL_SECONDS),
        artifacts=artifacts,
        store=artifact_store or OssArtifactStore(),
        budget=ExplorationBudget(
            max_actions=Config.EXPLORATION_MAX_ACTIONS,
            max_seconds=Config.EXPLORATION_MAX_SECONDS),
    )
    gateway = tool_gateway or SharedToolGateway(
        bridge=SharedToolRegistryBridge(),
        rest=tool_rest,
        credentials=tool_credentials,
        memory=memory,
        driver_proposals=driver_proposals,
        exploration=exploration,
    )
    skills = skill_registry or build_skill_registry(
        gateway, skills_root, custom=skill_repository)
    # INT-2549：自定义 Skill 的 CRUD / 版本 / 导入导出 / 发布门槛
    skill_service = build_skill_service(
        gateway, skills, skill_repository, run_skill_repository,
        resource_store=skill_resource_store, golden_tasks=golden_tasks,
        guard=skill_guard, settings=skill_settings,
        reviews=skill_review_repository)
    # INT-2551：TENANT 级共享 Skill 的发布审核流（提交 / 审批 / 撤回）
    skill_review_service = SkillReviewService(
        skills=skill_service, reviews=skill_review_repository,
        repository=skill_repository)
    # INT-2466：写审批服务（提案 / 决策 / 过期 / 执行前复核）与 Loop 共用
    # 同一份工具网关与仓储；run 归属校验在服务内部完成。
    approval_service = ApprovalService(
        approvals=approvals, events=events, runs=runs,
        tool_gateway=gateway,
        settings=ApprovalSettings(
            ttl_seconds=Config.APPROVAL_TTL_SECONDS,
            expiry_scan_limit=Config.APPROVAL_EXPIRY_SCAN_LIMIT),
    )
    sandbox_executor = sandbox or build_sandbox_tool_executor(skills)

    compaction = compaction_settings or CompactionSettings(
        enabled=True,
        keep_recent_turns=Config.CONTEXT_KEEP_RECENT_TURNS,
        tool_summary_chars=Config.CONTEXT_TOOL_SUMMARY_CHARS,
        max_summary_chars=Config.CONTEXT_MAX_SUMMARY_CHARS,
        artifact_threshold_chars=Config.CONTEXT_ARTIFACT_THRESHOLD_CHARS,
        list_top_n=Config.CONTEXT_LIST_TOP_N,
        list_trim_threshold_chars=Config.CONTEXT_LIST_TRIM_THRESHOLD_CHARS,
        max_key_fields=Config.CONTEXT_MAX_KEY_FIELDS,
        memo_min_candidates=Config.CONTEXT_MEMO_MIN_CANDIDATES,
        artifact_store_timeout_seconds=(
            Config.CONTEXT_ARTIFACT_TIMEOUT_SECONDS),
        debug=(Config.CONTEXT_DEBUG if context_debug is None
               else bool(context_debug)),
    )

    assembler = ContextAssembler(
        events, runs, system_prompt=Config.SYSTEM_PROMPT,
        max_runs=(Config.CONTEXT_MAX_RUNS if context_max_runs is None
                  else int(context_max_runs)),
        max_messages=(Config.CONTEXT_MAX_MESSAGES
                      if context_max_messages is None
                      else int(context_max_messages)),
        event_fetch_limit=Config.EVENT_SCAN_LIMIT,
        skills=skills, snapshots=snapshots, artifacts=artifacts,
        artifact_store=artifact_store or OssArtifactStore(),
        settings=compaction, memory=memory)

    ratios = budget_ratios or SectionRatios.from_dict(
        Config.context_section_ratios())
    budget_policy = ContextBudgetPolicy(
        windows, ratios=ratios,
        soft_ratio=Config.COMPACTION_SOFT_RATIO,
        hard_ratio=Config.COMPACTION_HARD_RATIO,
        token_budget_multiplier=Config.TOKEN_BUDGET_MULTIPLIER_DEFAULT)

    settings = OrchestratorSettings(
        budget_defaults=dict(budgets),
        max_consecutive_tool_failures=Config.MAX_CONSECUTIVE_TOOL_FAILURES,
        tool_max_concurrency=Config.TOOL_MAX_CONCURRENCY,
        tool_result_max_chars=Config.TOOL_RESULT_MAX_CHARS,
        temperature=Config.LLM_TEMPERATURE,
        max_output_tokens=Config.OUTPUT_TOKEN_CAP,
        cancel_db_check_every=Config.CANCEL_DB_CHECK_EVERY,
        event_scan_limit=Config.EVENT_SCAN_LIMIT,
        token_budget_multiplier=Config.TOKEN_BUDGET_MULTIPLIER_DEFAULT,
        auto_token_budget_multiplier=Config.TOKEN_BUDGET_MULTIPLIER_AUTO,
        compaction_soft_ratio=Config.COMPACTION_SOFT_RATIO,
        compaction_hard_ratio=Config.COMPACTION_HARD_RATIO,
        budget_policy=budget_policy,
        memo_max_output_tokens=Config.CONTEXT_MEMO_MAX_OUTPUT_TOKENS,
    )
    orchestrator = RunOrchestrator(
        sessions=sessions, runs=runs, events=events, steps=steps,
        tool_calls=tool_calls, artifacts=artifacts, assembler=assembler,
        provider_resolver=registry,
        tool_gateway=gateway, side_effects=side_effects, wakeup=wakeup,
        cancel_registry=cancel_registry, settings=settings,
        approvals=approval_service,
        sandbox=sandbox_executor,
        # INT-2549：在办 run 的 L2 / allowed-tools 按激活快照固定
        skill_snapshots=skill_service.snapshot_skill,
    )
    run_service = RunService(
        sessions, runs, events, wakeup, cancel_registry,
        budget_defaults=dict(budgets),
        default_model='',
        skills=skills,
        approvals=approval_service,
        run_skills=run_skill_repository,
    )
    event_stream = EventStreamService(
        events, runs, wakeup, page_size=Config.EVENT_PAGE_SIZE,
        poll_interval_seconds=Config.EVENT_POLL_INTERVAL_SECONDS,
        heartbeat_seconds=Config.EVENT_HEARTBEAT_SECONDS,
        terminal_grace_seconds=(
            Config.EVENT_TERMINAL_GRACE_SECONDS
            if terminal_grace_seconds is None else terminal_grace_seconds),
    )
    recovery = RecoveryService(
        runs=runs, steps=steps, tool_calls=tool_calls, events=events,
        side_effects=side_effects, wakeup=wakeup,
    )
    if executor_factory is not None:
        executor = executor_factory(orchestrator)
    else:
        executor = ThreadPoolRunExecutor(orchestrator, Config.WORKER_CONCURRENCY)

    return AgentContainer(
        run_service=run_service, event_stream=event_stream,
        recovery=recovery, executor=executor, wakeup=wakeup,
        orchestrator=orchestrator, assembler=assembler,
        skill_registry=skills,
        provider_service=provider_service, provider_registry=registry,
        tool_gateway=gateway, credentials=tool_credentials,
        sandbox=sandbox_executor,
        budget_policy=budget_policy, compaction_settings=compaction,
        memory_service=memory,
        approval_service=approval_service,
        skill_service=skill_service,
        skill_review_service=skill_review_service,
        repositories={
            'sessions': sessions, 'runs': runs, 'events': events,
            'steps': steps, 'tool_calls': tool_calls,
            'approvals': approvals,
            'artifacts': artifacts, 'snapshots': snapshots,
            'providers': provider_repository,
            'skills': skill_repository,
            'run_skills': run_skill_repository,
            'skill_reviews': skill_review_repository,
        },
    )
