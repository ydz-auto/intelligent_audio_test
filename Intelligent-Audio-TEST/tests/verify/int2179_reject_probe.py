# -*- coding: utf-8 -*-
"""INT-2179 补证：小艺拒识轮驱动（INT-2146）真实设备试验步骤探针。

在宿主 device_service（50053）+ 真实在线设备上走安全步骤：
initialize(reject 关键词) → post_process 三种参数口径 → teardown，
用耗时与服务端返回证明：
- 路由：keywords=harmony.xiaoyi_livechat_reject.v1 选中 XiaoyiLivechatReject
- 参数透传：is_reject / timing / next_round_is_reject 原样进入驱动
- 行为：timing=silence（非打断、非连续拒识）走受限等待；timing=response
  （打断型）与 next_round_is_reject=true 不等待

驱动日志落在库内 logs 表（task_id=--task-id），可直接回读作为证据。

用法（宿主交付树，conda env intelligent_audio_test）：
    PYTHONPATH=. python tests/verify/int2179_reject_probe.py [--task-id 999179]
"""
import argparse
import json
import sys
import time

import grpc

DEVICE_ENDPOINT = '127.0.0.1:50053'
REAL_SN = '5SM0125701000448'
REJECT_KEYWORDS = 'harmony.xiaoyi_livechat_reject.v1'


def _client():
    from shared.proto import device_service_pb2 as pb
    from shared.proto import device_service_pb2_grpc as pb_grpc
    channel = grpc.insecure_channel(DEVICE_ENDPOINT,
                                    options=[('grpc.max_receive_message_length', 16 * 1024 * 1024)])
    return pb, pb_grpc.DeviceServiceStub(channel), channel


def _call(pb, stub, task_id, action, kwargs, timeout=340):
    payload = {
        'action': action,
        'device_sn': REAL_SN,
        'system': 'HarmonyOS',
        'keywords': REJECT_KEYWORDS,
        'kwargs': kwargs,
    }
    began = time.time()
    resp = stub.CreateDriver(pb.CreateDriverRequest(
        task_id=str(task_id),
        device_config=json.dumps(payload, ensure_ascii=False)), timeout=timeout)
    elapsed = time.time() - began
    data = {}
    try:
        data = json.loads(resp.data or '{}')
    except Exception:
        data = resp.data
    print(f'[{action}] elapsed={elapsed:.2f}s success={resp.success} message={resp.message}')
    print(f'[{action}.data]', json.dumps(data, ensure_ascii=False)[:1200])
    return {'action': action, 'elapsed': elapsed, 'success': resp.success,
            'message': resp.message, 'data': data}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--task-id', default='999179', help='日志落库用的探针任务号（bigint）')
    args = parser.parse_args()
    task_id = args.task_id

    pb, stub, channel = _client()
    results = []
    try:
        results.append(_call(pb, stub, task_id, 'initialize', {}))
        base = {'is_reject': True, 'record_mode': 'round',
                'total_rounds': 1, 'round_number': 1}
        results.append(_call(pb, stub, task_id, 'post_process',
                             dict(base, timing='silence', next_round_is_reject=False)))
        results.append(_call(pb, stub, task_id, 'post_process',
                             dict(base, timing='response', next_round_is_reject=False)))
        results.append(_call(pb, stub, task_id, 'post_process',
                             dict(base, timing='silence', next_round_is_reject=True)))
        results.append(_call(pb, stub, task_id, 'teardown', {}))
    finally:
        channel.close()

    init = results[0]
    ok_route = init['success'] and init['data'].get('driver_name') == 'XiaoyiLivechatReject'
    ok_exec = all(r['success'] for r in results if r['action'] == 'post_process')
    print('RESULT', 'PASS' if (ok_route and ok_exec) else 'FAIL')
    return 0 if (ok_route and ok_exec) else 1


if __name__ == '__main__':
    sys.exit(main())
