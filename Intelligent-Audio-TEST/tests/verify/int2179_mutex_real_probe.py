# -*- coding: utf-8 -*-
"""INT-2179 补证：同 SN 步骤互斥的真实服务实测（宿主 device_service）。

两个线程同时向同一 SN 发 initialize（真实设备、真实驱动），另发一个 register
（非硬件动作）作为对照：
- 同 SN 两个 initialize 必须串行：第二个的完成时间晚于第一个的开始+耗时
- register 不受同 SN 步骤锁影响，立即返回

输出为每个请求的 [start, end] 墙钟时间，作为锁生效的外部证据。

用法：PYTHONPATH=. python tests/verify/int2179_mutex_real_probe.py
"""
import json
import sys
import threading
import time

import grpc

DEVICE_ENDPOINT = '127.0.0.1:50053'
REAL_SN = '5SM0125701000448'
KEYWORDS = 'harmony.xiaoyi_livechat.v1'
TASK_ID = '999181'


def _request(pb, action, device_sn, keywords=KEYWORDS, **extra):
    payload = {'action': action, 'device_sn': device_sn, 'system': 'HarmonyOS',
               'keywords': keywords}
    payload.update(extra)
    return pb.CreateDriverRequest(task_id=TASK_ID,
                                  device_config=json.dumps(payload, ensure_ascii=False))


def _run(stub, request, tag, out):
    box = {}
    began = time.time()
    try:
        resp = stub.CreateDriver(request, timeout=330)
        try:
            data = json.loads(resp.data or '{}')
        except Exception:
            data = {}
        box = {'tag': tag, 'start': began, 'end': time.time(),
               'success': resp.success, 'message': resp.message,
               'driver_name': data.get('driver_name') if isinstance(data, dict) else None}
    except Exception as exc:  # noqa: BLE001
        box = {'tag': tag, 'start': began, 'end': time.time(),
               'success': False, 'message': f'{type(exc).__name__}: {exc}',
               'driver_name': None}
    out[tag] = box


def main():
    from shared.proto import device_service_pb2 as pb
    from shared.proto import device_service_pb2_grpc as pb_grpc

    kw1 = sys.argv[1] if len(sys.argv) > 1 else KEYWORDS
    kw2 = sys.argv[2] if len(sys.argv) > 2 else KEYWORDS

    channel = grpc.insecure_channel(DEVICE_ENDPOINT,
                                    options=[('grpc.max_receive_message_length', 16 * 1024 * 1024)])
    stub = pb_grpc.DeviceServiceStub(channel)
    out = {}
    try:
        t1 = threading.Thread(target=_run, args=(
            stub, _request(pb, 'initialize', REAL_SN, kw1), 'init-1', out))
        t1.start()
        time.sleep(3)
        t2 = threading.Thread(target=_run, args=(
            stub, _request(pb, 'initialize', REAL_SN, kw2), 'init-2', out))
        t2.start()
        time.sleep(0.5)
        t3 = threading.Thread(target=_run, args=(
            stub, _request(pb, 'register', REAL_SN, kw1,
                           device_info_list=[{'device_sn': REAL_SN}]),
            'register', out))
        t3.start()
        for t in (t1, t2, t3):
            t.join(timeout=400)

        for tag in ('init-1', 'init-2', 'register'):
            r = out.get(tag, {})
            if r:
                print(f'[{tag}] start={r["start"]:.2f} end={r["end"]:.2f} '
                      f'dur={r["end"] - r["start"]:.2f}s success={r["success"]} '
                      f'driver={r.get("driver_name")} message={r["message"][:100]}')
        try:
            stub.CreateDriver(_request(pb, 'teardown', REAL_SN, kw1), timeout=120)
        except Exception:
            pass

        i1, i2, reg = out.get('init-1'), out.get('init-2'), out.get('register')
        # 串行判据：两个 initialize 自身耗时相近；后到者的额外耗时 ≈ 它等锁的时间。
        # waited = init-2 总耗时 - 自身工作量(以 init-1 耗时估算) 必须显著 > 0。
        waited = None
        if i1 and i2:
            waited = (i2['end'] - i2['start']) - (i1['end'] - i1['start'])
        serialized = waited is not None and waited >= 20
        ok = bool(i1 and i2 and reg
                  and i1['success'] and i2['success'] and reg['success']
                  and serialized
                  and (reg['end'] - reg['start']) < 2.0)
        print(f'[serialize] init-1.dur={i1["end"] - i1["start"]:.2f}s '
              f'init-2.dur={i2["end"] - i2["start"]:.2f}s '
              f'waited≈{waited:.2f}s serialized={serialized}')
        print('[control] register（非硬件动作）耗时应 <2s:', bool(reg and (reg['end'] - reg['start']) < 2.0))
        print('RESULT', 'PASS' if ok else 'FAIL')
        return 0 if ok else 1
    finally:
        channel.close()


if __name__ == '__main__':
    sys.exit(main())
