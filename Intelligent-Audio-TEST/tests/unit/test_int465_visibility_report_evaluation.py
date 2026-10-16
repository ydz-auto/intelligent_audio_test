# -*- coding: utf-8 -*-
"""INT-465 专项：report + evaluation 域数据可见性（INT-423 体系）。

验收口径对齐原卡：
1. 私有报告 / 维度 / 分类非 owner 列表不可见、详情 404、写 403；owner 全操作
2. 共享零回归（共享资源对任意用户可见，含未认证）
3. 报告 7 子表跟随父报告可见性（子表无独立列，父报告可见则子表数据可读）
4. 批量逐行过滤（filter_visible_owners 口径：私有非 owner 行跳过，不整批放行）

DB：进程级 SQLite 文件库（对齐 test_int145_dimension_batch_cascade.py 的
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
from shared.infrastructure.visibility_filter import VisibilityDenied

USER_A = 1001
USER_B = 1002


def _create_tables(engine):
    """建齐本专项涉及的 report/evaluation 表。"""
    from report_service.infrastructure.persistence.models import (
        Report,
        ReportSummary,
        ReportSummaryMeta,
        ReportRawData,
        ReportCase,
        ReportMetricStats,
        ReportComparisonMatrix,
        ReportFavorite,
    )
    from evaluation_service.infrastructure.persistence.orm_models import (
        Category,
        Dimension,
    )
    database.Base.metadata.create_all(engine, tables=[
        Report.__table__, ReportSummary.__table__, ReportSummaryMeta.__table__,
        ReportRawData.__table__, ReportCase.__table__,
        ReportMetricStats.__table__, ReportComparisonMatrix.__table__,
        ReportFavorite.__table__,
        Category.__table__, Dimension.__table__,
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
    """每个用例开始前清空 user context（防跨用例残留）。"""
    set_current_user_id(None)
    set_current_user_is_admin(False)
    yield
    set_current_user_id(None)
    set_current_user_is_admin(False)


def _make_report(session, name, created_by, visibility='shared', task_id=None):
    """直接写 Report PO（绕过仓储，精确控制 owner/visibility）。"""
    from report_service.infrastructure.persistence.models import Report
    po = Report(name=name, type='task', status='completed', task_id=task_id,
                created_by_user_id=created_by, visibility=visibility)
    session.add(po)
    session.flush()
    return po.id


def _make_dimension(session, name, created_by, visibility='shared'):
    """直接写 Dimension PO。"""
    from evaluation_service.infrastructure.persistence.orm_models import Dimension
    po = Dimension(name=name, type='auto', result_type=1,
                   created_by_user_id=created_by, visibility=visibility)
    session.add(po)
    session.flush()
    return po.id


def _make_category(session, name, created_by, visibility='shared'):
    """直接写 Category PO。"""
    from evaluation_service.infrastructure.persistence.orm_models import Category
    po = Category(name=name, icon='icon', created_by_user_id=created_by,
                  visibility=visibility)
    session.add(po)
    session.flush()
    return po.id


# ==================== report_service：私有隔离 / 共享零回归 ====================

class TestReportVisibility:
    """验收①私有报告 + 验收②共享零回归（report 域）。"""

    def test_private_report_hidden_from_non_owner(self, db):
        """非 owner 列表不可见 / 详情 404 / 更新删除 403。"""
        session = db.get_db_session()
        rid_private = _make_report(session, 'A私有报告', USER_A, 'private')
        rid_shared = _make_report(session, 'B共享报告', USER_B, 'shared')
        rid_task_private = _make_report(session, 'A私有任务报告', USER_A, 'private', task_id=501)
        rid_task_shared = _make_report(session, 'B共享任务报告', USER_B, 'shared', task_id=502)
        session.commit()
        db.remove_db_session()

        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )
        from report_service.application.handlers.report_handlers import (
            ReportCommandHandler,
            ReportQueryHandler,
        )

        set_current_user_id(USER_B)  # 非 owner 视角

        # 列表：A 私有报告不可见，B 共享报告可见
        ids = [r.id for r in report_repository.list_reports(page=1, page_size=20)]
        assert rid_private not in ids
        assert rid_shared in ids

        # 详情：私有非 owner 按不存在处理（404 语义）；按任务取最新报告同样 404
        assert report_repository.get_by_id(rid_private) is None
        assert ReportQueryHandler().handle_get(
            _get_report_query(rid_private)) is None
        assert report_repository.get_by_task(501) is None
        assert report_repository.get_by_task(502) is not None

        # 写操作：私有非 owner 抛 VisibilityDenied（403 语义）
        cmd = ReportCommandHandler()
        with pytest.raises(VisibilityDenied):
            cmd.handle_update(_get_report_command(rid_private, name='篡改'))
        with pytest.raises(VisibilityDenied):
            cmd.handle_delete(_get_report_command(rid_private))

        # 共享报告对非 owner 可读可写（回落既有权限语义，行级不设卡）
        assert report_repository.get_by_id(rid_shared) is not None
        assert cmd.handle_update(_get_report_command(rid_shared, name='B改')) is True

    def test_owner_full_ops_and_admin_exempt(self, db):
        """owner 全操作；admin 跨过私有过滤全量可见可写。"""
        session = db.get_db_session()
        rid_private = _make_report(session, 'A私有报告', USER_A, 'private')
        session.commit()
        db.remove_db_session()

        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )
        from report_service.application.handlers.report_handlers import (
            ReportCommandHandler,
        )

        # owner 视角：列表可见 / 详情可读 / 更新删除可操作
        set_current_user_id(USER_A)
        assert rid_private in [r.id for r in
                               report_repository.list_reports(page=1, page_size=20)]
        assert report_repository.get_by_id(rid_private) is not None
        cmd = ReportCommandHandler()
        assert cmd.handle_update(_get_report_command(rid_private, name='A自改')) is True
        assert cmd.handle_delete(_get_report_command(rid_private)) is True

        # admin 视角：私有报告全量可见
        session = db.get_db_session()
        rid_private2 = _make_report(session, 'A私有报告2', USER_A, 'private')
        session.commit()
        db.remove_db_session()
        set_current_user_id(USER_B)
        set_current_user_is_admin(True)
        assert rid_private2 in [r.id for r in
                                report_repository.list_reports(page=1, page_size=20)]
        assert report_repository.get_by_id(rid_private2) is not None

    def test_report_sub_tables_follow_parent(self, db):
        """验收③：报告 7 子表不单独设列——父报告可见则摘要子表数据可读。"""
        session = db.get_db_session()
        rid = _make_report(session, 'A私有报告', USER_A, 'private')
        from report_service.infrastructure.persistence.models import ReportSummary
        # SQLite 下 BigInteger 主键不自增，显式给 id（仅测试用）
        session.add(ReportSummary(id=1, report_id=rid, total_cases=3, pass_rate=0.9))
        session.commit()
        db.remove_db_session()

        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        # 非 owner 不可见（详情 404）
        set_current_user_id(USER_B)
        assert report_repository.get_by_id(rid) is None

        # owner 可见，子表数据随父报告可读（子表无独立可见性列）
        set_current_user_id(USER_A)
        agg = report_repository.get_by_id(rid)
        assert agg is not None
        summaries = report_repository.load_summaries(rid)
        # 摘要子表行存在且被加载（无独立可见性列，跟随父报告）
        assert summaries and summaries[0].report_id == rid

    def test_batch_delete_filters_invisible_rows(self, db):
        """验收④：批量删除逐行过滤——私有非 owner 行跳过，共享行删除。"""
        session = db.get_db_session()
        rid_private = _make_report(session, 'A私有报告', USER_A, 'private')
        rid_shared = _make_report(session, 'B共享报告', USER_B, 'shared')
        session.commit()
        db.remove_db_session()

        from shared.proto import report_service_pb2 as report_pb
        from report_service.interfaces.grpc.servicers import ReportServicer

        set_current_user_id(USER_B)
        resp = ReportServicer().BatchActionReports(
            report_pb.BatchActionReportsRequest(
                data='{"ids": [%d, %d], "action": "delete"}' % (rid_private, rid_shared)),
            context=None)
        assert resp.success is True
        import json
        data = json.loads(resp.data)
        by_id = {i['report_id']: i['deleted'] for i in data['items']}
        # 私有非 owner 行跳过（deleted=False），共享行删除
        assert by_id[rid_private] is False
        assert by_id[rid_shared] is True


# ==================== evaluation_service：维度 / 分类可见性 ====================

class TestEvaluationDimensionVisibility:
    """验收①私有维度隔离 + 验收②共享零回归（evaluation 域）。"""

    def test_private_dimension_hidden_from_non_owner(self, db):
        """非 owner 列表不可见 / 详情 404 / 更新删除 403。"""
        from evaluation_service.application.queries.evaluation_query_service import (
            evaluation_query_service,
        )
        from evaluation_service.application.commands.evaluation_command_service import (
            evaluation_command_service,
        )

        session = db.get_db_session()
        dim_private = _make_dimension(session, 'A私有维度', USER_A, 'private')
        dim_shared = _make_dimension(session, 'B共享维度', USER_B, 'shared')
        session.commit()
        db.remove_db_session()

        set_current_user_id(USER_B)

        # 列表：A 私有维度不可见，B 共享维度可见
        listed = evaluation_query_service.list_dimensions(
            page=1, per_page=50)['data']['items']
        listed_ids = {i['id'] for i in listed}
        assert dim_private not in listed_ids
        assert dim_shared in listed_ids

        # 详情：私有非 owner 404
        detail = evaluation_query_service.get_dimension(dim_private)
        assert detail['success'] is False and detail.get('code') == 404

        # 写操作：私有非 owner 403
        upd = evaluation_command_service.update_dimension(
            dim_private, {'name': '篡改'})
        assert upd['success'] is False and upd.get('code') == 403
        dele = evaluation_command_service.delete_dimension(dim_private)
        assert dele['success'] is False and dele.get('code') == 403

        # 共享维度对非 owner 可读可写
        assert evaluation_query_service.get_dimension(dim_shared)['success'] is True
        assert evaluation_command_service.update_dimension(
            dim_shared, {'name': 'B共享维度改'})['success'] is True

    def test_owner_full_ops_and_admin_exempt(self, db):
        """owner 全操作；admin 跨过过滤。"""
        from evaluation_service.application.queries.evaluation_query_service import (
            evaluation_query_service,
        )
        from evaluation_service.application.commands.evaluation_command_service import (
            evaluation_command_service,
        )

        session = db.get_db_session()
        dim_private = _make_dimension(session, 'A私有维度', USER_A, 'private')
        session.commit()
        db.remove_db_session()

        # owner 视角
        set_current_user_id(USER_A)
        listed_ids = {i['id'] for i in
                      evaluation_query_service.list_dimensions(
                          page=1, per_page=50)['data']['items']}
        assert dim_private in listed_ids
        assert evaluation_query_service.get_dimension(dim_private)['success'] is True
        assert evaluation_command_service.update_dimension(
            dim_private, {'name': 'A自改'})['success'] is True

        # admin 视角（列表全量 + 详情可读）
        session = db.get_db_session()
        dim_private2 = _make_dimension(session, 'A私有维度2', USER_A, 'private')
        session.commit()
        db.remove_db_session()
        set_current_user_id(USER_B)
        set_current_user_is_admin(True)
        listed_ids = {i['id'] for i in
                      evaluation_query_service.list_dimensions(
                          page=1, per_page=50)['data']['items']}
        assert dim_private2 in listed_ids
        assert evaluation_query_service.get_dimension(dim_private2)['success'] is True

    def test_batch_action_filters_invisible_dimension(self, db):
        """验收④：batch delete 逐行过滤——私有非 owner 维度不被删除。"""
        from evaluation_service.application.commands.evaluation_command_service import (
            evaluation_command_service,
        )

        session = db.get_db_session()
        dim_private = _make_dimension(session, 'A私有维度', USER_A, 'private')
        dim_shared = _make_dimension(session, 'B共享维度', USER_B, 'shared')
        session.commit()
        db.remove_db_session()

        set_current_user_id(USER_B)
        result = evaluation_command_service.batch_action(
            {'ids': [dim_private, dim_shared], 'action': 'delete'})
        assert result['success'] is True

        from evaluation_service.infrastructure.persistence.orm_models import Dimension
        session = db.get_db_session()
        try:
            po_private = session.get(Dimension, dim_private)
            po_shared = session.get(Dimension, dim_shared)
            # 私有非 owner 维度未被删除；共享维度被软删
            assert po_private.deleted is False
            assert po_shared.deleted is True
        finally:
            db.remove_db_session()

    def test_create_with_visibility(self, db):
        """新建维度/分类可指定 private；非法值 400。"""
        from evaluation_service.application.commands.evaluation_command_service import (
            evaluation_command_service,
        )

        set_current_user_id(USER_A)
        ok = evaluation_command_service.create_dimension(
            {'name': '新建私有维度', 'type': 'auto', 'result_type': 1,
             'visibility': 'private'})
        assert ok['success'] is True
        bad = evaluation_command_service.create_dimension(
            {'name': '非法可见性', 'type': 'auto', 'result_type': 1,
             'visibility': 'team'})
        assert bad['success'] is False and bad.get('code') == 400

    def test_shared_visible_to_anonymous(self, db):
        """验收②：共享资源对未认证用户可见（guest 视角零回归）。"""
        from evaluation_service.application.queries.evaluation_query_service import (
            evaluation_query_service,
        )
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        session = db.get_db_session()
        dim_shared = _make_dimension(session, 'B共享维度', USER_B, 'shared')
        rid_shared = _make_report(session, 'B共享报告', USER_B, 'shared')
        session.commit()
        db.remove_db_session()

        set_current_user_id(None)  # 未认证
        listed_ids = {i['id'] for i in
                      evaluation_query_service.list_dimensions(
                          page=1, per_page=50)['data']['items']}
        assert dim_shared in listed_ids
        assert rid_shared in [r.id for r in
                              report_repository.list_reports(page=1, page_size=20)]


class TestEvaluationCategoryVisibility:
    """验收①私有分类隔离 + 共享零回归（evaluation 域）。"""

    def test_private_category_hidden_from_non_owner(self, db):
        """非 owner 列表不可见 / 更新删除 403。"""
        from evaluation_service.application.queries.evaluation_query_service import (
            evaluation_query_service,
        )
        from evaluation_service.application.commands.evaluation_command_service import (
            evaluation_command_service,
        )

        session = db.get_db_session()
        cat_private = _make_category(session, 'A私有分类', USER_A, 'private')
        cat_shared = _make_category(session, 'B共享分类', USER_B, 'shared')
        session.commit()
        db.remove_db_session()

        set_current_user_id(USER_B)
        listed_ids = {i['id'] for i in
                      evaluation_query_service.list_categories()['data']['items']}
        assert cat_private not in listed_ids
        assert cat_shared in listed_ids

        upd = evaluation_command_service.update_category(
            cat_private, {'name': '篡改'})
        assert upd['success'] is False and upd.get('code') == 403
        dele = evaluation_command_service.delete_category(cat_private)
        assert dele['success'] is False and dele.get('code') == 403

        # 共享分类对非 owner 可写
        assert evaluation_command_service.update_category(
            cat_shared, {'name': 'B共享分类改'})['success'] is True

    def test_owner_full_ops(self, db):
        """owner 全操作。"""
        from evaluation_service.application.queries.evaluation_query_service import (
            evaluation_query_service,
        )
        from evaluation_service.application.commands.evaluation_command_service import (
            evaluation_command_service,
        )

        session = db.get_db_session()
        cat_private = _make_category(session, 'A私有分类', USER_A, 'private')
        session.commit()
        db.remove_db_session()

        set_current_user_id(USER_A)
        listed_ids = {i['id'] for i in
                      evaluation_query_service.list_categories()['data']['items']}
        assert cat_private in listed_ids
        assert evaluation_command_service.update_category(
            cat_private, {'name': 'A自改'})['success'] is True
        assert evaluation_command_service.delete_category(
            cat_private)['success'] is True


# ==================== 辅助构造 ====================

def _get_report_query(report_id):
    from report_service.application.queries.report_queries import GetReportQuery
    return GetReportQuery(report_id=report_id)


def _get_report_command(report_id, name=None):
    from report_service.application.commands.report_commands import (
        DeleteReportCommand,
        UpdateReportCommand,
    )
    if name is not None:
        return UpdateReportCommand(report_id=report_id, name=name)
    return DeleteReportCommand(report_id=report_id)
