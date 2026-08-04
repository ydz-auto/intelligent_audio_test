import time

from shared.algorithm.field_mapper import get_field_mapper
from e2e_test_service.core.e2e_executor.grpc_helpers import (
    _register_task_devices_via_grpc,
    _play_voiceprint_via_grpc,
)


class PreparationMixin:
    """阶段一：循环前准备 —— 设备准备 + 音频预下载 + 声纹注册 + 预创建 TestResult"""

    def _prepare_rounds(self, task_id, tc_rel_id, data, case_config, algorithm_type,
                        case_field_values, rounds, test_case_id):
        """设备准备 + 声纹注册 + 预创建 TestResult，返回 (device_info_list, result_id)"""
        # 设备准备
        device_result = self._device_manager.get_device_info(task_id, case_config)
        if not device_result['success']:
            error_msg = f"设备信息获取失败: {device_result.get('error')}"
            self._log(level='ERROR', content=error_msg, task_id=task_id, test_case_id=test_case_id)
            self._update_tc_rel_status(tc_rel_id, execution_status='failed', status='failed', error_message=error_msg)
            raise RuntimeError(error_msg)

        device_info_list = device_result['data']['device_info_list']
        self.current_extra_params = self._execute_extra_params(algorithm_type, case_field_values, include_format_strings=True)
        # 跨服务调用：通过 gRPC DeviceService 注册任务设备
        _register_task_devices_via_grpc(task_id, device_info_list)

        for info in device_info_list:
            if info.get("driver"):
                info["driver"].set_task_id(task_id)
                info["driver"].set_test_case_id(test_case_id)
                info["driver"].set_device_id(info["device_id"])

        self._device_manager.initialize_devices(device_info_list, task_id, test_case_id=test_case_id, algorithm_type=algorithm_type)

        # 音频预下载：遍历所有 rounds，把 audio_id 对应的 OSS 文件提前下载到本地
        self._prepare_audio_files(task_id, rounds, test_case_id)

        # 声纹注册
        self._register_voiceprint(task_id, tc_rel_id, rounds, test_case_id)

        # 预创建 TestResult
        first_device_id = device_info_list[0].get('device_id') if device_info_list else None
        result_id = self._save_result(
            task_id=task_id,
            test_case_id=test_case_id,
            result_data={'multi_round': True, 'total_rounds': len(rounds)},
            algo_result={'test_type': 'e2e', 'algorithm_type': algorithm_type, 'total_rounds': len(rounds), 'rounds': [], 'aggregated': {}},
            algorithm_type=algorithm_type,
            device_id=first_device_id,
            api_id=None,
            execution_status='running',
            response_time=0,
            error_message=None
        )
        self._log(
            level='DEBUG',
            content=f"预先创建多轮 TestResult: result_id={result_id}, total_rounds={len(rounds)}",
            task_id=task_id, test_case_id=test_case_id,
        )

        return device_info_list, result_id

    def _prepare_audio_files(self, task_id, rounds, test_case_id):
        """遍历所有 rounds，收集 audio_id 并从 OSS 预下载到本地，建立 audio_id→local_path 映射。

        覆盖范围：干声 audios[].audio_id、噪声 background_noise.audio_id、
        干扰人 interferers[].audios[].audio_id、声纹 algorithmParams.voiceprint_audio_id。
        """
        from shared.models.database import db
        from shared.models.models import Audio
        from shared.infrastructure.storage import storage

        audio_ids = set()

        for round_config in (rounds or []):
            if not isinstance(round_config, dict):
                continue
            # 干声
            for audio_cfg in round_config.get('audios', []) or []:
                aid = audio_cfg.get('audio_id')
                if aid:
                    audio_ids.add(aid)
            # 噪声
            bg = round_config.get('background_noise') or {}
            if bg.get('audio_id'):
                audio_ids.add(bg['audio_id'])
            # 干扰人
            for interferer in round_config.get('interferers', []) or []:
                for ia in interferer.get('audios', []) or []:
                    aid = ia.get('audio_id')
                    if aid:
                        audio_ids.add(aid)
            # 声纹
            from shared.algorithm.case_parameter_extractor import _normalize_algorithm_params
            algo_params = _normalize_algorithm_params(round_config.get('algorithm_params', []))
            vp_audio_id = algo_params.get('voiceprint_audio_id')
            if vp_audio_id:
                audio_ids.add(vp_audio_id)

        if not audio_ids:
            return

        self._log(
            level='INFO',
            content=f'开始预下载音频: {len(audio_ids)} 个 (audio_ids={list(audio_ids)})',
            task_id=task_id, test_case_id=test_case_id,
        )

        success_count = 0
        for audio_id in audio_ids:
            if audio_id in self._audio_local_paths:
                continue
            try:
                audio_obj = db.session.get(Audio, audio_id)
                if not audio_obj or not audio_obj.file_path:
                    self._log(
                        level='WARNING',
                        content=f'预下载: audio_id={audio_id} 不存在或无 file_path，跳过',
                        task_id=task_id, test_case_id=test_case_id,
                    )
                    continue
                local_path = storage.load_file(audio_obj.file_path)
                self._audio_local_paths[audio_id] = local_path
                success_count += 1
            except Exception as e:
                self._log(
                    level='ERROR',
                    content=f'预下载音频失败 audio_id={audio_id}: {e}',
                    task_id=task_id, test_case_id=test_case_id,
                )

        self._log(
            level='INFO',
            content=f'音频预下载完成: {success_count}/{len(audio_ids)} 成功',
            task_id=task_id, test_case_id=test_case_id,
        )

    def _register_voiceprint(self, task_id, tc_rel_id, rounds, test_case_id):
        """从首轮 algorithmParams 提取声纹配置并执行注册"""
        from shared.algorithm.case_parameter_extractor import _normalize_algorithm_params

        first_round_algo_params = {}
        if rounds and isinstance(rounds[0], dict):
            first_round_algo_params = _normalize_algorithm_params(rounds[0].get('algorithm_params', []))

        voiceprint_config = {
            'enabled': first_round_algo_params.get('voiceprint_enabled', False),
            'audio_id': first_round_algo_params.get('voiceprint_audio_id'),
            'playback_device_id': first_round_algo_params.get('voiceprint_playback_device_id'),
            'spl': first_round_algo_params.get('voiceprint_spl', 70.0),
            'wait_time': first_round_algo_params.get('voiceprint_wait_time', 5.0),
        }
        if voiceprint_config.get('enabled'):
            # 跨服务调用：通过 gRPC PlaybackService 播放声纹
            if not _play_voiceprint_via_grpc(voiceprint_config, task_id):
                self._log(level='ERROR', content='声纹注册失败，中止测试', task_id=task_id, test_case_id=test_case_id)
                self._update_tc_rel_status(tc_rel_id, execution_status='failed', status='failed', error_message='声纹注册失败')
                raise RuntimeError('声纹注册失败')
