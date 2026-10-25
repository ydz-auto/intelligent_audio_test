# -*- coding: utf-8 -*-
"""INT-838 日志模块 user_id 覆盖补全回归。

缺口：INT-806 只覆盖了 DB 入库写侧与读侧过滤，业务日志文件 JSONL 行、
WebSocket 实时推送载荷、读侧 LogItem 响应三处仍未带操作人 user_id。

本文件固化：
- 写侧业务日志：_enqueue_business_log 载荷带 user_id（emit 请求线程可得）；
  后台线程无上下文 → None（不硬编码兜底）；BusinessLogFileWriter 落盘 JSONL
  行带 user_id 字段
- WS 推送：_emit_websocket log_payload 含 user_id（DB 日志与业务日志均透传）
- 读侧：_log_po_to_dict 带 created_by_user_id；LogItem schema 有 user_id；
  _to_log_item 把 DB 行 created_by_user_id / 业务文件条目 user_id 映射到
  LogItem.user_id
"""
import json
import os
import tempfile
from datetime import datetime
from types import SimpleNamespace

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + os.path.join(os.environ.get('TEMP', '/tmp'),
                                                  'int838_unused.db'))
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest  # noqa: E402

from shared.infrastructure.user_context import set_current_user_id  # noqa: E402

_TASK_ID = 9100838  # 隔离用 task_id（与 INT-806 的 9100806 错开）


@pytest.fixture(scope='module', autouse=True)
def _db():
    """sqlite 建 logs 表（servicer 读侧用例用真实仓储）。"""
    from shared.models.database import Base, get_engine, init_db
    init_db()
    from task_service.infrastructure.persistence.models.system_models import Log
    Base.metadata.create_all(get_engine(), tables=[Log.__table__])
    yield


@pytest.fixture()
def repo():
    from task_service.infrastructure.persistence.log_repository import LogRepository
    return LogRepository()


@pytest.fixture(autouse=True)
def _clean_logs(_db):
    """每个用例后清掉本卡 task_id 的行（共享 sqlite，防计数串扰）。"""
    yield
    from shared.models.database import get_db_session
    from task_service.infrastructure.persistence.models.system_models import Log
    session = get_db_session()
    try:
        session.query(Log).filter(Log.task_id == _TASK_ID).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()


def _make_settings(root):
    from shared.logging.config import LogSettings
    from shared.logging.enums import LogEnvironment
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
        business_scan_cache_ttl_seconds=0,
    )


@pytest.fixture()
def log_root(tmp_path, monkeypatch):
    root = str(tmp_path / 'logs')
    monkeypatch.setattr('shared.logging.config._SETTINGS', _make_settings(root))
    yield root
    from shared.logging import reset_log_settings
    reset_log_settings()
    import shared.logging.audit_reader as ar
    ar._SCAN_CACHE.clear()


def _write_audit_file(root, date_seg, records):
    """在临时日志根下写审计 JSONL（审计读侧用例夹具）。"""
    from shared.logging.enums import AUDIT_DIR

    dir_path = os.path.join(root, AUDIT_DIR, date_seg)
    os.makedirs(dir_path, exist_ok=True)
    path = os.path.join(dir_path, 'auth.api_gateway.test-1.jsonl')
    with open(path, 'w', encoding='utf-8') as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + '\n')
    return path


def _business_record(**overrides):
    base = {
        'levelname': 'INFO',
        'module': 'task_engine',
        'category': 'execution',
        'source': 'backend',
        'content': 'step done',
        'task_id': 838,
        'device_id': 3,
        'api_id': None,
        'test_case_id': 'TC-838',
        'thread_id': None,
        'algorithm_type': None,
        'round': 2,
        'evaluation_id': None,
        'push_to_websocket': True,
        'from_log_and_emit': True,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


# ========== 1. 写侧业务日志载荷带 user_id ==========

class TestEnqueueBusinessLogUserId:

    def _enqueue(self, monkeypatch, record, user_id=None):
        import queue as _queue
        from shared.utils.log_handler._emit_mixin import _EmitMixin

        captured = []

        class _Stub(_EmitMixin):
            def __init__(self, settings):
                self._settings = settings
                self.queue = _queue.Queue()

        settings = _make_settings(tempfile.mkdtemp(prefix='int838_emit_'))
        stub = _Stub(settings)
        stub.queue.put_nowait = captured.append  # 直接捕获入队载荷
        set_current_user_id(user_id)
        try:
            stub._enqueue_business_log(record, record.task_id,
                                       record.test_case_id, record.category,
                                       record.content)
        finally:
            set_current_user_id(None)
        assert len(captured) == 1
        return captured[0]

    def test_entry_carries_user_id_from_context(self):
        record = _business_record()
        entry = self._enqueue(None, record, user_id=42)
        assert entry['user_id'] == 42

    def test_entry_user_id_none_without_context(self):
        # 后台线程无用户上下文 → None，不硬编码兜底
        record = _business_record()
        entry = self._enqueue(None, record, user_id=None)
        assert entry['user_id'] is None


# ========== 2. 业务日志文件 JSONL 行带 user_id ==========

class TestBusinessFileUserId:

    def _entry(self, user_id=None, **overrides):
        entry = {
            'time': '2026-10-19T12:00:00+08:00',
            'level': 'INFO',
            'category': 'execution',
            'module': 'Engine',
            'source': 'backend',
            'content': 'round line',
            'task_id': 838,
            'device_id': 7,
            'api_id': None,
            'test_case_id': 'TC-1',
            'thread_id': 't1',
            'algorithm_type': None,
            'user_id': user_id,
            'round': 2,
            'evaluation_id': None,
        }
        entry.update(overrides)
        return entry

    def test_entry_fields_whitelist_includes_user_id(self):
        from shared.logging.business_writer import _ENTRY_FIELDS
        assert 'user_id' in _ENTRY_FIELDS

    def test_write_lands_user_id_in_jsonl(self, log_root):
        from shared.logging import BusinessLogFileWriter
        writer = BusinessLogFileWriter(settings=_make_settings(log_root),
                                       service_name='svc', process_id=4321)
        rel = writer.write(self._entry(user_id=42))
        with open(os.path.join(log_root, rel), encoding='utf-8') as handle:
            line = json.loads(handle.readline())
        assert line['user_id'] == 42

    def test_write_keeps_null_user_id(self, log_root):
        # 后台线程无上下文 → user_id=None，JSONL 行为 null（不硬编码兜底）
        from shared.logging import BusinessLogFileWriter
        writer = BusinessLogFileWriter(settings=_make_settings(log_root),
                                       service_name='svc', process_id=4321)
        rel = writer.write(self._entry(user_id=None))
        with open(os.path.join(log_root, rel), encoding='utf-8') as handle:
            line = json.loads(handle.readline())
        assert line['user_id'] is None

    def test_reader_passes_user_id_through(self, log_root):
        from shared.logging import BusinessLogFileWriter, BusinessLogReader
        writer = BusinessLogFileWriter(settings=_make_settings(log_root),
                                       service_name='svc', process_id=4321)
        writer.write(self._entry(user_id=77))
        items = BusinessLogReader(root_dir=log_root).read_entries(task_id=838)
        assert len(items) == 1
        assert items[0]['user_id'] == 77


# ========== 3. WebSocket 推送载荷含 user_id ==========

class TestWebSocketPayloadUserId:

    def _emit_ws(self, monkeypatch, data):
        from shared.utils.log_handler._websocket_mixin import _WebSocketMixin

        published = {}

        class _FakeEventBus:
            def __init__(self, *a, **k):
                pass

            def publish(self, channel, event_type, message):
                published['message'] = message

        monkeypatch.setattr('shared.utils.redis_pubsub.EventBus', _FakeEventBus)
        _WebSocketMixin()._emit_websocket(data)
        return published['message']['log_payload']

    def test_db_log_payload_carries_user_id(self, monkeypatch):
        data = {
            'id': 1, '_db_failed': False, 'level': 'INFO', 'module': 'm',
            'content': 'db log', 'task_id': 1, 'test_case_id': None,
            'category': 'auth', 'source': 'backend', 'user_id': 42,
        }
        payload = self._emit_ws(monkeypatch, data)
        assert payload['user_id'] == 42

    def test_business_log_payload_carries_user_id(self, monkeypatch):
        data = {
            'id': -1, '_db_failed': False, 'level': 'INFO', 'module': 'm',
            'content': 'biz log', 'task_id': 1, 'test_case_id': None,
            'category': 'execution', 'source': 'backend', 'user_id': 9,
        }
        payload = self._emit_ws(monkeypatch, data)
        assert payload['user_id'] == 9

    def test_payload_user_id_none_when_absent(self, monkeypatch):
        data = {
            'id': 1, '_db_failed': False, 'level': 'INFO', 'module': 'm',
            'content': 'db log', 'task_id': 1, 'test_case_id': None,
            'category': 'auth', 'source': 'backend',
        }
        payload = self._emit_ws(monkeypatch, data)
        assert payload['user_id'] is None


# ========== 4. 读侧 LogItem 响应带 user_id ==========

class TestReadSideLogItemUserId:

    def test_log_po_to_dict_carries_created_by_user_id(self):
        from task_service.infrastructure.persistence.models.system_models import Log
        from task_service.infrastructure.persistence.log_repository import (
            _log_po_to_dict,
        )
        po = Log(
            id=1, time=datetime(2026, 10, 19, 12, 0, 0), level='INFO',
            category='auth', module='gateway', source='backend',
            content='audit', task_id=838, created_by_user_id=42,
        )
        d = _log_po_to_dict(po)
        assert d['created_by_user_id'] == 42

    def test_log_po_to_dict_null_stays_null(self):
        from task_service.infrastructure.persistence.models.system_models import Log
        from task_service.infrastructure.persistence.log_repository import (
            _log_po_to_dict,
        )
        po = Log(
            id=2, time=datetime(2026, 10, 19, 12, 0, 0), level='INFO',
            category='auth', module='gateway', source='backend',
            content='history row', task_id=838, created_by_user_id=None,
        )
        assert _log_po_to_dict(po)['created_by_user_id'] is None

    def test_log_item_schema_has_user_id(self):
        from api_gateway.schemas.log import LogItem
        item = LogItem(id=1, time='2026-10-19T12:00:00', level='INFO',
                       category='auth', module='m', source='s',
                       content='c', user_id=42)
        assert item.user_id == 42
        assert LogItem(id=1, time='t', level='L', category='c',
                       module='m', source='s', content='c').user_id is None

    def test_to_log_item_maps_db_row(self):
        from api_gateway.application.services.log.log_query_service import _to_log_item
        item = _to_log_item({
            'id': 1, 'time': '2026-10-19T12:00:00', 'level': 'INFO',
            'category': 'auth', 'module': 'gateway', 'source': 'db',
            'content': 'audit', 'created_by_user_id': 42,
        })
        assert item.user_id == 42

    def test_to_log_item_maps_business_file_entry(self):
        from api_gateway.application.services.log.log_query_service import _to_log_item
        item = _to_log_item({
            'id': 100, 'time': '2026-10-19T12:00:00', 'level': 'INFO',
            'category': 'execution', 'module': 'task_engine', 'source': 'backend',
            'content': 'step', 'user_id': 77,
        })
        assert item.user_id == 77

    def test_to_log_item_no_user_id_is_none(self):
        from api_gateway.application.services.log.log_query_service import _to_log_item
        item = _to_log_item({
            'id': 3, 'time': '2026-10-19T12:00:00', 'level': 'INFO',
            'category': 'system', 'module': 'm', 'source': 's', 'content': 'c',
        })
        assert item.user_id is None

    def test_merged_view_db_row_maps_user_id(self, monkeypatch, log_root):
        """任务合并视图：DB 历史行 created_by_user_id → LogItem.user_id。"""
        from api_gateway.schemas.log import LogListQuery
        from api_gateway.application.services.log.log_query_service import (
            LogQueryService,
        )
        import api_gateway.infrastructure.grpc_proxies as proxies_mod

        resp = {'items': [{'id': 999, 'time': '2026-10-19T11:00:00',
                           'level': 'ERROR', 'category': 'auth',
                           'module': 'gateway', 'source': 'db',
                           'content': 'db audit', 'task_id': 838,
                           'created_by_user_id': 5}],
                'total': 1, 'page': 1, 'per_page': 50, 'pages': 1}

        class _FakeProxy:
            def list_logs(self, **kwargs):
                return resp

        monkeypatch.setattr(proxies_mod, 'task_data_service', _FakeProxy())
        result, _code = LogQueryService._get_task_logs_merged(
            LogListQuery(task_id=838, page=1, per_page=50))
        items = result['data']['items']
        assert len(items) == 1
        assert items[0]['user_id'] == 5


# ========== 5. gRPC servicer 读侧带 user_id（真实仓储 + sqlite） ==========

@pytest.mark.usefixtures('_db')
class TestServicerReadSideUserId:
    """gRPC ListLogs / ListLogsAfterId 响应 items 带 created_by_user_id
    （真实仓储读模型，链路 = 网关 → gRPC → 仓储 _log_po_to_dict）。"""

    def _insert_log(self, repo, user_id=None):
        from datetime import datetime
        return repo.batch_create([{
            'time': datetime(2026, 10, 19, 12, 0, 0),
            'level': 'INFO', 'category': 'auth', 'module': 'gateway',
            'source': 'audit', 'content': 'operator action',
            'task_id': _TASK_ID, 'user_id': user_id,
        }])[0]

    def test_list_logs_response_carries_created_by_user_id(self, repo):
        from types import SimpleNamespace
        from task_service.interfaces.grpc.task_data_service import (
            TaskDataServiceServicer,
        )
        self._insert_log(repo, user_id=5)
        servicer = TaskDataServiceServicer()
        req = SimpleNamespace(
            task_id=_TASK_ID, level='', start_date='', end_date='',
            page=1, per_page=20, module='', category='', mark='',
            device_id=0, api_id=0, test_case_id='', thread_id='', keyword='',
            content_include='', content_exclude='', algorithm_type='',
            user_id=0,
        )
        resp = servicer.ListLogs(req)
        items = json.loads(resp.data)['items']
        assert items[0]['created_by_user_id'] == 5

    def test_list_logs_after_id_response_carries_created_by_user_id(self, repo):
        from types import SimpleNamespace
        from task_service.interfaces.grpc.task_data_service import (
            TaskDataServiceServicer,
        )
        log_id = self._insert_log(repo, user_id=5)
        servicer = TaskDataServiceServicer()
        resp = servicer.ListLogsAfterId(
            SimpleNamespace(last_id=log_id - 1, limit=100))
        items = json.loads(resp.data)['items']
        assert items[0]['created_by_user_id'] == 5

    def test_list_logs_unattributed_row_is_null(self, repo):
        from types import SimpleNamespace
        from task_service.interfaces.grpc.task_data_service import (
            TaskDataServiceServicer,
        )
        self._insert_log(repo, user_id=None)  # 历史行无归属
        servicer = TaskDataServiceServicer()
        req = SimpleNamespace(
            task_id=_TASK_ID, level='', start_date='', end_date='',
            page=1, per_page=20, module='', category='', mark='',
            device_id=0, api_id=0, test_case_id='', thread_id='', keyword='',
            content_include='', content_exclude='', algorithm_type='',
            user_id=0,
        )
        resp = servicer.ListLogs(req)
        items = json.loads(resp.data)['items']
        assert items[0]['created_by_user_id'] is None


# ========== 6. 网关 refresh_logs 读侧带 user_id ==========

class TestRefreshLogsUserId:
    def test_refresh_logs_maps_user_id(self, log_root):
        """refresh_logs：审计文件条目 user_id（写侧 H2 提取的 operator_id）→ LogItem.user_id。

        INT-1812 起 refresh 的增量源是审计文件游标（契约 §Q4），不再读 logs 表
        id；本用例随之改为构造审计 JSONL 行，映射口径不变（两前端零改动）。
        """
        from api_gateway.application.services.log.log_query_service import (
            LogQueryService,
        )
        from api_gateway.infrastructure.request_adapter import set_current_request
        from shared.logging import cursor_to_date_seg

        cursor = 1_790_000_000_000_000  # 契约 §Q4 游标域（事件时间 epoch 微秒）
        _write_audit_file(log_root, cursor_to_date_seg(cursor), [{
            'cursor': cursor,
            'time': '2026-09-23 12:00:00.000000',
            'level': 'INFO', 'category': 'auth', 'module': 'gateway',
            'source': 'api_gateway', 'service': 'api_gateway',
            'event': 'AUTH_LOGIN', 'operator_id': 42, 'user_id': 42,
            'content': '{"operator_id": 42, "event": "AUTH_LOGIN"}',
        }])

        class _FakeReq:
            state = SimpleNamespace(_json_body={'last_id': cursor - 1})

        set_current_request(_FakeReq())
        try:
            result, _code = LogQueryService.refresh_logs()
        finally:
            set_current_request(None)
        items = result['data']['items']
        assert items[0]['user_id'] == 42
        assert items[0]['id'] == cursor
