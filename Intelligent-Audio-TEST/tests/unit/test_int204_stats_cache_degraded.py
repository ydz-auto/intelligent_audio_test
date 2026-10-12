# -*- coding: utf-8 -*-
"""INT-204 首页统计降级快照污染缓存缺陷单测

故障窗口内任一 _fetch_*_via_grpc 失败曾以 0 兜底并按正常 TTL（1h）照常写入
Redis，首页统计全 0 长达 1 小时无自愈（INT-138 第 3 轮实机复现：task/evaluation
掉线后 tasks/test_cases/dimensions 置 0，audio_files/devices 正常）。

修复后的降级契约：
1. 全部域失败 → 不写缓存（既有快照原样保留/保持缺失），refresh 返回 False；
2. 部分域失败 → 失败域沿用旧快照值（stale-while-error），按降级短 TTL 写入；
3. 全部成功 → 按正常 TTL 写入全新值；
4. 域内协议级失败（success=False）与传输异常均不得静默置 0。
"""
import json
import os
import types

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

import api_gateway.application.services.stats_cache as stats_cache_module
from api_gateway.application.services.stats_cache import (
    _CACHE_KEY,
    StatsFetchError,
    refresh_stats_cache,
)

# 既有快照（模拟故障前最后一次健康刷新写入的值）
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


def _raise_domain_error(*args, **kwargs):
    raise StatsFetchError('模拟域服务不可达')


# 全部健康时的拉取结果（与 _OLD_SNAPSHOT 数值刻意错开，便于区分新旧值）
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


def _patch_fetches(monkeypatch, failed_names=()):
    for name, fn in _OK_FETCHES.items():
        monkeypatch.setattr(
            stats_cache_module, name,
            _raise_domain_error if name in failed_names else fn)


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


class TestStatsCacheDegraded:

    def test_all_failed_no_cache_written(self, monkeypatch):
        """全部域失败且无既有缓存：不写缓存，返回 False（下轮请求重试）"""
        _patch_fetches(monkeypatch, failed_names=set(_OK_FETCHES))
        fake = _patch_redis(monkeypatch)

        assert refresh_stats_cache() is False
        assert fake.setex_calls == []
        assert fake.get(_CACHE_KEY) is None

    def test_all_failed_existing_cache_preserved(self, monkeypatch):
        """全部域失败且既有快照在：原样保留（不重置 TTL、不覆写），返回 False"""
        _patch_fetches(monkeypatch, failed_names=set(_OK_FETCHES))
        fake = _patch_redis(monkeypatch, initial=_OLD_SNAPSHOT)
        before = fake.get(_CACHE_KEY)

        assert refresh_stats_cache() is False
        assert fake.setex_calls == []
        assert fake.get(_CACHE_KEY) == before

    def test_partial_failure_keeps_stale_values_with_degraded_ttl(self, monkeypatch):
        """部分域失败（复现 INT-138 场景：task/evaluation 掉线）：失败域沿用旧值，
        在线域取新值，按降级短 TTL 写入"""
        failed = {
            '_fetch_testcase_stats_via_grpc',
            '_fetch_testcase_group_count_via_grpc',
            '_fetch_task_stats_via_grpc',
            '_fetch_dimension_stats_via_grpc',
        }
        _patch_fetches(monkeypatch, failed_names=failed)
        fake = _patch_redis(monkeypatch, initial=_OLD_SNAPSHOT)

        assert refresh_stats_cache() is True
        assert len(fake.setex_calls) == 1
        _, ttl, raw = fake.setex_calls[0]
        assert ttl == stats_cache_module._CACHE_TTL_DEGRADED
        assert ttl < stats_cache_module._CACHE_TTL

        parsed = json.loads(raw)
        # 失败域沿用旧快照值（而非 0）
        assert parsed['tasks'] == _OLD_SNAPSHOT['tasks']
        assert parsed['test_cases'] == _OLD_SNAPSHOT['test_cases']
        assert parsed['dimensions'] == _OLD_SNAPSHOT['dimensions']
        # 在线域为全新值
        assert parsed['audio_files']['total'] == 19800
        assert parsed['devices'] == {'online': 20, 'offline': 10, 'total': 30}
        assert parsed['reports'] == 120
        # 降级快照仍满足读侧 Schema（extra=ignore，不破坏首页接口）
        from api_gateway.schemas.home import HomeStatsDetails
        HomeStatsDetails(**parsed)

    def test_partial_failure_without_old_cache_writes_degraded_zeros(self, monkeypatch):
        """部分域失败且无既有快照（首次刷新即遇故障）：失败域无旧值可沿用落 0，
        但仍按降级短 TTL 写入，恢复后一个短 TTL 周期内自动回正"""
        failed = {'_fetch_task_stats_via_grpc'}
        _patch_fetches(monkeypatch, failed_names=failed)
        fake = _patch_redis(monkeypatch)

        assert refresh_stats_cache() is True
        _, ttl, raw = fake.setex_calls[0]
        assert ttl == stats_cache_module._CACHE_TTL_DEGRADED
        parsed = json.loads(raw)
        assert parsed['tasks'] == {'total': 0, 'completed': 0, 'running': 0, 'failed': 0}
        assert parsed['test_cases'] == {'total': 40, 'groups': 30}

    def test_full_success_writes_fresh_with_normal_ttl(self, monkeypatch):
        """全部域成功：全新值按正常 TTL 写入"""
        _patch_fetches(monkeypatch)
        fake = _patch_redis(monkeypatch, initial=_OLD_SNAPSHOT)

        assert refresh_stats_cache() is True
        _, ttl, raw = fake.setex_calls[0]
        assert ttl == stats_cache_module._CACHE_TTL

        parsed = json.loads(raw)
        assert parsed['tasks'] == {'total': 50, 'completed': 20, 'running': 10, 'failed': 10}
        assert parsed['test_cases'] == {'total': 40, 'groups': 30}
        assert parsed['dimensions'] == {'total': 370, 'with_endpoints': 0, 'endpoints': 0}


class TestFetchFailureContract:
    """域内失败必须抛出（由 refresh 统一降级），不得静默置 0"""

    def _install_report_stub(self, monkeypatch, resp):
        from api_gateway.infrastructure import grpc_proxies

        class _StubReportConfigService:
            stub = types.SimpleNamespace(ListReports=lambda request: resp)

        monkeypatch.setattr(grpc_proxies, 'report_config_service', _StubReportConfigService())

    def test_report_fetch_raises_on_success_false(self, monkeypatch):
        """ListReports 返回 success=False 时抛 StatsFetchError（原先静默返回 0）"""
        self._install_report_stub(
            monkeypatch, types.SimpleNamespace(success=False, message='服务内部错误', data=''))
        with pytest.raises(StatsFetchError):
            stats_cache_module._fetch_reports_count_via_grpc()

    def test_report_fetch_returns_total_on_success(self, monkeypatch):
        """success=True 且载荷含 total 时正常返回计数"""
        self._install_report_stub(
            monkeypatch, types.SimpleNamespace(
                success=True, message='', data=json.dumps({'total': 12})))
        assert stats_cache_module._fetch_reports_count_via_grpc() == 12

    def test_task_fetch_transport_error_propagates(self, monkeypatch):
        """gRPC 传输异常向上抛出（原先被吞掉并返回 0 元组）"""
        from api_gateway.infrastructure import grpc_proxies

        class _StubTaskDataService:
            @staticmethod
            def get_task_stats(group_by=None):
                raise ConnectionError('task_service 不可达')

        monkeypatch.setattr(grpc_proxies, 'task_data_service', _StubTaskDataService())
        with pytest.raises(ConnectionError):
            stats_cache_module._fetch_task_stats_via_grpc()

    def test_transport_failure_degrades_to_stale_in_refresh(self, monkeypatch):
        """端到端：task_service 传输异常时 refresh 不落 0，tasks 沿用旧值"""
        from api_gateway.infrastructure import grpc_proxies

        class _StubTaskDataService:
            @staticmethod
            def get_task_stats(group_by=None):
                raise ConnectionError('task_service 不可达')

            @staticmethod
            def get_testcase_stats(reraise=False):
                return {'total': 40}

            @staticmethod
            def list_testcase_groups(reraise=False):
                return {'items': [{'id': 1, 'name': 'g1'}]}

        monkeypatch.setattr(grpc_proxies, 'task_data_service', _StubTaskDataService())
        for name, fn in _OK_FETCHES.items():
            if name not in ('_fetch_testcase_stats_via_grpc',
                            '_fetch_testcase_group_count_via_grpc',
                            '_fetch_task_stats_via_grpc'):
                monkeypatch.setattr(stats_cache_module, name, fn)
        fake = _patch_redis(monkeypatch, initial=_OLD_SNAPSHOT)

        assert refresh_stats_cache() is True
        _, ttl, raw = fake.setex_calls[0]
        assert ttl == stats_cache_module._CACHE_TTL_DEGRADED
        parsed = json.loads(raw)
        assert parsed['tasks'] == _OLD_SNAPSHOT['tasks']
        assert parsed['test_cases'] == {'total': 40, 'groups': 1}
