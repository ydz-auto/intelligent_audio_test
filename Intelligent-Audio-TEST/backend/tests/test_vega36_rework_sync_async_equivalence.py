# -*- coding: utf-8 -*-
"""VEGA-36 返工复验（测试工程师独立用例）：同步前置校验 ⟺ 异步终止分支

返工交付 `6f6ea0a3` 把 `_check_generation_preconditions()` 重写成"逐条复刻异步路径"。
本文件**不复用**开发自测文件的夹具与断言，独立回答三个问题：

1. **等价性**：对 8 种任务形态逐一比对「同步前置校验的裁决」与「异步四个终止分支的裁决」，
   必须完全一致（同步失败 ⟺ 异步失败）。既验证 P1（任务级维度口径）不再漏放，
   也验证反向不误伤——同步放行的形态必须真能生成出报告。
2. **P1 非空转**：P1 形态（任务用到的维度全停用/软删、系统里还有其它启用维度）
   在返工前的同步口径下是**放行**的（旧实现判"全库是否有启用维度"），
   本条把它一并断言下来，证明新口径确实改变了裁决，而不是断言了个恒真式。
3. **P2 补口**：有 test_results、无任何 test_result_dimensions 行的形态
   （旧同步侧完全没有这条判定）现在必须明确失败。
4. **红线**：维度分支校验失败时 `regenerate` 不得软删原报告（报告生成即固化）。

说明：controller 内部会 `db.session.commit()`，造出的数据在用例结束时显式清理；
测试库按 pytest 会话物理隔离（VEGA-49，intelligent_audio_test_test_p<pid>）。
"""
import time
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


# --------------------------------------------------------------------------
# 造数 / 清理
# --------------------------------------------------------------------------

def _build_task(shape):
    """按形态造任务

    shape:
      healthy            —— test_results 有 device_id、维度启用且有得分（应放行）
      relations_only     —— 同上，另补 task_device_relations（应放行）
      no_resource        —— test_results 无 device_id/api_id、无关联表（应拦：设备/API）
      dims_disabled      —— 任务维度 status=False，另有一个无关启用维度（应拦：维度）
      dims_soft_deleted  —— 任务维度 deleted=True，另有一个无关启用维度（应拦：维度）
      no_dim_scores      —— 有 test_results、无 test_result_dimensions（应拦：维度得分）
      status_stopped     —— 任务状态 stopped（应拦：任务状态）
      results_soft_deleted —— test_results 全软删（应拦：无结果数据）
    """
    suffix = uuid.uuid4().hex[:8]
    device = Device(
        name=f'V36R设备_{suffix}', model='M1', type='phone', system='Android',
        system_version='14', app_name='App', app_version='1.0', status='online',
    )
    # 任务自己用到的维度
    dim = Dimension(
        name=f'V36R任务维度_{suffix}', type='auto', result_type=1, weight=1,
        status=True, deleted=False, statistic_method='average',
    )
    # 一个与该任务无关的启用维度：用来制造"全库有启用维度、但本任务没有"的形态，
    # 使 P1 用例自足，不依赖测试库里恰好残留的其它维度（VEGA-49 起测试库按进程全新创建）。
    other_dim = Dimension(
        name=f'V36R无关启用维度_{suffix}', type='auto', result_type=1, weight=1,
        status=True, deleted=False, statistic_method='average',
    )
    db.session.add_all([device, dim, other_dim])
    db.session.flush()

    task = Task(
        name=f'V36R任务_{suffix}', type='e2e',
        status='stopped' if shape == 'status_stopped' else 'completed',
        total_cases=1, completed_cases=1, failed_cases=0, algorithm_type='asr',
    )
    test_case = TestCase(
        id=f'v36r_case_{suffix}', name=f'V36R用例_{suffix}', config={}, test_type='e2e',
    )
    db.session.add_all([task, test_case])
    db.session.flush()

    db.session.add(TaskCase(
        task_id=task.id, test_case_id=test_case.id, status='completed',
        execution_status='completed', evaluation_status='completed', deleted=False,
    ))

    use_device = shape != 'no_resource'
    result = TestResult(
        task_id=task.id, test_case_id=test_case.id,
        device_id=device.id if use_device else None, api_id=None,
        execution_status='completed', result_data={'result_type': 'default'},
        deleted=(shape == 'results_soft_deleted'),
    )
    db.session.add(result)
    db.session.flush()

    if shape != 'no_dim_scores':
        db.session.add(TestResultDimension(
            test_result_id=result.id, dimension_id=dim.id, round_number=None,
            dimension_value=0.5, score=0.5, status='passed', evaluation_status='completed',
        ))

    if shape == 'relations_only':
        db.session.add(TaskDevice(task_id=task.id, device_id=device.id))
    if shape == 'dims_disabled':
        dim.status = False
    if shape == 'dims_soft_deleted':
        dim.deleted = True

    db.session.commit()

    return {
        'task_id': task.id, 'device_id': device.id,
        'dimension_id': dim.id, 'other_dimension_id': other_dim.id,
        'test_case_id': test_case.id, 'result_id': result.id, 'shape': shape,
    }


_REPORT_CHILD_TABLES = [
    'report_summaries', 'report_summary_meta', 'report_raw_data',
    'report_cases', 'report_metric_stats', 'report_comparison_matrix',
]


def _exec(sql, params=None):
    try:
        db.session.execute(text(sql), params or {})
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        return False


def _drain_logs():
    """等异步日志管道把队列写完再删行（否则后台批量落库会撞 logs_task_id_fkey）"""
    try:
        from backend.utils.web.log_handler import get_db_handler
        handler = get_db_handler()
    except Exception:
        return
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            if handler.queue.empty():
                break
        except Exception:
            return
        time.sleep(0.1)
    time.sleep(1.5)


def _purge(data):
    task_id = data.get('task_id')
    if not task_id:
        return
    _drain_logs()
    scope = 'SELECT id FROM test_reports WHERE task_id = :tid'
    for table in _REPORT_CHILD_TABLES:
        _exec(f'DELETE FROM {table} WHERE report_id IN ({scope})', {'tid': task_id})
    _exec('DELETE FROM test_reports WHERE task_id = :tid', {'tid': task_id})
    _exec('DELETE FROM test_result_dimensions WHERE test_result_id IN '
          '(SELECT id FROM test_results WHERE task_id = :tid)', {'tid': task_id})
    _exec('DELETE FROM test_results WHERE task_id = :tid', {'tid': task_id})
    _exec('DELETE FROM task_case_relations WHERE task_id = :tid', {'tid': task_id})
    _exec('DELETE FROM task_device_relations WHERE task_id = :tid', {'tid': task_id})
    _exec('DELETE FROM task_api_relations WHERE task_id = :tid', {'tid': task_id})
    _exec('DELETE FROM task_merge_relations WHERE merged_task_id = :tid OR source_task_id = :tid',
          {'tid': task_id})
    _exec('DELETE FROM logs WHERE task_id = :tid', {'tid': task_id})
    _exec('DELETE FROM test_cases WHERE id = :cid', {'cid': data.get('test_case_id')})
    _exec('DELETE FROM test_tasks WHERE id = :tid', {'tid': task_id})
    for key in ('dimension_id', 'other_dimension_id'):
        if data.get(key):
            _exec('DELETE FROM dimensions WHERE id = :did', {'did': data[key]})
    if data.get('device_id'):
        _exec('DELETE FROM devices WHERE id = :did', {'did': data['device_id']})


@pytest.fixture
def built():
    created = {}

    def _make(shape):
        created.clear()
        created.update(_build_task(shape))
        return created

    yield _make
    _purge(created)


@pytest.fixture
def quiet_logs(monkeypatch):
    """只记录、不落库：分支级用例不需要真日志，避免给清理添外键麻烦"""
    records = []

    def spy(level, module, content, **kwargs):
        records.append((level, module, content, kwargs.get('task_id')))

    monkeypatch.setattr(rct_module, 'log_and_emit', spy)
    return records


@pytest.fixture
def no_executor(monkeypatch):
    """屏蔽真实线程池：POST 只做同步校验，异步由用例显式同步调用"""
    monkeypatch.setattr(rct_module._report_executor, 'submit', lambda *a, **k: None)


# --------------------------------------------------------------------------
# 两侧裁决：同步前置校验 vs 异步终止分支（独立复刻，不调用被测函数）
# --------------------------------------------------------------------------

def _async_terminates(task_id):
    """独立复刻 `_generate_task_report_async` 的四个终止分支，返回 (是否终止, 原因)

    刻意**不调用** `_check_generation_preconditions`，只调用异步路径自己用的那批函数，
    这样两侧的比对才有意义。
    """
    from backend.utils.report.report_utils import ReportUtils

    task, results, error = ReportControllerTask._validate_task_and_get_results(task_id)
    if error:
        return True, 'validate'
    results = ReportUtils.filter_results_by_case_evaluation(results)
    source_task_ids = ReportControllerTask._get_source_task_ids(task)
    task_ids_for_query = source_task_ids if source_task_ids else [task_id]
    res_ids = [r.id for r in results]

    dim_results_map, dim_stats = ReportControllerTask._get_dimension_results_batch(res_ids)
    if not dim_results_map:
        return True, 'no_dim_data'

    all_dimensions_all = Dimension.query.filter_by(status=True, deleted=False)\
        .order_by(Dimension.sort_order, Dimension.id).all()
    all_dimensions = [d for d in all_dimensions_all if d.id in dim_stats] if dim_stats else all_dimensions_all
    devices_list, apis_list, _d, _a = ReportControllerTask._get_task_resources(task_ids_for_query)
    all_metrics = ReportControllerTask._build_all_metrics(all_dimensions)

    if not devices_list and not apis_list:
        return True, 'no_resource'
    if not all_metrics:
        return True, 'no_dimension'
    return False, None


def _sync_verdict(task_id):
    """同步前置校验的裁决（调用被测实现），返回 (是否拦下, message)"""
    task = db.session.get(Task, task_id)
    resp = ReportControllerTask._check_generation_preconditions(task, task_id)
    if resp is None:
        return False, None
    return True, resp[0].get_json().get('message')


def _old_sync_verdict(task_id):
    """返工前（8edd545d）的同步口径复刻：只判「设备/API 是否为空」+「全库是否有启用维度」

    用于证明 P1 形态在旧口径下会被**放行**（即新口径不是恒真式）。
    """
    task = db.session.get(Task, task_id)
    source_task_ids = ReportControllerTask._get_source_task_ids(task)
    task_ids_for_query = source_task_ids if source_task_ids else [task_id]
    devices_list, apis_list, _d, _a = ReportControllerTask._get_task_resources(task_ids_for_query)
    if not devices_list and not apis_list:
        return True, 'no_resource'
    if Dimension.query.filter_by(status=True, deleted=False).count() == 0:
        return True, 'no_dimension_global'
    return False, None


_SHAPES = [
    ('healthy', False, None),
    ('relations_only', False, None),
    ('no_resource', True, '没有关联任何设备或API'),
    ('dims_disabled', True, '没有关联任何评估维度'),
    ('dims_soft_deleted', True, '没有关联任何评估维度'),
    ('no_dim_scores', True, '未找到维度得分数据'),
    ('status_stopped', True, 'completed'),
    ('results_soft_deleted', True, '没有测试结果数据'),
]


@pytest.mark.parametrize('shape,should_reject,reason_keyword', _SHAPES,
                         ids=[s[0] for s in _SHAPES])
def test_sync_precheck_equals_async_branches(app, built, quiet_logs,
                                            shape, should_reject, reason_keyword):
    """等价性：同步前置校验的裁决必须与异步终止分支的裁决完全一致"""
    data = built(shape)
    task_id = data['task_id']

    async_rejects, async_why = _async_terminates(task_id)
    sync_rejects, sync_message = _sync_verdict(task_id)

    assert sync_rejects == async_rejects, (
        f'形态 {shape}: 同步裁决={sync_rejects}({sync_message}) 与异步裁决='
        f'{async_rejects}({async_why}) 不一致——同步失败 ⟺ 异步失败被破坏'
    )
    assert sync_rejects is should_reject, (
        f'形态 {shape}: 期望拦下={should_reject}，实际={sync_rejects}（{sync_message}）'
    )

    if should_reject:
        assert sync_message, f'形态 {shape}: 失败响应没有文案'
        assert reason_keyword in sync_message, f'形态 {shape}: 文案缺少 {reason_keyword!r}：{sync_message}'
        # 拦下 = 真的没落库
        assert Report.query.filter(Report.task_id == task_id, Report.deleted == False).count() == 0
        # 有 error 级日志、且带 task_id
        errs = [r for r in quiet_logs if r[0] == 'ERROR' and r[3] == task_id]
        assert errs, f'形态 {shape}: 没有 error 级日志'
    else:
        # 放行 = 异步真能跑完并落库（反向不误伤）
        with app.app_context():
            ReportControllerTask._generate_task_report_async(task_id, f'V36R_{shape}', None)
        assert Report.query.filter(Report.task_id == task_id, Report.deleted == False).count() == 1, \
            f'形态 {shape}: 同步放行但异步没生成出报告'
        errs = [r for r in quiet_logs if r[0] == 'ERROR' and r[3] == task_id]
        assert not errs, f'形态 {shape}: 放行形态却出现 error 日志：{errs}'


@pytest.mark.parametrize('shape', ['dims_disabled', 'dims_soft_deleted', 'no_dim_scores'])
def test_p1_p2_shapes_were_falsely_passed_before_rework(app, built, quiet_logs, shape):
    """P1/P2 非空转：这些形态在返工前的同步口径下是**放行**的，返工后必须拦下

    若旧口径本来也会拦，说明用例测不到 P1/P2 的改动点（恒真式），本条把它钉死。
    """
    data = built(shape)
    task_id = data['task_id']

    # 前提：全库确实还有其它启用维度（否则旧口径也会拦，形态就不成立）
    assert Dimension.query.filter_by(status=True, deleted=False).count() > 0, \
        '用例前提不成立：测试库里没有其它启用维度'

    old_rejects, old_why = _old_sync_verdict(task_id)
    assert old_rejects is False, (
        f'形态 {shape}: 返工前口径本来就拦下了（{old_why}），用例无法体现 P1/P2 的改动'
    )

    new_rejects, new_message = _sync_verdict(task_id)
    assert new_rejects is True, f'形态 {shape}: 返工后仍未拦下（{new_message}）'


# --------------------------------------------------------------------------
# HTTP 端到端 + 真实日志落库
# --------------------------------------------------------------------------

def _wait_for_error_log(task_id, keyword):
    row = None
    deadline = time.time() + 15
    while time.time() < deadline:
        row = db.session.execute(text(
            "SELECT level, module, content FROM logs "
            "WHERE task_id = :tid AND level = 'ERROR' AND content LIKE :kw "
            "ORDER BY id DESC LIMIT 1"
        ), {'tid': task_id, 'kw': f'%{keyword}%'}).fetchone()
        if row:
            return row
        db.session.rollback()
        time.sleep(0.3)
    return row


@pytest.mark.parametrize('shape,keyword', [
    ('dims_disabled', '没有关联任何评估维度'),
    ('dims_soft_deleted', '没有关联任何评估维度'),
    ('no_dim_scores', '未找到维度得分数据'),
])
def test_http_branch_returns_explicit_error_and_writes_db_log(app, client, built,
                                                              no_executor, shape, keyword):
    """P1/P2：HTTP 调用方拿到明确失败，且 logs 表里真的有一条 error 级记录"""
    data = built(shape)
    task_id = data['task_id']

    resp = client.post('/api/v1/reports/generate-task', json={'taskId': task_id})
    payload = resp.get_json()

    assert payload['success'] is False, f'HTTP 调用方仍拿到"成功": {payload}'
    assert payload['code'] == 203, payload
    assert keyword in payload['message'], payload
    assert resp.status_code == 400, resp.status_code
    assert 'generating' not in str(payload.get('data')), payload

    assert Report.query.filter(Report.task_id == task_id, Report.deleted == False).count() == 0

    row = _wait_for_error_log(task_id, keyword)
    assert row is not None, f'logs 表里没有 error 级 {keyword!r} 记录'
    assert row.module == 'report', row.module
    assert str(task_id) in row.content, row.content


def test_regenerate_dimension_branch_failure_keeps_old_report(app, client, built, no_executor):
    """红线：维度分支校验失败时 regenerate 不得软删原报告"""
    data = built('healthy')
    task_id = data['task_id']

    resp = client.post('/api/v1/reports/generate-task', json={'taskId': task_id})
    assert resp.get_json()['success'] is True, resp.get_json()
    with app.app_context():
        ReportControllerTask._generate_task_report_async(task_id, 'V36R原报告', None)
    report = Report.query.filter(Report.task_id == task_id, Report.deleted == False).first()
    assert report is not None
    report_id = report.id

    # 把该任务用到的维度停用（全库仍有其它启用维度）→ 该任务变成"维度不可用"
    db.session.execute(text('UPDATE dimensions SET status = FALSE WHERE id = :did'),
                       {'did': data['dimension_id']})
    db.session.commit()

    resp = client.post(f'/api/v1/reports/{report_id}/regenerate', json={})
    payload = resp.get_json()

    assert payload['success'] is False, f'regenerate 未明确失败: {payload}'
    assert payload['code'] == 203, payload
    assert '没有关联任何评估维度' in payload['message'], payload

    db.session.expire_all()
    still = Report.query.filter(Report.id == report_id).first()
    assert still is not None, '原报告被物理删除'
    assert still.deleted is False, '原报告被软删——违反"报告生成即固化"'
