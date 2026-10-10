# -*- coding: utf-8 -*-
"""INT-100 测试工程师独立验收（集成级：真实 proto 契约 + 真实 servicer + 真实仓储）。

与开发自测 test_int100_log_query_pushdown.py（合并视图用 FakeProxy）互补：

- 验收1：大任务 DB 行拉取受 LOG_DB_MERGE_MAX_ROWS 约束且可配置——经真实
  _TaskDataProxy 构造 proto 请求 → in-process stub → 真实 servicer → 真实
  仓储全链路断言；文件侧物化受 business_max_scan_entries 约束（多文件场景
  超限后更旧文件不再解析）且可配置。
- 验收2：真实 list（_get_task_logs_merged）+ stats（_merge_file_stats）调用
  链在 TTL 窗口内共享一次文件扫描（解析计数断言）；两调用点缓存键一致性
  （覆盖前端默认参数与显式过滤组合）；TTL 内新写入行不可见（有界展示时延）、
  过期后可见。
- 验收3：旧调用方向后兼容——shared.clients._grpc_task_data.list_logs 旧签名
  （仅 task_id/level/page/per_page/日期，event_manager 进度日志路径）经真实
  servicer 行为不变；proto3 默认空值不引入新过滤；单级别大小写修复为超集
  语义（旧行为精确匹配 ERROR，新行为大小写不敏感，ERROR 精确值不变）。

已知边界（非本卡缺陷，验收备注）：文件侧 _match 对 module 参数未处理 'all'
（category/algorithm_type 均处理），api_gateway 合并视图 list 侧 module 原样
透传、stats 侧 'all'→None——显式传 module=all 的 API 调用方在文件侧会按
字面 'all' 过滤且两调用点缓存键不一致；前端 'all' 时不传该参数，默认轮询
不受影响。该形态系 INT-81 既有代码，INT-100 未触碰。
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + os.path.join(os.environ.get('TEMP', '/tmp'),
                                                  'int100_accept_unused.db'))
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest  # noqa: E402

import shared.logging  # noqa: E402  定位仓库根
from shared.logging import BusinessLogReader, LogEnvironment, reset_log_settings  # noqa: E402

_REPO_ROOT = str(Path(shared.logging.__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_TASK_ID = 9100200  # 独立 task_id，与开发自测用例及共享 sqlite 中其他用例隔离


def _make_settings(root, *, scan_ttl_seconds=3, scan_cap=100_000):
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
        business_max_scan_entries=scan_cap,
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


@pytest.fixture()
def insert_logs():
    def _insert(rows):
        from task_service.infrastructure.persistence.log_repository import LogRepository
        base = datetime(2026, 10, 10, 12, 0, 0)
        payload = []
        for i, row in enumerate(rows):
            item = dict(row)
            item.setdefault('time', base + timedelta(seconds=i))
            item.setdefault('category', 'Task')
            item.setdefault('module', 'exec')
            item.setdefault('source', 'int100-accept')
            item.setdefault('content', 'hello world')
            item['task_id'] = _TASK_ID
            payload.append(item)
        return LogRepository().batch_create(payload)
    return _insert


class _InProcessTaskDataStub:
    """in-process gRPC 替身：请求对象原样递给真实 servicer，返回真实 pb 响应。"""

    def __init__(self):
        from task_service.interfaces.grpc.task_data_service import TaskDataServiceServicer
        self.servicer = TaskDataServiceServicer()
        self.requests = []

    def ListLogs(self, request, context=None):
        self.requests.append(request)
        return self.servicer.ListLogs(request, context)


@pytest.fixture()
def inproc_stub(monkeypatch):
    stub = _InProcessTaskDataStub()
    import api_gateway.infrastructure.grpc_proxies.task_data_proxies as proxies
    monkeypatch.setattr(proxies, 'get_task_data_service_stub', lambda: stub)
    import shared.clients._grpc_task_data as old_client
    monkeypatch.setattr(old_client, 'get_task_data_service_stub', lambda: stub)
    return stub


def _merged_query(**overrides):
    from api_gateway.schemas.log import LogListQuery
    defaults = dict(task_id=_TASK_ID, page=1, per_page=50)
    defaults.update(overrides)
    return LogListQuery(**defaults)


# ========== 验收 1：大任务拉取量有界且可配置（真实契约全链路） ==========

class TestLargeTaskBoundedPulls:
    DB_ROWS = 250

    def _rows(self):
        rows = []
        for i in range(self.DB_ROWS):
            rows.append({'level': 'INFO', 'module': 'exec', 'content': f'db row {i}'})
        return rows

    def test_db_pull_capped_configurable_real_contract(self, insert_logs, inproc_stub,
                                                       log_root, monkeypatch):
        insert_logs(self._rows())
        from api_gateway.application.services.log.log_query_service import LogQueryService

        monkeypatch.setattr('shared.infrastructure.config.BaseConfig.LOG_DB_MERGE_MAX_ROWS', 100)
        resp, _ = LogQueryService._get_task_logs_merged(_merged_query(per_page=50))
        data = resp['data']
        # 真实 proto 请求：per_page == 100（受配置约束，不再硬编码 100000）
        assert len(inproc_stub.requests) == 1
        assert inproc_stub.requests[0].per_page == 100
        # 合并 total = 文件行(0) + DB 拉取行(100)，为真实总数 250 的下界
        assert data['total'] == 100

        # 可配置：改配置即生效
        monkeypatch.setattr('shared.infrastructure.config.BaseConfig.LOG_DB_MERGE_MAX_ROWS', 123)
        inproc_stub.requests.clear()
        LogQueryService._get_task_logs_merged(_merged_query(per_page=50))
        assert inproc_stub.requests[0].per_page == 123

        # 0 = 不限：int32 上限占位
        monkeypatch.setattr('shared.infrastructure.config.BaseConfig.LOG_DB_MERGE_MAX_ROWS', 0)
        inproc_stub.requests.clear()
        resp, _ = LogQueryService._get_task_logs_merged(_merged_query(per_page=50))
        assert inproc_stub.requests[0].per_page == 2 ** 31 - 1
        assert resp['data']['total'] == self.DB_ROWS

    def test_file_scan_cap_single_file_and_multi_file(self, log_root, monkeypatch):
        """文件侧物化有界（cap=50 保留最新 50 条）且可配置；多文件超限后
        更旧文件不再解析（扫描停止）。"""
        from shared.logging import BusinessLogReader

        def _write(rel, n, level='INFO', mtime=None):
            path = Path(log_root) / 'business' / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            base = datetime(2026, 10, 10, 12, 0, 0)
            with open(path, 'w', encoding='utf-8') as fh:
                for i in range(n):
                    t = (base + timedelta(seconds=i)).isoformat()
                    fh.write(f'{{"time": "{t}", "level": "{level}", '
                             f'"content": "file {rel} {i}", "task_id": {_TASK_ID}}}\n')
            if mtime is not None:
                os.utime(path, (mtime, mtime))
            return str(path)

        old = datetime(2026, 10, 9).timestamp()
        newer = datetime(2026, 10, 10, 12).timestamp()
        _write(f'{_TASK_ID}/dev-1/round-1/older.log', 60, mtime=old)
        _write(f'{_TASK_ID}/dev-1/round-1/newer.log', 60, mtime=newer)

        reader = BusinessLogReader()
        parse_calls = {'n': 0}
        original_parse = reader._parse_file

        def counting_parse(file_path):
            parse_calls['n'] += 1
            return original_parse(file_path)

        monkeypatch.setattr(reader, '_parse_file', counting_parse)

        # cap=50：物化 50 条（最新），且只解析最新文件（60 ≥ cap，旧文件跳过）
        monkeypatch.setattr('shared.logging.config._SETTINGS',
                            _make_settings(log_root, scan_cap=50))
        items = reader.read_entries(task_id=_TASK_ID)
        assert len(items) == 50
        assert parse_calls['n'] == 1

        # cap=200（> 单文件量）：两个文件都解析，共 120 条。
        # 缓存键不含 cap（同参数 TTL 内命中旧结果），切换配置需清缓存后复测。
        import shared.logging.business_reader as br
        br._SCAN_CACHE.clear()
        parse_calls['n'] = 0
        monkeypatch.setattr('shared.logging.config._SETTINGS',
                            _make_settings(log_root, scan_cap=200))
        items = reader.read_entries(task_id=_TASK_ID)
        assert len(items) == 120
        assert parse_calls['n'] == 2

        # cap=0 = 不限
        br._SCAN_CACHE.clear()
        monkeypatch.setattr('shared.logging.config._SETTINGS',
                            _make_settings(log_root, scan_cap=0))
        items = reader.read_entries(task_id=_TASK_ID)
        assert len(items) == 120


# ========== 验收 2：list + stats TTL 窗口内单次扫描（真实调用链） ==========

class TestListStatsSingleScan:
    FILE_N = 40

    def _write_file(self, log_root, n=FILE_N):
        path = Path(log_root) / 'business' / str(_TASK_ID) / 'dev-1' / 'round-1' / 'act.log'
        path.parent.mkdir(parents=True, exist_ok=True)
        base = datetime(2026, 10, 10, 12, 0, 0)
        with open(path, 'w', encoding='utf-8') as fh:
            for i in range(n):
                level = 'ERROR' if i % 10 == 0 else 'INFO'
                t = (base + timedelta(seconds=i)).isoformat()
                fh.write(f'{{"time": "{t}", "level": "{level}", '
                         f'"content": "file line {i}", "task_id": {_TASK_ID}}}\n')
        return str(path)

    @pytest.fixture()
    def counting_reader(self, monkeypatch):
        """类级计数 _parse_file：覆盖 merged list 与 merge_file_stats 各自新建
        的 BusinessLogReader 实例。"""
        import shared.logging.business_reader as br
        calls = {'n': 0}
        original_parse = br.BusinessLogReader._parse_file

        def counting_parse(self, file_path):
            calls['n'] += 1
            return original_parse(self, file_path)

        monkeypatch.setattr(br.BusinessLogReader, '_parse_file', counting_parse)
        return calls

    def _do_list(self, **overrides):
        from api_gateway.application.services.log.log_query_service import LogQueryService
        return LogQueryService._get_task_logs_merged(_merged_query(per_page=20, **overrides))

    def _do_stats(self, **overrides):
        from api_gateway.application.services.log.log_query_service import LogQueryService
        from api_gateway.schemas.log import LogStatsQuery
        defaults = dict(task_id=_TASK_ID)
        defaults.update(overrides)
        return LogQueryService._merge_file_stats(LogStatsQuery(**defaults), {})

    def test_list_then_stats_single_scan_in_ttl(self, log_root, inproc_stub,
                                                counting_reader):
        """验收2 核心断言：同一轮询周期 list（合并视图）+ stats（文件统计）
        共享一次文件扫描。"""
        self._write_file(log_root)
        resp, _ = self._do_list()
        assert resp['data']['total'] == self.FILE_N
        assert counting_reader['n'] == 1
        self._do_stats()
        assert counting_reader['n'] == 1  # stats 命中 TTL 缓存，零扫描
        # 第二轮轮询（TTL 内）依旧单扫描
        self._do_list()
        self._do_stats()
        assert counting_reader['n'] == 1

    def test_cache_key_consistency_between_call_sites(self, log_root, inproc_stub,
                                                      monkeypatch):
        """两调用点对相同查询语义构造的缓存键必须一致（list 原样透传 vs
        stats 'all'→None 的映射差异不得造成默认/显式过滤参数键分裂）。"""
        from shared.logging import BusinessLogReader
        captured = {'list': None, 'stats': None}

        def capture(which):
            def _spy(inner_self, **kwargs):
                captured[which] = kwargs
                return original(inner_self, **kwargs)
            return _spy

        original = BusinessLogReader.read_entries
        monkeypatch.setattr(BusinessLogReader, 'read_entries', capture('list'))
        from api_gateway.application.services.log.log_query_service import LogQueryService
        LogQueryService._get_task_logs_merged(_merged_query())
        monkeypatch.setattr(BusinessLogReader, 'read_entries', capture('stats'))
        self._do_stats()

        root = 'any-root'
        key_list = BusinessLogReader._scan_cache_key(root, captured['list'])
        key_stats = BusinessLogReader._scan_cache_key(root, captured['stats'])
        assert key_list == key_stats

        # 显式过滤组合（前端选择具体值时不传 'all'）同样一致
        captured['list'] = captured['stats'] = None
        monkeypatch.setattr(BusinessLogReader, 'read_entries', capture('list'))
        LogQueryService._get_task_logs_merged(_merged_query(
            level='error,warning', module='exec', category='Task',
            keyword='timeout', content_include='inc', content_exclude='exc'))
        monkeypatch.setattr(BusinessLogReader, 'read_entries', capture('stats'))
        self._do_stats(level='error,warning', module='exec', category='Task',
                       keyword='timeout', content_include='inc', content_exclude='exc')
        assert BusinessLogReader._scan_cache_key(root, captured['list']) == \
            BusinessLogReader._scan_cache_key(root, captured['stats'])

    def test_ttl_staleness_bounded_then_visible(self, log_root, inproc_stub,
                                                monkeypatch, counting_reader):
        """TTL 内新写入行不可见（有界展示时延，前端已注明）；TTL 过期后可见。"""
        self._write_file(log_root, 10)
        resp, _ = self._do_list()
        assert resp['data']['total'] == 10

        # TTL 内追加新行：仍返回旧结果、零扫描
        path = self._write_file(log_root, 12)
        resp, _ = self._do_list()
        assert resp['data']['total'] == 10
        assert counting_reader['n'] == 1

        # 过期后：重新扫描，新行可见
        import shared.logging.business_reader as br
        real_monotonic = __import__('time').monotonic
        clock = {'now': real_monotonic()}
        monkeypatch.setattr(br.time, 'monotonic', lambda: clock['now'])
        clock['now'] += 4.0  # TTL=3s
        resp, _ = self._do_list()
        assert resp['data']['total'] == 12
        assert counting_reader['n'] == 2
        assert os.path.exists(path)

    def test_different_filters_rescan(self, log_root, inproc_stub, counting_reader):
        self._write_file(log_root)
        self._do_list()
        assert counting_reader['n'] == 1
        self._do_list(level='error,info')
        assert counting_reader['n'] == 2


# ========== 验收 3：旧调用方向后兼容（真实旧签名 → 真实 servicer） ==========

class TestOldCallerBackwardCompat:
    ROWS = [
        {'level': 'ERROR', 'module': 'exec', 'content': 'timeout on device'},
        {'level': 'WARNING', 'module': 'gateway', 'content': 'slow but fine'},
        {'level': 'INFO', 'module': 'exec', 'content': 'all good'},
    ]

    def test_old_client_signature_returns_unfiltered_rows(self, insert_logs, inproc_stub):
        """event_manager 进度日志路径：shared.clients._grpc_task_data.list_logs
        旧签名（无新参数）→ 全量返回，新下推字段不得隐性过滤。"""
        from shared.clients import _grpc_task_data
        insert_logs(self.ROWS)
        result = _grpc_task_data.list_logs(task_id=_TASK_ID, page=1, per_page=20)
        assert result['total'] == 3
        assert {item['module'] for item in result['items']} == {'exec', 'gateway'}
        # 旧签名 level/日期参数行为不变
        assert _grpc_task_data.list_logs(
            task_id=_TASK_ID, level='ERROR', page=1, per_page=20)['total'] == 1
        # 真实 proto 请求新字段均为 proto3 默认空值
        req = inproc_stub.requests[-1]
        assert req.module == '' and req.keyword == '' and req.device_id == 0
        assert req.algorithm_type == '' and req.thread_id == ''

    def test_proto_defaults_introduce_no_filtering(self, insert_logs, inproc_stub):
        """只含旧字段的真实 proto 消息与新字段显式置空，经真实 servicer 结果一致。"""
        from shared.proto import task_service_pb2 as task_pb
        insert_logs(self.ROWS)
        old_style = task_pb.ListLogsRequest(task_id=_TASK_ID, page=1, per_page=20)
        explicit_empty = task_pb.ListLogsRequest(
            task_id=_TASK_ID, page=1, per_page=20,
            level='', start_date='', end_date='',
            module='', category='', mark='', device_id=0, api_id=0,
            test_case_id='', thread_id='', keyword='',
            content_include='', content_exclude='', algorithm_type='')
        r1 = inproc_stub.servicer.ListLogs(old_style)
        r2 = inproc_stub.servicer.ListLogs(explicit_empty)
        assert r1.success and r2.success
        assert r1.data == r2.data
        import json
        assert json.loads(r1.data)['total'] == 3

    def test_single_level_case_fix_is_superset(self, insert_logs, inproc_stub):
        """单级别大小写错位修复为超集语义：'ERROR' 精确匹配行为不变，
        'Error' 由旧行为（永不命中）变为命中。"""
        from shared.proto import task_service_pb2 as task_pb
        insert_logs(self.ROWS)
        for lv, expected in (('ERROR', 1), ('Error', 1), ('error', 1), ('INFO', 1)):
            resp = inproc_stub.servicer.ListLogs(
                task_pb.ListLogsRequest(task_id=_TASK_ID, level=lv, page=1, per_page=20))
            import json
            assert json.loads(resp.data)['total'] == expected, lv


# ========== 备查：module='all' 文件侧边界（既有形态，非本卡引入） ==========

class TestKnownEdgeModuleAll:
    def test_module_all_file_side_preexisting_shape(self, log_root, monkeypatch):
        """记录既有边界：文件侧 _match 不处理 module='all'（category/
        algorithm_type 均处理）。前端 'all' 时不传参，默认轮询不受影响；
        显式传 module=all 的 API 调用方文件行为 0（INT-81 起既有形态）。"""
        path = Path(log_root) / 'business' / str(_TASK_ID) / 'dev-1' / 'act.log'
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write('{"time": "2026-10-10T12:00:00", "level": "INFO", '
                     '"module": "exec", "content": "x", "task_id": %d}\n' % _TASK_ID)
        reader = BusinessLogReader()
        # category/algorithm_type 'all' = 不过滤（既有且正确）
        assert len(reader.read_entries(task_id=_TASK_ID, category='all')) == 1
        assert len(reader.read_entries(task_id=_TASK_ID, algorithm_type='all')) == 1
        # module='all' 按字面过滤（既有形态，记录用；非 INT-100 引入）
        assert len(reader.read_entries(task_id=_TASK_ID, module='all')) == 0
