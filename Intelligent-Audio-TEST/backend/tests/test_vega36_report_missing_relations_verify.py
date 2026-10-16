# -*- coding: utf-8 -*-
"""VEGA-36 独立验收（测试工程师）：报告生成缺设备/API 关联时的静默问题

本文件**不复用**开发自测文件（test_report_generate_missing_relations.py）的夹具与断言，
用于独立复核以下验收标准：

1. 无资源任务 → HTTP 调用方拿到明确错误码与文案（不再"看起来成功"）；
2. 采用回退方案时，回退口径生成的报告内容必须与"补过关联表"的版本**逐字段一致**
   （需求规划师明确要求这条必须验，开发自测只断言了"报告非空"）；
3. `regenerate` 在无资源任务上明确失败，且**不软删**原报告（红线：报告生成即固化）；
4. 关联表有记录时以关联表为准，**不与 test_results 取并集**（既有任务口径不变）；
5. 多设备时回退口径取到的资源集合与关联表口径一致（set 语义，不看顺序）。

说明：controller 内部会 db.session.commit()，造出的数据需显式清理；
本文件按测试库物理隔离（intelligent_audio_test_test）运行，可单独执行。
"""
import json
import time
import uuid

import pytest
from sqlalchemy import text

from backend.models.database import db
from backend.models.models import (
    Device,
    Dimension,
    Report,
    ReportCase,
    ReportMetricStats,
    ReportRawData,
    ReportSummary,
    ReportSummaryMeta,
    Task,
    TaskCase,
    TaskDevice,
    TestCase,
    TestResult,
    TestResultDimension,
)
import backend.controllers.report_controller_task as rct_module
from backend.controllers.report_controller_task import ReportControllerTask


# --------------------------------------------------------------------------
# 造数 / 清理
# --------------------------------------------------------------------------

def _build_task(device_count=1, api_count=0):
    """造一个"有 test_results、无 task_device_relations/task_api_relations"的任务

    device_count=0 且 api_count=0 → test_results 也没有 device_id/api_id（彻底无资源）。
    """
    suffix = uuid.uuid4().hex[:8]
    devices = [
        Device(
            name=f'V36V设备{i}_{suffix}', model='M1', type='phone', system='Android',
            system_version='14', app_name='App', app_version='1.0', status='online',
        )
        for i in range(device_count)
    ]
    dimension = Dimension(
        name=f'V36V维度_{suffix}', type='auto', result_type=1, weight=1,
        status=True, deleted=False, statistic_method='average',
    )
    db.session.add_all(devices + [dimension])
    db.session.flush()

    task = Task(
        name=f'V36V任务_{suffix}', type='e2e', status='completed',
        total_cases=1, completed_cases=1, failed_cases=0, algorithm_type='asr',
    )
    test_case = TestCase(
        id=f'v36v_case_{suffix}', name=f'V36V用例_{suffix}', config={}, test_type='e2e',
    )
    db.session.add_all([task, test_case])
    db.session.flush()

    db.session.add(TaskCase(
        task_id=task.id, test_case_id=test_case.id, status='completed',
        execution_status='completed', evaluation_status='completed', deleted=False,
    ))

    results = []
    if devices:
        for dev in devices:
            results.append(TestResult(
                task_id=task.id, test_case_id=test_case.id, device_id=dev.id, api_id=None,
                execution_status='completed', result_data={'result_type': 'default'},
                deleted=False,
            ))
    else:
        results.append(TestResult(
            task_id=task.id, test_case_id=test_case.id, device_id=None, api_id=None,
            execution_status='completed', result_data={'result_type': 'default'},
            deleted=False,
        ))
    db.session.add_all(results)
    db.session.flush()

    for res in results:
        db.session.add(TestResultDimension(
            test_result_id=res.id, dimension_id=dimension.id, round_number=None,
            dimension_value=0.5, score=0.5, status='passed', evaluation_status='completed',
        ))
    db.session.commit()

    return {
        'task_id': task.id,
        'device_ids': [d.id for d in devices],
        'dimension_id': dimension.id,
        'test_case_id': test_case.id,
        'result_ids': [r.id for r in results],
    }


_REPORT_CHILD_TABLES = [
    'report_summaries',
    'report_summary_meta',
    'report_raw_data',
    'report_cases',
    'report_metric_stats',
    'report_comparison_matrix',
]


def _exec(sql, params=None):
    """单条语句独立提交；失败只回滚该条，不牵连后续清理"""
    try:
        db.session.execute(text(sql), params or {})
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        return False


def _drop_reports(task_id):
    scope = 'SELECT id FROM test_reports WHERE task_id = :tid'
    for table in _REPORT_CHILD_TABLES:
        _exec(f'DELETE FROM {table} WHERE report_id IN ({scope})', {'tid': task_id})
    _exec('DELETE FROM test_reports WHERE task_id = :tid', {'tid': task_id})


def _drain_logs():
    """等异步日志管道把队列写完再删行

    log_handler 是队列 + 后台线程批量落库（batch_timeout=1.0s）。若在日志还没写完时
    就删掉 test_tasks 行，后台线程随后插入 logs 会撞 logs_task_id_fkey 外键，
    并且该失败会污染当前测试共用的那条连接（StaticPool），殃及后续断言。
    """
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
    time.sleep(1.5)  # 跨过一次 batch_timeout，确保批次已落库


def _purge(data):
    """清理造出的数据（外键依赖倒序）"""
    task_id = data.get('task_id')
    if not task_id:
        return
    _drain_logs()
    _drop_reports(task_id)
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
    _exec('DELETE FROM dimensions WHERE id = :did', {'did': data.get('dimension_id')})
    for dev_id in data.get('device_ids') or []:
        _exec('DELETE FROM devices WHERE id = :did', {'did': dev_id})


@pytest.fixture
def no_executor(monkeypatch):
    """屏蔽真实线程池：POST 只做同步校验，异步生成由测试显式同步调用，避免竞态"""
    monkeypatch.setattr(
        rct_module._report_executor, 'submit', lambda *a, **k: None
    )


@pytest.fixture
def built():
    """造数 + 收尾清理"""
    created = {}

    def _make(**kwargs):
        created.clear()
        created.update(_build_task(**kwargs))
        return created

    yield _make
    _purge(created)


# --------------------------------------------------------------------------
# 报告内容快照（用于 A/B 逐字段比对）
# --------------------------------------------------------------------------

def _json_norm(value):
    """归一化 JSON 列

    本项目的 *_meta / raw_data / metric_stats 列是 Column(JSON)，但写入时又做了一次
    json.dumps（见 _create_report_summary / _create_report_detail_data），
    读回来是"字符串里套 JSON"。这里统一解成 Python 对象再比对，避免拿编码差异当内容差异。
    """
    for _ in range(3):
        if not isinstance(value, str):
            break
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            break
    return value


def _snapshot(report_id):
    """抓取报告落库内容，剔除 id / 名称 / 时间戳等易变字段"""
    summary = ReportSummary.query.filter_by(report_id=report_id).first()
    meta = ReportSummaryMeta.query.filter_by(report_id=report_id).first()
    raw = ReportRawData.query.filter_by(report_id=report_id).first()
    stats = ReportMetricStats.query.filter_by(report_id=report_id).first()
    cases = ReportCase.query.filter_by(report_id=report_id).order_by(ReportCase.id).all()

    assert summary is not None, f'report {report_id} 缺少 report_summaries'
    assert meta is not None, f'report {report_id} 缺少 report_summary_meta'
    assert raw is not None, f'report {report_id} 缺少 report_raw_data'

    return {
        'summary': {
            'total_cases': summary.total_cases,
            'completed_cases': summary.completed_cases,
            'failed_cases': summary.failed_cases,
            'pass_rate': summary.pass_rate,
            'duration': summary.duration,
            'started_at': str(summary.started_at),
            'completed_at': str(summary.completed_at),
        },
        'meta': {
            'dimension_values': _json_norm(meta.dimension_values),
            'case_categories': _json_norm(meta.case_categories),
            'all_case_tags': _json_norm(meta.all_case_tags),
            'devices': _json_norm(meta.devices),
            'apis': _json_norm(meta.apis),
            'resources': _json_norm(meta.resources),
            'resource_headers': _json_norm(meta.resource_headers),
            'all_metrics': _json_norm(meta.all_metrics),
            'field_mappings': _json_norm(meta.field_mappings),
        },
        'raw_data': _json_norm(raw.raw_data),
        'metric_stats': {
            'metric_data': _json_norm(stats.metric_data) if stats else None,
            'tag_metric_data': _json_norm(stats.tag_metric_data) if stats else None,
            'case_type_stats': _json_norm(stats.case_type_stats) if stats else None,
            'device_stats': _json_norm(stats.device_stats) if stats else None,
            'api_stats': _json_norm(stats.api_stats) if stats else None,
        },
        'cases': [
            {
                'test_case_id': c.test_case_id, 'name': c.name, 'category': c.category,
                'tags': _json_norm(c.tags), 'metrics': _json_norm(c.metrics),
                'results': _json_norm(c.results),
            }
            for c in cases
        ],
    }


def _diff(a, b, path=''):
    """返回两份快照的差异路径列表"""
    diffs = []
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b)):
            diffs.extend(_diff(a.get(key), b.get(key), f'{path}.{key}'))
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            diffs.append(f'{path}: 长度 {len(a)} vs {len(b)}')
        else:
            for i, (x, y) in enumerate(zip(a, b)):
                diffs.extend(_diff(x, y, f'{path}[{i}]'))
    elif a != b:
        diffs.append(f'{path}: {a!r} != {b!r}')
    return diffs


# --------------------------------------------------------------------------
# 用例
# --------------------------------------------------------------------------

def test_no_resource_returns_explicit_error_not_fake_success(app, client, built, no_executor):
    """验收标准 1：彻底无资源时 HTTP 拿到明确失败，而不是 'success=true/generating'

    这是 VEGA-25 现场"看起来成功"的直接回归。
    """
    data = built(device_count=0)
    task_id = data['task_id']

    resp = client.post('/api/v1/reports/generate-task', json={'taskId': task_id})
    payload = resp.get_json()

    assert payload['success'] is False, f'HTTP 调用方仍拿到"成功": {payload}'
    assert payload['code'] == 203, payload
    assert '没有关联任何设备或API' in payload['message'], payload
    assert resp.status_code == 400, resp.status_code
    assert 'generating' not in str(payload.get('data')), payload

    # 报告确实没有落库（失败是真实的，不是"生成了但没告诉你"）
    assert Report.query.filter(Report.task_id == task_id, Report.deleted == False).count() == 0


def test_error_level_log_is_written_to_db(app, client, built, no_executor):
    """验收标准 1（日志侧）：error 级日志必须真的落进 logs 表

    开发自测用 monkeypatch 拦截 log_and_emit，只证明"函数被调用"；
    这里走真实的异步日志管道，轮询 logs 表确认落库。
    """
    data = built(device_count=0)
    task_id = data['task_id']

    resp = client.post('/api/v1/reports/generate-task', json={'taskId': task_id})
    assert resp.get_json()['success'] is False

    row = None
    deadline = time.time() + 15
    while time.time() < deadline:
        row = db.session.execute(text(
            "SELECT id, level, module, content FROM logs "
            "WHERE task_id = :tid AND level = 'ERROR' AND content LIKE '%报告生成终止%' "
            "ORDER BY id DESC LIMIT 1"
        ), {'tid': task_id}).fetchone()
        if row:
            break
        db.session.rollback()
        time.sleep(0.3)

    assert row is not None, 'logs 表里没有 error 级"报告生成终止"记录'
    assert str(task_id) in row.content, row.content
    assert row.module == 'report', row.module


@pytest.mark.parametrize('device_count', [1, 3])
def test_fallback_report_content_equals_relations_report(app, client, built, no_executor, device_count):
    """验收标准 2：回退口径与"补过关联表"口径生成的报告内容逐字段一致

    A：关联表为空 → 走 test_results 回退；
    B：补 task_device_relations → 走配置侧口径。
    两份报告落库内容必须一致（除 id/名称/时间戳）。
    多设备（3 台）跑一遍是为了顺带验证 device_ids 的 set 无序性不会渗进报告内容。
    """
    data = built(device_count=device_count)
    task_id = data['task_id']
    expected_device_ids = set(data['device_ids'])

    # --- A：回退路径 ---
    resp = client.post('/api/v1/reports/generate-task', json={'taskId': task_id})
    assert resp.get_json()['success'] is True, resp.get_json()
    with app.app_context():
        ReportControllerTask._generate_task_report_async(task_id, 'A_回退', None)
    report_a = Report.query.filter(Report.task_id == task_id, Report.deleted == False).first()
    assert report_a is not None, '回退口径下报告未落库'
    snap_a = _snapshot(report_a.id)
    # 回退确实生效：资源取自 test_results.device_id
    assert snap_a['meta']['devices'], '报告里没有设备资源'
    assert {d['id'] for d in snap_a['meta']['devices']} == expected_device_ids, \
        snap_a['meta']['devices']

    # --- 清掉 A 的报告，补关联表 ---
    _drop_reports(task_id)
    assert Report.query.filter(Report.task_id == task_id, Report.deleted == False).count() == 0
    for dev_id in data['device_ids']:
        db.session.add(TaskDevice(task_id=task_id, device_id=dev_id))
    db.session.commit()

    # --- B：关联表路径 ---
    resp = client.post('/api/v1/reports/generate-task', json={'taskId': task_id})
    assert resp.get_json()['success'] is True, resp.get_json()
    with app.app_context():
        ReportControllerTask._generate_task_report_async(task_id, 'B_关联表', None)
    report_b = Report.query.filter(Report.task_id == task_id, Report.deleted == False).first()
    assert report_b is not None, '关联表口径下报告未落库'
    snap_b = _snapshot(report_b.id)

    diffs = _diff(snap_a, snap_b)
    assert not diffs, '回退口径与关联表口径的报告内容不一致:\n' + '\n'.join(diffs[:20])


def test_regenerate_failure_does_not_soft_delete_old_report(app, client, built, no_executor):
    """红线：regenerate 前置校验失败时不得软删原报告（报告生成即固化）"""
    data = built(device_count=1)
    task_id = data['task_id']

    # 先正常生成一份报告
    resp = client.post('/api/v1/reports/generate-task', json={'taskId': task_id})
    assert resp.get_json()['success'] is True, resp.get_json()
    with app.app_context():
        ReportControllerTask._generate_task_report_async(task_id, '原报告', None)
    report = Report.query.filter(Report.task_id == task_id, Report.deleted == False).first()
    assert report is not None
    report_id = report.id

    # 抹掉执行侧资源 → 该任务变成"无资源"
    db.session.execute(text('UPDATE test_results SET device_id = NULL WHERE task_id = :tid'),
                       {'tid': task_id})
    db.session.commit()

    resp = client.post(f'/api/v1/reports/{report_id}/regenerate', json={})
    payload = resp.get_json()

    assert payload['success'] is False, f'regenerate 未明确失败: {payload}'
    assert payload['code'] == 203, payload

    db.session.expire_all()
    still = Report.query.filter(Report.id == report_id).first()
    assert still is not None, '原报告被物理删除'
    assert still.deleted is False, '原报告被软删——违反"报告生成即固化"'


def test_relations_take_precedence_no_union(app, built):
    """验收标准 3：关联表有记录时只认关联表，不与 test_results 取并集"""
    data = built(device_count=2)
    task_id = data['task_id']
    configured = data['device_ids'][0]

    db.session.add(TaskDevice(task_id=task_id, device_id=configured))
    db.session.commit()

    _devices, _apis, device_ids, api_ids = ReportControllerTask._get_task_resources([task_id])
    assert device_ids == [configured], (
        f'关联表有记录时口径被污染：期望 [{configured}]，实际 {device_ids}'
    )
    assert api_ids == []


def test_fallback_resource_set_matches_relations(app, built):
    """多设备时：回退口径取到的资源集合 == 关联表口径（set 语义，不看顺序）"""
    data = built(device_count=3)
    task_id = data['task_id']
    expected = set(data['device_ids'])

    _d, _a, fallback_ids, _ai = ReportControllerTask._get_task_resources([task_id])
    assert set(fallback_ids) == expected, fallback_ids

    for dev_id in data['device_ids']:
        db.session.add(TaskDevice(task_id=task_id, device_id=dev_id))
    db.session.commit()

    _d, _a, relation_ids, _ai = ReportControllerTask._get_task_resources([task_id])
    assert set(relation_ids) == expected, relation_ids


def test_soft_deleted_results_not_used_by_fallback(app, built):
    """回退只认未删除的执行记录：软删掉的 test_results 不应把资源带进报告"""
    data = built(device_count=1)
    task_id = data['task_id']

    db.session.execute(text('UPDATE test_results SET deleted = TRUE WHERE task_id = :tid'),
                       {'tid': task_id})
    db.session.commit()

    _devices, _apis, device_ids, api_ids = ReportControllerTask._get_task_resources([task_id])
    assert device_ids == [], f'软删的 test_results 仍被回退采用: {device_ids}'
    assert api_ids == []
