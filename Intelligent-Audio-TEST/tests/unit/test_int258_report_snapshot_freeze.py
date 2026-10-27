# -*- coding: utf-8 -*-
"""INT-258 回归：发布报告快照语义修正——冻结历史报告（引用 + 冻结双轨）。

原缺陷：report_snapshot 存的是执行数据摘要（v1 结构，metric_data 等统计
被 _to_json_obj 丢弃、无 raw_data / comparison 相关渲染字段），负责人要的
是"报告管理（历史页面）生成的真实报告被冻结"。

修复语义（本文件覆盖）：
- freeze_report_snapshot：schemaVersion=2 双轨结构（sourceReportId 引用 +
  报告 7 表渲染字段冻结：summaries / summary_meta 全字段 / metric_stats 全
  字段 / raw_data / 逐用例结果与日志），metric_data/tag_metric_data 保留原
  类型（数组不被 _to_json_obj 丢弃）；已软删除报告不参与冻结；
- create_version：指定新来源任务时冻结该任务当前报告；无新来源任务时沿用
  当前版本冻结报告（版本链语义延续）。

隔离方式：freeze 用独立 sqlite 内存库建报告 7 表 + monkeypatch get_db_session；
create_version 用 fake repo 替身（同 test_published_task_benchmark 惯例）。
"""
import os

# BaseConfig 在 import 时校验环境变量（测试环境无 .env），先补齐必需项
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

import task_service.infrastructure.persistence.published_task_repository as ptr_module
from task_service.application.services.published_task_service import (
    PublishedTaskService,
)


def _build_session_factory(monkeypatch, tables):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from shared.models.database import Base

    engine = create_engine(
        'sqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool)
    Base.metadata.create_all(bind=engine, tables=tables)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(ptr_module, 'get_db_session', factory)
    return factory


def _seed_report_with_full_tables(factory, *, deleted=False, analysis='整体通过'):
    """写入报告 7 表完整素材（task 123），返回报告 ID。

    JSON 列直接传 Python 对象（与生产 psycopg2 序列化口径一致）；
    BigInteger 主键表在 sqlite 无自增，显式指定 id。
    analysis 支持 JSON config 形态（name/description/conclusion 存于其中）。

    INT-1995（档4 M1）：用例行只写五列 + 快照指针，九字段 payload 走
    report_case_snapshots（与生产写路径 add_case 同口径）。
    """
    import json as _json

    from report_service.infrastructure.persistence import (
        report_case_snapshot_store as store,
    )
    from report_service.infrastructure.persistence.models import (
        Report, ReportSummary, ReportSummaryMeta, ReportMetricStats,
        ReportCase, ReportRawData,
    )

    session = factory()
    report = Report(
        id=391, name='INT-258 验收报告', type='task', status='published',
        task_id=123, analysis=analysis, deleted=deleted)
    session.add(report)
    session.flush()
    session.add(ReportSummary(
        id=1, report_id=391, total_cases=10, completed_cases=9, failed_cases=1,
        pass_rate=90.0, duration=120.5))
    session.add(ReportSummaryMeta(
        id=1, report_id=391,
        dimension_values=[{'name': 'WER', 'average_value': 7.2}],
        case_categories=['登录功能', '播放功能'],
        all_case_tags=['回归', '冒烟'],
        all_metrics=[{'name': 'WER', 'unit': '%', 'decimalPlaces': 2}],
        devices=[{'id': 1, 'name': '测试手机'}],
        apis=[],
        resources=['res-a'],
        resource_headers=[{'key': 'res-a', 'label': '资源A'}],
        field_mappings={'asr': {'result': ['text'], 'reference': ['ref']}},
    ))
    session.add(ReportMetricStats(
        id=1, report_id=391,
        metric_data=[{'resource': 'res-a', 'metrics': [{'metric': 'WER', 'value': 7.2}]}],
        tag_metric_data=[{'tag': '回归', 'metrics': {'WER': 7.2}}],
        tag_category_metric_data=[{'category': '分类1'}],
        case_type_stats=[{'type': 'api', 'count': 10}],
        device_stats=[{'id': 1, 'name': '测试手机', 'totalCases': 10}],
        api_stats=[],
    ))
    session.add(ReportRawData(
        id=1, report_id=391,
        raw_data=[{'resource': 'res-a', 'dimension': 'WER', 'values': [7.1, 7.3]}]))
    _seed_cases(session, (
        dict(test_case_id='tc-1', name='登录用例', category='登录功能',
             tags=['回归'], metrics={'res-a': {'WER': 7.2}},
             results=[{'resource': 'res-a', 'text': '你好'}], audios=[],
             reference_params={}, algorithm_results={}, algorithm_type='asr',
             logs='round1 log', id=9001),
        dict(test_case_id='tc-2', name='播放用例', category='播放功能', tags=[],
             metrics={}, results=[], audios=[], reference_params={},
             algorithm_results={}, algorithm_type='asr', logs='round2 log',
             id=9002),
    ))
    session.commit()
    session.close()
    return 391


def _seed_cases(session, case_payloads):
    """写用例行（五列 + 快照指针）+ 快照行（先快照后行，与 add_case 同口径）。"""
    from report_service.infrastructure.persistence import (
        report_case_snapshot_store as store,
    )
    from report_service.infrastructure.persistence.models import ReportCase

    for data in case_payloads:
        payload = store.build_payload(data)
        pointer = store.put(session, payload)
        po = ReportCase(
            report_id=391, id=data['id'], test_case_id=data['test_case_id'],
            algorithm_type=data['algorithm_type'], logs=data['logs'])
        store.apply_pointer(po, pointer)
        session.add(po)


def _raw_cases_from_db(factory, report_id):
    """从 sqlite 行读原始 payload（等价 report_service 解引用出口的返回）。

    INT-1996：freeze_report_snapshot 改走 report_service 解引用出口（gRPC +
    ACL）。INT-1995（M1）后行上无内容列，payload 从 report_case_snapshots 解引用
    （store.resolve_rows），本替身模拟出口返回的原始九字段 dict（不经
    build_case_item 的 falsy 归一，metrics==[] 原样保留）。
    """
    from report_service.infrastructure.persistence import (
        report_case_snapshot_store as store,
    )
    from report_service.infrastructure.persistence.models import ReportCase

    session = factory()
    try:
        rows = (
            session.query(ReportCase)
            .filter(ReportCase.report_id == report_id)
            .order_by(ReportCase.id.asc())
            .all()
        )
        resolved = store.resolve_rows(session, rows, report_id=report_id)
        return [
            {
                'id': c.id,
                'test_case_id': c.test_case_id,
                **{f: getattr(c, f) for f in store.PAYLOAD_FIELDS},
                'algorithm_type': c.algorithm_type,
                'logs': c.logs,
            }
            for c in resolved
        ]
    finally:
        session.close()


def _monkeypatch_raw_cases(monkeypatch, factory):
    """freeze_report_snapshot 经 gRPC+ACL 取用例后，用行读替身喂回原始 payload。"""
    monkeypatch.setattr(
        ptr_module.report_acl_repository,
        'get_report_cases_raw_payload',
        lambda report_id: _raw_cases_from_db(factory, report_id),
    )


class TestFreezeReportSnapshotDualTrack:
    """freeze_report_snapshot：引用 + 冻结双轨（7 表完整冻结）。"""

    TABLES = None  # 类级延迟初始化（依赖 ORM import）

    @classmethod
    def _tables(cls):
        if cls.TABLES is None:
            from report_service.infrastructure.persistence.models import (
                Report, ReportSummary, ReportSummaryMeta, ReportMetricStats,
                ReportCase, ReportCaseSnapshot, ReportRawData,
            )
            cls.TABLES = [Report.__table__, ReportSummary.__table__,
                          ReportSummaryMeta.__table__, ReportMetricStats.__table__,
                          ReportCase.__table__, ReportCaseSnapshot.__table__,
                          ReportRawData.__table__]
        return cls.TABLES

    def test_freeze_v2_dual_track_structure(self, monkeypatch):
        factory = _build_session_factory(monkeypatch, self._tables())
        report_id = _seed_report_with_full_tables(factory)
        _monkeypatch_raw_cases(monkeypatch, factory)

        snapshot = ptr_module.published_task_repository.freeze_report_snapshot(123)

        assert snapshot is not None
        # 引用轨：sourceReportId（+ 兼容 reportId）
        assert snapshot['schemaVersion'] == 2
        assert snapshot['sourceReportId'] == report_id
        assert snapshot['reportId'] == report_id
        # 报告元数据冻结
        assert snapshot['name'] == 'INT-258 验收报告'
        assert snapshot['analysis'] == '整体通过'
        # summary：报告 7 表渲染字段（报告页组件消费口径）
        summary = snapshot['summary']
        assert summary['totalCases'] == 10
        assert summary['passRate'] == 90.0
        assert summary['dimensionValues'] == [{'name': 'WER', 'average_value': 7.2}]
        assert summary['caseCategories'] == ['登录功能', '播放功能']
        assert summary['allCaseTags'] == ['回归', '冒烟']
        assert summary['resources'] == ['res-a']
        assert summary['resourceHeaders'] == [{'key': 'res-a', 'label': '资源A'}]
        assert summary['fieldMappings'] == {'asr': {'result': ['text'], 'reference': ['ref']}}
        # metric_data/tag_metric_data 保留原类型（数组不被 _to_json_obj 丢弃）
        assert summary['metricData'] == [
            {'resource': 'res-a', 'metrics': [{'metric': 'WER', 'value': 7.2}]}]
        assert summary['tagMetricData'] == [{'tag': '回归', 'metrics': {'WER': 7.2}}]
        assert summary['tagCategoryMetricData'] == [{'category': '分类1'}]
        assert summary['caseTypeStats'] == [{'type': 'api', 'count': 10}]
        assert summary['deviceStats'] == [{'id': 1, 'name': '测试手机', 'totalCases': 10}]
        # raw_data（report_raw_data 表）冻结
        assert summary['rawData'] == [
            {'resource': 'res-a', 'dimension': 'WER', 'values': [7.1, 7.3]}]
        # 逐用例冻结：行 id + 逐轮结果 + 日志
        cases = snapshot['cases']
        assert [c['id'] for c in cases] == [9001, 9002]
        assert cases[0]['testCaseId'] == 'tc-1'
        assert cases[0]['logs'] == 'round1 log'
        assert cases[0]['results'] == [{'resource': 'res-a', 'text': '你好'}]

    def test_freeze_excludes_soft_deleted_report(self, monkeypatch):
        factory = _build_session_factory(monkeypatch, self._tables())
        _seed_report_with_full_tables(factory, deleted=True)

        assert ptr_module.published_task_repository.freeze_report_snapshot(123) is None

    def test_freeze_returns_none_without_report(self, monkeypatch):
        _build_session_factory(monkeypatch, self._tables())

        assert ptr_module.published_task_repository.freeze_report_snapshot(999) is None

    def test_freeze_returns_none_without_task_id(self, monkeypatch):
        assert ptr_module.published_task_repository.freeze_report_snapshot(None) is None

    def test_freeze_analysis_json_config_resolution(self, monkeypatch):
        """analysis 为 JSON config 序列化串时：name/description/conclusion 按
        报告页 _aggregate_to_dict 口径解析（V9.7.31 报告更新链路把 config 存 analysis）。"""
        import json as _json
        factory = _build_session_factory(monkeypatch, self._tables())
        _seed_report_with_full_tables(
            factory,
            analysis=_json.dumps({
                'name': '任务报告_20261013', 'description': None,
                'conclusion': '本轮整体通过，WER 达标',
            }))
        _monkeypatch_raw_cases(monkeypatch, factory)

        snapshot = ptr_module.published_task_repository.freeze_report_snapshot(123)

        assert snapshot is not None
        assert snapshot['name'] == 'INT-258 验收报告'  # PO.name 优先（对齐 _aggregate_to_dict）
        assert snapshot['analysis'] == '本轮整体通过，WER 达标'  # conclusion 解析为展示文本
        # PO.name 为空时回退 config.name
        from report_service.infrastructure.persistence.models import Report
        session = factory()
        session.query(Report).filter(Report.id == 391).update({'name': ''})
        session.commit()
        session.close()
        snapshot2 = ptr_module.published_task_repository.freeze_report_snapshot(123)
        assert snapshot2['name'] == '任务报告_20261013'


# ---------------------------------------------------------------------------
# create_version 冻结/继承语义
# ---------------------------------------------------------------------------

def make_task(**overrides):
    task = type('TaskPO', (), {})()
    task.id = 456
    task.deleted = False
    task.status = 'completed'
    task.config = {}
    task.algorithm_type = 'translation'
    task.algorithm_params = {}
    task.created_by_user_id = None
    task.visibility = 'shared'
    for k, v in overrides.items():
        setattr(task, k, v)
    return task


def make_pt(**overrides):
    pt = type('PublishedTaskPO', (), {})()
    pt.id = 1001
    pt.task_group_id = 1001
    pt.source_task_id = 123
    pt.name = '已发布任务'
    pt.description = None
    pt.type = 'e2e'
    pt.algorithm_type = 'translation'
    pt.status = 'published'
    pt.benchmark = False
    pt.version = 1
    pt.is_current = True
    pt.snapshot_config = {'caseIds': [1], 'deviceIds': [], 'apiIds': [], 'tags': []}
    pt.report_snapshot = {'schemaVersion': 2, 'sourceReportId': 391}
    pt.published_by = None
    pt.published_at = None
    pt.archived_by = None
    pt.archived_at = None
    pt.created_at = None
    pt.created_by_user_id = None
    pt.visibility = 'shared'
    for k, v in overrides.items():
        setattr(pt, k, v)
    return pt


class FakeRepo:
    """published_task_repository 替身：记录冻结与 create_version 调用。"""

    def __init__(self, source_task=None, current_pt=None, frozen=None):
        self.source_task = source_task or make_task()
        self.current_pt = current_pt or make_pt()
        self.frozen = frozen
        self.freeze_calls = []
        self.create_version_kwargs = None

    def get_task(self, task_id):
        return self.source_task

    def get_task_case_devices(self, task_id):
        return []

    def get_task_case_ids(self, task_id):
        return [1, 2]

    def get_task_device_ids(self, task_id):
        return []

    def get_task_api_ids(self, task_id):
        return []

    def get_task_tag_names(self, task_id):
        return []

    def get_existing_case_ids(self, case_ids):
        return set(case_ids)

    def freeze_report_snapshot(self, source_task_id):
        self.freeze_calls.append(source_task_id)
        return self.frozen

    def freeze_task_snapshot(self, task):
        return {'schemaVersion': 2, 'task': {}, 'cases': []}

    def get_by_id(self, published_task_id):
        return self.current_pt

    def get_current_version(self, group_id):
        return self.current_pt

    def create_version(self, **kwargs):
        self.create_version_kwargs = kwargs
        return make_pt(**{
            'id': 1002,
            'version': kwargs.get('version', 2),
            'task_group_id': self.current_pt.task_group_id,
        })

    def get_source_task_summary(self, task_id):
        return None

    def get_group_versions(self, group_id):
        return [self.current_pt]

    def get_execution_history(self, version_ids):
        return []

    def update_task_trace(self, *args, **kwargs):
        return True


class FakeLogRepository:
    """审计写入器替身（INT-1793：S4 改调审计文件写入器，隔离真实日志目录）。"""

    def __init__(self):
        self.logs = []

    def write_audit_event(self, **kwargs):
        self.logs.append({'content': kwargs.get('content'),
                          'event': kwargs.get('event'),
                          'category': kwargs.get('category')})
        return len(self.logs)


class TestCreateVersionReportSnapshotSemantics:
    """create_version：新来源任务冻结 / 无新来源任务继承。"""

    def _run(self, monkeypatch, repo, data):
        import task_service.application.services.published_task_service as pts_module
        monkeypatch.setattr(pts_module, 'repo', repo)
        monkeypatch.setattr('shared.logging.audit_writer.write_audit_event', FakeLogRepository().write_audit_event)
        return PublishedTaskService.create_version(1001, data)

    def test_new_source_task_freezes_its_report(self, monkeypatch):
        frozen = {'schemaVersion': 2, 'sourceReportId': 555}
        repo = FakeRepo(source_task=make_task(id=456), frozen=frozen)

        result = self._run(monkeypatch, repo, {'sourceTaskId': 456})

        assert result['success'] is True
        assert repo.freeze_calls == [456]
        assert repo.create_version_kwargs['report_snapshot'] is frozen
        assert repo.create_version_kwargs['source_task_id'] == 456

    def test_no_new_source_inherits_current_frozen_report(self, monkeypatch):
        repo = FakeRepo(current_pt=make_pt())  # current.report_snapshot = v2 快照

        result = self._run(monkeypatch, repo, {})

        assert result['success'] is True
        assert repo.freeze_calls == []
        assert repo.create_version_kwargs['report_snapshot'] == {
            'schemaVersion': 2, 'sourceReportId': 391}
        assert repo.create_version_kwargs['source_task_id'] == 123
