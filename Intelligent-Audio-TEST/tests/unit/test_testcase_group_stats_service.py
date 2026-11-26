# -*- coding: utf-8 -*-
"""分组时长统计读模型服务单测：Redis 缓存 / DB 读模型 / 失效 / 降级。"""
import time
from datetime import datetime, timedelta, timezone

from task_service.application.testcase import testcase_group_stats_service as svc


class FakeRepo:
    """最小仓储替身：读模型行 + 回源聚合 + 回写记录。"""

    def __init__(self, db_rows=None, computed=None):
        self.db_rows = db_rows or {}
        self.computed = computed or {}
        self.upserted = {}
        self.deleted = None
        self.read_calls = 0
        self.compute_calls = 0

    def read_group_stats(self, group_ids):
        self.read_calls += 1
        return {g: self.db_rows[g] for g in group_ids if g in self.db_rows}

    def compute_group_durations(self, group_ids):
        self.compute_calls += 1
        return {g: self.computed.get(g, 0.0) for g in group_ids}

    def upsert_group_stats(self, stats):
        self.upserted.update(stats)

    def delete_group_stats(self, group_ids=None):
        self.deleted = group_ids


class FakeStore:
    """最小 Redis 替身：记录写入/删除，可模拟不可用。"""

    def __init__(self, data=None, fail=False):
        self.data = dict(data or {})
        self.fail = fail
        self.saved = {}
        self.deleted_key = False
        self.removed = []

    def load_task(self, key):
        if self.fail:
            raise RuntimeError('redis down')
        return dict(self.data)

    def save_task(self, key, value, ttl_seconds=None):
        if self.fail:
            raise RuntimeError('redis down')
        self.data.update(value)
        self.saved.update(value)

    def delete_task(self, key):
        self.data.clear()
        self.deleted_key = True

    def remove_fields(self, key, *fields):
        for field in fields:
            self.data.pop(field, None)
        self.removed.extend(fields)


def _fresh_ts():
    return time.time()


def _db_row(duration, age_seconds=0):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return {'total_duration': duration,
            'stats_updated_at': now - timedelta(seconds=age_seconds)}


def test_cache_hit_skips_db_and_compute(monkeypatch):
    repo = FakeRepo()
    store = FakeStore({'g1': {'total_duration': 12.5, 'ts': _fresh_ts()}})
    monkeypatch.setattr(svc, '_repo', lambda: repo)
    monkeypatch.setattr(svc, '_store', lambda: store)

    assert svc.get_group_durations(['g1']) == {'g1': 12.5}
    assert repo.read_calls == 0 and repo.compute_calls == 0


def test_fresh_db_row_used_and_backfilled(monkeypatch):
    repo = FakeRepo(db_rows={'g1': _db_row(8.0)})
    store = FakeStore()
    monkeypatch.setattr(svc, '_repo', lambda: repo)
    monkeypatch.setattr(svc, '_store', lambda: store)

    assert svc.get_group_durations(['g1']) == {'g1': 8.0}
    assert repo.compute_calls == 0
    assert store.saved['g1']['total_duration'] == 8.0  # 回填读缓存


def test_stale_or_missing_row_recomputes_and_persists(monkeypatch):
    repo = FakeRepo(
        db_rows={'g1': _db_row(1.0, age_seconds=svc._STATS_TTL_SECONDS + 5)},
        computed={'g1': 20.0, 'g2': 3.0},
    )
    store = FakeStore()
    monkeypatch.setattr(svc, '_repo', lambda: repo)
    monkeypatch.setattr(svc, '_store', lambda: store)

    assert svc.get_group_durations(['g1', 'g2']) == {'g1': 20.0, 'g2': 3.0}
    assert repo.upserted == {'g1': 20.0, 'g2': 3.0}  # DB 物化
    assert store.saved['g2']['total_duration'] == 3.0  # Redis 缓存


def test_redis_unavailable_degrades_to_live_compute(monkeypatch):
    repo = FakeRepo(computed={'g1': 5.5})
    store = FakeStore(fail=True)
    monkeypatch.setattr(svc, '_repo', lambda: repo)
    monkeypatch.setattr(svc, '_store', lambda: store)

    assert svc.get_group_durations(['g1']) == {'g1': 5.5}
    assert repo.compute_calls == 1


def test_invalidate_deletes_cache_and_read_model(monkeypatch):
    repo = FakeRepo()
    store = FakeStore({'g1': {'total_duration': 1.0, 'ts': _fresh_ts()}})
    monkeypatch.setattr(svc, '_repo', lambda: repo)
    monkeypatch.setattr(svc, '_store', lambda: store)

    svc.invalidate_group_stats(['g1'])
    assert store.removed == ['g1']
    assert repo.deleted == ['g1']

    svc.invalidate_group_stats()
    assert store.deleted_key is True
    assert repo.deleted is None  # None = 全部分组
