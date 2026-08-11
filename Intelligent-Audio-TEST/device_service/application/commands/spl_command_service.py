# -*- coding: utf-8 -*-
"""SPL 映射命令应用服务（写侧）

CQRS 拆分后的写操作服务，包含原 SPLCrudService 的写操作方法：
- create / update / delete / calibrate / play_test_tone / stop_test_tone
- 以及相关辅助方法
"""
import time
import os
import wave
import logging

from shared.utils.query_utils import now_cst
from shared.utils.log_handler import log_not_emit, log_and_emit
from device_service.infrastructure.acl.task_acl_repository import task_acl_repository
from device_service.domain.repositories import SPLRepositoryInterface, PlaybackRepositoryInterface

logger = logging.getLogger(__name__)


class SPLCommandService:
    """SPL 映射命令应用服务（写侧）"""

    def __init__(self, repo: SPLRepositoryInterface = None, playback_repo: PlaybackRepositoryInterface = None):
        if repo is None:
            from device_service.infrastructure.persistence.device_repository import spl_repository
            repo = spl_repository
        if playback_repo is None:
            from device_service.infrastructure.persistence.device_repository import playback_repository
            playback_repo = playback_repository
        self.repo = repo
        self.playback_repo = playback_repo

    @staticmethod
    def _get_audio_service():
        """获取 audio_service gRPC stub（AudioService）"""
        from shared.clients.grpc_clients import get_audio_service_stub
        return get_audio_service_stub()

    @staticmethod
    def _get_device_index_via_grpc(unique_id):
        """通过 gRPC 获取设备索引"""
        from shared.proto import audio_service_pb2 as _e2e_pb
        from shared.utils.grpc_json import loads as _grpc_loads
        try:
            stub = get_audio_service_stub()
            resp = stub.GetDeviceIndex(_e2e_pb.GetDeviceIndexRequest(unique_id=unique_id))
            if resp.success:
                data = _grpc_loads(resp.data, {}) or {}
                return data.get('device_index')
        except Exception:
            pass
        return None

    @staticmethod
    def _play_audio_via_grpc(task_id, file_path, device_index, channel_index, gain, loop=False, player_type='', offset=0):
        """通过 gRPC 播放音频"""
        import json as _json
        from shared.proto import audio_service_pb2 as _e2e_pb
        try:
            stub = get_audio_service_stub()
            play_config = _json.dumps({
                'device_index': device_index,
                'channel_index': channel_index,
                'gain': gain,
                'loop': loop,
                'player_type': player_type,
                'offset': offset,
            })
            resp = stub.PlayAudio(_e2e_pb.PlayAudioRequest(
                task_id=task_id,
                audio_file_paths=_json.dumps([file_path]),
                play_config=play_config,
            ))
            return resp.success
        except Exception:
            return False

    @staticmethod
    def _stop_audio_by_pattern_via_grpc(task_id_pattern, player_type_pattern):
        """通过 gRPC 按模式停止音频"""
        from shared.proto import e2e_service_pb2 as _e2e_pb
        from shared.utils.grpc_json import loads as _grpc_loads
        try:
            stub = get_audio_service_stub()
            resp = stub.StopAudioByPattern(_e2e_pb.StopAudioByPatternRequest(
                task_id_pattern=task_id_pattern,
                player_type_pattern=player_type_pattern,
            ))
            if resp.success:
                data = _grpc_loads(resp.data, {}) or {}
                return data.get('stopped_count', 0)
        except Exception:
            pass
        return 0

    # ========== 写操作 ==========

    def create(self, data: dict) -> dict:
        """创建 SPL 映射"""
        device_id = data.get('device_id')
        device_type = data.get('device_type')

        if device_id is None and device_type is None:
            return {'success': False, 'message': '必须提供 device_id 或 device_type 之一', 'data': None, 'code': 400}

        try:
            calibration_data = data.get('calibration_data')
            calibration_status = data.get('calibration_status')

            log_not_emit('DEBUG', 'spl_controller',
                         f'创建映射 - calibration_data: {calibration_data}, calibration_status: {calibration_status}, data: {data}',
                         category='spl')

            if calibration_data and isinstance(calibration_data, dict) and 'points' in calibration_data:
                valid_points, validation_errors = self._validate_calibration_points(calibration_data)
                if validation_errors:
                    return {'success': False, 'message': '; '.join(validation_errors), 'data': None, 'code': 400}
                calibration_data['points'] = valid_points
                if len(valid_points) > 0:
                    calibration_status = 'calibrated'
            else:
                calibration_data = {'points': []}

            target_spl = data.get('target_spl')
            if not target_spl and calibration_data and calibration_data['points']:
                target_spl = calibration_data['points'][0]['spl']

            create_data = {
                'name': data['name'],
                'description': data.get('description'),
                'device_id': device_id,
                'device_type': device_type,
                'distance': data.get('distance') or 1.0,
                'target_spl': target_spl,
                'digital_gain': None,
                'test_frequency': data.get('test_frequency') or 1000,
                'calibration_status': calibration_status or 'uncalibrated',
                'calibration_data': calibration_data,
            }

            new_mapping = self.repo.create_spl_mapping(create_data)

            if device_id:
                device = self.playback_repo.get_playback_device(device_id)
                if device:
                    self.repo.update_playback_device_spl_ref(device_id, new_mapping.id)
                    log_not_emit('DEBUG', 'spl_controller',
                                 f'创建设备 {device_id} 的映射关联: current_spl_mapping_id = {new_mapping.id}',
                                 category='spl')

            # 提交事务（create_spl_mapping 只 flush 不 commit）
            self.repo.commit()

            return {
                'success': True,
                'message': 'SPL 映射记录创建成功',
                'data': {'id': new_mapping.id},
                'code': 201,
            }
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def update(self, mapping_id: int, data: dict) -> dict:
        """更新 SPL 映射"""
        mapping = self.repo.get_spl_mapping(mapping_id)
        if not mapping or mapping.deleted:
            return {'success': False, 'message': '未找到 SPL 映射记录', 'data': None, 'code': 404}

        try:
            env_params_changed = False
            distance = data.get('distance')
            test_frequency = data.get('test_frequency')

            if distance is not None and distance != mapping.distance:
                env_params_changed = True
            if test_frequency is not None and test_frequency != mapping.test_frequency:
                env_params_changed = True

            update_fields = {}
            field_map = {
                'name': 'name',
                'description': 'description',
                'device_id': 'device_id',
                'device_type': 'device_type',
                'distance': 'distance',
                'target_spl': 'target_spl',
                'digital_gain': 'digital_gain',
                'test_frequency': 'test_frequency',
                'calibration_status': 'calibration_status',
            }
            for field_name, attr_name in field_map.items():
                if field_name in data and data[field_name] is not None:
                    update_fields[attr_name] = data[field_name]

            calibration_data = data.get('calibration_data')
            if calibration_data is not None:
                if isinstance(calibration_data, dict) and 'points' in calibration_data:
                    valid_points, validation_errors = self._validate_calibration_points(calibration_data)
                    if validation_errors:
                        return {'success': False, 'message': '; '.join(validation_errors), 'data': None, 'code': 400}
                    calibration_data['points'] = valid_points
                    if len(valid_points) > 0:
                        update_fields['calibration_status'] = 'calibrated'
                    update_fields['calibration_data'] = calibration_data
                else:
                    update_fields['calibration_data'] = {'points': []}

            if env_params_changed:
                update_fields['calibration_status'] = 'uncalibrated'
                update_fields['calibration_data'] = None

            is_current = data.get('is_current')
            new_device_id = data.get('device_id')

            if new_device_id is not None and new_device_id != mapping.device_id:
                old_device_id = mapping.device_id
                if old_device_id:
                    old_device = self.playback_repo.get_playback_device(old_device_id)
                    if old_device and old_device.current_spl_mapping_id == mapping.id:
                        self.playback_repo.update_playback_device_spl_ref(old_device_id, None)

                if new_device_id:
                    new_device = self.playback_repo.get_playback_device(new_device_id)
                    if new_device:
                        if is_current or (is_current is None and new_device.current_spl_mapping_id is None):
                            self.playback_repo.update_playback_device_spl_ref(new_device_id, mapping.id)
            elif is_current is not None:
                device = self.playback_repo.get_playback_device(mapping.device_id) if mapping.device_id else None
                if device:
                    if is_current:
                        self.playback_repo.update_playback_device_spl_ref(mapping.device_id, mapping.id)
                    elif device.current_spl_mapping_id == mapping.id:
                        self.playback_repo.update_playback_device_spl_ref(mapping.device_id, None)

            self.repo.update_spl_mapping(mapping_id, update_fields)
            return {'success': True, 'message': 'SPL 映射记录更新成功', 'data': None, 'code': 200}
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def delete(self, mapping_id: int) -> dict:
        """软删除 SPL 映射"""
        mapping = self.repo.get_spl_mapping(mapping_id)
        if not mapping or mapping.deleted:
            return {'success': False, 'message': '未找到 SPL 映射记录', 'data': None, 'code': 404}

        try:
            if mapping.device_id:
                device = self.playback_repo.get_playback_device(mapping.device_id)
                if device and device.current_spl_mapping_id == mapping_id:
                    self.playback_repo.update_playback_device_spl_ref(mapping.device_id, None)

            self.repo.clear_playback_spl_refs(mapping_id)
            self.repo.delete_spl_mapping(mapping_id)
            return {'success': True, 'message': 'SPL 映射记录已删除', 'data': None, 'code': 200}
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def calibrate(self, mapping_id: int) -> dict:
        """SPL 校准"""
        mapping = self.repo.get_spl_mapping(mapping_id)
        if not mapping or mapping.deleted:
            return {'success': False, 'message': '未找到映射记录', 'data': None, 'code': 404}

        try:
            log_and_emit('info', 'SPL_CALIBRATION',
                         f'开始校准映射: {mapping.id} - {mapping.name}',
                         category='spl', task_id=None, device_id=mapping.device_id)

            scan_points = []
            for gain in [1, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
                measured_spl = 40 + (gain - 1) * (90 - 40) / (100 - 1)
                scan_points.append({"gain": gain, "spl": round(measured_spl, 2)})
                log_and_emit('info', 'SPL_CALIBRATION',
                             f'校准点测量完成: 增益={gain}, SPL={round(measured_spl, 2)}dB',
                             category='spl', task_id=None, device_id=mapping.device_id)
                time.sleep(0.1)

            calibration_data = {"points": scan_points}
            self.repo.update_spl_mapping(mapping_id, {
                'calibration_data': calibration_data,
                'calibration_status': 'calibrated',
            })

            self.repo.create_calibration_history(
                mapping_id, calibration_data, mapping.distance, mapping.test_frequency
            )

            log_and_emit('info', 'SPL_CALIBRATION',
                         f'校准完成: {mapping.id} - {mapping.name}',
                         category='spl', task_id=None, device_id=mapping.device_id)

            return {
                'success': True,
                'message': '校准成功',
                'data': {'id': mapping_id, 'calibration_status': 'calibrated'},
                'code': 200,
            }
        except Exception as e:
            try:
                log_and_emit('error', 'SPL_CALIBRATION',
                             f'校准失败: {str(e)}', category='spl',
                             task_id=None, device_id=mapping.device_id)
            except Exception:
                pass
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def play_test_tone(self, data: dict = None) -> dict:
        """播放测试音"""
        if task_acl_repository.has_running_e2e_tasks():
            return {
                'success': False,
                'message': '当前有待执行的E2E测试任务，不允许使用后端扬声器播放',
                'data': None,
                'code': 403,
            }

        data = data or {}
        gain_value = data.get('gain_value') or 50
        gain_offset = data.get('gain_offset')
        target_spl = data.get('target_spl')
        if target_spl is None:
            target_spl = 65
        unique_id_raw = data.get('unique_id')
        unique_id = str(unique_id_raw).strip() if unique_id_raw is not None else None
        if unique_id == '':
            unique_id = None

        try:
            from device_service.config.config import Config
            sample_audio = os.path.join(Config.AUDIO_STORAGE_PATH, 'test.wav')

            if not os.path.exists(sample_audio):
                return {'success': False, 'message': f'音频文件不存在: {sample_audio}', 'data': None, 'code': 404}

            with wave.open(sample_audio, 'rb') as wf:
                duration = wf.getnframes() / float(wf.getframerate())

            reference_dbfs = -30.0

            if gain_offset is not None:
                gain_offset_db = float(gain_offset)
            else:
                gain_offset_db = (gain_value - 50) * 0.24

            final_dbfs = reference_dbfs + gain_offset_db
            linear_gain = 10 ** (gain_offset_db / 20)

            devices_to_use = []
            if unique_id:
                device = self.playback_repo.find_playback_by_unique_id(unique_id)
                if device:
                    devices_to_use.append(device)
                else:
                    return {'success': False, 'message': f'找不到设备: {unique_id}', 'data': None, 'code': 404}
            else:
                devices = self.playback_repo.find_playback_limit(10)
                devices_to_use = devices if devices else []

            if not devices_to_use:
                return {'success': False, 'message': '没有找到可用的播放设备', 'data': None, 'code': 404}

            results = []
            for device in devices_to_use:
                device_name = getattr(device, 'name', '未知设备')
                device_unique_id = getattr(device, 'device_unique_id', '')
                channel_index = getattr(device, 'channel_index', 0)

                final_gain = linear_gain

                device_index = 0
                if device_unique_id:
                    device_index = self._get_device_index_via_grpc(device_unique_id)
                    if device_index is None:
                        continue

                player_type = f'test_tone_{getattr(device, "id", "default")}'
                self._play_audio_via_grpc(
                    task_id=f'test_tone_{device_index}_{int(target_spl)}',
                    file_path=sample_audio,
                    device_index=device_index,
                    channel_index=channel_index,
                    gain=final_gain,
                    loop=True,
                    player_type=player_type,
                    offset=0,
                )

                results.append({
                    'device': device_name,
                    'gain_db': round(gain_offset_db, 2),
                    'final_dbfs': round(final_dbfs, 2),
                    'target_spl': target_spl,
                })

            if not results:
                return {'success': False, 'message': '没有找到可用的播放设备', 'data': None, 'code': 404}

            return {
                'success': True,
                'message': f'测试音频已在 {len(results)} 个设备上播放',
                'data': {'devices': results, 'duration': round(duration, 2)},
                'code': 200,
            }
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def stop_test_tone(self, data: dict = None) -> dict:
        """停止测试音"""
        data = data or {}
        unique_id_raw = data.get('unique_id')
        unique_id = str(unique_id_raw).strip() if unique_id_raw is not None else None
        if unique_id == '':
            unique_id = None

        try:
            if unique_id:
                device_index = self._get_device_index_via_grpc(unique_id)
                if device_index is not None:
                    task_id_pattern = f'test_tone_{device_index}_*'
                    stopped = self._stop_audio_by_pattern_via_grpc(task_id_pattern, 'test_tone_*')
                    if stopped > 0:
                        return {
                            'success': True,
                            'message': f'已停止 {stopped} 个测试音任务',
                            'data': {'stopped_count': stopped},
                            'code': 200,
                        }
                    else:
                        return {
                            'success': True,
                            'message': '没有正在播放的测试音',
                            'data': {'stopped_count': 0},
                            'code': 200,
                        }
                else:
                    return {'success': False, 'message': '设备未找到', 'data': None, 'code': 404}
            else:
                stopped = self._stop_audio_by_pattern_via_grpc('test_tone_*', 'test_tone_*')
                return {
                    'success': True,
                    'message': f'已停止 {stopped} 个测试音任务',
                    'data': {'stopped_count': stopped},
                    'code': 200,
                }
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    # ========== 辅助方法 ==========

    @staticmethod
    def _validate_calibration_points(calibration_data):
        """校准校验点数据，返回 (valid_points, validation_errors)"""
        valid_points = []
        validation_errors = []
        for i, point in enumerate(calibration_data['points']):
            if not isinstance(point, dict):
                continue

            gain_offset_value = point.get('gainOffset') if point.get('gainOffset') is not None else point.get('gain_offset')
            digital_gain_value = point.get('digital_gain') if point.get('digital_gain') is not None else point.get('gain')

            if gain_offset_value is None and digital_gain_value is None:
                continue

            if gain_offset_value is None and digital_gain_value is not None:
                gain_offset_value = (float(digital_gain_value) - 50) * 0.24

            base_level_value = point.get('baseLevel') if point.get('baseLevel') is not None else point.get('base_level', -30)

            max_gain_offset = 25
            if gain_offset_value > max_gain_offset:
                validation_errors.append(f'增益点 {i+1}: 增益偏移 ({gain_offset_value} dB) 超过最大值 (+{max_gain_offset} dB)，最终电平不能大于 -5 dBFS')
                gain_offset_value = max_gain_offset

            normalized_point = {
                'spl': point.get('spl'),
                'gainOffset': gain_offset_value,
                'baseLevel': base_level_value,
                'finalLevel': -30 + (gain_offset_value if gain_offset_value else 0),
            }
            if digital_gain_value is not None:
                normalized_point['digital_gain'] = digital_gain_value

            valid_points.append(normalized_point)

        return valid_points, validation_errors


# 模块级实例
spl_command_service = SPLCommandService()
