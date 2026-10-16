# -*- coding: utf-8 -*-
"""评估任务超时后的状态机收尾回归测试（VEGA-43）。

缺陷链（VEGA-25 全量重评后实测）：
  1. 评估任务轮询 600s 超时 ⇒ 只把维度级置 failed；
  2. update_task_case_status 在「已采集结果数 < 期望设备/API 数」时提前 return
     （e2e 任务配 3 台设备、用例只落 1 个 TestResult ⇒ 永远 1/3），
     用例级永久停在 calculating；
  3. maybe_finalize 判据（用例级到终态）永不成立 ⇒ 任务永久 running，
     重评入口被锁死；
  4. reevaluate_type='failed' 要求用例级 == 'failed' ⇒ 补救通道同时不可达。

不跑真实 ASR / eval_server：超时路径用 stub 让评估调用直接返回超时错误，
轮询路径用假时钟（不真等 600 秒）。
"""
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

# 任务配 3 台设备（复现实测的「结果未全 1/3」守卫卡死）
TASK_DEVICE_COUNT = 3
DIM_COUNT = 2
ALGORITHM_TYPE = 'voice_llm'
TIMEOUT_MESSAGE = '评估任务超时: eval_task_id=task_fake0001, 等待时间超过600秒'


# ────────────────────────────────────────────────────────
# 夹具
# ────────────────────────────────────────────────────────
@pytest.fixture
def wired_app(app, monkeypatch):
    """把各评估模块延迟导入的 app 全局指向当前测试应用。

    evaluation_service / evaluation_result_processor 等模块各自缓存一份
    `app` 全局（get_app()），不重置会跨测试串用上一个测试的 app 实例。
    """
    import backend.services.evaluation.evaluation_service as evaluation_service_module
    import backend.services.evaluation.evaluation_result_processor as processor_module
    import backend.services.evaluation.endpoint_worker as worker_module

    monkeypatch.setattr(evaluation_service_module, 'app', app, raising=False)
    monkeypatch.setattr(processor_module, 'app', app, raising=False)
    monkeypatch.setattr(worker_module, 'app', app, raising=False)
    return app


@pytest.fixture
def timeout_scenario(wired_app):
    """构造「评估任务超时」现场：任务 3 台设备、用例只落 1 个 TestResult，
    用例级停在 calculating、维度全部 pending。"""
    suffix = uuid.uuid4().hex[:8]

    task = Task(name=f'VEGA-43 超时场景_{suffix}', type='e2e', status='running', total_cases=1)
    db.session.add(task)
    db.session.flush()

    # task_device_relations.device_id 有外键约束，必须先建真实设备
    devices = []
    for _ in range(TASK_DEVICE_COUNT):
        device = Device(
            name=f'VEGA43设备_{suffix}_{uuid.uuid4().hex[:6]}', model='M1', type='phone',
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
            name=f'VEGA43超时维度_{suffix}_{idx}', type='auto', result_type=0, weight=1,
            status=True, deleted=False, statistic_method='average',
        )
        db.session.add(dim)
        db.session.flush()
        dims.append(dim)

    case_id = f'vega43_case_{suffix}'
    test_case = TestCase(
        id=case_id,
        name=f'VEGA-43 超时用例_{suffix}',
        algorithm_type=ALGORITHM_TYPE,
        test_type='e2e',
        config={
            'rounds': [{'evaluation': {'dimensions': [{'id': d.id} for d in dims]}}],
            'dimensions': [{'id': d.id} for d in dims],
        },
    )
    db.session.add(test_case)
    db.session.flush()  # 无 relationship 声明，需显式 flush 保证先落 test_cases

    task_case = TaskCase(
        task_id=task.id,
        test_case_id=case_id,
        status='pending',
        execution_status='completed',
        evaluation_status='calculating',
    )
    db.session.add(task_case)

    result = TestResult(
        task_id=task.id,
        test_case_id=case_id,
        device_id=devices[0].id,
        algorithm_type=ALGORITHM_TYPE,
        execution_status='completed',
        algorithm_result={'rounds': [{'reference_params': []}]},
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
    return SimpleNamespace(
        task=task, case_id=case_id, dims=dims, result=result, trds=trds,
        task_case=task_case,
    )


def _reload_task_case(task_id, case_id):
    """重新查询（避开身份映射缓存），返回 (TaskCase, [TRD...])"""
    db.session.expire_all()
    tc = db.session.query(TaskCase).filter_by(
        task_id=task_id, test_case_id=case_id
    ).first()
    trds = db.session.query(TestResultDimension).join(
        TestResult, TestResultDimension.test_result_id == TestResult.id
    ).filter(TestResult.task_id == task_id).all()
    return tc, trds


def _reload_task(task_id):
    """重新查询任务。

    被测代码（maybe_finalize / update_all_dimensions_in_group_failed）在各自的
    app context 里用的是另一个 Session 实例，本测试 Session 的身份映射里可能
    留着改动前的旧对象；Query.get() 命中身份映射时不会重新 SELECT，
    必须先 expire_all 才能读到真实落库状态。
    """
    db.session.expire_all()
    return db.session.query(Task).filter_by(id=task_id).first()


def _mark_dimensions_failed(task_id):
    """把该任务所有维度置 failed（模拟超时只写维度级的既有行为）。"""
    db.session.query(TestResultDimension).filter(
        TestResultDimension.test_result_id.in_(
            db.session.query(TestResult.id).filter(TestResult.task_id == task_id)
        )
    ).update({'evaluation_status': 'failed'}, synchronize_session=False)
    db.session.commit()


def _arm_reevaluation(monkeypatch, task_id):
    """让 ReevaluationExecutor 认为自己正是该任务的当前重评处理者。"""
    executor = ReevaluationExecutor.get_instance()
    monkeypatch.setattr(executor, 'is_reevaluating', True)
    monkeypatch.setattr(executor, 'running_task_id', task_id)
    return executor


# ────────────────────────────────────────────────────────
# 1. max_wait_time 配置化（验收标准 3）
# ────────────────────────────────────────────────────────
class _FakeClock:
    """假时钟：每次取时间前进固定步长，sleep 不真等。

    否则「max_wait_time 未到」的循环在 sleep 被打桩后会空转成死循环。
    """

    def __init__(self, step=0.5):
        self.now = 0.0
        self.step = step

    def time(self):
        self.now += self.step
        return self.now

    def sleep(self, seconds):
        return None


def test_max_wait_time_default_is_600(app):
    """默认值不变：配置项缺省即 600（与改造前的函数默认参数一致）。"""
    assert Config.EVALUATION_TASK_MAX_WAIT_TIME == 600
    assert get_evaluation_task_max_wait_time() == 600


def test_wait_for_task_completion_reads_timeout_from_config(app, monkeypatch):
    """超时上限从配置读取：改配置即改等待上限，轮询到点返回超时错误。"""
    monkeypatch.setattr(Config, 'EVALUATION_TASK_MAX_WAIT_TIME', 2)
    monkeypatch.setattr(
        'backend.services.evaluation.api_request_handler.time', _FakeClock(step=0.5)
    )

    handler = ApiRequestHandler()
    polls = []
    monkeypatch.setattr(
        handler, 'get_task_status',
        lambda url, eval_task_id, timeout=120: (
            polls.append(eval_task_id) or {'code': 0, 'data': {'status': 'processing'}}
        ),
    )

    resp = handler.wait_for_task_completion('http://127.0.0.1:5001', 'task_fake0001')

    assert resp.get('__error__'), '超时路径必须返回 __error__ 让上层判失败'
    assert '评估任务超时' in resp['__error__']
    assert '超过2秒' in resp['__error__'], '超时文案里的上限必须来自配置'
    assert polls, '超时前应真实轮询过评估任务状态'


# ────────────────────────────────────────────────────────
# 2. 根因锁定：既有收尾路径被「结果数未全」守卫挡住（验收标准 1/2 的反面）
# ────────────────────────────────────────────────────────
def test_legacy_guard_leaves_case_calculating(timeout_scenario):
    """维度级已全部到终态，既有 update_task_case_status 仍把用例级留在 calculating。

    这就是「用例级永久驻留 calculating」的根因：守卫按任务设备数（3）要求结果数，
    而该用例只落了 1 个 TestResult（外部结果导入任务实测形态）。
    """
    scenario = timeout_scenario
    _mark_dimensions_failed(scenario.task.id)

    EvaluationResultProcessor().update_task_case_status(
        result_id=scenario.result.id,
        current_result_all_completed=False,
        task_id=scenario.task.id,
        test_case_id=scenario.case_id,
        test_type='e2e',
    )

    task_case, trds = _reload_task_case(scenario.task.id, scenario.case_id)
    assert [t.evaluation_status for t in trds] == ['failed'] * DIM_COUNT
    assert task_case.evaluation_status == 'calculating', (
        '前置：既有守卫确实把用例级卡在 calculating（否则本用例失去意义）'
    )


# ────────────────────────────────────────────────────────
# 3. 超时端到端：用例级与维度级一致 + 任务离开 running（验收标准 1/2）
# ────────────────────────────────────────────────────────
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


def _group_items(scenario):
    dim_data_list = []
    for dim, trd in zip(scenario.dims, scenario.trds):
        dim_data_list.append((
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
        ))
    return dim_data_list


def test_eval_timeout_advances_case_and_finalizes_task(
    timeout_scenario, monkeypatch
):
    """评估任务超时后：维度级 failed ⇒ 用例级 failed ⇒ 任务离开 running。"""
    scenario = timeout_scenario
    executor = _arm_reevaluation(monkeypatch, scenario.task.id)

    api_client = _StubApiClient({'__error__': TIMEOUT_MESSAGE})
    stub_service = SimpleNamespace(
        api_client=api_client,
        result_processor=EvaluationResultProcessor(),
    )
    worker = EndpointWorker('http://127.0.0.1:5001', stub_service, max_timeout=1, max_concurrent=1)

    group_items = _group_items(scenario)
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

    task_case, trds = _reload_task_case(scenario.task.id, scenario.case_id)
    assert [t.evaluation_status for t in trds] == ['failed'] * DIM_COUNT
    assert task_case.evaluation_status == 'failed', (
        '超时用例的用例级必须与维度级一致（都是 failed）'
    )
    assert task_case.status == 'failed'

    task = _reload_task(scenario.task.id)
    assert task.status == 'completed', '任务必须离开 running，不再永久卡死'

    # 队列状态已释放（maybe_finalize 收尾后不再占用重评通道）
    assert executor.running_task_id is None


# ────────────────────────────────────────────────────────
# 4. maybe_finalize 兜底：用例级仍卡 calculating 也能收尾（验收标准 1）
# ────────────────────────────────────────────────────────
def test_maybe_finalize_fallback_on_stuck_calculating(timeout_scenario, monkeypatch):
    """存量卡死数据（用例级停在 calculating、维度级已终态）也能被收尾。

    对应「改完之后是否仍需人工 stop」：不需要——兜底判据按维度级认定评估已结束。
    """
    scenario = timeout_scenario
    executor = _arm_reevaluation(monkeypatch, scenario.task.id)

    # 只把维度级收尾，用例级故意留在 calculating（模拟本次修复前的存量数据）
    _mark_dimensions_failed(scenario.task.id)

    task_case, _ = _reload_task_case(scenario.task.id, scenario.case_id)
    assert task_case.evaluation_status == 'calculating'

    assert executor.maybe_finalize(scenario.task.id) is True

    task = _reload_task(scenario.task.id)
    assert task.status == 'completed'


def test_maybe_finalize_does_not_finalize_running_evaluation(
    timeout_scenario, monkeypatch
):
    """反向保护：仍有维度在算（真在评估中）时不得收尾。"""
    scenario = timeout_scenario
    executor = _arm_reevaluation(monkeypatch, scenario.task.id)

    # 一个维度到终态、另一个仍在 calculating ⇒ 评估确实没结束
    db.session.query(TestResultDimension).filter_by(id=scenario.trds[0].id).update(
        {'evaluation_status': 'completed'}, synchronize_session=False
    )
    db.session.query(TestResultDimension).filter_by(id=scenario.trds[1].id).update(
        {'evaluation_status': 'calculating'}, synchronize_session=False
    )
    db.session.commit()

    assert executor.maybe_finalize(scenario.task.id) is False

    task = _reload_task(scenario.task.id)
    assert task.status == 'running', '真在算的任务不能被误收尾'

    task_case, _ = _reload_task_case(scenario.task.id, scenario.case_id)
    assert task_case.evaluation_status == 'calculating', '用例级也不该被提前推进'


def test_case_status_advanced_to_completed_when_dims_all_completed(timeout_scenario):
    """成功路径同理：维度全部 completed、用例级卡 calculating 时同步推进为 completed。

    实测里这条路径同样会被「结果未全 1/3」守卫挡住（19:16:07 的 f3350f1d 用例），
    与超时路径是同一条缺陷链，只是维度级终态是 completed 而不是 failed。
    """
    from backend.services.evaluation.evaluation_mixin import (
        sync_case_evaluation_status_from_dimensions,
    )

    scenario = timeout_scenario
    db.session.query(TestResultDimension).filter(
        TestResultDimension.test_result_id == scenario.result.id
    ).update({'evaluation_status': 'completed'}, synchronize_session=False)
    db.session.commit()

    advanced, new_status = sync_case_evaluation_status_from_dimensions(
        db.session, scenario.task.id, scenario.case_id
    )

    assert (advanced, new_status) == (True, 'completed')
    task_case, _ = _reload_task_case(scenario.task.id, scenario.case_id)
    assert task_case.evaluation_status == 'completed'
    assert task_case.status == 'completed'
    assert task_case.completed_at is not None


def test_case_status_not_advanced_when_evaluation_pending(timeout_scenario):
    """反向保护：用例级还没提交到 eval_server（queued/running）时不凭现有维度推进。

    否则会把「该轮维度还没建出来」的窗口误判成评估已结束。
    """
    from backend.services.evaluation.evaluation_mixin import (
        sync_case_evaluation_status_from_dimensions,
    )

    scenario = timeout_scenario
    _mark_dimensions_failed(scenario.task.id)  # 现有维度全部到终态
    db.session.query(TaskCase).filter_by(
        task_id=scenario.task.id, test_case_id=scenario.case_id
    ).update({'evaluation_status': 'queued'}, synchronize_session=False)
    db.session.commit()

    advanced, new_status = sync_case_evaluation_status_from_dimensions(
        db.session, scenario.task.id, scenario.case_id
    )

    assert advanced is False and new_status is None
    task_case, _ = _reload_task_case(scenario.task.id, scenario.case_id)
    assert task_case.evaluation_status == 'queued'


# ────────────────────────────────────────────────────────
# 5. failed 重评通道可达且真的发出请求（验收标准 2）
# ────────────────────────────────────────────────────────
def _run_failed_reevaluation(monkeypatch, task_id):
    """跑一次 reevaluate_type='failed' 提交，返回 evaluate_case 的调用记录。"""
    from backend.services.evaluation.evaluation_service import evaluation_service

    calls = []
    monkeypatch.setattr(
        evaluation_service, 'evaluate_case',
        lambda **kwargs: (calls.append(kwargs) or True),
    )
    executor = _arm_reevaluation(monkeypatch, task_id)
    executor._run_reevaluation(task_id, reextract_device_output=False, reevaluate_type='failed')
    return calls


def test_reevaluate_failed_channel_reachable_after_timeout(
    timeout_scenario, monkeypatch
):
    """超时把用例级推进到 failed 后，reevaluate_type='failed' 能真正发出评估请求。"""
    scenario = timeout_scenario
    _mark_dimensions_failed(scenario.task.id)
    db.session.query(TaskCase).filter_by(
        task_id=scenario.task.id, test_case_id=scenario.case_id
    ).update(
        {'evaluation_status': 'failed', 'status': 'failed'}, synchronize_session=False
    )
    db.session.commit()

    calls = _run_failed_reevaluation(monkeypatch, scenario.task.id)

    assert calls, (
        "reevaluate_type='failed' 必须真的发出评估请求，"
        '而不是空跑一次却报告成功（超时后用例级= failed 才让它可达）'
    )


def test_reevaluate_failed_channel_locked_while_case_calculating(
    timeout_scenario, monkeypatch
):
    """对照：用例级停在 calculating（修复前的卡死态）时，failed 通道是空跑的。"""
    scenario = timeout_scenario
    _mark_dimensions_failed(scenario.task.id)
    task_case, _ = _reload_task_case(scenario.task.id, scenario.case_id)
    assert task_case.evaluation_status == 'calculating'

    calls = _run_failed_reevaluation(monkeypatch, scenario.task.id)

    assert calls == [], '用例级非 failed 时不该有任何评估请求（正是被锁死的通道）'
