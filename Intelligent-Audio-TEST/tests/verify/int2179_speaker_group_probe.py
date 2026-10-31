# -*- coding: utf-8 -*-
"""INT-2179 补证：播放音箱分组（逻辑音箱）分辨率与派发口径探针。

对宿主 device_service（50053）的 PlaybackConfigService 走真实 gRPC：
- ListPlaybackDevices：取各实验室播放设备及在线状态
- ListPlaybackSpeakerGroups：组 + 各实验室成员（playback_device_id）
- ResolvePlaybackSpeakerGroupDevice(group, lab)：逐组核对「组→实验室成员」一一对应
- 空分组：临时建一个无成员的 接线测试_走查B3_ 组，resolve 应失败并给出原因，
  用完即删
- 离线成员：解析后的设备若 status=offline，记录 resolved 结果（用于说明
  「成员离线无后端提示/降级」是否成立）

只读为主；唯一写操作是临时组创建/删除（前缀 接线测试_走查B3_，finally 清理）。

用法：PYTHONPATH=. python tests/verify/int2179_speaker_group_probe.py
"""
import json
import sys

import grpc

DEVICE_ENDPOINT = '127.0.0.1:50053'
LAB_ID = 38
TEMP_GROUP_NAME = '接线测试_走查B3_音箱组'


def _stub():
    from shared.proto import device_service_pb2 as pb
    from shared.proto import device_service_pb2_grpc as pb_grpc
    channel = grpc.insecure_channel(DEVICE_ENDPOINT,
                                    options=[('grpc.max_receive_message_length', 16 * 1024 * 1024)])
    return pb, pb_grpc.PlaybackConfigServiceStub(channel), channel


def _loads(raw, default):
    try:
        return json.loads(raw or '')
    except Exception:
        return default


def main():
    pb, stub, channel = _stub()
    temp_group_id = None
    failures = []
    try:
        dev_resp = stub.ListPlaybackDevices(pb.ListPlaybackDevicesRequest(page=1, per_page=100))
        dev_data = _loads(dev_resp.data, [])
        if isinstance(dev_data, dict):
            dev_data = dev_data.get('items', [])
        devices = {int(d['id']): d for d in dev_data}
        print(f'[playback_devices] total={len(devices)}')

        grp_resp = stub.ListPlaybackSpeakerGroups(pb.ListPlaybackSpeakerGroupsRequest())
        groups = _loads(grp_resp.data, [])
        print(f'[speaker_groups] total={len(groups)}')

        checked = 0
        for group in groups:
            gid = int(group['id'])
            items = {int(i['lab_id']): int(i['playback_device_id'])
                     for i in group.get('items') or []}
            if LAB_ID not in items:
                print(f'[group {gid}] {group.get("name")} lab {LAB_ID} 无成员，跳过')
                continue
            resp = stub.ResolvePlaybackSpeakerGroupDevice(
                pb.ResolvePlaybackSpeakerGroupDeviceRequest(group_id=gid, target_lab_id=LAB_ID))
            resolved = _loads(resp.data, None)
            resolved_id = (resolved.get('target_device_id')
                           if isinstance(resolved, dict) else resolved)
            device = devices.get(int(resolved_id)) if resolved_id is not None else None
            status = device.get('status') if device else None
            ok = resp.success and int(resolved_id) == items[LAB_ID]
            checked += 1
            if not ok:
                failures.append(f'group {gid}: resolve={resolved_id} expected={items[LAB_ID]}')
            print(f'[group {gid}] {group.get("name")} member[lab {LAB_ID}]={items[LAB_ID]} '
                  f'resolve={resolved_id}({device.get("name") if device else None}) '
                  f'status={status} success={resp.success} ok={ok}')
        print(f'[one_to_one] checked={checked} mismatches={len(failures)}')

        # 空分组：创建 → 解析 → 删除
        create = stub.CreatePlaybackSpeakerGroup(pb.CreatePlaybackSpeakerGroupRequest(
            data=json.dumps({'name': TEMP_GROUP_NAME, 'description': 'INT-2179 走查临时'},
                            ensure_ascii=False)))
        created = _loads(create.data, {})
        temp_group_id = created.get('id') if isinstance(created, dict) else None
        print(f'[empty_group.create] success={create.success} message={create.message} id={temp_group_id}')
        if temp_group_id is not None:
            empty_resolve = stub.ResolvePlaybackSpeakerGroupDevice(
                pb.ResolvePlaybackSpeakerGroupDeviceRequest(
                    group_id=int(temp_group_id), target_lab_id=LAB_ID))
            print(f'[empty_group.resolve] success={empty_resolve.success} '
                  f'message={empty_resolve.message} data={empty_resolve.data}')
    finally:
        if temp_group_id is not None:
            try:
                dele = stub.DeletePlaybackSpeakerGroup(
                    pb.DeletePlaybackSpeakerGroupRequest(group_id=int(temp_group_id)))
                print(f'[empty_group.delete] success={dele.success} message={dele.message}')
            except Exception as exc:  # noqa: BLE001
                print('[empty_group.delete] 异常:', exc)
        channel.close()

    print('RESULT', 'PASS' if not failures else 'FAIL')
    return 0 if not failures else 1


if __name__ == '__main__':
    sys.exit(main())
