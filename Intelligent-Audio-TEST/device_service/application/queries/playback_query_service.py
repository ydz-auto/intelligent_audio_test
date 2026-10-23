# -*- coding: utf-8 -*-
"""播放设备 Query 应用服务（读侧）

CQRS 拆分后的纯读操作服务，包含 get_all/get_one/scan。
- scan 仅读取物理设备列表并与已注册设备做差集，不更新设备状态，故归 query 侧。
- 方法签名和实现与原 playback_crud_service 完全一致。
"""
import logging

from shared.models.common_enums import (
    PlaybackDiagnosisKey,
    PlaybackDiagnosisStatus,
)
from shared.utils.query_utils import now_cst
from device_service.domain.repositories import PlaybackRepositoryInterface, SPLRepositoryInterface
from device_service.application.services.playback_channel_probe import (
    channel_capacity,
    match_physical_channel,
)

logger = logging.getLogger(__name__)

# 诊断项固定 6 项（契约 §2.5：不得臆造后端没有的能力）
_DIAGNOSIS_LABELS = {
    PlaybackDiagnosisKey.ENUMERABLE.value: '物理设备可枚举',
    PlaybackDiagnosisKey.CHANNEL_INDEX.value: '通道索引',
    PlaybackDiagnosisKey.SAMPLE_RATE.value: '采样率',
    PlaybackDiagnosisKey.SPL_MAPPING.value: '声压映射关联',
    PlaybackDiagnosisKey.STATUS.value: '设备在线状态',
    PlaybackDiagnosisKey.BUSY.value: '测试占用',
}
# 硬件枚举不可用（gRPC 失败 / success=false）时的统一文案（返回 unsupported，不制造噪声告警）
_UNSUPPORTED_DETAIL = '音频服务不可用，无法枚举物理设备'
_UNSUPPORTED_SUGGESTION = '检查 audio_service 是否运行后重新诊断'
# 枚举可用、但结果里没有这台设备：不能归因到音频服务，避免把用户引向错误处置
_MISSING_DETAIL = '未在物理设备枚举中找到该设备'
_MISSING_SUGGESTION = '检查设备电源与连接线后执行「重启」重新枚举'
# 枚举到了设备、但硬件未给出该字段：无法判定，不等于故障
_UNDETERMINED_SUGGESTION = '执行「重启」重新枚举物理设备后重新诊断'


class PlaybackQueryService:
    """播放设备 Query 应用服务（读侧）"""

    def __init__(self, repo: PlaybackRepositoryInterface = None, spl_repo: SPLRepositoryInterface = None):
        if repo is None:
            from device_service.infrastructure.persistence.device_repository import playback_repository
            repo = playback_repository
        if spl_repo is None:
            from device_service.infrastructure.persistence.device_repository import spl_repository
            spl_repo = spl_repository
        self.repo = repo
        self.spl_repo = spl_repo

    @staticmethod
    def _get_physical_devices_via_grpc():
        """通过 ACL 仓储获取物理设备列表"""
        from device_service.infrastructure.acl.audio_service_acl_repository import audio_service_acl_repository
        return audio_service_acl_repository.get_physical_devices()

    # ========== 读操作 ==========

    def get_all(self, page: int = 1, per_page: int = 10, keyword: str = None,
                device_type: str = None, lab_id: int = None) -> dict:
        """分页查询"""
        try:
            result = self.repo.list_playback_devices(
                page=page, per_page=per_page, keyword=keyword, device_type=device_type,
                lab_id=lab_id,
            )
            return {'success': True, 'message': 'Success', 'data': result, 'code': 200}
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def get_one(self, device_id: int) -> dict:
        """查询详情"""
        device = self.repo.get_playback_device(device_id)
        if not device:
            return {'success': False, 'message': '未找到播放设备', 'data': None, 'code': 404}

        return {'success': True, 'message': 'Success', 'data': device.to_dict(), 'code': 200}

    def scan(self) -> dict:
        """扫描物理播放通道"""
        try:
            physical_devices = self._get_physical_devices_via_grpc()

            registered = self.repo.get_all_playback_devices()
            registered_keys = set([f'{d.device_unique_id}_{d.channel_index}' for d in registered])

            scanned_results = []
            for dev in physical_devices:
                key = f"{dev['unique_id']}_{dev['channel_index']}"
                if key not in registered_keys:
                    scanned_results.append({
                        'name': dev['name'],
                        'model': f"Hardware Channel ({dev['host_api']})",
                        'device_unique_id': dev['unique_id'],
                        'channel_index': dev['channel_index'],
                        'sample_rate': dev['sample_rate'],
                        'type': 'dry',
                        'status': 'online',
                    })

            return {
                'success': True,
                'message': f'成功扫描到 {len(scanned_results)} 个新通道',
                'data': scanned_results,
                'code': 200,
            }
        except Exception as e:
            return {'success': False, 'message': f'扫描失败: {str(e)}', 'data': None, 'code': 400}


    def diagnosis(self, device_id: int) -> dict:
        """播放设备诊断（只读，契约 §2.5 固定 6 项，无副作用）"""
        device = self.repo.get_playback_device(device_id)
        if not device:
            return {'success': False, 'message': '未找到播放设备', 'data': None, 'code': 404}

        try:
            from device_service.infrastructure.acl.audio_service_acl_repository import audio_service_acl_repository
            devices, available = audio_service_acl_repository.enumerate_physical_devices()
            matched = match_physical_channel(devices, device.device_unique_id,
                                             device.channel_index) if available else None

            items = [
                self._item_enumerable(matched, available),
                self._item_channel_index(device, matched, devices, available),
                self._item_sample_rate(device, matched, available),
                self._item_spl_mapping(device),
                self._item_status(device),
                self._item_busy(),
            ]
            return {
                'success': True,
                'message': '诊断完成',
                'data': {'checkedAt': now_cst().isoformat(), 'items': items},
                'code': 200,
            }
        except Exception as e:
            logger.error(f'Device diagnosis error: {str(e)}', exc_info=True)
            return {'success': False, 'message': f'诊断失败: {str(e)}', 'data': None, 'code': 400}

    @staticmethod
    def _item(key, status, detail, suggestion=None) -> dict:
        return {
            'key': key,
            'label': _DIAGNOSIS_LABELS[key],
            'status': status,
            'detail': detail,
            'suggestion': suggestion,
        }

    def _item_enumerable(self, matched, available) -> dict:
        key = PlaybackDiagnosisKey.ENUMERABLE.value
        if not available:
            return self._item(key, PlaybackDiagnosisStatus.UNSUPPORTED.value,
                              _UNSUPPORTED_DETAIL, _UNSUPPORTED_SUGGESTION)
        if matched:
            return self._item(key, PlaybackDiagnosisStatus.OK.value, '物理设备已枚举到对应通道')
        return self._item(
            key, PlaybackDiagnosisStatus.ERROR.value, _MISSING_DETAIL, _MISSING_SUGGESTION)

    def _item_channel_index(self, device, matched, devices, available) -> dict:
        key = PlaybackDiagnosisKey.CHANNEL_INDEX.value
        if not available:
            return self._item(key, PlaybackDiagnosisStatus.UNSUPPORTED.value,
                              _UNSUPPORTED_DETAIL, _UNSUPPORTED_SUGGESTION)
        if not matched:
            return self._item(key, PlaybackDiagnosisStatus.UNSUPPORTED.value,
                              f'{_MISSING_DETAIL}，无法判定通道容量', _MISSING_SUGGESTION)
        capacity = channel_capacity(devices, matched.get('device_index'))
        if not capacity:
            return self._item(key, PlaybackDiagnosisStatus.UNSUPPORTED.value,
                              '硬件通道容量未知，无法判定', _UNDETERMINED_SUGGESTION)
        if device.channel_index in capacity:
            return self._item(
                key, PlaybackDiagnosisStatus.OK.value,
                f'通道索引 {device.channel_index} 在硬件通道容量内')
        return self._item(
            key, PlaybackDiagnosisStatus.WARN.value,
            f'通道索引 {device.channel_index} 超出硬件通道范围 {sorted(capacity)}',
            '执行「重置配置」按硬件重新探测通道索引')

    def _item_sample_rate(self, device, matched, available) -> dict:
        key = PlaybackDiagnosisKey.SAMPLE_RATE.value
        if not available:
            return self._item(key, PlaybackDiagnosisStatus.UNSUPPORTED.value,
                              _UNSUPPORTED_DETAIL, _UNSUPPORTED_SUGGESTION)
        if not matched:
            return self._item(key, PlaybackDiagnosisStatus.UNSUPPORTED.value,
                              f'{_MISSING_DETAIL}，无法判定采样率', _MISSING_SUGGESTION)
        hardware_rate = matched.get('sample_rate')
        if not hardware_rate:
            return self._item(key, PlaybackDiagnosisStatus.UNSUPPORTED.value,
                              '硬件默认采样率未知，无法判定', _UNDETERMINED_SUGGESTION)
        if device.sample_rate == hardware_rate:
            return self._item(
                key, PlaybackDiagnosisStatus.OK.value,
                f'库中采样率 {device.sample_rate} Hz 与硬件一致')
        return self._item(
            key, PlaybackDiagnosisStatus.WARN.value,
            f'库中采样率 {device.sample_rate} Hz 与硬件默认 {hardware_rate} Hz 不一致',
            '执行「重置配置」按硬件对齐采样率')

    def _item_spl_mapping(self, device) -> dict:
        key = PlaybackDiagnosisKey.SPL_MAPPING.value
        if device.current_spl_mapping_id:
            return self._item(
                key, PlaybackDiagnosisStatus.OK.value,
                f'已关联声压映射 ID {device.current_spl_mapping_id}')
        return self._item(
            key, PlaybackDiagnosisStatus.WARN.value, '未关联声压映射',
            '在设备行「关联声压映射」中绑定校准映射')

    def _item_status(self, device) -> dict:
        key = PlaybackDiagnosisKey.STATUS.value
        if device.status == 'online':
            return self._item(key, PlaybackDiagnosisStatus.OK.value, '设备当前在线')
        return self._item(
            key, PlaybackDiagnosisStatus.WARN.value, f'设备当前状态: {device.status}',
            '确认设备连接后执行「重启」重新枚举')

    def _item_busy(self) -> dict:
        key = PlaybackDiagnosisKey.BUSY.value
        try:
            from device_service.infrastructure.acl.task_acl_repository import task_acl_repository
            busy = task_acl_repository.has_running_e2e_tasks()
        except Exception:
            logger.debug("查询运行中任务失败，按未占用处理", exc_info=True)
            busy = False
        if busy:
            return self._item(
                key, PlaybackDiagnosisStatus.WARN.value, '有运行中的测试任务占用设备',
                '等待任务结束后再执行控制操作')
        return self._item(key, PlaybackDiagnosisStatus.OK.value, '当前无测试任务占用')


# 模块级实例
playback_query_service = PlaybackQueryService()
