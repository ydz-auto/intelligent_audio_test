# -*- coding: utf-8 -*-
"""INT-132 日志查询 module='all' 语义归一回归。

现状整改前（INT-81 既有形态）：文件侧 _match 不处理 module='all'、合并视图
list 侧原样透传、stats 侧 'all'→None——显式传 module=all 的 API 调用方在
文件侧按字面 'all' 过滤返回 0 行，且 list/stats 两调用点缓存键分裂。

1. 文件侧（shared）：_match 对 module='all' 不过滤，与 category/
   algorithm_type 既有 'all' 语义一致；真实模块名过滤行为不变。
2. 应用层归一（api_gateway）：_get_task_logs_merged 对 module='all' 归一为
   None 后统一下发文件侧与 DB 侧（_merge_file_stats / get_stats 的 DB 调用
   既有归一保持不变）；显式 module=all 的合并 list 不再被字面清零。
3. 两调用点缓存键一致（计数断言）：TTL 窗口内 list + stats 同参（含
   module='all'）只扫一次文件。
4. DB 侧一致性（task_service）：list_logs 与 get_stats 对 module='all' 均
   不过滤（既有形态确认）。
"""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + os.path.join(os.environ.get('TEMP', '/tmp'),
                                                  'int132_module_all_unused.db'))
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest  # noqa: E402

import shared.logging  # noqa: E402  定位仓库根
from shared.logging import BusinessLogReader, LogEnvironment, reset_log_settings  # noqa: E402

_REPO_ROOT = str(Path(shared.logging.__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_TASK_ID = 9100132  # 独立 task_id，与共享 sqlite 中其他用例隔离


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


FILE_ENTRIES = [
    {'time': '2026-10-10T12:00:00', 'level': 'ERROR', 'module': 'exec',
     'content': 'file error one'},
    {'time': '2026-10-10T12:00:01', 'level': 'INFO', 'module': 'gateway',
     'content': 'file info one'},
]


def _write_business_file(root, rel, entries):
    path = Path(root) / 'business' / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as handle:
        for entry in entries:
            handle.write(
                '{"time": "' + entry['time'] + '", "level": "' + entry['level'] +
                '", "module": "' + entry['module'] + '", "content": "' +
                entry['content'] + '", "task_id": ' + str(_TASK_ID) + '}\n'
            )
    return str(path)


# ========== 1. 文件侧：module='all' = 不过滤 ==========

class TestFileSideModuleAll:
    def test_module_all_equals_no_filter(self, log_root):
        _write_business_file(log_root, f'{_TASK_ID}/dev-1/act.log', FILE_ENTRIES)
        reader = BusinessLogReader()
        baseline = reader.read_entries(task_id=_TASK_ID)
        assert len(baseline) == 2
        # 'all' 与不传等价：不过滤（归一后与 category/algorithm_type 一致）
        assert len(reader.read_entries(task_id=_TASK_ID, module='all')) == 2
        assert len(reader.read_entries(task_id=_TASK_ID, category='all')) == 2
        assert len(reader.read_entries(task_id=_TASK_ID, algorithm_type='all')) == 2
        # 真实模块名过滤行为不变
        assert len(reader.read_entries(task_id=_TASK_ID, module='exec')) == 1
        assert len(reader.read_entries(task_id=_TASK_ID, module='gateway')) == 1
        assert len(reader.read_entries(task_id=_TASK_ID, module='nomatch')) == 0
        # 'all' 查询命中的行集合与不传完全一致
        assert {item['id'] for item in reader.read_entries(task_id=_TASK_ID, module='all')} == \
            {item['id'] for item in baseline}


# ========== 2. 应用层归一：合并视图 list 侧 ==========

class TestMergedListModuleAll:
    @pytest.fixture()
    def service(self):
        from api_gateway.application.services.log.log_query_service import LogQueryService
        return LogQueryService

    @pytest.fixture()
    def fake_proxy(self, monkeypatch):
        calls = {'kwargs': None, 'resp': {'items': [], 'total': 0}}

        class _FakeProxy:
            def list_logs(self, **kwargs):
                calls['kwargs'] = kwargs
                return calls['resp']

        monkeypatch.setattr('api_gateway.infrastructure.grpc_proxies.task_data_service',
                            _FakeProxy())
        return calls

    def test_merged_list_module_all_not_zeroed(self, service, fake_proxy, log_root):
        """显式 module=all：文件行不再按字面 'all' 清零，DB 侧收到归一后的
        None（两侧语义一致为不过滤）。"""
        _write_business_file(log_root, f'{_TASK_ID}/dev-1/act.log', FILE_ENTRIES)
        from api_gateway.schemas.log import LogListQuery
        resp, _code = service._get_task_logs_merged(
            LogListQuery(task_id=_TASK_ID, module='all', page=1, per_page=50))
        items = resp['data']['items']
        assert len(items) == 2
        assert fake_proxy['kwargs']['module'] is None

    def test_merged_list_real_module_passthrough(self, service, fake_proxy, log_root):
        """真实模块名不受归一影响：原样下发给文件侧与 DB 侧。"""
        _write_business_file(log_root, f'{_TASK_ID}/dev-1/act.log', FILE_ENTRIES)
        from api_gateway.schemas.log import LogListQuery
        resp, _code = service._get_task_logs_merged(
            LogListQuery(task_id=_TASK_ID, module='exec', page=1, per_page=50))
        assert len(resp['data']['items']) == 1
        assert fake_proxy['kwargs']['module'] == 'exec'

    def test_stats_file_side_module_all_consistent(self, service, log_root):
        """stats 文件统计侧（既有 'all'→None 归一）与 list 侧结果一致。"""
        _write_business_file(log_root, f'{_TASK_ID}/dev-1/act.log', FILE_ENTRIES)
        from api_gateway.schemas.log import LogStatsQuery
        merged_all = service._merge_file_stats(
            LogStatsQuery(task_id=_TASK_ID, module='all'), {'total': 0})
        merged_none = service._merge_file_stats(
            LogStatsQuery(task_id=_TASK_ID), {'total': 0})
        assert merged_all['total'] == 2
        assert merged_all['total'] == merged_none['total']
        assert merged_all['error'] == 1 and merged_all['info'] == 1


# ========== 3. 两调用点缓存键一致（计数断言） ==========

class TestCacheKeyUnification:
    @pytest.fixture()
    def counting_reader(self, monkeypatch):
        """类级计数 _parse_file：覆盖 list 与 stats 各自新建的 reader 实例。"""
        import shared.logging.business_reader as br
        calls = {'n': 0}
        original_parse = br.BusinessLogReader._parse_file

        def counting_parse(self, file_path):
            calls['n'] += 1
            return original_parse(self, file_path)

        monkeypatch.setattr(br.BusinessLogReader, '_parse_file', counting_parse)
        return calls

    def test_list_and_stats_module_all_single_scan(self, counting_reader, log_root,
                                                   monkeypatch):
        """验收 2：显式 module=all 同参 list + stats 在 TTL 窗口内只扫一次文件
        （两调用点缓存键统一，不再 'all' vs None 分裂）。"""
        _write_business_file(log_root, f'{_TASK_ID}/dev-1/act.log', FILE_ENTRIES)
        from api_gateway.application.services.log.log_query_service import LogQueryService
        from api_gateway.schemas.log import LogListQuery, LogStatsQuery

        calls = {'kwargs': None, 'resp': {'items': [], 'total': 0}}

        class _FakeProxy:
            def list_logs(self, **kwargs):
                calls['kwargs'] = kwargs
                return calls['resp']

        monkeypatch.setattr('api_gateway.infrastructure.grpc_proxies.task_data_service',
                            _FakeProxy())

        resp, _code = LogQueryService._get_task_logs_merged(
            LogListQuery(task_id=_TASK_ID, module='all', page=1, per_page=50))
        assert len(resp['data']['items']) == 2
        assert counting_reader['n'] == 1
        # stats 同参（module='all'）：命中同一缓存键，零复扫
        merged = LogQueryService._merge_file_stats(
            LogStatsQuery(task_id=_TASK_ID, module='all'), {'total': 0})
        assert merged['total'] == 2
        assert counting_reader['n'] == 1

    def test_module_all_key_equals_between_call_sites(self, log_root, monkeypatch):
        """list/stats 两调用点对 module='all' 构造的缓存键一致（归一前为
        'all' vs None 键分裂）。"""
        from api_gateway.application.services.log.log_query_service import LogQueryService
        from api_gateway.schemas.log import LogListQuery, LogStatsQuery

        calls = {'kwargs': None, 'resp': {'items': [], 'total': 0}}

        class _FakeProxy:
            def list_logs(self, **kwargs):
                calls['kwargs'] = kwargs
                return calls['resp']

        monkeypatch.setattr('api_gateway.infrastructure.grpc_proxies.task_data_service',
                            _FakeProxy())

        captured = {'list': None, 'stats': None}

        def capture(which):
            def _spy(inner_self, **kwargs):
                captured[which] = kwargs
                return original(inner_self, **kwargs)
            return _spy

        original = BusinessLogReader.read_entries
        monkeypatch.setattr(BusinessLogReader, 'read_entries', capture('list'))
        LogQueryService._get_task_logs_merged(
            LogListQuery(task_id=_TASK_ID, module='all', page=1, per_page=50))
        monkeypatch.setattr(BusinessLogReader, 'read_entries', capture('stats'))
        LogQueryService._merge_file_stats(
            LogStatsQuery(task_id=_TASK_ID, module='all'), {})

        root = 'any-root'
        assert BusinessLogReader._scan_cache_key(root, captured['list']) == \
            BusinessLogReader._scan_cache_key(root, captured['stats'])
        # 归一生效：两调用点下发的均为 None（不再携带字面 'all'）
        assert captured['list']['module'] is None
        assert captured['stats']['module'] is None


# ========== 4. DB 侧一致性：'all' = 不过滤（既有形态确认） ==========

class TestDbSideModuleAllConsistency:
    ROWS = [
        {'level': 'ERROR', 'module': 'executor', 'content': 'connect timeout'},
        {'level': 'WARNING', 'module': 'executor', 'content': 'slow response'},
        {'level': 'INFO', 'module': 'gateway', 'content': 'task started'},
    ]

    @pytest.fixture()
    def repo(self):
        from task_service.infrastructure.persistence.log_repository import LogRepository
        return LogRepository()

    def _insert(self, repo, rows):
        base = datetime(2026, 10, 10, 12, 0, 0)
        payload = []
        for i, row in enumerate(rows):
            item = dict(row)
            item.setdefault('time', base + timedelta(seconds=i))
            item.setdefault('category', 'Task')
            item.setdefault('source', 'int132')
            item['task_id'] = _TASK_ID
            payload.append(item)
        return repo.batch_create(payload)

    def test_list_and_stats_all_unfiltered(self, repo):
        """list_logs 与 get_stats 对 module='all' 均不过滤（两侧一致）。"""
        self._insert(repo, self.ROWS)
        assert repo.list_logs(task_id=_TASK_ID, module='all')['total'] == 3
        stats = repo.get_stats(task_id=_TASK_ID, module='all')
        assert stats['total'] == 3
        # 真实模块名过滤行为不变
        assert repo.list_logs(task_id=_TASK_ID, module='executor')['total'] == 2
        assert repo.get_stats(task_id=_TASK_ID, module='executor')['total'] == 2
