# -*- coding: utf-8 -*-
"""临时探针（测试工程师 INT-1762 验收用，不入库，验收后删除）"""
import json
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from tests.integration.test_data_transfer_roundtrip import db, storage_env  # noqa: F401

from report_service.infrastructure.persistence.models import (  # noqa: E402
    Report, ReportCase, ReportMergeSnapshot,
)
from evaluation_service.infrastructure.persistence.models import (  # noqa: E402
    EvaluationMergeSnapshot, TestResultDimension,
)
from task_service.infrastructure.persistence.models.result_models import TestResult  # noqa: E402


def _session():
    from shared.models.database import get_db_session
    return get_db_session()


def _rows(po_cls, **filters):
    session = _session()
    try:
        query = session.query(po_cls)
        for key, value in filters.items():
            query = query.filter(getattr(po_cls, key) == value)
        return query.order_by(po_cls.__mapper__.primary_key[0].asc()).all()
    finally:
        session.close()


def _seed_report(report_id, task_id, name, visibility='shared', created_by=7):
    session = _session()
    try:
        session.add(Report(id=report_id, name=name, type='task', task_id=task_id,
                           status='published', description=f'{name}-desc',
                           analysis='old-analysis', visibility=visibility,
                           created_by_user_id=created_by))
        session.add(ReportCase(id=report_id * 100, report_id=report_id,
                               test_case_id=f'case-{report_id}', name=f'用例{report_id}'))
        session.commit()
    finally:
        session.close()


def _package(new_report_id, task_id, analysis='new-analysis'):
    return {
        'test_reports': [{'id': new_report_id, 'name': '新报告', 'type': 'task',
                          'task_id': task_id, 'status': 'published',
                          'description': 'new-desc', 'analysis': analysis,
                          'visibility': 'private', 'created_by_user_id': 999}],
        'report_cases': [{'id': new_report_id * 100, 'report_id': new_report_id,
                          'test_case_id': 'n1', 'name': '新用例'}],
    }


# ---------------- 探针 1：新建目标报告 + 回滚，父行是否残留 ----------------
def test_probe_create_then_rollback_leaves_parent(db):
    from report_service.application.report_replacement_service import (
        report_replacement_service,
    )
    res = report_replacement_service.replace_reports(
        _package(1001, 13), task_id=13, batch_id='probe-create-rb')
    assert res['success'] is True, res
    new_id = res['data']['inserted_report_ids'][0]

    rb = report_replacement_service.rollback_replacement('probe-create-rb')
    assert rb['success'] is True, rb

    leftover = _rows(Report, id=new_id)
    children = _rows(ReportCase, report_id=new_id)
    print(f'\nPROBE1 new_report_id={new_id} leftover_parent_rows={len(leftover)} '
          f'leftover_children={len(children)} snapshot_rows={len(_rows(ReportMergeSnapshot))}')
    assert leftover == [], f'回滚后新建的报告父行仍残留: {[r.id for r in leftover]}'


# ---------------- 探针 2：target_report_id 属于别的任务 ----------------
def test_probe_target_of_other_task(db):
    _seed_report(25, 99, '别人任务的报告')
    from report_service.application.report_replacement_service import (
        report_replacement_service,
    )
    res = report_replacement_service.replace_reports(
        _package(999, 12), task_id=12, target_report_id=25, batch_id='probe-wrong-target')
    print(f'\nPROBE2 success={res["success"]} data={json.dumps(res.get("data"), ensure_ascii=False)}')
    report = _rows(Report, id=25)
    print(f'PROBE2 report25 task_id={report[0].task_id if report else None} '
          f'name={report[0].name if report else None}')
    assert res['success'] is False, '跨任务 target 被接受（会替换别的任务的报告）'
    assert report[0].name == '别人任务的报告'


# ---------------- 探针 3：包内 analysis 为 None，旧 analysis 是否被清掉 ----------------
def test_probe_none_analysis_kept_stale(db):
    _seed_report(30, 12, '旧报告')
    from report_service.application.report_replacement_service import (
        report_replacement_service,
    )
    pkg = _package(999, 12, analysis=None)
    res = report_replacement_service.replace_reports(pkg, task_id=12, batch_id='probe-none')
    assert res['success'] is True, res
    report = _rows(Report, id=30)[0]
    print(f'\nPROBE3 analysis_after={report.analysis!r} name={report.name!r}')
    assert report.analysis is None, '包内 analysis=None 未覆盖，残留 A 侧旧分析'


# ---------------- 探针 4：结果存在但无维度行 ----------------
def test_probe_existing_result_without_dimensions(db):
    session = _session()
    try:
        session.add(TestResult(id=201, task_id=1, test_case_id='c-201',
                               execution_status='completed'))
        session.commit()
    except Exception as e:
        session.rollback()
        print(f'\nPROBE4 seed TestResult 失败（模型必填字段）: {e}')
        raise
    finally:
        session.close()

    from evaluation_service.application.dimension_merge_service import (
        dimension_merge_service,
    )
    res = dimension_merge_service.merge_dimensions(
        rows=[{'test_result_id': 201, 'dimension_id': 1, 'score': 5.0,
               'evaluation_status': 'completed'}],
        batch_id='probe-empty-result')
    print(f'\nPROBE4 success={res["success"]} data={json.dumps(res.get("data"), ensure_ascii=False)}')
    assert res['success'] is True, 'test_results 中存在的 result 因无维度行被拒（A2-3 口径是"存在于 A 库"）'
