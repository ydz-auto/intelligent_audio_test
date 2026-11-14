# -*- coding: utf-8 -*-
"""INT-2571 §9.4.1：一次 tool call 影响 > 20 对象时拆成多条审批单。

覆盖验收 1~14（docker 真实栈验收 15 见交付评论）：

1. 拆单：21 个用例 → 21 张单（batch_total=21、batch_index 1..21、本单
   object_ref、proposal.arguments 收窄）；完整参数留在 agent_tool_call；
2. 边界：=20 不拆、21 拆；
3. 配置收紧：阈值 5 / 6 个对象拆；chunk_size=5 时 21 个对象 → 5 张；
4. 对象上限：101 个对象 → APPROVAL_OBJECT_LIMIT_EXCEEDED（0 张单、不执行、
   run 不挂死）；
5. all-or-nothing：20 张批准 + 1 张未决 → 不执行；最后一张批准 → 恰好执行
   一次，入参是完整 21 个对象；
6. 拒绝：任一张 REJECT → 整批拒绝 + 其余 PENDING 自动 REJECTED；
7. 过期：任一张 EXPIRED 且未全批准 → 整批 APPROVAL_EXPIRED；
8. DESTRUCTIVE：device_control batch 25 个设备 → 恒一张单 + confirm=true；
9. 原子：task_run merge 25 个任务 → 一张单；
10. 非枚举范围：reevaluate mode=all → 1 张、object_count=1；
11. 恢复幂等：重复 propose 不重复建单，已存在整批复用（不按新配置重建）；
12. 等待时长：同批 N 张单只计一次（区间并集）；
13. 接口字段：列表 / 决策响应都带 batch_* / object_ref。
"""
import os

import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from agent_service.application.approval_service import ApprovalSettings
from agent_service.domain.enums import (
    ApprovalDecision, ApprovalStatus, RunStatus, ToolCallStatus,
)
from agent_service.domain.exceptions import (
    ApprovalConfirmationRequired, ApprovalExpired,
)
from agent_service.domain.model.entities import ToolCallRequest
from agent_service.interfaces.api.schemas import ApprovalResponse
from tests.agent_write.helpers import (
    FakeLlm, FakeToolGateway, approvals_of, decide, destructive_tool,
    events_of_type, make_container, start_run, text_turn, tool_turn, write_tool,
)


def _ids(count, prefix='c'):
    return [f'{prefix}{index}' for index in range(1, count + 1)]


def _tag_args(ids, sub='add_tags'):
    return {'action': 'batch_tag', 'batch_action': sub,
            'ids': list(ids), 'tags': ['接线测试']}


def _split_scenario(tmp_path, *, ids=None, tool=None, args=None,
                    settings=None, followup='已完成'):
    ids = ids if ids is not None else _ids(21)
    tool = tool or write_tool('tag_group_manage',
                              permissions=('testcase:update',))
    args = args if args is not None else _tag_args(ids)
    call = ToolCallRequest(tool_call_id='c1', name=tool.name, arguments=args)
    llm = FakeLlm([tool_turn([call]), text_turn(followup)])
    gateway = FakeToolGateway(tools=[tool])
    container, _engine, _sf = make_container(
        tmp_path, llm, gateway, approval_settings=settings)
    run = start_run(container)
    return container, llm, gateway, run


def _batch(container, run_id):
    return sorted(approvals_of(container, run_id),
                  key=lambda item: item.batch_index)


def _expire_one(container, approval_id):
    """把一张单的过期时间改到过去（等价于 TTL 到点，避免 sleep）。"""
    from datetime import timedelta

    from agent_service.infrastructure.persistence.models.agent_models import (
        AgentApproval as AgentApprovalPO,
    )
    from shared.utils.time_utils import utcnow

    session = container.repositories['approvals']._session_factory()  # noqa: SLF001
    try:
        session.query(AgentApprovalPO).filter(
            AgentApprovalPO.id == approval_id).update(
                {'expires_at': utcnow() - timedelta(seconds=5)},
                synchronize_session=False)
        session.commit()
    finally:
        session.close()


# ---------------------------------------------------------------- 1 / 2 拆单

def test_21_objects_split_into_21_approvals(tmp_path):
    container, _llm, gateway, run = _split_scenario(tmp_path)
    batch = _batch(container, run.id)

    assert len(batch) == 21
    assert {item.batch_total for item in batch} == {21}
    assert [item.batch_index for item in batch] == list(range(1, 22))
    assert len({item.batch_id for item in batch}) == 1
    assert batch[0].batch_id
    for index, approval in enumerate(batch):
        assert approval.status is ApprovalStatus.PENDING
        assert approval.object_ref == {
            'kind': 'testcase', 'ids': [f'c{index + 1}']}
        assert approval.proposal['arguments']['ids'] == [f'c{index + 1}']
        assert approval.proposal['arguments']['tags'] == ['接线测试']
        assert approval.proposal['object_count'] == 21

    # 完整参数留在 agent_tool_call（审计 / 执行用完整入参）
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.arguments['ids'] == _ids(21)
    assert record.status is ToolCallStatus.WAITING_APPROVAL
    assert record.result['batch_total'] == 21
    assert record.result['object_count'] == 21
    assert gateway.executed == []

    # 每张单一条 SSE 事件，同批 tool_call_id 相同、载荷带批次字段
    events = events_of_type(container, run.id, 'approval_required')
    assert len(events) == 21
    assert {item.payload['tool_call_id'] for item in events} == {'c1'}
    assert {item.payload['batch_id'] for item in events} == {batch[0].batch_id}
    assert {item.payload['object_count'] for item in events} == {21}
    assert sorted(item.payload['batch_index'] for item in events) == \
        list(range(1, 22))


def test_20_objects_are_not_split(tmp_path):
    container, _llm, _gateway, run = _split_scenario(tmp_path, ids=_ids(20))
    batch = _batch(container, run.id)
    assert len(batch) == 1
    assert batch[0].batch_total == 1
    assert batch[0].batch_id is None
    assert batch[0].proposal['object_count'] == 20
    assert batch[0].object_ref == {'kind': 'testcase', 'ids': _ids(20)}


# ---------------------------------------------------------------- 3 配置收紧

def test_tightened_threshold_splits(tmp_path):
    settings = ApprovalSettings(split_threshold=5, split_chunk_size=1,
                                max_objects=100)
    container, _llm, _gateway, run = _split_scenario(
        tmp_path, ids=_ids(6), settings=settings)
    assert len(_batch(container, run.id)) == 6


def test_chunk_size_groups_objects_into_five_approvals(tmp_path):
    settings = ApprovalSettings(split_threshold=20, split_chunk_size=5,
                                max_objects=100)
    container, _llm, gateway, run = _split_scenario(
        tmp_path, ids=_ids(21), settings=settings)
    batch = _batch(container, run.id)

    assert len(batch) == 5
    assert {item.batch_total for item in batch} == {5}
    assert [len(item.object_ref['ids']) for item in batch] == [5, 5, 5, 5, 1]
    assert batch[0].proposal['arguments']['ids'] == _ids(5)
    assert batch[4].proposal['arguments']['ids'] == ['c21']
    # 全部批准后仍然只用完整参数执行一次
    for approval in batch:
        decide(container, approval.id, 'APPROVE',
               permissions=('testcase:update',))
    container.executor.submit(run.id)
    assert len(gateway.executed) == 1
    assert gateway.executed[0][2]['ids'] == _ids(21)


# ---------------------------------------------------------------- 4 对象上限

def test_object_limit_rejects_without_creating_approvals(tmp_path):
    container, llm, gateway, run = _split_scenario(
        tmp_path, ids=_ids(101), followup='对象太多，我改成多次调用')
    assert approvals_of(container, run.id) == []
    assert gateway.executed == []
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.status is ToolCallStatus.DENIED
    assert record.result_code == 'APPROVAL_OBJECT_LIMIT_EXCEEDED'
    assert '101' in record.error and '100' in record.error
    # 错误回灌模型：run 继续跑完，不挂死在 WAITING_APPROVAL
    assert len(llm.requests) == 2
    assert container.repositories['runs'].get(run.id).status is \
        RunStatus.SUCCEEDED


# ---------------------------------------------------------------- 5 all-or-nothing

def test_executes_once_after_every_approval(tmp_path):
    container, llm, gateway, run = _split_scenario(tmp_path)
    batch = _batch(container, run.id)

    for approval in batch[:-1]:
        decide(container, approval.id, 'APPROVE',
               permissions=('testcase:update',))
    # 20 张已批准、1 张 PENDING：不执行，run 停在 WAITING_APPROVAL
    container.executor.submit(run.id)
    assert gateway.executed == []
    assert container.repositories['runs'].get(run.id).status is \
        RunStatus.WAITING_APPROVAL
    assert len(llm.requests) == 1

    decide(container, batch[-1].id, 'APPROVE',
           permissions=('testcase:update',))
    container.executor.submit(run.id)

    # 恰好执行一次，入参是完整 21 个对象（不是 21 次单对象执行）
    assert len(gateway.executed) == 1
    assert gateway.executed[0][2]['ids'] == _ids(21)
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.status is ToolCallStatus.COMPLETED
    audit = record.result['approval']
    assert len(audit['approval_ids']) == 21
    assert audit['batch_total'] == 21
    assert container.repositories['runs'].get(run.id).status is \
        RunStatus.SUCCEEDED
    # 重复恢复 / 重复投递不重复执行
    container.orchestrator.execute(run.id)
    assert len(gateway.executed) == 1


# ---------------------------------------------------------------- 6 拒绝

def test_reject_any_rejects_the_whole_batch(tmp_path):
    container, llm, gateway, run = _split_scenario(
        tmp_path, followup='写操作未获批准')
    batch = _batch(container, run.id)
    for approval in batch[:10]:
        decide(container, approval.id, 'APPROVE',
               permissions=('testcase:update',))

    decide(container, batch[10].id, 'REJECT', permissions=('testcase:update',))
    # 整批拒绝：其余 PENDING 自动转 REJECTED
    statuses = {item.status for item in approvals_of(container, run.id)}
    assert ApprovalStatus.PENDING not in statuses
    assert sum(1 for item in approvals_of(container, run.id)
               if item.status is ApprovalStatus.REJECTED) == 11

    container.executor.submit(run.id)
    assert gateway.executed == []
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.status is ToolCallStatus.DENIED
    assert record.result_code == 'APPROVAL_REJECTED'
    # 回灌带被拒对象
    assert 'testcase' in record.error and 'c11' in record.error
    assert len(llm.requests) == 2
    assert container.repositories['runs'].get(run.id).status is \
        RunStatus.SUCCEEDED


# ---------------------------------------------------------------- 7 过期

def test_expire_any_expires_the_whole_batch(tmp_path):
    container, llm, gateway, run = _split_scenario(tmp_path)
    batch = _batch(container, run.id)
    for approval in batch[:20]:
        decide(container, approval.id, 'APPROVE',
               permissions=('testcase:update',))
    _expire_one(container, batch[20].id)

    container.executor.submit(run.id)
    statuses = {item.status for item in approvals_of(container, run.id)}
    # 整批按过期收口：不再留 PENDING；已批准的决策不回溯改写
    assert ApprovalStatus.PENDING not in statuses
    assert ApprovalStatus.EXPIRED in statuses
    assert gateway.executed == []
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.status is ToolCallStatus.DENIED
    assert record.result_code == 'APPROVAL_EXPIRED'
    assert len(llm.requests) == 2


def test_expire_pending_siblings_are_closed(tmp_path):
    """未决兄弟单一起转 EXPIRED（不留半批 PENDING）。"""
    container, _llm, gateway, run = _split_scenario(tmp_path)
    batch = _batch(container, run.id)
    _expire_one(container, batch[0].id)
    container.executor.submit(run.id)
    assert {item.status for item in approvals_of(container, run.id)} == {
        ApprovalStatus.EXPIRED}
    assert gateway.executed == []


def test_full_approval_before_expiry_still_executes(tmp_path):
    container, _llm, gateway, run = _split_scenario(tmp_path)
    batch = _batch(container, run.id)
    for approval in batch:
        decide(container, approval.id, 'APPROVE',
               permissions=('testcase:update',))
    container.executor.submit(run.id)
    assert len(gateway.executed) == 1


# ---------------------------------------------------------------- 8 DESTRUCTIVE

def test_destructive_device_batch_is_one_approval_with_confirm(tmp_path):
    device_ids = list(range(1, 26))
    container, _llm, gateway, run = _split_scenario(
        tmp_path, tool=destructive_tool('device_control'),
        args={'action': 'batch', 'operation': 'reboot',
              'device_ids': device_ids})
    batch = _batch(container, run.id)
    assert len(batch) == 1
    assert batch[0].batch_total == 1
    assert batch[0].proposal['object_count'] == 25
    assert batch[0].object_ref == {'kind': 'device', 'ids': device_ids}
    assert batch[0].proposal['risk'] == 'DESTRUCTIVE'

    with pytest.raises(ApprovalConfirmationRequired):
        decide(container, batch[0].id, 'APPROVE',
               permissions=('device:control',))
    assert gateway.executed == []
    decide(container, batch[0].id, 'APPROVE',
           permissions=('device:control',), confirm=True)
    container.executor.submit(run.id)
    assert len(gateway.executed) == 1
    assert gateway.executed[0][2]['device_ids'] == device_ids


# ---------------------------------------------------------------- 9 / 10 原子 / 范围

def test_atomic_merge_is_one_approval(tmp_path):
    task_ids = list(range(1, 26))
    container, _llm, _gateway, run = _split_scenario(
        tmp_path, tool=write_tool('task_run', permissions=('task:merge',)),
        args={'action': 'merge', 'body': {'task_ids': task_ids}})
    batch = _batch(container, run.id)
    assert len(batch) == 1
    assert batch[0].proposal['object_count'] == 25
    assert batch[0].object_ref == {'kind': 'task', 'ids': task_ids}
    assert batch[0].proposal['arguments']['body']['task_ids'] == task_ids


def test_range_mode_counts_one_object(tmp_path):
    container, _llm, _gateway, run = _split_scenario(
        tmp_path,
        tool=write_tool('evaluation_manage',
                        permissions=('evaluation:execute',)),
        args={'action': 'reevaluate',
              'body': {'task_id': 1, 'mode': 'all'}})
    batch = _batch(container, run.id)
    assert len(batch) == 1
    assert batch[0].proposal['object_count'] == 1
    assert batch[0].object_ref == {'kind': 'testcase', 'ids': []}
    # 范围语义在未收窄的参数里（审批人能看到 mode=all）
    assert batch[0].proposal['arguments']['body']['mode'] == 'all'


# ---------------------------------------------------------------- 算法域（INT-2593）

def _import_args(count):
    return {'action': 'import', 'body': {'algorithms': [
        {'type': f'algo_{index}', 'name': f'算法 {index}',
         'params': [{'param_code': f'p{index}'}]}
        for index in range(1, count + 1)]}}


def test_algorithm_import_splits_into_approvals(tmp_path):
    """25 份算法导入 → 25 张单；全批批准后只用完整参数执行一次（INT-2593）。"""
    args = _import_args(25)
    container, _llm, gateway, run = _split_scenario(
        tmp_path,
        tool=write_tool('algorithm_manage',
                        permissions=('algorithm:definition_manage',)),
        args=args)
    batch = _batch(container, run.id)

    assert len(batch) == 25
    assert [item.batch_index for item in batch] == list(range(1, 26))
    assert batch[0].object_ref == {
        'kind': 'algorithm_definition', 'ids': ['algo_1']}
    # 每张单只展示自己那份定义（名称 / 设备参数一并保留）
    assert batch[0].proposal['arguments']['body']['algorithms'] == \
        [args['body']['algorithms'][0]]
    assert batch[0].proposal['object_count'] == 25
    # 完整参数留在 agent_tool_call（执行入参）
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert len(record.arguments['body']['algorithms']) == 25

    for approval in batch:
        decide(container, approval.id, 'APPROVE')
    container.executor.submit(run.id)
    assert len(gateway.executed) == 1
    assert len(gateway.executed[0][2]['body']['algorithms']) == 25


# ---------------------------------------------------------------- 11 恢复幂等

def test_repropose_reuses_existing_batch_not_new_config(tmp_path):
    container, _llm, _gateway, run = _split_scenario(tmp_path)
    first = _batch(container, run.id)
    assert len(first) == 21

    # 用「收紧后的新配置」再提案同一 tool call：整批复用，不按新配置重建
    from agent_service.application.approval_service import ApprovalService

    tightened = ApprovalService(
        approvals=container.repositories['approvals'],
        events=container.repositories['events'],
        runs=container.repositories['runs'],
        tool_gateway=container.tool_gateway,
        settings=ApprovalSettings(split_threshold=1, split_chunk_size=1))
    stored_run = container.repositories['runs'].get(run.id)
    again, created = tightened.propose(
        stored_run, step_id=None,
        call=ToolCallRequest(tool_call_id='c1', name='tag_group_manage',
                             arguments=_tag_args(_ids(21))),
        risk=container.repositories['tool_calls'].find(
            run.id, 'c1').risk,
        turn=0, idempotency_key='k', args_hash='h')
    assert created is False
    assert [item.id for item in again] == [item.id for item in first]
    assert len(approvals_of(container, run.id)) == 21
    assert len(events_of_type(container, run.id, 'approval_required')) == 21


def test_recovery_settles_batch_after_restart(tmp_path):
    """崩溃恢复：批次已落库，重新进入 Loop 仍按整批结算（不重复建单）。"""
    container, _llm, gateway, run = _split_scenario(tmp_path)
    batch = _batch(container, run.id)
    for approval in batch:
        decide(container, approval.id, 'APPROVE',
               permissions=('testcase:update',))
    # 直接重入 Loop（模拟进程重启后的恢复投递）
    container.orchestrator.execute(run.id)
    assert len(gateway.executed) == 1
    assert len(approvals_of(container, run.id)) == 21


# ---------------------------------------------------------------- 12 等待时长

def test_batch_wait_seconds_counts_the_interval_once(tmp_path):
    from datetime import timedelta

    from agent_service.infrastructure.persistence.models.agent_models import (
        AgentApproval as AgentApprovalPO,
    )
    from shared.utils.time_utils import utcnow

    container, _llm, _gateway, run = _split_scenario(tmp_path)
    batch = _batch(container, run.id)
    start = utcnow() - timedelta(seconds=10)
    end = utcnow()
    session = container.repositories['approvals']._session_factory()  # noqa: SLF001
    try:
        session.query(AgentApprovalPO).filter(
            AgentApprovalPO.run_id == run.id,
            AgentApprovalPO.status == ApprovalStatus.PENDING.value,
        ).update({'created_at': start, 'decided_at': end,
                  'status': ApprovalStatus.APPROVED.value},
                 synchronize_session=False)
        session.commit()
    finally:
        session.close()

    waited = container.orchestrator._excluded_wait_seconds(run.id)  # noqa: SLF001
    # 21 张单覆盖同一段等待：只计一次（≈10s），不是 21 × 10s
    assert 9.0 <= waited <= 11.0, waited
    assert len(batch) == 21


def test_interval_union_handles_overlap_and_gaps():
    from agent_service.application.run_orchestrator import (
        _interval_union_seconds,
    )

    assert _interval_union_seconds([]) == 0.0
    assert _interval_union_seconds([(0.0, 10.0)]) == pytest.approx(10.0)
    # 同批三张单完全重叠 → 只算一次
    assert _interval_union_seconds(
        [(0.0, 10.0), (0.0, 10.0), (0.0, 10.0)]) == pytest.approx(10.0)
    # 部分重叠 → 并集
    assert _interval_union_seconds(
        [(0.0, 10.0), (5.0, 15.0)]) == pytest.approx(15.0)
    # 不重叠 → 求和（历史逐张口径不变）
    assert _interval_union_seconds(
        [(0.0, 10.0), (20.0, 25.0)]) == pytest.approx(15.0)


# ---------------------------------------------------------------- 13 接口字段

def test_list_and_decision_responses_expose_batch_fields(tmp_path):
    container, _llm, _gateway, run = _split_scenario(tmp_path)
    items = container.run_service.list_approvals(
        run.id, owner_id=7, tenant_id='t1')
    assert len(items) == 21
    for index, item in enumerate(items):
        assert item['batch_total'] == 21
        assert item['batch_index'] == index + 1
        assert item['batch_id']
        assert item['object_ref'] == {
            'kind': 'testcase', 'ids': [f'c{index + 1}']}
        # 响应模型逐字段校验（网关 / 前端 DTO 同源）
        ApprovalResponse(**item)

    decision, _run = container.run_service.decide_approval(
        items[0]['id'], owner_id=7, tenant_id='t1',
        decision=ApprovalDecision.APPROVE,
        permissions=('testcase:update',))
    assert decision['batch_index'] == 1
    assert decision['batch_total'] == 21
    assert decision['object_ref']['ids'] == ['c1']
    ApprovalResponse(**decision)


# ---------------------------------------------------------------- 配置口径

def test_config_defaults_and_threshold_cap():
    """默认口径：阈值 20（只允许收紧）、粒度 1、对象上限 100。"""
    import json
    import os as _os

    from agent_service.config.config import Config

    assert Config.APPROVAL_SPLIT_THRESHOLD_CAP == 20
    assert Config.APPROVAL_SPLIT_THRESHOLD == 20
    assert Config.APPROVAL_SPLIT_CHUNK_SIZE == 1
    assert Config.APPROVAL_MAX_OBJECTS == 100

    path = _os.path.join(
        _os.path.dirname(_os.path.dirname(_os.path.dirname(
            _os.path.abspath(__file__)))),
        'agent_service', 'config', 'agent_defaults.json')
    with open(path, encoding='utf-8') as handle:
        defaults = json.load(handle)
    assert defaults['approval']['split_threshold'] == 20
    assert defaults['approval']['split_chunk_size'] == 1
    assert defaults['approval']['max_objects'] == 100
