# -*- coding: utf-8 -*-
"""VEGA-52 独立验收用例（测试工程师）。

验收对象：VEGA-50 对 VEGA-43 修复的审计结论 D1–D4，修复 commit `e411b802`
（`evaluation_mixin` 判据补「轮次完整性」前置 + 兜底同步契约收紧；`reevaluation_executor.maybe_finalize`
调用点显式传执行状态）。本文件不复用开发自测文件 `test_vega52_eval_round_integrity.py`
的任何夹具，按卡内「验收标准」1–4 独立构造现场，并额外锁住三处开发自测未覆盖的行为：

1. **轮次间隙的对照口径**：同一现场同时断言「不带执行状态 ⇒ 误判为已结束」与
   「带执行状态 ⇒ 未结束」，证明判据确实由新增前置决定，而不是恒真/恒假；
2. **排除过滤器两个方向都测**：`update_task_case_status_in_db` 对 stopped/skipped
   必须 0 行（D2 现象二），对普通 pending 用例必须照常 1 行——否则「保护生效」可由
   「过滤器把所有用例都挡掉」这种退化解满足；
3. **真实时序**：评估派发走线程池异步（`evaluation_service` → `thread_pool.submit`），
   600s 超时到达时执行侧早已收尾，故 VEGA-43 主链路自证按此口径构造（用例级
   execution_status 已是收尾态）；并另有一例锁住「超时早于执行收尾」时的语义
   （不推进、收尾后由下一次同步补齐）。

已知遗留窗口（本文件以 `xfail(strict=True)` 显式留痕，见
`test_ac1_residual_task_finalize_with_other_settled_case`）：任务内**另有**执行已收尾的
卡死用例时，`maybe_finalize` 仍会把仍在跑轮次的任务收尾。该窗口需要「本进程正在重评
该任务（running_task_id 匹配）」才可达，且本卡建议的最小改法同样不覆盖它——故不在本卡
验收口径内，仅作为证据留给 VEGA-50 复审。

运行：python -m pytest backend/tests/test_vega52_acceptance_independent.py -q
（需本机 PostgreSQL 已启动：python start_postgres.py；本文件单独运行，避免跨文件 commit 污染）
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
from backend.services.evaluation.evaluation_result_processor import EvaluationResultProcessor
from backend.services.evaluation.endpoint_worker import EndpointWorker
from backend.services.execution.reevaluation_executor import ReevaluationExecutor

TASK_DEVICE_COUNT = 3      # 复现 VEGA-43 实测现场：3 台设备、每用例只落 1 个 TestResult
DIM_COUNT = 2
ALGORITHM_TYPE = 'voice_llm'
TIMEOUT_MESSAGE = '评估任务超时: eval_task_id=task_vega52a, 等待时间超过600秒'
REEVAL_REJECT_MESSAGE = '只有已完成/失败/停止/暂停/跳过的任务才能重新评估'


# ────────────────────────────────────────────────────────
# 夹具与构造工具
# ────────────────────────────────────────────────────────
@pytest.fixture
def wired_app(app, monkeypatch):
    """把各评估模块缓存的 app 全局指向当前测试应用（否则跨测试串用上一个 app 实例）。"""
    import backend.services.evaluation.evaluation_service as evaluation_service_module
    import backend.services.evaluation.evaluation_result_processor as processor_module
    import backend.services.evaluation.endpoint_worker as worker_module

    monkeypatch.setattr(evaluation_service_module, 'app', app, raising=False)
    monkeypatch.setattr(processor_module, 'app', app, raising=False)
    monkeypatch.setattr(worker_module, 'app', app, raising=False)
    return app


def _make_task(suffix):
    """建任务（3 台设备，type=e2e，running）。"""
    task = Task(name=f'VEGA52独立验收_{suffix}', type='e2e', status='running', total_cases=1)
    db.session.add(task)
    db.session.flush()
    for _ in range(TASK_DEVICE_COUNT):
        device = Device(
            name=f'VEGA52A设备_{suffix}_{uuid.uuid4().hex[:6]}', model='M1', type='phone',
            system='Android', system_version='14', app_name='App', app_version='1.0',
            status='online',
        )
        db.session.add(device)
        db.session.flush()
        db.session.add(TaskDevice(task_id=task.id, device_id=device.id))
    db.session.flush()
    return task


def _add_case(task, suffix, index, round_count, execution_status, evaluation_status,
              status='pending', device_id=None):
    """在任务下建一个用例：配 round_count 轮、1 个 TestResult（3 台设备 ⇒ 结果永远 1/3）。"""
    dims = []
    for dim_idx in range(DIM_COUNT):
        dim = Dimension(
            name=f'VEGA52A维度_{suffix}_{index}_{dim_idx}', type='auto', result_type=0,
            weight=1, status=True, deleted=False, statistic_method='average',
        )
        db.session.add(dim)
        db.session.flush()
        dims.append(dim)

    case_id = f'vega52a_case_{suffix}_{index}'
    round_cfg = {'evaluation': {'dimensions': [{'id': d.id} for d in dims]}}
    db.session.add(TestCase(
        id=case_id,
        name=f'VEGA-52 独立验收用例_{suffix}_{index}',
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
    ))
    result = TestResult(
        task_id=task.id,
        test_case_id=case_id,
        device_id=device_id,
        algorithm_type=ALGORITHM_TYPE,
        execution_status='completed',
        algorithm_result={'rounds': [{'reference_params': []}]},
        result_data={'multi_round': True, 'total_rounds': round_count},
    )
    db.session.add(result)
    db.session.flush()
    db.session.flush()
    return SimpleNamespace(case_id=case_id, dims=dims, result=result)


def _scenario(round_count=2, execution_status='running', evaluation_status='calculating',
              status='pending'):
    """单用例现场（含 3 台设备）。"""
    suffix = uuid.uuid4().hex[:8]
    task = _make_task(suffix)
    case = _add_case(task, suffix, 0, round_count, execution_status, evaluation_status, status)
    return SimpleNamespace(task=task, case=case, suffix=suffix)


def _add_round_dimensions(case, round_number, evaluation_status):
    """为指定轮次建出维度行（等价于该轮评估派发时 _create_dimension_results 落库）。"""
    trds = []
    for dim in case.dims:
        trd = TestResultDimension(
            test_result_id=case.result.id,
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


def _reload(task_id, case_id=None):
    db.session.expire_all()
    task = db.session.query(Task).filter_by(id=task_id).first()
    if case_id is None:
        return task
    tc = db.session.query(TaskCase).filter_by(task_id=task_id, test_case_id=case_id).first()
    return tc, task


def _set_case(task_id, case_id, **fields):
    db.session.query(TaskCase).filter_by(
        task_id=task_id, test_case_id=case_id
    ).update(fields, synchronize_session=False)
    db.session.commit()


def _arm_reevaluation(monkeypatch, task_id):
    """让 ReevaluationExecutor 认为自己正是该任务的当前重评处理者。"""
    executor = ReevaluationExecutor.get_instance()
    monkeypatch.setattr(executor, 'is_reevaluating', True)
    monkeypatch.setattr(executor, 'running_task_id', task_id)
    return executor


def _group_items(case, trds):
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
        for dim, trd in zip(case.dims, trds)
    ]


class _TimeoutApiClient:
    """打桩评估端点：提交后直接返回超时错误（等价 eval_server 600s 无响应）。"""

    def __init__(self, response):
        self.response = response
        self.requests = []

    def build_payload(self, body_template, context, **kwargs):
        return {'task_type': 'wer'}

    def make_api_request_with_fallback(self, **kwargs):
        self.requests.append(kwargs)
        return 'http://127.0.0.1:5001', self.response


def _run_timeout_worker(task_id, result_id, case_id, case, trds):
    """经真实 EndpointWorker 超时链路驱动一次评估（提交 → 超时 → 维度/用例级收尾）。"""
    api_client = _TimeoutApiClient({'__error__': TIMEOUT_MESSAGE})
    stub_service = SimpleNamespace(
        api_client=api_client,
        result_processor=EvaluationResultProcessor(),
    )
    worker = EndpointWorker(
        'http://127.0.0.1:5001', stub_service, max_timeout=1, max_concurrent=1
    )
    group_items = _group_items(case, trds)
    worker._execute_evaluation(
        task_id=task_id,
        result_id=result_id,
        test_case_id=case_id,
        algorithm_result={'rounds': [{'output': {}}]},
        representative_dim_data=group_items[0][0],
        group_items=group_items,
        algorithm_type=ALGORITHM_TYPE,
        test_type='e2e',
    )
    return api_client


def _call_reeval_entry(app, task_id, reevaluate_type='failed'):
    """直接调用官方重评入口（走真实控制器守卫）。"""
    import json as _json

    from backend.controllers.evaluation_controller import EvaluationController

    with app.test_request_context(json={
        'task_id': task_id,
        'reevaluate_type': reevaluate_type,
        'reextract_device_output': False,
    }):
        result = EvaluationController.reevaluate_task_results()

    http_code = 200
    body = result
    if isinstance(result, tuple):
        body, http_code = result[0], result[1]
    raw = body.get_data(as_text=True) if hasattr(body, 'get_data') else str(body)
    try:
        payload = _json.loads(raw)
    except (ValueError, TypeError):
        payload = raw
    return SimpleNamespace(http_code=http_code, payload=payload, raw=raw)


def _reeval_rejected(resp):
    if isinstance(resp.payload, dict):
        return resp.payload.get('success') is False
    return REEVAL_REJECT_MESSAGE in str(resp.payload)


# ════════════════════════════════════════════════════════
# 验收标准 1（D1）：多轮用例在轮次间隙不得被判定为评估结束
# ════════════════════════════════════════════════════════
@pytest.fixture
def between_rounds(wired_app):
    """D1 现场：配 2 轮，第 0 轮维度全部到终态、第 1 轮维度尚未建出；
    用例仍在执行（execution_status='running'）、用例级 calculating。"""
    scenario = _scenario(round_count=2, execution_status='running',
                         evaluation_status='calculating', status='running')
    _add_round_dimensions(scenario.case, round_number=0, evaluation_status='completed')
    return scenario


def test_ac1_criterion_false_between_rounds_and_true_only_when_execution_settled(between_rounds):
    """判据正反对照：轮次间隙（执行未收尾）⇒ False；执行收尾 ⇒ True。

    同现场双向断言，排除「判据恒真/恒假」的退化解：状态字典完全相同，唯一变量是
    执行状态，结论必须随之翻转。
    """
    sc = between_rounds
    state = _dim_state(sc.task.id, sc.case.case_id)
    assert state == {'total': DIM_COUNT, 'in_progress': 0, 'failed': 0}, (
        '前置：第 0 轮维度确实全部到终态（审计探针同款现场）'
    )

    # 审计探针口径（不带执行状态）⇒ 误判为「评估已结束」（这正是 D1）
    assert is_case_evaluation_finished('calculating', state) is True

    # 修复后口径：执行未收尾 ⇒ 轮次不完整 ⇒ 未结束
    assert is_case_evaluation_finished('calculating', state, 'running') is False
    assert is_case_evaluation_finished('calculating', state, 'queued') is False

    # 对照：执行已收尾（同一状态字典）⇒ 结束
    assert is_case_evaluation_finished('calculating', state, 'completed') is True
    assert is_case_evaluation_finished('calculating', state, 'failed') is True

    # D4 边界（有意不覆盖）：用例级停在 pending/queued/running 时不认定结束
    assert is_case_evaluation_finished('queued', state, 'completed') is False
    assert is_case_evaluation_finished('running', state, 'completed') is False


def test_ac1_sync_not_advanced_between_rounds(between_rounds):
    """轮次间隙：兜底同步不得推进用例级，且不得写入完成时间。"""
    sc = between_rounds

    advanced, new_status = sync_case_evaluation_status_from_dimensions(
        db.session, sc.task.id, sc.case.case_id
    )

    assert (advanced, new_status) == (False, None)
    tc, _ = _reload(sc.task.id, sc.case.case_id)
    assert tc.evaluation_status == 'calculating', '轮次间隙不得推进用例级评估状态'
    assert tc.status == 'running', '用例状态也不得被兜底同步改写'
    assert tc.completed_at is None, '不得写入完成时间'


def test_ac1_task_not_finalized_between_rounds(between_rounds, monkeypatch):
    """轮次间隙：任务不得被收尾（用例仍在跑轮次）。"""
    sc = between_rounds
    executor = _arm_reevaluation(monkeypatch, sc.task.id)

    assert executor.maybe_finalize(sc.task.id) is False

    tc, task = _reload(sc.task.id, sc.case.case_id)
    assert task.status == 'running', '仍在跑轮次的任务不得被提前收尾'
    assert tc.evaluation_status == 'calculating'
    assert executor.running_task_id == sc.task.id, '不得释放重评队列句柄'


@pytest.mark.xfail(
    strict=True,
    reason='VEGA-52 遗留窗口：maybe_finalize 的用例集只按「执行已收尾」过滤，'
           '任务内另有执行已收尾的卡死用例时，仍在跑轮次的用例不在集合内、'
           '无法阻止任务收尾。修复后请删除本标记。',
)
def test_ac1_residual_task_finalize_with_other_settled_case(wired_app, monkeypatch):
    """遗留窗口（非本卡验收口径，仅留痕）：任务内另有执行已收尾的卡死用例时，
    仍在跑轮次的用例阻止不了任务收尾。

    可达性：需本进程正重评该任务（`running_task_id` 匹配）；重评入口要求任务处于
    completed/failed/stopped/paused/skipped，故正常执行中不可达（paused 现场除外）。
    """
    sc = _scenario(round_count=2, execution_status='running',
                   evaluation_status='calculating', status='running')
    _add_round_dimensions(sc.case, round_number=0, evaluation_status='completed')

    # 同一任务内第二个用例：执行已收尾 + 维度全终态 + 用例级 calculating（VEGA-43 卡死形态）
    other = _add_case(sc.task, sc.suffix, 1, round_count=1, execution_status='completed',
                      evaluation_status='calculating', status='pending')
    _add_round_dimensions(other, round_number=0, evaluation_status='completed')

    executor = _arm_reevaluation(monkeypatch, sc.task.id)
    assert executor.maybe_finalize(sc.task.id) is False

    _, task = _reload(sc.task.id, sc.case.case_id)
    assert task.status == 'running', '任务内仍有用例在跑轮次时不得收尾'


# ════════════════════════════════════════════════════════
# 验收标准 2（D2）：兜底同步不得覆盖「已停止 / 已终态 / 执行失败」的用例
# ════════════════════════════════════════════════════════
def test_ac2_manual_stopped_case_untouched(wired_app):
    """人工停止用例（停止路径实际写 status='skipped' + evaluation_status='stopped'）
    经兜底同步后两个状态与完成时间都不变（审计探针实测会被改写为 completed/completed）。"""
    sc = _scenario(round_count=1, execution_status='stopped',
                   evaluation_status='stopped', status='skipped')
    _add_round_dimensions(sc.case, round_number=0, evaluation_status='completed')

    advanced, new_status = sync_case_evaluation_status_from_dimensions(
        db.session, sc.task.id, sc.case.case_id
    )

    assert (advanced, new_status) == (False, None)
    tc, _ = _reload(sc.task.id, sc.case.case_id)
    assert (tc.status, tc.evaluation_status) == ('skipped', 'stopped')
    assert tc.completed_at is None


def test_ac2_execution_failed_case_not_rolled_back(wired_app):
    """执行失败用例（execution_status/evaluation_status 均 failed）在维度恰好全
    completed 时不得被改判 completed（D2 现象三：只推进不回退）。"""
    sc = _scenario(round_count=1, execution_status='failed',
                   evaluation_status='failed', status='failed')
    _add_round_dimensions(sc.case, round_number=0, evaluation_status='completed')

    advanced, new_status = sync_case_evaluation_status_from_dimensions(
        db.session, sc.task.id, sc.case.case_id
    )

    assert (advanced, new_status) == (False, None)
    tc, _ = _reload(sc.task.id, sc.case.case_id)
    assert (tc.status, tc.evaluation_status) == ('failed', 'failed')


def test_ac2_already_completed_case_untouched(wired_app):
    """已到终态（completed）的用例即便维度里存在 failed 也不得被改判。"""
    sc = _scenario(round_count=1, execution_status='completed',
                   evaluation_status='completed', status='completed')
    _add_round_dimensions(sc.case, round_number=0, evaluation_status='failed')

    advanced, new_status = sync_case_evaluation_status_from_dimensions(
        db.session, sc.task.id, sc.case.case_id
    )

    assert (advanced, new_status) == (False, None)
    tc, _ = _reload(sc.task.id, sc.case.case_id)
    assert (tc.status, tc.evaluation_status) == ('completed', 'completed')


@pytest.mark.parametrize('stopped_status', ['skipped', 'stopped'])
def test_ac2_update_helper_excludes_stopped_and_skipped(wired_app, stopped_status):
    """D2 现象二：exclude_stopped 必须同时排除 'skipped'（停止路径实际写入值）
    与历史数据里的 'stopped'——原实现只过滤 'stopped'，保护永不生效。"""
    sc = _scenario(round_count=1, execution_status='stopped',
                   evaluation_status='stopped', status=stopped_status)

    update_count = update_task_case_status_in_db(
        db.session, sc.task.id, sc.case.case_id, 'completed', 'completed'
    )

    assert update_count == 0, f'status={stopped_status!r} 必须被排除'
    tc, _ = _reload(sc.task.id, sc.case.case_id)
    assert (tc.status, tc.evaluation_status) == (stopped_status, 'stopped')


def test_ac2_stopped_case_with_reeval_in_progress_keeps_stop_semantics(wired_app):
    """VEGA-54 交互锁（非本卡 D2 口径，仅留痕）：人工停止的用例**又被显式提交重评**时
    （evaluation_status 已被重评入口从 'stopped' 置回 calculating），兜底同步只收敛
    评估状态，status/completed_at 保留停止语义。

    与 D2 的关系：D2 的探针现场是 evaluation_status='stopped'（评估已不在进行中），
    那种现场一律不推进（见 test_ac2_manual_stopped_case_untouched）；本例是评估
    重新在算的现场，收敛的是「评估是否算完」，不改变「用例被人为停止」这一事实。
    """
    sc = _scenario(round_count=1, execution_status='stopped',
                   evaluation_status='calculating', status='skipped')
    _add_round_dimensions(sc.case, round_number=0, evaluation_status='completed')

    advanced, new_status = sync_case_evaluation_status_from_dimensions(
        db.session, sc.task.id, sc.case.case_id
    )

    assert (advanced, new_status) == (True, 'completed')
    tc, _ = _reload(sc.task.id, sc.case.case_id)
    assert tc.status == 'skipped', '停止语义必须保留（报告口径依赖它）'
    assert tc.evaluation_status == 'completed', '评估状态按维度级收敛'
    assert tc.completed_at is None, '不得把停止用例写成已完成时间'


def test_ac2_update_helper_still_updates_normal_case(wired_app):
    """反向对照：普通用例必须照常被更新（否则「保护生效」可由过滤器全挡满足）。"""
    sc = _scenario(round_count=1, execution_status='completed',
                   evaluation_status='calculating', status='pending')

    update_count = update_task_case_status_in_db(
        db.session, sc.task.id, sc.case.case_id, 'completed', 'completed'
    )

    assert update_count == 1
    tc, _ = _reload(sc.task.id, sc.case.case_id)
    assert (tc.status, tc.evaluation_status) == ('completed', 'completed')
    assert tc.completed_at is not None


# ════════════════════════════════════════════════════════
# 验收标准 3（D3）：无维度记录时不得抛 TypeError
# ════════════════════════════════════════════════════════
def test_ac3_no_dimension_rows_calculating_case(wired_app):
    """用例无任何维度记录 + 用例级 calculating：安全返回 (False, None)。"""
    sc = _scenario(round_count=1, execution_status='completed',
                   evaluation_status='calculating', status='pending')
    assert _dim_state(sc.task.id, sc.case.case_id) is None, '前置：该用例无维度记录'

    advanced, new_status = sync_case_evaluation_status_from_dimensions(
        db.session, sc.task.id, sc.case.case_id
    )

    assert (advanced, new_status) == (False, None)
    tc, _ = _reload(sc.task.id, sc.case.case_id)
    assert tc.evaluation_status == 'calculating'


def test_ac3_no_dimension_rows_terminal_case_level(wired_app):
    """无维度记录 + 用例级已是终态：同样直接返回（旧实现会走到 state['failed'] 抛
    TypeError，被调用点 try/except 吞掉，表现为兜底同步静默失败）。"""
    sc = _scenario(round_count=1, execution_status='completed',
                   evaluation_status='completed', status='completed')
    assert _dim_state(sc.task.id, sc.case.case_id) is None

    try:
        result = sync_case_evaluation_status_from_dimensions(
            db.session, sc.task.id, sc.case.case_id
        )
    except TypeError as exc:  # pragma: no cover - 失败时给出明确诊断
        pytest.fail(f'state 为 None 时不得抛 TypeError: {exc}')

    assert result == (False, None)
    tc, _ = _reload(sc.task.id, sc.case.case_id)
    assert (tc.status, tc.evaluation_status) == ('completed', 'completed')


def test_ac3_no_dimension_rows_and_stopped_case(wired_app):
    """无维度记录 + 人工停止用例：既不抛异常也不改写停止语义。"""
    sc = _scenario(round_count=1, execution_status='stopped',
                   evaluation_status='stopped', status='skipped')
    assert _dim_state(sc.task.id, sc.case.case_id) is None

    advanced, new_status = sync_case_evaluation_status_from_dimensions(
        db.session, sc.task.id, sc.case.case_id
    )

    assert (advanced, new_status) == (False, None)
    tc, _ = _reload(sc.task.id, sc.case.case_id)
    assert (tc.status, tc.evaluation_status) == ('skipped', 'stopped')


# ════════════════════════════════════════════════════════
# 验收标准 4：VEGA-43 主链路不回归（3 台设备 / 1 个 TestResult / 多轮）
# ════════════════════════════════════════════════════════
def test_ac4_multi_round_timeout_chain_end_to_end(wired_app, monkeypatch):
    """端到端：3 台设备 / 1 个 TestResult / 2 轮，第 1 轮评估已超时到终态、
    第 0 轮评估此刻超时 ⇒ 用例级随维度级到 failed、任务离开 running、
    官方重评入口（真实控制器守卫）放行。

    时序口径：评估经 `evaluation_service` 线程池异步派发，600s 超时到达时执行侧
    已由 e2e_aggregator 收尾（execution_status='completed'），故现场按此构造。
    """
    sc = _scenario(round_count=2, execution_status='completed',
                   evaluation_status='calculating', status='pending')
    round0 = _add_round_dimensions(sc.case, round_number=0, evaluation_status='pending')
    round1 = _add_round_dimensions(sc.case, round_number=1, evaluation_status='pending')
    db.session.query(TestResultDimension).filter(
        TestResultDimension.id.in_([t.id for t in round1])
    ).update({'evaluation_status': 'failed'}, synchronize_session=False)
    db.session.commit()

    executor = _arm_reevaluation(monkeypatch, sc.task.id)
    api_client = _run_timeout_worker(
        sc.task.id, sc.case.result.id, sc.case.case_id, sc.case, round0
    )
    assert api_client.requests, '应真实发起过评估请求'

    # ① 维度级与用例级一致：本组维度 failed，用例级被兜底同步推进到 failed
    tc, task = _reload(sc.task.id, sc.case.case_id)
    assert tc.evaluation_status == 'failed', '多轮用例所有轮次维度到终态后用例级必须跟上'
    assert tc.status == 'failed'

    # ② 任务离开 running，且重评队列句柄释放
    assert task.status != 'running', '任务不得永久停在 running'
    assert executor.running_task_id is None

    # ③ 官方重评入口真的放行（failed 通道可达）
    monkeypatch.setattr(executor, 'submit', lambda **kwargs: (True, 'mocked submit'))
    resp = _call_reeval_entry(wired_app, sc.task.id)
    assert not _reeval_rejected(resp), (
        f'收尾后 failed 重评通道必须可达，实际返回 {resp.raw!r}'
    )


def test_ac4_reeval_entry_rejects_still_running_task(wired_app):
    """对照：任务仍 running 时重评入口必须拒绝——证明上面的「放行」断言不是恒真。"""
    sc = _scenario(round_count=2, execution_status='running',
                   evaluation_status='calculating', status='running')
    _add_round_dimensions(sc.case, round_number=0, evaluation_status='completed')

    assert _reload(sc.task.id).status == 'running'
    resp = _call_reeval_entry(wired_app, sc.task.id)

    assert _reeval_rejected(resp)
    assert REEVAL_REJECT_MESSAGE in resp.payload.get('message', '')


def test_ac4_timeout_before_execution_settled_is_deferred_not_lost(wired_app):
    """时序边界（D1 前置的直接后果）：真实超时路径在「执行未收尾」时刻触发时，
    用例级不被推进（轮次完整性前置）；执行收尾后由下一次同步补齐到 failed。

    锁住语义：该前置只推迟兜底、不永久丢失——收尾后同一次调用链的后续同步即可收敛。
    生产时序下（异步派发 + 600s 超时）超时通常晚于执行收尾，此例为窄窗口留痕。
    """
    sc = _scenario(round_count=2, execution_status='running',
                   evaluation_status='calculating', status='running')
    trds = _add_round_dimensions(sc.case, round_number=0, evaluation_status='pending')

    # ① 超时到达时执行未收尾 ⇒ 不推进
    _run_timeout_worker(sc.task.id, sc.case.result.id, sc.case.case_id, sc.case, trds)
    tc, _ = _reload(sc.task.id, sc.case.case_id)
    assert tc.evaluation_status == 'calculating', '执行未收尾时不得推进用例级'
    assert _dim_state(sc.task.id, sc.case.case_id) == {
        'total': DIM_COUNT, 'in_progress': 0, 'failed': DIM_COUNT
    }, '维度级已被超时链路置 failed'

    # ② 执行侧收尾（e2e_aggregator 多轮成功分支：execution_status=completed / status=pending）
    _set_case(sc.task.id, sc.case.case_id, execution_status='completed', status='pending')
    advanced, new_status = sync_case_evaluation_status_from_dimensions(
        db.session, sc.task.id, sc.case.case_id
    )
    assert (advanced, new_status) == (True, 'failed'), '执行收尾后必须补齐推进'
    tc, _ = _reload(sc.task.id, sc.case.case_id)
    assert (tc.status, tc.evaluation_status) == ('failed', 'failed')
