# -*- coding: utf-8 -*-
"""VEGA-43 独立验收用例（测试工程师）。

与开发自测文件 `test_eval_timeout_state_machine.py` 相互独立：本文件不复用其夹具，
按卡内「验收标准」逐条独立构造现场，重点补开发自测未覆盖的三处：

1. 验收标准 2 的**端到端闭环**：超时收尾后，官方重评入口
   （`EvaluationController.reevaluate_task_results`）真的放行——直接调用控制器
   静态方法，而不是只断言「任务状态在放行名单里」；并配一条 running 任务被拒的对照；
2. 验收标准 2 的**计数证据精确化**：`reevaluate_type='failed'` 不是「有请求即可」，
   而是**请求命中的用例集合恰等于 failed 用例集合**（2 failed + 1 calculating ⇒ 恰 2 个用例）；
3. 验收标准 3 的**边界**：显式入参优先于配置、配置非法/非正数回退 600、
   函数签名里不再有魔法数字默认值。

运行：python -m pytest backend/tests/test_vega43_acceptance_independent.py -q
（需本机 PostgreSQL 已启动；本文件单独运行，避免跨文件 commit 污染）
"""
import inspect
import uuid

import pytest
from types import SimpleNamespace

from backend.config.config import Config
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
from backend.services.evaluation.api_request_handler import (
    ApiRequestHandler,
    get_evaluation_task_max_wait_time,
)
from backend.services.evaluation.evaluation_result_processor import EvaluationResultProcessor
from backend.services.evaluation.endpoint_worker import EndpointWorker
from backend.services.execution.reevaluation_executor import ReevaluationExecutor

TASK_DEVICE_COUNT = 3          # 复现实测「3 台设备 / 每用例只落 1 个 TestResult」
DIM_COUNT = 2
ALGORITHM_TYPE = 'voice_llm'
TIMEOUT_MESSAGE = '评估任务超时: eval_task_id=task_vega43x, 等待时间超过600秒'

# 官方重评入口放行的任务状态（backend/controllers/evaluation_controller.py 守卫）
REEVAL_REJECT_MESSAGE = '只有已完成/失败/停止/暂停/跳过的任务才能重新评估'
REEVAL_ALLOWED_TASK_STATUSES = ['completed', 'failed', 'stopped', 'paused', 'skipped']


# ────────────────────────────────────────────────────────
# 夹具：把各评估模块缓存的 app 全局指向当前测试应用
# ────────────────────────────────────────────────────────
@pytest.fixture
def wired_app(app, monkeypatch):
    import backend.services.evaluation.evaluation_service as evaluation_service_module
    import backend.services.evaluation.evaluation_result_processor as processor_module
    import backend.services.evaluation.endpoint_worker as worker_module

    monkeypatch.setattr(evaluation_service_module, 'app', app, raising=False)
    monkeypatch.setattr(processor_module, 'app', app, raising=False)
    monkeypatch.setattr(worker_module, 'app', app, raising=False)
    return app


def _make_case(task, device_id, suffix, index, evaluation_status='calculating', status='pending'):
    """建一个用例（含 1 个 TestResult + DIM_COUNT 个 pending 维度行）。

    只落 1 个 TestResult，而任务配 3 台设备 ⇒ 既有收尾守卫永远「已采集 1/3」，
    复现 VEGA-25 实测的卡死形态。
    """
    dims = []
    for idx in range(DIM_COUNT):
        dim = Dimension(
            name=f'VEGA43V维度_{suffix}_{index}_{idx}', type='auto', result_type=0, weight=1,
            status=True, deleted=False, statistic_method='average',
        )
        db.session.add(dim)
        db.session.flush()
        dims.append(dim)

    case_id = f'vega43v_case_{suffix}_{index}'
    db.session.add(TestCase(
        id=case_id,
        name=f'VEGA-43 独立验收用例_{suffix}_{index}',
        algorithm_type=ALGORITHM_TYPE,
        test_type='e2e',
        config={
            'rounds': [{'evaluation': {'dimensions': [{'id': d.id} for d in dims]}}],
            'dimensions': [{'id': d.id} for d in dims],
        },
    ))
    db.session.flush()

    db.session.add(TaskCase(
        task_id=task.id,
        test_case_id=case_id,
        status=status,
        execution_status='completed',
        evaluation_status=evaluation_status,
    ))

    result = TestResult(
        task_id=task.id,
        test_case_id=case_id,
        device_id=device_id,
        algorithm_type=ALGORITHM_TYPE,
        execution_status='completed',
        algorithm_result={'rounds': [{'output': {}, 'reference_params': []}]},
        result_data={'multi_round': False},
    )
    db.session.add(result)
    db.session.flush()

    trds = []
    for dim in dims:
        trd = TestResultDimension(
            test_result_id=result.id,
            dimension_id=dim.id,
            algorithm_type=ALGORITHM_TYPE,
            evaluation_status='pending',
        )
        db.session.add(trd)
        db.session.flush()
        trds.append(trd)

    db.session.flush()
    return SimpleNamespace(case_id=case_id, dims=dims, result=result, trds=trds)


@pytest.fixture
def scenario(wired_app):
    """任务（3 台设备，type=e2e）+ 1 个 calculating 用例。"""
    suffix = uuid.uuid4().hex[:8]
    task = Task(name=f'VEGA-43独立验收_{suffix}', type='e2e', status='running', total_cases=1)
    db.session.add(task)
    db.session.flush()

    device_ids = []
    for _ in range(TASK_DEVICE_COUNT):
        device = Device(
            name=f'VEGA43V设备_{suffix}_{uuid.uuid4().hex[:6]}', model='M1', type='phone',
            system='Android', system_version='14', app_name='App', app_version='1.0',
            status='online',
        )
        db.session.add(device)
        db.session.flush()
        device_ids.append(device.id)
        db.session.add(TaskDevice(task_id=task.id, device_id=device.id))
    db.session.flush()

    case = _make_case(task, device_ids[0], suffix, 0)
    return SimpleNamespace(
        task=task, case=case, suffix=suffix, device_id=device_ids[0], wired_app=wired_app
    )


def _reload_case(task_id, case_id):
    db.session.expire_all()
    tc = db.session.query(TaskCase).filter_by(task_id=task_id, test_case_id=case_id).first()
    trds = db.session.query(TestResultDimension).join(
        TestResult, TestResultDimension.test_result_id == TestResult.id
    ).filter(TestResult.task_id == task_id).all()
    return tc, trds


def _reload_task(task_id):
    db.session.expire_all()
    return db.session.query(Task).filter_by(id=task_id).first()


def _set_dims(task_id, evaluation_status):
    db.session.query(TestResultDimension).filter(
        TestResultDimension.test_result_id.in_(
            db.session.query(TestResult.id).filter(TestResult.task_id == task_id)
        )
    ).update({'evaluation_status': evaluation_status}, synchronize_session=False)
    db.session.commit()


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


# ════════════════════════════════════════════════════════
# 验收标准 3：max_wait_time 从配置读取，默认值不变（600）
# ════════════════════════════════════════════════════════
class _FakeClock:
    """假时钟：time 每次前进固定步长，sleep 不真等（否则循环空转成死循环）。"""

    def __init__(self, step=0.5):
        self.now = 0.0
        self.step = step

    def time(self):
        self.now += self.step
        return self.now

    def sleep(self, seconds):
        return None


def _stub_handler(monkeypatch, handler):
    monkeypatch.setattr(
        handler, 'get_task_status',
        lambda url, eval_task_id, timeout=120: {'code': 0, 'data': {'status': 'processing'}},
    )


def test_ac3_config_default_is_600_and_no_magic_number_in_signature(app):
    """默认值不变（600），且函数签名里不再把上限写成默认参数（红线：拒绝魔法数字）。"""
    assert Config.EVALUATION_TASK_MAX_WAIT_TIME == 600
    assert get_evaluation_task_max_wait_time() == 600

    default = inspect.signature(
        ApiRequestHandler.wait_for_task_completion
    ).parameters['max_wait_time'].default
    assert default is None, '上限必须来自配置，不能留在函数默认参数里'


def test_ac3_invalid_config_falls_back_to_600(app, monkeypatch):
    """配置非法（0 / 负数 / 非数字）时回退 600，不退化成无上限等待。"""
    for bad in (0, -5, 'abc', None):
        monkeypatch.setattr(Config, 'EVALUATION_TASK_MAX_WAIT_TIME', bad, raising=False)
        assert get_evaluation_task_max_wait_time() == 600, f'配置 {bad!r} 应回退 600'


def test_ac3_explicit_argument_overrides_config(app, monkeypatch):
    """显式入参优先于配置（调用方仍可自行指定上限）。"""
    monkeypatch.setattr(Config, 'EVALUATION_TASK_MAX_WAIT_TIME', 600)
    monkeypatch.setattr(
        'backend.services.evaluation.api_request_handler.time', _FakeClock(step=0.5)
    )

    handler = ApiRequestHandler()
    _stub_handler(monkeypatch, handler)

    resp = handler.wait_for_task_completion(
        'http://127.0.0.1:5001', 'task_vega43x', max_wait_time=3
    )
    assert resp.get('__error__') and '超过3秒' in resp['__error__']


def test_ac3_config_value_is_used_by_wait(app, monkeypatch):
    """配置改动确实作用到等待上限（不是只读了个没人用的常量）。"""
    monkeypatch.setattr(Config, 'EVALUATION_TASK_MAX_WAIT_TIME', 7)
    monkeypatch.setattr(
        'backend.services.evaluation.api_request_handler.time', _FakeClock(step=0.5)
    )

    handler = ApiRequestHandler()
    _stub_handler(monkeypatch, handler)

    resp = handler.wait_for_task_completion('http://127.0.0.1:5001', 'task_vega43x')
    assert '超过7秒' in resp.get('__error__', ''), '上限必须取自配置项'


# ════════════════════════════════════════════════════════
# 验收标准 1 + 2：超时 ⇒ 用例级与维度级一致 ⇒ 任务离开 running ⇒ 重评入口放行
# ════════════════════════════════════════════════════════
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


def _group_items(case):
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
        for dim, trd in zip(case.dims, case.trds)
    ]


def _call_reeval_entry(app, task_id, reevaluate_type='failed'):
    """直接调用官方重评入口（走真实控制器守卫）。

    Returns:
        SimpleNamespace(http_code, payload, raw)：payload 为响应体 JSON 解析结果
        （非 JSON 时退化为原始文本）。响应体把中文转义成 \\uXXXX，故断言必须看
        payload['message'] 而不是原始文本。
    """
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
    """官方重评入口是否拒绝了本次提交（error_response ⇒ success=false）。"""
    if isinstance(resp.payload, dict):
        return resp.payload.get('success') is False
    return REEVAL_REJECT_MESSAGE in str(resp.payload)


def test_ac1_ac2_timeout_chain_and_reeval_entry_unlocked(scenario, monkeypatch):
    """端到端：评估任务超时 ⇒ 维度 failed + 用例级 failed ⇒ 任务离开 running
    ⇒ 官方重评入口（控制器守卫）真的放行。"""
    task, case, app = scenario.task, scenario.case, scenario.wired_app
    executor = _arm_reevaluation(monkeypatch, task.id)

    api_client = _TimeoutApiClient({'__error__': TIMEOUT_MESSAGE})
    stub_service = SimpleNamespace(
        api_client=api_client,
        result_processor=EvaluationResultProcessor(),
    )
    worker = EndpointWorker(
        'http://127.0.0.1:5001', stub_service, max_timeout=1, max_concurrent=1
    )

    group_items = _group_items(case)
    worker._execute_evaluation(
        task_id=task.id,
        result_id=case.result.id,
        test_case_id=case.case_id,
        algorithm_result={'rounds': [{'output': {}}]},
        representative_dim_data=group_items[0][0],
        group_items=group_items,
        algorithm_type=ALGORITHM_TYPE,
        test_type='e2e',
    )

    assert api_client.requests, '应真实发起过评估请求'

    # ① 用例级与维度级一致（都是 failed）
    tc, trds = _reload_case(task.id, case.case_id)
    assert [t.evaluation_status for t in trds] == ['failed'] * DIM_COUNT
    assert tc.evaluation_status == 'failed', '超时用例的用例级必须与维度级一致'
    assert tc.status == 'failed'

    # ② 任务离开 running（不再永久卡死）
    reloaded = _reload_task(task.id)
    assert reloaded.status != 'running', '任务必须离开 running'
    assert reloaded.status in REEVAL_ALLOWED_TASK_STATUSES

    # ③ 官方重评入口真的放行（走控制器守卫，而不是只看状态名单）
    monkeypatch.setattr(executor, 'submit', lambda **kwargs: (True, 'mocked submit'))
    resp = _call_reeval_entry(app, task.id)
    assert not _reeval_rejected(resp), (
        f'超时收尾后重评入口必须放行（卡内「重评入口被锁死」的验收点），实际返回 {resp.raw!r}'
    )


def test_ac1_reeval_entry_still_rejects_running_task(scenario, monkeypatch):
    """对照：任务仍 running 时重评入口必须拒绝（证明上面的放行断言不是恒真）。"""
    task, app = scenario.task, scenario.wired_app
    assert _reload_task(task.id).status == 'running'

    resp = _call_reeval_entry(app, task.id)
    assert _reeval_rejected(resp), (
        f'running 任务必须被拒绝——否则「放行」断言无意义，实际返回 {resp.raw!r}'
    )
    assert REEVAL_REJECT_MESSAGE in resp.payload.get('message', ''), (
        '拒绝原因应仍是「只有已完成/失败/停止/暂停/跳过的任务才能重新评估」'
    )


def test_ac2_failed_channel_request_targets_exactly_the_failed_cases(scenario, monkeypatch):
    """计数证据（精确）：3 个用例（2 failed + 1 calculating）时，
    `reevaluate_type='failed'` 命中的用例集合恰为 2 个 failed 用例。"""
    from backend.services.evaluation.evaluation_service import evaluation_service

    task, base = scenario.task, scenario.case
    case_b = _make_case(
        task, scenario.device_id, scenario.suffix, 1,
        evaluation_status='failed', status='failed',
    )
    case_c = _make_case(task, scenario.device_id, scenario.suffix, 2,
                        evaluation_status='calculating')
    _set_case(task.id, base.case_id, evaluation_status='failed', status='failed')
    _set_dims(task.id, 'failed')

    submitted_cases = []
    monkeypatch.setattr(
        evaluation_service, 'evaluate_case',
        lambda **kwargs: (submitted_cases.append(kwargs.get('test_case_id')) or True),
    )
    executor = _arm_reevaluation(monkeypatch, task.id)
    executor._run_reevaluation(
        task.id, reextract_device_output=False, reevaluate_type='failed'
    )

    assert submitted_cases, 'failed 重评通道必须真的发出评估请求（不是空跑成功）'
    assert set(submitted_cases) == {base.case_id, case_b.case_id}, (
        f'请求必须精确命中 2 个 failed 用例，实际命中 {sorted(set(submitted_cases))}'
    )
    assert case_c.case_id not in submitted_cases, 'calculating 用例不在 failed 通道范围内'


def test_ac2_failed_channel_reachable_after_real_timeout(scenario, monkeypatch):
    """验收标准 2 字面口径：真的走一遍超时收尾，随后 failed 重评能提交且真的发出请求。

    与上一条的区别：上一条手工把用例级置 failed（模拟「超时路径已经推进过」的结果），
    这一条由被测代码自己把用例级推到 failed，再据此跑 failed 通道——证明两条是接上的。
    """
    from backend.services.evaluation.evaluation_service import evaluation_service

    task, case = scenario.task, scenario.case
    _arm_reevaluation(monkeypatch, task.id)

    api_client = _TimeoutApiClient({'__error__': TIMEOUT_MESSAGE})
    stub_service = SimpleNamespace(
        api_client=api_client,
        result_processor=EvaluationResultProcessor(),
    )
    worker = EndpointWorker(
        'http://127.0.0.1:5001', stub_service, max_timeout=1, max_concurrent=1
    )
    group_items = _group_items(case)
    worker._execute_evaluation(
        task_id=task.id,
        result_id=case.result.id,
        test_case_id=case.case_id,
        algorithm_result={'rounds': [{'output': {}}]},
        representative_dim_data=group_items[0][0],
        group_items=group_items,
        algorithm_type=ALGORITHM_TYPE,
        test_type='e2e',
    )

    tc, _ = _reload_case(task.id, case.case_id)
    assert tc.evaluation_status == 'failed', '前置：超时收尾把用例级推到 failed'

    submitted_cases = []
    monkeypatch.setattr(
        evaluation_service, 'evaluate_case',
        lambda **kwargs: (submitted_cases.append(kwargs.get('test_case_id')) or True),
    )
    executor = _arm_reevaluation(monkeypatch, task.id)
    executor._run_reevaluation(
        task.id, reextract_device_output=False, reevaluate_type='failed'
    )

    assert case.case_id in submitted_cases, (
        '超时收尾后 reevaluate_type=\'failed\' 必须能提交并真的发出评估请求'
    )


def test_ac2_failed_channel_is_vacuous_while_case_stuck_calculating(scenario, monkeypatch):
    """对照（缺陷原状）：用例级停在 calculating 时 failed 通道零请求（被锁死）。"""
    from backend.services.evaluation.evaluation_service import evaluation_service

    task, case = scenario.task, scenario.case
    _set_dims(task.id, 'failed')
    tc, _ = _reload_case(task.id, case.case_id)
    assert tc.evaluation_status == 'calculating'

    submitted_cases = []
    monkeypatch.setattr(
        evaluation_service, 'evaluate_case',
        lambda **kwargs: (submitted_cases.append(kwargs.get('test_case_id')) or True),
    )
    executor = _arm_reevaluation(monkeypatch, task.id)
    executor._run_reevaluation(
        task.id, reextract_device_output=False, reevaluate_type='failed'
    )

    assert submitted_cases == [], '用例级非 failed 时不得有任何评估请求'


# ════════════════════════════════════════════════════════
# 边界：不误推进 / 不误收尾
# ════════════════════════════════════════════════════════
def test_sync_advances_to_completed_on_success_path(scenario):
    """成功路径：3 台设备只落 1 个结果、维度全 completed ⇒ 用例级推进为 completed。"""
    from backend.services.evaluation.evaluation_mixin import (
        sync_case_evaluation_status_from_dimensions,
    )

    task, case = scenario.task, scenario.case
    _set_dims(task.id, 'completed')

    advanced, new_status = sync_case_evaluation_status_from_dimensions(
        db.session, task.id, case.case_id
    )
    assert (advanced, new_status) == (True, 'completed')
    tc, _ = _reload_case(task.id, case.case_id)
    assert tc.evaluation_status == 'completed'
    assert tc.completed_at is not None


def test_sync_does_not_touch_stopped_case(scenario):
    """已停止（status=skipped / evaluation_status=stopped）的用例不被兜底同步覆盖。"""
    from backend.services.evaluation.evaluation_mixin import (
        sync_case_evaluation_status_from_dimensions,
    )

    task, case = scenario.task, scenario.case
    _set_dims(task.id, 'failed')
    _set_case(task.id, case.case_id, status='skipped', evaluation_status='stopped')

    advanced, new_status = sync_case_evaluation_status_from_dimensions(
        db.session, task.id, case.case_id
    )
    assert (advanced, new_status) == (False, None)
    tc, _ = _reload_case(task.id, case.case_id)
    assert tc.status == 'skipped' and tc.evaluation_status == 'stopped'


def test_sync_does_not_advance_while_a_dimension_still_calculating(scenario):
    """真在算：仍有维度 calculating 时用例级不得被推进。"""
    from backend.services.evaluation.evaluation_mixin import (
        sync_case_evaluation_status_from_dimensions,
    )

    task, case = scenario.task, scenario.case
    db.session.query(TestResultDimension).filter_by(id=case.trds[0].id).update(
        {'evaluation_status': 'completed'}, synchronize_session=False
    )
    db.session.query(TestResultDimension).filter_by(id=case.trds[1].id).update(
        {'evaluation_status': 'calculating'}, synchronize_session=False
    )
    db.session.commit()

    advanced, new_status = sync_case_evaluation_status_from_dimensions(
        db.session, task.id, case.case_id
    )
    assert (advanced, new_status) == (False, None)
    tc, _ = _reload_case(task.id, case.case_id)
    assert tc.evaluation_status == 'calculating'


def test_maybe_finalize_keeps_running_task_running(scenario, monkeypatch):
    """真在评估中（有维度还在算）时 maybe_finalize 不得收尾，任务保持 running。"""
    task, case = scenario.task, scenario.case
    executor = _arm_reevaluation(monkeypatch, task.id)

    db.session.query(TestResultDimension).filter_by(id=case.trds[0].id).update(
        {'evaluation_status': 'completed'}, synchronize_session=False
    )
    db.session.query(TestResultDimension).filter_by(id=case.trds[1].id).update(
        {'evaluation_status': 'calculating'}, synchronize_session=False
    )
    db.session.commit()

    assert executor.maybe_finalize(task.id) is False
    assert _reload_task(task.id).status == 'running'
    tc, _ = _reload_case(task.id, case.case_id)
    assert tc.evaluation_status == 'calculating'


def test_maybe_finalize_settles_stuck_calculating_case(scenario, monkeypatch):
    """存量卡死数据（用例级停在 calculating、维度级已终态）能被兜底收尾。

    对应验收标准 5：改完之后存量卡死任务不再需要人工 stop（新路径下自动收尾）。
    """
    task, case = scenario.task, scenario.case
    executor = _arm_reevaluation(monkeypatch, task.id)
    _set_dims(task.id, 'failed')

    tc, _ = _reload_case(task.id, case.case_id)
    assert tc.evaluation_status == 'calculating', '前置：存量卡死态'

    assert executor.maybe_finalize(task.id) is True
    assert _reload_task(task.id).status == 'completed'
