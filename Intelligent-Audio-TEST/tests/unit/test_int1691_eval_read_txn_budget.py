# -*- coding: utf-8 -*-
"""INT-1691：evaluation_service 读事务收口守卫。

事故形态（2026-10-24 采样，docker 真实库栈主库）：evaluation_service 的连接
`idle in transaction` 962s、持 `dimensions` ACCESS SHARE，同一事务里反复 SELECT
却从不 commit / rollback。ACCESS SHARE 长挂会挡 `ALTER TABLE`（需 ACCESS
EXCLUSIVE），DDL 排队后所有读写该表的会话排在它后面 → 网关 60s
DEADLINE_EXCEEDED（INT-1651 / INT-1664 同型事故）。

INT-1652 只给 algorithm_service 的读路径接了
`shared/models/database.py::end_read_transaction()`；本卡把它补到
evaluation_service：查询服务、维度仓储读方法、端点配置预加载（后台订阅线程）、
评估链路里的音频路径补全（EndpointWorker 长驻线程），并在 HTTP 边界挂
DbSessionScopeMiddleware。

本文件守这些不变量：
1. 读路径返回前事务已结束（in_transaction() 为 False）；
2. 读路径不吞掉调用链上的 pending 写（end_read_transaction 返回 False）；
3. 404/403 等提前返回路径同样收口；
4. 写路径仍落库（不回归）。
"""
import os
import tempfile

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int1691_') + '/guard.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.models.database import (
    Base,
    get_db_session,
    get_engine,
    init_db,
    remove_db_session,
)


def _current_session():
    """当前 scope 的真实 Session（不存在则新建）。"""
    return get_db_session()()


@pytest.fixture(scope='module', autouse=True)
def _schema():
    """建本服务自有 PO 的三张表（categories / dimensions / test_result_dimensions）。"""
    init_db()
    from evaluation_service.infrastructure.persistence.orm_models import (
        Category, Dimension, TestResultDimension,
    )
    Base.metadata.create_all(get_engine(), tables=[
        Category.__table__, Dimension.__table__, TestResultDimension.__table__,
    ])
    yield


@pytest.fixture(autouse=True)
def _clean_session():
    """每个用例从干净的线程级 session 起步，结束清理（连接不跨用例存活）。"""
    remove_db_session()
    yield
    sess = _current_session()
    try:
        sess.rollback()
    finally:
        remove_db_session()


def _make_dimension(name='接线测试_读事务守卫', **overrides):
    """插入一条可见（shared/未删除/已启用）维度，返回主键。"""
    from evaluation_service.infrastructure.persistence.orm_models import Dimension
    fields = dict(
        name=name,
        type='auto',
        result_type=1,
        deleted=False,
        visibility='shared',
        status=True,
        dimension_type='main',
    )
    fields.update(overrides)
    session = _current_session()
    dim = Dimension(**fields)
    session.add(dim)
    session.commit()
    return dim.id


# ==================== 读路径：事务必须结束 ====================

def test_query_service_list_dimensions_ends_read_transaction():
    """ListDimensions 读 RPC：返回后不得留 idle in transaction。"""
    dim_id = _make_dimension()
    from evaluation_service.application.queries.evaluation_query_service import (
        evaluation_query_service,
    )

    result = evaluation_query_service.list_dimensions(page=1, per_page=10)

    assert result['success'] is True
    assert any(item['id'] == dim_id for item in result['data']['items'])
    assert _current_session().in_transaction() is False, \
        'ListDimensions 返回后仍持有事务（dimensions ACCESS SHARE 会挡 DDL）'


def test_query_service_get_dimension_ends_read_transaction():
    """维度详情（含参数 / 关联）：业务码无关，读后事务必须结束。"""
    dim_id = _make_dimension(name='接线测试_详情读事务')
    from evaluation_service.application.queries.evaluation_query_service import (
        evaluation_query_service,
    )

    result = evaluation_query_service.get_dimension(dim_id)

    assert result['success'] is True
    assert result['data']['id'] == dim_id
    assert _current_session().in_transaction() is False


def test_query_service_list_categories_ends_read_transaction():
    from evaluation_service.application.queries.evaluation_query_service import (
        evaluation_query_service,
    )

    result = evaluation_query_service.list_categories()

    assert result['success'] is True
    assert _current_session().in_transaction() is False


def test_query_service_keeps_pending_write():
    """有 pending 写时不回滚：只读收口绝不能吞掉调用链上的写。"""
    from evaluation_service.application.queries.evaluation_query_service import (
        evaluation_query_service,
    )
    from evaluation_service.infrastructure.persistence.orm_models import Dimension

    session = _current_session()
    session.add(Dimension(
        name='接线测试_pending写', type='auto', result_type=1,
        deleted=False, visibility='shared', status=True, dimension_type='main',
    ))
    assert session.new, '前置：session 里应有 pending 写'

    result = evaluation_query_service.list_categories()

    assert result['success'] is True
    assert session.in_transaction() is True, '有待提交写时不得回滚'
    # autoflush 已把 pending 写发给数据库（new 集合随之清空），回滚会把这条写
    # 静默丢掉——同一事务内必须仍能查到它。
    assert session.query(Dimension).filter(
        Dimension.name == '接线测试_pending写').count() == 1, 'pending 写必须原样保留'
    session.rollback()


def test_uncommitted_write_flag_cleared_after_close():
    """flush 后 close 也必须清「未提交写」标记（close 不发 after_rollback）。

    漏清会让复用线程的 session 永久表现为「有未提交写」，只读收口从此失效——
    比原先的空事务泄漏更隐蔽。
    """
    from evaluation_service.application.queries.evaluation_query_service import (
        evaluation_query_service,
    )
    from evaluation_service.infrastructure.persistence.orm_models import Dimension

    session = _current_session()
    session.add(Dimension(
        name='接线测试_close清标', type='auto', result_type=1,
        deleted=False, visibility='shared', status=True, dimension_type='main',
    ))
    session.flush()
    assert session.info.get('_int1691_uncommitted_write') is True
    session.close()
    assert session.info.get('_int1691_uncommitted_write') is None,         'close 之后未提交写标记必须清掉'

    evaluation_query_service.list_categories()
    assert _current_session().in_transaction() is False


# ==================== 仓储读：长驻线程（EndpointWorker / 订阅线程）幂等收口 ====================

def test_dimension_repository_reads_end_transaction():
    """维度聚合根 / 基础信息 / 维度评分三类读方法返回后事务都已结束。"""
    from evaluation_service.infrastructure.persistence.evaluation_dimension_repository import (
        evaluation_dimension_repository as repo,
    )

    dim_id = _make_dimension(name='接线测试_仓储读事务')

    aggs = repo.list_active_dimensions_by_ids([dim_id])
    assert [a.id for a in aggs] == [dim_id]
    assert _current_session().in_transaction() is False

    basics = repo.get_dimension_basics_by_ids([dim_id])
    assert basics and basics[0]['id'] == dim_id
    assert _current_session().in_transaction() is False

    all_dims = repo.list_all_endpoint_dimensions()
    assert any(d.id == dim_id for d in all_dims)
    assert _current_session().in_transaction() is False

    assert repo.find_score(1, dim_id, None) is None
    assert _current_session().in_transaction() is False


def test_endpoint_config_preload_ends_transaction():
    """端点配置预加载（lifespan + DimensionConfigSub 订阅线程）读后收口。"""
    from evaluation_service.infrastructure.evaluation_api.worker_management import (
        WorkerManagementMixin,
    )

    class _StubApiClient:
        default_max_concurrent = 1

        def __init__(self):
            self.loaded = None

        def load_endpoint_configs(self, aggregates):
            self.loaded = aggregates

    class _StubHost(WorkerManagementMixin):
        def __init__(self):
            self.endpoint_workers = {}
            self.api_client = _StubApiClient()
            self.logs = []

        def _log(self, **kwargs):
            self.logs.append(kwargs)

    _make_dimension(name='接线测试_端点预加载')
    host = _StubHost()

    host._load_all_endpoint_configs()

    assert host.api_client.loaded is not None, '前置：预加载应读完维度'
    assert _current_session().in_transaction() is False, \
        '订阅线程反复读 dimensions 不得把空事务带下去'


# ==================== 写路径：提前返回收口 + 不回归 ====================

def test_update_dimension_not_found_ends_transaction():
    """404 提前返回路径：读出来的事务必须收口（原先直接 return 留下空事务）。"""
    from evaluation_service.application.handlers.evaluation_config_handler import (
        evaluation_config_handler,
    )

    result = evaluation_config_handler.update_dimension(2_000_000_000, {'name': 'x'})

    assert result['success'] is False and result.get('code') == 404
    assert _current_session().in_transaction() is False


def test_calculate_score_not_found_ends_transaction():
    """纯读 RPC（计算分值）404 路径同样收口。"""
    from evaluation_service.application.handlers.evaluation_config_handler import (
        evaluation_config_handler,
    )

    result = evaluation_config_handler.calculate_score(2_000_000_000, {'value': 1})

    assert result['success'] is False
    assert _current_session().in_transaction() is False


def test_category_write_path_still_commits():
    """写路径不回归：分类创建 2xx 且落库，返回后无残留事务；随后软删清理。"""
    from evaluation_service.application.handlers.evaluation_config_handler import (
        evaluation_config_handler,
    )

    created = evaluation_config_handler.create_category({
        'name': '接线测试_读事务守卫分类',
        'description': '',
        'icon': 'icon-read-txn',
        'visibility': 'shared',
    })
    assert created['success'] is True and created.get('code') == 201
    cat_id = created['data']['id']
    assert _current_session().in_transaction() is False

    remove_db_session()
    from evaluation_service.infrastructure.persistence.orm_models import Category
    row = _current_session().get(Category, cat_id)
    assert row is not None and row.name == '接线测试_读事务守卫分类'
    _current_session().rollback()

    deleted = evaluation_config_handler.delete_category(cat_id)
    assert deleted['success'] is True
    assert _current_session().in_transaction() is False


# ==================== HTTP 边界 ====================

def test_evaluation_service_registers_request_scope_middleware():
    """HTTP 边界必须挂请求级 session scope（与 algorithm_service INT-1652 同型）。"""
    from shared.infrastructure.db_session_middleware import DbSessionScopeMiddleware
    from evaluation_service.app import create_app

    app = create_app()
    assert any(m.cls is DbSessionScopeMiddleware for m in app.user_middleware), \
        'evaluation_service 未注册 DbSessionScopeMiddleware：只读路由会遗留 idle in transaction'
