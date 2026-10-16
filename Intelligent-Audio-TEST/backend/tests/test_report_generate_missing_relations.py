# -*- coding: utf-8 -*-
"""报告生成：缺设备/API 关联、维度不可用时的行为回归（VEGA-36）

背景：`_get_task_resources()` 原先只读配置侧的 task_device_relations / task_api_relations，
而"直连库注入结果"型任务只写 test_results.device_id，两张关联表一行都没有，
于是必然命中 report_controller_task 里的静默 return —— HTTP 调用方拿到成功、报告不落库、日志无记录。

本文件覆盖六条：
1. 关联表为空但 test_results 有 device_id → 回退取执行侧事实，报告能正常生成；
2. 关联表为空且 test_results 也没有 device_id/api_id → HTTP 拿到明确失败 + error 级日志（不再静默）；
3. 关联表有记录时以关联表为准（既有任务口径不变）；
4. P1：任务用到的维度全被停用/软删、但全库还有其它启用维度 → 明确失败
   （旧实现用"全库是否有启用维度"代替"该任务可见维度是否为空"，这种情况会错误放行）；
5. P2：有 test_results、但一条 test_result_dimensions 都没有 → 明确失败（旧实现无此判定，必然假成功）；
6. 反向保障：正常任务必须能通过同步前置校验（同步失败 ⟺ 异步失败，不能误伤）。

注意：controller 里的 db.session.commit() 会真正提交到独立测试库，
因此本文件用唯一后缀造数并在结束时清理，可单独运行。
"""
import uuid

import pytest
from sqlalchemy import text

from backend.models.database import db
from backend.models.models import (
    Device, Dimension, Report, Task, TaskCase, TaskDevice,
    TestCase, TestResult, TestResultDimension,
)

import backend.controllers.report_controller_task as rct_module
from backend.controllers.report_controller_task import ReportControllerTask


@pytest.fixture(autouse=True)
def _neutralize_async_log_writer(monkeypatch):
    """切断 log_handler 后台线程的写库链路（仅本文件，纯加固）

    原因：DatabaseLogHandler 的写库线程用 `sessionmaker(bind=db.engine)` 自建 Session，
    而 TestingConfig 走 StaticPool（`db.engine.connect()` 始终返回同一条物理连接），
    于是后台线程与测试线程变成"一条连接上两个 Session"，各自 commit/rollback，
    后台线程每 ~1s 冲一次批就可能把测试线程未落盘的 INSERT/UPDATE 一起回滚掉。
    本文件断言的是"生产代码有没有以 ERROR 级、带 task_id 调用 log_and_emit"，
    落库/推送由 log_handler 负责、不属于本 issue 验收范围，因此让后台线程跳过写库，
    使断言只取决于被测代码本身。

    注：本文件早期观察到的偶发失败（ObjectDeletedError、task_case_relations 外键冲突）
    经排查主因是**并行跑测试的其它 pytest 进程共用同一个测试库**
    （intelligent_audio_test_test，日志里能看到别人的任务在执行、并清掉本进程刚插入的行），
    与本夹具无关；该夹具只消除进程内的连接争用。
    """
    from backend.utils.web import log_handler as lh

    handler = lh.get_db_handler()
    monkeypatch.setattr(handler, '_process_batch', lambda *args, **kwargs: None)
    monkeypatch.setattr(handler, '_check_and_archive', lambda *args, **kwargs: None)
    yield


@pytest.fixture
def captured_logs(monkeypatch):
    """记录 log_and_emit 调用（同时透传原实现，保持真实日志写入行为）"""
    records = []
    original = rct_module.log_and_emit

    def spy(level, module, content, **kwargs):
        records.append({
            'level': level,
            'module': module,
            'content': content,
            'task_id': kwargs.get('task_id'),
        })
        return original(level, module, content, **kwargs)

    monkeypatch.setattr(rct_module, 'log_and_emit', spy)
    return records


@pytest.fixture
def scaffold(app):
    """造一个"有 test_results、无 task_device_relations/task_api_relations"的任务

    use_device_in_results=True  → test_results.device_id 指向真实设备（GPTLive 31 例那种形态）
    use_device_in_results=False → test_results 也没有 device_id/api_id（彻底无资源）
    测试结束后清理造出的数据。
    """
    suffix = uuid.uuid4().hex[:8]
    created = {}

    def build(use_device_in_results=True, with_dimension_scores=True):
        device = Device(
            name=f'VEGA36设备_{suffix}', model='M1', type='phone', system='Android',
            system_version='14', app_name='App', app_version='1.0', status='online',
        )
        dimension = Dimension(
            name=f'VEGA36维度_{suffix}', type='auto', result_type=1, weight=1,
            status=True, deleted=False, statistic_method='average',
        )
        # 一个与该任务无关的启用维度：P1 用例需要"全库还有其它启用维度"这个前提。
        # 不能依赖测试库里恰好残留的维度（VEGA-49 起测试库按 pytest 进程全新创建，
        # 库里除本用例造的行以外是空的），必须由用例自己造出来。
        extra_dimension = Dimension(
            name=f'VEGA36无关启用维度_{suffix}', type='auto', result_type=1, weight=1,
            status=True, deleted=False, statistic_method='average',
        )
        db.session.add_all([device, dimension, extra_dimension])
        db.session.flush()

        task = Task(
            name=f'VEGA36无关联任务_{suffix}', type='e2e', status='completed',
            total_cases=1, completed_cases=1, failed_cases=0, algorithm_type='asr',
        )
        test_case = TestCase(
            id=f'vega36_case_{suffix}', name=f'VEGA36用例_{suffix}',
            config={}, test_type='e2e',
        )
        db.session.add_all([task, test_case])
        db.session.flush()

        db.session.add(TaskCase(
            task_id=task.id, test_case_id=test_case.id, status='completed',
            execution_status='completed', evaluation_status='completed', deleted=False,
        ))

        result = TestResult(
            task_id=task.id, test_case_id=test_case.id,
            device_id=device.id if use_device_in_results else None,
            api_id=None, execution_status='completed',
            result_data={'result_type': 'default'}, deleted=False,
        )
        db.session.add(result)
        db.session.flush()

        if with_dimension_scores:
            db.session.add(TestResultDimension(
                test_result_id=result.id, dimension_id=dimension.id,
                round_number=None, dimension_value=0.5, score=0.5,
                status='passed', evaluation_status='completed',
            ))
        db.session.commit()

        created.update({
            'task_id': task.id, 'device_id': device.id, 'dimension_id': dimension.id,
            'extra_dimension_id': extra_dimension.id,
            'test_case_id': test_case.id, 'result_id': result.id,
        })
        return created

    yield build

    _purge(created)


def _purge(created):
    """清理造出的数据

    controller 里的 db.session.commit() 会真正提交到测试库，必须显式清理。
    按外键依赖顺序逐条执行、逐条提交，单条失败只回滚该条，
    避免一条失败导致后面全被跳过、在测试库里留下孤儿行。
    """
    task_id = created.get('task_id')
    if not task_id:
        return

    report_scope = 'SELECT id FROM test_reports WHERE task_id = :tid'
    statements = [
        (f'DELETE FROM report_summaries WHERE report_id IN ({report_scope})', {'tid': task_id}),
        (f'DELETE FROM report_summary_meta WHERE report_id IN ({report_scope})', {'tid': task_id}),
        (f'DELETE FROM report_raw_data WHERE report_id IN ({report_scope})', {'tid': task_id}),
        (f'DELETE FROM report_cases WHERE report_id IN ({report_scope})', {'tid': task_id}),
        (f'DELETE FROM report_metric_stats WHERE report_id IN ({report_scope})', {'tid': task_id}),
        (f'DELETE FROM report_comparison_matrix WHERE report_id IN ({report_scope})', {'tid': task_id}),
        ('DELETE FROM test_reports WHERE task_id = :tid', {'tid': task_id}),
        ('DELETE FROM test_result_dimensions WHERE test_result_id IN '
         '(SELECT id FROM test_results WHERE task_id = :tid)', {'tid': task_id}),
        ('DELETE FROM test_results WHERE task_id = :tid', {'tid': task_id}),
        ('DELETE FROM task_case_relations WHERE task_id = :tid', {'tid': task_id}),
        ('DELETE FROM task_device_relations WHERE task_id = :tid', {'tid': task_id}),
        ('DELETE FROM task_api_relations WHERE task_id = :tid', {'tid': task_id}),
        ('DELETE FROM task_merge_relations WHERE merged_task_id = :tid OR source_task_id = :tid', {'tid': task_id}),
        ('DELETE FROM logs WHERE task_id = :tid', {'tid': task_id}),
        ('DELETE FROM test_cases WHERE id = :cid', {'cid': created.get('test_case_id')}),
        ('DELETE FROM test_tasks WHERE id = :tid', {'tid': task_id}),
        ('DELETE FROM dimensions WHERE id = :did', {'did': created.get('dimension_id')}),
        ('DELETE FROM dimensions WHERE id = :did', {'did': created.get('extra_dimension_id')}),
        ('DELETE FROM devices WHERE id = :devid', {'devid': created.get('device_id')}),
    ]
    for sql, params in statements:
        try:
            db.session.execute(text(sql), params)
            db.session.commit()
        except Exception:
            db.session.rollback()


def _error_logs(captured_logs, task_id):
    return [
        r for r in captured_logs
        if r['level'] == 'ERROR' and r['task_id'] == task_id
        and '报告生成终止' in r['content']
    ]


def test_generate_report_falls_back_to_results_when_relations_missing(app, client, scaffold, captured_logs):
    """关联表为空、test_results 有 device_id → 回退取执行侧事实，报告正常生成

    这是 VEGA-25 的现场形态：不补 task_device_relations 也应能出报告。
    """
    data = scaffold(use_device_in_results=True)
    task_id = data['task_id']

    resp = client.post('/api/v1/reports/generate-task', json={'taskId': task_id})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['success'] is True, payload
    assert payload['data']['status'] == 'generating'

    # 同步跑完异步生成（测试里不依赖线程池调度）
    with app.app_context():
        ReportControllerTask._generate_task_report_async(task_id, None, None)

    assert not _error_logs(captured_logs, task_id), _error_logs(captured_logs, task_id)

    report = Report.query.filter(Report.task_id == task_id, Report.deleted == False).first()
    assert report is not None, '回退口径下报告应正常落库'

    # 资源取自 test_results.device_id（执行侧事实）
    devices, apis, device_ids, api_ids = ReportControllerTask._get_task_resources([task_id])
    assert device_ids == [data['device_id']]
    assert len(devices) == 1
    assert apis == [] and api_ids == []


def test_generate_report_without_any_resource_returns_explicit_error(app, client, scaffold, captured_logs):
    """彻底无资源（关联表为空 + test_results 也无 device_id/api_id）→ 明确失败，不再静默"""
    data = scaffold(use_device_in_results=False)
    task_id = data['task_id']

    resp = client.post('/api/v1/reports/generate-task', json={'taskId': task_id})
    payload = resp.get_json()

    # 1) HTTP 调用方拿到明确失败（不再是"看起来成功"）
    assert payload['success'] is False, payload
    assert payload['code'] == 203, payload
    assert '没有关联任何设备或API' in payload['message'], payload
    assert resp.status_code == 400

    # 2) 有 error 级日志，且带 task_id
    logs = _error_logs(captured_logs, task_id)
    assert logs, f'缺少 error 级日志，实际日志: {captured_logs}'
    assert str(task_id) in logs[0]['content']

    # 3) 报告没有落库
    assert Report.query.filter(Report.task_id == task_id, Report.deleted == False).count() == 0


def test_relations_take_precedence_over_results(app, scaffold, captured_logs):
    """关联表有记录时以关联表为准：既有任务（402/407 等）口径不变"""
    data = scaffold(use_device_in_results=True)
    task_id = data['task_id']

    other = Device(
        name='VEGA36仅配置侧设备', model='M2', type='phone', system='Android',
        system_version='14', app_name='App', app_version='1.0', status='online',
    )
    db.session.add(other)
    db.session.flush()
    db.session.add(TaskDevice(task_id=task_id, device_id=other.id))
    db.session.commit()

    try:
        devices, _apis, device_ids, _api_ids = ReportControllerTask._get_task_resources([task_id])
        # 只认关联表里的设备，不回退、不与 test_results 取并集
        assert device_ids == [other.id], device_ids
        assert len(devices) == 1
    finally:
        _purge_extra_device(task_id, other.id)


def _purge_extra_device(task_id, device_id):
    for sql, params in [
        ('DELETE FROM task_device_relations WHERE task_id = :tid AND device_id = :did',
         {'tid': task_id, 'did': device_id}),
        ('DELETE FROM devices WHERE id = :did', {'did': device_id}),
    ]:
        try:
            db.session.execute(text(sql), params)
            db.session.commit()
        except Exception:
            db.session.rollback()


def test_task_level_dimension_branch_returns_explicit_error(app, client, scaffold, captured_logs):
    """P1：任务用到的维度全被停用/软删、系统里还有其它启用维度 → 必须明确失败

    旧实现用「全库是否有启用维度」代替「该任务可见维度是否为空」，这种情况下会错误放行，
    异步随后静默终止 → HTTP 假成功、报告不落库。本条锁定任务级判定口径。
    """
    data = scaffold(use_device_in_results=True)
    task_id = data['task_id']

    # 只停用该任务用到的维度，保留系统里其它启用维度（制造"全库有启用维度但本任务没有"）
    Dimension.query.filter(Dimension.id == data['dimension_id']).update(
        {'status': False}, synchronize_session=False
    )
    db.session.commit()

    try:
        assert Dimension.query.filter_by(status=True, deleted=False).count() > 0, \
            '用例前提：系统里必须还有其它启用维度，否则测不到任务级判定'
        resp = client.post('/api/v1/reports/generate-task', json={'taskId': task_id})
        payload = resp.get_json()

        assert payload['success'] is False, payload
        assert payload['code'] == 203, payload
        assert '没有关联任何评估维度' in payload['message'], payload
        assert _error_logs(captured_logs, task_id), captured_logs
        assert Report.query.filter(Report.task_id == task_id, Report.deleted == False).count() == 0
    finally:
        Dimension.query.filter(Dimension.id == data['dimension_id']).update(
            {'status': True}, synchronize_session=False
        )
        db.session.commit()


def test_no_dimension_scores_returns_explicit_error(app, client, scaffold, captured_logs):
    """P2：有 test_results、但一条 test_result_dimensions 都没有 → 明确失败（不再假成功）"""
    data = scaffold(use_device_in_results=True, with_dimension_scores=False)
    task_id = data['task_id']

    resp = client.post('/api/v1/reports/generate-task', json={'taskId': task_id})
    payload = resp.get_json()

    assert payload['success'] is False, payload
    assert payload['code'] == 203, payload
    assert '未找到维度得分数据' in payload['message'], payload
    assert _error_logs(captured_logs, task_id), captured_logs
    assert Report.query.filter(Report.task_id == task_id, Report.deleted == False).count() == 0


def test_healthy_task_passes_sync_precheck(app, scaffold):
    """反向保障：正常任务必须能通过同步判定（同步失败 ⟺ 异步失败，不能误伤）"""
    data = scaffold(use_device_in_results=True)
    with app.app_context():
        task = db.session.get(Task, data['task_id'])
        assert ReportControllerTask._check_generation_preconditions(task, data['task_id']) is None
