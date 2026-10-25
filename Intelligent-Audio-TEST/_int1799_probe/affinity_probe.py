# -*- coding: utf-8 -*-
"""INT-1799 跨服务接线回环取证：真 gRPC server（本卡 servicer）+ 真 ACL 客户端。

链路：task_service.infrastructure.acl.api_acl_repository.get_api_streaming_flags
      → gRPC GetAPIConfig（protobuf 序列化）→ api_test_service servicer
      → APICrudService.get_one（读 apis.protocol / apis.streaming 列）
      → task_service 亲和域令牌派生 resolve_api_affinity_token

以及网关侧链路：ListAPIConfigs 的新 proto 字段 protocol / streaming 经线上序列化
后再到仓储 WHERE 过滤。

用法：DATABASE_URL 指向 int1799_verify（隔离库副本，apis 已迁移）。
"""
import json
import os
import sys
from concurrent import futures

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

assert os.environ.get('DATABASE_URL'), '必须由调用方注入 DATABASE_URL'

import grpc  # noqa: E402

from shared.models.database import init_db  # noqa: E402

init_db()

from shared.proto import api_test_service_pb2 as api_pb  # noqa: E402
from shared.proto import api_test_service_pb2_grpc as api_grpc  # noqa: E402
from api_test_service.interfaces.grpc.servicers import APITestServiceServicer  # noqa: E402
from api_test_service.application import api_crud_service as mod  # noqa: E402
from api_test_service.application.api_crud_service import APICrudService  # noqa: E402

mod.APICrudService._publish_config_changed = staticmethod(lambda *a, **k: None)
mod.refresh_stats_cache = lambda: None

RESULTS = []


def _rec(name, ok, detail):
    RESULTS.append((name, ok, detail))
    print(('[PASS] ' if ok else '[FAIL] ') + name + ' :: ' + detail)


def _start_server():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    api_grpc.add_APITestServiceServicer_to_server(APITestServiceServicer(), server)
    port = server.add_insecure_port('127.0.0.1:0')
    server.start()
    channel = grpc.insecure_channel('127.0.0.1:%d' % port)
    grpc.channel_ready_future(channel).result(timeout=15)
    return server, channel, port


def run():
    server, channel, port = _start_server()
    print('loopback gRPC server on 127.0.0.1:%d' % port)

    # 让 ACL 客户端打到本回环 server（真客户端 + 真 servicer + 真 protobuf）
    import shared.clients.grpc_clients as clients_mod
    clients_mod.get_api_test_service_stub = lambda *a, **k: api_grpc.APITestServiceStub(channel)

    ws = APICrudService.create({'name': 'int1799-rt', 'meta': {},
                                'protocol': 'websocket', 'streaming': True})
    http = APICrudService.create({'name': 'int1799-http', 'meta': {},
                                  'protocol': 'http', 'streaming': False})
    ws_id, http_id = ws['data']['id'], http['data']['id']
    _rec('setup_two_apis', ws['code'] == 201 and http['code'] == 201,
         f"ws_id={ws_id} http_id={http_id}")

    # ① 单 API：令牌按 streaming 派生
    from task_service.infrastructure.persistence._task_crud_mixin import (
        ExecutionAffinityError, resolve_api_affinity_token)
    _rec('affinity_streaming_api', resolve_api_affinity_token([ws_id]) == 'websocket_api',
         'streaming=true → websocket_api')
    _rec('affinity_non_streaming_api', resolve_api_affinity_token([http_id]) == 'http_api',
         'streaming=false → http_api')

    # ② 混道 → 显式拒绝（任务创建 400 的来源）
    try:
        resolve_api_affinity_token([ws_id, http_id])
        _rec('affinity_mixed_rejected', False, '未抛错（应拒绝混道）')
    except ExecutionAffinityError as e:
        _rec('affinity_mixed_rejected', '流式性不一致' in str(e), str(e))

    # ③ 取不到 API（软删后 GetAPIConfig 失败）→ 拒绝，不猜 http_api
    APICrudService.delete(ws_id)
    try:
        token = resolve_api_affinity_token([ws_id])
        _rec('affinity_missing_api_rejected', False, f'未抛错，回落成 {token}')
    except ExecutionAffinityError as e:
        _rec('affinity_missing_api_rejected', '取不到' in str(e), str(e))

    # ④ 列表筛选经线上 proto 新字段透传
    stub = api_grpc.APITestServiceStub(channel)
    resp = stub.ListAPIConfigs(api_pb.ListAPIConfigsRequest(
        page=1, per_page=500, protocol='http', streaming='false'))
    data = json.loads(resp.data or '{}')
    items = data.get('items') or []
    _rec('grpc_list_filter_true_wire',
         resp.success and items and all(
             i.get('protocol') == 'http' and i.get('streaming') is False for i in items),
         f"success={resp.success} total={data.get('total')} 首行={items[0].get('protocol') if items else None}/"
         f"{items[0].get('streaming') if items else None}")

    bad = stub.ListAPIConfigs(api_pb.ListAPIConfigsRequest(
        page=1, per_page=10, streaming='maybe'))
    _rec('grpc_list_bad_streaming_rejected', not bad.success and 'streaming' in bad.message,
         f"success={bad.success} msg={bad.message}")

    # ⑤ 详情 JSON 里确实带 streaming 键（ACL 依赖该键，缺键即 400）
    one = stub.GetAPIConfig(api_pb.GetAPIConfigRequest(api_id=http_id))
    payload = json.loads(one.data or '{}')
    _rec('grpc_get_api_has_streaming_key',
         one.success and 'streaming' in payload and 'device_type' not in payload,
         f"keys={sorted(k for k in payload if k in ('protocol', 'streaming', 'device_type'))}")

    for api_id in (ws_id, http_id):
        APICrudService.delete(api_id)

    channel.close()
    server.stop(0).wait(timeout=5)

    failed = [n for n, ok, _ in RESULTS if not ok]
    total = len(RESULTS)
    print('\n===== SUMMARY %d/%d passed =====' % (total - len(failed), total))
    if failed:
        print('FAILED: ' + ', '.join(failed))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(run())
