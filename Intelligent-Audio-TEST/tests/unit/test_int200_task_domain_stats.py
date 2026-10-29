# -*- coding: utf-8 -*-
"""INT-200 任务域全量聚合统计：统计卡/图表数据源由当前页过滤改为任务域聚合。

缺陷：任务管理页统计卡与图表对当前页（每页 10 条）tasks 过滤计数，分页下
统计数字与真实总量不符。

修复契约：
1. task_service GetTaskStats 扩展 — group_by='trend' 返回完成任务按
   created_at 分桶（granularity=day/week/month/year，键格式与前端一致：周键为
   日历年-W ISO 周数不补零）；deleted=True 统计回收站软删除任务
   （任务类型 api/e2e/mixed 概念已废除，不再有 group_by='type'）。
2. servicer 透传 deleted/granularity。
3. 网关 TaskQueryService.domain_stats 聚合组合（status 求和 = 未删除总数、
   deleted_total、trend 透传；聚合失败整体 400 不以 0 兜底）。
"""
import os
import tempfile
import types
from datetime import datetime

import pytest

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int200_stats_') + '/stats.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.models.database import (
    Base, get_db_session, get_engine, init_db, remove_db_session,
)
from sqlalchemy import BigInteger
from sqlalchemy.ext.compiler import compiles


@compiles(BigInteger, 'sqlite')
def _render_bigint_as_integer_sqlite(type_, compiler, **kw):
    """SQLite 不支持 BigInteger 主键自增，建表时渲染为 INTEGER。"""
    return 'INTEGER'


def _count_map(result):
    return {item['key']: int(item['count']) for item in result.get('items', [])}


@pytest.fixture(scope='module')
def db():
    """初始化 SQLite 库并建 task/task_case 表，种子 7 条任务 + 6 条任务用例行。

    全量跑时共享引擎可能已被先前用例建表/插数（单例 engine，setdefault 的
    DATABASE_URL 不生效），各断言均以种子前基线为参照，不假设库为空。
    """
    from task_service.infrastructure.persistence.models import Task, TaskCase
    init_db(pool_size=3)
    engine = get_engine()
    assert ':memory:' not in str(engine.url), \
        f'int200 sqlite 需要文件型 sqlite，实际绑定 {engine.url}'
    remove_db_session()
    Base.metadata.create_all(bind=engine, tables=[Task.__table__, TaskCase.__table__])

    repo = _repo()
    baseline = {
        'status': _count_map(repo.get_task_stats(group_by='status')),
        'trend_day': _count_map(repo.get_task_stats(group_by='trend', granularity='day')),
        'trend_week': _count_map(repo.get_task_stats(group_by='trend', granularity='week')),
        'trend_month': _count_map(repo.get_task_stats(group_by='trend', granularity='month')),
        'trend_year': _count_map(repo.get_task_stats(group_by='trend', granularity='year')),
        'deleted_total': int(repo.get_task_stats(deleted=True).get('total', 0)),
        'deleted_completed': _count_map(repo.get_task_stats(group_by='status', deleted=True)),
    }

    session = get_db_session()
    # A=仅 physical(e2e)；B=仅 http_api(api)；C=physical+websocket_api(mixed)；
    # D=无用例行(api 口径)；E/F=已完成（趋势分桶）；G=软删除且已完成（排除出全部默认统计）
    a = Task(name='int200-a', status='completed', total_cases=1,
             created_at=datetime(2026, 3, 15, 10, 0, 0))
    b = Task(name='int200-b', status='failed', total_cases=1)
    c = Task(name='int200-c', status='running', total_cases=2)
    d = Task(name='int200-d', status='pending', total_cases=0)
    e = Task(name='int200-e', status='completed', total_cases=1,
             created_at=datetime(2026, 3, 15, 23, 30, 0))
    f = Task(name='int200-f', status='completed', total_cases=1,
             created_at=datetime(2025, 1, 1, 8, 0, 0))
    g = Task(name='int200-g', status='completed', total_cases=1,
             created_at=datetime(2024, 6, 1, 8, 0, 0), deleted=True)
    session.add_all([a, b, c, d, e, f, g])
    session.flush()
    session.add_all([
        TaskCase(task_id=a.id, test_case_id='int200-c1', device_type='physical'),
        TaskCase(task_id=b.id, test_case_id='int200-c2', device_type='http_api'),
        TaskCase(task_id=c.id, test_case_id='int200-c3', device_type='physical'),
        TaskCase(task_id=c.id, test_case_id='int200-c4', device_type='websocket_api'),
        TaskCase(task_id=e.id, test_case_id='int200-c5', device_type='http_api'),
        TaskCase(task_id=g.id, test_case_id='int200-c6', device_type='physical'),
    ])
    session.commit()
    session.close()

    yield {'baseline': baseline}
    remove_db_session()


def _repo():
    from task_service.infrastructure.persistence.task_repository import task_repository
    return task_repository


def _delta(counts, baseline, key):
    return counts.get(key, 0) - baseline.get(key, 0)


# ===== 1) 仓储层：deleted 统计范围 =====

def test_deleted_scope_counts_only_soft_deleted(db):
    """默认统计（deleted=False）不含软删除任务；deleted=True 只含软删除任务。"""
    repo = _repo()
    baseline = db['baseline']
    not_deleted = _count_map(repo.get_task_stats(group_by='status'))
    assert _delta(not_deleted, baseline['status'], 'completed') == 3  # A + E + F（G 被排除）
    deleted_only = _count_map(repo.get_task_stats(group_by='status', deleted=True))
    assert _delta(deleted_only, baseline['deleted_completed'], 'completed') == 1  # G


def test_deleted_total_scope(db):
    """无 group_by 时 deleted=True 返回回收站总数。"""
    assert int(_repo().get_task_stats(deleted=True).get('total', 0)) \
        == db['baseline']['deleted_total'] + 1


# ===== 3) 仓储层：trend 完成趋势分桶 =====

def test_trend_day_buckets(db):
    counts = _count_map(_repo().get_task_stats(group_by='trend', granularity='day'))
    baseline = db['baseline']['trend_day']
    assert _delta(counts, baseline, '2026-03-15') == 2  # A + E 同日
    assert _delta(counts, baseline, '2025-01-01') == 1  # F


def test_trend_week_month_year_keys(db):
    """周键 = 日历年-W ISO 周数（不补零）：2026-03-15→W11、2025-01-01→W1。"""
    repo = _repo()
    week = _count_map(repo.get_task_stats(group_by='trend', granularity='week'))
    assert _delta(week, db['baseline']['trend_week'], '2026-W11') == 2
    assert _delta(week, db['baseline']['trend_week'], '2025-W1') == 1
    month = _count_map(repo.get_task_stats(group_by='trend', granularity='month'))
    assert _delta(month, db['baseline']['trend_month'], '2026-03') == 2
    assert _delta(month, db['baseline']['trend_month'], '2025-01') == 1
    year = _count_map(repo.get_task_stats(group_by='trend', granularity='year'))
    assert _delta(year, db['baseline']['trend_year'], '2026') == 2
    assert _delta(year, db['baseline']['trend_year'], '2025') == 1


def test_trend_excludes_deleted_and_non_completed(db):
    """G（软删除已完成，2024）与非完成任务不计入趋势分桶。"""
    counts = _count_map(_repo().get_task_stats(group_by='trend', granularity='year'))
    assert _delta(counts, db['baseline']['trend_year'], '2024') == 0


def test_trend_unsupported_granularity(db):
    result = _repo().get_task_stats(group_by='trend', granularity='hourly')
    assert 'error' in result
    assert 'hourly' in result['error']


def test_trend_items_sorted(db):
    items = _repo().get_task_stats(group_by='trend', granularity='day').get('items', [])
    keys = [item['key'] for item in items]
    assert keys == sorted(keys)


# ===== 4) servicer 透传 =====

def test_servicer_passthrough_deleted_and_granularity(db, monkeypatch):
    from task_service.interfaces.grpc import task_data_service as servicer_mod
    from shared.utils.grpc_json import loads as _loads

    captured = {}

    def fake_get_task_stats(status='', algorithm_type='', group_by='',
                            deleted=False, granularity=''):
        captured.update(status=status, algorithm_type=algorithm_type,
                        group_by=group_by, deleted=deleted, granularity=granularity)
        return {'items': [{'key': '2026-03', 'count': 2}]}

    monkeypatch.setattr(servicer_mod.task_repository, 'get_task_stats',
                        fake_get_task_stats)
    req = types.SimpleNamespace(status='completed', algorithm_type='',
                                group_by='trend', deleted=True, granularity='month')
    resp = servicer_mod.TaskDataServiceServicer().GetTaskStats(req)
    assert resp.success is True
    assert captured == {'status': 'completed', 'algorithm_type': '',
                        'group_by': 'trend', 'deleted': True, 'granularity': 'month'}
    payload = _loads(resp.data, {})
    assert payload == {'items': [{'key': '2026-03', 'count': 2}]}


def test_servicer_repo_error_surfaces_false(db, monkeypatch):
    """仓储返回 error dict（如非法 granularity）→ servicer success=False。"""
    from task_service.interfaces.grpc import task_data_service as servicer_mod

    monkeypatch.setattr(servicer_mod.task_repository, 'get_task_stats',
                        lambda **kw: {'error': 'unsupported granularity: hourly'})
    req = types.SimpleNamespace(status='', algorithm_type='',
                                group_by='trend', deleted=False, granularity='hourly')
    resp = servicer_mod.TaskDataServiceServicer().GetTaskStats(req)
    assert resp.success is False


# ===== 5) 网关 domain_stats 组合 =====

def test_gateway_domain_stats_composition(monkeypatch):
    from api_gateway.infrastructure.grpc_proxies import task_data_service as proxy
    from api_gateway.application.services.task.task_query_service import TaskQueryService

    calls = []

    def fake_get_task_stats(status=None, algorithm_type=None, group_by=None,
                            deleted=None, granularity=None):
        calls.append({'group_by': group_by, 'deleted': deleted,
                      'granularity': granularity})
        if group_by == 'status':
            return {'items': [{'key': 'completed', 'count': 3},
                              {'key': 'running', 'count': 2}]}
        if group_by == 'trend':
            return {'items': [{'key': '2026-03-15', 'count': 2}]}
        if deleted:
            return {'total': 9}
        return {'total': 0}

    monkeypatch.setattr(proxy, 'get_task_stats', fake_get_task_stats)
    payload, http_code = TaskQueryService.domain_stats()
    assert http_code == 200
    data = payload['data']
    assert data['total'] == 5                      # status 分组求和
    assert data['deleted_total'] == 9
    assert data['status_counts'] == {'completed': 3, 'running': 2}
    assert data['trend'] == [{'key': '2026-03-15', 'count': 2}]
    assert data['granularity'] == 'day'            # 无请求上下文时缺省 day
    # 三次聚合调用齐全；granularity 仅用于 trend、deleted 仅用于回收站计数
    assert {c['group_by'] for c in calls} == {'status', 'trend', None}
    assert [c for c in calls if c['group_by'] == 'trend'][0]['granularity'] == 'day'
    assert [c for c in calls if c['group_by'] is None][0]['deleted'] is True


def test_gateway_domain_stats_granularity_param(monkeypatch):
    from api_gateway.infrastructure.grpc_proxies import task_data_service as proxy
    from api_gateway.application.services.task import task_query_service as tqs

    captured = {}

    def fake_get_task_stats(status=None, algorithm_type=None, group_by=None,
                            deleted=None, granularity=None):
        if group_by == 'trend':
            captured['granularity'] = granularity
        if group_by == 'status':
            return {'items': [{'key': 'completed', 'count': 1}]}
        if deleted:
            return {'total': 0}
        return {'total': 0}

    monkeypatch.setattr(proxy, 'get_task_stats', fake_get_task_stats)

    class _FakeRequest:
        class args:
            @staticmethod
            def to_dict():
                return {'granularity': 'week'}

    monkeypatch.setattr(tqs, 'request', _FakeRequest)
    payload, http_code = tqs.TaskQueryService.domain_stats()
    assert http_code == 200
    assert captured['granularity'] == 'week'
    assert payload['data']['granularity'] == 'week'


def test_gateway_domain_stats_failure_no_zero_fallback(monkeypatch):
    """聚合 RPC 失败 → 整体 400，不得以 0 兜底（对齐 INT-204 降级语义）。"""
    from api_gateway.infrastructure.grpc_proxies import task_data_service as proxy
    from api_gateway.application.services.task.task_query_service import TaskQueryService

    def fake_get_task_stats(**kw):
        if kw.get('group_by') == 'trend':
            raise RuntimeError('GetTaskStats gRPC 失败: task_service 不可达')
        return {'items': [{'key': 'completed', 'count': 1}]}

    monkeypatch.setattr(proxy, 'get_task_stats', fake_get_task_stats)
    payload, http_code = TaskQueryService.domain_stats()
    assert http_code == 400
    assert '任务聚合统计失败' in payload['message']
