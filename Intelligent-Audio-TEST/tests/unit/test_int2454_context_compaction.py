# -*- coding: utf-8 -*-
"""INT-2454 上下文压缩 L1–L3 / 预算 / 快照。

验收锚点（卡面 §8.3 / §8.4 / §8.5）：
1. 预算按有效 W 派生：W=32k → 总预算 64k、软 / 硬阈值 19.2k / 25.6k；
2. L1：大工具结果 → 摘要 + 关键字段 + artifact 引用，原文落对象存储；
3. L2：相同查询去重，列表只留计数 + TopN + 查询入口；
4. L3：旧对话压成固定 schema（事实带来源 ID），失败回退 L1；
5. 永不压缩清单逐项仍在上下文中；
6. 每次压缩一条 agent_context_snapshot + context_compacted 事件（调试模式带明细）。
"""
import json
import os
import re
import uuid

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from agent_service.application.context_assembler import (
    CompactionSettings, L1_PREFIX, L2_PREFIX, MEMO_PREFIX,
)
from agent_service.application.run_worker import InlineRunExecutor
from agent_service.domain.enums import EventType, LlmMessageRole
from agent_service.domain.model.context_budget import ContextSection
from agent_service.domain.model.entities import AgentArtifact
from agent_service.domain.ports.artifact_store import ArtifactStore
from agent_service.domain.services.context_budget_policy import (
    ContextBudgetPolicy,
)
from agent_service.domain.services.context_window_resolver import (
    ContextWindowResolver,
)
from shared.utils.time_utils import utcnow
from tests.unit.int2451_agent_fakes import (
    FakeLlm, build_stack, new_session, text_turn,
)

OWNER = 7
TENANT = 't1'
WINDOW = 8192  # 小窗口，便于在少量轮次内触发压缩


class FakeArtifactStore(ArtifactStore):
    def __init__(self):
        self.items = {}

    def put(self, content, *, run_id, name,
            content_type='application/json'):
        uri = f'oss://archives/agent-context/{run_id}/{name}'
        self.items[uri] = content
        return uri


def _container(tmp_path, name='ctx.db', *, store=None, debug=False,
               settings=None, llm=None):
    return build_stack(
        tmp_path / name, llm or FakeLlm([]),
        executor_factory=lambda orch: InlineRunExecutor(orch),
        artifact_store=store or FakeArtifactStore(),
        compaction_settings=settings or CompactionSettings(
            keep_recent_turns=2, debug=debug),
        context_max_runs=60, context_max_messages=1000,
        context_debug=debug,
    )


def _budget(container, window=WINDOW, reserve=0):
    return container.budget_policy.build(window, reserve)


def _seed_run(container, session, message, *, tools=(), text='',
              approve=False):
    """创建一个 run 并手工写入工具 / 文本事件（不提交执行）。"""
    run, created = container.run_service.create_run(
        session.id, owner_id=OWNER, tenant_id=TENANT, message=message)
    assert created
    events = container.repositories['events']
    for item in tools:
        call_id = item['call_id']
        events.append(run.id, EventType.TOOL_CALL, {
            'tool_call_id': call_id, 'tool': item['tool'],
            'arguments': item.get('arguments') or {},
            'risk': item.get('risk', 'READ'), 'turn': 0,
        })
        events.append(run.id, EventType.TOOL_RESULT, {
            'tool_call_id': call_id, 'tool': item['tool'],
            'ok': not approve, 'content': item['content'],
            'error_code': 'APPROVAL_REQUIRED' if approve else None,
            'turn': 0,
        })
    if text:
        events.append(run.id, EventType.MESSAGE_DELTA, {
            'message_id': f'msg-{run.id}', 'delta': text,
            'index': 0, 'turn': 1 if tools else 0,
        })
    return run


def _big_result(task_id='T1', size=20000):
    payload = {
        'task_id': task_id,
        'status': 'SUCCEEDED',
        'progress': 62,
        'details': 'x' * size,
    }
    return json.dumps(payload, ensure_ascii=False)


# ---------------------------------------------------------------- 预算模型

def test_budget_is_derived_from_effective_window():
    resolver = ContextWindowResolver.from_dict(
        {'fallback_context_window': 32000, 'models': []})
    policy = ContextBudgetPolicy(resolver, soft_ratio=0.6, hard_ratio=0.8)
    budget = policy.build(32000, 0)
    assert budget.total_token_budget == 64000          # 2×W
    assert (budget.soft_threshold, budget.hard_threshold) == (19200, 25600)
    assert budget.section_limit(ContextSection.SYSTEM) == 4800
    assert budget.section_limit(ContextSection.SCRATCHPAD) == 3200
    assert budget.section_limit(ContextSection.DIALOGUE) == 11200
    assert budget.section_limit(ContextSection.TOOL_RESULTS) == 9600
    assert budget.section_limit(ContextSection.RESERVE) == 3200

    # 换模型 → 按新窗口重算，不沿用旧阈值
    bigger = policy.build(64000, 0)
    assert bigger.total_token_budget == 128000
    assert (bigger.soft_threshold, bigger.hard_threshold) == (38400, 51200)

    # 可用窗口 = W − 输出预留，阈值按可用窗口派生
    reserved = policy.build(32000, 3200)
    assert reserved.available == 28800
    assert reserved.soft_threshold == int(28800 * 0.6)


def test_invalid_budget_ratios_rejected():
    from agent_service.domain.model.context_budget import SectionRatios
    with pytest.raises(ValueError):
        SectionRatios(system=0.5, scratchpad=0.1, dialogue=0.35,
                      tool_results=0.3, reserve=0.1).validate()
    with pytest.raises(ValueError):
        ContextBudgetPolicy(
            ContextWindowResolver.from_dict({'models': []}),
            soft_ratio=0.9, hard_ratio=0.8)


# ---------------------------------------------------------------- L1

def test_l1_summarizes_large_tool_result_and_stores_artifact(tmp_path):
    store = FakeArtifactStore()
    container, _engine, _sf = _container(tmp_path, store=store)
    session = new_session(container)
    big_run = _seed_run(container, session, '查询任务 T1', tools=[{
        'call_id': 'call-big', 'tool': 'task_query',
        'arguments': {'action': 'detail', 'task_id': 'T1'},
        'content': _big_result('T1'),
    }])
    for index in range(3):
        _seed_run(container, session, f'跟进 {index}',
                  text=f'第 {index} 轮答复')
    latest, _ = container.run_service.create_run(
        session.id, owner_id=OWNER, tenant_id=TENANT, message='现在呢')

    messages = container.assembler.assemble(
        session.id, latest, budget=_budget(container))
    tools = [m for m in messages if m.role == LlmMessageRole.TOOL.value]
    assert tools, messages
    summarized = [m for m in tools if (m.content or '').startswith(L1_PREFIX)]
    assert len(summarized) == 1
    content = summarized[0].content
    assert 'task_id=T1' in content and 'status=SUCCEEDED' in content
    assert 'artifact: oss://archives/agent-context/' in content
    assert 'x' * 1000 not in content  # 原文不再进入模型上下文
    assert any('call-big' in uri for uri in store.items)

    snapshots = container.repositories['snapshots'].list_by_run(latest.id)
    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.level.value == 'L1_TRIM'
    assert snapshot.token_count > 0
    assert 'tool:call-big' in snapshot.dropped_ids
    artifacts = container.repositories['artifacts'].list_by_run(big_run.id)
    assert artifacts and artifacts[0].kind == 'context_tool_result'
    assert artifacts[0].uri in store.items

    # 再次组装（同一结果重建后重新摘要）不得重复上传 / 重复记账
    container.assembler.assemble(session.id, latest,
                                 budget=_budget(container))
    assert len(store.items) == 1
    assert len(container.repositories['artifacts'].list_by_run(big_run.id)) == 1
    container.shutdown()


# ---------------------------------------------------------------- L2

def test_l2_dedupes_queries_and_trims_lists(tmp_path):
    container, _engine, _sf = _container(tmp_path, name='l2.db')
    session = new_session(container)
    items = [{'task_id': f'T{i}', 'status': 'SUCCEEDED'} for i in range(50)]
    list_payload = json.dumps({'items': items, 'total': 50})
    for call_id in ('call-a', 'call-b'):
        _seed_run(container, session, '列任务', tools=[{
            'call_id': call_id, 'tool': 'task_query',
            'arguments': {'action': 'list'},
            'content': list_payload,
        }])
    # 老轮次的大段对话把总量推过软阈值，但工具结果仍在区段预算内
    _seed_run(container, session, '闲聊', text='y' * 16000)
    for index in range(2):
        _seed_run(container, session, f'最近 {index}', text='ok')
    latest, _ = container.run_service.create_run(
        session.id, owner_id=OWNER, tenant_id=TENANT, message='汇总')

    messages = container.assembler.assemble(
        session.id, latest, budget=_budget(container))
    tool_contents = [m.content or '' for m in messages
                     if m.role == LlmMessageRole.TOOL.value]
    assert any(c.startswith(L2_PREFIX) for c in tool_contents), tool_contents
    trimmed = [json.loads(c) for c in tool_contents
               if c.startswith('{') and 'list_compaction' in c]
    assert trimmed
    data = trimmed[0]
    assert data['list_compaction']['total_count'] == 50
    assert data['list_compaction']['returned_count'] == 5
    assert len(data['items']) == 5
    snapshots = container.repositories['snapshots'].list_by_run(latest.id)
    assert snapshots[0].level.value in ('L2_DEDUPE', 'L3_MEMO')
    container.shutdown()


def test_l2_same_query_changed_result_keeps_latest_fact(tmp_path):
    """同工具同参数但结果变化 → 不得声称「结果一致」，最新结果必须保留。

    回归：L2 只按「工具 + 参数」判重时，轮询同一个查询会把旧结果当权威，
    把后到的 SUCCEEDED 替换成「结果一致，此处省略」，模型拿到陈旧的
    RUNNING（§8.2 要求「相同查询**结果**去重」，§8.1 要求事实可核对）。
    """
    container, _engine, _sf = _container(
        tmp_path, name='l2changed.db',
        settings=CompactionSettings(keep_recent_turns=2))
    session = new_session(container)
    args = {'action': 'detail', 'task_id': 'T1'}
    _seed_run(container, session, '查询任务 T1', tools=[{
        'call_id': 'call-r5', 'tool': 'task_query', 'arguments': args,
        'content': json.dumps({'task_id': 'T1', 'status': 'RUNNING'}),
    }])
    _seed_run(container, session, '再查任务 T1', tools=[{
        'call_id': 'call-r20', 'tool': 'task_query', 'arguments': args,
        'content': json.dumps({'task_id': 'T1', 'status': 'SUCCEEDED'}),
    }])
    # 把两条查询推出「最近 N 轮」，并把总量推过软阈值
    _seed_run(container, session, '闲聊', text='y' * 21000)
    for index in range(2):
        _seed_run(container, session, f'最近 {index}', text='ok')
    latest, _ = container.run_service.create_run(
        session.id, owner_id=OWNER, tenant_id=TENANT, message='汇总')

    messages = container.assembler.assemble(
        session.id, latest, budget=_budget(container))
    tool_contents = [m.content or '' for m in messages
                     if m.role == LlmMessageRole.TOOL.value]
    blob = '\n'.join(tool_contents)
    assert 'SUCCEEDED' in blob, tool_contents       # 最新事实仍在上下文
    assert '结果一致' not in blob, tool_contents     # 不得声称结果一致
    snapshots = container.repositories['snapshots'].list_by_run(latest.id)
    assert snapshots and 'tool:call-r5' in snapshots[0].dropped_ids
    assert 'tool:call-r20' not in snapshots[0].dropped_ids
    container.shutdown()


def test_l2_changed_result_reaches_l3_memo(tmp_path):
    """结果变化时 L3 摘要必须能看到最新事实，而不是旧的 RUNNING。"""
    container, _engine, _sf = _container(
        tmp_path, name='l2changed-l3.db',
        settings=CompactionSettings(keep_recent_turns=2))
    session = new_session(container)
    args = {'action': 'detail', 'task_id': 'T1'}
    _seed_run(container, session, '查询任务 T1', tools=[{
        'call_id': 'call-r5', 'tool': 'task_query', 'arguments': args,
        'content': json.dumps({'task_id': 'T1', 'status': 'RUNNING'}),
    }])
    _seed_run(container, session, '再查任务 T1', tools=[{
        'call_id': 'call-r20', 'tool': 'task_query', 'arguments': args,
        'content': json.dumps({'task_id': 'T1', 'status': 'SUCCEEDED'}),
    }])
    _seed_run(container, session, '闲聊', text='z' * 30000)
    for index in range(2):
        _seed_run(container, session, f'最近 {index}', text='ok')
    latest, _ = container.run_service.create_run(
        session.id, owner_id=OWNER, tenant_id=TENANT, message='汇总')

    seen = []

    def summarizer(items):
        seen.append(list(items))
        blob = '\n'.join((item.get('content') or '') for item in items)
        assert 'SUCCEEDED' in blob, blob
        assert '结果一致' not in blob, blob
        return {
            'goal': '查询任务状态',
            'constraints': ['只读'],
            'facts': [{'fact': '任务 T1 状态为 SUCCEEDED',
                       'value': 'SUCCEEDED', 'source_id': 'tool:call-r20'}],
            'decisions': ['继续'],
            'artifacts': [],
            'open_questions': [],
            'next_steps': ['汇总'],
        }

    messages = container.assembler.assemble(
        session.id, latest, budget=_budget(container),
        memo_summarizer=summarizer)
    assert seen
    system = next(m.content for m in messages if m.role == 'system')
    assert MEMO_PREFIX in system and 'SUCCEEDED' in system
    snapshot = container.repositories['snapshots'].list_by_run(latest.id)[0]
    assert snapshot.level.value == 'L3_MEMO'
    assert snapshot.memo['facts'][0]['source_id'] == 'tool:call-r20'
    container.shutdown()


# ---------------------------------------------------------------- L3

def _memo_payload():
    return {
        'goal': '查询任务状态',
        'constraints': ['只读'],
        'facts': [{'fact': '任务 T1 状态为 SUCCEEDED',
                   'value': 'SUCCEEDED', 'source_id': 'tool:call-big'}],
        'decisions': ['继续'],
        'artifacts': [],
        'open_questions': [],
        'next_steps': ['汇总'],
    }


def _seed_long_history(container, session):
    run = _seed_run(container, session, '查询任务 T1', tools=[{
        'call_id': 'call-big', 'tool': 'task_query',
        'arguments': {'action': 'detail'},
        'content': _big_result('T1'),
    }])
    _seed_run(container, session, '闲聊', text='z' * 30000)
    for index in range(2):
        _seed_run(container, session, f'最近 {index}', text='ok')
    latest, _ = container.run_service.create_run(
        session.id, owner_id=OWNER, tenant_id=TENANT, message='最后')
    return run, latest


def test_l3_memo_fixed_schema_and_snapshot(tmp_path):
    container, _engine, _sf = _container(tmp_path, name='l3.db')
    session = new_session(container)
    _old, latest = _seed_long_history(container, session)

    calls = []

    def summarizer(messages):
        calls.append(list(messages))
        return _memo_payload()

    messages = container.assembler.assemble(
        session.id, latest, budget=_budget(container),
        memo_summarizer=summarizer)
    assert calls
    system = next(m.content for m in messages if m.role == 'system')
    assert MEMO_PREFIX in system
    assert 'tool:call-big' in system
    memo_json = system.split(MEMO_PREFIX, 1)[1]
    memo = json.loads(memo_json)
    assert memo['goal'] and memo['facts'][0]['source_id'] == 'tool:call-big'

    snapshots = container.repositories['snapshots'].list_by_run(latest.id)
    assert snapshots[0].level.value == 'L3_MEMO'
    assert snapshots[0].memo['facts'][0]['source_id'] == 'tool:call-big'
    assert snapshots[0].dropped_ids
    container.shutdown()


def test_l3_failure_falls_back_to_l1(tmp_path):
    container, _engine, _sf = _container(tmp_path, name='l3fb.db')
    session = new_session(container)
    _old, latest = _seed_long_history(container, session)

    def broken(_messages):
        raise RuntimeError('model unavailable')

    messages = container.assembler.assemble(
        session.id, latest, budget=_budget(container),
        memo_summarizer=broken)
    system = next(m.content for m in messages if m.role == 'system')
    assert MEMO_PREFIX not in system
    snapshots = container.repositories['snapshots'].list_by_run(latest.id)
    assert snapshots[0].level.value == 'L1_TRIM'
    container.shutdown()


def test_l3_invalid_memo_falls_back_to_l1(tmp_path):
    container, _engine, _sf = _container(tmp_path, name='l3bad.db')
    session = new_session(container)
    _old, latest = _seed_long_history(container, session)

    def invalid(_messages):
        return {'goal': 'x', 'facts': [{'fact': '无来源的事实'}]}

    container.assembler.assemble(
        session.id, latest, budget=_budget(container),
        memo_summarizer=invalid)
    snapshots = container.repositories['snapshots'].list_by_run(latest.id)
    assert snapshots[0].level.value == 'L1_TRIM'
    assert not snapshots[0].memo
    container.shutdown()


def test_l3_snapshot_is_replayed_without_recalling_model(tmp_path):
    """重建上下文时回放缓存的备忘：不重复调摘要模型，被裁消息不再出现。"""
    container, _engine, _sf = _container(tmp_path, name='replay.db')
    session = new_session(container)
    _old, latest = _seed_long_history(container, session)
    calls = []

    def summarizer(messages):
        calls.append(list(messages))
        return _memo_payload()

    first = container.assembler.assemble(
        session.id, latest, budget=_budget(container),
        memo_summarizer=summarizer)
    assert len(calls) == 1
    snapshot = container.repositories['snapshots'].list_by_run(latest.id)[-1]
    assert snapshot.level.value == 'L3_MEMO'
    assert 'tool:call-big' in snapshot.dropped_ids

    second = container.assembler.assemble(
        session.id, latest, budget=_budget(container),
        memo_summarizer=summarizer)
    # 复核轮次全部命中备忘 / 原始事件仍在库，无需再次压缩
    assert len(calls) == 1
    system = next(m.content for m in second if m.role == 'system')
    assert MEMO_PREFIX in system and 'tool:call-big' in system
    assert not any(m.tool_call_id == 'call-big' for m in second)
    assert not any('x' * 1000 in (m.content or '') for m in first + second)
    container.shutdown()


# ---------------------------------------------------------------- 永不压缩

def test_never_compress_items_survive_compaction(tmp_path):
    container, _engine, _sf = _container(
        tmp_path, name='never.db',
        settings=CompactionSettings(keep_recent_turns=4))
    session = new_session(container)
    invariant = '系统不变量：只依据工具真实数据回答 XYZ'
    container.assembler._system_prompt = invariant
    old_run = _seed_run(container, session, '用户明确约束：只读，不得编造 ABC',
                        tools=[{
                            'call_id': 'call-big', 'tool': 'task_query',
                            'arguments': {'action': 'detail'},
                            'content': _big_result('T1'),
                        }])
    _seed_run(container, session, '闲聊', text='z' * 30000)
    # 审批状态（§8.4-4）
    container.repositories['events'].append(old_run.id, EventType.TOOL_CALL, {
        'tool_call_id': 'call-approval', 'tool': 'task_run',
        'arguments': {}, 'risk': 'WRITE', 'turn': 2})
    container.repositories['events'].append(
        old_run.id, EventType.TOOL_RESULT, {
            'tool_call_id': 'call-approval', 'tool': 'task_run',
            'ok': False, 'content': '写操作需要审批',
            'error_code': 'APPROVAL_REQUIRED', 'turn': 2})
    # artifact 索引（§8.4-5）
    container.repositories['artifacts'].add(AgentArtifact(
        id='art-keep-1', run_id=old_run.id, kind='context_tool_result',
        uri='oss://archives/agent-context/keep.json', size=10,
        created_at=utcnow()))
    for index in range(2):
        _seed_run(container, session, f'最近 {index}', text='ok')
    latest, _ = container.run_service.create_run(
        session.id, owner_id=OWNER, tenant_id=TENANT, message='最后')

    messages = container.assembler.assemble(
        session.id, latest, budget=_budget(container),
        active_skill='platform-reference',
        memo_summarizer=lambda _m: _memo_payload())
    system = next(m.content for m in messages if m.role == 'system')
    assert invariant in system                       # 1 系统不变量
    assert '回答「平台长什么样」的唯一入口' in system  # 2 激活 Skill 正文（L2）
    assert any('用户明确约束：只读' in (m.content or '')
               for m in messages)                    # 3 用户约束
    assert any((m.content or '') == '写操作需要审批'
               or 'APPROVAL' in (m.content or '')
               for m in messages)                    # 4 审批状态
    assert 'art-keep-1' in system and 'keep.json' in system  # 5 artifact 索引
    recent = [m.content for m in messages if m.content in ('ok',)]
    assert len(recent) >= 2                          # 6 最近 N 轮原文
    container.shutdown()


# ---------------------------------------------------------------- 快照 / 事件

def test_debug_event_carries_dropped_ids_and_memo(tmp_path):
    container, _engine, _sf = _container(tmp_path, name='dbg.db', debug=True)
    session = new_session(container)
    _old, latest = _seed_long_history(container, session)

    container.assembler.assemble(
        session.id, latest, budget=_budget(container),
        memo_summarizer=lambda _m: _memo_payload())
    compacted = [e for e in container.repositories['events'].list_after(
        latest.id, 0, 1000)
        if e.type is EventType.CONTEXT_COMPACTED]
    assert len(compacted) == 1
    payload = compacted[0].payload
    assert payload['level'] == 'L3_MEMO'
    assert payload['snapshot_version'] == 1
    assert payload['dropped_message_ids']
    assert payload['memo']['facts'][0]['source_id'] == 'tool:call-big'
    assert payload['debug'] is True
    container.shutdown()


def test_no_compaction_below_soft_threshold(tmp_path):
    container, _engine, _sf = _container(tmp_path, name='quiet.db')
    session = new_session(container)
    _seed_run(container, session, '你好', text='短答复')
    latest, _ = container.run_service.create_run(
        session.id, owner_id=OWNER, tenant_id=TENANT, message='再来')

    container.assembler.assemble(session.id, latest,
                                 budget=_budget(container))
    assert container.repositories['snapshots'].list_by_run(latest.id) == []
    assert not any(e.type is EventType.CONTEXT_COMPACTED
                   for e in container.repositories['events'].list_after(
                       latest.id, 0, 1000))
    container.shutdown()


# ---------------------------------------------------------------- Loop 接线

def test_orchestrator_uses_budget_and_persists_snapshots(tmp_path):
    """真实 Loop：小窗口下多轮大结果 → 压缩并落快照，run 正常结束。"""
    from tests.unit.int2451_agent_fakes import (
        FakeToolGateway, default_provider, read_tool, tool_turn,
    )

    llm = FakeLlm([        tool_turn([_call('task_query')]),
        text_turn('第一轮完成'),
        tool_turn([_call('task_query')]),
        text_turn('第二轮完成'),
        text_turn('第三轮完成'),
    ])
    gateway = FakeToolGateway(
        tools=[read_tool('task_query')],
        results={'task_query': _big_result('T9')})
    container, _engine, _sf = build_stack(
        tmp_path / 'loop.db', llm, gateway=gateway,
        executor_factory=lambda orch: InlineRunExecutor(orch),
        provider=default_provider(effective_context_window=WINDOW,
                                  max_output_tokens=1024),
        context_max_runs=20, context_max_messages=1000,
        artifact_store=FakeArtifactStore())
    session = new_session(container)
    for index in range(3):
        run, created = container.run_service.create_run(
            session.id, owner_id=OWNER, tenant_id=TENANT,
            message=f'第 {index} 轮')
        assert created
        container.executor.submit(run.id)

    snapshots = []
    for run in container.repositories['runs'].list_session_runs(session.id, 20):
        snapshots.extend(container.repositories['snapshots'].list_by_run(run.id))
    assert snapshots, '多轮大结果应触发压缩'
    steps = container.repositories['steps']
    assert steps is not None
    container.shutdown()


def test_memo_output_limit_capped_by_output_reserve(tmp_path):
    """P3：备忘调用上限按 min(配置 2048, 单轮输出预留) 收敛。

    W=8192、输出预留 1024 时，小窗口下申请 2048 会超过 §8.3 的单轮输出上限
    （min(8k, 10%×W)）；实际请求必须是 1024。
    """
    from tests.unit.int2451_agent_fakes import default_provider

    memo_json = json.dumps(_memo_payload(), ensure_ascii=False)
    llm = FakeLlm([text_turn(memo_json), text_turn('完成')])
    container, _engine, _sf = build_stack(
        tmp_path / 'memo-limit.db', llm,
        executor_factory=lambda orch: InlineRunExecutor(orch),
        provider=default_provider(effective_context_window=WINDOW,
                                  max_output_tokens=1024),
        context_max_runs=20, context_max_messages=1000,
        artifact_store=FakeArtifactStore())
    session = new_session(container)
    # 预置超过模型窗口的历史 → 首次组装强制 L3 备忘
    for index in range(4):
        _seed_run(container, session, f'旧任务 {index}', text='w' * 20000)
    run, created = container.run_service.create_run(
        session.id, owner_id=OWNER, tenant_id=TENANT, message='开始')
    assert created
    container.executor.submit(run.id)

    memo_requests = [item for item in llm.requests
                     if (item.metadata or {}).get('purpose') == 'context_memo']
    assert memo_requests, '超过模型窗口应强制触发 L3 备忘'
    assert [item.max_output_tokens for item in memo_requests] == [1024]
    container.shutdown()


def _call(tool):
    from agent_service.domain.model.entities import ToolCallRequest
    return ToolCallRequest(tool_call_id=f'call-{uuid.uuid4().hex[:8]}',
                           name=tool, arguments={'action': 'detail'})


# ---------------------------------------------------------------- 主键口径

def test_artifact_and_snapshot_ids_fit_pk_width():
    """P0（INT-2537）：主键生成不得超出库表 VARCHAR(36)。

    生产 PG 对超长主键抛 ``value too long for type character varying(36)``，
    而两个落库点都按「不阻塞本轮」降级 —— SQLite 不校验 VARCHAR 长度，只有
    对生成函数本身断言才能拦住这类回归。
    """
    from agent_service.application.context_assembler import (
        _artifact_id, _snapshot_id,
    )
    from agent_service.infrastructure.persistence.models.agent_models import (
        AgentArtifact as AgentArtifactModel,
        AgentContextSnapshot as AgentContextSnapshotModel,
    )

    width = AgentArtifactModel.__table__.c.id.type.length
    assert width == AgentContextSnapshotModel.__table__.c.id.type.length == 36

    run_id = uuid.uuid4().hex
    message_id = str(uuid.uuid4())
    artifact_id = _artifact_id(run_id, message_id)
    snapshot_id = _snapshot_id(run_id, 1)

    assert len(artifact_id) <= width, artifact_id
    assert len(snapshot_id) <= width, snapshot_id
    # 字符集：前缀 + 十六进制摘要，不含空白 / 长度溢出
    assert re.fullmatch(r'art-[0-9a-f]+', artifact_id), artifact_id
    assert re.fullmatch(r'snap-[0-9a-f]+', snapshot_id), snapshot_id
    # 确定性：同一 (run, message) / (run, version) 恒等，重启后才不重复上传 / 记账
    assert artifact_id == _artifact_id(run_id, message_id)
    assert snapshot_id == _snapshot_id(run_id, 1)
    assert artifact_id != _artifact_id(run_id, str(uuid.uuid4()))
    assert snapshot_id != _snapshot_id(run_id, 2)
