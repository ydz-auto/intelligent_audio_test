# -*- coding: utf-8 -*-
"""INT-2179 补证：设备侧驱动定位 / 小艺拒识轮驱动接口级探针（宿主机 device_service）。

只调 device_service 的只读查询 + 安全生命周期动作：
- GetRegisteredKeywords：拒识驱动关键词是否登记
- GetDriverNameByKeywords：同 SN 不同 App 关键词 → 精确选中不同驱动
- DriverScan：真实在线设备清单
- （可选 --initialize）CreateDriver action=initialize/teardown：抓设备侧真实
  初始化结果（成功或失败原文），用于「设备侧未覆盖」的替代证据

用法（宿主交付树，conda env intelligent_audio_test）：
    PYTHONPATH=. python tests/verify/int2179_device_probe.py [--initialize]
"""
import argparse
import json
import sys

import grpc

DEVICE_ENDPOINT = '127.0.0.1:50053'
REAL_SN = '5SM0125701000448'  # devices.id=232，HarmonyOS 新机，在线


def _client():
    from shared.proto import device_service_pb2 as pb
    from shared.proto import device_service_pb2_grpc as pb_grpc
    channel = grpc.insecure_channel(DEVICE_ENDPOINT,
                                    options=[('grpc.max_receive_message_length', 16 * 1024 * 1024)])
    return pb, pb_grpc.DeviceServiceStub(channel), channel


def _json(raw):
    try:
        return json.loads(raw or '{}')
    except Exception:
        return raw


def probe_keywords(pb, stub):
    resp = stub.GetRegisteredKeywords(pb.GetRegisteredKeywordsRequest())
    data = _json(resp.data)
    keywords = data.get('keywords', data) if isinstance(data, dict) else data
    print('[registered_keywords]', json.dumps(keywords, ensure_ascii=False))

    results = {}
    for kw in ('harmony.xiaoyi_livechat.v1', 'harmony.doubao.v1',
               'harmony.chatgpt.v1', 'harmony.xiaoyi_livechat_reject.v1',
               'harmony.unknown_app.v1'):
        r = stub.GetDriverNameByKeywords(pb.GetDriverNameByKeywordsRequest(
            system='HarmonyOS', keywords=kw))
        results[kw] = {'success': r.success, 'message': r.message,
                       'data': _json(r.data)}
        print(f'[driver_by_keywords] {kw} -> {json.dumps(results[kw], ensure_ascii=False)}')
    return results


def probe_scan(pb, stub):
    resp = stub.DriverScan(pb.DriverScanRequest(system='HarmonyOS'))
    data = _json(resp.data)
    print('[scan] success=%s message=%s devices=%s' %
          (resp.success, resp.message, json.dumps(data, ensure_ascii=False)[:2000]))
    return data


def probe_initialize(pb, stub, keywords, task_id):
    payload = {
        'action': 'initialize',
        'device_sn': REAL_SN,
        'system': 'HarmonyOS',
        'keywords': keywords,
        'test_case_id': None,
        'kwargs': {},
    }
    resp = stub.CreateDriver(pb.CreateDriverRequest(
        task_id=task_id,
        device_config=json.dumps(payload, ensure_ascii=False)), timeout=330)
    info = _json(resp.data)
    print(f'[initialize] {keywords} success={resp.success} message={resp.message} '
          f'driver={info.get("driver_name") if isinstance(info, dict) else info}')
    print('[initialize.data]', json.dumps(info, ensure_ascii=False)[:2000])
    try:
        stub.CreateDriver(pb.CreateDriverRequest(
            task_id=task_id,
            device_config=json.dumps({'action': 'teardown', 'device_sn': REAL_SN,
                                      'system': 'HarmonyOS', 'keywords': keywords},
                                     ensure_ascii=False)), timeout=120)
    except Exception as exc:  # noqa: BLE001
        print('[teardown] 忽略异常:', exc)
    return {'success': resp.success, 'message': resp.message, 'data': info}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--initialize', action='store_true',
                        help='对真实在线设备执行 initialize/teardown（安全动作）')
    parser.add_argument('--keywords', default='harmony.xiaoyi_livechat.v1',
                        help='--initialize 时使用的关键词（逗号分隔可多次）')
    args = parser.parse_args()

    pb, stub, channel = _client()
    try:
        keywords = probe_keywords(pb, stub)
        probe_scan(pb, stub)
        if args.initialize:
            for idx, kw in enumerate(args.keywords.split(',')):
                probe_initialize(pb, stub, kw.strip(), f'int2179-probe-{idx}')
        ok = keywords.get('harmony.xiaoyi_livechat_reject.v1', {}).get('success') is True
        print('RESULT', 'PASS' if ok else 'FAIL')
        return 0 if ok else 1
    finally:
        channel.close()


if __name__ == '__main__':
    sys.exit(main())
