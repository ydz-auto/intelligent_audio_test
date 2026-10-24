# -*- coding: utf-8 -*-
"""INT-1806 审计事件落文件写入侧单测（INT-1793 契约卡片 1）。

覆盖契约 §5 卡片 1 的可测项：
- 三分支互斥：task_id → 业务文件；audit_event → 审计文件；其余 → 服务文件（含 D2 预览日志）
- H1：同 category 的运维日志（category='device' 无 audit_event）不进审计目录
- H2：从 content JSON 提取 operator_id / operator / target_* / action / result，user_id = operator_id
- H3：cursor = 事件时间 epoch 微秒，同微秒 +1，进程内严格递增，< 2^53
- 字段白名单（不落 mark / id，拒绝任意 kwargs）
- 按天切换目录、超限切分 -NNN.jsonl
- BatchCreateLogs 按 sink 分流（audit_file → 审计文件并返回 cursor；db → 原仓储实现）
- LOG_AUDIT_DB_ENABLED=True 时同一事件文件一行 + DB 一行
- 保留清扫：审计子树按目录日期、到期先归档后删除、归档失败保留本地、单清扫者、
  统一 30 天（不得出现 180 天默认值）
"""
import json
import os
import tempfile
from datetime import date, datetime, timedelta, timezone

import pytest

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int1806_sink_') + '/sink.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.logging.audit_writer import (  # noqa: E402
    AuditLogFileWriter,
    epoch_micros,
    reset_audit_writer,
    write_audit_event,
)
from shared.logging.config import LogSettings  # noqa: E402
from shared.logging.enums import AUDIT_DIR, AuditLogCategory, LogEnvironment  # noqa: E402
from shared.logging.path_builder import BUSINESS_DIR  # noqa: E402
from shared.logging.retention import (  # noqa: E402
    audit_cutoff_date,
    sweep_audit_dates,
    sweep_log_root,
)
from shared.models.common_enums import AuditEvent  # noqa: E402

_CST = timezone(timedelta(hours=8))
_CURSOR_SAFE_MAX = 2 ** 53


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
        sweep_service='api_gateway',
        file_retention_days=30,
    )
    values.update(overrides)
    return LogSettings(**values)


def _writer(tmp_path, **overrides):
    return AuditLogFileWriter(
        settings=_make_settings(tmp_path / 'logs', **overrides),
        service_name='api_gateway',
        process_id='host-1',
    )


def _audit_file(tmp_path, day, category='auth', service='api_gateway'):
    return (tmp_path / 'logs' / AUDIT_DIR / day
            / f'{category}.{service}.host-1.jsonl')


def _entry(**overrides):
    base = {
        'time': datetime(2026, 10, 24, 9, 0, 0, 111111, tzinfo=_CST),
        'level': 'INFO',
        'category': 'auth',
        'module': 'auth_login',
        'source': 'api_gateway',
        'event': AuditEvent.AUTH_LOGIN.value,
        'service': 'api_gateway',
        'content': json.dumps({'event': 'AUTH_LOGIN', 'operator_id': 369,
                               'operator': '接线测试_admin', 'target_id': 369}),
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# 写入器：白名单 / H2 提取 / H3 游标
# ---------------------------------------------------------------------------

class TestAuditWriterRecord:

    def test_path_template_and_cursor(self, tmp_path):
        writer = _writer(tmp_path)
        cursor = writer.write(_entry())
        assert cursor == epoch_micros(datetime(2026, 10, 24, 9, 0, 0, 111111, tzinfo=_CST))
        assert cursor < _CURSOR_SAFE_MAX
        path = _audit_file(tmp_path, '2026-10-24')
        assert path.exists(), '审计文件未按 audit/{date}/{category}.{service}.{identity}.jsonl 落盘'
        record = json.loads(path.read_text(encoding='utf-8').strip())
        assert record['cursor'] == cursor
        assert record['event'] == 'AUTH_LOGIN'
        assert record['category'] == 'auth'
        assert record['service'] == 'api_gateway'      # 产生事件的进程
        assert record['time'] == '2026-10-24 09:00:00.111111'

    def test_h2_operator_extracted_from_content_json(self, tmp_path):
        writer = _writer(tmp_path)
        writer.write(_entry())
        record = json.loads(_audit_file(tmp_path, '2026-10-24').read_text(encoding='utf-8'))
        assert record['operator_id'] == 369
        assert record['operator'] == '接线测试_admin'
        assert record['user_id'] == 369          # 「仅自己」过滤口径
        assert record['target_id'] == 369
        assert record['result'] == 'success'     # 缺省显式写入 success
        assert record['detail'] == {'event': 'AUTH_LOGIN', 'operator_id': 369,
                                    'operator': '接线测试_admin', 'target_id': 369}
        assert json.loads(record['content'])['operator_id'] == 369

    def test_h2_target_and_action_fields(self, tmp_path):
        writer = _writer(tmp_path)
        writer.write(_entry(category='visibility', content=json.dumps({
            'event': 'PRIVATE_RESOURCE_ACCESS', 'resource_type': 'task',
            'resource_id': '12', 'action': 'read', 'operator_id': 7,
            'operator': 'admin',
        })))
        record = json.loads(
            _audit_file(tmp_path, '2026-10-24', 'visibility').read_text(encoding='utf-8'))
        assert record['target_type'] == 'task'
        assert record['target_id'] == '12'
        assert record['action'] == 'read'
        assert record['user_id'] == 7

    def test_event_required_otherwise_dropped(self, tmp_path):
        writer = _writer(tmp_path)
        # 条目 event 与 content JSON 都没有事件名：不算审计，直接丢弃（H1）
        assert writer.write(_entry(event=None, content=json.dumps({'operator_id': 1}))) is None
        assert not (tmp_path / 'logs' / AUDIT_DIR / '2026-10-24').exists(), \
            '无 event 的条目不得进审计目录（H1）'

    def test_field_whitelist_drops_mark_and_arbitrary_kwargs(self, tmp_path):
        writer = _writer(tmp_path)
        writer.write(_entry(mark='flagged', id=999, raw_secret='x', extra_field={'a': 1}))
        record = json.loads(_audit_file(tmp_path, '2026-10-24').read_text(encoding='utf-8'))
        assert 'mark' not in record, '文件日志不可标记，不得落 mark'
        assert 'id' not in record, '读侧 id = cursor，不得落 id'
        assert 'raw_secret' not in record and 'extra_field' not in record
        assert set(record) <= {
            'cursor', 'time', 'level', 'category', 'module', 'source', 'service',
            'event', 'operator_id', 'operator', 'target_type', 'target_id', 'action',
            'result', 'user_id', 'detail', 'content',
            'task_id', 'device_id', 'api_id', 'test_case_id', 'thread_id', 'algorithm_type',
        }

    def test_cursor_strictly_increasing_same_microsecond(self, tmp_path):
        writer = _writer(tmp_path)
        same = datetime(2026, 10, 24, 9, 0, 0, 500000, tzinfo=_CST)
        first = writer.write(_entry(time=same))
        second = writer.write(_entry(time=same))
        third = writer.write(_entry(time=same + timedelta(microseconds=1)))
        assert second == first + 1, '同微秒冲突必须 +1'
        assert third > second, 'cursor 必须与事件时间同序且严格递增'
        lines = _audit_file(tmp_path, '2026-10-24').read_text(encoding='utf-8').splitlines()
        cursors = [json.loads(line)['cursor'] for line in lines]
        assert cursors == sorted(cursors) and len(set(cursors)) == 3

    def test_disabled_writes_nothing(self, tmp_path):
        writer = _writer(tmp_path, audit_enabled=False)
        assert writer.write(_entry()) is None
        assert not (tmp_path / 'logs' / AUDIT_DIR).exists()


class TestRotationAndDaySwitch:

    def test_day_switch_creates_new_date_dir(self, tmp_path):
        writer = _writer(tmp_path)
        writer.write(_entry(time=datetime(2026, 10, 23, 23, 59, tzinfo=_CST)))
        writer.write(_entry(time=datetime(2026, 10, 24, 0, 1, tzinfo=_CST)))
        assert (tmp_path / 'logs' / AUDIT_DIR / '2026-10-23').is_dir()
        assert (tmp_path / 'logs' / AUDIT_DIR / '2026-10-24').is_dir()

    def test_size_split_uses_index_suffix(self, tmp_path):
        writer = _writer(tmp_path, audit_max_bytes=200)
        for index in range(5):
            writer.write(_entry(time=datetime(2026, 10, 24, 9, 0, index, tzinfo=_CST)))
        day_dir = tmp_path / 'logs' / AUDIT_DIR / '2026-10-24'
        names = sorted(os.listdir(day_dir))
        assert any(name.endswith('-001.jsonl') for name in names), \
            f'超限未切分 -NNN 序号: {names}'


# ---------------------------------------------------------------------------
# emit 三分支互斥 + H1 + D2 + 双写
# ---------------------------------------------------------------------------

@pytest.fixture()
def emit_env(tmp_path, monkeypatch):
    """独立 DatabaseLogHandler：worker 冲刷后由 fake batch_create_logs 捕获载荷。"""
    import shared.clients.grpc_clients as grpc_clients_mod
    import shared.utils.log_handler._state as lh_state
    from shared.utils.log_handler import DatabaseLogHandler

    prev = lh_state._global_db_handler
    if prev is not None:
        prev.queue.put(None)
        prev_worker = getattr(prev, 'worker_thread', None)
        if prev_worker is not None:
            prev_worker.join(timeout=2.0)

    captured = []
    files = []

    def _fake_batch_create(logs_payload):
        captured.extend(logs_payload)
        ids = []
        for item in logs_payload:
            if item.get('sink') == 'audit_file':
                cursor = 1_792_814_400_000_000 + len(captured)
                files.append(item)
                ids.append(cursor)
            else:
                ids.append(9000 + len(ids))
        return ids

    monkeypatch.setattr(grpc_clients_mod, 'batch_create_logs', _fake_batch_create)
    monkeypatch.setattr(grpc_clients_mod, 'get_log_count', lambda: {'total': 0})
    monkeypatch.setattr(
        grpc_clients_mod, 'archive_logs',
        lambda days=30, dry_run=False: {'groups': {}, 'remaining_count': 0})
    import shared.clients.oss_client as oss_client_mod
    monkeypatch.setattr(oss_client_mod.oss, 'is_available', lambda: False)
    monkeypatch.setattr('shared.logging.config._SETTINGS',
                        _make_settings(tmp_path / 'logs'))
    monkeypatch.chdir(tmp_path)
    handler = DatabaseLogHandler()
    handler._batch_size = 1
    handler.set_console_log(False)
    monkeypatch.setattr(lh_state, '_global_db_handler', handler)
    yield handler, captured, tmp_path / 'logs'
    handler.queue.put(None)


def _wait_for(condition, timeout=3.0, interval=0.05):
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(interval)
    return condition()


class TestEmitThreeBranches:

    def test_audit_event_goes_to_audit_sink_only(self, emit_env):
        from auth_service.application.services.auth_audit import write_auth_audit
        handler, captured, logs_root = emit_env
        write_auth_audit(AuditEvent.AUTH_USER_CREATED, 'user_management',
                         {'operator_id': 1, 'target_id': 2})
        assert _wait_for(lambda: len(captured) >= 1), '审计事件未进入 gRPC 批次'
        item = captured[0]
        assert item['sink'] == 'audit_file'
        assert item['event'] == 'AUTH_USER_CREATED'
        assert item['service'], '审计条目必须携带产生进程名（H4 路径段）'
        assert item['content']  # 原 content 字符串原样透传
        # 不写服务文件（一条事件恰好一行）
        service_file = logs_root / 'unknown' / f"app-{_process_identity()}.log"
        if service_file.exists():
            assert 'AUTH_USER_CREATED' not in service_file.read_text(encoding='utf-8')

    def test_device_ops_log_without_audit_event_never_enters_audit(self, emit_env):
        """H1：同 category='device' 的运维日志只进服务文件，不进审计目录。"""
        from shared.utils.log_handler import log_not_emit
        handler, captured, logs_root = emit_env
        log_not_emit('INFO', 'DeviceGroupCommand', 'group command dispatched',
                     category='device', source='backend', device_id=5)
        assert not _wait_for(lambda: len(captured) >= 1, timeout=1.5), \
            '无 audit_event 的运维日志不得进入 gRPC 批次（审计文件）'
        assert not (logs_root / AUDIT_DIR).exists(), '运维日志进入了审计目录'
        assert _wait_for(lambda: any(logs_root.rglob('app-*.log'))), '运维日志未写服务文件'

    def test_device_audit_event_enters_audit_sink(self, emit_env):
        """H1 对照：device_audit 的真审计事件（带 audit_event）进审计文件。"""
        from api_gateway.application.services.device.device_audit import write_device_audit
        handler, captured, logs_root = emit_env
        write_device_audit(AuditEvent.DEVICE_GROUP_CREATED, 'device_group',
                           {'name': '接线测试_组', 'success': True})
        assert _wait_for(lambda: len(captured) >= 1), 'device 审计事件未进审计批次'
        assert captured[0]['sink'] == 'audit_file'
        assert captured[0]['category'] == 'device'

    def test_preview_log_with_case_id_only_serves_file(self, emit_env):
        """D2：test_case_id 有值、无 task_id 的预览日志只写服务文件，DB 增量 0。"""
        from shared.utils.testcase_helpers import log as common_log
        handler, captured, logs_root = emit_env
        common_log('INFO', 'case preview step', test_case_id='TC-9', category='preview')
        assert not _wait_for(lambda: len(captured) >= 1, timeout=1.5), '预览日志不应入 DB 批次'
        assert _wait_for(lambda: any(logs_root.rglob('app-*.log')))

    def test_task_log_goes_to_business_file(self, emit_env):
        from shared.utils.log_handler import log_not_emit
        handler, captured, logs_root = emit_env
        log_not_emit('INFO', 'task_engine', 'step done', category='execution',
                     task_id=77, device_id=3, round=1)
        assert not _wait_for(lambda: len(captured) >= 1, timeout=1.5)
        assert _wait_for(lambda: any((logs_root / BUSINESS_DIR / '77').rglob('*.log')))

    def test_audit_db_fallback_writes_two_entries(self, tmp_path, monkeypatch):
        """LOG_AUDIT_DB_ENABLED=True：同一事件审计文件一行 + DB 一行。"""
        import shared.clients.grpc_clients as grpc_clients_mod
        import shared.utils.log_handler._state as lh_state
        from shared.utils.log_handler import DatabaseLogHandler, log_not_emit

        prev = lh_state._global_db_handler
        if prev is not None:
            prev.queue.put(None)
            prev_worker = getattr(prev, 'worker_thread', None)
            if prev_worker is not None:
                prev_worker.join(timeout=2.0)

        captured = []

        def _fake_batch_create(logs_payload):
            captured.extend(logs_payload)
            return list(range(len(logs_payload)))

        monkeypatch.setattr(grpc_clients_mod, 'batch_create_logs', _fake_batch_create)
        monkeypatch.setattr(grpc_clients_mod, 'get_log_count', lambda: {'total': 0})
        monkeypatch.setattr(
            grpc_clients_mod, 'archive_logs',
            lambda days=30, dry_run=False: {'groups': {}, 'remaining_count': 0})
        import shared.clients.oss_client as oss_client_mod
        monkeypatch.setattr(oss_client_mod.oss, 'is_available', lambda: False)
        monkeypatch.setattr('shared.logging.config._SETTINGS',
                            _make_settings(tmp_path / 'logs', audit_db_enabled=True))
        monkeypatch.chdir(tmp_path)
        handler = DatabaseLogHandler()
        handler._batch_size = 2
        handler.set_console_log(False)
        monkeypatch.setattr(lh_state, '_global_db_handler', handler)
        try:
            log_not_emit('INFO', 'auth_login', json.dumps({'operator_id': 5}),
                         category='auth', source='api_gateway',
                         audit_event=AuditEvent.AUTH_LOGIN)
            assert _wait_for(lambda: len(captured) >= 2), '双写未产生两条载荷'
            sinks = sorted(item['sink'] for item in captured)
            assert sinks == ['audit_file', 'db'], f'期望审计 + DB 各一条: {sinks}'
        finally:
            handler.queue.put(None)


def _process_identity():
    from shared.logging.identity import process_identity
    return process_identity()


# ---------------------------------------------------------------------------
# BatchCreateLogs 按 sink 分流（task_service 单写者）
# ---------------------------------------------------------------------------

class TestBatchCreateLogsSink:

    def _servicer(self, monkeypatch, tmp_path):
        from shared.proto import task_service_pb2 as task_pb
        from task_service.interfaces.grpc import task_data_service as module

        db_rows = []

        def _fake_batch_create(rows):
            db_rows.extend(rows)
            return [5000 + index for index in range(len(rows))]

        monkeypatch.setattr(module.log_repository, 'batch_create', _fake_batch_create)
        log_settings = _make_settings(tmp_path / 'logs')
        monkeypatch.setattr('shared.logging.config._SETTINGS', log_settings)
        monkeypatch.setattr('shared.utils.log_handler._state._global_db_handler', None)
        reset_audit_writer()
        servicer = module.TaskDataServiceServicer()
        return servicer, task_pb, db_rows, tmp_path / 'logs'

    def test_audit_file_sink_writes_jsonl_and_returns_cursor(self, monkeypatch, tmp_path):
        servicer, task_pb, db_rows, logs_root = self._servicer(monkeypatch, tmp_path)
        payload = [dict(_entry())]
        payload[0]['sink'] = 'audit_file'
        response = servicer.BatchCreateLogs(
            task_pb.BatchCreateLogsRequest(logs_json=json.dumps(payload, default=str)), None)
        assert response.success, response.message
        ids = json.loads(response.data)['ids']
        assert ids and isinstance(ids[0], int)
        assert not db_rows, 'audit_file 条目不得再写 logs 表'
        record = json.loads(next(logs_root.joinpath(AUDIT_DIR).rglob('*.jsonl'))
                            .read_text(encoding='utf-8'))
        assert record['cursor'] == ids[0]
        assert record['event'] == 'AUTH_LOGIN'
        reset_audit_writer()

    def test_db_sink_keeps_repository_path(self, monkeypatch, tmp_path):
        servicer, task_pb, db_rows, logs_root = self._servicer(monkeypatch, tmp_path)
        payload = [{'time': '2026-10-24T09:00:00', 'level': 'INFO', 'category': 'auth',
                    'module': 'm', 'source': 's', 'content': 'x', 'sink': 'db'}]
        response = servicer.BatchCreateLogs(
            task_pb.BatchCreateLogsRequest(logs_json=json.dumps(payload)), None)
        assert response.success
        assert json.loads(response.data)['ids'] == [5000]
        assert len(db_rows) == 1
        assert not logs_root.joinpath(AUDIT_DIR).exists()

    def test_mixed_payload_preserves_request_order(self, monkeypatch, tmp_path):
        servicer, task_pb, db_rows, logs_root = self._servicer(monkeypatch, tmp_path)
        audit_item = dict(_entry())
        audit_item['sink'] = 'audit_file'
        db_item = {'time': '2026-10-24T09:00:00', 'category': 'auth',
                   'content': 'db row', 'sink': 'db'}
        response = servicer.BatchCreateLogs(
            task_pb.BatchCreateLogsRequest(
                logs_json=json.dumps([audit_item, db_item], default=str)), None)
        ids = json.loads(response.data)['ids']
        assert len(ids) == 2 and ids[0] is not None and ids[1] == 5000
        assert len(db_rows) == 1
        reset_audit_writer()


# ---------------------------------------------------------------------------
# S4 直写路径（task_service 进程内）
# ---------------------------------------------------------------------------

class TestS4DirectWriter:

    def test_write_audit_event_returns_cursor(self, monkeypatch, tmp_path):
        monkeypatch.setattr('shared.logging.config._SETTINGS',
                            _make_settings(tmp_path / 'logs'))
        monkeypatch.setenv('SERVICE_NAME', 'task_service')
        reset_audit_writer()
        cursor = write_audit_event(
            event=AuditEvent.PUBLISHED_TASK_CREATED,
            category=AuditLogCategory.SYSTEM.value,
            module='published_task',
            source='published_task_service',
            content=json.dumps({'event': 'PUBLISHED_TASK_CREATED',
                                'published_by': 42, 'published_task_id': 7,
                                'result': 'success'}),
        )
        assert isinstance(cursor, int) and cursor > 0
        record = json.loads(
            next((tmp_path / 'logs' / AUDIT_DIR).rglob('system.task_service.*.jsonl'))
            .read_text(encoding='utf-8'))
        assert record['category'] == 'system'
        assert record['service'] == 'task_service'
        assert record['operator_id'] == 42          # published_by 折叠为操作人
        assert record['target_id'] == 7             # published_task_id 折叠为 target_id
        reset_audit_writer()


# ---------------------------------------------------------------------------
# 保留清扫（审计子树 + 单清扫者 + 30 天统一）
# ---------------------------------------------------------------------------

def _touch(path, content='{}'):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content + '\n', encoding='utf-8')


class TestAuditRetention:

    def test_default_retention_is_unified_30_days(self):
        from shared.infrastructure.config import BaseConfig
        assert BaseConfig.LOG_FILE_RETENTION_DAYS == 30
        assert BaseConfig.LOG_AUDIT_RETENTION_DAYS == 30
        settings = _make_settings(tempfile.mkdtemp())
        assert settings.audit_retention_days == 30
        assert 'LOG_AUDIT_RETENTION_DAYS' in os.environ or settings.file_retention_days == 30

    def test_expired_audit_dates_archived_then_deleted(self, tmp_path, monkeypatch):
        logs_root = tmp_path / 'logs'
        old31 = (date.today() - timedelta(days=31)).isoformat()
        old200 = (date.today() - timedelta(days=200)).isoformat()
        recent = (date.today() - timedelta(days=1)).isoformat()
        _touch(logs_root / AUDIT_DIR / old31 / 'auth.api_gateway.h-1.jsonl')
        _touch(logs_root / AUDIT_DIR / old200 / 'auth.api_gateway.h-1.jsonl')
        _touch(logs_root / AUDIT_DIR / recent / 'auth.api_gateway.h-1.jsonl')

        uploaded = []

        def _fake_save_file(local_path, category, key):
            uploaded.append((category, key))
            return f'oss://{category}/{key}'

        from shared.infrastructure.storage import storage
        monkeypatch.setattr(storage, 'save_file', _fake_save_file)

        stats = sweep_audit_dates(_make_settings(logs_root))
        assert stats['archived'] == 2 and stats['deleted'] == 2 and stats['failed'] == 0
        assert ('archives', f'audit/{old31}/auth.api_gateway.h-1.jsonl') in uploaded
        assert ('archives', f'audit/{old200}/auth.api_gateway.h-1.jsonl') in uploaded
        assert not (logs_root / AUDIT_DIR / old31).exists(), '到期审计目录未删除'
        assert not (logs_root / AUDIT_DIR / old200).exists()
        assert (logs_root / AUDIT_DIR / recent).exists(), '未到期目录被误删'

    def test_archive_failure_keeps_local_file(self, tmp_path, monkeypatch):
        logs_root = tmp_path / 'logs'
        expired = (date.today() - timedelta(days=60)).isoformat()
        target = logs_root / AUDIT_DIR / expired / 'auth.api_gateway.h-1.jsonl'
        _touch(target)

        def _boom(local_path, category, key):
            raise RuntimeError('storage down')

        from shared.infrastructure.storage import storage
        monkeypatch.setattr(storage, 'save_file', _boom)

        stats = sweep_audit_dates(_make_settings(logs_root))
        assert stats == {'archived': 0, 'deleted': 0, 'failed': 1}
        assert target.exists(), '归档失败必须保留本地（绝不先删后传）'

    def test_cutoff_date_follows_retention(self):
        today = date(2026, 10, 24)
        assert audit_cutoff_date(30, today) == date(2026, 9, 24)
        assert audit_cutoff_date(30, today) == today - timedelta(days=30)

    def test_non_owner_service_skips_sweep(self, tmp_path, monkeypatch):
        logs_root = tmp_path / 'logs'
        expired = (date.today() - timedelta(days=90)).isoformat()
        target = logs_root / AUDIT_DIR / expired / 'auth.api_gateway.h-1.jsonl'
        _touch(target)
        monkeypatch.setattr('shared.logging.retention.resolve_service_name',
                            lambda: 'device_service')
        deleted = sweep_log_root(_make_settings(logs_root, sweep_service='api_gateway'))
        assert deleted == 0
        assert target.exists(), '非清扫者不得删除审计文件'

    def test_owner_service_sweeps_service_and_audit_trees(self, tmp_path, monkeypatch):
        logs_root = tmp_path / 'logs'
        monkeypatch.setattr('shared.logging.retention.resolve_service_name',
                            lambda: 'api_gateway')
        expired = (date.today() - timedelta(days=90)).isoformat()
        audit_file = logs_root / AUDIT_DIR / expired / 'auth.api_gateway.h-1.jsonl'
        _touch(audit_file)
        service_file = logs_root / 'task_service' / 'app-h-1.log'
        _touch(service_file)
        old = (datetime.now() - timedelta(days=90)).timestamp()
        os.utime(service_file, (old, old))

        from shared.infrastructure.storage import storage
        monkeypatch.setattr(storage, 'save_file', lambda *a, **k: 'oss://x')

        deleted = sweep_log_root(_make_settings(logs_root))
        assert deleted == 2
        assert not audit_file.exists() and not service_file.exists()
