# -*- coding: utf-8 -*-
"""E2E 设备状态检查 Mixin（从 _task_runner_mixin.py 拆分，P4-4）。

包含 E2E 用例执行前的设备可用性检查：
- _check_e2e_devices：检查编排入口（被测设备 + 播放设备）
- _check_recording_devices：被测设备批量在线检查（含健康检查重试）
- _check_playback_devices：播放设备检查（含物理扫描重连）
"""
import logging

from task_service.infrastructure.persistence.models import TestCase

logger = logging.getLogger(__name__)


class DeviceCheckMixin:
    """E2E 设备状态检查：被测设备 / 播放设备在线性校验"""

    def _check_e2e_devices(self, task_id, task, tc_rel, local_db_session):
        """检查E2E设备状态 — 编排入口，分委托给子方法"""
        if task.type != 'e2e':
            return True, ""

        self._log(level='DEBUG', content=f"开始检查设备状态: 任务ID={task_id}, 用例ID={tc_rel.id}", task_id=task_id)

        # 检查被测设备
        device_ids = self._get_task_device_ids(task_id, local_db_session)
        passed, error_msg = self._check_recording_devices(task_id, device_ids, local_db_session)
        if not passed:
            return False, error_msg

        # 检查播放设备
        return self._check_playback_devices(task_id, tc_rel, local_db_session)

    def _get_task_device_ids(self, task_id, local_db_session):
        """获取任务关联的被测设备ID列表"""
        from task_service.infrastructure.persistence.models import TaskDevice
        relations = local_db_session.query(TaskDevice).filter_by(task_id=task_id).all()
        device_ids = [rel.device_id for rel in relations]
        self._log(level='DEBUG', content=f"设备关联信息: 关联数={len(relations)}, 设备ID列表={device_ids}", task_id=task_id)
        return device_ids

    def _check_recording_devices(self, task_id, device_ids, local_db_session):
        """通过 gRPC 批量检查被测设备在线状态，离线时健康检查"""
        if not device_ids:
            self._log(level='DEBUG', content="没有关联设备，设备检查通过", task_id=task_id)
            return True, ""

        devices = self._fetch_device_statuses(task_id, device_ids)
        for device in devices:
            if device.get('status') == 'online':
                continue
            # 离线设备尝试健康检查
            if self._health_check_device(task_id, device):
                continue
            return False, f"被测设备 {device.get('name')} 离线，无法执行测试"
        return True, ""

    def _fetch_device_statuses(self, task_id, device_ids):
        """通过 gRPC 批量获取被测设备状态"""
        try:
            import json as _json
            from shared.clients.grpc_clients import get_device_config_service_stub
            from shared.proto import device_service_pb2 as e2e_pb
            from shared.utils.grpc_json import loads as _loads
            stub = get_device_config_service_stub()
            resp = stub.GetDeviceStatuses(e2e_pb.GetDeviceStatusesRequest(data=_json.dumps({'ids': device_ids})))
            if resp.success and resp.data:
                payload = _loads(resp.data, {})
                return payload.get('items', []) if isinstance(payload, dict) else []
        except Exception as grpc_e:
            self._log(level='ERROR', content=f"通过 gRPC 获取设备状态失败: {str(grpc_e)}", task_id=task_id)
        return []

    def _health_check_device(self, task_id, device):
        """通过 gRPC 健康检查重新检测离线设备是否恢复"""
        try:
            import json as _json
            from shared.clients.grpc_clients import get_device_config_service_stub
            from shared.proto import device_service_pb2 as _dev_pb
            from shared.utils.grpc_json import loads as _loads
            stub = get_device_config_service_stub()
            resp = stub.HealthCheckDevices(_dev_pb.HealthCheckDevicesRequest(
                data=_json.dumps({'device_ids': [device.get('id')]})))
            if resp.success and resp.data:
                result = _loads(resp.data, [])
                if isinstance(result, list):
                    item = next((d for d in result if d.get('id') == device.get('id')), None)
                    if item and item.get('status') == 'online':
                        self._log(level='INFO', content=f"被测设备 {device.get('name')} 重新检测为在线",
                                  task_id=task_id, device_id=device.get('id'))
                        return True
        except Exception as e:
            self._log(level='WARNING', content=f"被测设备 {device.get('name')} 健康检查失败: {e}",
                      task_id=task_id, device_id=device.get('id'))
        return False

    def _check_playback_devices(self, task_id, tc_rel, local_db_session):
        """检查E2E用例中配置的播放设备是否在线"""
        self._log(level='DEBUG', content="开始检查播放设备状态", task_id=task_id)
        case = local_db_session.get(TestCase, tc_rel.test_case_id)
        if not case:
            self._log(level='DEBUG', content=f"未找到测试用例: {tc_rel.test_case_id}", task_id=task_id)
            return True, ""

        playback_ids = self._extract_playback_device_ids(task_id, case)
        for device_id in playback_ids:
            passed, error_msg = self._check_single_playback_device(task_id, device_id)
            if not passed:
                return False, error_msg
        return True, ""

    def _extract_playback_device_ids(self, task_id, case):
        """从用例配置中提取播放设备ID集合"""
        config = case.config or {}
        rounds = config.get('rounds', []) if isinstance(config, dict) else []
        audios = []
        for round_item in rounds:
            if isinstance(round_item, dict):
                round_audios = round_item.get('audios', [])
                if isinstance(round_audios, list):
                    audios.extend(round_audios)
        self._log(level='DEBUG', content=f"E2E用例配置: 音频数量={len(audios)}", task_id=task_id)

        playback_ids = set()
        for audio in audios:
            pb_dev_id = audio.get('playback_device_id')
            if pb_dev_id:
                playback_ids.add(pb_dev_id)
        self._log(level='DEBUG', content=f"播放设备ID集合: {playback_ids}", task_id=task_id)
        return playback_ids

    def _check_single_playback_device(self, task_id, device_id):
        """检查单个播放设备状态，离线时扫描物理设备"""
        playback_dev = self._fetch_playback_device(task_id, device_id)
        if not playback_dev:
            return False, f"找不到播放设备，ID: {device_id}"

        pb_status = playback_dev.get('status')
        self._log(level='DEBUG', content=f"检查播放设备: 设备ID={device_id}, 名称={playback_dev.get('name')}, 状态={pb_status}",
                  task_id=task_id)
        if pb_status == 'online':
            return True, ""

        # 数据库标记离线，尝试扫描物理设备
        return self._recheck_playback_device(task_id, playback_dev, device_id)

    def _fetch_playback_device(self, task_id, device_id):
        """通过 gRPC 获取单个播放设备信息"""
        try:
            from shared.clients.grpc_clients import get_playback_config_service_stub
            from shared.proto import device_service_pb2 as e2e_pb
            from shared.utils.grpc_json import loads as _loads
            stub = get_playback_config_service_stub()
            resp = stub.GetPlaybackDevice(e2e_pb.GetPlaybackDeviceRequest(device_id=int(device_id)))
            if resp.success and resp.data:
                return _loads(resp.data, {})
        except Exception as grpc_e:
            self._log(level='ERROR', content=f"通过 gRPC 获取播放设备失败 (id={device_id}): {str(grpc_e)}", task_id=task_id)
        return None

    def _recheck_playback_device(self, task_id, playback_dev, device_id):
        """扫描物理设备，若在线则更新数据库状态"""
        dev_name = playback_dev.get('name')
        try:
            from shared.clients.grpc_clients import get_playback_config_service_stub
            from shared.proto import device_service_pb2 as _pb
            import json as _json
            stub = get_playback_config_service_stub()
            scan_resp = stub.ScanPlaybackDevices(_pb.ScanPlaybackDevicesRequest())
            if scan_resp.success:
                scanned = _json.loads(scan_resp.data) if scan_resp.data else []
                unique_id = playback_dev.get('device_unique_id', '')
                ch_idx = playback_dev.get('channel_index', 0)
                phys_found = any(
                    d.get('unique_id') == unique_id and d.get('channel_index') == ch_idx
                    for d in scanned
                )
                if phys_found:
                    stub.UpdatePlaybackDevice(_pb.UpdatePlaybackDeviceRequest(
                        device_id=int(device_id), data=_json.dumps({'status': 'online'})))
                    self._log(level='INFO', content=f"播放设备 {dev_name} 物理设备已重新连接，状态更新为 online", task_id=task_id)
                    return True, ""
                else:
                    msg = f"播放设备 {dev_name} 离线且物理设备未检测到，无法执行测试"
                    self._log(level='ERROR', content=msg, task_id=task_id)
                    return False, msg
        except Exception as recheck_e:
            self._log(level='WARNING',
                      content=f"播放设备 {dev_name} 物理设备重新检测失败: {recheck_e}，跳过检查继续执行", task_id=task_id)
            return True, ""
