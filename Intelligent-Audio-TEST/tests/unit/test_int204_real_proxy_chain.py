# -*- coding: utf-8 -*-
"""INT-204 审计问题 2：task 域失败传播必须走真实 _TaskDataProxy 链路验证

首轮修复的契约测试用「直接抛 ConnectionError 的假 proxy」替换
task_data_service 单例，而真实 _TaskDataProxy 方法经 _grpc_call（默认
reraise=False 吞异常返回 default_return）根本不抛——致命缺陷
（task_service 掉线 → {} → items=[] → 0 值按正常 TTL 落缓存）在假对象
契约全绿下逃逸。

本文件在真实代理链路上锁定失败传播契约：

  stub（抛 grpc.RpcError / 返回 success=False / 返回正常载荷）
    → 真实 _TaskDataProxy（task_data_proxies.task_data_service 单例）
    → 真实 _grpc_call（reraise 透传）
    → stats_cache._fetch_*_via_grpc
    → refresh_stats_cache 降级判定

patch 点：_TaskDataProxy 方法内经模块级名字调用 get_task_data_service_stub()，
patch task_data_proxies 模块的该名字即可替换 stub；代理与 _grpc_call 代码
路径全程真实。其余六域在链路测试中按既有口径 mock 在 _fetch_* 函数层
（本文件的被测对象是 task 域真实链路）。
"""
import json
import os
import types

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import grpc
import pytest

import api_gateway.application.services.stats_cache as stats_cache_module
import api_gateway.infrastructure.grpc_proxies.task_data_proxies as task_data_proxies_module
from api_gateway.application.services.stats_cache import _CACHE_KEY, refresh_stats_cache
from api_gateway.infrastructure.grpc_proxies.task_data_proxies import task_data_service

# 既有快照（模拟故障前最后一次健康刷新写入的值，数值与新值刻意错开）
_OLD_SNAPSHOT = {
    'test_cases': {'total': 4, 'groups': 3},
    'tasks': {'total': 5, 'completed': 2, 'running': 1, 'failed': 1},
    'devices': {'online': 3, 'offline': 0, 'total': 3},
    'audio_files': {
        'total': 1980, 'dry': 900, 'noise': 600, 'prompt': 480,
        'duration': {'total': 0, 'dry': 0, 'noise': 0, 'prompt': 0},
    },
    'playback_devices': 3,
    'apis': {'online': 6, 'offline': 2, 'total': 8},
    'reports': 12,
    'dimensions': {'total': 37, 'with_endpoints': 0, 'endpoints': 0},
    'updated_at': '2026-10-12T19:00:00+08:00',
}

# task 域以外的六个域（链路测试中 mock 在 _fetch_* 函数层，数值区分新旧）
_OK_FETCHES_NON_TASK = {
    '_fetch_audio_stats_via_grpc': lambda: (19800, 9000, 6000, 4800, 0.0, 0.0, 0.0, 0.0),
    '_fetch_device_stats_via_grpc': lambda: (20, 10),
    '_fetch_playback_device_stats_via_grpc': lambda: 30,
    '_fetch_api_stats_via_grpc': lambda: (60, 20),
    '_fetch_dimension_stats_via_grpc': lambda: (370, 0, 0),
    '_fetch_reports_count_via_grpc': lambda: 120,
}


def _patch_non_task_fetches(monkeypatch):
    for name, fn in _OK_FETCHES_NON_TASK.items():
        monkeypatch.setattr(stats_cache_module, name, fn)


def _down_stub():
    """stub 层模拟 task_service 掉线：三个方法一律抛 gRPC 传输异常"""
    error = grpc.RpcError('UNAVAILABLE: failed to connect to task_service')

    class _DownStub:
        def GetTaskStats(self, request):
            raise error

        def GetTestCaseStats(self, request):
            raise error

        def ListTestCaseGroups(self, request):
            raise error

    return _DownStub()


def _app_error_stub():
    """stub 层模拟 task_service 应用层失败：success=False"""
    return types.SimpleNamespace(
        GetTaskStats=lambda req: types.SimpleNamespace(
            success=False, message='task_service 内部错误', data=''),
        GetTestCaseStats=lambda req: types.SimpleNamespace(
            success=False, message='task_service 内部错误', data=''),
        ListTestCaseGroups=lambda req: types.SimpleNamespace(
            success=False, message='task_service 内部错误', data=''),
    )


def _healthy_stub():
    """stub 层正常载荷（空库合法形态：items 键恒在）"""
    return types.SimpleNamespace(
        GetTaskStats=lambda req: types.SimpleNamespace(
            success=True, message='',
            data=json.dumps({'items': [
                {'key': 'completed', 'count': 2},
                {'key': 'running', 'count': 1},
            ]})),
        GetTestCaseStats=lambda req: types.SimpleNamespace(
            success=True, message='', data=json.dumps({'total': 40})),
        ListTestCaseGroups=lambda req: types.SimpleNamespace(
            success=True, message='',
            data=json.dumps({'items': [{'id': 'g1'}, {'id': 'g2'}, {'id': 'g3'}]})),
    )


def _patch_stub(monkeypatch, stub):
    monkeypatch.setattr(
        task_data_proxies_module, 'get_task_data_service_stub', lambda: stub)


class _FakeRedis:
    """仅覆盖 stats_cache 用到的 get/setex，记录写调用供断言"""

    def __init__(self, initial=None):
        self._store = {}
        self.setex_calls = []
        if initial is not None:
            self._store[_CACHE_KEY] = json.dumps(initial)

    def get(self, key):
        return self._store.get(key)

    def setex(self, key, ttl, value):
        self.setex_calls.append((key, ttl, value))
        self._store[key] = value


def _patch_redis(monkeypatch, initial=None):
    fake = _FakeRedis(initial)
    monkeypatch.setattr(stats_cache_module, '_get_redis', lambda: fake)
    return fake


class TestRealProxyFailureContract:
    """真实 _TaskDataProxy 上的失败传播契约（不经任何假 proxy）"""

    def test_get_task_stats_reraises_transport_error(self, monkeypatch):
        """掉线时 get_task_stats 必须上抛 RpcError，不得吞成 {}（首轮致命缺陷路径）"""
        _patch_stub(monkeypatch, _down_stub())
        with pytest.raises(grpc.RpcError):
            task_data_service.get_task_stats(group_by='status')

    def test_get_task_stats_reraises_on_success_false(self, monkeypatch):
        """success=False 时 get_task_stats 必须上抛 RuntimeError，不得吞成 {}"""
        _patch_stub(monkeypatch, _app_error_stub())
        with pytest.raises(RuntimeError, match='GetTaskStats gRPC 失败'):
            task_data_service.get_task_stats(group_by='status')

    def test_default_swallow_semantics_unchanged_without_reraise(self, monkeypatch):
        """未显式 reraise 的既有调用方语义不变：吞异常返回 {}

        锁定 _grpc_call 默认吞异常边界——只有统计链路显式 reraise，
        分组列表/删除前计数等调用方的失败语义不受影响。
        """
        _patch_stub(monkeypatch, _down_stub())
        assert task_data_service.get_testcase_stats() == {}
        assert task_data_service.list_testcase_groups() == {}

    def test_stats_optin_reraise_propagates(self, monkeypatch):
        """统计链路显式 reraise=True：get_testcase_stats / list_testcase_groups 上抛"""
        _patch_stub(monkeypatch, _down_stub())
        with pytest.raises(grpc.RpcError):
            task_data_service.get_testcase_stats(reraise=True)
        with pytest.raises(grpc.RpcError):
            task_data_service.list_testcase_groups(reraise=True)


class TestRealChainThroughStatsCache:
    """stub（抛 RpcError）→ 真实 proxy → _grpc_call → stats_cache → refresh 全真实链路"""

    def test_task_service_down_degrades_to_stale_not_zeros(self, monkeypatch):
        """核心逃逸场景锁定：task_service 掉线（真实 proxy 链路）时
        tasks/test_cases/groups 沿用旧值 + 降级短 TTL，绝不以 0 按正常 TTL 落缓存"""
        _patch_stub(monkeypatch, _down_stub())
        _patch_non_task_fetches(monkeypatch)
        fake = _patch_redis(monkeypatch, initial=_OLD_SNAPSHOT)

        assert refresh_stats_cache() is True
        assert len(fake.setex_calls) == 1
        _, ttl, raw = fake.setex_calls[0]
        assert ttl == stats_cache_module._CACHE_TTL_DEGRADED
        assert ttl < stats_cache_module._CACHE_TTL

        parsed = json.loads(raw)
        # 修复前：真实 proxy 吞掉 RpcError → {} → 三域静默置 0 且按 3600s 正常 TTL 落缓存
        assert parsed['tasks'] == _OLD_SNAPSHOT['tasks']
        assert parsed['tasks']['total'] == 5
        assert parsed['test_cases'] == _OLD_SNAPSHOT['test_cases']
        assert parsed['test_cases']['total'] == 4
        assert parsed['test_cases']['groups'] == 3
        # 在线域为全新值
        assert parsed['audio_files']['total'] == 19800
        assert parsed['dimensions']['total'] == 370

    def test_task_service_down_without_old_cache_uses_degraded_ttl(self, monkeypatch):
        """无旧缓存 + task 域真实失败：无旧值可沿用落 0，但必须按降级短 TTL 写入
        （若失败未透传，此场景会按 3600s 正常 TTL 写入全 0/部分 0）"""
        _patch_stub(monkeypatch, _down_stub())
        _patch_non_task_fetches(monkeypatch)
        fake = _patch_redis(monkeypatch)

        assert refresh_stats_cache() is True
        _, ttl, raw = fake.setex_calls[0]
        assert ttl == stats_cache_module._CACHE_TTL_DEGRADED
        parsed = json.loads(raw)
        assert parsed['tasks']['total'] == 0
        assert parsed['test_cases'] == {'total': 0, 'groups': 0}
        # 非失败域取到新值
        assert parsed['reports'] == 120

    def test_all_domains_failed_through_real_chain_no_cache_write(self, monkeypatch):
        """task 域真实失败 + 其余域一并失败：不写缓存，返回 False"""
        _patch_stub(monkeypatch, _down_stub())
        for name in _OK_FETCHES_NON_TASK:
            def _raise(*args, _name=name, **kwargs):
                raise ConnectionError('%s 不可达' % _name)
            monkeypatch.setattr(stats_cache_module, name, _raise)
        fake = _patch_redis(monkeypatch, initial=_OLD_SNAPSHOT)

        assert refresh_stats_cache() is False
        assert fake.setex_calls == []

    def test_healthy_stub_writes_fresh_values_through_real_proxy(self, monkeypatch):
        """健康路径回归：真实 proxy（reraise=True）正常解析载荷，按正常 TTL 写全新值"""
        _patch_stub(monkeypatch, _healthy_stub())
        _patch_non_task_fetches(monkeypatch)
        fake = _patch_redis(monkeypatch, initial=_OLD_SNAPSHOT)

        assert refresh_stats_cache() is True
        _, ttl, raw = fake.setex_calls[0]
        assert ttl == stats_cache_module._CACHE_TTL

        parsed = json.loads(raw)
        # GetTaskStats group_by=status：items 2+1 → total=3, completed=2, running=1, failed=0
        assert parsed['tasks'] == {'total': 3, 'completed': 2, 'running': 1, 'failed': 0}
        assert parsed['test_cases'] == {'total': 40, 'groups': 3}
