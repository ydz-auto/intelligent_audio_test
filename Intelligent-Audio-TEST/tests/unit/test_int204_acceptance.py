# -*- coding: utf-8 -*-
"""INT-204 验收补充测试（测试工程师）：接口层 + 真 Redis TTL 行为

开发侧 tests/unit/test_int204_stats_cache_degraded.py 已锁定 refresh_stats_cache
的降级契约（FakeRedis，mock 拉取）。本文件补验收盲区：

1. 手动刷新接口 POST /home/stats/refresh 的返回语义（开发建议测试点，此前无测试）：
   全部域失败 → 400 error（不谎报"已刷新"）；部分失败/全部成功 → 200。
2. 读侧 GET /home/stats/details 故障窗口不污染缓存（缺陷路径锁定）：
   无缓存 + 全部域失败 → 返回全 0 默认值但 Redis 不落缓存，下轮请求重试。
3. 真 Redis TTL 语义（FakeRedis 无法覆盖）：
   - 降级快照 TTL 真实为短 TTL，正常快照 TTL 真实为长 TTL；
   - 全部域失败时既有快照 TTL 不被重置；
   - 降级短 TTL 真实自然过期，恢复后下一次刷新按正常 TTL 回正（核心验收点：
     「恢复后自动回正」）。
4. task 域真实 proxy 链路 × 真 Redis（审计打回补充）：TestRealRedisTtlBehavior
   的 task 域失败 mock 在 _fetch_* 函数层，而审计致命缺陷（proxy 层吞异常）
   正是在真实 proxy 链路上才暴露——本组用例在 stub 层注入故障，经真实
   _TaskDataProxy → _grpc_call → stats_cache 全链路后落真 Redis。

隔离与卫生：两类测试均通过 monkeypatch 将 _CACHE_KEY（stats_cache 与
home_service 两处）改为本卡专属 scratch key，真库中不触碰线上 home_stats 键；
每用例前后删除 scratch key，不留测试残留。Redis 不可用时整文件 skip。
"""
import json
import os
import time
import types

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
import redis as redis_lib
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api_gateway.application.services.stats_cache as stats_cache_module
import api_gateway.application.services.home_service as home_service_module
from api_gateway.application.services.stats_cache import _CACHE_KEY, refresh_stats_cache
from api_gateway.routes.home_bp import router as home_router
from shared.infrastructure.config import BaseConfig

# 本卡专属 scratch key（与线上 home_stats 键隔离）。全量回归并行（pytest-xdist）
# 下 8 个 worker 共享同一 Redis：key 必须按 worker 隔离，否则并发 worker 间的
# setup 删除/写入互踩（gw5 写入降级快照、gw7 setup 删除又 seed 旧值之类的竞态）。
_SCRATCH_KEY = 'home_stats:int204_acceptance:%s' % (
    os.environ.get('PYTEST_XDIST_WORKER') or 'main')

# 故障前最后一次健康刷新写入的既有快照（数值与在线域新值刻意错开）
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

# 复现 INT-138 实机场景：task/evaluation 域掉线（tasks/test_cases/groups/dimensions）
_INT138_FAILED = (
    '_fetch_testcase_stats_via_grpc',
    '_fetch_testcase_group_count_via_grpc',
    '_fetch_task_stats_via_grpc',
    '_fetch_dimension_stats_via_grpc',
)


def _raise_domain_error(*args, **kwargs):
    raise ConnectionError('模拟域服务不可达（INT-204 验收）')


def _patch_fetchers(monkeypatch, failed_names=()):
    for name, fn in _OK_FETCHES.items():
        monkeypatch.setattr(
            stats_cache_module, name,
            _raise_domain_error if name in failed_names else fn)


def _redis_client():
    return redis_lib.from_url(BaseConfig.REDIS_URL)


@pytest.fixture()
def scratch_redis(monkeypatch):
    """_CACHE_KEY 双处改指 scratch key；每用例前后删除，不留残留。Redis 不可用 skip。"""
    try:
        r = _redis_client()
        r.ping()
    except Exception as e:
        pytest.skip(f'Redis 不可用，跳过真库验收用例: {e}')
    monkeypatch.setattr(stats_cache_module, '_CACHE_KEY', _SCRATCH_KEY)
    monkeypatch.setattr(home_service_module, '_CACHE_KEY', _SCRATCH_KEY)
    r.delete(_SCRATCH_KEY)
    yield r
    r.delete(_SCRATCH_KEY)


def _make_home_client(monkeypatch) -> TestClient:
    """装配真实 home 路由：RequestAdapter 等价中间件（预解析 JSON body +
    ContextVar 注入）+ AUTH_MODE=off 口径权限注入（同 INT-110 harness）。"""
    from api_gateway.infrastructure.request_adapter import set_current_request

    async def _req_adapter_and_admin(request, call_next):
        content_type = request.headers.get('content-type', '')
        request.state._json_body = None
        if 'application/json' in content_type:
            try:
                body = await request.body()
                request.state._json_body = json.loads(body) if body else None
            except Exception:
                request.state._json_body = None
        set_current_request(request)
        request.state.permissions = ['*']
        response = await call_next(request)
        set_current_request(None)
        return response

    app = FastAPI()
    app.include_router(home_router, prefix='/api/v1/home')
    app.middleware('http')(_req_adapter_and_admin)
    return TestClient(app)


class TestRefreshEndpointSemantics:
    """POST /home/stats/refresh 返回语义（此前无任何测试覆盖）"""

    def test_refresh_all_failed_returns_error(self, monkeypatch, scratch_redis):
        """全部域失败：接口返回 400 失败语义，不谎报"已刷新"，且不写缓存"""
        _patch_fetchers(monkeypatch, failed_names=set(_OK_FETCHES))
        client = _make_home_client(monkeypatch)

        resp = client.post('/api/v1/home/stats/refresh')

        assert resp.status_code == 400
        body = resp.json()
        assert body['success'] is False
        assert '上游统计服务暂不可用' in body['message']
        assert scratch_redis.get(_SCRATCH_KEY) is None

    def test_refresh_partial_failure_200_with_degraded_ttl(self, monkeypatch, scratch_redis):
        """部分域失败：接口 200 成功（降级快照已写），真库 TTL 为降级短 TTL"""
        scratch_redis.setex(_SCRATCH_KEY, 900, json.dumps(_OLD_SNAPSHOT))
        _patch_fetchers(monkeypatch, failed_names=set(_INT138_FAILED))
        client = _make_home_client(monkeypatch)

        resp = client.post('/api/v1/home/stats/refresh')

        assert resp.status_code == 200
        assert resp.json()['success'] is True
        ttl = scratch_redis.ttl(_SCRATCH_KEY)
        assert 0 < ttl <= stats_cache_module._CACHE_TTL_DEGRADED
        parsed = json.loads(scratch_redis.get(_SCRATCH_KEY))
        assert parsed['tasks'] == _OLD_SNAPSHOT['tasks']  # 失败域沿用旧值，绝不落 0
        assert parsed['audio_files']['total'] == 19800    # 在线域新值

    def test_refresh_all_success_200_with_normal_ttl(self, monkeypatch, scratch_redis):
        """全部成功：接口 200，真库 TTL 为正常长 TTL"""
        _patch_fetchers(monkeypatch)
        client = _make_home_client(monkeypatch)

        resp = client.post('/api/v1/home/stats/refresh')

        assert resp.status_code == 200
        ttl = scratch_redis.ttl(_SCRATCH_KEY)
        assert stats_cache_module._CACHE_TTL - 5 < ttl <= stats_cache_module._CACHE_TTL


class TestDetailsEndpointNoCachePoisoning:
    """GET /home/stats/details 故障窗口不污染缓存（缺陷路径锁定）"""

    def test_details_outage_returns_defaults_without_caching(self, monkeypatch, scratch_redis):
        """无缓存 + 全部域失败：返回全 0 默认值，但 Redis 不落缓存——
        这是原缺陷的污染路径，下轮请求必须仍会重试"""
        _patch_fetchers(monkeypatch, failed_names=set(_OK_FETCHES))
        client = _make_home_client(monkeypatch)

        resp = client.get('/api/v1/home/stats/details')

        assert resp.status_code == 200
        data = resp.json()['data']
        assert data['tasks']['total'] == 0
        assert data['test_cases']['total'] == 0
        assert data['dimensions']['total'] == 0
        # updated_at=None 经 success_response(exclude_none=True) 剔除出响应体
        assert data.get('updated_at') is None
        # 核心断言：全 0 响应不得写入缓存（修复前此路径会落 1h TTL 的全 0 快照）
        assert scratch_redis.get(_SCRATCH_KEY) is None

    def test_details_during_partial_outage_shows_stale_not_zeros(self, monkeypatch, scratch_redis):
        """部分域失败：先降级刷新，首页读到失败域旧值（非 0）+ 在线域新值——
        实机上成员看到的应是旧值回退而非全 0"""
        scratch_redis.setex(_SCRATCH_KEY, 900, json.dumps(_OLD_SNAPSHOT))
        _patch_fetchers(monkeypatch, failed_names=set(_INT138_FAILED))
        client = _make_home_client(monkeypatch)

        assert refresh_stats_cache() is True

        resp = client.get('/api/v1/home/stats/details')
        assert resp.status_code == 200
        data = resp.json()['data']
        assert data['tasks']['total'] == 5       # 旧值（INT-138 实机曾显示 0）
        assert data['test_cases']['total'] == 4  # 旧值
        assert data['dimensions']['total'] == 37  # 旧值
        assert data['audio_files']['total'] == 19800  # 在线域新值


class TestRealRedisTtlBehavior:
    """真 Redis TTL 语义（FakeRedis 无法覆盖）"""

    def test_all_failed_preserves_existing_snapshot_ttl(self, monkeypatch, scratch_redis):
        """全部域失败：既有快照原样保留，TTL 不被重置（不续命、不缩短）"""
        scratch_redis.setex(_SCRATCH_KEY, 900, json.dumps(_OLD_SNAPSHOT))
        before = scratch_redis.get(_SCRATCH_KEY)

        _patch_fetchers(monkeypatch, failed_names=set(_OK_FETCHES))
        assert refresh_stats_cache() is False

        assert scratch_redis.get(_SCRATCH_KEY) == before
        ttl = scratch_redis.ttl(_SCRATCH_KEY)
        assert 880 < ttl <= 900  # 原 TTL 自然流逝，未被改为降级/正常 TTL

    def test_recovery_after_degraded_ttl_expiry(self, monkeypatch, scratch_redis):
        """核心验收点端到端：故障窗口写入降级短 TTL 快照 → 真实自然过期 →
        上游恢复后下一次刷新按正常 TTL 写入全新值（恢复后自动回正）"""
        scratch_redis.setex(_SCRATCH_KEY, 900, json.dumps(_OLD_SNAPSHOT))

        # 故障窗口：复现 INT-138 部分掉线，降级 TTL 临时调短为 1s 以真实观察过期
        monkeypatch.setattr(stats_cache_module, '_CACHE_TTL_DEGRADED', 1)
        _patch_fetchers(monkeypatch, failed_names=set(_INT138_FAILED))
        assert refresh_stats_cache() is True
        ttl = scratch_redis.ttl(_SCRATCH_KEY)
        assert 0 < ttl <= 1
        degraded_raw = scratch_redis.get(_SCRATCH_KEY)
        assert json.loads(degraded_raw)['tasks'] == _OLD_SNAPSHOT['tasks']

        # 真实等待降级 TTL 自然过期（证明短 TTL 快照会消失，而非滞留 1 小时）
        deadline = time.time() + 5
        while time.time() < deadline and scratch_redis.get(_SCRATCH_KEY) is not None:
            time.sleep(0.1)
        assert scratch_redis.get(_SCRATCH_KEY) is None, '降级快照未在短 TTL 内自然过期'

        # 上游恢复：下一次刷新按正常 TTL 写入全新值
        _patch_fetchers(monkeypatch)  # 全部恢复健康
        assert refresh_stats_cache() is True
        parsed = json.loads(scratch_redis.get(_SCRATCH_KEY))
        assert parsed['tasks'] == {'total': 50, 'completed': 20, 'running': 10, 'failed': 10}
        assert parsed['test_cases'] == {'total': 40, 'groups': 30}
        assert parsed['dimensions'] == {'total': 370, 'with_endpoints': 0, 'endpoints': 0}
        ttl = scratch_redis.ttl(_SCRATCH_KEY)
        assert stats_cache_module._CACHE_TTL - 5 < ttl <= stats_cache_module._CACHE_TTL

        # 恢复后的快照经读侧 Schema 校验不破坏首页接口
        from api_gateway.schemas.home import HomeStatsDetails
        HomeStatsDetails(**parsed)


# task 域以外的六个域（真实链路用例中 mock 在 _fetch_* 函数层，非本组被测对象）
_NON_TASK_FETCH_NAMES = (
    '_fetch_audio_stats_via_grpc',
    '_fetch_device_stats_via_grpc',
    '_fetch_playback_device_stats_via_grpc',
    '_fetch_api_stats_via_grpc',
    '_fetch_dimension_stats_via_grpc',
    '_fetch_reports_count_via_grpc',
)


def _patch_non_task_fetches(monkeypatch):
    for name in _NON_TASK_FETCH_NAMES:
        monkeypatch.setattr(stats_cache_module, name, _OK_FETCHES[name])


def _patch_task_stub(monkeypatch, stub):
    import api_gateway.infrastructure.grpc_proxies.task_data_proxies as task_data_proxies_module
    monkeypatch.setattr(
        task_data_proxies_module, 'get_task_data_service_stub', lambda: stub)


class TestRealProxyChainRealRedis:
    """审计问题 2 闭环：task 域真实 _TaskDataProxy 链路 × 真 Redis

    其余四象限各有覆盖（假 proxy×FakeRedis=degraded 套件、真 proxy×FakeRedis=
    test_int204_real_proxy_chain、假 proxy 层×真 Redis=TestRealRedisTtlBehavior），
    本组补最后一象限：stub 层注入故障，经真实 proxy → _grpc_call →
    stats_cache 全链路后落真 Redis。
    """

    @staticmethod
    def _down_stub():
        import grpc
        error = grpc.RpcError('UNAVAILABLE: failed to connect to task_service')

        class _DownStub:
            def GetTaskStats(self, request):
                raise error

            def GetTestCaseStats(self, request):
                raise error

            def ListTestCaseGroups(self, request):
                raise error

        return _DownStub()

    @staticmethod
    def _healthy_stub():
        import types

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

    def test_task_service_down_real_proxy_stale_values_degraded_ttl(self, monkeypatch, scratch_redis):
        """主诉场景端到端（真实链路）：task_service 掉线窗口刷新首页统计 →
        真 Redis 中 tasks/test_cases/groups 为旧值（非 0）且按降级短 TTL 落缓存
        （修复前：proxy 吞异常 → {} → 0 值按 3600s 正常 TTL 落缓存）"""
        scratch_redis.setex(_SCRATCH_KEY, 900, json.dumps(_OLD_SNAPSHOT))
        _patch_task_stub(monkeypatch, self._down_stub())
        _patch_non_task_fetches(monkeypatch)

        assert refresh_stats_cache() is True

        ttl = scratch_redis.ttl(_SCRATCH_KEY)
        assert 0 < ttl <= stats_cache_module._CACHE_TTL_DEGRADED
        parsed = json.loads(scratch_redis.get(_SCRATCH_KEY))
        assert parsed['tasks'] == _OLD_SNAPSHOT['tasks']
        assert parsed['tasks']['total'] == 5
        assert parsed['test_cases'] == _OLD_SNAPSHOT['test_cases']
        assert parsed['test_cases'] == {'total': 4, 'groups': 3}
        assert parsed['audio_files']['total'] == 19800  # 在线域新值

    def test_task_service_recovery_real_proxy_back_to_normal_ttl(self, monkeypatch, scratch_redis):
        """恢复端到端（真实链路）：掉线窗口降级快照（TTL 调短为 1s）真实自然过期 →
        stub 恢复健康后下一次刷新经真实 proxy 写入全新值 + 正常 TTL"""
        scratch_redis.setex(_SCRATCH_KEY, 900, json.dumps(_OLD_SNAPSHOT))
        _patch_task_stub(monkeypatch, self._down_stub())
        _patch_non_task_fetches(monkeypatch)
        monkeypatch.setattr(stats_cache_module, '_CACHE_TTL_DEGRADED', 1)

        assert refresh_stats_cache() is True
        assert json.loads(scratch_redis.get(_SCRATCH_KEY))['tasks']['total'] == 5

        # 真实等待降级快照自然过期
        deadline = time.time() + 5
        while time.time() < deadline and scratch_redis.get(_SCRATCH_KEY) is not None:
            time.sleep(0.1)
        assert scratch_redis.get(_SCRATCH_KEY) is None, '降级快照未在短 TTL 内自然过期'

        # 上游恢复：真实 proxy 正常载荷 → 全新值 + 正常 TTL
        _patch_task_stub(monkeypatch, self._healthy_stub())
        assert refresh_stats_cache() is True
        parsed = json.loads(scratch_redis.get(_SCRATCH_KEY))
        assert parsed['tasks'] == {'total': 3, 'completed': 2, 'running': 1, 'failed': 0}
        assert parsed['test_cases'] == {'total': 40, 'groups': 3}
        ttl = scratch_redis.ttl(_SCRATCH_KEY)
        assert stats_cache_module._CACHE_TTL - 5 < ttl <= stats_cache_module._CACHE_TTL
