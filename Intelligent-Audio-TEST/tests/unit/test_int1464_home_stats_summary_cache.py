# -*- coding: utf-8 -*-
"""INT-1464 首页汇总 GET /home/stats/summary 缓存与设备计数口径单测

背景：summary 每次请求实时串行 4 次 gRPC（任务列表读模型 + 2 次用例分组聚合
+ 设备全量分页拉取），并发 40 下 avg 1.8s，而同级 details 早已有 Redis 缓存。

修复后的契约：
1. 命中 `home_stats_summary` 快照时零回源（不调 ACL / 分组 / 设备 RPC）；
2. 未命中时回源一次并按正常 TTL 写快照，后续请求复用；
3. 设备在线/离线改为 ListDevices per_page=1 按 status 计数（2 次 RPC），
   不再用 EXPORT_PAGE_SIZE 全量分页拉取；
4. 任一域回源失败 → 按降级短 TTL 写快照（不在故障窗口内长时间固化 0 值）；
5. 回源锁被他人持有时等待其快照，避免缓存过期瞬间并发击穿；
6. 数据变化触发的 refresh_stats_cache 连带失效汇总快照。
"""
import json
import os
import time

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api_gateway.application.services.home_service as home_service_module
import api_gateway.application.services.stats_cache as stats_cache_module
from api_gateway.routes.home_bp import router as home_router


def _task_item(**overrides):
    item = {
        'id': 7,
        'name': '最近任务A',
        'status': 'running',
        'device_types': ['phone'],
        'algorithm_type': 'dnn',
        'total_cases': 10,
        'completed_cases': 4,
        'created_at': '2026-10-20T10:00:00',
    }
    item.update(overrides)
    return item


class _StubTaskAcl:
    """记录 list_tasks 调用次数：命中缓存时该函数不得被调用。"""

    def __init__(self):
        self.calls = []

    def list_tasks(self, **kwargs):
        self.calls.append(kwargs)
        return {
            'success': True,
            'message': '',
            'data': {'items': [_task_item()], 'total': 1, 'page': 1, 'per_page': 5},
        }


class _StubDeviceCounts:
    """INT-1464 设备计数：2 次 per_page=1 的 ListDevices 聚合后的在线/离线数。"""

    def __init__(self, result=(3, 1), error=None):
        self.result = result
        self.error = error
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


class _StubTaskDataService:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = 0

    def list_testcase_groups(self, **kwargs):
        self.calls += 1
        if self.fail:
            raise RuntimeError('task_service 不可达')
        return {'items': [{'id': 'g1', 'name': '分组一'}, {'id': 'g2', 'name': '分组二'}]}

    def get_testcase_stats(self, group_by=None, **kwargs):
        self.calls += 1
        if self.fail:
            raise RuntimeError('task_service 不可达')
        return {'items': [{'key': 'g1', 'count': 9}, {'key': 'g2', 'count': 2}]}


class _FakeRedis:
    """覆盖 summary 缓存用到的 get/setex/delete/set(nx=...)。"""

    def __init__(self, initial=None):
        self._store = {}
        self.setex_calls = []
        self.set_calls = []
        self.deleted = []
        if initial is not None:
            self._store[stats_cache_module._SUMMARY_CACHE_KEY] = json.dumps(initial)

    def get(self, key):
        return self._store.get(key)

    def setex(self, key, ttl, value):
        self.setex_calls.append((key, ttl, value))
        self._store[key] = value

    def delete(self, key):
        self.deleted.append(key)
        self._store.pop(key, None)

    def set(self, key, value, nx=False, ex=None):
        self.set_calls.append((key, value, nx, ex))
        if nx and key in self._store:
            return None
        self._store[key] = value
        return True


_CACHED_SUMMARY = {
    'recent_tasks': [{
        'id': 99,
        'name': '缓存里的任务',
        'device_types': ['speaker'],
        'status': 'completed',
        'algorithm_type': None,
        'total_cases': 2,
        'completed_cases': 2,
        'created_at': '2026-10-19T08:00:00',
    }],
    'top_groups': [{'id': 'g9', 'name': '缓存分组', 'case_count': 42}],
    'device_status': {'online': 8, 'offline': 2},
}


def _make_client(monkeypatch, redis_initial=None):
    task_acl = _StubTaskAcl()
    device_counts = _StubDeviceCounts()
    task_data = _StubTaskDataService()
    fake_redis = _FakeRedis(redis_initial)
    monkeypatch.setattr(home_service_module, '_task_acl', task_acl)
    monkeypatch.setattr(home_service_module, 'fetch_device_status_counts', device_counts)
    monkeypatch.setattr(home_service_module, 'task_data_service', task_data)
    monkeypatch.setattr(stats_cache_module, '_get_redis', lambda: fake_redis)

    app = FastAPI()
    app.include_router(home_router, prefix='/api/v1/home')

    @app.middleware('http')
    async def _grant_admin_permissions(request, call_next):
        request.state.permissions = ['*']
        return await call_next(request)

    return TestClient(app), task_acl, device_counts, task_data, fake_redis


class TestSummaryCache:

    def test_cache_hit_skips_all_upstream(self, monkeypatch):
        """命中快照：不调任务列表 / 分组聚合 / 设备计数，返回缓存内容。"""
        client, task_acl, device_counts, task_data, fake = _make_client(
            monkeypatch, redis_initial=_CACHED_SUMMARY)

        resp = client.get('/api/v1/home/stats/summary')

        assert resp.status_code == 200
        body = resp.json()
        assert body.get('success') is True, body
        data = body.get('data') or {}
        assert data['recent_tasks'][0]['name'] == '缓存里的任务'
        assert data['top_groups'][0]['case_count'] == 42
        assert data['device_status'] == {'online': 8, 'offline': 2}
        assert task_acl.calls == []
        assert device_counts.calls == 0
        assert task_data.calls == 0

    def test_cache_miss_computes_once_and_writes_normal_ttl(self, monkeypatch):
        """未命中：回源一次并按正常 TTL 写快照。"""
        client, task_acl, device_counts, task_data, fake = _make_client(monkeypatch)

        resp = client.get('/api/v1/home/stats/summary')

        assert resp.status_code == 200
        data = resp.json()['data']
        assert data['recent_tasks'][0]['id'] == 7
        assert [g['name'] for g in data['top_groups']] == ['分组一', '分组二']
        assert data['top_groups'][0]['case_count'] == 9
        assert data['device_status'] == {'online': 3, 'offline': 1}
        assert len(task_acl.calls) == 1
        assert device_counts.calls == 1

        key, ttl, raw = fake.setex_calls[-1]
        assert key == stats_cache_module._SUMMARY_CACHE_KEY
        assert ttl == stats_cache_module._SUMMARY_CACHE_TTL
        assert 30 <= ttl <= 60, '汇总 TTL 应在 30~60s 区间（卡内规格）'
        assert json.loads(raw)['device_status'] == {'online': 3, 'offline': 1}

    def test_second_request_served_from_cache(self, monkeypatch):
        """首次回源写快照后，第二次请求零回源。"""
        client, task_acl, device_counts, _task_data, _fake = _make_client(monkeypatch)

        assert client.get('/api/v1/home/stats/summary').status_code == 200
        assert client.get('/api/v1/home/stats/summary').status_code == 200

        assert len(task_acl.calls) == 1
        assert device_counts.calls == 1

    def test_device_counts_use_count_rpc_not_full_listing(self, monkeypatch):
        """设备状态不再走全量分页拉取的 device ACL。"""
        assert not hasattr(home_service_module, '_device_acl'), \
            'INT-1464：设备状态不得再依赖全量分页 get_all 的 device ACL'

        client, _task_acl, device_counts, _task_data, _fake = _make_client(monkeypatch)
        resp = client.get('/api/v1/home/stats/summary')

        assert resp.status_code == 200
        assert device_counts.calls == 1
        assert resp.json()['data']['device_status'] == {'online': 3, 'offline': 1}

    def test_degraded_device_domain_uses_short_ttl(self, monkeypatch):
        """设备域回源失败：接口仍 200，快照按降级短 TTL 写入（不固化 0 值 45s）。"""
        client, _task_acl, _device_counts, _task_data, fake = _make_client(monkeypatch)
        monkeypatch.setattr(
            home_service_module, 'fetch_device_status_counts',
            _StubDeviceCounts(error=RuntimeError('device_service 不可达')))

        resp = client.get('/api/v1/home/stats/summary')

        assert resp.status_code == 200
        data = resp.json()['data']
        assert data['device_status'] == {'online': 0, 'offline': 0}
        assert data['recent_tasks'], '其他域不受影响'
        _key, ttl, _raw = fake.setex_calls[-1]
        assert ttl == stats_cache_module._SUMMARY_CACHE_TTL_DEGRADED
        assert ttl < stats_cache_module._SUMMARY_CACHE_TTL

    def test_degraded_top_groups_domain_uses_short_ttl(self, monkeypatch):
        """分组聚合失败：top_groups 为空且按降级短 TTL 写入。"""
        client, _task_acl, _device_counts, _task_data, fake = _make_client(monkeypatch)
        monkeypatch.setattr(home_service_module, 'task_data_service',
                            _StubTaskDataService(fail=True))

        resp = client.get('/api/v1/home/stats/summary')

        assert resp.status_code == 200
        assert resp.json()['data']['top_groups'] == []
        _key, ttl, _raw = fake.setex_calls[-1]
        assert ttl == stats_cache_module._SUMMARY_CACHE_TTL_DEGRADED

    def test_lock_held_waits_for_snapshot(self, monkeypatch):
        """锁被他人持有：等待其写出快照，不重复回源。"""
        client, task_acl, device_counts, _task_data, fake = _make_client(monkeypatch)
        monkeypatch.setattr(home_service_module, 'acquire_summary_refresh_lock', lambda: False)
        payload = _CACHED_SUMMARY
        _seed_summary(fake, payload)

        resp = client.get('/api/v1/home/stats/summary')

        assert resp.status_code == 200
        assert resp.json()['data']['top_groups'][0]['name'] == '缓存分组'
        assert task_acl.calls == []
        assert device_counts.calls == 0

    def test_lock_unavailable_computes_directly(self, monkeypatch):
        """Redis 不可用（锁 = None）：直接回源保证接口可用。"""
        client, task_acl, _device_counts, _task_data, _fake = _make_client(monkeypatch)
        monkeypatch.setattr(home_service_module, 'acquire_summary_refresh_lock', lambda: None)

        resp = client.get('/api/v1/home/stats/summary')

        assert resp.status_code == 200
        assert len(task_acl.calls) == 1


def _seed_summary(fake, payload):
    fake._store[stats_cache_module._SUMMARY_CACHE_KEY] = json.dumps(payload)


# ---- 汇总缓存失效 ----

_OK_FETCHES = {
    '_fetch_testcase_stats_via_grpc': lambda: 40,
    '_fetch_testcase_group_count_via_grpc': lambda: 30,
    '_fetch_task_stats_via_grpc': lambda: (50, 20, 10, 10),
    '_fetch_audio_stats_via_grpc': lambda: (19800, 9000, 6000, 4800, 0.0, 0.0, 0.0, 0.0),
    '_fetch_device_stats_via_grpc': lambda: (20, 10),
    '_fetch_playback_device_stats_via_grpc': lambda: 30,
    '_fetch_api_stats_via_grpc': lambda: (60, 20),
    '_fetch_dimension_stats_via_grpc': lambda: (370, 0, 0),
    '_fetch_reports_count_via_grpc': lambda: 120,
}


class TestSummaryInvalidation:

    def test_refresh_stats_cache_invalidates_summary(self, monkeypatch):
        """数据变化触发的详情刷新连带失效汇总快照。"""
        for name, fn in _OK_FETCHES.items():
            monkeypatch.setattr(stats_cache_module, name, fn)
        fake = _FakeRedis(initial=_CACHED_SUMMARY)
        monkeypatch.setattr(stats_cache_module, '_get_redis', lambda: fake)

        assert stats_cache_module.refresh_stats_cache() is True
        assert stats_cache_module._SUMMARY_CACHE_KEY in fake.deleted
        assert fake.get(stats_cache_module._SUMMARY_CACHE_KEY) is None

    def test_summary_ttl_recomputed_after_invalidation(self, monkeypatch):
        """失效后的下一次请求重新回源并写新快照。"""
        client, task_acl, device_counts, _task_data, fake = _make_client(monkeypatch)
        assert client.get('/api/v1/home/stats/summary').status_code == 200
        stats_cache_module.invalidate_summary_cache()

        assert client.get('/api/v1/home/stats/summary').status_code == 200
        assert len(task_acl.calls) == 2
        assert device_counts.calls == 2


class TestSummaryLockHelpers:

    def test_wait_summary_cache_returns_none_on_timeout(self, monkeypatch):
        monkeypatch.setattr(stats_cache_module, '_get_redis', lambda: _FakeRedis())
        start = time.monotonic()
        assert stats_cache_module.wait_summary_cache(timeout=0.1) is None
        assert time.monotonic() - start >= 0.1

    def test_acquire_lock_returns_none_when_redis_down(self, monkeypatch):
        def _boom():
            raise RuntimeError('redis 不可用')
        monkeypatch.setattr(stats_cache_module, '_get_redis', _boom)
        assert stats_cache_module.acquire_summary_refresh_lock() is None
        # 释放失败不得上抛
        stats_cache_module.release_summary_refresh_lock()
