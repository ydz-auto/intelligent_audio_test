# -*- coding: utf-8 -*-
"""VEGA-54 独立验收用例（测试工程师）。

验收对象：commit `319c0942`
（`evaluation_mixin.EXECUTION_SETTLED_STATUSES` 扩为 completed/failed/stopped/skipped、
`maybe_finalize` 用例集按该口径查询、停止态用例的评估状态收敛分支）。
本文件不复用开发自测文件 `test_vega54_stopped_task_finalize.py` 的任何夹具，按卡内
「验收标准」1–5 独立构造现场，并额外锁住开发自测未覆盖的四点：

1. **因果链而非相关**：把共享常量在**两个模块里同时收窄回修复前的
   ('completed','failed')**，同一现场必须重现实测症状（`maybe_finalize` 放弃 +
   报告门禁拒绝）——证明红→绿确实由那一处口径决定，不是夹具巧合
   （见 `test_ac1_narrowing_shared_constant_reproduces_field_symptom`）；
2. **实测日志锚点**：现场「后端日志里 `重新评估完成: task_id=420` 出现 0 次」，
   故本文件直接捕获 `log_and_emit` 调用，断言该行在**进程内**出现一次
   （不重启、不依赖恢复扫描）；
3. **等待 → 收敛 → 收尾的完整时序**：不收敛时拒绝收尾，补上最后一轮终态后**同一次调用**
   必须放行——证明修复是「等收敛」而不是「停止即收尾」；
4. **报告侧口径留痕**：收尾后报告门禁放行，且报告头计数把停止态用例排除在
   failed 之外（分母仍含它）——直接对应卡内风险「别把人为停止当失败写进报告」。

另有一处**已知窗口的加宽**以 `xfail(strict=True)` 显式留痕（见文件末尾
`test_ac3_widened_scope_window_characterized`）：`maybe_finalize` 的用例集只要求
「集合内的用例都到终态」，不要求「任务下不存在仍在执行的用例」。该窗口 VEGA-52 验收时
已留痕（`test_vega52_acceptance_independent.py::test_ac1_residual_task_finalize_with_other_settled_case`），
本卡把它从「另有 completed 用例」加宽到「另有 stopped 用例」；可达性分析见该用例 docstring。

运行：python -m pytest backend/tests/test_vega54_acceptance_independent.py -q
（需本机 PostgreSQL 已启动：python start_postgres.py；本文件单独运行，避免跨文件 commit 污染）
"""
import uuid
from datetime import datetime

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
    update_task_case_status_in_db,
)
from backend.services.execution.reevaluation_executor import ReevaluationExecutor

TASK_DEVICE_COUNT = 3          # 复现实测现场：3 台设备 / 每用例只落 1 个 TestResult
DIM_COUNT = 2
ROUND_COUNT = 2
ALGORITHM_TYPE = 'voice_llm'
STOP_MESSAGE = '任务被手动停止'
STOPPED_AT = datetime(2026, 10, 16, 20, 40, 0)   # 停止路径写入的 completed_at（用例级）
GATE_REJECT_MESSAGE = '只有任务状态为completed、failed或merged时才能生成报告'
FINALIZE_LOG = '重新评估完成'


# ────────────────────────────────────────────────────────
# 夹具与构造工具
# ────────────────────────────────────────────────────────
@pytest.fixture
def wired_app(app, monkeypatch):
    """把各评估模块缓存的 app 全局指向当前测试应用。"""
    import backend.services.evaluation.evaluation_service as evaluation_service_module
    import backend.services.evaluation.evaluation_result_processor as processor_module
    import backend.services.evaluation.endpoint_worker as worker_module

    monkeypatch.setattr(evaluation_service_module, 'app', app, raising=False)
    monkeypatch.setattr(processor_module, 'app', app, raising=False)
    monkeypatch.setattr(worker_module, 'app', app, raising=False)
    return app


def _make_task(suffix, status='stopped', stop_time=None):
    """建任务。停止路径会同时写 task.status='stopped' 与 completed_at（实测现场 420 同形）。"""
    task = Task(
        name=f'VEGA54独立验收_{suffix}', type='e2e', status=status,
        total_cases=1, completed_at=stop_time,
    )
    db.session.add(task)
    db.session.flush()
    for _ in range(TASK_DEVICE_COUNT):
        device = Device(
            name=f'VEGA54A设备_{suffix}_{uuid.uuid4().hex[:6]}', model='M1', type='phone',
            system='Android', system_version='14', app_name='App', app_version='1.0',
            status='online',
        )
        db.session.add(device)
        db.session.flush()
        db.session.add(TaskDevice(task_id=task.id, device_id=device.id))
    db.session.flush()
    return task


def _add_case(task, suffix, index, execution_status, evaluation_status,
              status='skipped', round_count=ROUND_COUNT, with_result=True,
              stopped_at=None):
    """在任务下建一个用例（含 TestResult，execution_status='completed'）。

    停止路径同形：status='skipped' + execution_status='stopped' + evaluation_status='stopped'
    + completed_at=停止时刻 + error_message='任务被手动停止'（见 execution_engine.control_task
    停止分支）。completed_at 显式落库，用于锁住「收敛不得覆盖停止时刻」。
    """
    dims = []
    for dim_idx in range(DIM_COUNT):
        dim = Dimension(
            name=f'VEGA54A维度_{suffix}_{index}_{dim_idx}', type='auto', result_type=0,
            weight=1, status=True, deleted=False, statistic_method='average',
        )
        db.session.add(dim)
        db.session.flush()
        dims.append(dim)

    case_id = f'vega54a_case_{suffix}_{index}'
    round_cfg = {'evaluation': {'dimensions': [{'id': d.id} for d in dims]}}
    db.session.add(TestCase(
        id=case_id,
        name=f'VEGA-54 独立验收用例_{suffix}_{index}',
        algorithm_type=ALGORITHM_TYPE,
        test_type='e2e',
        config={'rounds': [dict(round_cfg) for _ in range(round_count)], 'dimensions': []},
    ))
    db.session.flush()  # 无 relationship 声明，需显式 flush 保证先落 test_cases

    db.session.add(TaskCase(
        task_id=task.id,
        test_case_id=case_id,
        status=status,
        execution_status=execution_status,
        evaluation_status=evaluation_status,
        completed_at=stopped_at if status in ('stopped', 'skipped') else None,
        error_message=STOP_MESSAGE if status in ('stopped', 'skipped') else None,
    ))

    result = None
    if with_result:
        result = TestResult(
            task_id=task.id,
            test_case_id=case_id,
            algorithm_type=ALGORITHM_TYPE,
            execution_status='completed',
            algorithm_result={'rounds': [{'reference_params': []}]},
            result_data={'multi_round': True, 'total_rounds': round_count},
        )
        db.session.add(result)
    db.session.flush()
    return SimpleNamespace(case_id=case_id, dims=dims, result=result)


def _add_round_dimensions(case, round_number, evaluation_status):
    """为指定轮次建出维度行（等价于该轮评估派发时 _create_dimension_results 落库）。"""
    for dim in case.dims:
        db.session.add(TestResultDimension(
            test_result_id=case.result.id,
            dimension_id=dim.id,
            algorithm_type=ALGORITHM_TYPE,
            evaluation_status=evaluation_status,
            round_number=round_number,
        ))
    db.session.commit()


def _all_rounds_terminal(case, evaluation_status='completed'):
    """所有已配置轮次的维度都到终态（实测现场：TRD 638 行全 completed / 0 failed）。"""
    for round_number in range(ROUND_COUNT):
        _add_round_dimensions(case, round_number, evaluation_status)


def _stopped_task_scenario(stop_time=STOPPED_AT):
    """实测现场（task 420）同形：任务被手动 stop，用例 status='skipped' /
    execution_status='stopped' / evaluation_status='stopped' / completed_at=停止时刻。"""
    suffix = uuid.uuid4().hex[:8]
    task = _make_task(suffix, status='stopped', stop_time=stop_time)
    case = _add_case(task, suffix, 0, 'stopped', 'stopped', status='skipped',
                     stopped_at=stop_time)
    return SimpleNamespace(task=task, case=case, suffix=suffix)


def _reload(task_id, case_id=None):
    db.session.expire_all()
    task = db.session.query(Task).filter_by(id=task_id).first()
    if case_id is None:
        return task
    tc = db.session.query(TaskCase).filter_by(task_id=task_id, test_case_id=case_id).first()
    return tc, task


def _arm_reevaluation(monkeypatch, task_id):
    """让 ReevaluationExecutor 认为自己正是该任务的当前重评处理者（进程内收尾的前提）。"""
    executor = ReevaluationExecutor.get_instance()
    monkeypatch.setattr(executor, 'is_reevaluating', True)
    monkeypatch.setattr(executor, 'running_task_id', task_id)
    return executor


def _simulate_reeval_submit(task, executor):
    """模拟重评提交阶段的状态迁移：submit→reevaluate_queued、_check_queue→reevaluating、
    _on_complete(True)→running（评估仍在后台算）。"""
    task.status = 'reevaluating'
    db.session.commit()
    executor._on_complete(task.id, True)
    db.session.expire_all()


def _simulate_case_reeval_dispatch(task_id, case_id):
    """模拟 _reevaluate_multi_round + EndpointWorker 对停止态用例的驱动：
    evaluation_status 由 'stopped' 置回 queued→running→calculating，status 保持 'skipped'。"""
    for status in ('queued', 'running', 'calculating'):
        db.session.query(TaskCase).filter_by(
            task_id=task_id, test_case_id=case_id
        ).update({'evaluation_status': status}, synchronize_session=False)
        db.session.commit()
    db.session.expire_all()


def _capture_logs(monkeypatch):
    """捕获 reevaluation_executor 的 log_and_emit 调用（实测症状即「该行出现 0 次」）。"""
    import backend.services.execution.reevaluation_executor as reeval_module

    captured = []

    def fake_log(*args, **kwargs):
        content = args[2] if len(args) > 2 else kwargs.get('content')
        captured.append(content)

    monkeypatch.setattr(reeval_module, 'log_and_emit', fake_log)
    return captured


def _report_gate(task_id):
    """报告门禁：generate-task 与 regenerate 共用的同一处校验（返回 (task, results, error)）。

    先 expire_all：收尾发生在 maybe_finalize 自己的 app context 里（另一个会话），
    本会话的 identity map 可能还留着收尾前的 Task 实例，直接读会拿到过期状态。
    """
    from backend.controllers.report_controller_task import ReportControllerTask
    db.session.expire_all()
    return ReportControllerTask._validate_task_and_get_results(task_id)


def _gate_message(error):
    """把 error_response 的 (Response, http_code) 还原成可断言的文案。"""
    assert error is not None, '预期门禁拒绝，实际放行'
    response = error[0] if isinstance(error, tuple) else error
    return response.get_json()['message']


# ════════════════════════════════════════════════════════
# 验收标准 1：stop → 重评 → 收敛，任务不重启即可离开 running
# ════════════════════════════════════════════════════════
def test_ac1_stop_then_reeval_settles_task_in_process(wired_app, monkeypatch):
    """红锚点 + 实测日志锚点：全部用例都是停止态时，重评收敛必须由**进程内**回调收尾。

    实测现场（task 420）：TRD 全 completed、tcr 31/31 evaluation_status='completed'，
    但任务仍是 running，日志里 `重新评估完成: task_id=420` 出现 0 次；最后靠重启触发
    恢复扫描（`更新任务状态数: 1`）才置 failed 解锁。
    """
    sc = _stopped_task_scenario()
    _all_rounds_terminal(sc.case)
    logs = _capture_logs(monkeypatch)
    executor = _arm_reevaluation(monkeypatch, sc.task.id)

    _simulate_reeval_submit(sc.task, executor)
    assert _reload(sc.task.id).status == 'running', '前置：重评提交成功后任务回到 running'

    assert executor.maybe_finalize(sc.task.id) is True, (
        '停止过的用例（execution_status=stopped）必须在收尾用例集内，'
        '否则用例集查空 ⇒ 直接 return False ⇒ 任务永久 running'
    )

    task = _reload(sc.task.id)
    assert task.status == 'completed', '任务必须离开 running'
    assert any(FINALIZE_LOG in (c or '') for c in logs), (
        f'进程内必须打出「{FINALIZE_LOG}」日志（实测该行为 0 次即本缺陷症状）'
    )
    assert executor.running_task_id is None, '收尾后必须释放重评队列句柄'

    # 停止语义保留：用例级 status 不得被改写成 completed/failed（报告口径依赖它）
    tc, _ = _reload(sc.task.id, sc.case.case_id)
    assert tc.status == 'skipped', '人为停止不得被写成 completed/failed'


def test_ac1_narrowing_shared_constant_reproduces_field_symptom(wired_app, monkeypatch):
    """因果链自证：把共享常量在两个模块里同时收窄回修复前的 ('completed','failed')，
    同一现场必须重现实测症状（收尾放弃 + 报告门禁拒绝）。

    这排除了「夹具恰好让新代码变绿」的可能：红→绿确实由 EXECUTION_SETTLED_STATUSES
    这一处口径决定，而不是别处的副作用。
    """
    import backend.services.evaluation.evaluation_mixin as mixin_module
    import backend.services.execution.reevaluation_executor as reeval_module

    sc = _stopped_task_scenario()
    _all_rounds_terminal(sc.case)
    executor = _arm_reevaluation(monkeypatch, sc.task.id)
    _simulate_reeval_submit(sc.task, executor)

    # 修复前口径（VEGA-52 定稿 e411b802）
    monkeypatch.setattr(mixin_module, 'EXECUTION_SETTLED_STATUSES', ('completed', 'failed'))
    monkeypatch.setattr(reeval_module, 'EXECUTION_SETTLED_STATUSES', ('completed', 'failed'))

    assert executor.maybe_finalize(sc.task.id) is False, '旧口径下用例集查空 ⇒ 放弃收尾'
    assert _reload(sc.task.id).status == 'running', '症状一：任务永久 running'
    assert _gate_message(_report_gate(sc.task.id)[2]) == GATE_REJECT_MESSAGE, (
        '症状二：报告门禁拒绝（实测「报告不可生成」）'
    )

    # 恢复本卡口径：同一现场立刻可收尾、门禁放行
    monkeypatch.undo()
    executor = _arm_reevaluation(monkeypatch, sc.task.id)
    assert executor.maybe_finalize(sc.task.id) is True
    assert _reload(sc.task.id).status == 'completed'
    assert _report_gate(sc.task.id)[2] is None


def test_ac1_finalize_waits_for_last_round_then_settles(wired_app, monkeypatch):
    """时序：最后一轮维度仍在算时拒绝收尾；补上终态后**同一次调用**必须放行。

    证明修复是「等收敛」，不是「见到 stopped 就收尾」——否则会把真在跑的轮次提前收尾。
    """
    sc = _stopped_task_scenario()
    executor = _arm_reevaluation(monkeypatch, sc.task.id)
    _simulate_reeval_submit(sc.task, executor)
    _simulate_case_reeval_dispatch(sc.task.id, sc.case.case_id)

    _add_round_dimensions(sc.case, 0, 'completed')
    _add_round_dimensions(sc.case, 1, 'calculating')   # 第 1 轮仍在算

    assert executor.maybe_finalize(sc.task.id) is False, '仍有维度在算时不得收尾'
    assert _reload(sc.task.id).status == 'running'

    db.session.query(TestResultDimension).filter_by(
        test_result_id=sc.case.result.id, round_number=1
    ).update({'evaluation_status': 'completed'}, synchronize_session=False)
    db.session.commit()

    assert executor.maybe_finalize(sc.task.id) is True, '最后一轮到终态后必须能收尾'
    assert _reload(sc.task.id).status == 'completed'


# ════════════════════════════════════════════════════════
# 验收标准 2：报告门禁可通过（不再依赖恢复扫描）
# ════════════════════════════════════════════════════════
def test_ac2_report_gate_opens_only_after_settled(wired_app, monkeypatch):
    """门禁三段式：停止态拒绝 → 重评未收敛仍拒绝 → 收敛收尾后放行且结果进报告。"""
    from backend.utils.report.report_utils import ReportUtils

    sc = _stopped_task_scenario()
    _all_rounds_terminal(sc.case)

    assert _gate_message(_report_gate(sc.task.id)[2]) == GATE_REJECT_MESSAGE, (
        '前置：任务 stopped ⇒ 门禁拒绝（实测症状）'
    )

    executor = _arm_reevaluation(monkeypatch, sc.task.id)
    _simulate_reeval_submit(sc.task, executor)
    _simulate_case_reeval_dispatch(sc.task.id, sc.case.case_id)

    task, results, error = _report_gate(sc.task.id)
    assert error is not None, '任务仍 running（重评未收尾）时门禁必须拒绝'

    assert executor.maybe_finalize(sc.task.id) is True

    task, results, error = _report_gate(sc.task.id)
    assert error is None, f'收尾后门禁必须放行，实际: {_gate_message(error)}'
    assert task is not None and results, '门禁应返回任务与测试结果'
    kept = ReportUtils.filter_results_by_case_evaluation(results)
    assert kept, '维度级全 completed 的用例结果应进入报告（实测 638/638 行 completed）'


def test_ac2_report_head_counts_do_not_book_stop_as_failure(wired_app):
    """报告侧口径留痕：停止态用例（status='skipped'）不进 completed、也不进 failed。

    卡内风险「别把人为停止当失败写进报告」：分母（存活用例数）仍含它，但 failed 计数
    不含它——修复后走的是「维度级收敛」，不把人为停止改写成 failed。

    **本用例锁的是当前口径，供审计员判定**（报告头计数按用例级 status 取 completed/failed，
    而报告明细按维度级口径收录，二者对「停止但评估已收敛」的用例不一致）；若报告口径
    改为「停止态计入 completed」，本用例应同步更新，不是本卡的回退。
    """
    from backend.controllers.report_controller_task import ReportControllerTask

    sc = _stopped_task_scenario()
    other = _add_case(sc.task, sc.suffix, 1, 'completed', 'completed', status='completed')
    _all_rounds_terminal(sc.case)
    _all_rounds_terminal(other)
    db.session.commit()

    cases = db.session.query(TestCase).filter(
        TestCase.id.in_([sc.case.case_id, other.case_id])
    ).all()
    total, completed, failed = ReportControllerTask._surviving_case_counts(
        [sc.task.id], cases
    )

    assert (total, completed, failed) == (2, 1, 0), (
        f'停止态用例应留在分母、不计 failed，实际 {(total, completed, failed)}'
    )


# ════════════════════════════════════════════════════════
# 验收标准 3：反向——仍在执行的用例不得被误判收尾（VEGA-52 D1 不回退）
# ════════════════════════════════════════════════════════
@pytest.mark.parametrize('execution_status', ['pending', 'queued', 'running', 'evaluating'])
def test_ac3_non_settled_execution_status_never_finished(execution_status):
    """口径反向：任何「执行侧未终结」的取值都不得被判定为评估结束。

    现场即 VEGA-52 D1：多轮用例第 0 轮维度全终态、第 1 轮维度尚未建出、执行仍在跑；
    此时「现有维度都到终态」等价于「上一轮算完、下一轮还没派发」，不是评估结束。
    """
    state = {'total': DIM_COUNT, 'in_progress': 0, 'failed': 0}
    assert is_case_evaluation_finished('calculating', state, execution_status) is False, (
        f'execution_status={execution_status!r} 属执行侧未终结，不得判为评估结束'
    )


def test_ac3_settled_scope_is_exactly_manual_stop_plus_terminal(wired_app):
    """口径自证：收尾集合 = 执行侧终态（completed/failed）∪ 人工停止（stopped/skipped），
    不含任何「仍在进行」的取值；且 completed/failed 的既有语义未被改动。"""
    assert set(EXECUTION_SETTLED_STATUSES) == {'completed', 'failed', 'stopped', 'skipped'}
    for in_progress in ('pending', 'queued', 'running', 'evaluating'):
        assert in_progress not in EXECUTION_SETTLED_STATUSES

    state = {'total': DIM_COUNT, 'in_progress': 0, 'failed': 0}
    for settled in ('completed', 'failed', 'stopped', 'skipped'):
        assert is_case_evaluation_finished('calculating', state, settled) is True, (
            f'{settled} 属执行侧已终结 ⇒ 维度全终态即评估结束'
        )
    # 维度仍在算 ⇒ 任何执行状态都不算结束
    assert is_case_evaluation_finished(
        'calculating', {'total': DIM_COUNT, 'in_progress': 1, 'failed': 0}, 'stopped'
    ) is False


def test_ac3_running_case_keeps_task_running_end_to_end(wired_app, monkeypatch):
    """端到端反向：任务内用例仍在执行（execution_status='running'）时，收尾必须放弃。"""
    suffix = uuid.uuid4().hex[:8]
    task = _make_task(suffix, status='running')
    case = _add_case(task, suffix, 0, 'running', 'calculating', status='running')
    _add_round_dimensions(case, 0, 'completed')   # 第 0 轮算完，第 1 轮维度尚未建出

    executor = _arm_reevaluation(monkeypatch, task.id)
    assert executor.maybe_finalize(task.id) is False
    assert _reload(task.id).status == 'running', '仍在跑轮次的任务不得被提前收尾'
    tc, _ = _reload(task.id, case.case_id)
    assert tc.evaluation_status == 'calculating'


def test_ac3_vega52_d2_exclusion_still_effective(wired_app):
    """VEGA-52 D2 契约不回退：统一更新函数对 stopped/skipped 用例 0 行、普通用例 1 行。

    两个方向都测——否则「保护生效」可由「过滤器把所有用例都挡掉」这种退化解满足。
    """
    sc = _stopped_task_scenario()
    assert update_task_case_status_in_db(
        db.session, sc.task.id, sc.case.case_id, 'completed', 'completed'
    ) == 0, '停止路径写的是 status=skipped，保护必须对它生效'
    tc, _ = _reload(sc.task.id, sc.case.case_id)
    assert (tc.status, tc.evaluation_status) == ('skipped', 'stopped')

    other = _add_case(sc.task, sc.suffix, 1, 'completed', 'calculating', status='pending')
    assert update_task_case_status_in_db(
        db.session, sc.task.id, other.case_id, 'completed', 'completed'
    ) == 1, '普通用例必须照常被更新'
    tc, _ = _reload(sc.task.id, other.case_id)
    assert (tc.status, tc.evaluation_status) == ('completed', 'completed')


def test_ac3_stopped_case_reeval_convergence_keeps_stop_semantics(wired_app):
    """停止态用例被重评重新驱动后：只收敛 evaluation_status，status/completed_at 保持停止语义。

    若这一处不收敛，VEGA-43 要治的「用例级永久停在 calculating」会原样换到
    「先 stop → 再重评」这条路径上（VEGA-52 D2 的 exclude_stopped 让正常收尾写不进去）。
    """
    sc = _stopped_task_scenario()
    _simulate_case_reeval_dispatch(sc.task.id, sc.case.case_id)
    _all_rounds_terminal(sc.case)

    tc, _ = _reload(sc.task.id, sc.case.case_id)
    assert tc.evaluation_status == 'calculating', '前置：重评重新驱动后用例级在算'

    advanced, new_status = sync_case_evaluation_status_from_dimensions(
        db.session, sc.task.id, sc.case.case_id
    )

    assert (advanced, new_status) == (True, 'completed')
    tc, _ = _reload(sc.task.id, sc.case.case_id)
    assert tc.status == 'skipped', '停止语义必须保留（报告口径依赖它）'
    assert tc.evaluation_status == 'completed'
    assert tc.completed_at == STOPPED_AT, '不得把人为停止的用例改成别的完成时间'


def test_ac3_untouched_stopped_case_stays_untouched(wired_app):
    """VEGA-52 D2 不回退：未被重评驱动的停止态用例（evaluation_status='stopped'）
    即便维度全 completed 也不得被兜底同步改写。"""
    sc = _stopped_task_scenario()
    _all_rounds_terminal(sc.case)

    advanced, new_status = sync_case_evaluation_status_from_dimensions(
        db.session, sc.task.id, sc.case.case_id
    )

    assert (advanced, new_status) == (False, None)
    tc, _ = _reload(sc.task.id, sc.case.case_id)
    assert (tc.status, tc.evaluation_status) == ('skipped', 'stopped')
    assert tc.completed_at == STOPPED_AT, '停止时刻不得被改写'


@pytest.mark.xfail(
    strict=True,
    reason='VEGA-52 遗留窗口（VEGA-54 加宽了触发集合，未新增类别）：maybe_finalize 只要求'
           '「用例集内的用例都到终态」，不要求「任务下不存在仍在执行的用例」。'
           '本卡把该集合由「另有 completed 用例」加宽到「另有 stopped 用例」。'
           '若后续把判据收紧为「任务下不存在执行侧未终结的用例」，本标记应删除。',
)
def test_ac3_widened_scope_window_characterized(wired_app, monkeypatch):
    """窗口留痕：同一任务内「一个停止态用例 + 一个仍在执行的用例」时，收尾判据仍会放行。

    可达性（读码复核）：需同时满足 ①本进程正在重评该任务（running_task_id 匹配——
    重评入口只放行 completed/failed/stopped/paused/skipped，故任务此刻已被 _on_complete
    置回 running）；②任务内存在 execution_status='running' 的用例；③其余用例都是
    「已收尾但未到终态」的形态。任务级 stop 会把所有未完成用例置 stopped（不会留下
    running 用例），单用例 skip 又拒绝执行中的用例，故 ②③ 并存需 paused 现场
    （API 任务暂停时用例保留 execution_status='running'，见 execution_engine 暂停分支）
    或 status 与 execution_status 不一致的历史数据。

    与 VEGA-52 的关系：修复前该窗口在「另有 completed 用例」时同样成立
    （test_vega52_acceptance_independent.py::test_ac1_residual_task_finalize_with_other_settled_case
    已 xfail 留痕），本卡只把触发集合加宽，未新增缺陷类别。
    """
    suffix = uuid.uuid4().hex[:8]
    task = _make_task(suffix, status='running')
    stopped = _add_case(task, suffix, 0, 'stopped', 'stopped', status='skipped')
    running = _add_case(task, suffix, 1, 'running', 'calculating', status='running')
    _add_round_dimensions(stopped, 0, 'completed')
    _add_round_dimensions(running, 0, 'completed')   # 第 1 轮维度尚未建出

    executor = _arm_reevaluation(monkeypatch, task.id)
    assert executor.maybe_finalize(task.id) is False, (
        '任务内仍有用例在执行时不得收尾（当前实现会放行 ⇒ 本用例按 xfail 留痕）'
    )
    assert _reload(task.id).status == 'running'


# ════════════════════════════════════════════════════════
# 验收标准 4：与 VEGA-52 共存（本文件内的行为级证据；跨文件合并运行见评论）
# ════════════════════════════════════════════════════════
def test_ac4_vega52_d1_round_integrity_semantics_preserved(wired_app):
    """VEGA-52 D1 的轮次完整性前置在 VEGA-54 口径下逐条不变。

    D1 的实质是「执行侧未终结 ⇒ 不认定评估结束」；VEGA-54 只把「已终结」的集合补上
    人工停止，未触碰「未终结」的一侧。本用例把 D1 的两个方向都钉住。
    """
    terminal = {'total': DIM_COUNT, 'in_progress': 0, 'failed': 0}
    in_flight = {'total': DIM_COUNT, 'in_progress': 1, 'failed': 0}

    # D1 保护方向：执行未终结 ⇒ 一律不结束（与 VEGA-52 定稿逐字一致）
    for unsettled in ('pending', 'queued', 'running'):
        assert is_case_evaluation_finished('calculating', terminal, unsettled) is False
        assert is_case_evaluation_finished('completed', terminal, unsettled) is False
    # 评估仍在派发前（pending/queued/running）⇒ 不凭「现有维度都到终态」判定结束（D4 边界）
    for eval_status in ('pending', 'queued', 'running'):
        assert is_case_evaluation_finished(eval_status, terminal, 'completed') is False
    # 维度仍在算 ⇒ 不结束
    assert is_case_evaluation_finished('calculating', in_flight, 'completed') is False
    # 无维度记录 ⇒ 不结束（避免把未派发当成算完）
    assert is_case_evaluation_finished('calculating', None, 'completed') is False
