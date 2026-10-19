# -*- coding: utf-8 -*-
"""INT-806 日志 user_id 过滤（「仅自己」视图范围）回归。

读侧：LogListQuery/LogStatsQuery 解析 user_id；LogRepository.list_logs /
get_stats 按 created_by_user_id 过滤（含无匹配 → 空）；gRPC servicer
ListLogs/GetLogStats 透传 user_id；网关 _authorize_log_user 403 判定；
任务合并视图 file 侧排除 + stats 跳过文件合并。

写侧：batch_create 写 created_by_user_id（显式 user_id / context 回退 /
None→NULL 三径）；_worker_mixin._process_batch 载荷透传 user_id。
"""
import json
import os
import tempfile
from datetime import datetime, timedelta
from types import SimpleNamespace

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + os.path.join(os.environ.get('TEMP', '/tmp'),
                                                  'int806_user_filter_unused.db'))
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest  # noqa: E402

import shared.logging  # noqa: E402
from shared.logging import BusinessLogReader, reset_log_settings  # noqa: E402
from shared.logging.enums import LogEnvironment  # noqa: E402
from shared.infrastructure.user_context import set_current_user_id  # noqa: E402
from task_service.infrastructure.persistence.log_repository import (  # noqa: E402
    LogRepository,
)

_TASK_ID = 9100806  # 隔离用 task_id


def _make_settings(root):
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
        business_scan_cache_ttl_seconds=3,
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
    """rows: [{user_id?, level, module, ...}]，time 依次递推保证顺序可断言。"""
    base = datetime(2026, 10, 10, 12, 0, 0)
    payload = []
    for i, row in enumerate(rows):
        item = dict(row)
        item.setdefault('time', base + timedelta(seconds=i))
        item.setdefault('category', 'Task')
        item.setdefault('module', 'exec')
        item.setdefault('source', 'int806')
        item.setdefault('content', 'hello world')
        item['task_id'] = _TASK_ID
        payload.append(item)
    return repo.batch_create(payload)


def _write_business_file(root, rel, entries):
    from pathlib import Path
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


class _State:
    def __init__(self, user_id):
        self.user_id = user_id


class _FakeRequest:
    """网关测试用伪请求：query_params 供 _parse_query_params，state.user_id 供 current_operator_id。"""
    def __init__(self, query_params=None, user_id=0):
        self.query_params = query_params or {}
        self.state = _State(user_id)


@pytest.fixture()
def fake_request():
    from api_gateway.infrastructure.request_adapter import set_current_request
    set_current_request(None)  # 清理上一用例残留

    def _set(query_params, user_id):
        set_current_request(_FakeRequest(query_params, user_id))

    yield _set
    set_current_request(None)


@pytest.fixture()
def fake_task_proxy(monkeypatch):
    """替换 api_gateway.infrastructure.grpc_proxies.task_data_service。

    捕获 list_logs / get_log_stats 调用 kwargs；resp 可注入伪造返回。
    """
    calls = {'kwargs': None, 'resp': {'items': [], 'total': 0, 'page': 1,
                                      'per_page': 20, 'pages': 0},
             'stats_kwargs': None,
             'stats_resp': {'total': 0, 'debug': 0, 'info': 0,
                            'warning': 0, 'error': 0, 'critical': 0}}

    class _FakeProxy:
        def list_logs(self, **kwargs):
            calls['kwargs'] = kwargs
            return calls['resp']

        def get_log_stats(self, **kwargs):
            calls['stats_kwargs'] = kwargs
            return calls['stats_resp']

    monkeypatch.setattr('api_gateway.infrastructure.grpc_proxies.task_data_service',
                        _FakeProxy())
    return calls


# ========== 1. Schema 解析 user_id ==========

class TestSchemaParseUserId:
    def test_list_query_parses_user_id(self):
        from api_gateway.schemas.log import LogListQuery
        q = LogListQuery(user_id=368)
        assert q.user_id == 368
        # query string 经 pydantic 字符串→int 强转
        assert LogListQuery.model_validate({'user_id': '368'}).user_id == 368
        assert LogListQuery().user_id is None

    def test_stats_query_parses_user_id(self):
        from api_gateway.schemas.log import LogStatsQuery
        assert LogStatsQuery(user_id=368).user_id == 368
        assert LogStatsQuery().user_id is None


# ========== 2. 仓储过滤 created_by_user_id ==========

@pytest.mark.usefixtures('_db')
class TestRepositoryUserFilter:
    ROWS = [
        {'user_id': 5, 'level': 'ERROR', 'module': 'executor', 'category': 'auth'},
        {'user_id': 5, 'level': 'INFO', 'module': 'gateway', 'category': 'auth'},
        {'user_id': 8, 'level': 'WARNING', 'module': 'executor', 'category': 'auth'},
        {'level': 'INFO', 'module': 'gateway', 'category': 'auth'},  # 无归属（历史行）
    ]

    def test_list_logs_filter_by_user(self, repo):
        _insert_logs(repo, self.ROWS)
        result = repo.list_logs(task_id=_TASK_ID, user_id=5)
        assert result['total'] == 2
        assert all(item['content'] for item in result['items'])
        result8 = repo.list_logs(task_id=_TASK_ID, user_id=8)
        assert result8['total'] == 1

    def test_list_logs_no_match_empty(self, repo):
        _insert_logs(repo, self.ROWS)
        result = repo.list_logs(task_id=_TASK_ID, user_id=999)
        assert result['items'] == []
        assert result['total'] == 0

    def test_list_logs_no_user_returns_all(self, repo):
        _insert_logs(repo, self.ROWS)
        # 旧调用方不传 user_id = 不过滤，行为不变
        assert repo.list_logs(task_id=_TASK_ID)['total'] == 4

    def test_get_stats_filter_by_user(self, repo):
        _insert_logs(repo, self.ROWS)
        stats = repo.get_stats(task_id=_TASK_ID, user_id=5)
        assert stats['total'] == 2
        assert stats['error'] == 1 and stats['info'] == 1 and stats['warning'] == 0

    def test_get_stats_no_match_empty(self, repo):
        _insert_logs(repo, self.ROWS)
        stats = repo.get_stats(task_id=_TASK_ID, user_id=999)
        assert stats['total'] == 0


# ========== 3. batch_create 写 created_by_user_id ==========

@pytest.mark.usefixtures('_db')
class TestBatchCreateOperator:
    def test_explicit_user_id(self, repo):
        rows = _insert_logs(repo, [{'user_id': 42, 'level': 'INFO'}])
        _assert_operator(repo, rows[0], 42)

    def test_context_fallback(self, repo):
        set_current_user_id(7)
        try:
            rows = _insert_logs(repo, [{'level': 'INFO'}])
        finally:
            set_current_user_id(None)
        _assert_operator(repo, rows[0], 7)

    def test_none_to_null(self, repo):
        # 无 user_id 且上下文未认证 → NULL（不硬编码兜底）
        rows = _insert_logs(repo, [{'level': 'INFO'}])
        _assert_operator(repo, rows[0], None)

    def test_zero_user_id_is_null(self, repo):
        # user_id=0 视为未认证 → normalize 为 None → 回退 context；无 context → NULL
        rows = _insert_logs(repo, [{'user_id': 0, 'level': 'INFO'}])
        _assert_operator(repo, rows[0], None)

    def test_explicit_overrides_context(self, repo):
        set_current_user_id(7)
        try:
            rows = _insert_logs(repo, [{'user_id': 42, 'level': 'INFO'}])
        finally:
            set_current_user_id(None)
        _assert_operator(repo, rows[0], 42)


def _assert_operator(repo, log_id, expected):
    """直读 PO 断言 created_by_user_id。"""
    from shared.models.database import get_db_session
    from task_service.infrastructure.persistence.models.system_models import Log
    session = get_db_session()
    try:
        po = session.get(Log, log_id)
        assert po.created_by_user_id == expected
    finally:
        session.close()


# ========== 4. gRPC servicer 透传 ==========

class TestServicerUserPassthrough:
    def _servicer(self):
        from task_service.interfaces.grpc.task_data_service import TaskDataServiceServicer
        return TaskDataServiceServicer(), SimpleNamespace

    def test_list_logs_user_id_pushdown(self, repo):
        servicer, ns = self._servicer()
        _insert_logs(repo, [
            {'user_id': 5, 'level': 'ERROR'}, {'user_id': 8, 'level': 'INFO'},
        ])
        request = ns(
            task_id=_TASK_ID, level='', start_date='', end_date='',
            page=1, per_page=20, module='', category='', mark='',
            device_id=0, api_id=0, test_case_id='', thread_id='', keyword='',
            content_include='', content_exclude='', algorithm_type='', user_id=5,
        )
        resp = servicer.ListLogs(request)
        data = json.loads(resp.data)
        assert data['total'] == 1

    def test_get_stats_user_id_pushdown(self, repo):
        servicer, ns = self._servicer()
        _insert_logs(repo, [
            {'user_id': 5, 'level': 'ERROR'}, {'user_id': 5, 'level': 'INFO'},
            {'user_id': 8, 'level': 'WARNING'},
        ])
        request = ns(
            level='', module='', category='', mark='', device_id=0, task_id=_TASK_ID,
            keyword='', content_include='', content_exclude='', start_time='',
            end_time='', algorithm_type='', user_id=5,
        )
        resp = servicer.GetLogStats(request)
        stats = json.loads(resp.data)
        assert stats['total'] == 2
        assert stats['error'] == 1 and stats['info'] == 1 and stats['warning'] == 0

    def test_proto_message_accepts_user_id(self):
        """重新生成的 pb2 接受 user_id 字段（契约扩展就绪）。"""
        from shared.proto import task_service_pb2 as task_pb
        req = task_pb.ListLogsRequest(task_id=1, page=1, per_page=10, user_id=368)
        assert req.user_id == 368
        stats = task_pb.GetLogStatsRequest(task_id=1, user_id=368)
        assert stats.user_id == 368


# ========== 5. 网关鉴权 403 ==========

class TestGatewayAuth:
    def _authorize(self, query_user_id):
        """调用 _authorize_log_user（current_operator_id 读当前 request.state.user_id）。"""
        from api_gateway.application.services.log.log_query_service import (
            LogQueryService,
        )
        return LogQueryService._authorize_log_user(query_user_id)

    def test_403_when_user_mismatch(self, fake_request):
        fake_request({'user_id': '368'}, 1)
        result = self._authorize(368)
        assert result is not None
        assert result[1] == 403

    def test_pass_when_user_matches(self, fake_request):
        fake_request({'user_id': '368'}, 368)
        assert self._authorize(368) is None

    def test_pass_when_operator_zero_auth_off(self, fake_request):
        # AUTH_MODE=off：operator=0 一律放行，不按字面 None 比较
        fake_request({'user_id': '368'}, 0)
        assert self._authorize(368) is None

    def test_pass_when_no_user_id(self, fake_request):
        fake_request({}, 1)
        assert self._authorize(None) is None

    def test_get_logs_passes_user_id_to_proxy(self, fake_request, fake_task_proxy):
        from api_gateway.application.services.log.log_query_service import (
            LogQueryService,
        )
        fake_request({'user_id': '368', 'page': '1', 'per_page': '50'}, 368)
        LogQueryService.get_logs()
        assert fake_task_proxy['kwargs']['user_id'] == 368

    def test_get_logs_403_mismatch_no_proxy_call(self, fake_request, fake_task_proxy):
        from api_gateway.application.services.log.log_query_service import (
            LogQueryService,
        )
        fake_request({'user_id': '368', 'page': '1', 'per_page': '50'}, 1)
        result = LogQueryService.get_logs()
        assert result[1] == 403
        assert fake_task_proxy['kwargs'] is None

    def test_get_stats_passes_user_id_to_proxy(self, fake_request, fake_task_proxy):
        from api_gateway.application.services.log.log_query_service import (
            LogQueryService,
        )
        fake_request({'user_id': '368'}, 368)
        LogQueryService.get_stats()
        assert fake_task_proxy['stats_kwargs']['user_id'] == 368

    def test_get_stats_403_mismatch(self, fake_request, fake_task_proxy):
        from api_gateway.application.services.log.log_query_service import (
            LogQueryService,
        )
        fake_request({'user_id': '368'}, 1)
        result = LogQueryService.get_stats()
        assert result[1] == 403
        assert fake_task_proxy['stats_kwargs'] is None


# ========== 6. 任务合并视图 file 侧排除 + stats 跳过文件合并 ==========

class TestMergedViewUserFilter:
    def test_merged_view_excludes_file_when_user_active(
            self, log_root, fake_task_proxy):
        """「仅自己」时文件侧业务执行日志排除，DB 侧按 user_id 过滤。"""
        from api_gateway.schemas.log import LogListQuery
        from api_gateway.application.services.log.log_query_service import (
            LogQueryService,
        )
        _write_business_file(log_root, f'{_TASK_ID}/dev-1/round-1/act.log',
                             [{'time': '2026-10-10T12:00:05', 'level': 'ERROR',
                               'content': 'file error'}])
        db_row = {'id': 999, 'time': '2026-10-10T11:00:00', 'level': 'ERROR',
                  'category': 'auth', 'module': 'gateway', 'source': 'db',
                  'content': 'db audit', 'task_id': _TASK_ID}
        fake_task_proxy['resp'] = {'items': [db_row], 'total': 1, 'page': 1,
                                   'per_page': 50, 'pages': 1}
        resp, _code = LogQueryService._get_task_logs_merged(
            LogListQuery(task_id=_TASK_ID, user_id=5, page=1, per_page=50))
        data = resp['data']
        assert data['total'] == 1  # 只有 DB 行，文件行被排除
        assert data['items'][0]['content'] == 'db audit'
        assert fake_task_proxy['kwargs']['user_id'] == 5

    def test_merged_view_without_user_still_merges_file(
            self, log_root, fake_task_proxy):
        """未激活 user_id 时保持原有合并语义（文件 + DB 两侧都显示）。"""
        from api_gateway.schemas.log import LogListQuery
        from api_gateway.application.services.log.log_query_service import (
            LogQueryService,
        )
        _write_business_file(log_root, f'{_TASK_ID}/dev-1/round-1/act.log',
                             [{'time': '2026-10-10T12:00:05', 'level': 'ERROR',
                               'content': 'file error'}])
        db_row = {'id': 999, 'time': '2026-10-10T11:00:00', 'level': 'ERROR',
                  'category': 'auth', 'module': 'gateway', 'source': 'db',
                  'content': 'db audit', 'task_id': _TASK_ID}
        fake_task_proxy['resp'] = {'items': [db_row], 'total': 1, 'page': 1,
                                   'per_page': 50, 'pages': 1}
        resp, _code = LogQueryService._get_task_logs_merged(
            LogListQuery(task_id=_TASK_ID, page=1, per_page=50))
        data = resp['data']
        assert data['total'] == 2
        assert fake_task_proxy['kwargs']['user_id'] is None

    def test_stats_skips_file_merge_when_user_active(
            self, log_root, fake_request, fake_task_proxy, monkeypatch):
        """user_id 激活时 get_stats 不得叠加文件侧统计（徽章数与列表一致）。"""
        from api_gateway.application.services.log.log_query_service import (
            LogQueryService,
        )
        _write_business_file(log_root, f'{_TASK_ID}/dev-1/round-1/act.log',
                             [{'time': '2026-10-10T12:00:05', 'level': 'ERROR',
                               'content': 'file error'}])
        fake_request({'user_id': '368', 'task_id': str(_TASK_ID)}, 368)
        called = {'merge': False}
        monkeypatch.setattr(LogQueryService, '_merge_file_stats',
                            lambda q, s: called.__setitem__('merge', True) or s)
        LogQueryService.get_stats()
        assert called['merge'] is False, 'user_id 激活时不得叠加文件侧统计'

    def test_stats_merges_file_when_no_user(
            self, log_root, fake_request, fake_task_proxy, monkeypatch):
        """未激活 user_id 时 stats 保持原合并语义（文件侧叠加）。"""
        from api_gateway.application.services.log.log_query_service import (
            LogQueryService,
        )
        _write_business_file(log_root, f'{_TASK_ID}/dev-1/round-1/act.log',
                             [{'time': '2026-10-10T12:00:05', 'level': 'ERROR',
                               'content': 'file error'}])
        fake_request({'task_id': str(_TASK_ID)}, 368)
        called = {'merge': False}
        monkeypatch.setattr(LogQueryService, '_merge_file_stats',
                            lambda q, s: called.__setitem__('merge', True) or s)
        LogQueryService.get_stats()
        assert called['merge'] is True


# ========== 7. worker 载荷透传 user_id ==========

class TestWorkerPayloadUserId:
    def test_process_batch_passes_user_id(self, monkeypatch):
        """_process_batch 载荷逐条透传 user_id（worker 线程不继承 contextvar）。"""
        from shared.utils.log_handler._worker_mixin import _WorkerMixin

        captured = []

        class _Stub(_WorkerMixin):
            enable_console_log = False

        def _fake_batch_create(logs_payload):
            captured.append(logs_payload)
            return [100 + i for i in range(len(logs_payload))]

        monkeypatch.setattr('shared.clients.grpc_clients.batch_create_logs',
                            _fake_batch_create)
        stub = _Stub()
        batch = [
            {'time': None, 'level': 'INFO', 'category': 'auth',
             'module': 'm', 'source': 's', 'content': 'c1', 'user_id': 42},
            {'time': None, 'level': 'INFO', 'category': 'auth',
             'module': 'm', 'source': 's', 'content': 'c2'},  # 无 user_id
        ]
        stub._process_batch(batch)
        assert len(captured) == 1
        payload = captured[0]
        assert payload[0]['user_id'] == 42
        assert payload[1]['user_id'] is None
