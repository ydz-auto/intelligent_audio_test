# -*- coding: utf-8 -*-
"""INT-2179 补证：用逻辑音箱（播放音箱分组）分辨率发起一次真实播放。

流程（全部走宿主常驻服务 gRPC）：
1. PlaybackConfigService.ListPlaybackSpeakerGroups / ResolvePlaybackSpeakerGroupDevice
   → 组在实验室 38 的成员播放设备（一一对应）
2. AudioService.GetDeviceIndex(device_unique_id) → 物理通道索引
3. AudioService.PlayAudio 播放一段 1.6s 测试音频 → GetPlayStatus → StopAudio
   （真实出声，验证「分组 → 实体设备 → 实际播放」链路）
4. 另取一个 status=offline 的组成员做同样解析，记录解析/播放是否被离线状态拦截
   （用于「成员离线提示/降级」口径）

用法：PYTHONPATH=. python tests/verify/int2179_group_playback_probe.py
"""
import json
import sys
import time

import grpc

DEVICE_ENDPOINT = '127.0.0.1:50053'
AUDIO_ENDPOINT = '127.0.0.1:50052'
LAB_ID = 38
AUDIO_ID = 2100
AUDIO_PATH = 'D:/00_static/static/audios/环境理解/环境理解/单一环境识别-无语义/HJ050_单一环境声音识别-无语义_枪声_女_silence_用户.wav'
PROBE_TASK_ID = 'int2179-probe-play'


def _loads(raw, default):
    try:
        return json.loads(raw or '')
    except Exception:
        return default


def main():
    from shared.proto import device_service_pb2 as dpb
    from shared.proto import device_service_pb2_grpc as dgrpc
    from shared.proto import audio_service_pb2 as apb
    from shared.proto import audio_service_pb2_grpc as agrpc

    dch = grpc.insecure_channel(DEVICE_ENDPOINT)
    ach = grpc.insecure_channel(AUDIO_ENDPOINT)
    dstub = dgrpc.PlaybackConfigServiceStub(dch)
    astub = agrpc.AudioServiceStub(ach)
    results = {}
    try:
        devs = _loads(dstub.ListPlaybackDevices(dpb.ListPlaybackDevicesRequest(page=1, per_page=100)).data, [])
        if isinstance(devs, dict):
            devs = devs.get('items', [])
        by_id = {int(d['id']): d for d in devs}
        groups = _loads(dstub.ListPlaybackSpeakerGroups(
            dpb.ListPlaybackSpeakerGroupsRequest()).data, [])

        online_group = offline_group = None
        for group in groups:
            for item in group.get('items') or []:
                if int(item['lab_id']) != LAB_ID:
                    continue
                dev = by_id.get(int(item['playback_device_id']))
                if not dev:
                    continue
                if dev.get('status') == 'online' and online_group is None:
                    online_group = (group, dev)
                if dev.get('status') == 'offline' and offline_group is None:
                    offline_group = (group, dev)

        for label, pick in (('online', online_group), ('offline', offline_group)):
            if pick is None:
                print(f'[{label}] 未找到该状态的组成员')
                results[label] = None
                continue
            group, dev = pick
            gid = int(group['id'])
            resolve = dstub.ResolvePlaybackSpeakerGroupDevice(
                dpb.ResolvePlaybackSpeakerGroupDeviceRequest(group_id=gid, target_lab_id=LAB_ID))
            resolved_id = _loads(resolve.data, {}).get('target_device_id')
            print(f'[{label}] group={gid}({group.get("name")}) member_device={dev["id"]} '
                  f'({dev.get("name")}) status={dev.get("status")} '
                  f'resolve={resolved_id} success={resolve.success}')
            idx = astub.GetDeviceIndex(apb.GetDeviceIndexRequest(
                unique_id=dev.get('device_unique_id') or ''))
            device_index = _loads(idx.data, {}).get('device_index')
            print(f'[{label}] GetDeviceIndex unique_id={dev.get("device_unique_id")!r} '
                  f'success={idx.success} device_index={device_index}')
            results[label] = {'group_id': gid, 'device_id': dev['id'],
                              'resolved': resolved_id, 'device_index': device_index,
                              'status': dev.get('status')}

            if label == 'online' and device_index is not None:
                cfg = {'file_path': AUDIO_PATH, 'device_index': device_index,
                       'channel_index': dev.get('channel_index', 0), 'gain': 1.0,
                       'loop': False, 'player_type': 'dry', 'offset': 0, 'kwargs': {}}
                play = astub.PlayAudio(apb.PlayAudioRequest(
                    task_id=PROBE_TASK_ID,
                    audio_file_paths=json.dumps([AUDIO_PATH], ensure_ascii=False),
                    play_config=json.dumps(cfg, ensure_ascii=False)))
                print(f'[online.play] success={play.success} message={play.message} '
                      f'data={play.data[:300]}')
                results[label]['play'] = {'success': play.success,
                                          'message': play.message}
                time.sleep(2.5)
                status = astub.GetPlayStatus(apb.GetPlayStatusRequest(task_id=PROBE_TASK_ID))
                print(f'[online.play_status] success={status.success} data={status.data[:300]}')
                stop = astub.StopAudio(apb.StopAudioRequest(task_id=PROBE_TASK_ID))
                print(f'[online.stop] success={stop.success} message={stop.message}')
    finally:
        dch.close()
        ach.close()

    online_ok = bool(results.get('online') and results['online'].get('resolved') == results['online']['device_id']
                     and results['online'].get('play', {}).get('success'))
    print('[summary]', json.dumps(results, ensure_ascii=False))
    print('RESULT', 'PASS' if online_ok else 'FAIL')
    return 0 if online_ok else 1


if __name__ == '__main__':
    sys.exit(main())
