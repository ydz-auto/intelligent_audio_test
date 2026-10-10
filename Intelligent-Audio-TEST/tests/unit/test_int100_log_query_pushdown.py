# -*- coding: utf-8 -*-
"""INT-100 日志读取侧查询优化回归。

1. DB 侧过滤下推（task_service）：LogRepository.list_logs 支持逗号分隔
   多级别（大小写不敏感，与 get_stats/文件侧同语义）与 module/category/
   mark/device_id/api_id/test_case_id/thread_id/keyword/content_*/
   algorithm_type 下推过滤；TaskDataServiceServicer.ListLogs 契约透传；
   旧调用方不传新参数（proto3 默认空值）行为不变。
2. list/stats 单次扫描共享（shared）：BusinessLogReader.read_entries 同
   参数短 TTL 结果缓存——TTL 窗口内 list 与 stats 只扫一次文件（计数断言），
   不同参数/过期/关闭（0）各回退到真实扫描；只缓存查询结果（返回列表为
   快照拷贝，CQRS 查询侧只读）。
3. 合并视图 DB 拉取上限（api_gateway）：_db_merge_page_size 配置化
   （LOG_DB_MERGE_MAX_ROWS，0 = 不限→int32 上限占位），合并视图调用
   task_service 时全量过滤下推，不再 per_page=100000 全量拉取。
"""
import os
import sys
import tempfile
import types
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + os.path.join(os.environ.get('TEMP', '/tmp'),
                                                  'int100_pushdown_unused.db'))
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest  # noqa: E402

import shared.logging  # noqa: E402  定位仓库根
from shared.logging import BusinessLogReader, reset_log_settings  # noqa: E402
from shared.logging.enums import LogEnvironment  # noqa: E402
from task_service.infrastructure.persistence.log_repository import (  # noqa: E402
    LogRepository,
)

_REPO_ROOT = str(Path(shared.logging.__file__).resolve().parents[2])

if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_TASK_ID = 9100100  # 隔离用 task_id（同一 sqlite 文件可能被其他模块用例共用）


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
    """每个用例后清掉本卡 task_id 的行（module 级共享 sqlite，防计数串扰）。"""
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


@pytest.fixture()
def repo():
    return LogRepository()


def _insert_logs(repo, rows):
    """rows: [{level, module, content, ...}]，time 依次递推保证顺序可断言。"""
    base = datetime(2026, 10, 10, 12, 0, 0)
    payload = []
    for i, row in enumerate(rows):
        item = dict(row)
        item.setdefault('time', base + timedelta(seconds=i))
        item.setdefault('category', 'Task')
        item.setdefault('module', 'exec')
        item.setdefault('source', 'int100')
        item.setdefault('content', 'hello world')
        item['task_id'] = _TASK_ID
        payload.append(item)
    return repo.batch_create(payload)


def _write_business_file(root, rel, entries):
    path = Path(root) / 'business' / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as handle:
        for entry in entries:
            handle.write(
                '{"time": "' + entry['time'] + '", "level": "' + entry['level'] +
                '", "content": "' + entry.get('content', 'file line') +
                '", "task_id": ' + str(_TASK_ID) + '}\n'
            )
    return str(path)


# ========== 1. DB 侧过滤下推 ==========

@pytest.mark.usefixtures('_db')
class TestListLogsRepoPushdown:
    """LogRepository.list_logs 多级别/新过滤字段下推。"""

    ROWS = [
        {'level': 'ERROR', 'module': 'executor', 'category': 'Task',
         'content': 'connect timeout to device', 'thread_id': 'th-a', 'mark': 'flagged',
         'device_id': 3, 'api_id': 7, 'test_case_id': 'case-1', 'algorithm_type': 'asr'},
        {'level': 'WARNING', 'module': 'executor', 'category': 'Task',
         'content': 'slow response', 'thread_id': 'th-b', 'algorithm_type': 'asr'},
        {'level': 'INFO', 'module': 'gateway', 'category': 'System',
         'content': 'task started', 'thread_id': 'th-a', 'algorithm_type': 'tts'},
    ]

    def test_multi_level_csv_pushdown(self, repo):
        _insert_logs(repo, self.ROWS)
        result = repo.list_logs(task_id=_TASK_ID, level='ERROR,warning')
        levels = {item['level'] for item in result['items']}
        assert levels == {'ERROR', 'WARNING'}
        assert result['total'] == 2

    def test_multi_level_csv_case_insensitive(self, repo):
        _insert_logs(repo, self.ROWS)
        result = repo.list_logs(task_id=_TASK_ID, level='error, Warning ,')
        assert result['total'] == 2

    def test_single_level_backward_compat(self, repo):
        """旧调用方传单级别：语义不变（大小写不敏感匹配，与 get_stats 一致）。"""
        _insert_logs(repo, self.ROWS)
        result = repo.list_logs(task_id=_TASK_ID, level='error')
        assert result['total'] == 1
        assert result['items'][0]['level'] == 'ERROR'
        # 大小写变体同样命中（DB 存大写、前端传首字母大写的历史错位修复）
        assert repo.list_logs(task_id=_TASK_ID, level='Error')['total'] == 1

    def test_no_filters_returns_all(self, repo):
        _insert_logs(repo, self.ROWS)
        result = repo.list_logs(task_id=_TASK_ID)
        assert result['total'] == 3

    def test_module_category_pushdown(self, repo):
        _insert_logs(repo, self.ROWS)
        assert repo.list_logs(task_id=_TASK_ID, module='executor')['total'] == 2
        assert repo.list_logs(task_id=_TASK_ID, module='EXECUTOR')['total'] == 2
        assert repo.list_logs(task_id=_TASK_ID, category='System')['total'] == 1
        # 'all' 视为不过滤
        assert repo.list_logs(task_id=_TASK_ID, module='all')['total'] == 3

    def test_exact_match_fields(self, repo):
        _insert_logs(repo, self.ROWS)
        assert repo.list_logs(task_id=_TASK_ID, mark='flagged')['total'] == 1
        assert repo.list_logs(task_id=_TASK_ID, device_id=3)['total'] == 1
        assert repo.list_logs(task_id=_TASK_ID, api_id=7)['total'] == 1
        assert repo.list_logs(task_id=_TASK_ID, test_case_id='case-1')['total'] == 1
        assert repo.list_logs(task_id=_TASK_ID, algorithm_type='tts')['total'] == 1
        assert repo.list_logs(task_id=_TASK_ID, algorithm_type='all')['total'] == 3

    def test_containment_fields(self, repo):
        _insert_logs(repo, self.ROWS)
        assert repo.list_logs(task_id=_TASK_ID, thread_id='th-')['total'] == 3
        assert repo.list_logs(task_id=_TASK_ID, thread_id='th-a')['total'] == 2
        assert repo.list_logs(task_id=_TASK_ID, keyword='timeout')['total'] == 1
        assert repo.list_logs(task_id=_TASK_ID, content_include='slow')['total'] == 1
        assert repo.list_logs(task_id=_TASK_ID, content_exclude='slow')['total'] == 2

    def test_date_range_and_combined(self, repo):
        rows = _insert_logs(repo, self.ROWS)
        items = {item['content']: item for item in
                 repo.list_logs(task_id=_TASK_ID, per_page=100)['items']}
        times = {content: datetime.fromisoformat(item['time'])
                 for content, item in items.items()}
        mid = times['slow response']
        result = repo.list_logs(
            task_id=_TASK_ID,
            level='error,warning',
            start_date=mid.isoformat(),
            module='executor',
            thread_id='th-',
        )
        assert result['total'] == 1
        assert result['items'][0]['level'] == 'WARNING'
        assert rows  # batch_create 返回 id 列表

    def test_pagination_with_pushdown(self, repo):
        _insert_logs(repo, self.ROWS)
        page1 = repo.list_logs(task_id=_TASK_ID, level='error,warning', page=1, per_page=1)
        page2 = repo.list_logs(task_id=_TASK_ID, level='error,warning', page=2, per_page=1)
        assert page1['total'] == 2 and page2['total'] == 2
        assert page1['items'][0]['id'] != page2['items'][0]['id']


# ========== 2. gRPC servicer 契约透传 ==========

class TestListLogsServicerPassthrough:
    """TaskDataServiceServicer.ListLogs 新字段透传与旧调用方兼容。"""

    def _servicer(self):
        from types import SimpleNamespace

        from task_service.interfaces.grpc.task_data_service import TaskDataServiceServicer
        return TaskDataServiceServicer(), SimpleNamespace

    def test_new_fields_pushdown(self, repo):
        servicer, ns = self._servicer()
        _insert_logs(repo, TestListLogsRepoPushdown.ROWS)
        request = ns(
            task_id=_TASK_ID, level='error,warning', start_date='', end_date='',
            page=1, per_page=20, module='executor', category='', mark='',
            device_id=0, api_id=0, test_case_id='', thread_id='', keyword='',
            content_include='', content_exclude='', algorithm_type='',
        )
        resp = servicer.ListLogs(request)
        assert resp.success is True
        data = __import__('json').loads(resp.data)
        assert data['total'] == 2
        assert {item['level'] for item in data['items']} == {'ERROR', 'WARNING'}

    def test_old_caller_defaults_unchanged(self, repo):
        """旧调用方只传 task_id/level/分页/日期：结果与新增字段无关。"""
        servicer, ns = self._servicer()
        _insert_logs(repo, TestListLogsRepoPushdown.ROWS)
        request = ns(
            task_id=_TASK_ID, level='', start_date='', end_date='',
            page=1, per_page=20, module='', category='', mark='',
            device_id=0, api_id=0, test_case_id='', thread_id='', keyword='',
            content_include='', content_exclude='', algorithm_type='',
        )
        resp = servicer.ListLogs(request)
        data = __import__('json').loads(resp.data)
        assert data['total'] == 3

    def test_proto_message_accepts_new_fields(self):
        """重新生成的 pb2 接受新字段（契约扩展就绪）。"""
        from shared.proto import task_service_pb2 as task_pb
        req = task_pb.ListLogsRequest(
            task_id=1, level='error,warning', page=1, per_page=10,
            module='m', category='c', mark='flagged', device_id=3, api_id=7,
            test_case_id='case-1', thread_id='th', keyword='kw',
            content_include='inc', content_exclude='exc', algorithm_type='asr',
        )
        assert req.module == 'm' and req.content_exclude == 'exc'


# ========== 3. list/stats 单次扫描共享（TTL 结果缓存） ==========

class TestScanCacheTtl:
    """BusinessLogReader.read_entries 同参数短 TTL 缓存（计数断言）。"""

    FILE_ENTRIES = [
        {'time': '2026-10-10T12:00:00', 'level': 'ERROR', 'content': 'file error one'},
        {'time': '2026-10-10T12:00:01', 'level': 'WARNING', 'content': 'file warn one'},
        {'time': '2026-10-10T12:00:02', 'level': 'INFO', 'content': 'file info one'},
    ]

    @pytest.fixture()
    def scanned_reader(self, log_root, monkeypatch):
        """写一个业务日志文件，并对 _parse_file 计数。"""
        _write_business_file(log_root, f'{_TASK_ID}/dev-1/round-1/act.log',
                             self.FILE_ENTRIES)
        reader = BusinessLogReader()
        calls = {'n': 0}
        original_parse = reader._parse_file

        def counting_parse(file_path):
            calls['n'] += 1
            return original_parse(file_path)

        monkeypatch.setattr(reader, '_parse_file', counting_parse)
        return reader, calls

    def test_list_and_stats_share_one_scan(self, scanned_reader):
        """验收 2：TTL 窗口内 list 与 stats 相同过滤参数只扫一次文件。"""
        reader, calls = scanned_reader
        list_args = dict(task_id=_TASK_ID, level='error,warning,info',
                         category=None, module=None, keyword=None,
                         content_include=None, content_exclude=None,
                         algorithm_type=None, test_case_id=None,
                         start_time=None, end_time=None)
        first = reader.read_entries(**list_args)
        assert len(first) == 3
        assert calls['n'] == 1
        # stats 路径第二次同参查询：命中缓存，零扫描
        second = reader.read_entries(**list_args)
        assert calls['n'] == 1
        assert [item['id'] for item in second] == [item['id'] for item in first]

    def test_different_args_rescan(self, scanned_reader):
        reader, calls = scanned_reader
        reader.read_entries(task_id=_TASK_ID, level='error')
        assert calls['n'] == 1
        reader.read_entries(task_id=_TASK_ID, level='error,warning')
        assert calls['n'] == 2

    def test_ttl_expiry_rescans(self, scanned_reader, monkeypatch):
        reader, calls = scanned_reader
        clock = {'now': 1000.0}
        monkeypatch.setattr('shared.logging.business_reader.time',
                            types.SimpleNamespace(monotonic=lambda: clock['now']))
        args = dict(task_id=_TASK_ID, level='error')
        reader.read_entries(**args)
        assert calls['n'] == 1
        clock['now'] += 2.0  # TTL=3s 内
        reader.read_entries(**args)
        assert calls['n'] == 1
        clock['now'] += 2.0  # 越过 TTL
        reader.read_entries(**args)
        assert calls['n'] == 2

    def test_ttl_zero_disables_cache(self, log_root, monkeypatch):
        _write_business_file(log_root, f'{_TASK_ID}/dev-1/round-1/act.log',
                             self.FILE_ENTRIES)
        monkeypatch.setattr('shared.logging.config._SETTINGS',
                            _make_settings(log_root, scan_ttl_seconds=0))
        reader = BusinessLogReader()
        calls = {'n': 0}
        original_parse = reader._parse_file

        def counting_parse(file_path):
            calls['n'] += 1
            return original_parse(file_path)

        monkeypatch.setattr(reader, '_parse_file', counting_parse)
        args = dict(task_id=_TASK_ID, level='error')
        reader.read_entries(**args)
        reader.read_entries(**args)
        assert calls['n'] == 2

    def test_cached_result_is_snapshot_copy(self, scanned_reader):
        """CQRS 只读：命中返回列表快照，调用方修改列表不污染缓存。"""
        reader, _ = scanned_reader
        args = dict(task_id=_TASK_ID, level='error')
        first = reader.read_entries(**args)
        first.append({'id': -1})
        first.clear()
        second = reader.read_entries(**args)
        assert len(second) == 1
        assert second[0]['level'] == 'ERROR'

    def test_cache_eviction_bounded(self, log_root, monkeypatch):
        """不同过滤组合缓存条目有界（_SCAN_CACHE_MAX），不随参数组合无限增长。"""
        _write_business_file(log_root, f'{_TASK_ID}/dev-1/round-1/act.log',
                             self.FILE_ENTRIES)
        import shared.logging.business_reader as br
        for i in range(br._SCAN_CACHE_MAX + 8):
            reader = BusinessLogReader()
            reader.read_entries(task_id=_TASK_ID, keyword=f'kw-{i}')
        assert len(br._SCAN_CACHE) <= br._SCAN_CACHE_MAX


# ========== 4. 合并视图 DB 拉取上限与全量下推 ==========

class TestMergedViewPushdownAndCap:
    """_get_task_logs_merged 下推过滤 + LOG_DB_MERGE_MAX_ROWS 上限。"""

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

    def _query(self):
        from api_gateway.schemas.log import LogListQuery
        return LogListQuery(task_id=_TASK_ID, level='error,warning',
                            module='executor', keyword='timeout', page=1,
                            per_page=50)

    def test_merge_page_size_configurable(self, service, monkeypatch):
        monkeypatch.setattr('shared.infrastructure.config.BaseConfig.LOG_DB_MERGE_MAX_ROWS',
                            12345)
        assert service._db_merge_page_size() == 12345
        monkeypatch.setattr('shared.infrastructure.config.BaseConfig.LOG_DB_MERGE_MAX_ROWS',
                            0)
        assert service._db_merge_page_size() == 0

    def test_merged_view_pushdown_all_filters(self, service, fake_proxy):
        query = self._query()
        service._get_task_logs_merged(query)
        kwargs = fake_proxy['kwargs']
        assert kwargs['task_id'] == _TASK_ID
        assert kwargs['level'] == 'error,warning'  # 多级别整体下推，不再取首值
        assert kwargs['module'] == 'executor'
        assert kwargs['keyword'] == 'timeout'
        assert kwargs['page'] == 1

    def test_merged_view_db_pull_capped(self, service, fake_proxy, monkeypatch):
        monkeypatch.setattr('shared.infrastructure.config.BaseConfig.LOG_DB_MERGE_MAX_ROWS',
                            500)
        service._get_task_logs_merged(self._query())
        assert fake_proxy['kwargs']['per_page'] == 500

    def test_merged_view_unbounded_uses_int32_max(self, service, fake_proxy, monkeypatch):
        monkeypatch.setattr('shared.infrastructure.config.BaseConfig.LOG_DB_MERGE_MAX_ROWS',
                            0)
        service._get_task_logs_merged(self._query())
        assert fake_proxy['kwargs']['per_page'] == 2 ** 31 - 1

    def test_merged_view_merges_file_and_db(self, service, fake_proxy, log_root):
        _write_business_file(log_root, f'{_TASK_ID}/dev-1/round-1/act.log',
                             [{'time': '2026-10-10T12:00:05', 'level': 'ERROR',
                               'content': 'file error'}])
        db_row = {'id': 999, 'time': '2026-10-10T11:00:00', 'level': 'ERROR',
                  'category': 'Task', 'module': 'executor', 'source': 'db',
                  'content': 'db error', 'task_id': _TASK_ID}
        fake_proxy['resp'] = {'items': [db_row], 'total': 1}
        from api_gateway.schemas.log import LogListQuery
        resp, _code = service._get_task_logs_merged(
            LogListQuery(task_id=_TASK_ID, level='error,warning', page=1, per_page=50))
        data = resp['data']
        items = data['items']
        # 文件行（新）在前、DB 行（旧）在后，total = 两侧之和
        assert items[0]['content'] == 'file error'
        assert items[-1]['content'] == 'db error'
        assert data['total'] == 2
