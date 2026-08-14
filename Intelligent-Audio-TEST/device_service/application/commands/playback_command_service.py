# -*- coding: utf-8 -*-
"""播放设备 Command 应用服务（写侧）

CQRS 拆分后的写操作服务，包含 create/update/delete/associate_spl/test/stop_test/check_status。
- check_status 虽名为"检查"，但会调用 batch_update_playback_status 写库，故归 command 侧。
- 方法签名和实现与原 playback_crud_service 完全一致。
"""
import os
import re
import logging
import threading

from shared.utils.query_utils import now_cst
from shared.utils.log_handler import log_not_emit
from device_service.infrastructure.acl.task_acl_repository import task_acl_repository
from device_service.domain.repositories import PlaybackRepositoryInterface, SPLRepositoryInterface

logger = logging.getLogger(__name__)

# 用于存储测试播放的停止事件 {device_id: stop_event}
test_stop_events = {}


class PlaybackCommandService:
    """播放设备 Command 应用服务（写侧）"""

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
    def _log(level, content, task_id=None, test_case_id=None, api_id=None,
             category='execution', module='Playback', **kwargs):
        log_not_emit(
            level=level,
            module=module,
            content=content,
            category=category,
            source='backend',
            task_id=task_id,
            api_id=api_id,
            test_case_id=test_case_id,
            **kwargs
        )

    @staticmethod
    def _get_audio_service_stub():
        """获取 audio_service ACL 仓储（封装 AudioService gRPC 调用）"""
        from device_service.infrastructure.acl.audio_service_acl_repository import audio_service_acl_repository
        return audio_service_acl_repository

    @staticmethod
    def _get_device_index_via_grpc(unique_id):
        """通过 ACL 仓储获取设备索引"""
        from device_service.infrastructure.acl.audio_service_acl_repository import audio_service_acl_repository
        return audio_service_acl_repository.get_device_index(unique_id)

    @staticmethod
    def _play_audio_via_grpc(task_id, file_path, device_index, channel_index, gain, loop=False, player_type='', offset=0):
        """通过 ACL 仓储播放音频"""
        from device_service.infrastructure.acl.audio_service_acl_repository import audio_service_acl_repository
        return audio_service_acl_repository.play_audio(
            task_id, file_path, device_index, channel_index, gain,
            loop=loop, player_type=player_type, offset=offset,
        )

    @staticmethod
    def _stop_audio_via_grpc(task_id):
        """通过 ACL 仓储停止音频"""
        from device_service.infrastructure.acl.audio_service_acl_repository import audio_service_acl_repository
        return audio_service_acl_repository.stop_audio(task_id)

    @staticmethod
    def _get_physical_devices_via_grpc():
        """通过 ACL 仓储获取物理设备列表"""
        from device_service.infrastructure.acl.audio_service_acl_repository import audio_service_acl_repository
        return audio_service_acl_repository.get_physical_devices()

    @staticmethod
    def _spl_to_gain_via_grpc(mapping_id, target_spl):
        """通过 ACL 仓储获取 SPLMapping 并计算增益（不依赖 audio_service 代码）"""
        import numpy as np
        from device_service.infrastructure.acl.spl_config_acl_repository import spl_config_acl_repository
        try:
            mapping = spl_config_acl_repository.get_spl_mapping(mapping_id)
            if mapping is None:
                return 1.0
            target_spl_val = mapping.get('target_spl')
            digital_gain = mapping.get('digital_gain')
            calibration_data = mapping.get('calibration_data')

            MIN_GAIN_LINEAR = 10 ** (-70.0 / 20.0)
            MAX_GAIN_LINEAR = 10 ** (5.0 / 20.0)

            def _clamp(g):
                return max(MIN_GAIN_LINEAR, min(MAX_GAIN_LINEAR, g))

            if target_spl_val is not None and abs(target_spl_val - target_spl) < 0.1:
                if digital_gain is not None:
                    gain_db = digital_gain / 100.0 if digital_gain > 1 else digital_gain
                    return _clamp(gain_db)

            if calibration_data:
                points = calibration_data.get('points', [])
                if points:
                    valid_points = [p for p in points if p.get('spl') is not None]
                    if not valid_points:
                        return 1.0
                    processed = []
                    for p in valid_points:
                        spl = p['spl']
                        gain_offset = p.get('gainOffset') if p.get('gainOffset') is not None else p.get('gain_offset')
                        dg = p.get('digital_gain', p.get('gain', 0))
                        if gain_offset is not None:
                            linear = 10 ** (gain_offset / 20.0)
                        else:
                            linear = dg / 100.0
                        processed.append({'spl': spl, 'gain_linear': linear})
                    processed.sort(key=lambda x: x['spl'])
                    spls = [p['spl'] for p in processed]
                    gains = [p['gain_linear'] for p in processed]
                    if target_spl >= max(spls):
                        return _clamp(max(gains))
                    if target_spl <= min(spls):
                        if len(processed) >= 2:
                            coeffs = np.polyfit(spls, gains, 1)
                            extrapolated = np.polyval(coeffs, target_spl)
                            if extrapolated <= 0:
                                extrapolated = min(gains)
                            return _clamp(extrapolated)
                        return _clamp(min(gains))
                    return _clamp(np.interp(target_spl, spls, gains))

            if target_spl_val and digital_gain:
                diff_db = target_spl - target_spl_val
                factor = 10 ** (diff_db / 20.0)
                return _clamp(factor)
        except Exception:
            logger.debug("根据 SPL 计算增益失败 target_spl=%s", target_spl, exc_info=True)
        return 1.0

    # ========== 写操作 ==========

    def create(self, data: dict) -> dict:
        """添加播放设备"""
        try:
            device_unique_id = data.get('device_unique_id')
            channel_index = data.get('channel_index', 0)

            existing_device = self.repo.find_playback_by_unique_and_channel(
                device_unique_id, channel_index
            )

            if existing_device:
                return {
                    'success': False,
                    'message': '该播放设备已存在！请检查设备唯一标识和通道索引。',
                    'data': None,
                    'code': 400,
                }

            new_device = self.repo.create_playback_device(data)
            return {
                'success': True,
                'message': '播放设备添加成功',
                'data': {'id': new_device.id},
                'code': 201,
            }
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def update(self, device_id: int, data: dict) -> dict:
        """更新播放设备信息"""
        device = self.repo.get_playback_device(device_id)
        if not device:
            return {'success': False, 'message': '未找到播放设备', 'data': None, 'code': 404}

        try:
            update_fields = {}
            field_map = {
                'name': 'name',
                'model': 'model',
                'device_type': 'device_type',
                'sample_rate': 'sample_rate',
                'channel_index': 'channel_index',
                'device_unique_id': 'device_unique_id',
                'description': 'description',
                'status': 'status',
                'current_spl_mapping_id': 'current_spl_mapping_id',
            }
            for json_key, attr_name in field_map.items():
                if json_key in data and data[json_key] is not None:
                    update_fields[attr_name] = data[json_key]

            updated = self.repo.update_playback_device(device_id, update_fields)
            if not updated:
                return {'success': False, 'message': '未找到播放设备', 'data': None, 'code': 404}
            return {'success': True, 'message': '播放设备信息更新成功', 'data': None, 'code': 200}
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def delete(self, device_id: int) -> dict:
        """软删除（含 TestCase 引用检查）"""
        device = self.repo.get_playback_device(device_id)
        if not device:
            return {'success': False, 'message': '未找到播放设备', 'data': None, 'code': 404}

        try:
            usage_count = self.repo.check_playback_in_testcases(device_id)
            if usage_count > 0:
                return {
                    'success': False,
                    'message': f'无法删除：该设备正被 {usage_count} 个测试用例配置引用，请先修改相关配置',
                    'data': None,
                    'code': 400,
                }

            self.repo.delete_playback_device(device_id)
            return {'success': True, 'message': '播放设备已删除 (逻辑删除)', 'data': None, 'code': 200}
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def associate_spl(self, device_id: int, data: dict) -> dict:
        """关联 SPL 映射"""
        device = self.repo.get_playback_device(device_id)
        if not device:
            return {'success': False, 'message': '未找到播放设备', 'data': None, 'code': 404}

        spl_mapping_id = data.get('spl_mapping_id')
        if spl_mapping_id is None:
            return {'success': False, 'message': '缺少 spl_mapping_id', 'data': None, 'code': 400}

        mapping = self.spl_repo.get_spl_mapping(spl_mapping_id)
        if not mapping:
            return {'success': False, 'message': '未找到 SPL 映射记录', 'data': None, 'code': 404}

        if mapping.device_id and mapping.device_id != device_id:
            return {
                'success': False,
                'message': f'SPL 映射设备不匹配: 映射属于设备 ID {mapping.device_id}',
                'data': None,
                'code': 400,
            }

        if mapping.device_type and mapping.device_type != device.device_type:
            return {
                'success': False,
                'message': f'SPL 映射类型不匹配: 映射类型为 {mapping.device_type}, 设备类型为 {device.device_type}',
                'data': None,
                'code': 400,
            }

        try:
            self.repo.update_playback_device_spl_ref(device_id, spl_mapping_id)
            return {'success': True, 'message': 'SPL 映射关联成功', 'data': None, 'code': 200}
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def test(self, device_id: int, data: dict = None) -> dict:
        """测试播放设备（调用 audio_service）"""
        if task_acl_repository.has_running_e2e_tasks():
            return {
                'success': False,
                'message': '当前有待执行的E2E测试任务，不允许使用后端扬声器播放',
                'data': None,
                'code': 403,
            }

        device = self.repo.get_playback_device(device_id)
        if not device:
            return {'success': False, 'message': '未找到播放设备', 'data': None, 'code': 404}

        data = data or {}
        try:
            audio_id = data.get('audio_id')
            spl = data.get('spl')

            from device_service.config.config import Config
            sample_audio = os.path.join(Config.AUDIO_STORAGE_PATH, 'test.wav')

            audio_name = os.path.basename(sample_audio)
            if audio_id:
                # 通过 ACL 仓储调用 audio_service 获取音频信息
                from device_service.infrastructure.acl.audio_service_acl_repository import audio_service_acl_repository
                try:
                    audio = audio_service_acl_repository.get_audio(audio_id)
                    if audio:
                        file_path = audio.get('file_path')
                        if file_path and not audio.get('deleted'):
                            try:
                                from shared.infrastructure.storage import storage
                                sample_audio = storage.load_file(file_path)
                                audio_name = audio.get('name') or audio.get('filename')
                            except Exception:
                                logger.debug("从存储加载音频文件失败 file_path=%s", file_path, exc_info=True)
                except Exception:
                    logger.debug("通过 ACL 获取音频元数据失败 audio_id=%s", audio_id, exc_info=True)

            if not os.path.isabs(sample_audio):
                sample_audio = os.path.join(os.getcwd(), sample_audio)

            if not os.path.exists(sample_audio):
                return {
                    'success': False,
                    'message': f'音频文件不存在: {sample_audio}。请先确保音频文件存在。',
                    'data': None,
                    'code': 400,
                }

            device_index = self._get_device_index_via_grpc(device.device_unique_id)
            if device_index is None:
                self.repo.update_playback_device(device_id, {'status': 'offline'})
                return {
                    'success': False,
                    'message': f'无法定位物理设备: {device.device_unique_id}，设备已标记为离线',
                    'data': None,
                    'code': 400,
                }

            if device.status != 'online':
                self.repo.update_playback_device(device_id, {'status': 'online'})

            gain = 1.0
            if spl and device.current_spl_mapping_id:
                try:
                    # TODO: spl_to_gain 需通过 gRPC 获取校准数据后本地计算，暂跳过
                    pass
                except Exception:
                    logger.debug("spl_to_gain 计算失败 device_id=%s spl=%s", device_id, spl, exc_info=True)

            task_id = f'test_{device_id}'
            player_type = device.device_type or 'dry'

            self._play_audio_via_grpc(
                task_id=task_id,
                file_path=sample_audio,
                device_index=device_index,
                channel_index=device.channel_index,
                gain=gain,
                loop=True,
                player_type=player_type,
            )

            stop_event = threading.Event()
            test_stop_events[device_id] = stop_event

            self._log(
                level='INFO',
                category='DeviceTest',
                source=f'Device:{device.name}',
                content=f'已启动音频驱动播放: {audio_name}, 设备索引: {device_index}, 通道: {device.channel_index},增益: {round(gain, 4)}',
                playback_device_id=device_id,
            )

            return {
                'success': True,
                'message': f'已在设备 {device.name} 上开始测试播放',
                'data': {
                    'device': device.name,
                    'audio': audio_name,
                    'status': 'testing',
                    'device_index': device_index,
                    'channel_index': device.channel_index,
                    'gain': round(gain, 4),
                },
                'code': 200,
            }
        except Exception as e:
            logger.error(f'Device test error: {str(e)}', exc_info=True)
            return {'success': False, 'message': f'测试播放失败: {str(e)}', 'data': None, 'code': 400}

    def stop_test(self, device_id: int, data: dict = None) -> dict:
        """停止测试"""
        device = self.repo.get_playback_device(device_id)
        if not device:
            return {'success': False, 'message': '未找到播放设备', 'data': None, 'code': 404}

        try:
            task_id = f'test_{device_id}'
            self._stop_audio_via_grpc(task_id)

            stop_event = test_stop_events.get(device_id)
            if stop_event:
                stop_event.set()
                test_stop_events.pop(device_id, None)

            self._log(
                level='INFO',
                category='DeviceTest',
                source=f'Device:{device.name}',
                content='测试播放已手动停止',
                playback_device_id=device_id,
            )

            return {
                'success': True,
                'message': '测试音播放已停止',
                'data': {'id': device.id, 'status': 'online'},
                'code': 200,
            }
        except Exception as e:
            logger.error(f'Stop device test error: {str(e)}', exc_info=True)
            return {'success': False, 'message': f'停止测试失败: {str(e)}', 'data': None, 'code': 400}

    def check_status(self) -> dict:
        """检查所有播放设备状态（含写副作用：batch_update_playback_status）"""
        try:
            def normalize_unique_id(uid):
                if not uid:
                    return uid
                return re.sub(r'\((\d+)-\s+', '(', uid)

            devices = self.repo.get_all_playback_devices()
            audio_service = self._get_audio_service()
            physical_devices = audio_service.get_physical_devices()

            results = []
            current_time = now_cst()
            device_status_map = {}

            physical_device_info = {dev['unique_id']: dev['device_index'] for dev in physical_devices}
            for dev in physical_devices:
                normalized = normalize_unique_id(dev['unique_id'])
                if normalized != dev['unique_id']:
                    physical_device_info[normalized] = dev['device_index']

            physical_device_ids = set(physical_device_info.keys())
            log_not_emit('DEBUG', 'playback_controller', f'Physical devices: {physical_device_ids}', category='playback')

            for device in devices:
                device_unique_id = device.device_unique_id
                is_online = device_unique_id in physical_device_ids

                if not is_online:
                    normalized_id = normalize_unique_id(device_unique_id)
                    log_not_emit('DEBUG', 'playback_controller', f'Trying normalized match: {normalized_id}', category='playback')
                    is_online = normalized_id in physical_device_ids
                    if is_online:
                        device_unique_id = normalized_id

                log_not_emit('DEBUG', 'playback_controller', f'Checking device: {device.device_unique_id}, is online: {is_online}', category='playback')

                device_index = physical_device_info.get(device_unique_id)
                new_status = 'online' if is_online else 'offline'
                device_status_map[device.id] = new_status

                results.append({
                    'id': device.id,
                    'name': device.name,
                    'unique_id': device.device_unique_id,
                    'status': new_status,
                    'device_index': device_index,
                })

            if device_status_map:
                try:
                    self.repo.batch_update_playback_status(device_status_map)
                except Exception as commit_error:
                    logger.error(f'提交设备状态更新时出错: {str(commit_error)}', exc_info=True)

            return {
                'success': True,
                'message': '设备状态检查完成',
                'data': results,
                'code': 200,
            }
        except Exception as e:
            logger.error(f'检查设备状态时出错: {str(e)}', exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}


# 模块级实例
playback_command_service = PlaybackCommandService()
