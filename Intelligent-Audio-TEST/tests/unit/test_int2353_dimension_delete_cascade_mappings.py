# -*- coding: utf-8 -*-
"""INT-2353：删除评估维度不级联 param_mappings。

根因：``evaluation_service/application/commands/_dimension_ops_mixin.py`` 的
``_soft_delete_tree`` 只级联 params（硬删）与 algorithm_dimension_relations
（软删），没有清理 param_mappings。维度软删后，算法级（``api_id IS NULL``）、
API 实例级（``api_id`` 非空）、设备级（``device_id`` 非空）三种作用域下指向
该维度的映射仍 ``deleted=false``，算法详情的 ``mappings.evaluation`` 继续返回
「指向已删维度」的活动行。

修复：
1. algorithm_service 新增 ``DeleteParamMappingsByDimension`` RPC，按维度树
   软删全部作用域的映射；
2. evaluation_service 的 ``_soft_delete_tree`` 经 ACL 调用该 RPC。
"""
import os
import tempfile
import types

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from sqlalchemy import create_engine

import shared.models.database as database
from algorithm_service.infrastructure.persistence.models import ParamMapping


@pytest.fixture()
def db():
    """SQLite 临时文件库：engine 直装全局 scoped_session，仅建 param_mappings 表。"""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    engine = create_engine(f'sqlite:///{path}',
                           connect_args={'check_same_thread': False})
    database.remove_db_session()
    database._engine = engine
    database._SessionFactory.configure(bind=engine)
    database.Base.metadata.create_all(engine, tables=[ParamMapping.__table__])
    yield database
    database.remove_db_session()
    engine.dispose()
    try:
        os.remove(path)
    except PermissionError:
        pass


def _add(session, **kwargs):
    defaults = dict(
        algorithm_type='mat_test_int2336', api_id=None, device_id=None,
        source='evaluation', source_param='p', source_direction='output',
        target_param='p', transform_type='none', deleted=False,
    )
    defaults.update(kwargs)
    m = ParamMapping(**defaults)
    session.add(m)
    return m


# ==================== 1. 仓储：按维度树软删全部作用域 ====================

class TestDeleteByDimensionIds:
    def test_soft_deletes_all_scopes_of_tree(self, db):
        """三作用域（算法级/API 级/设备级）下的树内维度全部软删，树外不动。"""
        from algorithm_service.infrastructure.persistence.algorithm_repository import (
            param_mapping_query_repository,
        )
        session = db.get_db_session()
        tree = [10, 20]
        _add(session, source_param='algo10', dimension_id=10)
        _add(session, source_param='algo20', dimension_id=20)
        _add(session, source_param='api10', api_id=7, dimension_id=10)
        _add(session, source_param='dev20', device_id=9, dimension_id=20)
        _add(session, source_param='other30', dimension_id=30)  # 树外
        _add(session, source_param='gone10', dimension_id=10, deleted=True)  # 已删
        session.commit()

        affected = param_mapping_query_repository.delete_by_dimension_ids(tree)

        assert affected == 4
        session = db.get_db_session()
        alive_in_tree = session.query(ParamMapping).filter(
            ParamMapping.dimension_id.in_(tree),
            ParamMapping.deleted == False,  # noqa: E712
        ).all()
        assert alive_in_tree == []
        # 树外维度与已软删行不受影响
        other = session.query(ParamMapping).filter_by(source_param='other30').one()
        assert other.deleted is False
        gone = session.query(ParamMapping).filter_by(source_param='gone10').one()
        assert gone.deleted is True
        # 验收断言：树内 deleted=false 行数 0
        assert session.query(ParamMapping).filter(
            ParamMapping.dimension_id.in_(tree),
            ParamMapping.deleted.is_(False),
        ).count() == 0

    def test_empty_ids_is_noop(self, db):
        from algorithm_service.infrastructure.persistence.algorithm_repository import (
            param_mapping_query_repository,
        )
        session = db.get_db_session()
        _add(session, source_param='keep', dimension_id=10)
        session.commit()

        assert param_mapping_query_repository.delete_by_dimension_ids([]) == 0
        session = db.get_db_session()
        assert session.query(ParamMapping).filter_by(
            source_param='keep').one().deleted is False

    def test_lists_affected_algorithm_types_before_delete(self, db):
        """缓存定向失效的输入：仅活动映射的算法类型，去重排序、排除树外/已删。"""
        from algorithm_service.infrastructure.persistence.algorithm_repository import (
            param_mapping_query_repository,
        )
        session = db.get_db_session()
        tree = [10, 20]
        _add(session, source_param='a1', dimension_id=10,
             algorithm_type='algo_b')
        _add(session, source_param='a2', api_id=7, dimension_id=10,
             algorithm_type='algo_a')
        _add(session, source_param='a3', device_id=9, dimension_id=20,
             algorithm_type='algo_b')
        _add(session, source_param='other', dimension_id=30,
             algorithm_type='algo_outside')
        _add(session, source_param='gone', dimension_id=10,
             algorithm_type='algo_gone', deleted=True)
        session.commit()

        assert param_mapping_query_repository.list_algorithm_types_by_dimension_ids(
            tree) == ['algo_a', 'algo_b']
        # 列表取的是软删前的活动行；软删后不再返回
        param_mapping_query_repository.delete_by_dimension_ids(tree)
        assert param_mapping_query_repository.list_algorithm_types_by_dimension_ids(
            tree) == []
        assert param_mapping_query_repository.list_algorithm_types_by_dimension_ids(
            []) == []


# ==================== 2. RPC：JSON 维度列表解析并委托仓储 ====================

class _FakeMappingQueryRepo:
    def __init__(self, algorithm_types=None):
        self.calls = []
        self._algorithm_types = algorithm_types or []

    def list_algorithm_types_by_dimension_ids(self, dimension_ids):
        return list(self._algorithm_types)

    def delete_by_dimension_ids(self, dimension_ids):
        self.calls.append(list(dimension_ids))
        return len(dimension_ids)


class _MixinUnderTest:
    """只借用 _DimensionMixin 的 RPC 方法，缓存刷新捕获入参。"""

    def __init__(self):
        from algorithm_service.interfaces.grpc.mixins.dimension_mixin import (
            _DimensionMixin,
        )
        self.invalidate_calls = []
        self._invalidate_cache = lambda **kwargs: self.invalidate_calls.append(
            kwargs)
        self._rpc = _DimensionMixin.DeleteParamMappingsByDimension.__get__(
            self, type(self))

    def call(self, request):
        return self._rpc(request)


def test_rpc_parses_json_ids_and_delegates(db, monkeypatch):
    import algorithm_service.infrastructure.persistence.algorithm_repository as repo_mod

    fake = _FakeMappingQueryRepo(algorithm_types=['algo_b', 'algo_a'])
    monkeypatch.setattr(repo_mod, 'param_mapping_query_repository', fake)

    svc = _MixinUnderTest()
    resp = svc.call(types.SimpleNamespace(dimension_ids='[10, 20]'))

    assert resp.success is True
    assert fake.calls == [[10, 20]]
    assert '"deleted": 2' in resp.data


def test_rpc_invalidates_mappings_slice_by_affected_algorithm_types(
        db, monkeypatch):
    """打回修复：失效范围必须覆盖 mappings 桶（按受影响算法类型），
    不能只传 dimension_ids（那只重载 evaluation_dimension_params 切片）。"""
    import algorithm_service.infrastructure.persistence.algorithm_repository as repo_mod

    fake = _FakeMappingQueryRepo(algorithm_types=['voice_llm'])
    monkeypatch.setattr(repo_mod, 'param_mapping_query_repository', fake)

    svc = _MixinUnderTest()
    resp = svc.call(types.SimpleNamespace(dimension_ids='[578]'))

    assert resp.success is True
    assert svc.invalidate_calls == [{
        'algorithm_types': ['voice_llm'],
        'dimension_ids': [578],
    }]


def test_rpc_without_mappings_still_invalidates_dimension_params(
        db, monkeypatch):
    """无活动映射时仍按维度刷新（覆盖 evaluation_dimension_params 切片）。"""
    import algorithm_service.infrastructure.persistence.algorithm_repository as repo_mod

    fake = _FakeMappingQueryRepo(algorithm_types=[])
    monkeypatch.setattr(repo_mod, 'param_mapping_query_repository', fake)

    svc = _MixinUnderTest()
    resp = svc.call(types.SimpleNamespace(dimension_ids='[578]'))

    assert resp.success is True
    assert svc.invalidate_calls == [{
        'algorithm_types': [],
        'dimension_ids': [578],
    }]


def test_rpc_empty_ids_skips_repo(db, monkeypatch):
    import algorithm_service.infrastructure.persistence.algorithm_repository as repo_mod

    fake = _FakeMappingQueryRepo()
    monkeypatch.setattr(repo_mod, 'param_mapping_query_repository', fake)

    svc = _MixinUnderTest()
    resp = svc.call(types.SimpleNamespace(dimension_ids='[]'))

    assert resp.success is True
    assert fake.calls == []


# ==================== 3. 维度树删除逐维度级联映射 ====================

class _Dim:
    def __init__(self, dim_id):
        self.id = dim_id


class _FakeEvaluationRepo:
    """main(1) → sub(2) → subsub(3)，另一棵 main(4)。"""

    CHILDREN = {1: [2], 2: [3], 3: [], 4: []}
    DIMS = {i: _Dim(i) for i in (1, 2, 3, 4)}

    def __init__(self):
        self.mapping_calls = []
        self.relation_calls = []
        self.input_param_calls = []
        self.output_param_calls = []
        self.soft_deleted = []

    def list_sub_dimensions(self, parent_id):
        return [self.DIMS[i] for i in self.CHILDREN.get(parent_id, [])]

    def get_dimension(self, dim_id):
        return self.DIMS.get(dim_id)

    def soft_delete_dimension(self, dim):
        self.soft_deleted.append(dim.id)

    def delete_input_params_by_dimension(self, dim_id):
        self.input_param_calls.append(dim_id)
        return True

    def delete_output_params_by_dimension(self, dim_id):
        self.output_param_calls.append(dim_id)
        return True

    def delete_relations_by_dimension(self, dim_id):
        self.relation_calls.append(dim_id)
        return True

    def delete_param_mappings_by_dimension(self, dim_ids):
        self.mapping_calls.append(list(dim_ids))
        return True


def test_soft_delete_tree_cascades_mappings_for_every_node(db):
    from evaluation_service.application.commands.evaluation_command_service import (
        EvaluationCommandService,
    )

    repo = _FakeEvaluationRepo()
    svc = EvaluationCommandService(repo=repo)

    svc._soft_delete_tree(1)

    # 后序深搜：3 → 2 → 1，每个节点各清一次映射
    assert repo.mapping_calls == [[3], [2], [1]]
    assert repo.relation_calls == [3, 2, 1]
    assert repo.input_param_calls == [3, 2, 1]
    assert repo.soft_deleted == [3, 2, 1]
    # 另一棵树未受影响
    assert 4 not in [call[0] for call in repo.mapping_calls]
