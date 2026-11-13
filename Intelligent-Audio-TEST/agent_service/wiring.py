# -*- coding: utf-8 -*-
"""组合根（composition root）：装配 domain 端口 → infrastructure 适配器。

不放在 application 里，避免应用层反向依赖具体实现；接口层（app.py）调用。
测试可直接传入自定义 session_factory / llm_factory / tool_gateway / wakeup。
"""
import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

from agent_service.application.cancel_registry import CancelRegistry
from agent_service.application.context_assembler import ContextAssembler
from agent_service.application.event_stream import EventStreamService
from agent_service.application.recovery_service import RecoveryService
from agent_service.application.run_orchestrator import (
    OrchestratorSettings, RunOrchestrator,
)
from agent_service.application.run_service import RunService
from agent_service.application.run_worker import (
    RunExecutor, ThreadPoolRunExecutor,
)
from agent_service.application.skill_registry import SkillRegistry
from agent_service.application.tool_gateway import SharedToolGateway
from agent_service.config.config import Config
from agent_service.domain.ports.llm import LlmClient
from agent_service.domain.ports.run_wakeup import RunWakeup
from agent_service.domain.ports.side_effects import ReadOnlySideEffectChecker
from agent_service.domain.ports.tool_gateway import ToolGateway
from agent_service.infrastructure.llm.openai_compatible import (
    OpenAICompatibleLlmClient,
)
from agent_service.infrastructure.persistence.repositories import (
    SqlArtifactRepository, SqlContextSnapshotRepository, SqlEventRepository,
    SqlRunRepository, SqlSessionRepository, SqlStepRepository,
    SqlToolCallRepository,
)
from agent_service.infrastructure.skill.fs_skill_repository import (
    FsSkillRepository,
)
from agent_service.infrastructure.tools.registry_bridge import (
    RestToolClient, RunCredentialRegistry, SharedToolRegistryBridge,
)
from agent_service.infrastructure.wakeup import LocalRunWakeup, RedisRunWakeup

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
    tool_gateway: ToolGateway
    credentials: RunCredentialRegistry
    repositories: dict = field(default_factory=dict)

    def shutdown(self) -> None:
        try:
            self.executor.shutdown()
        finally:
            self.wakeup.close()


def _default_llm_factory() -> LlmClient:
    return OpenAICompatibleLlmClient(
        base_url=Config.LLM_BASE_URL,
        api_key=Config.LLM_API_KEY,
        model=Config.LLM_MODEL,
        timeout_seconds=Config.LLM_TIMEOUT_SECONDS,
        temperature=Config.LLM_TEMPERATURE,
        max_output_tokens=Config.LLM_MAX_OUTPUT_TOKENS,
        include_usage=Config.LLM_STREAM_INCLUDE_USAGE,
    )


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
                         strict: Optional[bool] = None) -> SkillRegistry:
    """装配 SkillRegistry 并装载 skills 目录（§4）。

    allowed-tools 的事实源是工具注册表：当前取自 ToolGateway.all_tools()；
    INT-2453 把注册表抽到 shared/agent_tools 后，这里换成同一份 Schema 即可，
    不为两套口径写兼容分支。
    """
    registry = SkillRegistry(
        FsSkillRepository(skills_root or Config.SKILLS_ROOT),
        known_tools=lambda: [d.name for d in tool_gateway.all_tools()],
        max_body_lines=Config.SKILL_BODY_MAX_LINES,
        strict=(Config.SKILL_VALIDATION_STRICT if strict is None else strict),
        l1_budget_tokens=Config.skill_l1_budget_tokens(),
    )
    return registry.load()


def build_container(session_factory,
                    llm_factory: Optional[Callable[[], LlmClient]] = None,
                    tool_gateway: Optional[ToolGateway] = None,
                    wakeup: Optional[RunWakeup] = None,
                    executor_factory: Optional[Callable] = None,
                    budget_defaults: Optional[dict] = None,
                    terminal_grace_seconds: Optional[float] = None,
                    skill_registry: Optional[SkillRegistry] = None,
                    skills_root: Optional[str] = None
                    ) -> AgentContainer:
    """组合根。``budget_defaults`` / ``terminal_grace_seconds`` /
    ``skill_registry`` / ``skills_root`` 仅供测试注入；生产一律取 Config。"""
    budgets = budget_defaults or Config.budget_defaults()
    sessions = SqlSessionRepository(session_factory)
    runs = SqlRunRepository(session_factory)
    events = SqlEventRepository(session_factory)
    steps = SqlStepRepository(session_factory)
    tool_calls = SqlToolCallRepository(session_factory)
    artifacts = SqlArtifactRepository(session_factory)
    snapshots = SqlContextSnapshotRepository(session_factory)

    wakeup = build_wakeup(wakeup)
    cancel_registry = CancelRegistry()
    side_effects = ReadOnlySideEffectChecker()
    credentials = RunCredentialRegistry(Config.TOOL_CREDENTIAL_TTL_SECONDS)
    gateway = tool_gateway or SharedToolGateway(
        bridge=SharedToolRegistryBridge(),
        rest=RestToolClient(
            Config.TOOL_GATEWAY_BASE_URL,
            timeout_seconds=Config.TOOL_HTTP_TIMEOUT_SECONDS),
        credentials=credentials,
    )
    skills = skill_registry or build_skill_registry(gateway, skills_root)

    assembler = ContextAssembler(
        events, runs, system_prompt=Config.SYSTEM_PROMPT,
        max_runs=Config.CONTEXT_MAX_RUNS,
        max_messages=Config.CONTEXT_MAX_MESSAGES,
        event_fetch_limit=Config.EVENT_SCAN_LIMIT,
        skills=skills)

    settings = OrchestratorSettings(
        budget_defaults=dict(budgets),
        max_consecutive_tool_failures=Config.MAX_CONSECUTIVE_TOOL_FAILURES,
        tool_max_concurrency=Config.TOOL_MAX_CONCURRENCY,
        tool_result_max_chars=Config.TOOL_RESULT_MAX_CHARS,
        temperature=Config.LLM_TEMPERATURE,
        max_output_tokens=Config.LLM_MAX_OUTPUT_TOKENS,
        cancel_db_check_every=Config.CANCEL_DB_CHECK_EVERY,
        event_scan_limit=Config.EVENT_SCAN_LIMIT,
    )
    orchestrator = RunOrchestrator(
        sessions=sessions, runs=runs, events=events, steps=steps,
        tool_calls=tool_calls, artifacts=artifacts, assembler=assembler,
        llm_factory=llm_factory or _default_llm_factory,
        tool_gateway=gateway, side_effects=side_effects, wakeup=wakeup,
        cancel_registry=cancel_registry, settings=settings,
    )
    run_service = RunService(
        sessions, runs, events, wakeup, cancel_registry,
        budget_defaults=dict(budgets),
        default_model=Config.LLM_MODEL,
        skills=skills,
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
        tool_gateway=gateway, credentials=credentials,
        repositories={
            'sessions': sessions, 'runs': runs, 'events': events,
            'steps': steps, 'tool_calls': tool_calls,
            'artifacts': artifacts, 'snapshots': snapshots,
        },
    )
