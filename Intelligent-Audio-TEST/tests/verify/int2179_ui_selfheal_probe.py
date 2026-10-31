# -*- coding: utf-8 -*-
"""INT-2179 补证：UI 抓取自愈实跑（不断后端服务，只断设备端 uitest 守护）。

步骤：
1. 记录设备端 uitest 守护现状（`hdc shell ps -ef` 过滤）
2. `hdc shell pkill -f uitest` 制造屏幕通道不可用（后端服务不动）
3. 调 device_service CreateDriver action=initialize（真实驱动 + 真实设备）
   —— 命中 `_get_driver_for_initialize → _connect_ui_driver(RPC 异常) →
   _recover_ui_rpc → restart_uitest_daemon + _reconnect_driver` 自愈链
4. 断言 initialize 成功且 ui_capture_available=true（未降级、未 300s 空等）
5. 确认守护已恢复；teardown 收尾

用法：PYTHONPATH=. python tests/verify/int2179_ui_selfheal_probe.py
"""
import json
import subprocess
import sys
import time

import grpc

DEVICE_ENDPOINT = '127.0.0.1:50053'
REAL_SN = '5SM0125701000448'
KEYWORDS = 'harmony.xiaoyi_livechat.v1'


def _hdc(*args, timeout=30):
    try:
        r = subprocess.run(['hdc', '-t', REAL_SN, 'shell', *args],
                           capture_output=True, text=True, timeout=timeout)
        return (r.stdout or '') + (r.stderr or '')
    except Exception as exc:  # noqa: BLE001
        return f'<hdc error: {exc}>'


def _daemon_alive():
    out = _hdc('ps', '-ef')
    return 'uitest' in out, out


def _call(pb, stub, action, kwargs=None, timeout=330):
    payload = {'action': action, 'device_sn': REAL_SN, 'system': 'HarmonyOS',
               'keywords': KEYWORDS, 'kwargs': kwargs or {}}
    began = time.time()
    resp = stub.CreateDriver(pb.CreateDriverRequest(
        task_id='999180', device_config=json.dumps(payload, ensure_ascii=False)),
        timeout=timeout)
    elapsed = time.time() - began
    try:
        data = json.loads(resp.data or '{}')
    except Exception:
        data = resp.data
    return resp, data, elapsed


def main():
    from shared.proto import device_service_pb2 as pb
    from shared.proto import device_service_pb2_grpc as pb_grpc

    channel = grpc.insecure_channel(DEVICE_ENDPOINT,
                                    options=[('grpc.max_receive_message_length', 16 * 1024 * 1024)])
    stub = pb_grpc.DeviceServiceStub(channel)
    try:
        before, _ = _daemon_alive()
        print(f'[before] uitest daemon alive={before}')

        kill_out = _hdc('pkill', '-f', 'uitest')
        time.sleep(1.5)
        after_kill, ps_out = _daemon_alive()
        print(f'[break] pkill -f uitest output={kill_out.strip()[:200]} '
              f'daemon_alive={after_kill}')
        print(f'[break] ps -ef tail={ps_out.strip()[-300:]}')

        resp, data, elapsed = _call(pb, stub, 'initialize')
        print(f'[initialize] elapsed={elapsed:.2f}s success={resp.success} '
              f'message={resp.message}')
        print('[initialize.data]', json.dumps(data, ensure_ascii=False)[:800])

        recovered, ps2 = _daemon_alive()
        print(f'[after] uitest daemon alive={recovered} ps tail={ps2.strip()[-300:]}')

        caps = data.get('ui_capabilities') or {} if isinstance(data, dict) else {}
        ok = (resp.success and data.get('driver_name') == 'Xiaoyilivechat'
              and caps.get('ui_capture_available') is True and recovered)
        _call(pb, stub, 'teardown', timeout=120)
        print('RESULT', 'PASS' if ok else 'FAIL')
        return 0 if ok else 1
    finally:
        channel.close()


if __name__ == '__main__':
    sys.exit(main())
