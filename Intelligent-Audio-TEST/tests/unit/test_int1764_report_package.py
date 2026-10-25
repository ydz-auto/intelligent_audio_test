# -*- coding: utf-8 -*-
"""INT-1764 D6：报告包（链路 3a 平台报告 + 3b 上传文档 + 3c Agent 总结）单测

覆盖设计文档 §6.1 / §6.3 的判定口径：
- 3a：平台报告按 sourceTask 原地替换（保留 A 报告 id / visibility / owner），
  子表整表重建、回执统计准确；
- 3b/3c：文档拓扑序落库、两类 ID 翻译（report_id 走报告映射、parent_doc_id
  走文档映射）、agent_session_id 置空、孤儿降级写 warnings；
- 版本策略 full / latest；图表 report_id 失联降级为空且读取不报错；
- manifest 校验与报告包里"多个任务 / task 不一致 / 原任务缺失"的失败码。

DB：sqlite 临时库（复用 tests/integration/test_data_transfer_roundtrip.py 夹具）。
"""
import json
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from tests.integration.test_data_transfer_roundtrip import db, storage_env  # noqa: F401

from report_service.infrastructure.persistence.models import (  # noqa: E402
    Report,
    ReportCase,
    ReportStudioChartSpec,
    ReportStudioDocument,
    ReportStudioDocumentVersion,
    ReportSummary,
)

_REPORT_STUDIO_DOCS = 'report_studio_documents'
_REPORT_STUDIO_VERSIONS = 'report_studio_document_versions'
_REPORT_STUDIO_CHARTS = 'report_studio_chart_specs'


def _session():
    from shared.models.database import get_db_session
    return get_db_session()


def _add(po):
    session = _session()
    try:
        session.add(po)
        session.commit()
        return po
    finally:
        session.close()


def _all(po_cls):
    session = _session()
    try:
        return session.query(po_cls).all()
    finally:
        session.close()


def _seed_report(task_id=21, report_id=41, name='A 原报告'):
    _add(Report(id=report_id, name=name, type='task', task_id=task_id,
                status='published', visibility='private', created_by_user_id=7))
    _add(ReportSummary(report_id=report_id, total_cases=3, pass_rate=0.5))
    _add(ReportCase(report_id=report_id, test_case_id='case-a', name='原用例A'))
    _add(ReportCase(report_id=report_id, test_case_id='case-b', name='原用例B'))
    return report_id


def _seed_studio(report_id=41):
    """平台报告文档 + 上传文档 + Agent 总结（源为上传文档，带图表与两版版本链）"""
    _add(ReportStudioDocument(
        doc_id='doc-platform', report_id=report_id, source_type='platform_report',
        title='平台报告文档', markdown_content='v1', chart_refs=[], current_version=1,
        etag_hash='e1', created_by=7))
    _add(ReportStudioDocumentVersion(
        doc_id='doc-platform', version=1, markdown_content='v1', chart_specs={},
        snapshot_reason='manual_edit', created_by=7))
    _add(ReportStudioDocument(
        doc_id='doc-upload', report_id=report_id, source_type='uploaded_file',
        title='上传的 MD', markdown_content='上传正文', current_version=2,
        etag_hash='e2', created_by=7))
    _add(ReportStudioDocumentVersion(
        doc_id='doc-upload', version=1, markdown_content='旧版', chart_specs={},
        snapshot_reason='manual_edit', created_by=7))
    _add(ReportStudioDocumentVersion(
        doc_id='doc-upload', version=2, markdown_content='上传正文', chart_specs={},
        parent_version=1, snapshot_reason='manual_edit', created_by=7))
    _add(ReportStudioChartSpec(
        chart_id='chart-1', doc_id='doc-upload', report_id=report_id,
        metric_params={'metric': 'pass_rate'}, style={}, created_by=7))
    _add(ReportStudioDocument(
        doc_id='doc-summary', report_id=None, source_type='agent_summary',
        parent_doc_id='doc-upload', agent_session_id='dsh-session-1',
        title='Agent 总结', markdown_content='总结正文', current_version=1,
        chart_refs=['chart:chart-1'], etag_hash='e3', created_by=7))
    _add(ReportStudioDocumentVersion(
        doc_id='doc-summary', version=1, markdown_content='总结正文',
        chart_specs={'refs': ['chart:chart-1']}, snapshot_reason='ai_edit', created_by=7))


def _package_tables(report_id, task_id=21):
    from report_service.infrastructure.persistence.report_transfer_repository import (
        report_transfer_repository,
    )
    tables = report_transfer_repository.export_by_report_ids([report_id])
    for row in tables['test_reports']:
        row['name'] = 'B 侧新报告'
        row['analysis'] = 'B 侧分析'
    for row in tables['report_summaries']:
        row['total_cases'] = 99
        row['pass_rate'] = 1.0
    return tables


# ==================================================================
# Studio 三表：导出（闭包 / 版本策略）
# ==================================================================

class TestStudioExport:
    def test_export_collects_document_closure_and_all_versions(self, db):
        _seed_report()
        _seed_studio()
        from report_service.infrastructure.persistence.report_studio_transfer_repository import (
            report_studio_transfer_repository,
        )
        rows = report_studio_transfer_repository.export_studio_rows([41], 'full')
        assert {d['doc_id'] for d in rows[_REPORT_STUDIO_DOCS]} == {
            'doc-platform', 'doc-upload', 'doc-summary'}
        # full：上传文档两版 + 另两文档各一版
        assert len(rows[_REPORT_STUDIO_VERSIONS]) == 4
        assert len(rows[_REPORT_STUDIO_CHARTS]) == 1

    def test_export_latest_scope_only_current_version(self, db):
        _seed_report()
        _seed_studio()
        from report_service.infrastructure.persistence.report_studio_transfer_repository import (
            report_studio_transfer_repository,
        )
        rows = report_studio_transfer_repository.export_studio_rows([41], 'latest')
        versions = rows[_REPORT_STUDIO_VERSIONS]
        assert len(versions) == 3
        upload_versions = [v for v in versions if v['doc_id'] == 'doc-upload']
        assert [v['version'] for v in upload_versions] == [2]


# ==================================================================
# Studio 三表：导入（两类 ID 翻译 / 孤儿降级 / 会话置空）
# ==================================================================

class TestStudioImport:
    def test_translates_report_and_parent_doc_ids_and_drops_session(self, db):
        from report_service.infrastructure.persistence.report_studio_transfer_repository import (
            report_studio_transfer_repository,
        )
        studio = {
            _REPORT_STUDIO_DOCS: [
                {'doc_id': 'src-doc-upload', 'report_id': 41,
                 'source_type': 'uploaded_file', 'title': '上传文档',
                 'markdown_content': '正文', 'current_version': 1, 'etag_hash': 'x',
                 'chart_refs': []},
                {'doc_id': 'src-doc-summary', 'report_id': None,
                 'source_type': 'agent_summary', 'parent_doc_id': 'src-doc-upload',
                 'agent_session_id': 'dsh-9', 'title': '总结',
                 'markdown_content': '总结', 'current_version': 1, 'etag_hash': 'y',
                 'chart_refs': []},
            ],
            _REPORT_STUDIO_VERSIONS: [
                {'doc_id': 'src-doc-upload', 'version': 1, 'markdown_content': '正文',
                 'chart_specs': {}, 'snapshot_reason': 'manual_edit'},
                {'doc_id': 'src-doc-summary', 'version': 1, 'markdown_content': '总结',
                 'chart_specs': {}, 'snapshot_reason': 'ai_edit'},
            ],
            _REPORT_STUDIO_CHARTS: [],
        }
        result = report_studio_transfer_repository.import_studio_rows(
            studio, {41: 88}, 'full')

        mapping = result['document_id_mapping']
        assert set(mapping) == {'src-doc-upload', 'src-doc-summary'}
        assert mapping['src-doc-upload'] != 'src-doc-upload'   # A 侧重新分配 doc_id
        assert result['session_dropped'] == 1
        assert result['warnings'] == []

        docs = {d.doc_id: d for d in _all(ReportStudioDocument)}
        upload = docs[mapping['src-doc-upload']]
        summary = docs[mapping['src-doc-summary']]
        assert upload.report_id == 88                       # 报告映射翻译
        assert summary.parent_doc_id == upload.doc_id       # 文档映射翻译
        assert summary.agent_session_id is None             # 规则 1：会话不迁移
        assert len(_all(ReportStudioDocumentVersion)) == 2

    def test_orphan_parent_degrades_and_warns(self, db):
        from report_service.infrastructure.persistence.report_studio_transfer_repository import (
            report_studio_transfer_repository,
        )
        studio = {
            _REPORT_STUDIO_DOCS: [
                {'doc_id': 'src-orphan', 'report_id': None,
                 'source_type': 'agent_summary', 'parent_doc_id': 'not-in-package',
                 'title': '孤儿总结', 'markdown_content': 'x', 'current_version': 1,
                 'chart_refs': []},
            ],
            _REPORT_STUDIO_VERSIONS: [],
            _REPORT_STUDIO_CHARTS: [],
        }
        result = report_studio_transfer_repository.import_studio_rows(studio, {}, 'full')

        assert result['imported'][_REPORT_STUDIO_DOCS] == 1
        assert any('孤儿文档' in w for w in result['warnings'])
        doc = _all(ReportStudioDocument)[0]
        assert doc.parent_doc_id is None

    def test_chart_report_degrades_to_null_and_refs_are_translated(self, db):
        from report_service.infrastructure.persistence.report_studio_transfer_repository import (
            report_studio_transfer_repository,
        )
        studio = {
            _REPORT_STUDIO_DOCS: [
                {'doc_id': 'src-up', 'report_id': 41,
                 'source_type': 'uploaded_file', 'title': '上传',
                 'markdown_content': 'm', 'current_version': 1,
                 'chart_refs': ['chart:src-chart'], 'etag_hash': 'z'},
            ],
            _REPORT_STUDIO_VERSIONS: [
                {'doc_id': 'src-up', 'version': 1, 'markdown_content': 'm',
                 'chart_specs': {'refs': ['chart:src-chart']},
                 'snapshot_reason': 'manual_edit'},
            ],
            _REPORT_STUDIO_CHARTS: [
                {'chart_id': 'src-chart', 'doc_id': 'src-up', 'report_id': 41,
                 'metric_params': {}, 'style': {}, 'version': 1},
                {'chart_id': 'src-orphan-chart', 'doc_id': 'src-up', 'report_id': 999,
                 'metric_params': {}, 'style': {}, 'version': 1},
            ],
        }
        result = report_studio_transfer_repository.import_studio_rows(
            studio, {41: 77}, 'full')

        mapping = result['document_id_mapping']
        charts = {c.chart_id: c for c in _all(ReportStudioChartSpec)}
        assert charts['src-chart'].report_id == 77
        assert charts['src-orphan-chart'].report_id is None
        assert any('需重新绑定' in w for w in result['warnings'])

        doc = [d for d in _all(ReportStudioDocument) if d.doc_id == mapping['src-up']][0]
        assert doc.chart_refs == ['chart:src-chart']     # 未冲突时 chart_id 保持
        version = [v for v in _all(ReportStudioDocumentVersion)][0]
        assert version.chart_specs == {'refs': ['chart:src-chart']}

        # 图表 report_id 为空时读取路径不报错（列表查询照常返回）
        from report_service.infrastructure.persistence.report_studio_repository import (
            ReportStudioRepositoryImpl,
        )
        rows, total = ReportStudioRepositoryImpl().list_documents(source_type='uploaded_file')
        assert total == 1 and rows[0].doc_id == mapping['src-up']

    def test_cross_document_chart_ref_is_translated(self, db):
        """Agent 总结的 chart_refs 指向父上传文档的图表：包内全局映射也能翻译。"""
        from report_service.infrastructure.persistence.report_studio_transfer_repository import (
            report_studio_transfer_repository,
        )
        studio = {
            _REPORT_STUDIO_DOCS: [
                {'doc_id': 'src-up', 'report_id': 41, 'source_type': 'uploaded_file',
                 'title': '上传', 'markdown_content': 'm', 'current_version': 1,
                 'chart_refs': [], 'etag_hash': 'a'},
                {'doc_id': 'src-sum', 'report_id': None, 'source_type': 'agent_summary',
                 'parent_doc_id': 'src-up', 'title': '总结', 'markdown_content': 's',
                 'current_version': 1, 'chart_refs': ['chart:src-chart'], 'etag_hash': 'b'},
            ],
            _REPORT_STUDIO_VERSIONS: [],
            _REPORT_STUDIO_CHARTS: [
                {'chart_id': 'src-chart', 'doc_id': 'src-up', 'report_id': 41,
                 'metric_params': {}, 'style': {}, 'version': 1},
            ],
        }
        result = report_studio_transfer_repository.import_studio_rows(
            studio, {41: 41}, 'full')
        mapping = result['document_id_mapping']
        summary = [d for d in _all(ReportStudioDocument)
                   if d.doc_id == mapping['src-sum']][0]
        assert summary.chart_refs == ['chart:src-chart']     # 未与 A 冲突 → 保持原 id
        assert not any('未随包搬运' in w for w in result['warnings'])

    def test_latest_scope_imports_only_current_version(self, db):
        from report_service.infrastructure.persistence.report_studio_transfer_repository import (
            report_studio_transfer_repository,
        )
        studio = {
            _REPORT_STUDIO_DOCS: [
                {'doc_id': 'src-up', 'report_id': 41, 'source_type': 'uploaded_file',
                 'title': '上传', 'markdown_content': 'v3', 'current_version': 3,
                 'chart_refs': [], 'etag_hash': 'e'},
            ],
            _REPORT_STUDIO_VERSIONS: [
                {'doc_id': 'src-up', 'version': 1, 'markdown_content': 'v1',
                 'chart_specs': {}, 'snapshot_reason': 'manual_edit'},
                {'doc_id': 'src-up', 'version': 3, 'markdown_content': 'v3',
                 'chart_specs': {}, 'parent_version': 1,
                 'snapshot_reason': 'manual_edit'},
            ],
            _REPORT_STUDIO_CHARTS: [],
        }
        result = report_studio_transfer_repository.import_studio_rows(
            studio, {41: 41}, 'latest')

        versions = _all(ReportStudioDocumentVersion)
        assert [v.version for v in versions] == [3]
        doc = _all(ReportStudioDocument)[0]
        assert doc.current_version == 3
        assert result['imported'][_REPORT_STUDIO_VERSIONS] == 1


# ==================================================================
# 报告包整体导入（3a 原地替换 + 3b/3c）
# ==================================================================

class TestReportPackageImport:
    def test_in_place_replacement_and_studio_import(self, db):
        _seed_report()
        _seed_studio()
        from report_service.infrastructure.persistence.report_studio_transfer_repository import (
            report_studio_transfer_repository,
        )
        from report_service.application.report_package_service import (
            report_package_service,
        )
        tables = _package_tables(41)
        studio = report_studio_transfer_repository.export_studio_rows([41], 'full')

        result = report_package_service.import_package(
            21, tables, studio, batch_id='batch-d6-1')

        assert result['success'] is True, result
        receipt = result['data']
        assert receipt['reportId'] == 41                  # 保留 A 报告 id
        assert receipt['deletedCounts']['report_cases'] == 2
        assert receipt['insertedCounts']['report_cases'] == 2
        assert receipt['agentSessionDropped'] == 1
        assert receipt['rollbackAvailable'] is True

        report = [r for r in _all(Report) if r.id == 41][0]
        assert report.name == 'B 侧新报告'                 # 内容来自 B
        assert report.visibility == 'private'             # 可见性保留 A
        assert report.created_by_user_id == 7             # owner 保留 A
        summary = [s for s in _all(ReportSummary) if s.report_id == 41][0]
        assert summary.total_cases == 99

        # Studio 文档全部指向 A 报告 id，会话已置空
        docs = _all(ReportStudioDocument)
        assert len(docs) == 6                            # 3 原有 + 3 新导入
        imported = [d for d in docs if d.doc_id in receipt['documentIdMapping'].values()]
        assert len(imported) == 3
        assert all(d.agent_session_id is None for d in imported)
        platform_docs = [d for d in imported if d.source_type == 'platform_report']
        assert platform_docs[0].report_id == 41

    def test_package_without_platform_report_imports_studio_only(self, db):
        from report_service.application.report_package_service import (
            report_package_service,
        )
        studio = {
            _REPORT_STUDIO_DOCS: [
                {'doc_id': 'only-up', 'report_id': None, 'source_type': 'uploaded_file',
                 'title': '独立上传', 'markdown_content': '正文', 'current_version': 1,
                 'chart_refs': []},
            ],
            _REPORT_STUDIO_VERSIONS: [],
            _REPORT_STUDIO_CHARTS: [],
        }
        result = report_package_service.import_package(
            21, {}, studio, batch_id='batch-d6-2')

        assert result['success'] is True, result
        assert result['data']['reportId'] is None
        assert any('包内无平台报告行' in w for w in result['data']['warnings'])
        assert len(_all(ReportStudioDocument)) == 1


# ==================================================================
# 导出可见性（INT-423）与单任务包校验（审计 P1 / P2 返工）
# ==================================================================

def _seed_other_report(report_id=42, task_id=22, owner=8, name='他人私有报告'):
    _add(Report(id=report_id, name=name, type='task', task_id=task_id,
                status='published', visibility='private', created_by_user_id=owner))
    _add(ReportSummary(report_id=report_id, total_cases=1, pass_rate=0.0))
    return report_id


def _seed_task(task_id, owner=None, visibility='private', name=None):
    from task_service.infrastructure.persistence.models import Task
    _add(Task(id=task_id, name=name or f'任务{task_id}', status='completed',
              created_by_user_id=owner, visibility=visibility))
    return task_id


class _AsUser:
    """临时切换操作人上下文（可见性过滤读 get_current_user_id / is_admin）"""

    def __init__(self, user_id, is_admin=False):
        self.user_id = user_id
        self.is_admin = is_admin

    def __enter__(self):
        from shared.infrastructure.user_context import (
            set_current_user_id, set_current_user_is_admin)
        set_current_user_id(self.user_id)
        set_current_user_is_admin(self.is_admin)
        return self

    def __exit__(self, *exc):
        from shared.infrastructure.user_context import (
            set_current_user_id, set_current_user_is_admin)
        set_current_user_id(None)
        set_current_user_is_admin(False)


class TestExportVisibility:
    """报告包导出必须与 GetReportDetail 同一行级可见性口径（INT-423）"""

    def test_report_ids_export_skips_others_private_report(self, db):
        _seed_report()                                # 41 / task 21 / owner 7 / private
        _seed_other_report()                          # 42 / task 22 / owner 8 / private
        _seed_studio(41)
        from report_service.application.report_package_service import report_package_service

        with _AsUser(7):
            result = report_package_service.export_package([], [41, 42], 'full')

        assert result['success'] is True, result
        data = result['data']
        assert [r['id'] for r in data['tables']['test_reports']] == [41]
        assert {r['report_id'] for r in data['tables']['report_summaries']} == {41}
        assert data['reportIds'] == [41]
        assert data['taskIds'] == [21]                # 任务 id 只用过滤后的报告行反推
        assert data['studio'][_REPORT_STUDIO_DOCS]    # Studio 闭包随报告一起过滤

    def test_task_ids_export_skips_others_private_reports(self, db):
        _seed_report()                                # 41 / task 21 / owner 7
        _seed_other_report(report_id=43, task_id=21, owner=8)   # 同任务下他人私有
        from report_service.application.report_package_service import report_package_service

        with _AsUser(7):
            result = report_package_service.export_package([21], [], 'full')

        assert [r['id'] for r in result['data']['tables']['test_reports']] == [41]
        assert result['data']['taskIds'] == [21]

    def test_all_invisible_reports_yield_empty_package(self, db):
        """全不可见 → 包内无报告；编排层据此返回 404，不回显报告是否存在"""
        _seed_report()
        from report_service.application.report_package_service import report_package_service

        with _AsUser(9):
            result = report_package_service.export_package([], [41], 'full')

        assert result['success'] is True
        assert result['data']['tables']['test_reports'] == []
        assert result['data']['reportIds'] == []
        assert result['data']['taskIds'] == []

    def test_admin_exports_every_report(self, db):
        _seed_report()
        _seed_other_report()
        from report_service.application.report_package_service import report_package_service

        with _AsUser(1, is_admin=True):
            result = report_package_service.export_package([], [41, 42], 'full')

        assert {r['id'] for r in result['data']['tables']['test_reports']} == {41, 42}


class TestExportSingleTaskGuard:
    """导出端不得下发导入端必然拒绝的跨任务包（审计 P2）"""

    @staticmethod
    def _patch_package(monkeypatch, tables_rows, task_ids, report_ids=None):
        from task_service.application.task import data_transfer_export_service as export_mod
        payload = {
            'tables': tables_rows,
            'studio': {},
            'reportIds': report_ids or [r['id'] for r in tables_rows.get('test_reports') or []],
            'taskIds': task_ids,
            'entities': ['platform_report'],
            'counts': {},
        }
        monkeypatch.setattr(export_mod.report_transfer_acl_repository,
                            'export_report_package',
                            lambda task_ids_arg, report_ids_arg, scope: payload)
        return export_mod

    def test_multi_task_report_ids_rejected_400(self, db, storage_env, monkeypatch):
        _seed_task(21, owner=7)
        _seed_task(22, owner=7)
        export_mod = self._patch_package(monkeypatch, {'test_reports': [
            {'id': 41, 'task_id': 21, 'name': 'a', 'type': 'task'},
            {'id': 42, 'task_id': 22, 'name': 'b', 'type': 'task'},
        ]}, [21, 22])

        with _AsUser(7):
            result = export_mod.data_transfer_export_service.export_report_package(
                [], [41, 42], 'full')

        assert result['success'] is False
        assert result['code'] == 400
        assert '同一个任务' in result['message']

    def test_report_of_invisible_task_rejected_400(self, db, storage_env, monkeypatch):
        _seed_task(21, owner=7)
        _seed_task(22, owner=8)                       # 他人私有任务
        export_mod = self._patch_package(monkeypatch, {'test_reports': [
            {'id': 41, 'task_id': 21, 'name': 'a', 'type': 'task'},
            {'id': 42, 'task_id': 22, 'name': 'b', 'type': 'task'},
        ]}, [21, 22])

        with _AsUser(7):
            result = export_mod.data_transfer_export_service.export_report_package(
                [], [41, 42], 'full')

        assert result['success'] is False
        assert result['code'] == 400
        assert '不可导出' in result['message']

    def test_empty_package_returns_404(self, db, storage_env, monkeypatch):
        export_mod = self._patch_package(
            monkeypatch, {'test_reports': []}, [], report_ids=[])

        with _AsUser(7):
            result = export_mod.data_transfer_export_service.export_report_package(
                [], [999], 'full')

        assert result['success'] is False
        assert result['code'] == 404

    def test_single_task_package_writes_manifest(self, db, storage_env, monkeypatch):
        import zipfile
        _seed_task(21, owner=7, name='接线测试_任务21')
        export_mod = self._patch_package(monkeypatch, {'test_reports': [
            {'id': 41, 'task_id': 21, 'name': 'a', 'type': 'task',
             'status': 'published', 'visibility': 'private'},
        ]}, [21])

        with _AsUser(7):
            result = export_mod.data_transfer_export_service.export_report_package(
                [], [41], 'full')

        assert result['success'] is True, result
        manifest = result['data']['manifest']
        assert manifest['sourceTask']['id'] == 21
        assert manifest['sourceTask']['localTaskId'] == 21
        assert manifest['sourceTask']['name'] == '接线测试_任务21'
        with zipfile.ZipFile(result['data']['zip_path']) as zf:
            assert 'manifest.json' in zf.namelist()
            assert 'db/test_reports.json' in zf.namelist()


class TestStudioImportDefaults:
    def test_missing_created_at_falls_back_to_now(self, db):
        """包内缺 / 坏 created_at 时不得对 NOT NULL 列写 NULL（审计 P3）"""
        from report_service.infrastructure.persistence.report_studio_transfer_repository import (
            report_studio_transfer_repository,
        )
        studio = {
            _REPORT_STUDIO_DOCS: [
                {'doc_id': 'no-ts', 'report_id': None, 'source_type': 'uploaded_file',
                 'title': '无时间戳', 'markdown_content': 'm', 'current_version': 1,
                 'chart_refs': [], 'created_at': 'not-a-date'},
            ],
            _REPORT_STUDIO_VERSIONS: [
                {'doc_id': 'no-ts', 'version': 1, 'markdown_content': 'm',
                 'chart_specs': {}, 'snapshot_reason': 'manual_edit'},
            ],
            _REPORT_STUDIO_CHARTS: [
                {'chart_id': 'no-ts-chart', 'doc_id': 'no-ts', 'report_id': None,
                 'metric_params': {}, 'style': {}, 'version': 1},
            ],
        }
        report_studio_transfer_repository.import_studio_rows(studio, {}, 'full')

        assert _all(ReportStudioDocument)[0].created_at is not None
        assert _all(ReportStudioDocumentVersion)[0].created_at is not None
        assert _all(ReportStudioChartSpec)[0].created_at is not None


# ==================================================================
# manifest 校验与 task_service 导入侧失败码
# ==================================================================

def _write_package(path, manifest, tables):
    from task_service.infrastructure.transfer.zip_io import build_zip
    build_zip(path, tables, manifest, iter(()))


def _manifest(task_id=21, local_task_id=21, entities=None):
    from task_service.domain.services.data_transfer.manifest import (
        build_report_package_manifest,
    )
    return build_report_package_manifest(
        source_task_id=task_id, local_task_id=local_task_id, task_name='任务',
        report_ids=[41], entities=entities or ['platform_report'])


class TestManifestAndImportErrors:
    def test_manifest_requires_kind_and_source_task(self):
        from task_service.domain.services.data_transfer.manifest import (
            ManifestError,
            validate_report_package_manifest,
        )
        with pytest.raises(ManifestError):
            validate_report_package_manifest({'version': '1.0', 'tasks': []})
        with pytest.raises(ManifestError):
            validate_report_package_manifest({
                'version': '1.0', 'kind': 'report_package', 'entities': []})
        ok = validate_report_package_manifest(_manifest())
        assert ok['sourceTask']['id'] == 21

    def test_missing_source_task_returns_404(self, db, storage_env, tmp_path):
        from task_service.application.task.data_transfer_import_service import (
            data_transfer_import_service,
        )
        zip_path = str(tmp_path / 'pkg404.zip')
        _write_package(zip_path, _manifest(task_id=999999, local_task_id=999999),
                       {'test_reports': []})
        result = data_transfer_import_service.import_report_package(zip_path)
        assert result['success'] is False
        assert result['code'] == 404
        assert result['data']['sourceTaskId'] == 999999

    def test_multiple_task_ids_rejected(self, db, storage_env, tmp_path):
        from task_service.application.task.data_transfer_import_service import (
            data_transfer_import_service,
        )
        zip_path = str(tmp_path / 'pkgmulti.zip')
        tables = {'test_reports': [
            {'id': 1, 'task_id': 21, 'name': 'a', 'type': 'task', 'status': 'published'},
            {'id': 2, 'task_id': 22, 'name': 'b', 'type': 'task', 'status': 'published'},
        ]}
        _write_package(zip_path, _manifest(), tables)
        result = data_transfer_import_service.import_report_package(zip_path)
        assert result['success'] is False
        assert result['code'] == 400
        assert result['data']['taskIds'] == [21, 22]
