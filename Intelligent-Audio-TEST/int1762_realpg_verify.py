# -*- coding: utf-8 -*-
"""INT-1762 D4 真实 PG 隔离库验收脚本（测试工程师临时工具，不入库）

用法（DATABASE_URL 指向隔离库 int1762_tst_verify）：
    python int1762_realpg_verify.py seed
    python int1762_realpg_verify.py replace
    python int1762_realpg_verify.py rb-report
    python int1762_realpg_verify.py merge
    python int1762_realpg_verify.py rb-dim
"""
import json
import os
import sys
from datetime import datetime

os.environ.setdefault(
    'DATABASE_URL',
    'postgresql://intelligent_audio_test:intelligent_audio_test666'
    '@localhost:15432/int1762_tst_verify')
os.environ.setdefault('OSS_ACCESS_KEY', 'dummy')
os.environ.setdefault('OSS_SECRET_KEY', 'dummy')
os.environ.setdefault('OSS_BUCKET_NAME', 'intelligent-audio-test')
os.environ.setdefault('OSS_KEY_PREFIX', 'intelligent_audio_test')

TASK_ID = 20001
HIST_REPORT = 5000
LATEST_REPORT = 5001


def _session():
    from shared.models.database import init_db
    init_db()
    from shared.models.database import get_db_session
    return get_db_session()


def seed():
    from report_service.infrastructure.persistence.models import (
        BenchmarkRanking, BenchmarkReport, Report, ReportCase,
        ReportComparisonMatrix, ReportFavorite, ReportMetricStats,
        ReportRawData, ReportShare, ReportStudioChartSpec,
        ReportStudioDocument, ReportSummary, ReportSummaryMeta,
    )
    from evaluation_service.infrastructure.persistence.models import (
        TestResultDimension,
    )
    from task_service.infrastructure.persistence.models.result_models import (
        TestResult,
    )

    session = _session()
    try:
        # ---- 任务与结果（结果行存在，供 A2-3 存在性口径） ----
        from task_service.infrastructure.persistence.models.task_models import Task
        session.add(Task(id=TASK_ID, name='INT1762验收任务', status='completed',
                         algorithm_type='api'))
        session.add_all([
            TestResult(id=101, task_id=TASK_ID, test_case_id='case-101',
                       execution_status='completed'),
            TestResult(id=102, task_id=TASK_ID, test_case_id='case-102',
                       execution_status='completed'),
        ])

        # ---- 维度评分：101 dim1 两轮 + dim2；102 dim1 ----
        session.add_all([
            TestResultDimension(id=801, test_result_id=101, dimension_id=1,
                                round_number=0, score=10.0, status='failed',
                                evaluation_status='completed',
                                created_at=datetime(2026, 10, 1, 9, 0, 0, 123456)),
            TestResultDimension(id=802, test_result_id=101, dimension_id=1,
                                round_number=1, score=11.0, status='failed',
                                evaluation_status='completed',
                                created_at=datetime(2026, 10, 1, 9, 0, 1, 654321)),
            TestResultDimension(id=803, test_result_id=101, dimension_id=2,
                                round_number=None, score=20.0, status='passed',
                                evaluation_status='completed'),
            TestResultDimension(id=804, test_result_id=102, dimension_id=1,
                                round_number=None, score=30.0, status='passed',
                                evaluation_status='completed'),
        ])

        # ---- 两份报告：5000 历史、5001 最新（private / owner=7） ----
        for rid, name, visibility, owner, cases in (
                (HIST_REPORT, 'A侧历史报告', 'shared', 8, 1),
                (LATEST_REPORT, 'A侧旧报告', 'private', 7, 2)):
            session.add(Report(id=rid, name=name, type='task', task_id=TASK_ID,
                               status='published', description=f'{name}-desc',
                               analysis='A侧旧分析', visibility=visibility,
                               created_by_user_id=owner,
                               created_at=datetime(2026, 10, 2, 9, 0, 0, 111111)))
            session.add(ReportSummary(id=rid * 10 + 1, report_id=rid,
                                      total_cases=cases, pass_rate=0.5))
            session.add(ReportSummaryMeta(id=rid * 10 + 2, report_id=rid,
                                          all_metrics=[{'name': 'old'}]))
            session.add(ReportRawData(id=rid * 10 + 3, report_id=rid,
                                      raw_data={'old': True}))
            session.add(ReportMetricStats(id=rid * 10 + 4, report_id=rid,
                                          metric_data={'old': 1}))
            session.add(ReportComparisonMatrix(id=rid * 10 + 5, report_id=rid,
                                               comparison_matrix={'old': 1}))
            for i in range(cases):
                session.add(ReportCase(id=rid * 100 + i, report_id=rid,
                                       test_case_id=f'old-case-{rid}-{i}',
                                       name=f'旧用例{rid}-{i}'))

        # ---- A5 引用方：share / studio doc+chart / benchmark / 收藏 ----
        session.add(ReportShare(id=1, report_id=LATEST_REPORT, token='token-5001',
                                access='login'))
        session.add(ReportStudioDocument(doc_id='doc-000000000001',
                                         report_id=LATEST_REPORT, title='报告文档'))
        session.add(ReportStudioChartSpec(chart_id='chart-00000001',
                                          doc_id='doc-000000000001',
                                          report_id=LATEST_REPORT))
        session.add(BenchmarkReport(id=1, report_id=LATEST_REPORT, suite='s1'))
        # BenchmarkRanking 有多列 NOT NULL，验收只覆盖 benchmark_reports 引用方
        session.add(ReportFavorite(id=1, user_id=3, entity_type='report',
                                   entity_id=str(LATEST_REPORT)))
        session.commit()
        print('SEED OK')
    finally:
        session.close()


def _package():
    rid = 9001
    return {
        'test_reports': [{
            'id': rid, 'name': 'B侧新报告', 'type': 'task', 'task_id': 888,
            'status': 'published', 'description': 'B侧描述', 'analysis': 'B侧分析',
            'visibility': 'private', 'created_by_user_id': 999,
            'created_at': '2026-10-20T10:00:00',
        }],
        'report_summaries': [{'id': rid * 10 + 1, 'report_id': rid,
                              'total_cases': 3, 'pass_rate': 0.9}],
        'report_summary_meta': [{'id': rid * 10 + 2, 'report_id': rid,
                                 'all_metrics': [{'name': 'new'}]}],
        'report_raw_data': [{'id': rid * 10 + 3, 'report_id': rid,
                             'raw_data': {'new': True}}],
        'report_cases': [{'id': rid * 100 + i, 'report_id': rid,
                          'test_case_id': f'new-case-{i}', 'name': f'新用例{i}'}
                         for i in range(3)],
        'report_metric_stats': [{'id': rid * 10 + 4, 'report_id': rid,
                                 'metric_data': {'new': 2}}],
        'report_comparison_matrix': [{'id': rid * 10 + 5, 'report_id': rid,
                                      'comparison_matrix': {'new': 2}}],
    }


def replace():
    from report_service.interfaces.grpc.servicers import ReportServicer
    from shared.proto import report_service_pb2 as report_pb
    req = report_pb.ReplaceReportsRequest(data=json.dumps({
        'rows_by_table': _package(), 'task_id': TASK_ID,
        'batch_id': 'd4-tst-rep'}, ensure_ascii=False))
    resp = ReportServicer().ReplaceReports(req)
    print('ReplaceReports success=%s code=%s message=%s' %
          (resp.success, resp.code, resp.message))
    print('data=' + json.dumps(json.loads(resp.data or '{}'), ensure_ascii=False))


def rb_report():
    from report_service.interfaces.grpc.servicers import ReportServicer
    from shared.proto import report_service_pb2 as report_pb
    resp = ReportServicer().RollbackReportReplacement(
        report_pb.RollbackReportReplacementRequest(batch_id='d4-tst-rep'))
    print('RollbackReportReplacement success=%s code=%s message=%s' %
          (resp.success, resp.code, resp.message))
    print('data=' + json.dumps(json.loads(resp.data or '{}'), ensure_ascii=False))


def merge():
    from evaluation_service.interfaces.grpc.evaluation_data_servicer import (
        EvaluationDataServiceServicer,
    )
    from shared.proto import evaluation_service_pb2 as eval_pb
    req = eval_pb.MergeDimensionsRequest(data=json.dumps({
        'rows': [
            {'id': 901, 'test_result_id': 101, 'dimension_id': 1,
             'round_number': 0, 'score': 88.0, 'status': 'passed',
             'evaluation_status': 'completed'},
            {'id': 902, 'test_result_id': 101, 'dimension_id': 1,
             'round_number': 1, 'score': 89.0, 'status': 'passed',
             'evaluation_status': 'completed'},
        ],
        'dimension_id_mapping': {}, 'batch_id': 'd4-tst-dim'}, ensure_ascii=False))
    resp = EvaluationDataServiceServicer().MergeDimensions(req)
    print('MergeDimensions success=%s message=%s' % (resp.success, resp.message))
    print('data=' + json.dumps(json.loads(resp.data or '{}'), ensure_ascii=False))


def rb_dim():
    from evaluation_service.interfaces.grpc.evaluation_data_servicer import (
        EvaluationDataServiceServicer,
    )
    from shared.proto import evaluation_service_pb2 as eval_pb
    resp = EvaluationDataServiceServicer().RollbackDimensionMerge(
        eval_pb.RollbackDimensionMergeRequest(batch_id='d4-tst-dim'))
    print('RollbackDimensionMerge success=%s message=%s' % (resp.success, resp.message))
    print('data=' + json.dumps(json.loads(resp.data or '{}'), ensure_ascii=False))


def merge_missing():
    """A2-3：包内 result id 在 A 无维度行 → 409 + 零写入"""
    from evaluation_service.interfaces.grpc.evaluation_data_servicer import (
        EvaluationDataServiceServicer,
    )
    from shared.proto import evaluation_service_pb2 as eval_pb
    req = eval_pb.MergeDimensionsRequest(data=json.dumps({
        'rows': [{'test_result_id': 101, 'dimension_id': 2, 'score': 1.0},
                 {'test_result_id': 99999, 'dimension_id': 1, 'score': 1.0}],
        'batch_id': 'd4-tst-dim-bad'}, ensure_ascii=False))
    resp = EvaluationDataServiceServicer().MergeDimensions(req)
    print('MergeDimensions(missing) success=%s message=%s' % (resp.success, resp.message))
    print('data=' + json.dumps(json.loads(resp.data or '{}'), ensure_ascii=False))


def replace_create():
    """A5-2 ③：任务下无报告 → 新建；随后回滚，检验新建父行是否被清掉"""
    from report_service.interfaces.grpc.servicers import ReportServicer
    from shared.proto import report_service_pb2 as report_pb
    req = report_pb.ReplaceReportsRequest(data=json.dumps({
        'rows_by_table': _package(), 'task_id': 20002,
        'batch_id': 'd4-tst-rep-create'}, ensure_ascii=False))
    resp = ReportServicer().ReplaceReports(req)
    print('ReplaceReports(create) success=%s code=%s message=%s' %
          (resp.success, resp.code, resp.message))
    print('data=' + json.dumps(json.loads(resp.data or '{}'), ensure_ascii=False))
    resp2 = ReportServicer().RollbackReportReplacement(
        report_pb.RollbackReportReplacementRequest(batch_id='d4-tst-rep-create'))
    print('RollbackReportReplacement(create) success=%s message=%s data=%s' %
          (resp2.success, resp2.message, resp2.data))


def replace_cross_task():
    """target_report_id 属于别的任务时是否被拒（防止错任务报告被改写）"""
    from report_service.interfaces.grpc.servicers import ReportServicer
    from shared.proto import report_service_pb2 as report_pb
    req = report_pb.ReplaceReportsRequest(data=json.dumps({
        'rows_by_table': _package(), 'task_id': 20002,
        'target_report_id': 5000,
        'batch_id': 'd4-tst-rep-crosstask'}, ensure_ascii=False))
    resp = ReportServicer().ReplaceReports(req)
    print('ReplaceReports(cross-task target) success=%s code=%s message=%s' %
          (resp.success, resp.code, resp.message))
    print('data=' + json.dumps(json.loads(resp.data or '{}'), ensure_ascii=False))


def replace_fail():
    """中途失败：第 4 张子表写入超长 name 触发 PG 错误，检验旧报告 7 表原样"""
    from report_service.interfaces.grpc.servicers import ReportServicer
    from shared.proto import report_service_pb2 as report_pb
    pkg = _package()
    pkg['report_cases'][0]['name'] = 'X' * 600   # report_cases.name 是 VARCHAR(500)
    req = report_pb.ReplaceReportsRequest(data=json.dumps({
        'rows_by_table': pkg, 'task_id': TASK_ID,
        'batch_id': 'd4-tst-rep-fail'}, ensure_ascii=False))
    resp = ReportServicer().ReplaceReports(req)
    print('ReplaceReports(injected failure) success=%s code=%s message=%s' %
          (resp.success, resp.code, resp.message[:200]))
    print('data=' + json.dumps(json.loads(resp.data or '{}'), ensure_ascii=False))


COMMANDS = {
    'seed': seed, 'replace': replace, 'rb-report': rb_report, 'merge': merge,
    'rb-dim': rb_dim, 'merge-missing': merge_missing,
    'replace-create': replace_create, 'replace-cross-task': replace_cross_task,
    'replace-fail': replace_fail,
}

if __name__ == '__main__':
    from shared.models.database import init_db
    init_db()
    COMMANDS[sys.argv[1]]()

