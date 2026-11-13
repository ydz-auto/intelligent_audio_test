# -*- coding: utf-8 -*-
"""INT-2466 写操作基座测试夹具（非测试文件，pytest 不收集）。

复用 INT-2451 的内存库 stack：``build_stack`` 已装配 ApprovalService，
这里只补齐「发起 run / 读取事件 / 审批决策」的快捷方法。
"""
import os
from typing import Iterable, Optional

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from agent_service.application.run_worker import InlineRunExecutor
from agent_service.domain.enums import ApprovalDecision, SandboxTier, ToolRisk
from agent_service.domain.ports.tool_gateway import ToolDescriptor
from tests.unit.int2451_agent_fakes import (
    FakeLlm, FakeToolGateway, build_stack, events_of, text_turn, tool_turn,
)

OWNER_ID = 7
TENANT_ID = 't1'


def inline_executor(orchestrator):
    return InlineRunExecutor(orchestrator)


def write_tool(name='task_create', permissions=('task:execute',)):
    """带权限域的写工具（权限快照回收测试需要非空权限码）。"""
    return ToolDescriptor(
        name=name, description='写操作', parameters={}, risk=ToolRisk.WRITE,
        sandbox_tier=SandboxTier.T0_NONE, permissions=permissions, enabled=True)


def destructive_tool(name='device_control'):
    return ToolDescriptor(
        name=name, description='破坏性写', parameters={},
        risk=ToolRisk.DESTRUCTIVE, sandbox_tier=SandboxTier.T0_NONE,
        permissions=('device:control',), enabled=True)


def make_container(tmp_path, llm, gateway=None, name='agent_write.db',
                   **kwargs):
    container, engine, session_factory = build_stack(
        tmp_path / name, llm, gateway=gateway,
        executor_factory=inline_executor, **kwargs)
    return container, engine, session_factory


def start_run(container, *, message='创建任务', permissions=('*',),
              owner_id=OWNER_ID, tenant_id=TENANT_ID, active_skill=None):
    session = container.run_service.create_session(
        owner_id=owner_id, tenant_id=tenant_id, title='写操作测试',
        permissions=list(permissions), active_skill=active_skill)
    run, created = container.run_service.create_run(
        session.id, owner_id=owner_id, tenant_id=tenant_id, message=message,
        permissions=list(permissions), active_skill=active_skill)
    assert created
    container.executor.submit(run.id)
    return run


def decide(container, approval_id: str, decision: str, *,
           owner_id=OWNER_ID, tenant_id=TENANT_ID,
           permissions: Iterable[str] = ('*',), confirm: bool = False):
    return container.run_service.decide_approval(
        approval_id, owner_id=owner_id, tenant_id=tenant_id,
        decision=ApprovalDecision(decision.upper()),
        permissions=tuple(permissions), confirm=confirm)


def approvals_of(container, run_id):
    return container.repositories['approvals'].list_by_run(run_id)


def events_of_type(container, run_id, event_type: str):
    return [event for event in events_of(container, run_id)
            if event.type.value == event_type]


def pending_approval(container, run_id):
    items = [item for item in approvals_of(container, run_id)
             if item.status.value == 'PENDING']
    assert len(items) == 1, f'期望 1 条待审批单，实际 {len(items)}'
    return items[0]


__all__ = [
    'FakeLlm', 'FakeToolGateway', 'OWNER_ID', 'TENANT_ID', 'approvals_of',
    'decide', 'destructive_tool', 'events_of_type', 'inline_executor',
    'make_container', 'pending_approval', 'start_run', 'text_turn',
    'tool_turn', 'write_tool',
]
