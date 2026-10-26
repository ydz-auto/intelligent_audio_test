# -*- coding: utf-8 -*-
"""INT-1963 回归：日志归档「先上传、后删除」+ 分批。

改造前 ``log_repository.archive()`` 先 ``commit()`` 删除全部冷日志，再返回
全量分组给调用方上传：单条响应 237MB ≫ ``GRPC_MAX_MESSAGE_MB``(64) 必然失败，
结果是数据既不在库、也不在 OSS。本文件固化改造后的四件事：

1. 上传失败（``ArchiveStoreError``）→ 该批行**仍在库**、一行都没删、
   且不产生 ``local://`` 本地落盘产物（``ArchiveStore`` 不做本地降级）；
2. 上传成功 → 该批行删除，归档对象内容与删除行集合逐条对应；
3. 分批边界：0 行 / 1 行 / 恰好 N 行 / N+1 行都正确，``has_more`` 如实；
4. 同一批重复执行幂等（归档对象按 log id 去重、按 id 删除不报错）。

另加固：单批 gRPC 响应字节数远低于 ``GRPC_MAX_MESSAGE_MB``；``dry_run`` 只统计不删。
"""
import json
import os
from datetime import timedelta

import pytest
from botocore.exceptions import ClientError

# 共享配置在导入期校验必填环境变量（OSS 凭证），本文件不触真实 OSS
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.infrastructure.config import BaseConfig  # noqa: E402
from task_service.infrastructure.persistence.log_db_archive import (  # noqa: E402
    ArchiveFormatError,
    ArchiveStore,
    ArchiveStoreError,
    LogArchivePurger,
    merge_archive_entries,
    write_archive_entries,
)

_TASK_ID = 1963001001
_BATCH_ROWS_ENV = 'LOG_ARCHIVE_BATCH_ROWS'


class _FakeOSS:
    """内存 OSS 替身（与 OSSClient 的 download_bytes / upload_bytes / exists 同形）。"""

    def __init__(self):
        self.objects = {}
        self.fail_upload = False
        self.fail_download = False
        self.corrupt_existing = False
        self.uploads = []

    def exists(self, category, key):
        return (category, key) in self.objects

    def upload_bytes(self, data, category, key, content_type=None):
        if self.fail_upload:
            raise ConnectionError('OSS upload down (test stub)')
        self.objects[(category, key)] = data
        self.uploads.append((category, key, data))

    def download_bytes(self, category, key):
        if self.fail_download:
            raise ConnectionError('OSS download down (test stub)')
        if (category, key) not in self.objects:
            raise ClientError(
                {'Error': {'Code': 'NoSuchKey'}, 'ResponseMetadata': {'HTTPStatusCode': 404}},
                'GetObject')
        if self.corrupt_existing:
            return b'not-a-json-array'
        return self.objects[(category, key)]


@pytest.fixture()
def oss(monkeypatch):
    """把归档存储端口固定到内存 OSS（归档走 ArchiveStore → OSSClient 单例）。"""
    import shared.clients.oss_client as oss_mod
    fake = _FakeOSS()
    monkeypatch.setattr(oss_mod, 'oss', fake)
    return fake


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
        session.query(Log).filter(Log.source == 'int1963').delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _batch_cfg(monkeypatch):
    """默认单批 3 行、单轮不限批数（用例内可再覆盖）。"""
    monkeypatch.setattr(BaseConfig, _BATCH_ROWS_ENV, 3)
    monkeypatch.setattr(BaseConfig, 'LOG_ARCHIVE_BATCH_MAX_BYTES', 8 * 1024 * 1024)
    monkeypatch.setattr(BaseConfig, 'LOG_ARCHIVE_MAX_BATCHES_PER_RUN', 100)


def _insert_cold(count, content='cold', days=40, test_case_id=None, task_id=_TASK_ID):
    """插入 count 行冷日志（> days 天）。"""
    from shared.models.database import get_db_session, utc8now
    from task_service.infrastructure.persistence.models.system_models import Log
    cold = utc8now() - timedelta(days=days)
    session = get_db_session()
    try:
        for _ in range(count):
            session.add(Log(
                time=cold, level='INFO', category='Task', module='test',
                source='int1963', content=content,
                task_id=task_id, test_case_id=test_case_id,
            ))
        session.commit()
    finally:
        session.close()
    return count


def _db_rows():
    from shared.models.database import get_db_session
    from task_service.infrastructure.persistence.models.system_models import Log
    session = get_db_session()
    try:
        return (session.query(Log)
                .filter(Log.source == 'int1963')
                .order_by(Log.id.asc())
                .all())
    finally:
        session.close()


def _archive_entries(oss_fake):
    """读出所有归档对象里的日志条目。"""
    entries = []
    for (_category, key), raw in oss_fake.objects.items():
        if not key.endswith('.json'):
            continue
        entries.extend(json.loads(raw))
    return entries


def _local_archive_file():
    """本用例冷行会落到的本地降级路径（ArchiveStore 下必须不存在）。"""
    from shared.utils.query_utils import now_cst
    cold_date = (now_cst() - timedelta(days=40)).strftime('%Y-%m-%d')
    return os.path.join(BaseConfig.STORAGE_LOCAL_ROOT, 'archives',
                        'tasks', str(_TASK_ID), f'{cold_date}.json')


def _archive_batch(days=7, dry_run=False):
    from task_service.application.services.log_archive_service import LogArchiveService
    return LogArchiveService.archive_batch(days=days, dry_run=dry_run)


# ============================================================
# 1) 上传失败：行仍在库、一行不删、无本地落盘
# ============================================================

def test_upload_failure_keeps_rows_and_writes_nothing(oss):
    """上传失败 → 该批行仍在库、deleted_count=0、无 local:// 产物。"""
    from shared.proto import task_service_pb2 as task_pb
    from task_service.interfaces.grpc.task_data_service import TaskDataServiceServicer

    _insert_cold(3)
    oss.fail_upload = True

    resp = TaskDataServiceServicer().ArchiveLogs(
        task_pb.ArchiveLogsRequest(days=7, dry_run=False))

    assert resp.success is False, '上传失败必须让调用方看到失败，不得静默成功'
    assert 'OSS upload down' in resp.message, resp.message
    assert len(_db_rows()) == 3, '上传失败时该批行必须原样留在库内'
    assert not os.path.exists(_local_archive_file()), \
        'ArchiveStore 不允许降级本地，不得产生 local:// 落盘产物'

    # 恢复后重试同一批：行还在，归档+删除照常完成
    oss.fail_upload = False
    result = _archive_batch()
    assert result['archived_count'] == 3 and result['deleted_count'] == 3


def test_read_failure_does_not_overwrite_existing_archive(oss):
    """已有归档读不出来时整批中止（不覆盖、不删行），而不是当成「不存在」。"""
    from task_service.infrastructure.persistence.log_db_archive import ArchiveStoreError as _Err

    _insert_cold(2)
    _archive_batch()  # 先正常归档一批，制造已有对象

    _insert_cold(2)
    oss.fail_download = True
    with pytest.raises(_Err):
        _archive_batch()
    assert len(_db_rows()) == 2, '读不出已有归档时必须保留待归档行'


def test_corrupt_existing_archive_aborts_batch(oss):
    """已有归档内容不是 JSON 数组：整批中止，不覆盖也不删行。"""
    _insert_cold(2)
    _archive_batch()

    _insert_cold(1)
    oss.corrupt_existing = True
    with pytest.raises(ArchiveFormatError):
        _archive_batch()
    assert len(_db_rows()) == 1


# ============================================================
# 2) 上传成功：行删除 + 归档内容逐条对应
# ============================================================

def test_upload_success_deletes_and_archive_matches(oss):
    """上传成功 → 该批行删除，OSS 对象内容与删除行集合逐条对应。"""
    _insert_cold(3, content='a')
    _insert_cold(1, content='hot', days=1)  # 热日志，不得被归档
    cold_ids = [r.id for r in _db_rows() if r.content == 'a']

    result = _archive_batch()

    assert result['archived_count'] == 3
    assert result['deleted_count'] == 3
    assert result['has_more'] is False
    assert 'groups' not in result, '响应不得再携带全量分组内容（那正是 237MB 的来源）'

    left = _db_rows()
    assert [r.content for r in left] == ['hot'], '热日志必须保留'

    archived = _archive_entries(oss)
    assert sorted(item['id'] for item in archived) == sorted(cold_ids), \
        '归档对象内容必须与删除行集合逐条对应'
    assert all(item['content'] == 'a' for item in archived)


def test_response_bytes_far_below_grpc_limit(oss):
    """单批响应字节数远低于 GRPC_MAX_MESSAGE_MB（计数口径，与行数无关）。"""
    _insert_cold(3, content='x' * 2000)
    result = _archive_batch()

    limit = BaseConfig.GRPC_MAX_MESSAGE_MB * 1024 * 1024
    assert result['response_bytes'] < limit
    assert result['response_bytes'] < 4096, \
        f"单批响应应只有计数，实际 {result['response_bytes']} 字节"


def test_group_keys_canonical_prefixes(oss, monkeypatch):
    """归档对象 key 与读侧 tasks / cases / other 前缀口径一致（INT-554 口径保留）。"""
    from shared.models.database import utc8now

    monkeypatch.setattr(BaseConfig, _BATCH_ROWS_ENV, 10)
    cold = utc8now() - timedelta(days=40)
    log_date = cold.strftime('%Y-%m-%d')

    _insert_cold(1, test_case_id='case-1')                    # both → tasks/
    _insert_cold(1, test_case_id=None)                        # task only → tasks/
    _insert_cold(1, task_id=None, test_case_id='case-2')      # case only → cases/
    _insert_cold(1, task_id=None, test_case_id=None)          # neither → other/

    result = _archive_batch()

    keys = {key for (_category, key) in oss.objects if key.endswith('.json')}
    assert keys == {
        f'tasks/{_TASK_ID}/case-1/{log_date}.json',
        f'tasks/{_TASK_ID}/{log_date}.json',
        f'cases/case-2/{log_date}.json',
        f'other/{log_date}.json',
    }, f'归档 key 应为 tasks/cases/other 口径，实际: {sorted(keys)}'
    assert result['archive_write_count'] == 4, '四个分组各写一个归档对象'
    assert _db_rows() == [], '四类分组行都必须在上传成功后删除'


# ============================================================
# 3) 分批边界：0 / 1 / 恰好 N / N+1
# ============================================================

@pytest.mark.parametrize('rows,expect_first,expect_more', [
    (0, 0, False),
    (1, 1, False),
    (3, 3, False),   # 恰好 N（批大小 3）
    (4, 3, True),    # N+1
])
def test_batch_boundaries(oss, rows, expect_first, expect_more):
    _insert_cold(rows)
    result = _archive_batch()

    assert result['archived_count'] == expect_first
    assert result['deleted_count'] == expect_first
    assert result['has_more'] is expect_more
    assert len(_db_rows()) == rows - expect_first

    if expect_more:
        second = _archive_batch()
        assert second['archived_count'] == rows - expect_first
        assert second['has_more'] is False
        assert _db_rows() == []


def test_batch_byte_cap_never_stalls(oss, monkeypatch):
    """字节上限比单行还小时仍至少取 1 行（保证每批都有进展，不死循环）。"""
    monkeypatch.setattr(BaseConfig, _BATCH_ROWS_ENV, 10)
    monkeypatch.setattr(BaseConfig, 'LOG_ARCHIVE_BATCH_MAX_BYTES', 1)
    _insert_cold(2, content='y' * 100)

    result = _archive_batch()
    assert result['archived_count'] == 1
    assert result['has_more'] is True


# ============================================================
# 4) 幂等：同一批重复执行
# ============================================================

def test_repeat_batch_is_idempotent(oss):
    """同一批重复执行：第二次无可删行、不报错、归档对象不重复。"""
    _insert_cold(3)
    first = _archive_batch()
    assert first['deleted_count'] == 3

    second = _archive_batch()
    assert second['archived_count'] == 0
    assert second['deleted_count'] == 0
    assert second['has_more'] is False

    archived = _archive_entries(oss)
    assert len(archived) == 3, '重复归档不得在归档对象里产生重复条目'


def test_reupload_same_rows_dedupes(oss):
    """「归档写成功但删除前中断」的重试：同样 id 再写一遍仍只有一份。"""
    store = ArchiveStore(client=oss)
    entries = [{'id': 7, 'time': '2026-10-17T10:00:00', 'level': 'INFO',
                'module': 'test', 'content': 'dup', 'task_id': None, 'test_case_id': None}]

    first = merge_archive_entries([], entries)
    write_archive_entries(store, 'other/2026-10-17', first)
    second = merge_archive_entries(first, entries)
    write_archive_entries(store, 'other/2026-10-17', second)

    archived = _archive_entries(oss)
    assert len(archived) == 1, '按 log id 去重后重试不会写重复行'


def test_delete_batch_idempotent():
    """按 id 删除对已删除行幂等（返回 0，不抛异常）。"""
    from shared.models.database import get_db_session
    from task_service.infrastructure.persistence.models.system_models import Log

    _insert_cold(1)
    session = get_db_session()
    try:
        log_id = session.query(Log.id).filter(Log.source == 'int1963').scalar()
    finally:
        session.close()

    purger = LogArchivePurger()
    assert purger._delete_batch([log_id]) == 1
    assert purger._delete_batch([log_id]) == 0


# ============================================================
# 5) dry_run 只统计
# ============================================================

def test_dry_run_counts_without_delete(oss):
    _insert_cold(3)
    result = _archive_batch(dry_run=True)

    assert result['cold_logs_count'] == 3
    assert 'cutoff_date' in result
    assert len(_db_rows()) == 3, 'dry_run 不得删除任何行'
    assert oss.uploads == [], 'dry_run 不得触达存储'


def test_archive_semantics_keep_audit_and_marked_rows_in_scope(oss):
    """ArchiveLogs 口径保持历史语义：审计类与已 mark 行同样参与归档。"""
    from shared.models.database import get_db_session, utc8now
    from task_service.infrastructure.persistence.models.system_models import Log

    cold = utc8now() - timedelta(days=40)
    session = get_db_session()
    try:
        session.add(Log(time=cold, level='INFO', category='auth', module='test',
                        source='int1963', content='audit', task_id=_TASK_ID,
                        test_case_id=None, mark=None))
        session.add(Log(time=cold, level='INFO', category='Task', module='test',
                        source='int1963', content='marked', task_id=_TASK_ID,
                        test_case_id=None, mark='flagged'))
        session.commit()
    finally:
        session.close()

    result = _archive_batch()
    assert result['archived_count'] == 2
    assert _db_rows() == []


# ============================================================
# 6) 调用方分批推进（log_worker 巡检 / 网关手动归档）
# ============================================================

def test_mixin_loops_until_has_more_false(monkeypatch, capsys):
    """log_worker 按 has_more 推进下一批，每批打印响应字节数。"""
    import shared.clients.grpc_clients as grpc_clients_mod
    from shared.utils.log_handler._archive_mixin import _ArchiveMixin

    calls = []

    def _fake_archive_logs(days=30, dry_run=True):
        calls.append((days, dry_run))
        idx = len(calls)
        return {
            'archived_count': 3, 'deleted_count': 3, 'remaining_count': 100 - idx,
            'has_more': idx < 2, 'response_bytes': 210,
        }

    monkeypatch.setattr(grpc_clients_mod, 'archive_logs', _fake_archive_logs)
    monkeypatch.setattr(BaseConfig, 'LOG_ARCHIVE_MAX_BATCHES_PER_RUN', 10)

    class _Host(_ArchiveMixin):
        def _clean_expired_archives(self):
            pass

    _Host()._archive_old_logs()

    out = capsys.readouterr().out
    assert len(calls) == 2, 'has_more=True 时必须推进下一批'
    assert all(dry is False for _days, dry in calls)
    assert 'response_bytes=210' in out
    assert 'Archived 6 logs' in out


def test_mixin_respects_max_batches(monkeypatch, capsys):
    """单轮批数达上限即停，剩余留给下一轮。"""
    import shared.clients.grpc_clients as grpc_clients_mod
    from shared.utils.log_handler._archive_mixin import _ArchiveMixin

    calls = []

    def _fake_archive_logs(days=30, dry_run=True):
        calls.append(1)
        return {'archived_count': 3, 'deleted_count': 3, 'remaining_count': 900,
                'has_more': True, 'response_bytes': 210}

    monkeypatch.setattr(grpc_clients_mod, 'archive_logs', _fake_archive_logs)
    monkeypatch.setattr(BaseConfig, 'LOG_ARCHIVE_MAX_BATCHES_PER_RUN', 2)

    class _Host(_ArchiveMixin):
        def _clean_expired_archives(self):
            pass

    _Host()._archive_old_logs()

    assert len(calls) == 2, '达到单轮批数上限必须停下'
    assert 'will continue archiving next cycle' in capsys.readouterr().out


def test_mixin_stops_on_error(monkeypatch, capsys):
    """任一批失败即停：不再打下一批，异常交给外层 ARCHIVE ERROR。"""
    import shared.clients.grpc_clients as grpc_clients_mod
    from shared.utils.log_handler._archive_mixin import _ArchiveMixin

    calls = []

    def _fake_archive_logs(days=30, dry_run=True):
        calls.append(1)
        raise RuntimeError('task_service unavailable')

    monkeypatch.setattr(grpc_clients_mod, 'archive_logs', _fake_archive_logs)
    monkeypatch.setattr(grpc_clients_mod, 'get_log_count', lambda: {'total': 300001})

    class _Host(_ArchiveMixin):
        def _clean_expired_archives(self):
            pass

    host = _Host()
    host._check_and_archive()

    out = capsys.readouterr().out
    assert len(calls) == 1
    assert 'ARCHIVE ERROR' in out


def test_gateway_aggregates_batches(monkeypatch):
    """网关手动归档接口把多批计数聚合成一个响应，绝不自己上传分组。"""
    from api_gateway.application.services.log.log_command_service import LogCommandService
    from api_gateway.infrastructure.grpc_proxies import task_data_service

    state = {'n': 0}

    def _fake_archive_logs(days=30, dry_run=False):
        state['n'] += 1
        return {
            'archived_count': 3, 'deleted_count': 3, 'remaining_count': 50,
            'has_more': state['n'] < 2,
            'response_bytes': 220,
        }

    monkeypatch.setattr(task_data_service, 'archive_logs', _fake_archive_logs)
    monkeypatch.setattr(BaseConfig, 'LOG_ARCHIVE_MAX_BATCHES_PER_RUN', 10)

    payload, http_code = LogCommandService.archive_logs()

    assert http_code == 200
    assert payload['data']['archived_count'] == 6
    assert payload['data']['deleted_count'] == 6
    assert '成功归档 6 条日志' in payload['message'], payload['message']
    assert '2 批' in payload['message'], payload['message']
    assert state['n'] == 2
