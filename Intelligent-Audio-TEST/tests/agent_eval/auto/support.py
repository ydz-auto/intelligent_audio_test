# -*- coding: utf-8 -*-
"""INT-2474 Auto 模式测试夹具（非测试文件，pytest 不收集）。

复用 INT-2451 / INT-2466 的内存库 stack：这里只补 Auto 相关的创建 /
事件读取 / 继续 便捷方法，以及按模式注入的预算。
"""
import os
from typing import Iterable

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from agent_service.application.run_worker import InlineRunExecutor
from agent_service.domain.enums import SandboxTier, ToolRisk
from agent_service.domain.ports.tool_gateway import ToolDescriptor
from tests.unit.int2451_agent_fakes import (
    FakeLlm, FakeToolGateway, build_stack, events_of, text_turn, tool_turn,
)

OWNER_ID = 7
TENANT_ID = 't1'


def inline_executor(orchestrator):
    return InlineRunExecutor(orchestrator)


def read_tool(name='task_query'):
    """只读工具（跨域长任务用不同名字模拟跨域调用）。"""
    return ToolDescriptor(name=name, description='只读查询', parameters={},
                          risk=ToolRisk.READ, sandbox_tier=SandboxTier.T0_NONE,
                          enabled=True)


def write_tool(name='task_create', permissions=('task:execute',)):
    return ToolDescriptor(
        name=name, description='写操作', parameters={}, risk=ToolRisk.WRITE,
        sandbox_tier=SandboxTier.T0_NONE, permissions=permissions,
        enabled=True)


def auto_budget(**overrides):
    """Auto 预算注入（默认取服务端 Auto 默认值，只改被测维度）。"""
    from agent_service.config.config import Config
    budgets = dict(Config.auto_budget_defaults())
    budgets.update(overrides)
    return budgets


def make_auto_stack(tmp_path, llm, gateway=None, name='auto.db', **kwargs):
    return build_stack(tmp_path / name, llm, gateway=gateway,
                       executor_factory=inline_executor, **kwargs)


def start_run(container, *, message='把任务、设备与报告三个域的数据汇总成一份报告',
              mode='auto', permissions=('*',), budget=None, submit=True):
    session = container.run_service.create_session(
        owner_id=OWNER_ID, tenant_id=TENANT_ID, title='Auto 测试',
        permissions=list(permissions))
    run, created = container.run_service.create_run(
        session.id, owner_id=OWNER_ID, tenant_id=TENANT_ID, message=message,
        permissions=list(permissions), mode=mode, budget_overrides=budget)
    assert created
    if submit:
        container.executor.submit(run.id)
    return run


def resume(container, run_id: str):
    """用户点「继续」：落 run_resumed 事件后重新投递（等价网关 /resume）。"""
    run = container.run_service.resume_run(
        run_id, owner_id=OWNER_ID, tenant_id=TENANT_ID)
    container.executor.submit(run_id)
    return run


def events_by_type(container, run_id: str, event_type: str):
    return [event for event in events_of(container, run_id)
            if event.type.value == event_type]


def steps_of(container, run_id: str):
    return container.repositories['steps'].list_by_run(run_id)


def status_of(container, run_id: str):
    return container.repositories['runs'].get(run_id).status


def finished_payload(container, run_id: str):
    events = events_by_type(container, run_id, 'run_finished')
    assert events, 'run 没有 run_finished 事件'
    return events[-1].payload


def approve(container, approval_id: str, permissions: Iterable[str] = ('*',)):
    from agent_service.domain.enums import ApprovalDecision
    return container.run_service.decide_approval(
        approval_id, owner_id=OWNER_ID, tenant_id=TENANT_ID,
        decision=ApprovalDecision.APPROVE, permissions=tuple(permissions))


def pending_approvals(container, run_id: str):
    return [item for item in container.repositories['approvals'].list_by_run(run_id)
            if item.status.value == 'PENDING']


__all__ = [
    'FakeLlm', 'FakeToolGateway', 'OWNER_ID', 'TENANT_ID', 'approve',
    'auto_budget', 'events_by_type', 'finished_payload', 'inline_executor',
    'make_auto_stack', 'pending_approvals', 'read_tool', 'resume', 'start_run',
    'status_of', 'steps_of', 'text_turn', 'tool_turn', 'write_tool',
]
