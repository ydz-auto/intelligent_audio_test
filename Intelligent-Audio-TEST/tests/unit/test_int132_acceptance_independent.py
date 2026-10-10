# -*- coding: utf-8 -*-
"""INT-132 测试工程师独立验收（集成级：真实 proto 契约 + 真实 servicer + 真实仓储）。

与开发自测 test_int132_module_all_semantics.py（FakeProxy 层断言）互补：

- 验收1：显式 module=all 经真实 _TaskDataProxy 构造 proto 请求 → in-process
  stub → 真实 servicer → 真实仓储全链路，list（文件+DB 合并）与 stats
  （DB 统计 + 文件行叠加）两侧语义一致且等于不传 module；真实模块名过滤
  行为不变；空 module 归一等价。
- 验收2：真实 list + stats 调用链同参（module='all'）TTL 窗口内共享一次
  文件扫描（解析计数断言）；两调用点捕获的真实 read_entries 参数缓存键
  相等；应用层归一经 proto 契约下发为空串（非字面 'all'）。
"""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + os.path.join(os.environ.get('TEMP', '/tmp'),
                                                  'int132_accept_unused.db'))
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest  # noqa: E402

import shared.logging  # noqa: E402  定位仓库根
from shared.logging import BusinessLogReader, LogEnvironment, reset_log_settings  # noqa: E402

_REPO_ROOT = str(Path(shared.logging.__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_TASK_ID = 9100232  # 独立 task_id，与开发自测用例及共享 sqlite 中其他用例隔离


def _make_settings(root, *, scan_ttl_seconds=3):
    from shared.logging.config import LogSettings
    return LogSettings(
        root_dir=root,
        environment=LogEnvironment.DEV,
        service_max_bytes=50 * 1024 * 1024,
        service_retention_days=30,
        business_enabled=True,
        business_db_enabled=False,
        business_max_bytes=50 * 1024 * 1024,
        business_retention_days=30,
        business_max_scan_entries=100_000,
        business_scan_cache_ttl_seconds=scan_ttl_seconds,
    )


@pytest.fixture(scope='module', autouse=True)
def _db():
    from shared.models.database import Base, get_engine, init_db
    init_db()
    from task_service.infrastructure.persistence.models.system_models import Log
    Base.metadata.create_all(get_engine(), tables=[Log.__table__])
    yield


@pytest.fixture(autouse=True)
def _clean_logs():
    yield
    from shared.models.database import get_db_session
    from task_service.infrastructure.persistence.models.system_models import Log
    session = get_db_session()
    try:
        session.query(Log).filter(Log.task_id == _TASK_ID).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()


@pytest.fixture()
def log_root(tmp_path, monkeypatch):
    root = str(tmp_path / 'logs')
    monkeypatch.setattr('shared.logging.config._SETTINGS', _make_settings(root))
    yield root
    reset_log_settings()
    import shared.logging.business_reader as br
    br._SCAN_CACHE.clear()


FILE_ROWS = [
    {'time': '2026-10-10T12:10:00', 'level': 'ERROR', 'module': 'exec',
     'content': 'file exec error'},
    {'time': '2026-10-10T12:10:01', 'level': 'INFO', 'module': 'exec',
     'content': 'file exec info'},
]
DB_ROWS = [
    {'level': 'ERROR', 'module': 'gateway', 'content': 'db gateway error',
     'time': datetime(2026, 10, 10, 12, 0, 0)},
    {'level': 'INFO', 'module': 'gateway', 'content': 'db gateway info',
     'time': datetime(2026, 10, 10, 12, 0, 1)},
]


def _write_business_file(root):
    path = Path(root) / 'business' / str(_TASK_ID) / 'dev-1' / 'act.log'
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        for row in FILE_ROWS:
            fh.write('{"time": "%s", "level": "%s", "module": "%s", '
                     '"content": "%s", "task_id": %d}\n'
                     % (row['time'], row['level'], row['module'],
                        row['content'], _TASK_ID))
    return str(path)


@pytest.fixture()
def mixed_task(log_root):
    """文件侧（module=exec）+ DB 侧（module=gateway）混合任务。"""
    from task_service.infrastructure.persistence.log_repository import LogRepository
    _write_business_file(log_root)
    payload = []
    for i, row in enumerate(DB_ROWS):
        item = dict(row)
        item.setdefault('category', 'Task')
        item.setdefault('source', 'int132-accept')
        item['task_id'] = _TASK_ID
        payload.append(item)
    LogRepository().batch_create(payload)
    return log_root


class _InProcessTaskDataStub:
    """in-process gRPC 替身：请求对象原样递给真实 servicer，返回真实 pb 响应，
    并记录收到的 proto 请求（归一后下发值经真实契约断言）。"""

    def __init__(self):
        from task_service.interfaces.grpc.task_data_service import TaskDataServiceServicer
        self.servicer = TaskDataServiceServicer()
        self.list_requests = []
        self.stats_requests = []

    def ListLogs(self, request, context=None):
        self.list_requests.append(request)
        return self.servicer.ListLogs(request, context)

    def GetLogStats(self, request, context=None):
        self.stats_requests.append(request)
        return self.servicer.GetLogStats(request, context)


@pytest.fixture()
def inproc_stub(monkeypatch):
    stub = _InProcessTaskDataStub()
    import api_gateway.infrastructure.grpc_proxies.task_data_proxies as proxies
    monkeypatch.setattr(proxies, 'get_task_data_service_stub', lambda: stub)
    return stub


def _merged_query(**overrides):
    from api_gateway.schemas.log import LogListQuery
    defaults = dict(task_id=_TASK_ID, page=1, per_page=50)
    defaults.update(overrides)
    return LogListQuery(**defaults)


# ========== 验收 1：module=all 两侧语义一致（真实契约全链路） ==========

class TestModuleAllSemanticsRealChain:
    def test_list_module_all_equals_no_filter(self, mixed_task, inproc_stub,
                                              monkeypatch):
        """显式 module=all 合并 list：文件行不再按字面清零，条目集合与不传
        module 完全一致；proto 请求收到归一后的空串（非字面 'all'）。"""
        from api_gateway.application.services.log.log_query_service import LogQueryService

        captured = {}

        original = BusinessLogReader.read_entries

        def spy(inner_self, **kwargs):
            captured['file_kwargs'] = kwargs
            return original(inner_self, **kwargs)

        monkeypatch.setattr(BusinessLogReader, 'read_entries', spy)

        resp_all, _ = LogQueryService._get_task_logs_merged(
            _merged_query(module='all'))
        resp_none, _ = LogQueryService._get_task_logs_merged(_merged_query())
        items_all = resp_all['data']['items']
        items_none = resp_none['data']['items']

        assert len(items_all) == 4
        assert {(i['level'], i['module'], i['content']) for i in items_all} == \
            {(i['level'], i['module'], i['content']) for i in items_none}
        # 应用层归一：文件侧收到 None、DB 侧 proto 契约收到空串
        assert captured['file_kwargs']['module'] is None
        assert len(inproc_stub.list_requests) == 2
        assert inproc_stub.list_requests[-1].module == ''
        # DB 行确实下发了（DB 侧参与合并且不过滤）
        assert {i['module'] for i in items_all} == {'exec', 'gateway'}

    def test_stats_module_all_equals_no_filter_and_list(self, mixed_task,
                                                        inproc_stub):
        """显式 module=all stats：DB 统计（真实 servicer）不过滤，叠加文件行
        后与不传 module 一致，且与合并 list total 一致。"""
        from api_gateway.application.services.log.log_query_service import LogQueryService
        from api_gateway.infrastructure.grpc_proxies import task_data_service
        from api_gateway.schemas.log import LogStatsQuery

        db_stats_all = task_data_service.get_log_stats(
            task_id=_TASK_ID, module='all')
        db_stats_none = task_data_service.get_log_stats(task_id=_TASK_ID)
        assert db_stats_all == db_stats_none
        assert db_stats_all['total'] == 2  # DB 侧 'all' 不过滤（2 行 DB 历史行）
        assert inproc_stub.stats_requests[-1].module == ''

        merged_all = LogQueryService._merge_file_stats(
            LogStatsQuery(task_id=_TASK_ID, module='all'), db_stats_all)
        merged_none = LogQueryService._merge_file_stats(
            LogStatsQuery(task_id=_TASK_ID), db_stats_none)
        assert merged_all['total'] == 4
        assert merged_all['total'] == merged_none['total']
        assert merged_all['error'] == 2 and merged_all['info'] == 2

        resp_list, _ = LogQueryService._get_task_logs_merged(
            _merged_query(module='all'))
        assert resp_list['data']['total'] == merged_all['total']

    def test_real_module_filter_unchanged(self, mixed_task, inproc_stub):
        """真实模块名过滤行为不变：exec 命中文件行、gateway 命中 DB 行、
        未匹配模块两侧均为空。"""
        from api_gateway.application.services.log.log_query_service import LogQueryService

        resp_exec, _ = LogQueryService._get_task_logs_merged(
            _merged_query(module='exec'))
        modules_exec = {i['module'] for i in resp_exec['data']['items']}
        assert modules_exec == {'exec'}
        assert resp_exec['data']['total'] == 2

        resp_gateway, _ = LogQueryService._get_task_logs_merged(
            _merged_query(module='gateway'))
        modules_gw = {i['module'] for i in resp_gateway['data']['items']}
        assert modules_gw == {'gateway'}
        assert resp_gateway['data']['total'] == 2

        resp_none, _ = LogQueryService._get_task_logs_merged(
            _merged_query(module='nomatch'))
        assert resp_none['data']['total'] == 0

    def test_empty_module_normalizes_like_all(self, mixed_task, inproc_stub,
                                              monkeypatch):
        """空 module 与 'all'/不传同语义（归一 '' → None）。"""
        from api_gateway.application.services.log.log_query_service import LogQueryService

        captured = {}

        original = BusinessLogReader.read_entries

        def spy(inner_self, **kwargs):
            captured['file_kwargs'] = kwargs
            return original(inner_self, **kwargs)

        monkeypatch.setattr(BusinessLogReader, 'read_entries', spy)

        resp_empty, _ = LogQueryService._get_task_logs_merged(
            _merged_query(module=''))
        assert resp_empty['data']['total'] == 4
        assert captured['file_kwargs']['module'] is None
        assert inproc_stub.list_requests[-1].module == ''


# ========== 验收 2：两调用点缓存键统一（真实链路计数断言） ==========

class TestCacheKeyUnificationRealChain:
    def test_list_then_stats_single_scan_module_all(self, mixed_task, inproc_stub,
                                                    monkeypatch):
        """显式 module=all 同参 list + stats：TTL 窗口内只扫一次文件；两调用
        点捕获的真实 read_entries 参数缓存键相等（归一前 'all' vs None 分裂）。"""
        import shared.logging.business_reader as br
        from api_gateway.application.services.log.log_query_service import LogQueryService
        from api_gateway.schemas.log import LogStatsQuery

        parse_calls = {'n': 0}
        captured = {'list': None, 'stats': None}
        original_parse = br.BusinessLogReader._parse_file
        original_read = BusinessLogReader.read_entries

        def counting_parse(inner_self, file_path):
            parse_calls['n'] += 1
            return original_parse(inner_self, file_path)

        def spy(which):
            def _spy(inner_self, **kwargs):
                captured[which] = kwargs
                return original_read(inner_self, **kwargs)
            return _spy

        monkeypatch.setattr(br.BusinessLogReader, '_parse_file', counting_parse)
        monkeypatch.setattr(BusinessLogReader, 'read_entries', spy('list'))

        resp, _ = LogQueryService._get_task_logs_merged(
            _merged_query(module='all'))
        assert resp['data']['total'] == 4
        assert parse_calls['n'] == 1

        monkeypatch.setattr(BusinessLogReader, 'read_entries', spy('stats'))
        from api_gateway.infrastructure.grpc_proxies import task_data_service
        db_stats = task_data_service.get_log_stats(task_id=_TASK_ID)
        merged = LogQueryService._merge_file_stats(
            LogStatsQuery(task_id=_TASK_ID, module='all'), db_stats)
        assert merged['total'] == 4
        assert parse_calls['n'] == 1  # stats 命中 list 的扫描缓存，零复扫

        # 两调用点缓存键相等（真实查询对象捕获的完整参数）
        root = str(Path(mixed_task))
        assert BusinessLogReader._scan_cache_key(root, captured['list']) == \
            BusinessLogReader._scan_cache_key(root, captured['stats'])
        assert captured['list']['module'] is None
        assert captured['stats']['module'] is None
