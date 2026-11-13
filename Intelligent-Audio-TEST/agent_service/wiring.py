# -*- coding: utf-8 -*-
"""组合根（composition root）：装配 domain 端口 → infrastructure 适配器。

不放在 application 里，避免应用层反向依赖具体实现；接口层（app.py）调用。
测试可直接传入自定义 session_factory / provider_resolver / tool_gateway / wakeup。
"""
import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

from agent_service.application.cancel_registry import CancelRegistry
from agent_service.application.context_assembler import ContextAssembler
from agent_service.application.event_stream import EventStreamService
from agent_service.application.provider_service import ProviderService
from agent_service.application.recovery_service import RecoveryService
from agent_service.application.run_orchestrator import (
    OrchestratorSettings, RunOrchestrator,
)
from agent_service.application.run_service import RunService
from agent_service.application.run_worker import (
    RunExecutor, ThreadPoolRunExecutor,
)
from agent_service.config.config import Config
from agent_service.domain.ports.llm_provider import (
    LlmProviderResolver, ProviderVerifier,
)
from agent_service.domain.ports.run_wakeup import RunWakeup
from agent_service.domain.ports.side_effects import ReadOnlySideEffectChecker
from agent_service.domain.ports.tool_gateway import NoopToolGateway, ToolGateway
from agent_service.domain.services.context_window_resolver import (
    ContextWindowResolver,
)
from agent_service.infrastructure.llm.credential_store import CredentialStore
from agent_service.infrastructure.llm.provider_registry import ProviderRegistry
from agent_service.infrastructure.llm.verifier import HttpProviderVerifier
from agent_service.infrastructure.persistence.repositories import (
    SqlArtifactRepository, SqlContextSnapshotRepository, SqlEventRepository,
    SqlLlmProviderRepository, SqlRunRepository, SqlSessionRepository,
    SqlStepRepository, SqlToolCallRepository,
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
    provider_service: ProviderService = None
    provider_registry: LlmProviderResolver = None
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


def build_container(session_factory,
                    provider_resolver: Optional[LlmProviderResolver] = None,
                    tool_gateway: Optional[ToolGateway] = None,
                    wakeup: Optional[RunWakeup] = None,
                    executor_factory: Optional[Callable] = None,
                    budget_defaults: Optional[dict] = None,
                    terminal_grace_seconds: Optional[float] = None,
                    credential_store: Optional[CredentialStore] = None,
                    window_resolver: Optional[ContextWindowResolver] = None,
                    provider_verifier: Optional[ProviderVerifier] = None,
                    http_transport=None
                    ) -> AgentContainer:
    """组合根。``provider_resolver`` / ``credential_store`` / ``window_resolver``
    / ``provider_verifier`` / ``http_transport`` 仅供测试注入替身；生产一律
    取 Config + 环境。"""
    budgets = budget_defaults or Config.budget_defaults()
    sessions = SqlSessionRepository(session_factory)
    runs = SqlRunRepository(session_factory)
    events = SqlEventRepository(session_factory)
    steps = SqlStepRepository(session_factory)
    tool_calls = SqlToolCallRepository(session_factory)
    artifacts = SqlArtifactRepository(session_factory)
    snapshots = SqlContextSnapshotRepository(session_factory)
    provider_repository = SqlLlmProviderRepository(session_factory)

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
    gateway = tool_gateway or NoopToolGateway()

    assembler = ContextAssembler(
        events, runs, system_prompt=Config.SYSTEM_PROMPT,
        max_runs=Config.CONTEXT_MAX_RUNS,
        max_messages=Config.CONTEXT_MAX_MESSAGES,
        event_fetch_limit=Config.EVENT_SCAN_LIMIT)

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
    )
    orchestrator = RunOrchestrator(
        sessions=sessions, runs=runs, events=events, steps=steps,
        tool_calls=tool_calls, artifacts=artifacts, assembler=assembler,
        provider_resolver=registry,
        tool_gateway=gateway, side_effects=side_effects, wakeup=wakeup,
        cancel_registry=cancel_registry, settings=settings,
    )
    run_service = RunService(
        sessions, runs, events, wakeup, cancel_registry,
        budget_defaults=dict(budgets),
        default_model='',
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
        provider_service=provider_service, provider_registry=registry,
        repositories={
            'sessions': sessions, 'runs': runs, 'events': events,
            'steps': steps, 'tool_calls': tool_calls,
            'artifacts': artifacts, 'snapshots': snapshots,
            'providers': provider_repository,
        },
    )
