# -*- coding: utf-8 -*-
"""VEGA-52：评估结束判据的「轮次完整性」前置 + 兜底同步契约收紧（D1–D3）回归测试。

被测缺陷（VEGA-50 对 VEGA-43 修复的审计结论）：
  D1 评估结束判据等价于「该用例**现有**维度行都不在评估中」，对多轮用例无法区分
     「本轮算完、下一轮还没派发」与「真的卡死」——每轮维度在该轮评估派发时才创建
     （evaluation_service._create_dimension_results），故轮次间隙会被误判为已结束，
     用例级被提前置终态、任务可能被提前收尾。
  D2 兜底同步会覆盖「已停止/已终态/执行失败」的用例，与函数自述契约不符
     （is_case_evaluation_finished 对任何非 in-progress 状态直接 return True；
      update_task_case_status_in_db 的 exclude_stopped 过滤 'stopped'，
      而停止路径实际写的是 status='skipped' ⇒ 保护永不生效）。
  D3 state 为 None 时 state['failed'] 抛 TypeError（表现为兜底同步静默失败）。

不跑真实 ASR / eval_server：直接驱动判据与兜底同步函数，构造「多轮 + 1 个 TestResult
（复现 3 台设备场景的『结果未全』守卫）」的现场。
"""
import uuid

import pytest
from types import SimpleNamespace

from backend.models.database import db
from backend.models.models import (
    Device,
    Dimension,
    Task,
    TaskCase,
    TaskDevice,
    TestCase,
    TestResult,
    TestResultDimension,
)
from backend.services.evaluation.evaluation_mixin import (
    is_case_evaluation_finished,
    sync_case_evaluation_status_from_dimensions,
    update_task_case_status_in_db,
)
from backend.services.execution.reevaluation_executor import ReevaluationExecutor

# 任务配 3 台设备（复现实测的「结果未全 1/3」守卫现场），用例只落 1 个 TestResult
TASK_DEVICE_COUNT = 3
DIM_COUNT = 2
ALGORITHM_TYPE = 'voice_llm'


# ────────────────────────────────────────────────────────
# 夹具
# ────────────────────────────────────────────────────────
@pytest.fixture
def wired_app(app, monkeypatch):
    """把各评估模块延迟导入的 app 全局指向当前测试应用。

    evaluation_service 等模块各自缓存一份 `app` 全局（get_app()），
    reevaluation_executor 也复用同一份，不重置会跨测试串用上一个 app 实例。
    """
    import backend.services.evaluation.evaluation_service as evaluation_service_module
    import backend.services.evaluation.evaluation_result_processor as processor_module
    import backend.services.evaluation.endpoint_worker as worker_module

    monkeypatch.setattr(evaluation_service_module, 'app', app, raising=False)
    monkeypatch.setattr(processor_module, 'app', app, raising=False)
    monkeypatch.setattr(worker_module, 'app', app, raising=False)
    return app


def _build_scenario(round_count, case_execution_status, case_evaluation_status,
                    case_status='pending'):
    """构造「多轮 + 3 台设备 + 1 个 TestResult」现场。

    Args:
        round_count: 用例配置的轮次数（用于复现「已配置 N 轮、只建出部分轮次维度」）
        case_execution_status: TaskCase.execution_status（多轮执行中为 running）
        case_evaluation_status: TaskCase.evaluation_status
        case_status: TaskCase.status
    """
    suffix = uuid.uuid4().hex[:8]

    task = Task(name=f'VEGA-52 多轮场景_{suffix}', type='e2e', status='running', total_cases=1)
    db.session.add(task)
    db.session.flush()

    devices = []
    for _ in range(TASK_DEVICE_COUNT):
        device = Device(
            name=f'VEGA52设备_{suffix}_{uuid.uuid4().hex[:6]}', model='M1', type='phone',
            system='Android', system_version='14', app_name='App', app_version='1.0',
            status='online',
        )
        db.session.add(device)
        db.session.flush()
        devices.append(device)
        db.session.add(TaskDevice(task_id=task.id, device_id=device.id))

    dims = []
    for idx in range(DIM_COUNT):
        dim = Dimension(
            name=f'VEGA52维度_{suffix}_{idx}', type='auto', result_type=0, weight=1,
            status=True, deleted=False, statistic_method='average',
        )
        db.session.add(dim)
        db.session.flush()
        dims.append(dim)

    case_id = f'vega52_case_{suffix}'
    round_cfg = {'evaluation': {'dimensions': [{'id': d.id} for d in dims]}}
    test_case = TestCase(
        id=case_id,
        name=f'VEGA-52 多轮用例_{suffix}',
        algorithm_type=ALGORITHM_TYPE,
        test_type='e2e',
        config={'rounds': [dict(round_cfg) for _ in range(round_count)], 'dimensions': []},
    )
    db.session.add(test_case)
    db.session.flush()  # 无 relationship 声明，需显式 flush 保证先落 test_cases

    task_case = TaskCase(
        task_id=task.id,
        test_case_id=case_id,
        status=case_status,
        execution_status=case_execution_status,
        evaluation_status=case_evaluation_status,
    )
    db.session.add(task_case)

    result = TestResult(
        task_id=task.id,
        test_case_id=case_id,
        device_id=devices[0].id,
        algorithm_type=ALGORITHM_TYPE,
        execution_status='completed',
        algorithm_result={'rounds': [{'reference_params': []}]},
        result_data={'multi_round': True, 'total_rounds': round_count},
    )
    db.session.add(result)
    db.session.flush()

    db.session.flush()
    return SimpleNamespace(
        task=task, case_id=case_id, dims=dims, result=result, task_case=task_case,
        round_count=round_count,
    )


def _add_round_dimensions(scenario, round_number, evaluation_status):
    """为指定轮次建出维度行（模拟该轮评估派发时 _create_dimension_results 落库）。"""
    trds = []
    for dim in scenario.dims:
        trd = TestResultDimension(
            test_result_id=scenario.result.id,
            dimension_id=dim.id,
            algorithm_type=ALGORITHM_TYPE,
            evaluation_status=evaluation_status,
            round_number=round_number,
        )
        db.session.add(trd)
        db.session.flush()
        trds.append(trd)
    db.session.commit()
    return trds


def _dim_state(task_id, case_id):
    from backend.services.evaluation.evaluation_mixin import (
        get_task_dimension_evaluation_states,
    )
    db.session.expire_all()
    return get_task_dimension_evaluation_states(db.session, task_id, case_id).get(case_id)


def _reload_task_case(task_id, case_id):
    db.session.expire_all()
    return db.session.query(TaskCase).filter_by(
        task_id=task_id, test_case_id=case_id
    ).first()


def _reload_task(task_id):
    db.session.expire_all()
    return db.session.query(Task).filter_by(id=task_id).first()


def _arm_reevaluation(monkeypatch, task_id):
    """让 ReevaluationExecutor 认为自己正是该任务的当前重评处理者。"""
    executor = ReevaluationExecutor.get_instance()
    monkeypatch.setattr(executor, 'is_reevaluating', True)
    monkeypatch.setattr(executor, 'running_task_id', task_id)
    return executor


# ────────────────────────────────────────────────────────
# D1：多轮用例在轮次间隙不得被判定为评估结束
# ────────────────────────────────────────────────────────
@pytest.fixture
def between_rounds(wired_app):
    """D1 现场：配 2 轮，第 0 轮维度全部到终态、第 1 轮维度尚未建出，
    用例仍在执行（execution_status='running'）、用例级 calculating。"""
    scenario = _build_scenario(
        round_count=2,
        case_execution_status='running',
        case_evaluation_status='calculating',
    )
    _add_round_dimensions(scenario, round_number=0, evaluation_status='completed')
    return scenario


def test_is_case_evaluation_finished_false_between_rounds(between_rounds):
    """轮次间隙：仅按维度级判定会误判为已结束，补「轮次完整性」前置后为 False。"""
    scenario = between_rounds
    state = _dim_state(scenario.task.id, scenario.case_id)
    assert state == {'total': DIM_COUNT, 'in_progress': 0, 'failed': 0}, (
        '前置：现有维度（第 0 轮）确实全部到终态'
    )

    # 修复前口径（不传 execution_status）：等价于「现有维度都不在评估中」⇒ 误判为已结束
    assert is_case_evaluation_finished('calculating', state) is True, (
        '红锚点：不带执行状态时判据会把「第 1 轮还没派发」误判成评估已结束'
    )

    # 修复后口径：执行未收尾 ⇒ 轮次不完整 ⇒ 不认定评估结束
    assert is_case_evaluation_finished('calculating', state, 'running') is False

    # 对照组（审计探针同款）：第 1 轮维度已建出且仍在评估中 ⇒ 同样为 False
    _add_round_dimensions(scenario, round_number=1, evaluation_status='pending')
    state_with_round1 = _dim_state(scenario.task.id, scenario.case_id)
    assert state_with_round1 == {'total': DIM_COUNT * 2, 'in_progress': DIM_COUNT, 'failed': 0}
    assert is_case_evaluation_finished('calculating', state_with_round1, 'running') is False


def test_sync_not_advanced_between_rounds(between_rounds):
    """轮次间隙：用例级不得被兜底同步推进。"""
    scenario = between_rounds

    advanced, new_status = sync_case_evaluation_status_from_dimensions(
        db.session, scenario.task.id, scenario.case_id
    )

    assert (advanced, new_status) == (False, None)
    task_case = _reload_task_case(scenario.task.id, scenario.case_id)
    assert task_case.evaluation_status == 'calculating', '用例级不该在轮次间隙被推进'
    assert task_case.status == 'pending', '用例状态也不该被改写'
    assert task_case.completed_at is None, '不得写入完成时间'


def test_maybe_finalize_not_finalized_between_rounds(between_rounds, monkeypatch):
    """轮次间隙：任务不得被收尾（用例仍在执行，重评收尾判据不成立）。"""
    scenario = between_rounds
    executor = _arm_reevaluation(monkeypatch, scenario.task.id)

    assert executor.maybe_finalize(scenario.task.id) is False

    task = _reload_task(scenario.task.id)
    assert task.status == 'running', '仍在跑轮次的任务不能被提前收尾'
    task_case = _reload_task_case(scenario.task.id, scenario.case_id)
    assert task_case.evaluation_status == 'calculating'


def test_sync_still_advances_after_execution_settled(wired_app):
    """VEGA-43 主链路不回归：执行已收尾 + 所有轮次维度都到终态 ⇒ 仍能推进。

    现场即 VEGA-43 要救的卡死形态：3 台设备 / 1 个 TestResult / 多轮，
    用例级被「结果未全」守卫永久留在 calculating。
    """
    scenario = _build_scenario(
        round_count=2,
        case_execution_status='completed',
        case_evaluation_status='calculating',
    )
    _add_round_dimensions(scenario, round_number=0, evaluation_status='completed')
    _add_round_dimensions(scenario, round_number=1, evaluation_status='failed')

    advanced, new_status = sync_case_evaluation_status_from_dimensions(
        db.session, scenario.task.id, scenario.case_id
    )

    assert (advanced, new_status) == (True, 'failed'), (
        '执行已收尾、所有轮次维度都到终态 ⇒ 兜底同步必须照常生效（维度有 failed ⇒ 用例级 failed）'
    )
    task_case = _reload_task_case(scenario.task.id, scenario.case_id)
    assert task_case.evaluation_status == 'failed'
    assert task_case.status == 'failed'
    assert task_case.completed_at is not None


def test_maybe_finalize_still_finalizes_after_execution_settled(wired_app, monkeypatch):
    """VEGA-43 主链路不回归（任务收尾侧）：执行已收尾的卡死用例仍能让任务离开 running。"""
    scenario = _build_scenario(
        round_count=2,
        case_execution_status='completed',
        case_evaluation_status='calculating',
    )
    _add_round_dimensions(scenario, round_number=0, evaluation_status='completed')
    _add_round_dimensions(scenario, round_number=1, evaluation_status='failed')
    executor = _arm_reevaluation(monkeypatch, scenario.task.id)

    assert executor.maybe_finalize(scenario.task.id) is True

    task = _reload_task(scenario.task.id)
    assert task.status == 'completed'
    assert executor.running_task_id is None


# ────────────────────────────────────────────────────────
# VEGA-43 主链路端到端自证（3 台设备 / 1 个 TestResult / 多轮）
# ────────────────────────────────────────────────────────
TIMEOUT_MESSAGE = '评估任务超时: eval_task_id=task_fake0001, 等待时间超过600秒'


class _StubApiClient:
    """打桩评估端点：提交后直接返回超时错误（等价 eval_server 600s 无响应）。"""

    def __init__(self, response):
        self.response = response
        self.requests = []

    def build_payload(self, body_template, context, **kwargs):
        return {'task_type': 'wer'}

    def make_api_request_with_fallback(self, **kwargs):
        self.requests.append(kwargs)
        return 'http://127.0.0.1:5001', self.response


def _group_items(dims, trds):
    return [
        (
            {
                'id': dim.id,
                'name': dim.name,
                'dimension_type': 'main',
                'task_type_code': 'wer',
                'api_endpoints': [{'url': 'http://127.0.0.1:5001'}],
                'api_settings': {'method': 'POST'},
                'input_params': [],
            },
            trd.id,
        )
        for dim, trd in zip(dims, trds)
    ]


def test_multi_round_eval_timeout_advances_case_and_finalizes_task(wired_app, monkeypatch):
    """多轮 + 3 台设备 + 1 个 TestResult：评估超时后用例级到终态、任务离开 running。

    第 1 轮评估已先超时到终态、第 0 轮评估此刻超时 ⇒ 该用例所有轮次维度都到终态，
    用例级虽被「结果未全 1/3」守卫留在 calculating，兜底同步必须把它推进到 failed。
    """
    from backend.services.evaluation.endpoint_worker import EndpointWorker
    from backend.services.evaluation.evaluation_result_processor import EvaluationResultProcessor

    scenario = _build_scenario(
        round_count=2,
        case_execution_status='completed',
        case_evaluation_status='calculating',
    )
    round0 = _add_round_dimensions(scenario, round_number=0, evaluation_status='pending')
    round1 = _add_round_dimensions(scenario, round_number=1, evaluation_status='pending')
    # 先派发的第 1 轮评估已超时到终态
    db.session.query(TestResultDimension).filter(
        TestResultDimension.id.in_([t.id for t in round1])
    ).update({'evaluation_status': 'failed'}, synchronize_session=False)
    db.session.commit()

    executor = _arm_reevaluation(monkeypatch, scenario.task.id)
    api_client = _StubApiClient({'__error__': TIMEOUT_MESSAGE})
    stub_service = SimpleNamespace(
        api_client=api_client,
        result_processor=EvaluationResultProcessor(),
    )
    worker = EndpointWorker('http://127.0.0.1:5001', stub_service, max_timeout=1, max_concurrent=1)

    group_items = _group_items(scenario.dims, round0)
    worker._execute_evaluation(
        task_id=scenario.task.id,
        result_id=scenario.result.id,
        test_case_id=scenario.case_id,
        algorithm_result={'rounds': [{'output': {}}]},
        representative_dim_data=group_items[0][0],
        group_items=group_items,
        algorithm_type=ALGORITHM_TYPE,
        test_type='e2e',
    )

    assert api_client.requests, '应真实发起过评估请求'

    task_case = _reload_task_case(scenario.task.id, scenario.case_id)
    assert task_case.evaluation_status == 'failed', (
        '多轮用例所有轮次维度都到终态后，用例级必须与维度级一致'
    )
    assert task_case.status == 'failed'

    task = _reload_task(scenario.task.id)
    assert task.status == 'completed', '任务必须离开 running，不再永久卡死'
    assert executor.running_task_id is None


# ────────────────────────────────────────────────────────
# D2：兜底同步不得覆盖「已停止 / 已终态 / 执行失败」的用例
# ────────────────────────────────────────────────────────
def test_sync_skips_manual_stopped_case(wired_app):
    """已停止用例（status='skipped' + evaluation_status='stopped'）经兜底同步后状态不变。"""
    scenario = _build_scenario(
        round_count=1,
        case_execution_status='stopped',
        case_evaluation_status='stopped',
        case_status='skipped',
    )
    _add_round_dimensions(scenario, round_number=0, evaluation_status='completed')

    advanced, new_status = sync_case_evaluation_status_from_dimensions(
        db.session, scenario.task.id, scenario.case_id
    )

    assert (advanced, new_status) == (False, None)
    task_case = _reload_task_case(scenario.task.id, scenario.case_id)
    assert (task_case.status, task_case.evaluation_status) == ('skipped', 'stopped'), (
        '人工停止的用例不得被兜底同步改写为 completed/completed'
    )
    assert task_case.completed_at is None


def test_sync_skips_case_already_in_terminal_evaluation_status(wired_app):
    """用例级已到终态（completed）时兜底同步不推进、不改写。

    即便维度里存在 failed，也不得把已完成的用例改判 failed（只推进不回退）。
    """
    scenario = _build_scenario(
        round_count=1,
        case_execution_status='completed',
        case_evaluation_status='completed',
        case_status='completed',
    )
    _add_round_dimensions(scenario, round_number=0, evaluation_status='failed')

    advanced, new_status = sync_case_evaluation_status_from_dimensions(
        db.session, scenario.task.id, scenario.case_id
    )

    assert (advanced, new_status) == (False, None)
    task_case = _reload_task_case(scenario.task.id, scenario.case_id)
    assert (task_case.status, task_case.evaluation_status) == ('completed', 'completed')


def test_sync_does_not_rollback_execution_failed_case(wired_app):
    """执行失败用例（execution_status/evaluation_status 均 failed）不得被改判 completed。

    D2 现象三：维度恰好全 completed 时，旧判据会把它从 failed 改回 completed。
    """
    scenario = _build_scenario(
        round_count=1,
        case_execution_status='failed',
        case_evaluation_status='failed',
        case_status='failed',
    )
    _add_round_dimensions(scenario, round_number=0, evaluation_status='completed')

    advanced, new_status = sync_case_evaluation_status_from_dimensions(
        db.session, scenario.task.id, scenario.case_id
    )

    assert (advanced, new_status) == (False, None)
    task_case = _reload_task_case(scenario.task.id, scenario.case_id)
    assert (task_case.status, task_case.evaluation_status) == ('failed', 'failed'), (
        '执行失败的用例不得被兜底同步改判为 completed'
    )


def test_update_task_case_status_excludes_skipped_case(wired_app):
    """exclude_stopped 必须同时排除 'skipped'（停止路径实际写入的取值）。"""
    scenario = _build_scenario(
        round_count=1,
        case_execution_status='stopped',
        case_evaluation_status='stopped',
        case_status='skipped',
    )

    update_count = update_task_case_status_in_db(
        db.session, scenario.task.id, scenario.case_id, 'completed', 'completed'
    )

    assert update_count == 0, "停止路径写的是 status='skipped'，保护必须对它生效"
    task_case = _reload_task_case(scenario.task.id, scenario.case_id)
    assert (task_case.status, task_case.evaluation_status) == ('skipped', 'stopped')


def test_update_task_case_status_excludes_legacy_stopped_case(wired_app):
    """历史数据里的 'stopped' 仍被排除（保持原有语义）。"""
    scenario = _build_scenario(
        round_count=1,
        case_execution_status='stopped',
        case_evaluation_status='stopped',
        case_status='stopped',
    )

    update_count = update_task_case_status_in_db(
        db.session, scenario.task.id, scenario.case_id, 'completed', 'completed'
    )

    assert update_count == 0
    task_case = _reload_task_case(scenario.task.id, scenario.case_id)
    assert (task_case.status, task_case.evaluation_status) == ('stopped', 'stopped')


# ────────────────────────────────────────────────────────
# D3：state 为 None 不得抛 TypeError
# ────────────────────────────────────────────────────────
def test_sync_without_any_dimension_rows(wired_app):
    """用例没有任何维度记录时：不推进、不抛异常（旧代码会在 state['failed'] 抛 TypeError）。"""
    scenario = _build_scenario(
        round_count=1,
        case_execution_status='completed',
        case_evaluation_status='calculating',
    )

    assert _dim_state(scenario.task.id, scenario.case_id) is None, '前置：该用例无维度记录'

    advanced, new_status = sync_case_evaluation_status_from_dimensions(
        db.session, scenario.task.id, scenario.case_id
    )

    assert (advanced, new_status) == (False, None)
    task_case = _reload_task_case(scenario.task.id, scenario.case_id)
    assert task_case.evaluation_status == 'calculating'


def test_sync_without_dimension_rows_and_terminal_status(wired_app):
    """无维度记录 + 用例级终态：同样直接返回，不触碰 state（旧代码在此抛 TypeError）。"""
    scenario = _build_scenario(
        round_count=1,
        case_execution_status='completed',
        case_evaluation_status='stopped',
        case_status='skipped',
    )

    advanced, new_status = sync_case_evaluation_status_from_dimensions(
        db.session, scenario.task.id, scenario.case_id
    )

    assert (advanced, new_status) == (False, None)
    task_case = _reload_task_case(scenario.task.id, scenario.case_id)
    assert (task_case.status, task_case.evaluation_status) == ('skipped', 'stopped')


def test_sync_without_dimension_rows_does_not_raise_on_state_access(wired_app):
    """直接锁死 D3 的异常形态：旧代码在此抛 TypeError('NoneType' object is not subscriptable)。"""
    scenario = _build_scenario(
        round_count=1,
        case_execution_status='completed',
        case_evaluation_status='calculating',
    )
    # 用旧口径（终态直接 return True）模拟：把用例级置终态并调用兜底同步，
    # 旧实现会走到 state['failed']；新实现必须安全返回。
    db.session.query(TaskCase).filter_by(
        task_id=scenario.task.id, test_case_id=scenario.case_id
    ).update({'evaluation_status': 'completed'}, synchronize_session=False)
    db.session.commit()

    try:
        result = sync_case_evaluation_status_from_dimensions(
            db.session, scenario.task.id, scenario.case_id
        )
    except TypeError as exc:  # pragma: no cover - 失败时给出明确诊断
        pytest.fail(f'state 为 None 时不得抛 TypeError: {exc}')

    assert result == (False, None)
