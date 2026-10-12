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

INT-234 追加会话级 autouse isolated_log_root：业务日志写入/读取两侧均从
get_log_settings() 快照取根目录，本夹具在进程内任何业务写入发生前把
LOG_ROOT_DIR 重定向到本次 pytest 进程独占的空临时目录，读取域即本次运行
产物，跨运行磁盘残留不再进入断言域。
"""
import pytest


@pytest.fixture(scope='session', autouse=True)
def isolated_log_root(tmp_path_factory):
    """业务日志根目录按 pytest 进程隔离（INT-234）。

    缺陷机制：pg_db 每次运行新建临时库（任务 id 从 1 重编号），业务日志却
    落磁盘固定目录 {root}/business/{task_id}/（默认根 ./logs）跨运行持久
    累积；BusinessLogReader 扫描该目录全部历史 PID 文件，前次运行残留
    （如 2026-10-11 含「评估参数提取为空」WARNING 的旧文件）进入本次读取
    域，日志断言类用例被环境性打红（INT-118 链路确定性假红实测确证，
    空日志根重跑即绿）。同族风险覆盖所有对 read_entries 断言的集成用例。

    实现口径：直接覆盖 BaseConfig.LOG_ROOT_DIR 类属性（env 已晚于 import，
    与 storage_env 同款）+ reset_log_settings() 重建快照；写入侧
    BusinessLogFileWriter 惰性单例（首次业务写入时构造）与读取侧
    BusinessLogReader（用例内构造）均在重定向后取根，两侧同根。
    会话级（而非模块级）的原因：日志 worker 的业务写入器是进程级单例，
    先序模块一旦触发业务写入即持有旧根快照，后续模块级重定向对其不可见；
    会话级在进程内任何业务写入发生前完成重定向，单例只建一次、恒取新根。

    teardown 恢复原配置并清快照；临时日志目录随 pytest tmp 保留策略留存
    （最近几次运行可查），不再向仓库 logs/ 增量写入。
    """
    from shared.infrastructure.config import BaseConfig
    from shared.logging.config import reset_log_settings

    original = BaseConfig.LOG_ROOT_DIR
    BaseConfig.LOG_ROOT_DIR = str(tmp_path_factory.mktemp('log_root'))
    reset_log_settings()
    try:
        yield
    finally:
        BaseConfig.LOG_ROOT_DIR = original
        reset_log_settings()


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
