# -*- coding: utf-8 -*-
"""INT-841 专项：评估维度/类别 CRUD 操作人 user_id 补写 + 用户上下文拦截器。

背景（INT-841）：categories / dimensions 表已有 created_by_user_id /
updated_by_user_id 列，但评估维度/类别 CRUD 从不写入；且 evaluation_service
gRPC server 未装 server_user_context_interceptor，即使写入也取不到上下文用户。

覆盖（验收标准）：
1. 建维度/类别后 DB 行 created_by_user_id = 当前用户；无上下文（AUTH_MODE=off
   等价）为 NULL，不硬编码 0 充当真实用户。
2. 更新/软删路径 updated_by_user_id / deleted_by_user_id 正确
   （含维度树形级联软删：主维度及其子维度均盖删除人）。
3. server_user_context_interceptor 装入后：网关 x-user-id metadata 经 contextvar
   落到仓储（intercept_service 单测验证 context 透传 + 行 created_by_user_id）。
4. 批量 enable/disable（维度管理更新）补盖 updated_by_user_id。

DB：进程级 SQLite（临时文件库，engine 直装全局 scoped_session），对齐
test_int145 口径。gRPC 委托（algorithm ACL 仓储）失败降级返回 False，不影响写路径。
"""
import os
import tempfile

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from sqlalchemy import create_engine

import pytest

import shared.models.database as database
from shared.infrastructure.user_context import (
    set_current_user_id, get_current_user_id, USER_ID_METADATA_KEY,
)
from evaluation_service.application.commands.evaluation_command_service import (
    EvaluationCommandService,
)
from evaluation_service.infrastructure.persistence.evaluation_repository import (
    DIMENSION_SORT_STEP,
)
from evaluation_service.infrastructure.persistence.orm_models import (
    Category,
    Dimension,
)


@pytest.fixture()
def db():
    """SQLite 临时文件库：engine 直装全局 scoped_session，仅建维度/分类表。"""
    from evaluation_service.infrastructure.persistence.orm_models import (
        Category as CatPO,
        Dimension as DimPO,
    )

    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    engine = create_engine(f'sqlite:///{path}',
                           connect_args={'check_same_thread': False})
    database.remove_db_session()
    database._engine = engine
    database._SessionFactory.configure(bind=engine)
    database.Base.metadata.create_all(engine, tables=[
        CatPO.__table__, DimPO.__table__,
    ])
    yield database
    database.remove_db_session()
    set_current_user_id(None)
    engine.dispose()
    try:
        os.remove(path)
    except PermissionError:
        pass


@pytest.fixture()
def svc(db):
    """EvaluationCommandService（写路径经 application → 仓储，操作人取自 context）。"""
    return EvaluationCommandService()


def _get(session, po_cls, po_id):
    return session.get(po_cls, po_id)


# ==================== 分类 CRUD 操作人 ====================

class TestCategoryOperatorColumns:
    """分类 create/update/delete 操作人（INT-841）。"""

    def test_create_sets_created_by(self, db, svc):
        set_current_user_id(101)
        result = svc.create_category({'name': 'int841-cat', 'description': 'd',
                                      'icon': 'icon1'})
        assert result['success'] is True, result
        session = db.get_db_session()
        try:
            po = _get(session, Category, result['data']['id'])
            assert po.created_by_user_id == 101
            assert po.updated_by_user_id is None   # create 不写 updated_by
            assert po.deleted_by_user_id is None
        finally:
            session.close()

    def test_update_sets_updated_by(self, db, svc):
        set_current_user_id(101)
        result = svc.create_category({'name': 'int841-cat-u', 'icon': 'icon1'})
        cat_id = result['data']['id']
        set_current_user_id(102)
        r2 = svc.update_category(cat_id, {'description': '改过'})
        assert r2['success'] is True, r2
        session = db.get_db_session()
        try:
            po = _get(session, Category, cat_id)
            assert po.updated_by_user_id == 102
            assert po.created_by_user_id == 101   # 创建人保持原值
        finally:
            session.close()

    def test_delete_sets_deleted_by(self, db, svc):
        set_current_user_id(101)
        result = svc.create_category({'name': 'int841-cat-d', 'icon': 'icon1'})
        cat_id = result['data']['id']
        set_current_user_id(103)
        r2 = svc.delete_category(cat_id)
        assert r2['success'] is True, r2
        session = db.get_db_session()
        try:
            po = _get(session, Category, cat_id)
            assert po.deleted is True
            assert po.deleted_by_user_id == 103
            assert po.deleted_at is not None
            assert po.created_by_user_id == 101
        finally:
            session.close()

    def test_no_context_columns_null(self, db, svc):
        """无认证上下文（AUTH_MODE=off 等价）：操作人列 NULL，不硬编码 0。"""
        set_current_user_id(None)
        result = svc.create_category({'name': 'int841-cat-n', 'icon': 'icon1'})
        assert result['success'] is True, result
        cat_id = result['data']['id']
        assert svc.delete_category(cat_id)['success'] is True
        session = db.get_db_session()
        try:
            po = _get(session, Category, cat_id)
            assert po.created_by_user_id is None
            assert po.deleted_by_user_id is None
        finally:
            session.close()


# ==================== 维度 CRUD 操作人 ====================

class TestDimensionOperatorColumns:
    """维度 create/update/delete 操作人（INT-841）。"""

    def _create(self, svc, name='int841-dim'):
        return svc.create_dimension({
            'name': name, 'type': 'auto', 'result_type': 1,
        })

    def test_create_sets_created_by(self, db, svc):
        set_current_user_id(201)
        result = self._create(svc)
        assert result['success'] is True, result
        session = db.get_db_session()
        try:
            po = _get(session, Dimension, result['data']['id'])
            assert po.created_by_user_id == 201
            assert po.updated_by_user_id is None
            assert po.deleted_by_user_id is None
        finally:
            session.close()

    def test_update_sets_updated_by(self, db, svc):
        set_current_user_id(201)
        result = self._create(svc)
        dim_id = result['data']['id']
        set_current_user_id(202)
        r2 = svc.update_dimension(dim_id, {'name': 'int841-dim-改'})
        assert r2['success'] is True, r2
        session = db.get_db_session()
        try:
            po = _get(session, Dimension, dim_id)
            assert po.name == 'int841-dim-改'
            assert po.updated_by_user_id == 202
            assert po.created_by_user_id == 201
        finally:
            session.close()

    def test_delete_cascades_deleted_by_to_subs(self, db, svc):
        """树形级联软删：主维度及其子维度均盖删除人。"""
        session = db.get_db_session()
        set_current_user_id(201)
        main = Dimension(name='int841-main', dimension_type='main',
                         type='auto', result_type=1, sort_order=0, status=True)
        sub = Dimension(name='int841-sub', dimension_type='sub',
                        type='auto', result_type=1, sort_order=1, status=True)
        session.add_all([main, sub])
        session.flush()
        sub.parent_dimension_id = main.id
        session.commit()
        main_id, sub_id = main.id, sub.id
        db.remove_db_session()

        set_current_user_id(203)
        result = svc.delete_dimension(main_id)
        assert result['success'] is True, result
        session = db.get_db_session()
        try:
            assert _get(session, Dimension, main_id).deleted is True
            assert _get(session, Dimension, main_id).deleted_by_user_id == 203
            assert _get(session, Dimension, sub_id).deleted is True
            assert _get(session, Dimension, sub_id).deleted_by_user_id == 203
        finally:
            session.close()

    def test_batch_enable_sets_updated_by(self, db, svc):
        """批量 enable/disable（维度管理更新）补盖 updated_by_user_id。"""
        session = db.get_db_session()
        main = Dimension(name='int841-b', dimension_type='main',
                         type='auto', result_type=1, sort_order=0, status=True)
        session.add(main)
        session.commit()
        main_id = main.id
        db.remove_db_session()

        set_current_user_id(204)
        result = svc.batch_action({'ids': [main_id], 'action': 'disable'})
        assert result['success'] is True, result
        session = db.get_db_session()
        try:
            po = _get(session, Dimension, main_id)
            assert po.status is False
            assert po.updated_by_user_id == 204
        finally:
            session.close()

    def test_no_context_columns_null(self, db, svc):
        """无认证上下文：维度三列 NULL。"""
        set_current_user_id(None)
        result = self._create(svc, 'int841-dim-n')
        assert result['success'] is True, result
        dim_id = result['data']['id']
        assert svc.delete_dimension(dim_id)['success'] is True
        session = db.get_db_session()
        try:
            po = _get(session, Dimension, dim_id)
            assert po.created_by_user_id is None
            assert po.deleted_by_user_id is None
        finally:
            session.close()


# ==================== 服务端用户上下文拦截器 ====================

class TestServerUserContextInterceptor:
    """server_user_context_interceptor：x-user-id metadata → contextvar → 仓储落库。"""

    def _continuation(self, behavior):
        class FakeHandler:
            def __init__(self):
                # 实例属性赋值（类属性会被 descriptor 绑定成 bound method，
                # 导致 _wrap_rpc_handler 取到 (self, request, context) 三参调用）
                self.unary_unary = behavior
                self.stream_unary = None
                self.unary_stream = None
                self.stream_stream = None
                self.request_deserializer = None
                self.response_serializer = None

        def continuation(_details):
            return FakeHandler()

        return continuation

    class _Context:
        def __init__(self, metadata):
            self._metadata = metadata

        def invocation_metadata(self):
            return self._metadata

    def test_x_user_id_metadata_reaches_repository(self, db):
        """网关 x-user-id metadata 经拦截器落到 contextvar，create 落 created_by。"""
        from shared.infrastructure.grpc_interceptors import (
            server_user_context_interceptor,
        )

        captured = {}

        def behavior(request, context):
            captured['context_user_id'] = get_current_user_id()
            # 真实仓储写路径：操作人取自拦截器设置的 contextvar
            from evaluation_service.infrastructure.persistence.evaluation_repository import (
                evaluation_repository,
            )
            dim = evaluation_repository.create_dimension({
                'name': 'int841-interceptor', 'type': 'auto', 'result_type': 1,
            })
            captured['dim_id'] = dim.id
            return 'ok'

        details = type('Details', (), {'method': '/EvaluationConfigService/CreateDimension'})()
        wrapped = server_user_context_interceptor.intercept_service(
            self._continuation(behavior), details)
        result = wrapped.unary_unary(None, self._Context(
            (('content-type', 'application/grpc'),
             (USER_ID_METADATA_KEY, '777'))))

        assert result == 'ok'
        assert captured['context_user_id'] == 777
        # RPC 结束清理 contextvar（线程池线程复用防串号）
        assert get_current_user_id() is None

        session = db.get_db_session()
        try:
            po = _get(session, Dimension, captured['dim_id'])
            assert po.created_by_user_id == 777
        finally:
            session.close()

    def test_no_metadata_clears_context(self, db):
        """无 x-user-id metadata：context 内 get_current_user_id() 为 None。"""
        from shared.infrastructure.grpc_interceptors import (
            server_user_context_interceptor,
        )
        set_current_user_id(999)  # 模拟线程池残留，拦截器应清掉
        captured = {}

        def behavior(request, context):
            captured['context_user_id'] = get_current_user_id()
            return 'ok'

        details = type('Details', (), {'method': '/EvaluationConfigService/ListDimensions'})()
        wrapped = server_user_context_interceptor.intercept_service(
            self._continuation(behavior), details)
        wrapped.unary_unary(None, self._Context(()))
        assert captured['context_user_id'] is None
        assert get_current_user_id() is None
