"""
PlaybackOrchestrator - 音频播放编排器

统一处理主讲人、噪声、干扰人等音频类型的配置构建、设备绑定、
SPL 增益计算和时间轴调度，最终调用 AudioEngine 播放。

调用方只需传高层配置（round_config / preview_config），不再关心底层细节。

配置构建逻辑已拆分到 playback_config_builder.py。
"""

import os
import time
import threading

from backend.services.audio.audio_engine import (
    audio_service as _default_audio_service,
    build_audio_timelines,
    build_speakers_map_from_dry_audios,
    get_audio_configs_for_offset,
    calculate_speaker_aware_audio_delays,
    log_not_emit,
)
from backend.services.audio.playback_config_builder import (
    resolve_dry_audios,
    build_noise_info,
    build_dry_configs,
    build_noise_play_configs,
    build_interferer_configs,
    prepare_preview_playback_info,
    resolve_spl_gain,
    extract_overlap_rate,
    extract_overlap_time,
    find_device_obj,
    _resolve_audio_file_path,
)


class PlaybackOrchestrator:
    """
    音频播放编排器。

    职责：
    - 接收高层配置（round_config / preview_config）
    - 调用 playback_config_builder 构建各类音频配置
    - 调用 AudioEngine.play_overlap() 执行播放

    不包含：
    - PyAudio 流操作（在 AudioDriver）
    - 时间轴计算细节（在 audio_timeline 模块函数）
    - 配置构建细节（在 playback_config_builder 模块函数）
    """

    def __init__(self, audio_service=None):
        self.audio_service = audio_service or _default_audio_service

    # ------------------------------------------------------------------ #
    #                           高层 API                                  #
    # ------------------------------------------------------------------ #

    def play_round(self, round_config, task_id,
                   case_config=None, test_case_id=None, round_number=None):
        """
        播放一轮 E2E 测试音频（主讲人 + 噪声 + 干扰人）。

        Args:
            round_config: 本轮配置 dict，包含 audios / backgroundNoise / interferers / algorithmParams
            task_id: 任务ID
            case_config: 用例全局配置（用于 fallback 噪声配置）
            test_case_id: 测试用例关联ID
            round_number: 本轮轮次号（从1开始），用于日志区分不同轮次

        Returns:
            dict: {'audio_timelines': [...], 'playback_result': ...}
            失败返回 None
        """
        round_tag = f'R{round_number}' if round_number else 'R?'

        if not round_config:
            self._log('WARNING', f'[play_round {round_tag}] round_config is empty', task_id=task_id)
            return None

        try:
            # 1. 解析本轮音频配置
            audios = round_config.get('audios', [])
            dry_audios_info = resolve_dry_audios(audios, round_config)
            if not dry_audios_info:
                self._log('WARNING', f'[play_round {round_tag}] no valid dry audios', task_id=task_id)
                return None

            # 2. 解析噪声配置
            noise_audio_info, noise_devices = build_noise_info(round_config, case_config)

            # 3. 构建主讲人 audio_to_play 配置
            #    playback_device_id 指向 PlaybackDevice 表，build_dry_configs 内部从 DB 加载
            dry_configs, playback_devices_map = build_dry_configs(
                dry_audios_info, self.audio_service, task_id=task_id
            )
            if not dry_configs:
                self._log('WARNING', f'[play_round {round_tag}] no dry configs built', task_id=task_id)
                return None

            # 4. 构建噪声 audio_to_play 配置
            noise_configs = build_noise_play_configs(
                noise_audio_info, noise_devices, self.audio_service
            )

            # 5. 构建干扰人 audio_to_play 配置（从 algorithmParams 读取）
            from backend.utils.algorithm.case_parameter_extractor import _normalize_algorithm_params
            round_algo_params = _normalize_algorithm_params(round_config.get('algorithmParams', []))
            interferers = round_algo_params.get('interferers', [])
            interferer_configs = build_interferer_configs(
                task_id, interferers, self.audio_service
            )

            # 6. 构建时间轴（主讲人 + speaker 感知）
            app = self._get_flask_app()
            speakers_map = build_speakers_map_from_dry_audios(dry_audios_info, app=app)
            overlap_rate = extract_overlap_rate(case_config)
            overlap_time = extract_overlap_time(case_config)
            audio_timelines = build_audio_timelines(
                dry_audios_info, overlap_rate, overlap_time, speakers_map
            )

            # 7. 合并三类音频为统一 audio_to_play 列表
            audio_to_play = []
            audio_to_play.extend(noise_configs)
            audio_to_play.extend(dry_configs)
            audio_to_play.extend(interferer_configs)

            if not audio_to_play:
                self._log('WARNING', f'[play_round {round_tag}] no audio to play', task_id=task_id)
                return None

            self._log(
                'DEBUG',
                f'[play_round {round_tag}] dry={len(dry_configs)}, noise={len(noise_configs)}, '
                f'interferer={len(interferer_configs)}, total={len(audio_to_play)}',
                task_id=task_id,
            )

            # 8. 执行播放（同步等待，干声结束后停噪声）
            threads, playback_started_events, playback_finished_events = self.audio_service.play_overlap(
                task_id=task_id,
                audio_configs=audio_to_play,
                overlap_time=overlap_time,
                overlap_rate=overlap_rate,
                offset=0,
                loop=False,
                speakers_map=speakers_map,
                app=app,
            )

            total_duration = max((t.get('end', 0) for t in audio_timelines), default=0)
            actual_play_time = None
            actual_end_time = None
            if threads and total_duration > 0:
                # 等待音频真正开始播放（重采样等准备工作完成后）
                for evt in playback_started_events:
                    evt.wait(timeout=60)
                actual_play_time = time.time()
                self._log(
                    'DEBUG',
                    f'[play_round {round_tag}] waiting {total_duration}s for dry audio to finish',
                    task_id=task_id,
                )
                time.sleep(total_duration)
                self.audio_service.stop_task_audio(task_id)
                # 等待所有设备流真正关闭
                for evt in playback_finished_events:
                    evt.wait(timeout=10)
                actual_end_time = time.time()

            # 9. 给每条 timeline 加上 actual_play_time / actual_end_time（毫秒级时间戳）
            if actual_play_time is None:
                actual_play_time = time.time()
            if actual_end_time is None:
                actual_end_time = actual_play_time
            audio_delays = calculate_speaker_aware_audio_delays(
                audio_to_play, overlap_rate, overlap_time > 0, 0, overlap_time,
                speakers_map=speakers_map,
            )
            delay_map = {cfg.get('play_order', 0): d for cfg, d in audio_delays}

            for timeline in audio_timelines:
                play_order = timeline.get('config', {}).get('play_order', 0)
                timeline['actual_play_time'] = actual_play_time + delay_map.get(play_order, 0)
                timeline['actual_end_time'] = actual_end_time
                # 毫秒级时间戳，供设备驱动用于时延统计
                timeline['playback_start_time_ms'] = int(round(
                    (actual_play_time + delay_map.get(play_order, 0)) * 1000
                ))
                timeline['playback_end_time_ms'] = int(round(actual_end_time * 1000))

            return {
                'audio_timelines': audio_timelines,
                'playback_result': True,
            }

        except Exception as e:
            self._log('ERROR', f'[play_round {round_tag}] failed: {e}', task_id=task_id)
            return None

    def preview(self, audio_configs, case_config, task_id,
                offset=0, overlap_rate=0, overlap_time=0):
        """
        用例预览播放（testcase_controller 调用）。

        Args:
            audio_configs: 音频配置列表 [{'audio_id': xxx, 'playback_device_id': xxx}, ...]
            case_config: 用例配置
            task_id: 预览任务ID
            offset: 播放起始偏移（秒）
            overlap_rate: 重叠率
            overlap_time: 重叠时间（秒）

        Returns:
            dict: {'audio_timelines': [...], 'total_duration': float}
        """
        try:
            # 1. 解析干声/噪声
            dry_audios_info, noise_audio_info, dry_devices, noise_devices = (
                prepare_preview_playback_info(audio_configs, case_config)
            )
            if not dry_audios_info:
                self._log('WARNING', 'preview: no valid dry audios', task_id=task_id)
                return None

            # 2. 构建主讲人配置
            dry_configs, playback_devices_map = build_dry_configs(
                dry_audios_info, self.audio_service, task_id=task_id
            )

            # 3. 构建噪声配置
            noise_configs = build_noise_play_configs(
                noise_audio_info, noise_devices, self.audio_service
            )

            # 4. 时间轴
            app = self._get_flask_app()
            speakers_map = build_speakers_map_from_dry_audios(dry_audios_info, app=app)
            audio_timelines = build_audio_timelines(
                dry_audios_info, overlap_rate, overlap_time, speakers_map
            )

            # 5. 主讲人按 offset 切分
            offset_configs = get_audio_configs_for_offset(
                audio_timelines, offset, playback_devices_map,
                audio_service=self.audio_service, app=app,
            )

            audio_to_play = []
            # 噪声在预览场景也要循环
            for nc in noise_configs:
                nc['offset'] = offset
            audio_to_play.extend(noise_configs)
            audio_to_play.extend(offset_configs)

            if not audio_to_play:
                self._log('WARNING', 'preview: no audio to play', task_id=task_id)
                return None

            # 6. 播放（异步）
            threads, playback_started_events, playback_finished_events = self.audio_service.play_overlap(
                task_id=task_id,
                audio_configs=audio_to_play,
                overlap_time=overlap_time,
                overlap_rate=overlap_rate,
                offset=offset,
                loop=False,
                speakers_map=speakers_map,
                app=app,
            )

            total_duration = max((t.get('end', 0) for t in audio_timelines), default=0)

            # 7. timeline 加 actual_play_time（等待播放真正开始后再记录）
            for evt in playback_started_events:
                evt.wait(timeout=60)
            actual_play_time = time.time()
            # 预览场景为异步播放，不等待 finished；end_time 用 理论值估算
            actual_end_time = actual_play_time + total_duration
            audio_delays = calculate_speaker_aware_audio_delays(
                audio_to_play, overlap_rate, overlap_time > 0, offset, overlap_time,
                speakers_map=speakers_map,
            )
            delay_map = {cfg.get('play_order', 0): d for cfg, d in audio_delays}
            for timeline in audio_timelines:
                play_order = timeline.get('config', {}).get('play_order', 0)
                timeline['actual_play_time'] = actual_play_time + delay_map.get(play_order, 0)
                timeline['actual_end_time'] = actual_end_time
                timeline['playback_start_time_ms'] = int(round(
                    (actual_play_time + delay_map.get(play_order, 0)) * 1000
                ))
                timeline['playback_end_time_ms'] = int(round(actual_end_time * 1000))

            return {
                'audio_timelines': audio_timelines,
                'total_duration': total_duration,
            }

        except Exception as e:
            self._log('ERROR', f'preview failed: {e}', task_id=task_id)
            return None

    def play_voiceprint(self, vp_config, task_id):
        """
        播放声纹注册音频并等待注册完成。

        Args:
            vp_config: 声纹配置 dict，扁平结构:
                {enabled, audio_id, playback_device_id, spl, wait_time}
            task_id: 任务ID

        Returns:
            True: 注册成功 / 不需要注册
            False: 注册失败
        """
        if not vp_config or not vp_config.get('enabled'):
            return True

        from backend.models import db
        from backend.models.models import Audio, PlaybackDevice

        audio_id = vp_config.get('audio_id')
        playback_dev_id = vp_config.get('playback_device_id')
        spl = vp_config.get('spl', 70.0)
        wait_time_sec = float(vp_config.get('wait_time', 5.0))

        if not audio_id or not playback_dev_id:
            self._log('WARNING',
                      '声纹注册配置不完整 (缺少 audio_id 或 playback_device_id)，跳过',
                      task_id=task_id)
            return True

        # 从 DB 加载 PlaybackDevice ORM 对象
        dev_obj = None
        try:
            dev_obj = db.session.get(PlaybackDevice, playback_dev_id)
        except Exception:
            dev_obj = None
        if not dev_obj:
            self._log('ERROR',
                      f'声纹注册播放设备 (id={playback_dev_id}) 未找到',
                      task_id=task_id)
            return False

        try:
            audio_obj = db.session.get(Audio, audio_id)
        except Exception:
            audio_obj = None

        if not audio_obj or not audio_obj.file_path:
            self._log('ERROR',
                      f'声纹注册音频 (id={audio_id}) 不存在或无文件路径',
                      task_id=task_id)
            return False

        try:
            device_unique_id = getattr(dev_obj, 'device_unique_id', None)
            channel_index = getattr(dev_obj, 'channel_index', 0)
            spl_mapping_id = getattr(dev_obj, 'current_spl_mapping_id', None)
            device_index = (
                self.audio_service.get_device_index(device_unique_id) if device_unique_id else 0
            )
            if device_index is None:
                self._log('ERROR',
                          f'声纹注册: 无法获取设备索引 (unique_id={device_unique_id})',
                          task_id=task_id)
                return False

            gain = resolve_spl_gain(spl_mapping_id, spl)

            audio_config = {
                'file': audio_obj.file_path,
                'device_index': device_index,
                'channel': channel_index,
                'gain': gain,
                'delay': 0,
                'is_noise': False,
                'loop': False,
                'type': 'dry',
            }

            self._log('INFO',
                      f'开始声纹注册: 播放 {audio_obj.name or audio_obj.file_path} '
                      f'(spl={spl}, gain={gain:.3f})',
                      task_id=task_id)

            _, playback_started_events, _ = self.audio_service.play_overlap(
                task_id=task_id,
                audio_configs=[audio_config],
                overlap_time=0,
                overlap_rate=0,
                offset=0,
                loop=False,
            )

            # 等待音频真正开始播放后再开始计时
            for evt in playback_started_events:
                evt.wait(timeout=60)

            self._log('INFO',
                      f'声纹注册等待 {wait_time_sec}s',
                      task_id=task_id)
            time.sleep(wait_time_sec)

            self._log('INFO', '声纹注册完成', task_id=task_id)
            return True

        except Exception as e:
            self._log('ERROR', f'声纹注册失败: {e}', task_id=task_id)
            return False

    # ------------------------------------------------------------------ #
    #                        内部：工具方法                                 #
    # ------------------------------------------------------------------ #

    def _get_flask_app(self):
        try:
            from flask import current_app
            return current_app._get_current_object()
        except Exception:
            return None

    # 委托方法，保持向后兼容
    def _find_device_obj(self, device_id, devices):
        return find_device_obj(device_id, devices)

    def _resolve_spl_gain(self, spl_mapping_id, target_spl):
        return resolve_spl_gain(spl_mapping_id, target_spl, app=self._get_flask_app())

    def _extract_overlap_rate(self, case_config):
        return extract_overlap_rate(case_config)

    def _extract_overlap_time(self, case_config):
        return extract_overlap_time(case_config)

    def _log(self, level, content, task_id=None, **kwargs):
        log_not_emit(level, 'playback_orchestrator', content, task_id=task_id, category='audio')


# 模块级单例
playback_orchestrator = PlaybackOrchestrator()
