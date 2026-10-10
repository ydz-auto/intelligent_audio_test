# -*- coding: utf-8 -*-
"""实例间亲和转发 —— 把绑定在其它存活实例的请求直达持有实例（INT-61，架构设计 §5.2）

双副本部署下请求可能落到无会话副本：启动/停止/状态三类 API 测试请求
在本地处理前先经 RealtimeSessionRegistry.resolve 门禁，绑定指向其它
存活实例时经此模块转发到持有实例（host:grpc_port 直连，绕过服务名负载均衡）。

转发不可达（持有实例恰在门禁后崩溃）返回 None，由调用方降级本地处理
（resolve 的失联重路由语义随后收敛绑定）。
"""
import json
import logging
import time

from shared.utils.realtime_session_registry import get_instance_target

logger = logging.getLogger(__name__)

# 启动转发的进程内去重窗（秒）：绑定在两副本间罕见抖动时封顶转发跳数，
# 防止 A↔B 互转死循环；窗口内的重复转发降级为本地执行，由 _running_tasks
# 幂等守卫兜底
FORWARD_DEDUP_WINDOW_SECONDS = 10

_recent_start_forwards = {}


def _start_forward_recent(task_id):
    """本进程近窗内已转发过该 task 的启动请求则返回 True（并记录本次）"""
    now = time.monotonic()
    expired = [k for k, v in _recent_start_forwards.items() if v <= now]
    for k in expired:
        _recent_start_forwards.pop(k, None)
    last = _recent_start_forwards.get(task_id)
    _recent_start_forwards[task_id] = now + FORWARD_DEDUP_WINDOW_SECONDS
    return last is not None


def _resolve_target(instance_id):
    return get_instance_target(instance_id=instance_id)


def _call_peer(target, rpc_name, request):
    """直连持有实例调用 RPC，返回解析后的 result dict；不可达返回 None"""
    try:
        from shared.clients.grpc_instance_client import get_api_test_service_stub_for_instance
        stub = get_api_test_service_stub_for_instance(target['host'], target['grpc_port'])
        resp = getattr(stub, rpc_name)(request)
        result = json.loads(resp.data) if resp.data else {}
        result['success'] = resp.success
        result['message'] = resp.message
        return result
    except Exception as e:
        logger.warning(f"亲和转发 {rpc_name} 到 {target.get('instance_id')} 失败: {e}")
        return None


def forward_create_api_test(task_id, case_ids, api_ids, instance_id):
    """转发创建/启动 API 测试到持有实例

    Returns:
        dict = 持有实例响应（已转发）；None = 不可达或近窗已转发（调用方降级本地）
    """
    target = _resolve_target(instance_id)
    if target is None:
        return None
    if _start_forward_recent(task_id):
        return None
    from shared.utils.grpc_json import dumps as _dumps
    from shared.proto import api_test_service_pb2 as api_pb
    request = api_pb.CreateAPITestRequest(
        task_id=str(task_id),
        test_config=_dumps({'case_ids': list(case_ids or []), 'api_ids': list(api_ids or [])}),
    )
    logger.info(f"会话亲和转发 CreateAPITest task={task_id} -> {target['instance_id']}")
    return _call_peer(target, 'CreateAPITest', request)


def forward_stop_api_test(task_id, instance_id):
    """转发停止 API 测试到持有实例；None = 不可达（调用方降级本地）"""
    target = _resolve_target(instance_id)
    if target is None:
        return None
    from shared.proto import api_test_service_pb2 as api_pb
    logger.info(f"会话亲和转发 StopAPITest task={task_id} -> {target['instance_id']}")
    return _call_peer(target, 'StopAPITest', api_pb.StopAPITestRequest(task_id=str(task_id)))


def forward_get_api_test_status(task_id, instance_id):
    """转发状态查询到持有实例；None = 不可达（调用方降级本地）"""
    target = _resolve_target(instance_id)
    if target is None:
        return None
    from shared.proto import api_test_service_pb2 as api_pb
    return _call_peer(target, 'GetAPITestStatus',
                      api_pb.GetAPITestStatusRequest(task_id=str(task_id)))
