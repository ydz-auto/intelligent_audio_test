# -*- coding: utf-8 -*-
"""INT-2000 C1：列表每请求跨服务 ListTags → 进程内 tag_id→name TTL 快照缓存。

INT-2047 改造后：请求线程只读快照（TTL 过期 / 冷启动时立即返回当前快照，
刷新交给后台 daemon 线程），因此本文件的用例在解析后会显式等后台刷新落地
（``wait_tag_acl_refresh_idle``），断言的是「快照内容 + 上游调用次数 + 计数」
而不是「请求线程同步刷新」。

覆盖卡面语义（两条红线）：
- TTL 内多次解析 → 上游只被调 1 次；TTL 过期 → 刷新一次；
- 上游抛异常 → 返回上一份快照、不写缓存、失败计数 +1，连续失败不清空快照；
- 上游成功但缺 id → 走「查不到」，正向映射不受影响；
- 并发解析 → 上游调用 = 1 次（后台刷新单飞）；
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
        self.timeouts = []
        self._lock = threading.Lock()

    def ListTags(self, req, timeout=None):
        with self._lock:
            self.list_calls += 1
            self.timeouts.append(timeout)
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
    acl.wait_tag_acl_refresh_idle(timeout=10)
    reset_tag_acl_cache()


@pytest.fixture(autouse=True)
def _default_config(monkeypatch):
    monkeypatch.setattr(BaseConfig, 'AUDIO_TAG_ACL_CACHE_TTL_SECONDS', 60)
    monkeypatch.setattr(BaseConfig, 'AUDIO_TAG_ACL_NEGATIVE_CACHE_SECONDS', 0)
    monkeypatch.setattr(BaseConfig, 'AUDIO_TAG_ACL_REFRESH_TIMEOUT_SECONDS', 2.0)
    monkeypatch.setattr(BaseConfig, 'AUDIO_TAG_ACL_REFRESH_AHEAD_RATIO', 0.7)
    monkeypatch.setattr(BaseConfig, 'AUDIO_TAG_ACL_REFRESH_BACKOFF_SECONDS', 1.0)
    monkeypatch.setattr(BaseConfig, 'AUDIO_TAG_ACL_WARMUP_ENABLED', True)


def _patch_stub(stub):
    return mock.patch('shared.clients.grpc_clients.get_tag_config_service_stub',
                      return_value=stub)


def _resolve(stub, tag_ids):
    """解析一次并等后台刷新落地（后台线程必须仍在上游补丁范围内调用）。"""
    with _patch_stub(stub):
        try:
            return TagAclRepository().get_tag_id_to_name_map(tag_ids)
        finally:
            acl.wait_tag_acl_refresh_idle(timeout=10)


def _warm(stub):
    """起服预热：把快照拉起来（与 audio_service 启动时同一条路径）。"""
    with _patch_stub(stub):
        try:
            return acl.warm_tag_acl_snapshot(attempts=1)
        finally:
            acl.wait_tag_acl_refresh_idle(timeout=10)


def _expire():
    """把快照时间戳推到 TTL 之外，模拟过期。"""
    with acl._COND:
        acl._SNAPSHOT_AT = acl._SNAPSHOT_AT - (acl.tag_cache_ttl_seconds() + 1)


# ---------------- 命中 / TTL ----------------

def test_ttl_hit_calls_upstream_once():
    stub = _FakeStub(items=[{'id': 74, 'name': '打断与恢复'},
                            {'id': 75, 'name': '拒识'}])

    assert _warm(stub) is True
    before = get_tag_acl_cache_stats()
    first = _resolve(stub, [74, 75])
    second = _resolve(stub, [74])

    assert first == {74: '打断与恢复', 75: '拒识'}
    assert second == {74: '打断与恢复'}
    assert stub.list_calls == 1          # 预热那一次之后 TTL 内零调用
    delta = get_tag_acl_cache_stats()
    assert delta['refresh_ok'] - before['refresh_ok'] == 0
    assert delta['hit'] - before['hit'] == 3


def test_ttl_expiry_triggers_exactly_one_refresh():
    stub = _FakeStub(items=[{'id': 74, 'name': '打断与恢复'}])
    _warm(stub)
    assert stub.list_calls == 1

    _expire()
    before = get_tag_acl_cache_stats()

    # 过期瞬间请求侧立即拿旧快照（不阻塞），刷新在后台完成
    assert _resolve(stub, [74]) == {74: '打断与恢复'}
    assert stub.list_calls == 2
    after = get_tag_acl_cache_stats()
    assert after['refresh_ok'] - before['refresh_ok'] == 1
    assert after['refresh_scheduled'] - before['refresh_scheduled'] == 1
    assert after['request_stale'] - before['request_stale'] == 1


def test_ttl_zero_disables_cache():
    """TTL=0 = 关闭缓存（线上紧急开关），退回每请求打上游的旧行为。"""
    with mock.patch.object(BaseConfig, 'AUDIO_TAG_ACL_CACHE_TTL_SECONDS', 0):
        stub = _FakeStub(items=[{'id': 74, 'name': '打断与恢复'}])
        assert _resolve(stub, [74]) == {74: '打断与恢复'}
        assert _resolve(stub, [74]) == {74: '打断与恢复'}
    assert stub.list_calls == 2


# ---------------- 「查不了」：上游异常 ----------------

def test_upstream_failure_serves_previous_snapshot_without_caching():
    """上游挂了：返回上一份快照（名称不是数字 id），不写缓存，失败计数 +1。"""
    ok_stub = _FakeStub(items=[{'id': 74, 'name': '打断与恢复'},
                               {'id': 75, 'name': '拒识'}])
    _warm(ok_stub)
    _expire()
    with acl._COND:
        snapshot_at_before = acl._SNAPSHOT_AT

    bad_stub = _FakeStub(exc=RuntimeError('task_service unavailable'))
    resolved = _resolve(bad_stub, [74, 75])

    assert resolved == {74: '打断与恢复', 75: '拒识'}
    assert all(not name.isdigit() for name in resolved.values())
    stats = get_tag_acl_cache_stats()
    assert stats['refresh_fail'] == 1
    assert stats['degraded'] == 1
    # 失败没有被当成一份新快照：快照时间戳仍是过期前的上一次成功时刻
    with acl._COND:
        assert acl._SNAPSHOT_AT == snapshot_at_before


def test_repeated_upstream_failures_do_not_clear_snapshot():
    ok_stub = _FakeStub(items=[{'id': 74, 'name': '打断与恢复'}])
    _warm(ok_stub)

    bad_stub = _FakeStub(exc=TimeoutError('deadline exceeded'))
    for _ in range(3):
        _expire()
        assert _resolve(bad_stub, [74]) == {74: '打断与恢复'}
        # 退避窗口挡住同一波失败刷屏：清掉退避，让每次尝试真正打上游
        with acl._COND:
            acl._LAST_ATTEMPT_FAILED = False

    stats = get_tag_acl_cache_stats()
    assert stats['refresh_fail'] == 3
    assert stats['degraded'] == 3
    with acl._COND:
        assert acl._SNAPSHOT == {74: '打断与恢复'}


def test_failure_on_cold_start_returns_empty_not_cached():
    """冷启动首次就失败：请求返回空映射（调用方回落数字 id），失败不入快照。"""
    bad_stub = _FakeStub(exc=RuntimeError('connection refused'))
    assert _resolve(bad_stub, [74]) == {}
    with acl._COND:
        assert acl._SNAPSHOT == {}
        assert acl._SNAPSHOT_AT is None

    # 上游恢复后，下一次刷新就能拿到名字，不被上一次失败「固化」
    ok_stub = _FakeStub(items=[{'id': 74, 'name': '打断与恢复'}])
    assert _warm(ok_stub) is True
    assert _resolve(ok_stub, [74]) == {74: '打断与恢复'}


# ---------------- 「查不到」：上游成功但缺 id ----------------

def test_missing_id_does_not_disturb_positive_mappings():
    stub = _FakeStub(items=[{'id': 74, 'name': '打断与恢复'}])
    _warm(stub)
    before = stub.list_calls
    resolved = _resolve(stub, [74, 999])

    assert resolved == {74: '打断与恢复'}
    assert 999 not in resolved
    assert get_tag_acl_cache_stats()['miss'] == 1
    # 查不到不触发额外上游调用
    assert stub.list_calls == before
    assert _resolve(stub, [74, 999]) == {74: '打断与恢复'}
    assert stub.list_calls == before


def test_negative_cache_marks_only_authoritative_miss():
    with mock.patch.object(BaseConfig, 'AUDIO_TAG_ACL_NEGATIVE_CACHE_SECONDS', 30):
        # 冷启动就失败 = 查不了，不得进负缓存
        bad_stub = _FakeStub(exc=RuntimeError('boom'))
        _resolve(bad_stub, [999])
        with acl._COND:
            assert 999 not in acl._NEGATIVE

        # 上游成功但没有该 id = 查不到，进负缓存；重复出现只记账
        ok_stub = _FakeStub(items=[{'id': 74, 'name': '打断与恢复'}])
        _warm(ok_stub)
        _resolve(ok_stub, [74, 999])
        with acl._COND:
            assert 999 in acl._NEGATIVE
        _resolve(ok_stub, [74, 999])
        assert get_tag_acl_cache_stats()['negative_hit'] == 1


# ---------------- 并发：后台刷新单飞 ----------------

def test_concurrent_cold_start_hits_upstream_once():
    """20 线程同时首轮解析：上游（含分页）只被打一次，请求线程不阻塞。"""
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
        acl.wait_tag_acl_refresh_idle(timeout=10)
        after_refresh = TagAclRepository().get_tag_id_to_name_map([74, 75])

    assert not errors
    assert len(results) == threads
    # 冷启动这一波请求立刻返回（空快照），名字由后台刷新补上
    assert all(r == {} for r in results)
    assert stub.list_calls == 1
    assert after_refresh == {74: '打断与恢复', 75: '拒识'}
    assert get_tag_acl_cache_stats()['refresh_ok'] == 1


def test_concurrent_failures_do_not_stampede():
    """上游不可用时，一轮并发也只打一次上游（失败后退避，不各自重试）。"""
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
        acl.wait_tag_acl_refresh_idle(timeout=10)

    assert stub.list_calls == 1
    assert get_tag_acl_cache_stats()['refresh_fail'] == 1
