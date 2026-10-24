# -*- coding: utf-8 -*-
"""INT-1785 logs 收口：历史日志流式归档清理 + 审计日志保留天数。

覆盖（卡面验收 1~4 的可自动化部分）：
1. 分组规则（task+case / 仅 task / 仅 case / other）与 `archive()` 一致；
2. 同名归档文件合并：按 id 去重、按 time 升序（重跑不重复、不覆盖）；
3. 分批边界：5 行 / batch 2 → 3 批，归档条数 = 删除条数；
4. 失败安全：第 2 批归档写失败 → 该批不删、前序批次已提交、脚本以 2 退出；
5. 幂等：连跑第二次 0 归档 0 删除，归档文件字节级不变；
6. 保留策略：LOG_DB_RETENTION_DAYS=1 时 3 天前的行归档后消失、今天的行保留，
   连续两次执行结果稳定；
7. 审计类（auth/device/benchmark）不参与清理，dry-run 不写不删。

DB 用 pytest 进程级 sqlite（conftest 兜底），存储用内存 FakeStorage 注入。
"""
import importlib.util
import json
import os

import pytest

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from datetime import timedelta  # noqa: E402

from shared.utils.query_utils import now_cst  # noqa: E402
from task_service.infrastructure.persistence.log_db_archive import (  # noqa: E402
    AUDIT_LOG_CATEGORIES,
    ArchiveFormatError,
    LogArchivePurger,
    build_group_key,
    merge_archive_entries,
)
from task_service.infrastructure.persistence.log_retention_cleaner import (  # noqa: E402
    LogRetentionCleaner,
)

_TASK_ID = 9101785
# 本文件的造数标记：sqlite 库为 pytest 进程共享，按 source 精确圈定自己的行
_SOURCE = 'int1785_test'
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class FakeStorage:
    """内存存储：键与统一存储层一致（'{category}/{key}'）。"""

    def __init__(self):
        self.files = {}

    def exists(self, path):
        return path in self.files

    def load_bytes(self, path):
        return self.files[path]

    def save_bytes(self, data, category, key, content_type=None):
        self.files[f'{category}/{key}'] = data
        return f'oss://{category}/{key}'

    def archive(self, group_key):
        """读归档条目（group_key 不含 category 前缀与 .json）。"""
        return json.loads(self.files[f'archives/{group_key}.json'])


class FailingStorage(FakeStorage):
    """第 N 次 save_bytes 抛错，用于模拟归档写入失败。"""

    def __init__(self, fail_on=1):
        super().__init__()
        self.fail_on = fail_on
        self.calls = 0

    def save_bytes(self, data, category, key, content_type=None):
        self.calls += 1
        if self.calls == self.fail_on:
            raise OSError('模拟 OSS 写失败')
        return super().save_bytes(data, category, key, content_type)


@pytest.fixture(scope='module', autouse=True)
def _db():
    from shared.models.database import Base, get_engine, init_db
    init_db()
    from task_service.infrastructure.persistence.models.system_models import Log
    Base.metadata.create_all(get_engine(), tables=[Log.__table__])
    yield


@pytest.fixture(autouse=True)
def _clean():
    from shared.models.database import get_db_session
    from task_service.infrastructure.persistence.models.system_models import Log
    session = get_db_session()
    try:
        session.query(Log).filter(Log.source == _SOURCE).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()


def _now():
    return now_cst().replace(tzinfo=None)


def _seed(rows):
    """rows: [(time, category, task_id, test_case_id, content)]"""
    from shared.models.database import get_db_session
    from task_service.infrastructure.persistence.models.system_models import Log
    session = get_db_session()
    try:
        session.add_all([
            Log(time=ts, level='INFO', category=cat, module='Test', source=_SOURCE,
                content=content, task_id=task_id, test_case_id=case_id)
            for ts, cat, task_id, case_id, content in rows
        ])
        session.commit()
    finally:
        session.close()


def _count():
    from sqlalchemy import func
    from shared.models.database import get_db_session
    from task_service.infrastructure.persistence.models.system_models import Log
    session = get_db_session()
    try:
        return (session.query(func.count(Log.id))
                .filter(Log.source == _SOURCE).scalar() or 0)
    finally:
        session.close()


# ---------------------------------------------------------------- 纯函数

def test_group_key_rules():
    assert build_group_key(7, 'c1', '2026-10-17') == 'tasks/7/c1/2026-10-17'
    assert build_group_key(7, None, '2026-10-17') == 'tasks/7/2026-10-17'
    assert build_group_key(None, 'c1', '2026-10-17') == 'cases/c1/2026-10-17'
    assert build_group_key(None, None, '2026-10-17') == 'other/2026-10-17'


def test_merge_dedupes_by_id_and_sorts_by_time():
    existing = [
        {'id': 2, 'time': '2026-10-17T10:00:00', 'content': 'b'},
        {'id': 1, 'time': '2026-10-17T09:00:00', 'content': 'a'},
    ]
    incoming = [
        {'id': 2, 'time': '2026-10-17T10:00:00', 'content': 'b-again'},
        {'id': 3, 'time': '2026-10-17T08:00:00', 'content': 'c'},
    ]
    merged = merge_archive_entries(existing, incoming)
    assert [e['id'] for e in merged] == [3, 1, 2]
    # 已有条目优先（不被同 id 的新条目覆盖）
    assert merged[-1]['content'] == 'b'


def test_merge_keeps_entries_without_id():
    merged = merge_archive_entries(
        [{'id': 1, 'time': '2026-10-17T09:00:00'}],
        [{'time': '2026-10-17T09:00:00'}],
    )
    assert len(merged) == 2


# ---------------------------------------------------------------- 分批归档 + 删除

def test_purge_archives_and_deletes_all_batches(tmp_path):
    cutoff = _now() - timedelta(days=3)
    day = (cutoff - timedelta(days=1)).replace(microsecond=0)
    _seed([
        (day, 'execution', _TASK_ID, 'c1', 'case log 1'),
        (day + timedelta(minutes=1), 'execution', _TASK_ID, 'c1', 'case log 2'),
        (day + timedelta(minutes=2), 'system', _TASK_ID, None, 'task log'),
        (day + timedelta(minutes=3), 'engine', None, 'c2', 'case only'),
        (day + timedelta(minutes=4), 'database', None, None, 'other'),
    ])
    storage = FakeStorage()
    purger = LogArchivePurger(storage=storage, batch_size=2)
    result = purger.run(cutoff)

    assert not result.failed
    assert result.archived_count == result.deleted_count == 5
    assert result.batch_count == 3  # 2 + 2 + 1
    assert result.archived_file_count == 4  # 去重的归档文件数
    assert result.archive_write_count == 4  # 每个文件本批只写一次
    assert _count() == 0

    date = day.strftime('%Y-%m-%d')
    assert len(storage.archive(f'tasks/{_TASK_ID}/c1/{date}')) == 2
    assert len(storage.archive(f'tasks/{_TASK_ID}/{date}')) == 1
    assert len(storage.archive(f'cases/c2/{date}')) == 1
    assert len(storage.archive(f'other/{date}')) == 1

    # 归档条目字段与 _log_po_to_dict 同口径，且按 time 升序
    entries = storage.archive(f'tasks/{_TASK_ID}/c1/{date}')
    assert [e['content'] for e in entries] == ['case log 1', 'case log 2']
    assert set(entries[0]) >= {
        'id', 'time', 'level', 'category', 'module', 'source', 'content',
        'mark', 'device_id', 'task_id', 'test_case_id', 'api_id', 'thread_id',
        'algorithm_type', 'created_by_user_id', 'created_at',
    }


def test_purge_merges_with_existing_archive_file():
    cutoff = _now() - timedelta(days=1)
    day = (cutoff - timedelta(days=1)).replace(microsecond=0)
    _seed([(day, 'execution', _TASK_ID, 'c9', 'new row')])

    storage = FakeStorage()
    date = day.strftime('%Y-%m-%d')
    existing = [{'id': 999999999, 'time': '2026-01-01T00:00:00', 'content': 'old row'}]
    storage.files[f'archives/tasks/{_TASK_ID}/c9/{date}.json'] = json.dumps(
        existing, ensure_ascii=False, indent=2).encode('utf-8')

    result = LogArchivePurger(storage=storage, batch_size=10).run(cutoff)
    assert result.deleted_count == 1
    entries = storage.archive(f'tasks/{_TASK_ID}/c9/{date}')
    assert [e['content'] for e in entries] == ['old row', 'new row']


def test_audit_categories_are_kept():
    cutoff = _now() - timedelta(days=1)
    day = (cutoff - timedelta(days=2)).replace(microsecond=0)
    _seed([
        (day, cat, _TASK_ID, None, f'{cat} audit')
        for cat in sorted(AUDIT_LOG_CATEGORIES)
    ] + [
        (day, 'Auth', _TASK_ID, None, 'capitalized audit stays too'),
        (day, 'execution', _TASK_ID, None, 'business log goes'),
    ])

    result = LogArchivePurger(storage=FakeStorage(), batch_size=10).run(cutoff)
    assert result.deleted_count == 1
    assert _count() == len(AUDIT_LOG_CATEGORIES) + 1  # 审计类原样保留


def test_dry_run_writes_nothing(tmp_path):
    cutoff = _now() - timedelta(days=1)
    day = (cutoff - timedelta(days=1)).replace(microsecond=0)
    _seed([(day, 'execution', _TASK_ID, 'c3', 'cold')])
    storage = FakeStorage()
    result = LogArchivePurger(storage=storage, batch_size=2, dry_run=True).run(cutoff)
    assert result.archived_count == 1
    assert result.deleted_count == 0
    assert storage.files == {}
    assert _count() == 1


def test_archive_failure_keeps_that_batch():
    cutoff = _now() - timedelta(days=1)
    day = (cutoff - timedelta(days=1)).replace(microsecond=0)
    _seed([
        (day + timedelta(minutes=i), 'execution', _TASK_ID,
         'c0' if i < 2 else 'c1', f'row {i}')
        for i in range(4)
    ])
    # 每批 2 行、各落 1 个归档文件；第 2 次写失败 → 第 1 批已删，第 2 批保留
    storage = FailingStorage(fail_on=2)
    result = LogArchivePurger(storage=storage, batch_size=2).run(cutoff)

    assert result.failed is True
    assert result.batch_count == 1
    assert result.completed_batches == [{'batch': 1, 'archived': 2, 'deleted': 2}]
    assert result.deleted_count == 2
    assert _count() == 2  # 第 2 批一行没删


def test_corrupt_existing_archive_aborts_batch():
    cutoff = _now() - timedelta(days=1)
    day = (cutoff - timedelta(days=1)).replace(microsecond=0)
    _seed([(day, 'execution', _TASK_ID, 'c4', 'row')])
    storage = FakeStorage()
    date = day.strftime('%Y-%m-%d')
    storage.files[f'archives/tasks/{_TASK_ID}/c4/{date}.json'] = b'{not json'

    result = LogArchivePurger(storage=storage, batch_size=5).run(cutoff)
    assert result.failed is True
    assert 'ArchiveFormatError' not in result.failure_reason  # 只带消息
    assert result.deleted_count == 0
    assert _count() == 1
    # 旧文件未被覆盖
    assert storage.files[f'archives/tasks/{_TASK_ID}/c4/{date}.json'] == b'{not json'


def test_second_run_is_idempotent_and_bytes_stable():
    cutoff = _now() - timedelta(days=1)
    day = (cutoff - timedelta(days=1)).replace(microsecond=0)
    _seed([
        (day, 'execution', _TASK_ID, 'c5', 'a'),
        (day + timedelta(minutes=1), 'execution', _TASK_ID, 'c5', 'b'),
    ])
    storage = FakeStorage()
    first = LogArchivePurger(storage=storage, batch_size=10).run(cutoff)
    assert first.deleted_count == 2
    snapshot = dict(storage.files)

    second = LogArchivePurger(storage=storage, batch_size=10).run(cutoff)
    assert (second.archived_count, second.deleted_count, second.batch_count) == (0, 0, 0)
    assert storage.files == snapshot


# ---------------------------------------------------------------- 每日保留清扫

def _cleaner(storage, days=1):
    cleaner = LogRetentionCleaner(retention_days=days, storage=storage, batch_size=10)
    # Redis 锁在无 Redis 的测试环境会降级；显式绕过避免依赖基础设施
    cleaner._acquire_lock = lambda: None
    cleaner._release_lock = lambda token: None
    return cleaner


def test_retention_cleaner_archives_old_keeps_new():
    old = (_now() - timedelta(days=3)).replace(microsecond=0)
    fresh = _now().replace(microsecond=0)
    _seed([
        (old, 'execution', _TASK_ID, 'c6', 'old row'),
        (fresh, 'execution', _TASK_ID, 'c6', 'fresh row'),
        (old, 'auth', _TASK_ID, None, 'audit row'),
    ])
    storage = FakeStorage()
    cleaner = _cleaner(storage, days=1)

    first = cleaner.run_once()
    assert first['status'] == 'ok'
    assert (first['archived'], first['deleted']) == (1, 1)
    assert _count() == 2  # 新行 + 审计行

    entries = storage.archive(f'tasks/{_TASK_ID}/c6/{old.strftime("%Y-%m-%d")}')
    assert [e['content'] for e in entries] == ['old row']

    snapshot = dict(storage.files)
    second = cleaner.run_once()
    assert second['status'] == 'ok'
    assert (second['archived'], second['deleted']) == (0, 0)
    assert storage.files == snapshot
    assert _count() == 2


def test_retention_cleaner_disabled_when_zero():
    cleaner = _cleaner(FakeStorage(), days=0)
    assert cleaner.run_once()['status'] == 'disabled'


def test_retention_cleaner_uses_log_settings(monkeypatch):
    """未显式传参时读 LogSettings.db_retention_days（LOG_DB_RETENTION_DAYS）。"""
    from shared.infrastructure.config import BaseConfig
    from shared.logging.config import reset_log_settings

    monkeypatch.setattr(BaseConfig, 'LOG_DB_RETENTION_DAYS', 1, raising=False)
    reset_log_settings()
    try:
        assert LogRetentionCleaner().retention_days() == 1
        # 负责人 2026-10-24 定：保留期 30 天（INT-1793 落地前的过渡期口径）
        monkeypatch.setattr(BaseConfig, 'LOG_DB_RETENTION_DAYS', 30, raising=False)
        reset_log_settings()
        assert LogRetentionCleaner().retention_days() == 30
    finally:
        reset_log_settings()


def test_default_retention_30_days_archives_31_day_old_row(monkeypatch):
    """保留期 30 天口径：31 天前的行归档后删除，今天的行保留。"""
    from shared.infrastructure.config import BaseConfig
    from shared.logging.config import reset_log_settings

    monkeypatch.setattr(BaseConfig, 'LOG_DB_RETENTION_DAYS', 30, raising=False)
    reset_log_settings()
    try:
        old = (_now() - timedelta(days=31)).replace(microsecond=0)
        fresh = _now().replace(microsecond=0)
        _seed([
            (old, 'execution', _TASK_ID, 'c11', '31 天前'),
            (fresh, 'execution', _TASK_ID, 'c11', '今天的行'),
        ])
        storage = FakeStorage()
        cleaner = LogRetentionCleaner(storage=storage, batch_size=10)
        cleaner._acquire_lock = lambda: None
        cleaner._release_lock = lambda token: None

        summary = cleaner.run_once()
        assert summary['retention_days'] == 30
        assert (summary['archived'], summary['deleted']) == (1, 1)
        assert _count() == 1

        entries = storage.archive(f'tasks/{_TASK_ID}/c11/{old.strftime("%Y-%m-%d")}')
        assert [e['content'] for e in entries] == ['31 天前']
    finally:
        reset_log_settings()


def test_cleaner_failure_returns_failed_status():
    """归档写失败时 run_once 不抛异常（守护线程继续跑），状态为 failed。"""
    old = (_now() - timedelta(days=3)).replace(microsecond=0)
    _seed([(old, 'execution', _TASK_ID, 'c7', 'old row')])
    cleaner = _cleaner(FailingStorage(fail_on=1), days=1)
    summary = cleaner.run_once()
    assert summary['status'] == 'failed'
    assert _count() == 1  # 数据保留


# ---------------------------------------------------------------- 脚本出口

def _load_script():
    path = os.path.join(_PROJECT_ROOT, 'scripts', 'maintenance',
                        'purge_legacy_logs_int1785.py')
    spec = importlib.util.spec_from_file_location('purge_legacy_logs_int1785', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_script_exits_nonzero_and_prints_completed_batches(monkeypatch, capsys):
    cutoff = _now() - timedelta(days=1)
    day = (cutoff - timedelta(days=1)).replace(microsecond=0)
    _seed([
        (day + timedelta(minutes=i), 'execution', _TASK_ID,
         'c80' if i < 2 else 'c81', f'row {i}')
        for i in range(4)
    ])
    storage = FailingStorage(fail_on=2)
    monkeypatch.setattr('shared.infrastructure.storage.storage', storage)

    script = _load_script()
    code = script.main(['--cutoff', cutoff.isoformat(), '--batch-size', '2'])
    out = capsys.readouterr().out

    assert code == script.EXIT_ARCHIVE_FAILED == 2
    assert '已完成批次: 批 1' in out
    assert _count() == 2


def test_script_dry_run_reports_without_deleting(monkeypatch, capsys):
    cutoff = _now() - timedelta(days=1)
    day = (cutoff - timedelta(days=1)).replace(microsecond=0)
    _seed([(day, 'execution', _TASK_ID, 'c10', 'row')])
    storage = FakeStorage()
    monkeypatch.setattr('shared.infrastructure.storage.storage', storage)

    script = _load_script()
    code = script.main(['--cutoff', cutoff.isoformat(), '--dry-run'])
    out = capsys.readouterr().out

    assert code == script.EXIT_OK == 0
    assert '[DRY-RUN] 将归档/删除 1 条' in out
    assert storage.files == {}
    assert _count() == 1


def test_archive_format_error_type_is_public():
    """ArchiveFormatError 是模块公开契约（脚本/清扫据此中止该批）。"""
    assert issubclass(ArchiveFormatError, RuntimeError)
