# -*- coding: utf-8 -*-
"""VEGA-54：手动 stop 过的任务在重评收敛后必须能正常收尾（不再靠重启恢复扫描解锁）。

被测缺陷（规划师直连库 + 读码复核；VEGA-25 第二轮补跑现场：任务 420 / 报告 462）：

  任务被手动 stop 后，未完成用例被停止路径置为 execution_status='stopped'
  （status='skipped'、evaluation_status='stopped'，见 execution_engine 停止分支）。
  「先 stop 解锁提交入口 → 再重评」是明确认可的标准操作（reevaluate_task_results
  的白名单含 stopped），但重评收敛后**没有任何人能收尾**：

    1. ``maybe_finalize`` 的用例集只查 ``execution_status='completed'`` ⇒ 停止过的
       用例全部被排除 ⇒ 用例集查空 ⇒ 直接 ``return False``（VEGA-52 新引入的维度级
       判据在这条路径上是死代码）；
    2. 即便用例集非空，``is_case_evaluation_finished`` 的「轮次完整性」前置只认
       completed/failed ⇒ stopped 被挡（VEGA-52 D1 建议的最小改法在本场景更死）。

  组合后果：任务永久 running、报告门禁（只放行 completed/failed/merged）不过，
  只能靠重启 :5000 触发 RECOVERY_SWEEP_ON_STARTUP 把任务置 failed 才解锁——
  那是重副作用通道（同一扫描会把进行中的用例/维度一并置 failed），不能当常规手段。

被测口径（VEGA-54）：
  - ``EXECUTION_SETTLED_STATUSES`` 扩为 completed/failed/stopped/skipped
    （人工停止后执行侧同样不会再派发新轮次 ⇒ 轮次完整性成立）；
  - ``maybe_finalize`` 的用例集按该口径查询；
  - 人工停止的用例在「评估进行中」（被用户显式重评重新驱动：evaluation_status 已由
    'stopped' 置回 queued/running/calculating）时，只收敛 evaluation_status，
    status 保持 skipped/stopped——停止语义要留给报告，不得把人为停止写成 completed/failed。

不跑真实 ASR / eval_server：直接驱动状态机与收尾判据，构造与实测现场同形的
「3 台设备 / 1 个 TestResult / 2 轮」现场。
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
    EXECUTION_SETTLED_STATUSES,
    is_case_evaluation_finished,
    sync_case_evaluation_status_from_dimensions,
)
from backend.services.execution.reevaluation_executor import ReevaluationExecutor

# 与实测现场同形：3 台设备（复现「结果未全 1/3」守卫）、2 个维度、2 轮
TASK_DEVICE_COUNT = 3
DIM_COUNT = 2
ROUND_COUNT = 2
ALGORITHM_TYPE = 'voice_llm'


# ────────────────────────────────────────────────────────
# 夹具
# ────────────────────────────────────────────────────────
@pytest.fixture
def wired_app(app, monkeypatch):
    """把各评估模块延迟导入的 app 全局指向当前测试应用（同 VEGA-52 夹具）。"""
    import backend.services.evaluation.evaluation_service as evaluation_service_module
    import backend.services.evaluation.evaluation_result_processor as processor_module
    import backend.services.evaluation.endpoint_worker as worker_module

    monkeypatch.setattr(evaluation_service_module, 'app', app, raising=False)
    monkeypatch.setattr(processor_module, 'app', app, raising=False)
    monkeypatch.setattr(worker_module, 'app', app, raising=False)
    return app


def _build_scenario(case_status, case_execution_status, case_evaluation_status,
                    task_status='stopped', round_count=ROUND_COUNT):
    """构造「多轮 + 3 台设备 + 1 个 TestResult」现场（TestResult 执行已完成）。"""
    suffix = uuid.uuid4().hex[:8]

    task = Task(name=f'VEGA-54 现场_{suffix}', type='e2e', status=task_status, total_cases=1)
    db.session.add(task)
    db.session.flush()

    devices = []
    for _ in range(TASK_DEVICE_COUNT):
        device = Device(
            name=f'VEGA54设备_{suffix}_{uuid.uuid4().hex[:6]}', model='M1', type='phone',
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
            name=f'VEGA54维度_{suffix}_{idx}', type='auto', result_type=0, weight=1,
            status=True, deleted=False, statistic_method='average',
        )
        db.session.add(dim)
        db.session.flush()
        dims.append(dim)

    case_id = f'vega54_case_{suffix}'
    round_cfg = {'evaluation': {'dimensions': [{'id': d.id} for d in dims]}}
    test_case = TestCase(
        id=case_id,
        name=f'VEGA-54 多轮用例_{suffix}',
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
        error_message='任务被手动停止' if case_status in ('stopped', 'skipped') else None,
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

    return SimpleNamespace(
        task=task, case_id=case_id, dims=dims, result=result, task_case=task_case,
        round_count=round_count,
    )


def _build_stopped_scenario(case_evaluation_status='stopped', task_status='stopped'):
    """实测现场（task 420）：任务被手动 stop ⇒ 用例 status='skipped'、
    execution_status='stopped'、evaluation_status='stopped'。"""
    return _build_scenario(
        case_status='skipped',
        case_execution_status='stopped',
        case_evaluation_status=case_evaluation_status,
        task_status=task_status,
    )


def _add_round_dimensions(scenario, round_number, evaluation_status):
    """为指定轮次建出维度行（模拟该轮评估派发时 _create_dimension_results 落库）。"""
    for dim in scenario.dims:
        db.session.add(TestResultDimension(
            test_result_id=scenario.result.id,
            dimension_id=dim.id,
            algorithm_type=ALGORITHM_TYPE,
            evaluation_status=evaluation_status,
            round_number=round_number,
        ))
    db.session.commit()


def _all_rounds_terminal(scenario, status='completed'):
    """所有已配置轮次的维度都到终态（实测现场：TRD 638 行全 completed / 0 failed）。"""
    for round_number in range(scenario.round_count):
        _add_round_dimensions(scenario, round_number, status)


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


def _simulate_reeval_submit(scenario, executor):
    """模拟重评**提交阶段**的状态迁移（真实代码逐段对应）：

    - ``submit()``          → task.status='reevaluate_queued'
    - ``_check_queue()``    → task.status='reevaluating'
    - ``_on_complete(True)``→ 提交成功、评估仍在后台算 ⇒ task.status='running'
    """
    scenario.task.status = 'reevaluating'
    db.session.commit()
    executor._on_complete(scenario.task.id, True)
    db.session.expire_all()


def _simulate_reeval_in_flight(scenario, executor):
    """模拟「停止过的任务被显式提交重评、且重评已收敛到维度级终态」的状态迁移。

    在提交阶段之上，补上用例级评估状态的推进：

    - ``_reevaluate_multi_round`` 把用例级 ``evaluation_status`` 由 'stopped'
      置回 'queued'（status 保持 skipped，见该函数内 ``if tc_rel.status not in
      ['stopped', 'skipped']`` 守卫）；
    - ``EndpointWorker`` 消费 → 'queued' → 'running' → 提交前置 'calculating'。
    """
    _simulate_reeval_submit(scenario, executor)
    scenario.task_case.evaluation_status = 'queued'
    db.session.commit()
    scenario.task_case.evaluation_status = 'running'
    db.session.commit()
    scenario.task_case.evaluation_status = 'calculating'
    db.session.commit()
    db.session.expire_all()


def _report_gate(task_id):
    """报告门禁：generate-task / regenerate 共用的同一处校验。"""
    from backend.controllers.report_controller_task import ReportControllerTask
    return ReportControllerTask._validate_task_and_get_results(task_id)


# ────────────────────────────────────────────────────────
# 验收标准 1：stop → 重评 → 收敛，任务不重启即可离开 running
# ────────────────────────────────────────────────────────
def test_maybe_finalize_settles_task_with_all_cases_manually_stopped(wired_app, monkeypatch):
    """红锚点：全部用例都是停止态时，收尾判据不得因「用例集查空」直接放弃。

    修复前：``tcs = query(execution_status='completed')`` ⇒ 空 ⇒ return False
    ⇒ 任务永久 running（VEGA-52 的维度级判据根本没被调用到）。
    """
    scenario = _build_stopped_scenario()
    _all_rounds_terminal(scenario)
    executor = _arm_reevaluation(monkeypatch, scenario.task.id)
    _simulate_reeval_submit(scenario, executor)

    assert _reload_task(scenario.task.id).status == 'running', '前置：重评提交后任务回到 running'

    assert executor.maybe_finalize(scenario.task.id) is True, (
        '停止过的用例（execution_status=stopped）必须在收尾用例集内，否则任务永远无人收尾'
    )

    task = _reload_task(scenario.task.id)
    assert task.status == 'completed', '任务必须离开 running，且不依赖重启恢复扫描'
    assert executor.running_task_id is None, '收尾后必须释放重评队列句柄'


def test_maybe_finalize_settles_task_when_stopped_case_reeval_converged(wired_app, monkeypatch):
    """实测现场（task 420）：用例被停止后又重评，重评收敛 ⇒ 任务收尾。

    这条路径下用例级 evaluation_status 会停在 calculating：VEGA-52 D2 让
    ``update_task_case_status_in_db(exclude_stopped=True)`` 排除 skipped 用例，
    正常收尾路径写不进去。收尾判据必须以**维度级**为准（VEGA-43 口径）才能收敛。
    """
    scenario = _build_stopped_scenario()
    executor = _arm_reevaluation(monkeypatch, scenario.task.id)
    _simulate_reeval_in_flight(scenario, executor)
    _all_rounds_terminal(scenario)

    task_case = _reload_task_case(scenario.task.id, scenario.case_id)
    assert task_case.evaluation_status == 'calculating', (
        '前置：停止过的用例被重评重新驱动后，用例级处于 calculating（写不进终态）'
    )
    assert _reload_task(scenario.task.id).status == 'running', '前置：提交阶段结束后任务回到 running'

    assert executor.maybe_finalize(scenario.task.id) is True

    task = _reload_task(scenario.task.id)
    assert task.status == 'completed', '重评收敛后任务必须自行离开 running（无需重启）'
    assert executor.running_task_id is None


def test_stop_then_reeval_converges_case_and_task_without_restart(wired_app, monkeypatch):
    """验收标准 1+2 端到端：stop → 重评 → 收敛，任务离开 running 且报告门禁通过。

    同时锁死「用例级不得永久停在 calculating」：兜底同步要把 evaluation_status 收敛到
    与维度级一致，但 status 保持 'skipped'（人为停止语义保留给报告）。
    """
    scenario = _build_stopped_scenario()
    executor = _arm_reevaluation(monkeypatch, scenario.task.id)

    # 前置：任务 stopped ⇒ 报告门禁不过（实测症状「报告不可生成」）
    _task, _results, error = _report_gate(scenario.task.id)
    assert error is not None, '前置：停止态任务的报告门禁必须拒绝'

    _simulate_reeval_in_flight(scenario, executor)
    _all_rounds_terminal(scenario)

    # 兜底同步（评估结果处理路径真实调用点）：收敛用例级评估状态
    advanced, new_status = sync_case_evaluation_status_from_dimensions(
        db.session, scenario.task.id, scenario.case_id
    )
    assert (advanced, new_status) == (True, 'completed'), (
        '维度级全 completed ⇒ 用例级评估状态必须收敛，不得永久停在 calculating'
    )

    task_case = _reload_task_case(scenario.task.id, scenario.case_id)
    assert task_case.evaluation_status == 'completed'
    assert task_case.status == 'skipped', (
        '人工停止的用例不得被改写成 completed/failed（停止语义要留给报告）'
    )

    # 收尾：任务离开 running
    assert executor.maybe_finalize(scenario.task.id) is True
    assert _reload_task(scenario.task.id).status == 'completed'

    # 验收标准 2：报告门禁通过（不再依赖恢复扫描）
    task, results, error = _report_gate(scenario.task.id)
    assert error is None, f'收尾后报告门禁必须通过，实际: {error}'
    assert task is not None and results, '报告门禁应返回任务与测试结果'

    from backend.utils.report.report_utils import ReportUtils
    kept = ReportUtils.filter_results_by_case_evaluation(results)
    assert kept, '维度级全 completed 的用例结果应进入报告（实测现场 638/638 行 completed）'


def test_report_gate_still_blocks_running_task(wired_app, monkeypatch):
    """反向保护：任务仍在 running（重评未收敛）时报告门禁照旧拒绝。"""
    scenario = _build_stopped_scenario()
    executor = _arm_reevaluation(monkeypatch, scenario.task.id)
    _simulate_reeval_in_flight(scenario, executor)
    # 只到终态了部分轮次（第 0 轮算完、第 1 轮仍在算）⇒ 不得收尾
    _add_round_dimensions(scenario, 0, 'completed')
    _add_round_dimensions(scenario, 1, 'calculating')

    assert executor.maybe_finalize(scenario.task.id) is False
    assert _reload_task(scenario.task.id).status == 'running'

    _task, _results, error = _report_gate(scenario.task.id)
    assert error is not None, '任务未收敛时报告门禁必须拒绝'


# ────────────────────────────────────────────────────────
# 验收标准 3：VEGA-52 D1 的保护不得回退（真在执行的用例不被误判收尾）
# ────────────────────────────────────────────────────────
def test_running_case_is_not_settled(wired_app, monkeypatch):
    """仍在执行（execution_status='running'）的用例：不算「执行侧已终结」。

    现场即 VEGA-52 D1：多轮用例第 0 轮维度全终态、第 1 轮维度尚未建出、执行仍在跑。
    """
    scenario = _build_scenario(
        case_status='pending',
        case_execution_status='running',
        case_evaluation_status='calculating',
        task_status='running',
    )
    _add_round_dimensions(scenario, 0, 'completed')
    executor = _arm_reevaluation(monkeypatch, scenario.task.id)

    state = {'total': DIM_COUNT, 'in_progress': 0, 'failed': 0}
    assert is_case_evaluation_finished('calculating', state, 'running') is False, (
        'VEGA-52 D1 的轮次完整性前置不得因 VEGA-54 的口径放宽而回退'
    )

    assert executor.maybe_finalize(scenario.task.id) is False
    assert _reload_task(scenario.task.id).status == 'running', '仍在跑轮次的任务不得被提前收尾'
    assert _reload_task_case(scenario.task.id, scenario.case_id).evaluation_status == 'calculating'


def test_settled_statuses_cover_manual_stop_only():
    """口径自证：收尾取值含人工停止，但不含任何「仍在进行」的取值。"""
    assert set(EXECUTION_SETTLED_STATUSES) == {'completed', 'failed', 'stopped', 'skipped'}
    for in_progress in ('pending', 'queued', 'running', 'evaluating'):
        assert in_progress not in EXECUTION_SETTLED_STATUSES


# ────────────────────────────────────────────────────────
# 停止态用例的口径边界：只在「评估进行中」时收敛，且不得越过未完成维度
# ────────────────────────────────────────────────────────
def test_stopped_case_with_dimension_still_running_is_not_advanced(wired_app, monkeypatch):
    """停止过的用例：仍有维度在算 ⇒ 既不收敛用例级、也不收尾任务。"""
    scenario = _build_stopped_scenario()
    executor = _arm_reevaluation(monkeypatch, scenario.task.id)
    _simulate_reeval_in_flight(scenario, executor)
    _add_round_dimensions(scenario, 0, 'completed')
    _add_round_dimensions(scenario, 1, 'calculating')

    advanced, new_status = sync_case_evaluation_status_from_dimensions(
        db.session, scenario.task.id, scenario.case_id
    )
    assert (advanced, new_status) == (False, None)

    task_case = _reload_task_case(scenario.task.id, scenario.case_id)
    assert task_case.evaluation_status == 'calculating', '仍有维度在算，不得收敛'
    assert task_case.status == 'skipped'

    assert executor.maybe_finalize(scenario.task.id) is False
    assert _reload_task(scenario.task.id).status == 'running'


def test_stopped_case_not_being_reevaluated_is_left_alone(wired_app):
    """VEGA-52 D2 不回退：未被重评驱动的停止态用例（evaluation_status='stopped'）
    即便维度全 completed，也不得被兜底同步改写。"""
    scenario = _build_stopped_scenario()
    _all_rounds_terminal(scenario)

    advanced, new_status = sync_case_evaluation_status_from_dimensions(
        db.session, scenario.task.id, scenario.case_id
    )

    assert (advanced, new_status) == (False, None)
    task_case = _reload_task_case(scenario.task.id, scenario.case_id)
    assert (task_case.status, task_case.evaluation_status) == ('skipped', 'stopped')
    assert task_case.completed_at is None


def test_stopped_case_reeval_with_failed_dimension_converges_to_failed(wired_app):
    """停止过的用例重评后维度有失败 ⇒ 用例级评估状态收敛为 failed（维度级为准）。"""
    scenario = _build_stopped_scenario()
    _add_round_dimensions(scenario, 0, 'completed')
    _add_round_dimensions(scenario, 1, 'failed')
    db.session.query(TaskCase).filter_by(
        task_id=scenario.task.id, test_case_id=scenario.case_id
    ).update({'evaluation_status': 'calculating'}, synchronize_session=False)
    db.session.commit()

    advanced, new_status = sync_case_evaluation_status_from_dimensions(
        db.session, scenario.task.id, scenario.case_id
    )

    assert (advanced, new_status) == (True, 'failed')
    task_case = _reload_task_case(scenario.task.id, scenario.case_id)
    assert task_case.evaluation_status == 'failed'
    assert task_case.status == 'skipped', '用例级 status 仍保留人工停止语义'
