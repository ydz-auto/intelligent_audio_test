# -*- coding: utf-8 -*-
"""INT-2236（P1）专项：报告二次对比越权读取他人私有 / 已软删报告用例。

缺陷：二次对比在校验源报告时用 get_report_by_id_raw（无 visibility、无 deleted
过滤）读 PO，随后 _get_source_cases_from_reports 把其中的用例名称/结果/评分复制
进新报告。持有 report:compare 的用户传他人私有或已软删报告 ID，即可越权读出内容。

修复口径：
1. 源报告改走仓储 get_report_by_id_visible（软删 + 行级可见性过滤）；
2. 任一报告不存在 / 已软删 / 私有非 owner → 整批拒绝，不做「跳过不可见行、
   剩余凑够两个就放行」；
3. 提交前同步校验，直接回明确错误（HTTP 404），不进线程池、不建报告；
   异步线程按同一助手复核（防提交后被删/收回）。

DB：进程级 SQLite 文件库（对齐 test_int465_visibility_report_evaluation.py 的
engine 直装全局 scoped_session 模式），用例内建表/清理。
"""
import os
import tempfile

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from sqlalchemy import create_engine

import shared.models.database as database
from shared.infrastructure.user_context import (
    set_current_user_id,
    set_current_user_is_admin,
)

USER_A = 1001
USER_B = 1002
DENIED_HINT = '报告不存在或无权访问'


def _create_tables(engine):
    from report_service.infrastructure.persistence.models import (
        Report,
        ReportSummary,
    )
    database.Base.metadata.create_all(engine, tables=[
        Report.__table__, ReportSummary.__table__,
    ])


@pytest.fixture()
def db():
    """SQLite 临时文件库：engine 直装全局 scoped_session。"""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    engine = create_engine(f'sqlite:///{path}',
                           connect_args={'check_same_thread': False})
    database.remove_db_session()
    database._engine = engine
    database._SessionFactory.configure(bind=engine)
    _create_tables(engine)
    yield database
    database.remove_db_session()
    set_current_user_id(None)
    set_current_user_is_admin(False)
    engine.dispose()
    try:
        os.remove(path)
    except PermissionError:
        pass


@pytest.fixture(autouse=True)
def _clean_context():
    set_current_user_id(None)
    set_current_user_is_admin(False)
    yield
    set_current_user_id(None)
    set_current_user_is_admin(False)


def _make_report(session, name, created_by, visibility='shared',
                 task_id=None, deleted=False):
    """直接写 Report PO（绕过仓储，精确控制 owner/visibility/deleted）。"""
    from report_service.infrastructure.persistence.models import Report
    po = Report(name=name, type='task', status='completed', task_id=task_id,
                created_by_user_id=created_by, visibility=visibility,
                deleted=deleted)
    session.add(po)
    session.flush()
    return po.id


def _seed(db, rows):
    session = db.get_db_session()
    ids = [_make_report(session, **row) for row in rows]
    session.commit()
    db.remove_db_session()
    return ids


class TestVisibleSourceReportRead:
    """仓储读源报告：软删 + 行级可见性过滤。"""

    def test_owner_and_shared_reports_readable(self, db):
        rid_a, rid_b = _seed(db, [
            {'name': 'A共享', 'created_by': USER_A, 'visibility': 'shared'},
            {'name': 'B共享', 'created_by': USER_B, 'visibility': 'shared'},
        ])
        from report_service.application.services.report_compare_helpers import (
            ReportCompareHelpers,
        )

        set_current_user_id(USER_B)
        reports, error = ReportCompareHelpers._load_secondary_source_reports(
            [rid_a, rid_b])

        assert error is None
        assert [r.id for r in reports] == [rid_a, rid_b]

    def test_private_report_of_other_user_denied_whole_batch(self, db):
        """私有非 owner：整批拒绝，不因另一条可见就放行。"""
        rid_private, rid_shared = _seed(db, [
            {'name': 'A私有', 'created_by': USER_A, 'visibility': 'private'},
            {'name': 'A共享', 'created_by': USER_A, 'visibility': 'shared'},
        ])
        from report_service.application.services.report_compare_helpers import (
            ReportCompareHelpers,
        )

        set_current_user_id(USER_B)
        reports, error = ReportCompareHelpers._load_secondary_source_reports(
            [rid_private, rid_shared])

        assert reports is None
        assert error == f'{DENIED_HINT}: {rid_private}'

    def test_owner_can_read_own_private_report(self, db):
        rid_private = _seed(db, [
            {'name': 'A私有', 'created_by': USER_A, 'visibility': 'private'},
        ])[0]
        from report_service.application.services.report_compare_helpers import (
            ReportCompareHelpers,
        )

        set_current_user_id(USER_A)
        reports, error = ReportCompareHelpers._load_secondary_source_reports(
            [rid_private])

        assert error is None
        assert [r.id for r in reports] == [rid_private]

    def test_soft_deleted_report_denied(self, db):
        rid_deleted, rid_ok = _seed(db, [
            {'name': '已软删', 'created_by': USER_A, 'visibility': 'shared',
             'deleted': True},
            {'name': '正常', 'created_by': USER_A, 'visibility': 'shared'},
        ])
        from report_service.application.services.report_compare_helpers import (
            ReportCompareHelpers,
        )

        set_current_user_id(USER_A)  # owner 自己也读不到已软删报告
        reports, error = ReportCompareHelpers._load_secondary_source_reports(
            [rid_deleted, rid_ok])

        assert reports is None
        assert error == f'{DENIED_HINT}: {rid_deleted}'

    def test_missing_report_denied(self, db):
        from report_service.application.services.report_compare_helpers import (
            ReportCompareHelpers,
        )

        set_current_user_id(USER_A)
        reports, error = ReportCompareHelpers._load_secondary_source_reports(
            [987654321])

        assert reports is None
        assert error == f'{DENIED_HINT}: 987654321'

    def test_admin_exempt_from_visibility(self, db):
        rid_private = _seed(db, [
            {'name': 'A私有', 'created_by': USER_A, 'visibility': 'private'},
        ])[0]
        from report_service.application.services.report_compare_helpers import (
            ReportCompareHelpers,
        )

        set_current_user_id(USER_B)
        set_current_user_is_admin(True)
        reports, error = ReportCompareHelpers._load_secondary_source_reports(
            [rid_private])

        assert error is None
        assert [r.id for r in reports] == [rid_private]

    def test_raw_read_still_used_by_generation_engine(self, db):
        """对照：生成引擎口径的 raw 读取不参与本链路，仅证明两者口径差异。"""
        rid_private = _seed(db, [
            {'name': 'A私有', 'created_by': USER_A, 'visibility': 'private'},
        ])[0]
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        set_current_user_id(USER_B)
        assert report_repository.get_report_by_id_visible(rid_private) is None
        assert report_repository.get_report_by_id_raw(rid_private) is not None


class TestValidateReportsAndGetTasks:
    """校验失败必须在复制用例之前整批返回，不调用任务/用例读取。"""

    def test_denied_report_returns_error_before_any_copy(self, db, monkeypatch):
        rid_private, rid_shared = _seed(db, [
            {'name': 'A私有', 'created_by': USER_A, 'visibility': 'private',
             'task_id': 501},
            {'name': 'A共享', 'created_by': USER_A, 'visibility': 'shared',
             'task_id': 502},
        ])
        import report_service.application.services.report_compare_helpers as rch

        def _boom(task_ids):
            raise AssertionError('越权请求不得进入任务/用例读取')

        monkeypatch.setattr(rch, '_grpc_get_tasks_by_ids', _boom)

        set_current_user_id(USER_B)
        reports, tasks, task_ids, error = (
            rch.ReportCompareHelpers._validate_reports_and_get_tasks(
                [rid_private, rid_shared]))

        assert (reports, tasks, task_ids) == (None, None, None)
        assert error == f'{DENIED_HINT}: {rid_private}'

    def test_visible_reports_still_resolve_tasks(self, db, monkeypatch):
        """正常 owner 链路不回归：可见报告照常解析任务。"""
        rid1, rid2 = _seed(db, [
            {'name': 'A1', 'created_by': USER_A, 'visibility': 'private',
             'task_id': 501},
            {'name': 'A2', 'created_by': USER_A, 'visibility': 'private',
             'task_id': 502},
        ])
        import report_service.application.services.report_compare_helpers as rch

        monkeypatch.setattr(
            rch, '_grpc_get_tasks_by_ids',
            lambda task_ids: [{'id': tid, 'status': 'completed'}
                              for tid in task_ids])

        set_current_user_id(USER_A)
        reports, tasks, task_ids, error = (
            rch.ReportCompareHelpers._validate_reports_and_get_tasks([rid1, rid2]))

        assert error is None
        assert [r.id for r in reports] == [rid1, rid2]
        assert sorted(task_ids) == [501, 502]
        assert len(tasks) == 2


class TestSecondaryCompareSubmit:
    """提交前同步校验：不可见的源报告不进线程池、不建报告。"""

    def test_denied_report_rejected_without_submit(self, db, monkeypatch):
        rid_private, rid_shared = _seed(db, [
            {'name': 'A私有', 'created_by': USER_A, 'visibility': 'private'},
            {'name': 'A共享', 'created_by': USER_A, 'visibility': 'shared'},
        ])
        import report_service.application.services.report_compare_generator as gen

        def _boom(*args, **kwargs):
            raise AssertionError('越权请求不得进入异步生成')

        monkeypatch.setattr(gen, '_submit_secondary_generation', _boom)

        set_current_user_id(USER_B)
        result = gen.ReportCompareGenerator.secondary_compare(
            [rid_private, rid_shared])

        assert result['success'] is False
        assert result['code'] == 404
        assert result['message'] == f'{DENIED_HINT}: {rid_private}'
        # 去重标记未被占用，后续合法请求不受影响
        assert tuple(sorted([rid_private, rid_shared])) not in gen._generating_secondary

    def test_owner_submit_unchanged(self, db, monkeypatch):
        rid1, rid2 = _seed(db, [
            {'name': 'A1', 'created_by': USER_A, 'visibility': 'private'},
            {'name': 'A2', 'created_by': USER_A, 'visibility': 'private'},
        ])
        import report_service.application.services.report_compare_generator as gen

        submitted = {}

        def _fake_submit(report_ids, report_key, description):
            submitted['ids'] = list(report_ids)
            return True

        monkeypatch.setattr(gen, '_submit_secondary_generation', _fake_submit)

        set_current_user_id(USER_A)
        try:
            result = gen.ReportCompareGenerator.secondary_compare([rid1, rid2])
        finally:
            gen._generating_secondary.pop(tuple(sorted([rid1, rid2])), None)

        assert result['success'] is True
        assert result['data']['status'] == 'generating'
        assert submitted['ids'] == [rid1, rid2]


class TestGrpcResponseBusinessCode:
    """gRPC 层把「源报告不可读」的业务码 404 折进 data，供网关提升 HTTP 状态。"""

    def test_denied_error_folds_404_code_into_data(self):
        from shared.utils.grpc_json import dumps as _dumps, loads as _loads
        from report_service.interfaces.grpc import servicers as svc

        class _FakeHandler:
            @staticmethod
            def handle_generate_secondary_compare_report(report_ids, description=None):
                return {
                    'success': False,
                    'data': None,
                    'message': f'{DENIED_HINT}: 12',
                    'code': 404,
                }

        servicer = svc.ReportServicer()
        servicer._command_handler = _FakeHandler()

        resp = servicer.GenerateSecondaryCompareReport(
            svc.report_pb.GenerateSecondaryCompareReportRequest(
                data=_dumps({'report_ids': [12, 13]})))

        assert resp.success is False
        assert resp.message == f'{DENIED_HINT}: 12'
        assert (_loads(resp.data, {}) or {}).get('code') == 404

