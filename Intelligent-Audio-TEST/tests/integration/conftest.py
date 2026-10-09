# -*- coding: utf-8 -*-
"""集成测试环境隔离（INT-54）。

grpc_mesh（test_task_execute_real_chain）只把 task / api_test / evaluation /
algorithm / report / audio 六个服务地址重定向到进程内 server；auth / device /
adapter / e2e_test 的客户端地址仍走默认配置端口。当本机驻留服务栈（run_all.py
启动）中任一「mesh 外」服务处于「接受连接但不响应」状态时，执行链路中的
best-effort gRPC 调用（如引擎 _register_task_events_via_grpc → device_service）
会永久阻塞（deadline 注入后有界失败）——本夹具把 mesh 外服务地址显式指向
必拒端口（localhost:1），调用即刻 UNAVAILABLE，测试行为与「服务栈未启动」
基线一致，不再隐式依赖驻留栈健康度。

会话级 autouse：仅覆盖 tests/integration/；与各模块 grpc_mesh 的重定向
（不同属性集）无冲突；channel/stub 缓存在夹具建立与拆除时各清一次。
"""
import pytest


@pytest.fixture(scope='session', autouse=True)
def nonmesh_grpc_addresses_refused():
    """mesh 外服务地址 → 必拒端口；channel/stub 缓存前后清理。"""
    import shared.clients._grpc_channels as _channels
    import shared.clients._grpc_stubs as _stubs

    refused = {
        'DEVICE_GRPC_ADDR': 'localhost:1',
        'AUTH_GRPC_ADDR': 'localhost:1',
        'ADAPTER_GRPC_ADDR': 'localhost:1',
        'E2E_GRPC_ADDR': 'localhost:1',
    }
    caches = [
        _channels._get_device_channel,
        _channels._get_auth_channel,
        _channels._get_adapter_channel,
        _channels._get_e2e_channel,
        _stubs.get_device_service_stub,
        _stubs.get_device_result_service_stub,
        _stubs.get_env_device_service_stub,
        _stubs.get_device_config_service_stub,
        _stubs.get_playback_config_service_stub,
        _stubs.get_spl_config_service_stub,
        _stubs.get_auth_service_stub,
        _stubs.get_adapter_service_stub,
        _stubs.get_e2e_execution_service_stub,
    ]

    mp = pytest.MonkeyPatch()
    for attr, addr in refused.items():
        mp.setattr(_channels, attr, addr)
    for clear in [c.cache_clear for c in caches]:
        clear()
    yield
    mp.undo()
    for clear in [c.cache_clear for c in caches]:
        clear()
