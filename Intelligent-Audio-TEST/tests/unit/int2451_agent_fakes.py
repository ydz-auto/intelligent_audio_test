# -*- coding: utf-8 -*-
"""INT-2451 测试替身与装配辅助（非测试文件，pytest 不收集）。

INT-2488 起 run 的模型参数来自用户默认供应商：``build_stack`` 默认注入
``FakeProviderResolver``（固定窗口 128k），需要验证「无可用 Key」或窗口
差异的用例显式传 ``provider_resolver``。
"""
import base64
import os
import threading
import time
from typing import List, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agent_service.domain.enums import (
    ContextWindowSource, LlmProtocol, SandboxTier, ToolRisk,
)
from agent_service.domain.exceptions import RunCancelled
from agent_service.domain.model.entities import ToolCallRequest, ToolResult
from agent_service.domain.ports.llm import (
    LlmClient, LlmFinished, LlmTextDelta, LlmToolCalls, LlmUsage,
)
from agent_service.domain.ports.llm_provider import (
    LlmProviderResolver, ResolvedProvider,
)
from agent_service.domain.ports.tool_gateway import (
    ToolDescriptor, ToolGateway,
)
from agent_service.infrastructure.llm.credential_store import CredentialStore
from agent_service.infrastructure.persistence.models import agent_models  # noqa: F401
from agent_service.infrastructure.wakeup import LocalRunWakeup
from agent_service.wiring import build_container
from shared.models.database import Base
from shared.utils.time_utils import utcnow

_AGENT_TABLES = [
    'agent_session', 'agent_run', 'agent_run_event', 'agent_step',
    'agent_tool_call', 'agent_artifact', 'agent_context_snapshot',
    'agent_llm_provider', 'agent_approval',
    # INT-2549：自定义 Skill 当前行 / 版本快照 / run 激活快照
    'agent_skill', 'agent_skill_version', 'agent_run_skill',
    # INT-2551：TENANT 级审核链
    'agent_skill_review',
]

TEST_MASTER_KEY = base64.b64encode(b'int2451-test-master-key-32byte!!').decode()


def make_engine(db_path: str):
    engine = create_engine(
        'sqlite:///' + str(db_path),
        connect_args={'check_same_thread': False, 'timeout': 30},
    )
    Base.metadata.create_all(
        engine, tables=[Base.metadata.tables[name] for name in _AGENT_TABLES])
    return engine, sessionmaker(bind=engine)


class Pause:
    """FakeLlm 脚本里的停顿标记（模拟流式耗时，给取消留窗口）。"""

    def __init__(self, seconds: float):
        self.seconds = seconds


class FakeLlm(LlmClient):
    """按脚本逐轮流式返回；记录每次收到的 LlmRequest。"""

    def __init__(self, script):
        self._script = list(script)
        self.requests: List = []
        self.model = 'fake-model'
        self.cancelled = False

    def stream(self, request, cancel_check=None):
        self.requests.append(request)
        chunks = self._script.pop(0) if self._script else [LlmTextDelta('done')]
        for chunk in chunks:
            if isinstance(chunk, Pause):
                deadline = time.monotonic() + chunk.seconds
                while time.monotonic() < deadline:
                    if cancel_check is not None and cancel_check():
                        self.cancelled = True
                        raise RunCancelled()
                    time.sleep(0.01)
                continue
            if cancel_check is not None and cancel_check():
                self.cancelled = True
                raise RunCancelled()
            if chunk is None:
                continue
            yield chunk


def text_turn(*parts: str):
    return [LlmTextDelta(part) for part in parts] + [LlmFinished()]


def tool_turn(calls, usage: Optional[LlmUsage] = None):
    chunks = []
    if usage is not None:
        chunks.append(usage)
    chunks.extend([LlmToolCalls(tuple(calls)), LlmFinished()])
    return chunks


class FakeToolGateway(ToolGateway):
    def __init__(self, tools=None, results=None, fail=False):
        self._tools = list(tools or [])
        self._results = results or {}
        self.fail = fail
        self.executed = []
        self._lock = threading.Lock()

    def all_tools(self):
        return tuple(self._tools)

    def describe(self, names):
        wanted = set(names)
        return tuple(t for t in self._tools if t.name in wanted)

    def risk_of(self, name):
        for tool in self._tools:
            if tool.name == name:
                return tool.risk
        return None

    def required_permissions(self, name, arguments=None):
        for tool in self._tools:
            if tool.name == name:
                return tuple(tool.permissions)
        return None

    def execute(self, call: ToolCallRequest, context) -> ToolResult:
        with self._lock:
            self.executed.append((call.tool_call_id, call.name, call.arguments))
        if self.fail:
            return ToolResult(tool_call_id=call.tool_call_id, tool=call.name,
                              ok=False, content='boom',
                              error_code='TOOL_FAILED')
        if call.name in self._results:
            content = self._results[call.name]
        else:
            content = f'ok:{call.name}'
        return ToolResult(tool_call_id=call.tool_call_id, tool=call.name,
                          ok=True, content=content)


def read_tool(name='task_query'):
    return ToolDescriptor(name=name, description='查询任务', parameters={},
                          risk=ToolRisk.READ, sandbox_tier=SandboxTier.T0_NONE)


def write_tool(name='task_run'):
    return ToolDescriptor(name=name, description='写操作', parameters={},
                          risk=ToolRisk.WRITE, sandbox_tier=SandboxTier.T0_NONE)


def default_provider(**overrides) -> ResolvedProvider:
    values = dict(
        provider_id='provider-fake', owner_id=7, tenant_id='t1',
        protocol=LlmProtocol.OPENAI_COMPATIBLE, base_url='http://fake-llm',
        model='fake-model', key_version=1,
        effective_context_window=131072,
        context_window_source=ContextWindowSource.MODEL_DEFAULT,
        catalog_context_window=131072, max_output_tokens=8192,
    )
    values.update(overrides)
    return ResolvedProvider(**values)


class FakeProviderResolver(LlmProviderResolver):
    """固定返回一个供应商；``error`` 非空时模拟「无可用 Key」。"""

    def __init__(self, llm, provider: Optional[ResolvedProvider] = None,
                 error: Optional[Exception] = None):
        self._llm = llm
        self._provider = provider or default_provider()
        self._error = error
        self.resolve_calls = 0
        self.build_calls = 0
        self.used_provider_ids: List[str] = []

    @property
    def provider(self) -> ResolvedProvider:
        return self._provider

    def resolve_for_run(self, run):
        self.resolve_calls += 1
        if self._error is not None:
            raise self._error
        return self._provider

    def build_client(self, provider):
        self.build_calls += 1
        self.used_provider_ids.append(provider.provider_id)
        return self._llm


def build_stack(db_path, llm, gateway=None, executor_factory=None,
                wakeup=None, budget_defaults=None,
                terminal_grace_seconds=None, provider_resolver=None,
                provider=None, **container_kwargs):
    engine, session_factory = make_engine(db_path)
    resolver = provider_resolver or FakeProviderResolver(
        llm, provider=provider)
    container = build_container(
        session_factory,
        provider_resolver=resolver,
        tool_gateway=gateway,
        wakeup=wakeup or LocalRunWakeup(),
        executor_factory=executor_factory,
        budget_defaults=budget_defaults,
        terminal_grace_seconds=terminal_grace_seconds,
        credential_store=CredentialStore.from_secret(TEST_MASTER_KEY),
        **container_kwargs,
    )
    return container, engine, session_factory


def server_budget(**overrides):
    """服务器侧预算注入（客户端不再能覆盖）：默认全放行，只改被测维度。"""
    from agent_service.config.config import Config
    budgets = dict(Config.budget_defaults())
    budgets.update(overrides)
    return budgets


def new_session(container, owner_id=7, tenant_id='t1'):
    return container.run_service.create_session(
        owner_id=owner_id, tenant_id=tenant_id, title='测试会话')


def events_of(container, run_id):
    return container.repositories['events'].list_after(run_id, 0, 10000)


def event_types(container, run_id):
    return [e.type.value for e in events_of(container, run_id)]


def wait_until(predicate, timeout=10.0, interval=0.02):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def iso_now():
    return utcnow()


def ensure_env():
    os.environ.setdefault('OSS_ACCESS_KEY', 'test')
    os.environ.setdefault('OSS_SECRET_KEY', 'test')
    os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
