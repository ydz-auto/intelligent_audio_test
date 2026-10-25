# -*- coding: utf-8 -*-
"""INT-1946 日志合并视图分页稳定性回归（每页尾部重复、页间漏行）。

背景（缺陷卡实测）：`GET /logs` 合并视图 DB 侧按 `need_rows = page * per_page`
只取前缀，前提是「DB 侧与合并侧同全序」。修复前 DB 侧是 `ORDER BY id DESC`，
合并侧是 `(time desc, id desc)`；库里存在「id 大、time 早」的行（主库实测
task_review / published_task 各一批）时，这些行每页都落在 id 取回窗口头部、
按 time 排序后又落到页尾，本该占位的行永远取不到 → 每页尾部固定同几条、
页间漏行，改 per_page 连行序和漏行批次一起变。

覆盖：
1. 仓储口径：`LogRepository.list_logs` 按 (time desc, id desc) 返回；
2. 全局合并视图：id/time 逆序夹具下连续翻页 id 互斥、并集 = total；
3. per_page 变化不改首页行序（per_page=40 前 20 == per_page=20）；
4. 任务维度合并视图（`_get_task_logs_merged`）同口径：页与页不重不漏、
   total 与同筛选行数一致。
"""
import os
import tempfile
from datetime import datetime, timedelta
from types import SimpleNamespace

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int1946_paging_') + '/paging.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest  # noqa: E402

import shared.logging.audit_reader as audit_reader_module  # noqa: E402
from shared.logging.config import LogSettings, reset_log_settings  # noqa: E402
from shared.logging.enums import LogEnvironment  # noqa: E402
from task_service.infrastructure.persistence.log_repository import LogRepository  # noqa: E402

_TASK_ID = 9101946
_MODULE = 'int1946'          # 全局视图用例的隔离筛选（同进程其它测试模块的行不串扰）
_BASE = datetime(2026, 10, 25, 20, 0, 0)


def _make_settings(root, **overrides):
    values = dict(
        root_dir=str(root),
        environment=LogEnvironment.DEV,
        service_max_bytes=50 * 1024 * 1024,
        service_retention_days=30,
        business_enabled=True,
        business_db_enabled=False,
        business_max_bytes=50 * 1024 * 1024,
        business_retention_days=30,
        business_max_scan_entries=100_000,
        audit_enabled=True,
        audit_db_enabled=False,
        audit_max_bytes=50 * 1024 * 1024,
        audit_retention_days=30,
        audit_archive_enabled=True,
        audit_max_scan_entries=100_000,
        audit_query_default_days=30,
        audit_scan_cache_ttl_seconds=3,
        sweep_service='api_gateway',
        file_retention_days=30,
    )
    values.update(overrides)
    return LogSettings(**values)


@pytest.fixture(scope='module', autouse=True)
def _db():
    from shared.models.database import Base, get_engine, init_db
    init_db()
    from task_service.infrastructure.persistence.models.system_models import Log
    Base.metadata.create_all(get_engine(), tables=[Log.__table__])
    yield


@pytest.fixture(autouse=True)
def _clean():
    """每个用例前后清掉本卡的 DB 行与聚合缓存（count 有 TTL 缓存）。"""
    from shared.models.database import get_db_session
    from task_service.infrastructure.persistence.models.system_models import Log
    from task_service.infrastructure.persistence import log_repository as repo_module

    def _purge():
        session = get_db_session()
        try:
            session.query(Log).filter(Log.task_id == _TASK_ID).delete(
                synchronize_session=False)
            session.commit()
        finally:
            session.close()
        repo_module._agg_cache_clear()

    _purge()
    yield
    _purge()


@pytest.fixture(autouse=True)
def _no_agg_cache(monkeypatch):
    """关掉列表 total 的 TTL 聚合缓存，避免上一个用例的计数串到本用例。"""
    from shared.infrastructure.config import BaseConfig
    monkeypatch.setattr(BaseConfig, 'LOG_DB_AGGREGATE_CACHE_TTL_SECONDS', 0,
                        raising=False)


@pytest.fixture()
def log_root(tmp_path, monkeypatch):
    """临时日志根：审计/业务文件侧为空，合并视图只剩 DB 侧行。"""
    root = str(tmp_path / 'logs')
    monkeypatch.setattr('shared.logging.config._SETTINGS', _make_settings(root))
    audit_reader_module._SCAN_CACHE.clear()
    yield root
    audit_reader_module._SCAN_CACHE.clear()
    reset_log_settings()
    import shared.logging.business_reader as business_reader
    business_reader._SCAN_CACHE.clear()


@pytest.fixture(autouse=True)
def _reset_request():
    yield
    from api_gateway.infrastructure.request_adapter import set_current_request
    set_current_request(None)


def _set_request(body=None, query=None, user_id=0):
    from api_gateway.infrastructure.request_adapter import set_current_request
    set_current_request(SimpleNamespace(
        state=SimpleNamespace(_json_body=body, user_id=user_id),
        query_params=query or {},
        method='GET',
    ))


def _seed():
    """按插入顺序写行：id 递增，time 递减——「后写的是更早的日志」。

    模仿主库 task_review/published_task 实测形态：高 id 的行 time 反而更早。
    分三组（内容前缀即组名），共 24 行：
    - n0..n9：最新（_BASE-0s 起，每行早 10s）
    - m0..m7：中段（_BASE-30min 起）
    - o0..o5：最旧（_BASE-6h 起），id 最大
    """
    from shared.models.database import get_db_session
    from task_service.infrastructure.persistence.models.system_models import Log

    groups = [('n', 10, 0), ('m', 8, 30 * 60), ('o', 6, 6 * 3600)]
    session = get_db_session()
    try:
        for prefix, count, offset in groups:
            for i in range(count):
                session.add(Log(
                    time=_BASE - timedelta(seconds=offset + i * 10),
                    level='INFO', category='Task', module=_MODULE,
                    source='int1946', content=f'{prefix}{i}', task_id=_TASK_ID))
                session.flush()          # 保证 id 递增顺序 = 插入顺序
        session.commit()
    finally:
        session.close()


def _expected_contents():
    """(time desc, id desc) 下的期望内容序。"""
    return ([f'n{i}' for i in range(10)]
            + [f'm{i}' for i in range(8)]
            + [f'o{i}' for i in range(6)])


def _call_logs(query=None, user_id=0):
    from api_gateway.application.services.log.log_query_service import LogQueryService

    _set_request({}, query or {}, user_id=user_id)
    body, code = LogQueryService.get_logs()
    assert code == 200, body
    return body['data']


def _all_pages(**filters):
    """按返回的 pages 翻完全部页，返回 (行列表, 首响应)。"""
    first = _call_logs(dict(filters, page='1'))
    rows = list(first['items'])
    for page in range(2, first['pages'] + 1):
        rows.extend(_call_logs(dict(filters, page=str(page)))['items'])
    return rows, first


# =====================================================================
# 1. 仓储口径：DB 侧也必须按 (time desc, id desc)
# =====================================================================

class TestRepositoryOrdering:
    def test_list_logs_orders_by_time_desc_then_id_desc(self):
        _seed()
        result = LogRepository().list_logs(task_id=_TASK_ID, per_page=100)

        assert result['total'] == 24
        assert [row['content'] for row in result['items']] == _expected_contents()

    def test_pages_are_disjoint_with_inverted_ids(self):
        _seed()
        rows = []
        for page in (1, 2, 3):
            rows.extend(LogRepository().list_logs(
                task_id=_TASK_ID, page=page, per_page=8)['items'])

        assert [row['content'] for row in rows] == _expected_contents()


# =====================================================================
# 2. 全局合并视图：连续翻页 id 互斥、并集 = total、per_page 不改行序
# =====================================================================

class TestGlobalMergedPaging:
    def test_pages_are_exclusive_and_complete(self, log_root, repo_proxy):
        _seed()
        filters = {'module': _MODULE, 'per_page': '8'}

        rows, first = _all_pages(**filters)

        assert first['total'] == 24
        assert first['pages'] == 3
        ids = [row['id'] for row in rows]
        assert len(ids) == 24
        assert len(set(ids)) == 24, f'翻页出现重复 id: {ids}'
        assert [row['content'] for row in rows] == _expected_contents()

    def test_per_page_does_not_change_first_rows(self, log_root, repo_proxy):
        _seed()

        small = _call_logs({'module': _MODULE, 'page': '1', 'per_page': '8'})
        large = _call_logs({'module': _MODULE, 'page': '1', 'per_page': '16'})

        assert [row['id'] for row in large['items'][:8]] == \
               [row['id'] for row in small['items'][:8]]

    def test_each_page_is_time_desc(self, log_root, repo_proxy):
        _seed()

        rows, _first = _all_pages(module=_MODULE, per_page='8')
        times = [row['time'] for row in rows]
        assert times == sorted(times, reverse=True)


# =====================================================================
# 3. 任务维度合并视图：同口径不重不漏
# =====================================================================

class TestTaskMergedPaging:
    def test_pages_are_exclusive_and_complete(self, log_root, repo_proxy):
        _seed()

        rows, first = _all_pages(task_id=str(_TASK_ID), per_page='8')

        assert first['total'] == 24
        ids = [row['id'] for row in rows]
        assert len(ids) == 24
        assert len(set(ids)) == 24, f'翻页出现重复 id: {ids}'
        assert [row['content'] for row in rows] == _expected_contents()


class _RepoProxy:
    """task_data_service 假代理：list_logs 直连真实 LogRepository。

    这样网关合并视图吃到的就是仓储的真实排序（修复前 id 倒序、修复后
    time+id 倒序），前缀取行的缺陷会在这一层原样复现。
    """

    def __init__(self):
        self.calls = []

    def list_logs(self, **kwargs):
        kwargs.pop('reraise', None)
        self.calls.append(dict(kwargs))
        return LogRepository().list_logs(**kwargs)


@pytest.fixture()
def repo_proxy(monkeypatch):
    """把网关的 gRPC 代理换成直连真实 LogRepository 的假代理。"""
    proxy = _RepoProxy()
    monkeypatch.setattr('api_gateway.infrastructure.grpc_proxies.task_data_service',
                        proxy)
    return proxy


def test_export_and_list_share_the_same_source(log_root, repo_proxy):
    """同筛选导出条数与列表 total 同源：DB 行数一致（导出取全部命中行）。"""
    from api_gateway.application.services.log import log_query_service as lqs

    _seed()

    data = _call_logs({'module': _MODULE, 'page': '1', 'per_page': '8'})
    rows, db_total = lqs.LogQueryService._fetch_db_rows(
        module=_MODULE, need_rows=0, convert=lqs._to_export_row)

    assert db_total == data['total'] == 24
    assert len(rows) == 24
