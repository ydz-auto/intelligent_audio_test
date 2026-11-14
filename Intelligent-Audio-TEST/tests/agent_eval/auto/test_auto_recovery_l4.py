# -*- coding: utf-8 -*-
"""INT-2474 验收 4：kill Worker 后恢复不重复写、上下文可重建（L4_REBUILD）。

场景：
1. Auto run 第 1 轮发起写操作 → 审批通过后执行一次（COMPLETED）；
2. 后续两轮工具连续失败 → 暂停（WAITING_APPROVAL）；
3. 进程「被杀」：丢掉容器 A，用同一个库新建容器 B 并走 RecoveryService；
4. 用户继续 → Loop 先做 L4_REBUILD（Run 表 + 产物索引），模型看到
   「已生效的写操作，禁止重复提交」，写操作只执行过一次。

断言：L4 快照（level=L4_REBUILD）+ 恢复请求带重建块 + 写只执行一次 +
重启不静默续跑暂停态。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from agent_service.domain.enums import (
    CompactionLevel, RunStatus, ToolCallStatus,
)
from agent_service.domain.model.entities import ToolCallRequest, ToolResult
from tests.agent_eval.auto.support import (
    FakeLlm, FakeToolGateway, approve, auto_budget, events_by_type,
    finished_payload, make_auto_stack, pending_approvals, read_tool, resume,
    start_run, status_of, steps_of, text_turn, tool_turn, write_tool,
)

MARKER = '[[AUTO_DONE]]'
DB_NAME = 'int2474_recovery.db'


class SelectiveGateway(FakeToolGateway):
    """写工具正常执行；``broken_query`` 固定失败（制造连续失败暂停）。"""

    def execute(self, call: ToolCallRequest, context) -> ToolResult:
        with self._lock:
            self.executed.append((call.tool_call_id, call.name, call.arguments))
        if call.name == 'broken_query':
            return ToolResult(tool_call_id=call.tool_call_id, tool=call.name,
                              ok=False, content='上游连接失败',
                              error_code='TOOL_FAILED')
        return ToolResult(tool_call_id=call.tool_call_id, tool=call.name,
                          ok=True, content=f'ok:{call.name}')


def _build(tmp_path, llm, gateway):
    return make_auto_stack(
        tmp_path, llm, gateway=gateway, name=DB_NAME,
        auto_budget_defaults=auto_budget())


def _script():
    write = ToolCallRequest(tool_call_id='w1', name='task_create',
                            arguments={'body': {'name': '汇总报告'}})
    bad1 = ToolCallRequest(tool_call_id='b1', name='broken_query',
                           arguments={'i': 1})
    bad2 = ToolCallRequest(tool_call_id='b2', name='broken_query',
                           arguments={'i': 2})
    return [tool_turn([write]), tool_turn([bad1]), tool_turn([bad2]),
            text_turn('已从中断处继续并完成 ', MARKER)]


def test_restart_rebuilds_context_and_never_repeats_write(tmp_path):
    llm = FakeLlm(_script())
    gateway = SelectiveGateway(tools=[write_tool('task_create'),
                                      read_tool('broken_query')])
    container_a, _engine_a, _sf_a = _build(tmp_path, llm, gateway)
    run = start_run(container_a)

    # 第 1 轮：写操作走审批，未执行
    assert status_of(container_a, run.id) is RunStatus.WAITING_APPROVAL
    approval = pending_approvals(container_a, run.id)[0]
    assert gateway.executed == []

    # 审批通过后执行写 → 后续两轮失败 → 连续失败暂停
    approve(container_a, approval.id)
    container_a.executor.submit(run.id)
    assert status_of(container_a, run.id) is RunStatus.WAITING_APPROVAL
    # 写执行一次，随后两轮只读失败 → 暂停
    assert [call[1] for call in gateway.executed] == [
        'task_create', 'broken_query', 'broken_query']
    write_record = container_a.repositories['tool_calls'].find(run.id, 'w1')
    assert write_record.status is ToolCallStatus.COMPLETED
    paused = events_by_type(container_a, run.id, 'run_paused')
    assert paused[-1].payload['reason'] == 'consecutive_tool_failures'

    # ---------------------------------------------------------- 进程被杀
    container_a.shutdown()
    writes_before_restart = [call for call in gateway.executed
                             if call[1] == 'task_create']
    requests_before = len(llm.requests)

    container_b, _engine_b, _sf_b = _build(tmp_path, llm, gateway)

    # 恢复投递不得静默续跑暂停态
    resumable = container_b.recovery.recover()
    assert run.id in resumable
    for run_id in resumable:
        container_b.executor.submit(run_id)
    assert status_of(container_b, run.id) is RunStatus.WAITING_APPROVAL
    assert len(llm.requests) == requests_before

    # 用户继续 → L4 重建 → 模型收口
    resume(container_b, run.id)
    assert status_of(container_b, run.id) is RunStatus.SUCCEEDED
    assert finished_payload(container_b, run.id)['reason'] == 'auto_complete'

    # 1) 落了一条 L4_REBUILD 快照，memo 里列出已生效的写操作
    snapshots = container_b.repositories['snapshots'].list_by_run(run.id)
    rebuilds = [item for item in snapshots
                if item.level is CompactionLevel.L4_REBUILD]
    assert rebuilds, '恢复后必须落 L4_REBUILD 快照'
    memo = rebuilds[-1].memo
    assert memo['goal'] == \
        '把任务、设备与报告三个域的数据汇总成一份报告'
    assert [item['tool_call_id'] for item in memo['executed_writes']] == ['w1']
    assert memo['steps_completed'] >= 3

    # 2) 恢复后第一次模型请求带重建块：写操作禁止重复提交
    resumed_request = llm.requests[-1]
    system_text = '\n'.join(message.content or ''
                            for message in resumed_request.messages
                            if message.role == 'system')
    assert '运行状态重建（L4_REBUILD）' in system_text
    assert '禁止重复提交' in system_text
    assert 'w1' in system_text and 'task_create' in system_text

    # 3) 写操作全程只执行一次（重启不重复写）
    writes_after_restart = [call for call in gateway.executed
                            if call[1] == 'task_create']
    assert len(writes_before_restart) == 1
    assert len(writes_after_restart) == 1

    # 4) 恢复上下文还有 context_compacted 事件（level=L4_REBUILD 可观测）
    compacted = [event for event in
                 events_by_type(container_b, run.id, 'context_compacted')
                 if event.payload.get('level') == 'L4_REBUILD']
    assert compacted and compacted[-1].payload['reason'] == 'resume'

    # 5) 重启后 step / scratchpad 仍可读（Run 表是事实源）
    steps = steps_of(container_b, run.id)
    assert steps[0].plan_snapshot['scratchpad']['mode'] == 'auto'
    container_b.shutdown()


def test_l4_rebuild_is_noop_before_first_step(tmp_path):
    """首轮（还没有任何 step）不做 L4 重建：避免循环引用空状态块。"""
    llm = FakeLlm([text_turn(f'完成 {MARKER}')])
    container, _engine, _sf = _build(tmp_path, llm, FakeToolGateway())
    run = start_run(container)
    assert status_of(container, run.id) is RunStatus.SUCCEEDED
    snapshots = container.repositories['snapshots'].list_by_run(run.id)
    assert [item for item in snapshots
            if item.level is CompactionLevel.L4_REBUILD] == []
    container.shutdown()
