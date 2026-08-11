# -*- coding: utf-8 -*-
"""音频试听应用服务

从 audio_crud_service.py 中提取的预览相关逻辑：
- preview_audio
- stop_preview_audio
"""
import logging

from audio_service.domain.repositories.audio_repository_abc import AudioRepositoryInterface
from audio_service.infrastructure.persistence.audio_repository import audio_repository

logger = logging.getLogger(__name__)


class AudioPreviewService:
    """音频试听应用服务"""

    def __init__(self, repo: AudioRepositoryInterface = None):
        self.repo = repo or audio_repository
        # ACL 仓储（跨域只读查询）
        from audio_service.infrastructure.acl.task_acl_repository import (
            TaskACLRepositoryImpl,
        )
        self._task_acl = TaskACLRepositoryImpl()

    def preview_audio(self, audio_id: int, data: dict) -> dict:
        """试听音频"""
        if self._task_acl.has_running_e2e_tasks():
            return {'success': False, 'message': '当前有待执行的E2E测试任务，不允许使用后端扬声器播放', 'data': None, 'code': 403}

        audio = self.repo.get_audio_with_deleted(audio_id)
        if not audio or audio.deleted:
            # audio_id 实为 testcase_id，从用例 config 解析真实 audio_id
            audios_config = self._task_acl.get_testcase_config_audios(audio_id)
            if audios_config:
                audio_item = audios_config[0]
                actual_audio_id = audio_item.get('audio_id')
                if actual_audio_id:
                    audio = self.repo.get_audio_with_deleted(actual_audio_id)

        if not audio or audio.deleted:
            return {'success': False, 'message': '音频不存在', 'data': None, 'code': 404}

        try:
            from audio_service.infrastructure.audio.audio_engine import audio_service
            from audio_service.infrastructure.audio.spl_service import spl_service
            from audio_service.infrastructure.audio.playback_config_builder import (
                _get_playback_device_via_grpc,
                _find_playback_device_by_unique_id,
            )
            from shared.clients.grpc_clients import get_playback_config_service_stub
            from shared.proto import device_service_pb2 as _e2e_pb
            from shared.utils.grpc_json import loads as _grpc_loads

            playback_device_id = data.get('playback_device_id') or data.get('playbackDeviceId')
            playback_device_ids = data.get('playback_device_ids') or data.get('playbackDeviceIds') or []
            device_unique_ids = data.get('device_unique_ids') or data.get('deviceUniqueIds') or []
            spl = data.get('spl')
            offset = data.get('offset', 0)

            if playback_device_id:
                playback_device_ids = [playback_device_id] + playback_device_ids
            playback_device_ids = list(set(playback_device_ids))
            device_unique_ids = list(set(device_unique_ids))

            device_names = []
            gains = []
            devices_to_use = []

            if device_unique_ids:
                for uid in device_unique_ids:
                    dev = _find_playback_device_by_unique_id(uid)
                    if dev:
                        devices_to_use.append(dev)
            elif playback_device_ids:
                for did in playback_device_ids:
                    try:
                        dev = _get_playback_device_via_grpc(int(did))
                    except (ValueError, TypeError):
                        dev = _find_playback_device_by_unique_id(did)
                    if dev:
                        devices_to_use.append(dev)
            else:
                devices_to_use.append({
                    'name': '默认设备',
                    'device_unique_id': '',
                    'channel_index': 0,
                    'current_spl_mapping_id': None,
                    'id': 'default',
                })

            for device in devices_to_use:
                device_name = device.get('name', '默认设备')
                dev_unique_id = device.get('device_unique_id', '')
                channel_index = device.get('channel_index', 0)
                gain = 1.0

                if spl and device.get('current_spl_mapping_id'):
                    gain = spl_service.spl_to_gain(device.get('current_spl_mapping_id'), spl)

                device_index = 0
                if dev_unique_id:
                    device_index = audio_service.get_device_index(dev_unique_id)
                    if device_index is None:
                        continue

                dev_id = device.get('id', 'default')
                player_type = f'ch_{dev_id}'
                audio_service.play_audio(
                    task_id=f"preview_{audio.id}_{dev_id}",
                    file_path=audio.file_path,
                    device_index=device_index,
                    channel_index=channel_index,
                    gain=gain,
                    player_type=player_type,
                    offset=offset,
                )
                device_names.append(device_name)
                gains.append(round(gain, 4))

            if not device_names:
                return {'success': False, 'message': '没有找到可用的播放设备', 'data': None, 'code': 404}

            response_data = {
                'audio': audio.name,
                'duration': audio.duration,
                'device': device_names[0] if device_names else None,
                'gain': gains[0] if gains else None,
                'devices': device_names,
                'gains': gains,
            }
            return {
                'success': True,
                'message': f'已在 {len(device_names)} 个设备上开始试听',
                'data': response_data,
                'code': 200,
            }
        except Exception as e:
            logger.error(f"Audio preview error: {str(e)}", exc_info=True)
            return {'success': False, 'message': f'硬件播放失败: {str(e)}', 'data': None, 'code': 400}

    def stop_preview_audio(self, audio_id: int) -> dict:
        """停止音频试听"""
        try:
            from audio_service.infrastructure.audio.audio_engine import audio_service

            actual_audio_id = audio_id
            audio = self.repo.get_audio_with_deleted(audio_id)
            if not audio or audio.deleted:
                # audio_id 实为 testcase_id，从用例 config 解析真实 audio_id
                audios_config = self._task_acl.get_testcase_config_audios(audio_id)
                if audios_config:
                    audio_item = audios_config[0]
                    resolved_audio_id = audio_item.get('audio_id')
                    if resolved_audio_id:
                        actual_audio_id = resolved_audio_id

            task_id_prefix = f"preview_{actual_audio_id}"
            stopped_tasks = []
            for task_id in list(audio_service.active_players.keys()):
                if task_id.startswith(task_id_prefix):
                    audio_service.stop_task_audio(task_id)
                    stopped_tasks.append(task_id)

            if stopped_tasks:
                return {
                    'success': True,
                    'message': f'音频试听已停止，共停止了 {len(stopped_tasks)} 个任务',
                    'data': None, 'code': 200,
                }
            else:
                return {'success': True, 'message': '没有找到正在播放的任务', 'data': None, 'code': 200}
        except Exception as e:
            logger.error(f"Stop audio preview error: {str(e)}", exc_info=True)
            return {'success': False, 'message': f'停止试听失败: {str(e)}', 'data': None, 'code': 400}


# 模块级实例
audio_preview_service = AudioPreviewService()
