import time

# 跨服务调用：通过 ACL 仓储访问 device_service / audio_service / playback_service
from e2e_test_service.infrastructure.acl import (
    DeviceAclRepositoryImpl,
    PlaybackAclRepositoryImpl,
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
            self._update_tc_rel_status(tc_rel_id, task_id=task_id, execution_status='failed', status='failed', error_message=error_msg)
            raise RuntimeError(error_msg)

        device_info_list = device_result['data']['device_info_list']
        self.current_extra_params = self._execute_extra_params(algorithm_type, case_field_values, include_format_strings=True)
        # 通过 ACL 仓储注册任务设备
        DeviceAclRepositoryImpl().register_task_devices(task_id, device_info_list)

        for info in device_info_list:
            if info.get("driver"):
                info["driver"].set_task_id(task_id)
                info["driver"].set_test_case_id(test_case_id)
                info["driver"].set_device_id(info["device_id"])

        self._device_manager.initialize_devices(device_info_list, task_id, test_case_id=test_case_id, algorithm_type=algorithm_type)

        # 音频预下载：遍历所有 rounds，把 audio_id 对应的 OSS 文件提前下载到本地
        self._prepare_audio_files(task_id, rounds, test_case_id, case_config)

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

    def _prepare_audio_files(self, task_id, rounds, test_case_id, case_config=None):
        """遍历所有 rounds，批量预下载并按设备采样率重采样，建立嵌套映射。

        通过 audio_service.PrepareAudios RPC 完成预下载+重采样，返回:
        {audio_id: {target_rate: local_path, "original": local_path}}

        覆盖范围：干声 audios[].audio_id、轮次噪声 background_noise.audio_id、
        全局噪声 case_config.background_noise.audio_id、
        干扰人 interferers[].audios[].audio_id、声纹 algorithmParams.voiceprint_audio_id。
        播放设备 ID 收集范围：干声 audios[].playback_device_id、
        噪声 background_noise.device_ids[]、干扰人 interferers[].device.id。
        """
        audio_ids = set()
        playback_device_ids = set()

        # 全局背景噪声（用例级，当轮次内未配置时回退使用）
        if case_config:
            global_bg = case_config.get('background_noise') or {}
            if global_bg.get('audio_id'):
                audio_ids.add(global_bg['audio_id'])
            for did in global_bg.get('device_ids', []) or []:
                if did:
                    playback_device_ids.add(did)

        for round_config in (rounds or []):
            if not isinstance(round_config, dict):
                continue
            # 干声
            for audio_cfg in round_config.get('audios', []) or []:
                aid = audio_cfg.get('audio_id')
                if aid:
                    audio_ids.add(aid)
                pid = audio_cfg.get('playback_device_id')
                if pid:
                    playback_device_ids.add(pid)
            # 轮次噪声
            bg = round_config.get('background_noise') or {}
            if bg.get('audio_id'):
                audio_ids.add(bg['audio_id'])
            for did in bg.get('device_ids', []) or []:
                if did:
                    playback_device_ids.add(did)
            # 干扰人
            for interferer in round_config.get('interferers', []) or []:
                # 嵌套结构：interferer.device.id
                dev_cfg = interferer.get('device')
                if dev_cfg and dev_cfg.get('id'):
                    playback_device_ids.add(dev_cfg['id'])
                # 扁平结构：interferer.playback_device_id
                _did = interferer.get('playback_device_id')
                if _did:
                    playback_device_ids.add(_did)
                for ia in interferer.get('audios', []) or []:
                    aid = ia.get('audio_id')
                    if aid:
                        audio_ids.add(aid)
            # 声纹
            from shared.clients.grpc_clients import algo_normalize_algorithm_params
            algo_params = algo_normalize_algorithm_params(round_config.get('algorithm_params', []))
            vp_audio_id = algo_params.get('voiceprint_audio_id')
            if vp_audio_id:
                audio_ids.add(vp_audio_id)

        if not audio_ids:
            return

        self._log(
            level='INFO',
            content=f'开始预下载音频: {len(audio_ids)} 个, 播放设备 {len(playback_device_ids)} 个 '
                    f'(audio_ids={list(audio_ids)})',
            task_id=task_id, test_case_id=test_case_id,
        )

        from shared.clients.grpc_clients import audio_prepare_audios
        result = audio_prepare_audios(list(audio_ids), list(playback_device_ids))

        if not result:
            self._log(
                level='WARNING',
                content='音频预下载返回空结果，播放时将回退到 OSS 原始文件',
                task_id=task_id, test_case_id=test_case_id,
            )
            return

        # 存储嵌套映射 {audio_id: {target_rate: local_path, "original": local_path}}
        self._audio_local_paths.update(result)

        prepared_count = len(result)
        self._log(
            level='INFO',
            content=f'音频预下载完成: {prepared_count}/{len(audio_ids)} 成功',
            task_id=task_id, test_case_id=test_case_id,
        )

    def _register_voiceprint(self, task_id, tc_rel_id, rounds, test_case_id):
        """从首轮 algorithmParams 提取声纹配置并执行注册"""
        from shared.clients.grpc_clients import algo_normalize_algorithm_params

        first_round_algo_params = {}
        if rounds and isinstance(rounds[0], dict):
            first_round_algo_params = algo_normalize_algorithm_params(rounds[0].get('algorithm_params', []))

        voiceprint_config = {
            'enabled': first_round_algo_params.get('voiceprint_enabled', False),
            'audio_id': first_round_algo_params.get('voiceprint_audio_id'),
            'playback_device_id': first_round_algo_params.get('voiceprint_playback_device_id'),
            'spl': first_round_algo_params.get('voiceprint_spl', 70.0),
            'wait_time': first_round_algo_params.get('voiceprint_wait_time', 5.0),
        }
        if voiceprint_config.get('enabled'):
            # 通过 ACL 仓储播放声纹
            if not PlaybackAclRepositoryImpl().play_voiceprint(voiceprint_config, task_id):
                self._log(level='ERROR', content='声纹注册失败，中止测试', task_id=task_id, test_case_id=test_case_id)
                self._update_tc_rel_status(tc_rel_id, task_id=task_id, execution_status='failed', status='failed', error_message='声纹注册失败')
                raise RuntimeError('声纹注册失败')
