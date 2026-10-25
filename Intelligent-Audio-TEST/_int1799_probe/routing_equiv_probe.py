# -*- coding: utf-8 -*-
"""INT-1799 存量等价性取证：迁移后的每一行「老 device_type 路由 == 新 lane 路由」。

对隔离库副本（apis 已迁移）逐行比对：
- 老口径：`device_type` 三值 → APISessionExecutor（http_api）/ RealtimeSessionExecutor
  （websocket_api），未知值回退会话执行器（INT-61 原实现）；
- 新口径：`lane_of(apis.streaming)` → 执行道 → 注册表取执行器；
- 协议推断：老口径「端点前缀 ws(s)→WEBSOCKET / 其余 HTTP」vs 新口径 `infer_protocol`
  只读 `apis.protocol` 列。
逐行相等即「迁移不改路由结论」，等价性覆盖全表而不是抽样。

用法：DATABASE_URL 指向 int1799_verify（apis 已迁移）。
"""
import os
import sys
from types import SimpleNamespace

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

assert os.environ.get('DATABASE_URL'), '必须由调用方注入 DATABASE_URL'

from shared.models.database import init_db, get_db_session  # noqa: E402

init_db()

from shared.models.common_enums import DeviceType, ExecutionLane, lane_of  # noqa: E402
from api_test_service.core.api_executor import APIExecutor  # noqa: E402
from api_test_service.infrastructure.adapters.registry import infer_protocol  # noqa: E402
from shared.models.common_enums import AdapterProtocol  # noqa: E402
from api_test_service.infrastructure.persistence.models.api_models import API  # noqa: E402
from api_test_service.domain.entities.api import resolve_api_endpoint  # noqa: E402


class _EngineStub:
    stop_flags = {}
    pause_flags = {}
    api_entry_lock = __import__('threading').Lock()
    api_entry_status = {}
    round_progress_cache = {}

    def _emit_progress(self, task_id, force=False):
        pass


def _old_executor_name(device_type):
    """INT-61 原口径（迁移前代码在 api_executor.route_executor 的映射 + 未知回退）。"""
    return 'realtime' if device_type == DeviceType.WEBSOCKET_API.value else 'session'


# 迁移映射的逆表：只有「streaming 与老 device_type 口径一致」的行才是迁移产物；
# 新代码建的行不再写 device_type（列废弃留默认），拿它当旧口径比较没有意义。
_LEGACY_LANE = {
    DeviceType.HTTP_API.value: False,
    DeviceType.WEBSOCKET_API.value: True,
}


def _new_executor_name(executor, streaming):
    inst = executor.route_executor(lane_of(streaming))
    if inst is executor._realtime_executor:
        return 'realtime'
    if inst is executor._session_executor:
        return 'session'
    raise AssertionError('未知执行器实例')


def _old_protocol(endpoint):
    """迁移前 infer_protocol 的端点前缀兜底（meta/case 级 protocol 主库 0 行使用）。"""
    if (endpoint or '').startswith(('ws://', 'wss://')):
        return AdapterProtocol.WEBSOCKET
    return AdapterProtocol.HTTP


def run():
    executor = APIExecutor(_EngineStub())
    session = get_db_session()
    rows = session.query(API).order_by(API.id).all()
    total = 0
    lane_mismatch = []
    proto_mismatch = []
    distribution = {}
    skipped = []
    for row in rows:
        if _LEGACY_LANE.get(row.device_type) != bool(row.streaming):
            # 迁移后由新代码建的行（device_type 不再维护，列退场后恒为默认值）
            skipped.append((row.id, row.device_type, row.protocol, bool(row.streaming)))
            continue
        total += 1
        old_ex = _old_executor_name(row.device_type)
        new_ex = _new_executor_name(executor, row.streaming)
        if old_ex != new_ex:
            lane_mismatch.append((row.id, row.device_type, row.protocol, row.streaming))
        endpoint = resolve_api_endpoint(SimpleNamespace(api_endpoints=row.api_endpoints or []))
        old_proto = _old_protocol(endpoint)
        new_proto = infer_protocol(SimpleNamespace(protocol=row.protocol))
        if old_proto is not new_proto:
            proto_mismatch.append((row.id, old_proto, new_proto, row.protocol))
        key = (row.device_type, row.protocol, bool(row.streaming), new_ex)
        distribution[key] = distribution.get(key, 0) + 1
    session.remove()

    print('扫描 %d 行；分布（device_type, protocol, streaming, 新执行器）:' % total)
    for key, cnt in sorted(distribution.items(), key=lambda kv: str(kv[0])):
        print('  %-40s %d 行' % (str(key), cnt))
    if skipped:
        print('跳过 %d 行（迁移后新代码建的行，device_type 已不维护）：%s'
              % (len(skipped), skipped[:5]))

    ok = True
    if lane_mismatch:
        ok = False
        print('[FAIL] 执行道路由不等价 %d 行（前 10）：%s' % (len(lane_mismatch), lane_mismatch[:10]))
    else:
        print('[PASS] 执行道路由逐行等价：老 device_type 口径 == 新 streaming 口径（%d 行）' % total)
    if proto_mismatch:
        ok = False
        print('[FAIL] 协议推断不等价 %d 行（前 10）：%s' % (len(proto_mismatch), proto_mismatch[:10]))
    else:
        print('[PASS] 协议推断逐行等价：老端点前缀口径 == 新 protocol 列（%d 行）' % total)

    print('\n===== SUMMARY %s =====' % ('PASS' if ok else 'FAIL'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(run())
