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

        testcase_id = None
        testcase_name = None

        audio = self.repo.get_audio_with_deleted(audio_id)
        if not audio or audio.deleted:
            # audio_id 实为 testcase_id，从用例 config 解析真实 audio_id
            audios_config = self._task_acl.get_testcase_config_audios(audio_id)
            if audios_config:
                audio_item = audios_config[0]
                actual_audio_id = audio_item.get('audio_id')
                if actual_audio_id:
                    audio = self.repo.get_audio_with_deleted(actual_audio_id)
                    testcase_id = audio_id
                    tc = self._task_acl.get_testcase_by_id(audio_id)
                    if tc:
                        testcase_name = tc.name

        if not audio or audio.deleted:
            return {'success': False, 'message': '音频不存在', 'data': None, 'code': 404}

        try:
            from audio_service.infrastructure.audio.audio_engine import audio_service
            from audio_service.infrastructure.audio.spl_service import spl_service
            from audio_service.infrastructure.audio.playback_config_builder import (
                _get_playback_device_via_grpc,
                _find_playback_device_by_unique_id,
            )

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
                self._record_playback_history(
                    audio, device, result='success',
                    testcase_id=testcase_id, testcase_name=testcase_name,
                )

            if not device_names:
                # 解析到设备但全部不可用/未真正发起播放：落一条失败记录
                attempted = devices_to_use[0] if devices_to_use else {'name': '未知设备', 'id': ''}
                self._record_playback_history(
                    audio, attempted, result='failed',
                    testcase_id=testcase_id, testcase_name=testcase_name,
                )
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
            # 硬件播放失败：落一条失败记录（不阻塞错误返回）
            try:
                attempted = devices_to_use[0] if devices_to_use else {'name': '未知设备', 'id': ''}
                self._record_playback_history(
                    audio, attempted, result='failed',
                    testcase_id=testcase_id, testcase_name=testcase_name,
                )
            except Exception:
                pass
            return {'success': False, 'message': f'硬件播放失败: {str(e)}', 'data': None, 'code': 400}

    def _record_playback_history(self, audio, device, result, testcase_id=None, testcase_name=None):
        """落一条播放历史（INT-782#2）；失败只记日志，不阻塞试听主流程。"""
        try:
            device_id = device.get('id') if device.get('id') not in (None, '') else device.get('device_unique_id', '')
            self.repo.record_playback_history({
                'audio_id': audio.id,
                'testcase_id': testcase_id,
                'testcase_name': testcase_name,
                'device_id': str(device_id) if device_id is not None else '',
                'device_name': device.get('name', '未知设备'),
                'result': result,
                'duration': audio.duration,
                'source': 'preview',
            })
            self.repo.commit()
        except Exception as e:
            logger.error(f"记录播放历史失败: {e}", exc_info=True)

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
