# -*- coding: utf-8 -*-
"""INT-2000 C1：列表每请求跨服务 ListTags → 进程内 tag_id→name TTL 快照缓存。

覆盖卡面「可测验收标准 / 1. 单测」五条 + 两条降级硬约束：
- TTL 内两次解析 → 上游只被调 1 次；
- TTL 过期 → 刷新一次；
- 上游抛异常 → 返回上一份快照、不写缓存、失败计数 +1，连续失败不清空快照；
- 上游成功但缺 id → 走「查不到」，正向映射不受影响；
- 20 线程同时首轮解析 → 上游调用 = 1 次（单飞）；
- 负缓存只记「查不到」，绝不给「查不了」记账（否则一次故障 = 一个 TTL 的假空表）。
"""
import json
import os
import tempfile
import threading

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('STORAGE_LOCAL_ROOT', tempfile.mkdtemp(prefix='int2000_'))
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('OSS_ENDPOINT', 'http://127.0.0.1:9')

import pytest
from unittest import mock

from shared.infrastructure.config import BaseConfig
from audio_service.infrastructure.acl import tag_acl_repository as acl
from audio_service.infrastructure.acl.tag_acl_repository import (
    TagAclRepository,
    get_tag_acl_cache_stats,
    reset_tag_acl_cache,
)


class _FakeStub:
    """最小 ListTags stub：可配页数据、异常、时延，并计数上游调用。"""

    def __init__(self, items=None, pages=None, exc=None, delay=0.0):
        self._items = list(items or [])
        self._pages = list(pages) if pages is not None else None
        self._exc = exc
        self._delay = delay
        self.list_calls = 0
        self._lock = threading.Lock()

    def ListTags(self, req, timeout=None):
        with self._lock:
            self.list_calls += 1
            exc = self._exc
        if self._delay:
            import time as _t
            _t.sleep(self._delay)
        if exc:
            raise exc
        with self._lock:
            if self._pages is None:
                items = list(self._items)   # 单页：每次刷新都返回同一份标签表
            else:
                items = self._pages.pop(0) if self._pages else []
        return mock.Mock(success=True, message='',
                         data=json.dumps({'items': items, 'pages': 1}))


@pytest.fixture(autouse=True)
def _clean_cache():
    """模块级单例快照跨用例共享：每个用例前后都清空，避免相互污染。"""
    reset_tag_acl_cache()
    yield
    reset_tag_acl_cache()


@pytest.fixture(autouse=True)
def _default_config(monkeypatch):
    monkeypatch.setattr(BaseConfig, 'AUDIO_TAG_ACL_CACHE_TTL_SECONDS', 60)
    monkeypatch.setattr(BaseConfig, 'AUDIO_TAG_ACL_NEGATIVE_CACHE_SECONDS', 0)


def _patch_stub(stub):
    return mock.patch('shared.clients.grpc_clients.get_tag_config_service_stub',
                      return_value=stub)


def _resolve(stub, tag_ids):
    with _patch_stub(stub):
        return TagAclRepository().get_tag_id_to_name_map(tag_ids)


# ---------------- 命中 / TTL ----------------

def test_ttl_hit_calls_upstream_once():
    stub = _FakeStub(items=[{'id': 74, 'name': '打断与恢复'},
                            {'id': 75, 'name': '拒识'}])

    first = _resolve(stub, [74, 75])
    second = _resolve(stub, [74])

    assert first == {74: '打断与恢复', 75: '拒识'}
    assert second == {74: '打断与恢复'}
    assert stub.list_calls == 1
    stats = get_tag_acl_cache_stats()
    assert stats['refresh_ok'] == 1
    assert stats['hit'] == 3


def test_ttl_expiry_triggers_exactly_one_refresh():
    stub = _FakeStub(items=[{'id': 74, 'name': '打断与恢复'}])
    _resolve(stub, [74])
    assert stub.list_calls == 1

    # 把快照时间戳推到 TTL 之外，模拟过期
    with acl._COND:
        acl._SNAPSHOT_AT = acl._SNAPSHOT_AT - (acl.tag_cache_ttl_seconds() + 1)

    assert _resolve(stub, [74]) == {74: '打断与恢复'}
    assert stub.list_calls == 2
    assert get_tag_acl_cache_stats()['refresh_ok'] == 2


def test_ttl_zero_disables_cache():
    """TTL=0 = 关闭缓存（线上紧急开关），退回每请求打上游的旧行为。"""
    with mock.patch.object(BaseConfig, 'AUDIO_TAG_ACL_CACHE_TTL_SECONDS', 0):
        stub = _FakeStub(items=[{'id': 74, 'name': '打断与恢复'}])
        _resolve(stub, [74])
        _resolve(stub, [74])
    assert stub.list_calls == 2


# ---------------- 「查不了」：上游异常 ----------------

def test_upstream_failure_serves_previous_snapshot_without_caching():
    """上游挂了：返回上一份快照（名称不是数字 id），不写缓存，失败计数 +1。"""
    ok_stub = _FakeStub(items=[{'id': 74, 'name': '打断与恢复'},
                               {'id': 75, 'name': '拒识'}])
    _resolve(ok_stub, [74, 75])

    with acl._COND:
        acl._SNAPSHOT_AT = acl._SNAPSHOT_AT - (acl.tag_cache_ttl_seconds() + 1)

    bad_stub = _FakeStub(exc=RuntimeError('task_service unavailable'))
    resolved = _resolve(bad_stub, [74, 75])

    assert resolved == {74: '打断与恢复', 75: '拒识'}
    assert all(not name.isdigit() for name in resolved.values())
    stats = get_tag_acl_cache_stats()
    assert stats['refresh_fail'] == 1
    assert stats['degraded'] == 1
    # 失败没有被当成一份新快照：快照时间戳仍是上一次成功的
    assert get_tag_acl_cache_stats()['refresh_ok'] == 1


def test_repeated_upstream_failures_do_not_clear_snapshot():
    ok_stub = _FakeStub(items=[{'id': 74, 'name': '打断与恢复'}])
    _resolve(ok_stub, [74])

    bad_stub = _FakeStub(exc=TimeoutError('deadline exceeded'))
    for _ in range(3):
        with acl._COND:
            acl._SNAPSHOT_AT = acl._SNAPSHOT_AT - (acl.tag_cache_ttl_seconds() + 1)
        assert _resolve(bad_stub, [74]) == {74: '打断与恢复'}

    stats = get_tag_acl_cache_stats()
    assert stats['refresh_fail'] == 3
    assert stats['degraded'] == 3
    with acl._COND:
        assert acl._SNAPSHOT == {74: '打断与恢复'}


def test_failure_on_cold_start_returns_empty_not_cached():
    """冷启动首次就失败：返回空映射（调用方回落数字 id），且失败不入快照。"""
    bad_stub = _FakeStub(exc=RuntimeError('connection refused'))
    assert _resolve(bad_stub, [74]) == {}
    with acl._COND:
        assert acl._SNAPSHOT == {}
        assert acl._SNAPSHOT_AT is None
    # 上游恢复后立刻能拿到名字，不被上一次失败「固化」
    ok_stub = _FakeStub(items=[{'id': 74, 'name': '打断与恢复'}])
    assert _resolve(ok_stub, [74]) == {74: '打断与恢复'}


# ---------------- 「查不到」：上游成功但缺 id ----------------

def test_missing_id_does_not_disturb_positive_mappings():
    stub = _FakeStub(items=[{'id': 74, 'name': '打断与恢复'}])
    resolved = _resolve(stub, [74, 999])

    assert resolved == {74: '打断与恢复'}
    assert 999 not in resolved
    assert get_tag_acl_cache_stats()['miss'] == 1
    # 查不到不触发额外上游调用
    assert stub.list_calls == 1
    assert _resolve(stub, [74, 999]) == {74: '打断与恢复'}
    assert stub.list_calls == 1


def test_negative_cache_marks_only_authoritative_miss():
    with mock.patch.object(BaseConfig, 'AUDIO_TAG_ACL_NEGATIVE_CACHE_SECONDS', 30):
        # 冷启动就失败 = 查不了，不得进负缓存
        bad_stub = _FakeStub(exc=RuntimeError('boom'))
        _resolve(bad_stub, [999])
        with acl._COND:
            assert 999 not in acl._NEGATIVE

        # 上游成功但没有该 id = 查不到，进负缓存；重复出现只记账
        ok_stub = _FakeStub(items=[{'id': 74, 'name': '打断与恢复'}])
        _resolve(ok_stub, [74, 999])
        with acl._COND:
            assert 999 in acl._NEGATIVE
        _resolve(ok_stub, [74, 999])
        assert get_tag_acl_cache_stats()['negative_hit'] == 1


# ---------------- 并发单飞 ----------------

def test_concurrent_first_load_hits_upstream_once():
    """20 线程同时首轮解析：上游（含分页）只被打一次。"""
    stub = _FakeStub(items=[{'id': 74, 'name': '打断与恢复'},
                            {'id': 75, 'name': '拒识'}], delay=0.05)
    threads = 20
    barrier = threading.Barrier(threads)
    results = []
    errors = []

    def worker(i):
        try:
            barrier.wait(timeout=10)
            results.append(TagAclRepository().get_tag_id_to_name_map([74, 75]))
        except Exception as exc:  # pragma: no cover - 仅用于报错定位
            errors.append(exc)

    # stub 只在主线程打一次补丁：多线程各自 patch 同一目标是竞态的，
    # 会让部分调用落回真实 stub。
    with _patch_stub(stub):
        workers = [threading.Thread(target=worker, args=(i,)) for i in range(threads)]
        for t in workers:
            t.start()
        for t in workers:
            t.join(timeout=20)

    assert not errors
    assert len(results) == threads
    assert all(r == {74: '打断与恢复', 75: '拒识'} for r in results)
    assert stub.list_calls == 1
    assert get_tag_acl_cache_stats()['refresh_ok'] == 1


def test_wait_timeout_serves_stale_snapshot(monkeypatch):
    """上游刷新迟迟不回时，等待者按上限降级用陈旧快照，不跟着一起挂住。"""
    import time as _t
    ok_stub = _FakeStub(items=[{'id': 74, 'name': '打断与恢复'}])
    _resolve(ok_stub, [74])

    with acl._COND:
        acl._SNAPSHOT_AT = acl._SNAPSHOT_AT - (acl.tag_cache_ttl_seconds() + 1)
        acl._REFRESHING = True      # 模拟另一个线程正在刷新且有去无回
    monkeypatch.setattr(acl, '_REFRESH_WAIT_SECONDS', 0.1)

    t0 = _t.perf_counter()
    resolved = _resolve(ok_stub, [74])
    elapsed = _t.perf_counter() - t0

    assert resolved == {74: '打断与恢复'}
    assert elapsed < 0.5
    assert ok_stub.list_calls == 1          # 等待者没有自己再打一次上游
    assert get_tag_acl_cache_stats()['degraded'] == 1


def test_concurrent_failures_do_not_stampede():
    """上游不可用时，一轮并发也只打一次上游（等待者服务陈旧快照，不各自重试）。"""
    stub = _FakeStub(exc=RuntimeError('unavailable'), delay=0.2)
    threads = 10
    barrier = threading.Barrier(threads)

    def worker():
        barrier.wait(timeout=10)
        TagAclRepository().get_tag_id_to_name_map([74])

    with _patch_stub(stub):
        workers = [threading.Thread(target=worker) for _ in range(threads)]
        for t in workers:
            t.start()
        for t in workers:
            t.join(timeout=20)

    assert stub.list_calls == 1
    assert get_tag_acl_cache_stats()['refresh_fail'] == 1
