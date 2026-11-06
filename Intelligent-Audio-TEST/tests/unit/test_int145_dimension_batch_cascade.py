# -*- coding: utf-8 -*-
"""INT-145 缺陷包 3/4：评估维度批量操作丢级联 + 排序/导入导出丢父子语义。

缺陷3（批量操作丢级联·严重）：修复前 dimensions/batch 的 delete 走
batch_update({'deleted': True}) 平铺处理、enable/disable 不扩展目标集合
——删主维度留孤儿子维度。修复后 delete 逐个树形级联软删（对齐旧库
_soft_delete_tree），enable/disable 目标集合扩展为选中维度及全部后代
（对齐旧库 _collect_descendant_ids 主/子联动）。

缺陷4（排序/导入导出丢父子语义）：修复前 reorder 平铺下标编码，丢失旧库
主/子分段编码（SORT_STEP=1000）。修复后主维度占独立段、子维度挂父段内
（父段值 + 组内序号）。
"""
import os
import tempfile

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from sqlalchemy import create_engine

import pytest

import shared.models.database as database
from evaluation_service.application.commands.evaluation_command_service import (
    EvaluationCommandService,
)
from evaluation_service.infrastructure.persistence.evaluation_repository import (
    DIMENSION_SORT_STEP,
    evaluation_repository,
)


@pytest.fixture()
def db():
    """SQLite 临时文件库：engine 直装全局 scoped_session，仅建维度/分类表。

    建库前先清掉本线程可能残留的旧 session（前一测试未 remove 时
    scoped_session 会复用绑在旧 engine 上的 session，查询落到旧库）。
    """
    from evaluation_service.infrastructure.persistence.orm_models import (
        Category,
        Dimension,
    )

    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    engine = create_engine(f'sqlite:///{path}',
                           connect_args={'check_same_thread': False})
    database.remove_db_session()
    database._engine = engine
    database._SessionFactory.configure(bind=engine)
    database.Base.metadata.create_all(engine, tables=[
        Category.__table__, Dimension.__table__,
    ])
    yield database
    database.remove_db_session()
    engine.dispose()
    # 尽力清理：发布维度配置事件会唤醒后台监听线程持连接，Windows 下
    # 文件可能仍被占用，删除失败不作为用例失败（临时目录由系统回收）
    try:
        os.remove(path)
    except PermissionError:
        pass


@pytest.fixture()
def svc(db):
    """EvaluationCommandService，依赖 api_gateway 的统计缓存刷新降级路径。"""
    return EvaluationCommandService()


def _seed_tree(session):
    """两棵主子树：main1(sub1, sub2) / main2(sub3)。返回 id 映射。"""
    from evaluation_service.infrastructure.persistence.orm_models import Dimension

    main1 = Dimension(name='主维度1', dimension_type='main', sort_order=0,
                      type='auto', result_type=1, category_id=1, status=True)
    sub1 = Dimension(name='子维度1', dimension_type='sub',
                     parent_dimension_id=None, type='auto', result_type=1,
                     category_id=1, status=True, sort_order=1)
    sub2 = Dimension(name='子维度2', dimension_type='sub',
                     parent_dimension_id=None, type='auto', result_type=1,
                     category_id=1, status=True, sort_order=2)
    main2 = Dimension(name='主维度2', dimension_type='main',
                      sort_order=DIMENSION_SORT_STEP, type='auto', result_type=1,
                      category_id=1, status=True)
    sub3 = Dimension(name='子维度3', dimension_type='sub',
                     parent_dimension_id=None, type='auto', result_type=1,
                     category_id=1, status=True, sort_order=DIMENSION_SORT_STEP + 1)
    session.add_all([main1, sub1, sub2, main2, sub3])
    session.flush()
    sub1.parent_dimension_id = main1.id
    sub2.parent_dimension_id = main1.id
    sub3.parent_dimension_id = main2.id
    session.commit()
    return {'main1': main1.id, 'sub1': sub1.id, 'sub2': sub2.id,
            'main2': main2.id, 'sub3': sub3.id}


def _get_dim(session, dim_id):
    from evaluation_service.infrastructure.persistence.orm_models import Dimension
    return session.get(Dimension, dim_id)


# ==================== 缺陷3：批量删除/启停级联 ====================

class TestBatchDeleteCascade:
    def test_delete_main_cascades_to_subs(self, db, svc):
        """删主维度：子维度一并软删（修复后遗留孤儿子维度）。"""
        session = db.get_db_session()
        ids = _seed_tree(session)
        db.remove_db_session()

        result = svc.batch_action({'ids': [ids['main1']], 'action': 'delete'})

        assert result['success'] is True
        session = db.get_db_session()
        try:
            assert _get_dim(session, ids['main1']).deleted is True
            assert _get_dim(session, ids['sub1']).deleted is True
            assert _get_dim(session, ids['sub2']).deleted is True
            # 其他子树不受影响
            assert _get_dim(session, ids['main2']).deleted is False
            assert _get_dim(session, ids['sub3']).deleted is False
        finally:
            db.remove_db_session()

    def test_delete_sub_only(self, db, svc):
        """删子维度：仅自身（无后代）。"""
        session = db.get_db_session()
        ids = _seed_tree(session)
        db.remove_db_session()

        result = svc.batch_action({'ids': [ids['sub1']], 'action': 'delete'})

        assert result['success'] is True
        session = db.get_db_session()
        try:
            assert _get_dim(session, ids['sub1']).deleted is True
            assert _get_dim(session, ids['main1']).deleted is False
            assert _get_dim(session, ids['sub2']).deleted is False
        finally:
            db.remove_db_session()

    def test_disable_extends_to_descendants(self, db, svc):
        """禁用主维度：其全部子维度一并禁用（主/子联动）。"""
        session = db.get_db_session()
        ids = _seed_tree(session)
        db.remove_db_session()

        result = svc.batch_action({'ids': [ids['main1']], 'action': 'disable'})

        assert result['success'] is True
        session = db.get_db_session()
        try:
            assert _get_dim(session, ids['main1']).status is False
            assert _get_dim(session, ids['sub1']).status is False
            assert _get_dim(session, ids['sub2']).status is False
            assert _get_dim(session, ids['main2']).status is True
            assert _get_dim(session, ids['sub3']).status is True
        finally:
            db.remove_db_session()

    def test_enable_extends_to_descendants(self, db, svc):
        """启用子维度：选中集合与其后代启用，父维度不受影响。"""
        session = db.get_db_session()
        ids = _seed_tree(session)
        db.remove_db_session()
        svc.batch_action({'ids': [ids['main1']], 'action': 'disable'})

        result = svc.batch_action({'ids': [ids['sub1']], 'action': 'enable'})

        assert result['success'] is True
        session = db.get_db_session()
        try:
            assert _get_dim(session, ids['sub1']).status is True
            assert _get_dim(session, ids['main1']).status is False
            assert _get_dim(session, ids['sub2']).status is False
        finally:
            db.remove_db_session()


# ==================== 缺陷4：分段排序编码 ====================

class TestReorderSegmentedEncoding:
    def test_reorder_encodes_main_segments_and_sub_offsets(self, db, svc):
        """重排编码：主维度占独立段，子维度挂父段内（父段值+组内序号，1 起）。"""
        session = db.get_db_session()
        ids = _seed_tree(session)
        db.remove_db_session()

        # 前端按层级重组后的全量顺序：main1, sub1, sub2, main2, sub3
        result = svc.batch_action({
            'ids': [ids['main1'], ids['sub1'], ids['sub2'],
                    ids['main2'], ids['sub3']],
            'action': 'reorder',
        })

        assert result['success'] is True
        session = db.get_db_session()
        try:
            assert _get_dim(session, ids['main1']).sort_order == 0
            assert _get_dim(session, ids['sub1']).sort_order == 1
            assert _get_dim(session, ids['sub2']).sort_order == 2
            assert _get_dim(session, ids['main2']).sort_order == DIMENSION_SORT_STEP
            assert _get_dim(session, ids['sub3']).sort_order == DIMENSION_SORT_STEP + 1
        finally:
            db.remove_db_session()

    def test_reorder_parent_not_in_list_falls_back_to_db_segment(self, db, svc):
        """父维度不在列表（筛选态）：取库中当前段值作为子维度基值。"""
        session = db.get_db_session()
        ids = _seed_tree(session)
        db.remove_db_session()

        result = svc.batch_action({'ids': [ids['sub3']], 'action': 'reorder'})

        assert result['success'] is True
        session = db.get_db_session()
        try:
            # main2 库中段值 DIMENSION_SORT_STEP，sub3 挂其段内 1 号
            assert _get_dim(session, ids['sub3']).sort_order == DIMENSION_SORT_STEP + 1
        finally:
            db.remove_db_session()

    def test_reorder_missing_id_rejected(self, db, svc):
        session = db.get_db_session()
        ids = _seed_tree(session)
        db.remove_db_session()

        result = svc.batch_action({'ids': [ids['main1'], 987654], 'action': 'reorder'})

        assert result['success'] is False
        assert '987654' in result['message']

    def test_create_main_appends_new_segment(self, db, svc):
        """创建主维度未指定排序：追加到主维度段末尾（段末 + SORT_STEP）。"""
        result = svc.create_dimension(
            {'name': '新主维度', 'type': 'auto', 'result_type': 1, 'category_id': 1})

        assert result['success'] is True
        session = db.get_db_session()
        try:
            from evaluation_service.infrastructure.persistence.orm_models import Dimension
            po = session.get(Dimension, result['data']['id'])
            assert po.sort_order == DIMENSION_SORT_STEP
        finally:
            db.remove_db_session()

    def test_create_sub_appends_in_parent_segment(self, db, svc):
        """创建子维度未指定排序：挂到父维度段内末尾并继承任务关键字。"""
        session = db.get_db_session()
        ids = _seed_tree(session)
        db.remove_db_session()

        result = svc.create_dimension({
            'name': '新子维度', 'parent_dimension_id': ids['main1'],
            'dimension_type': 'sub', 'type': 'auto', 'result_type': 1,
            'category_id': 1,
        })

        assert result['success'] is True
        session = db.get_db_session()
        try:
            po = _get_dim(session, result['data']['id'])
            assert po.sort_order == 3  # main1 段内现有 2 个子维度（1/2 号）之后
            assert po.parent_dimension_id == ids['main1']
        finally:
            db.remove_db_session()


# ==================== list_descendant_ids 主/子联动 ====================

class TestListDescendantIds:
    def test_collects_transitive_descendants(self, db):
        """BFS 收集全部后代（含孙代）。"""
        session = db.get_db_session()
        ids = _seed_tree(session)
        db.remove_db_session()

        result = evaluation_repository.list_descendant_ids([ids['main1']])

        assert set(result) == {ids['main1'], ids['sub1'], ids['sub2']}

    def test_empty_ids(self, db):
        assert evaluation_repository.list_descendant_ids([]) == []
