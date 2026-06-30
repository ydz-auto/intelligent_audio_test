"""
PlaybackOrchestrator - 音频播放编排器

统一处理主讲人、噪声、干扰人等音频类型的配置构建、设备绑定、
SPL 增益计算和时间轴调度，最终调用 AudioEngine 播放。

调用方只需传高层配置（round_config / preview_config），不再关心底层细节。
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
    log_and_emit,
)


def _resolve_audio_file_path(audio_info, audio_obj=None):
    """从 audio_info 或 Audio 对象中解析音频文件路径"""
    path = audio_info.get('path') or audio_info.get('file_path')
    if path:
        return path
    if audio_obj and getattr(audio_obj, 'file_path', None):
        return audio_obj.file_path
    return None


class PlaybackOrchestrator:
    """
    音频播放编排器。

    职责：
    - 接收高层配置（round_config / preview_config）
    - 内部统一构建主讲人、噪声、干扰人的 audio_to_play 配置
    - 调用 AudioEngine.play_overlap() 执行播放

    不包含：
    - PyAudio 流操作（在 AudioDriver）
    - 时间轴计算细节（在 audio_engine 模块函数）
    """

    def __init__(self, audio_service=None):
        self.audio_service = audio_service or _default_audio_service

    # ------------------------------------------------------------------ #
    #                           高层 API                                  #
    # ------------------------------------------------------------------ #

    def play_round(self, round_config, device_info_list, task_id,
                   case_config=None, test_case_id=None):
        """
        播放一轮 E2E 测试音频（主讲人 + 噪声 + 干扰人）。

        Args:
            round_config: 本轮配置 dict，包含 audios / backgroundNoise / interferers / algorithmParams
            device_info_list: 可用设备信息列表
            task_id: 任务ID
            case_config: 用例全局配置（用于 fallback 噪声配置）
            test_case_id: 测试用例关联ID

        Returns:
            dict: {'audio_timelines': [...], 'playback_result': ...}
            失败返回 None
        """
        if not round_config:
            self._log('WARNING', 'play_round: round_config is empty', task_id=task_id)
            return None

        try:
            # 1. 解析本轮音频配置
            audios = round_config.get('audios', [])
            dry_audios_info = self._resolve_dry_audios(audios, round_config)
            if not dry_audios_info:
                self._log('WARNING', 'play_round: no valid dry audios', task_id=task_id)
                return None

            # 2. 解析噪声配置
            noise_audio_info, noise_devices = self._build_noise_info(round_config, case_config)

            # 3. 构建主讲人 audio_to_play 配置
            dry_configs, playback_devices_map = self._build_dry_configs(
                dry_audios_info, device_info_list
            )
            if not dry_configs:
                self._log('WARNING', 'play_round: no dry configs built', task_id=task_id)
                return None

            # 4. 构建噪声 audio_to_play 配置
            noise_configs = self._build_noise_play_configs(
                noise_audio_info, noise_devices, device_info_list
            )

            # 5. 构建干扰人 audio_to_play 配置
            interferer_configs = self._build_interferer_configs(
                task_id, round_config.get('interferers', []), device_info_list
            )

            # 6. 构建时间轴（主讲人 + speaker 感知）
            app = self._get_flask_app()
            speakers_map = build_speakers_map_from_dry_audios(dry_audios_info, app=app)
            overlap_rate = self._extract_overlap_rate(case_config)
            overlap_time = self._extract_overlap_time(case_config)
            audio_timelines = build_audio_timelines(
                dry_audios_info, overlap_rate, overlap_time, speakers_map
            )

            # 7. 合并三类音频为统一 audio_to_play 列表
            audio_to_play = []
            audio_to_play.extend(noise_configs)
            audio_to_play.extend(dry_configs)
            audio_to_play.extend(interferer_configs)

            if not audio_to_play:
                self._log('WARNING', 'play_round: no audio to play', task_id=task_id)
                return None

            self._log(
                'DEBUG',
                f'[play_round] dry={len(dry_configs)}, noise={len(noise_configs)}, '
                f'interferer={len(interferer_configs)}, total={len(audio_to_play)}',
                task_id=task_id,
            )

            # 8. 执行播放（同步等待，干声结束后停噪声）
            threads = self.audio_service.play_overlap(
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
            if threads and total_duration > 0:
                self._log(
                    'DEBUG',
                    f'[play_round] waiting {total_duration}s for dry audio to finish',
                    task_id=task_id,
                )
                time.sleep(total_duration)
                self.audio_service.stop_task_audio(task_id)

            # 9. 给每条 timeline 加上 actual_play_time
            actual_play_time = time.time()
            audio_delays = calculate_speaker_aware_audio_delays(
                audio_to_play, overlap_rate, overlap_time > 0, 0, overlap_time,
                speakers_map=speakers_map,
            )
            delay_map = {cfg.get('play_order', 0): d for cfg, d in audio_delays}

            for timeline in audio_timelines:
                play_order = timeline.get('config', {}).get('play_order', 0)
                timeline['actual_play_time'] = actual_play_time + delay_map.get(play_order, 0)

            return {
                'audio_timelines': audio_timelines,
                'playback_result': True,
            }

        except Exception as e:
            self._log('ERROR', f'play_round failed: {e}', task_id=task_id)
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
                self._prepare_preview_playback_info(audio_configs, case_config)
            )
            if not dry_audios_info:
                self._log('WARNING', 'preview: no valid dry audios', task_id=task_id)
                return None

            # 2. 构建主讲人配置
            dry_configs, playback_devices_map = self._build_dry_configs(
                dry_audios_info, [d for d in dry_devices]
            )

            # 3. 构建噪声配置
            noise_configs = self._build_noise_play_configs(
                noise_audio_info, noise_devices, [d for d in noise_devices] if noise_devices else []
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
            threads = self.audio_service.play_overlap(
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

            # 7. timeline 加 actual_play_time
            actual_play_time = time.time()
            audio_delays = calculate_speaker_aware_audio_delays(
                audio_to_play, overlap_rate, overlap_time > 0, offset, overlap_time,
                speakers_map=speakers_map,
            )
            delay_map = {cfg.get('play_order', 0): d for cfg, d in audio_delays}
            for timeline in audio_timelines:
                play_order = timeline.get('config', {}).get('play_order', 0)
                timeline['actual_play_time'] = actual_play_time + delay_map.get(play_order, 0)

            return {
                'audio_timelines': audio_timelines,
                'total_duration': total_duration,
            }

        except Exception as e:
            self._log('ERROR', f'preview failed: {e}', task_id=task_id)
            return None

    def play_voiceprint(self, vp_config, device_info_list, task_id):
        """
        播放声纹注册音频并等待注册完成。

        Args:
            vp_config: 声纹配置 dict (case_config.voiceprint_config)
            device_info_list: 可用设备信息列表
            task_id: 任务ID

        Returns:
            True: 注册成功 / 不需要注册
            False: 注册失败
        """
        if not vp_config or not vp_config.get('enabled'):
            return True

        from backend.models import db
        from backend.models.models import Audio

        audio_info = vp_config.get('audio', {})
        device_cfg = vp_config.get('device', {})
        spl = vp_config.get('spl')
        wait_time_ms = int(vp_config.get('waitTime', 3000))

        audio_id = audio_info.get('id')
        device_id = device_cfg.get('id')

        if not audio_id or not device_id:
            self._log('WARNING',
                      '声纹注册配置不完整 (缺少 audio.id 或 device.id)，跳过',
                      task_id=task_id)
            return True

        target_info = next((d for d in device_info_list if d.get('device_id') == device_id), None)
        if target_info is None:
            self._log('ERROR',
                      f'声纹注册设备 (id={device_id}, name={device_cfg.get("name")}) 未找到',
                      task_id=task_id)
            return False

        driver = target_info.get('driver')
        device_sn = target_info.get('device_sn')

        try:
            audio_obj = db.session.get(Audio, audio_id)
        except Exception:
            audio_obj = None

        if not audio_obj or not audio_obj.file_path:
            self._log('ERROR',
                      f'声纹注册音频 (id={audio_id}) 不存在或无文件路径',
                      task_id=task_id)
            return False

        original_volume = None
        try:
            if driver and device_sn and spl:
                try:
                    original_volume = driver.get_volume(device_sn)
                    driver.set_volume(device_sn, int(spl))
                    self._log('INFO',
                              f'声纹注册: 设备 {device_sn} 音量已设为 {spl}',
                              task_id=task_id)
                except Exception as e:
                    self._log('WARNING', f'声纹注册: 音量控制失败: {e}', task_id=task_id)

            device_unique_id = target_info.get('device_unique_id')
            channel_index = target_info.get('channel_index', 0)
            device_index = (
                self.audio_service.get_device_index(device_unique_id) if device_unique_id else 0
            )
            if device_index is None:
                self._log('ERROR',
                          f'声纹注册: 无法获取设备索引 (unique_id={device_unique_id})',
                          task_id=task_id)
                return False

            audio_config = {
                'file': audio_obj.file_path,
                'device_index': device_index,
                'channel': channel_index,
                'gain': 1.0,
                'delay': 0,
                'is_noise': False,
                'loop': False,
                'type': 'dry',
            }

            self._log('INFO',
                      f'开始声纹注册: 播放 {audio_info.get("name", audio_obj.file_path)}',
                      task_id=task_id)

            self.audio_service.play_overlap(
                task_id=task_id,
                audio_configs=[audio_config],
                overlap_time=0,
                overlap_rate=0,
                offset=0,
                loop=False,
            )

            wait_seconds = wait_time_ms / 1000.0
            time.sleep(wait_seconds)

            self._log('INFO',
                      f'声纹注册完成 (等待 {wait_seconds}s)',
                      task_id=task_id)
            return True

        except Exception as e:
            self._log('ERROR', f'声纹注册失败: {e}', task_id=task_id)
            return False

        finally:
            if original_volume is not None and driver and device_sn:
                try:
                    driver.set_volume(device_sn, original_volume)
                except Exception:
                    pass

    # ------------------------------------------------------------------ #
    #                        内部：配置构建                                 #
    # ------------------------------------------------------------------ #

    def _resolve_dry_audios(self, audios, round_config):
        """从 audios 列表解析出 [(audio_config, audio_obj), ...]，仅保留干声。"""
        from backend.models import db
        from backend.models.models import Audio

        result = []
        for audio_config in audios or []:
            audio_id = audio_config.get('audio_id')
            if not audio_id:
                continue
            try:
                audio_obj = db.session.get(Audio, audio_id)
            except Exception:
                audio_obj = None
            if not audio_obj or getattr(audio_obj, 'audio_type', None) == 'noise':
                continue
            result.append((audio_config, audio_obj))

        result.sort(key=lambda x: x[0].get('play_order', 0))
        return result

    def _build_noise_info(self, round_config, case_config):
        """解析本轮噪声 audio_info + 噪声设备列表。"""
        from backend.models import db
        from backend.models.models import Audio, PlaybackDevice

        bg_noise = round_config.get('backgroundNoise') or {}
        if not bg_noise and case_config:
            bg_noise = (case_config.get('background_noise') or {})

        noise_audio = None
        noise_spl = 0
        audio_id = bg_noise.get('audio_id') or bg_noise.get('audioId')
        if audio_id:
            try:
                noise_audio = db.session.get(Audio, audio_id)
            except Exception:
                noise_audio = None
            noise_spl = bg_noise.get('spl', 0)

        device_ids = bg_noise.get('device_ids') or bg_noise.get('deviceIds') or []
        noise_devices = []
        for did in device_ids:
            dev = None
            try:
                if isinstance(did, str):
                    dev = PlaybackDevice.query.filter_by(
                        device_unique_id=did, is_deleted=0
                    ).first()
                else:
                    dev = db.session.get(PlaybackDevice, did)
            except Exception:
                dev = None
            if dev:
                noise_devices.append(dev)

        if noise_audio and noise_devices:
            return ({'spl': noise_spl, 'audio_id': getattr(noise_audio, 'id', None)},
                    noise_audio), noise_devices
        return None, noise_devices

    def _build_dry_configs(self, dry_audios_info, device_info_list_or_objs):
        """
        构建主讲人 audio_to_play 配置。

        Returns:
            (configs, playback_devices_map)
        """
        playback_devices_map = {}
        configs = []

        for audio_config, audio_obj in dry_audios_info:
            file_path = getattr(audio_obj, 'file_path', None) or audio_config.get('file_path')
            if not file_path:
                continue

            playback_dev_id = audio_config.get('playback_device_id')
            if not playback_dev_id:
                continue

            dev_obj = self._find_device_obj(playback_dev_id, device_info_list_or_objs)
            if not dev_obj:
                continue

            dev_id = dev_obj.id if hasattr(dev_obj, 'id') else dev_obj.get('id')
            dev_unique_id = (
                dev_obj.device_unique_id if hasattr(dev_obj, 'device_unique_id')
                else dev_obj.get('device_unique_id')
            )
            channel_index = (
                dev_obj.channel_index if hasattr(dev_obj, 'channel_index')
                else dev_obj.get('channel_index', 0)
            )
            spl_mapping_id = (
                dev_obj.current_spl_mapping_id if hasattr(dev_obj, 'current_spl_mapping_id')
                else dev_obj.get('current_spl_mapping_id')
            )
            device_index = self.audio_service.get_device_index(dev_unique_id) if dev_unique_id else None
            if device_index is None:
                continue

            gain = self._resolve_spl_gain(spl_mapping_id, audio_config.get('spl', 65.0))

            if dev_id not in playback_devices_map:
                playback_devices_map[dev_id] = {
                    'device_obj': dev_obj,
                    'device_index': device_index,
                    'channel_index': channel_index,
                    'gain': 1.0,
                    'name': dev_obj.name if hasattr(dev_obj, 'name') else dev_obj.get('name', ''),
                    'current_spl_mapping_id': spl_mapping_id,
                }

            configs.append({
                'file': file_path,
                'device_index': device_index,
                'channel': channel_index,
                'gain': gain,
                'offset': 0,
                'duration': getattr(audio_obj, 'duration', 0) or 0,
                'play_order': audio_config.get('play_order', 0),
                'loop': False,
                'is_noise': False,
                'type': 'dry',
                'audio_id': audio_config.get('audio_id'),
            })

        return configs, playback_devices_map

    def _build_noise_play_configs(self, noise_audio_info, noise_devices, device_info_list_or_objs):
        """构建噪声 audio_to_play 配置列表。"""
        if not noise_audio_info or not noise_devices:
            return []

        n_config, n_audio = noise_audio_info
        file_path = (
            n_audio.file_path if hasattr(n_audio, 'file_path') else n_audio.get('file_path')
        )
        noise_spl = n_config.get('spl', 60) if n_config else 60

        configs = []
        for n_dev in noise_devices:
            dev_unique_id = (
                n_dev.device_unique_id if hasattr(n_dev, 'device_unique_id')
                else n_dev.get('device_unique_id')
            )
            channel_index = (
                n_dev.channel_index if hasattr(n_dev, 'channel_index')
                else n_dev.get('channel_index', 0)
            )
            spl_mapping_id = (
                n_dev.current_spl_mapping_id if hasattr(n_dev, 'current_spl_mapping_id')
                else n_dev.get('current_spl_mapping_id')
            )
            n_gain = self._resolve_spl_gain(spl_mapping_id, noise_spl)
            device_index = self.audio_service.get_device_index(dev_unique_id) if dev_unique_id else None
            if device_index is None:
                continue

            configs.append({
                'file': file_path,
                'device_index': device_index,
                'channel': channel_index,
                'gain': n_gain,
                'offset': 0,
                'duration': getattr(n_audio, 'duration', 0) or 0,
                'play_order': 0,
                'loop': True,
                'is_noise': True,
                'type': 'noise',
            })

        return configs

    def _build_interferer_configs(self, task_id, interferer_config, device_info_list):
        """
        构建干扰人 audio_to_play 配置。

        语义：
        - type='interferer'：不参与主讲人交叠时间轴
        - is_noise=False：音频类型为人声
        - loop：控制是否循环播放（独立字段）
        - delay：保留 startDelay（ms 转 s）
        """
        if not interferer_config:
            return []

        from backend.models import db
        from backend.models.models import Audio

        audio_to_play = []

        for idx, interferer in enumerate(interferer_config):
            if not isinstance(interferer, dict):
                continue

            audio_info = interferer.get('audio')
            device_cfg = interferer.get('device')
            spl = interferer.get('spl')
            start_delay_ms = interferer.get('startDelay', 0)
            loop = interferer.get('loop', False)

            if not audio_info or not device_cfg:
                self._log(
                    'WARNING',
                    f'干扰人 {idx} 配置不完整 (缺少 audio 或 device)，跳过',
                    task_id=task_id,
                )
                continue

            device_id = device_cfg.get('id')
            target_info = next(
                (d for d in device_info_list if d.get('device_id') == device_id), None
            )
            if target_info is None:
                self._log(
                    'WARNING',
                    f'干扰人 {idx} 设备 (id={device_id}, name={device_cfg.get("name")}) 未找到，跳过',
                    task_id=task_id,
                )
                continue

            device_unique_id = target_info.get('device_unique_id')
            channel_index = target_info.get('channel_index', 0)
            device_index = (
                self.audio_service.get_device_index(device_unique_id) if device_unique_id else None
            )
            if device_index is None:
                self._log(
                    'WARNING',
                    f'干扰人 {idx} 无法获取设备索引 (unique_id={device_unique_id})，跳过',
                    task_id=task_id,
                )
                continue

            spl_mapping_id = target_info.get('current_spl_mapping_id')
            gain = self._resolve_spl_gain(spl_mapping_id, spl) if spl_mapping_id and spl else 1.0

            file_path = _resolve_audio_file_path(audio_info)
            if not file_path and audio_info.get('id'):
                try:
                    audio_obj = db.session.get(Audio, audio_info['id'])
                    if audio_obj:
                        file_path = audio_obj.file_path
                except Exception:
                    pass

            if not file_path:
                self._log(
                    'WARNING',
                    f'干扰人 {idx} 音频文件路径为空，跳过',
                    task_id=task_id,
                )
                continue

            audio_to_play.append({
                'file': file_path,
                'device_index': device_index,
                'channel': channel_index,
                'gain': gain,
                'delay': start_delay_ms / 1000.0,
                'loop': bool(loop),
                'is_noise': False,
                'type': 'interferer',
            })

        if audio_to_play:
            self._log(
                'INFO',
                f'构建了 {len(audio_to_play)} 个干扰人音频配置',
                task_id=task_id,
            )

        return audio_to_play

    # ------------------------------------------------------------------ #
    #                        内部：工具方法                                 #
    # ------------------------------------------------------------------ #

    def _prepare_preview_playback_info(self, audio_configs, case_config):
        """为 preview 场景分类干声/噪声音频及设备。"""
        from backend.models import db
        from backend.models.models import Audio, PlaybackDevice

        dry_audios_info = []
        noise_case_audio_info = None

        for audio_config in audio_configs or []:
            audio_id = audio_config.get('audio_id')
            if not audio_id:
                continue
            try:
                audio = db.session.get(Audio, audio_id)
            except Exception:
                audio = None
            if not audio:
                continue
            if getattr(audio, 'audio_type', None) == 'noise':
                noise_case_audio_info = (audio_config, audio)
            else:
                dry_audios_info.append((audio_config, audio))

        if not dry_audios_info:
            return [], None, [], []

        dry_audios_info.sort(key=lambda x: x[0].get('play_order', 0))

        device_ids_seen = set()
        dry_devices = []
        for audio_config, _ in dry_audios_info:
            pid = audio_config.get('playback_device_id')
            if pid and pid not in device_ids_seen:
                try:
                    dev = db.session.get(PlaybackDevice, pid)
                except Exception:
                    dev = None
                if dev:
                    dry_devices.append(dev)
                    device_ids_seen.add(pid)

        noise_audio = None
        noise_spl = 0
        if noise_case_audio_info:
            n_ca, n_audio = noise_case_audio_info
            noise_audio = n_audio
            noise_spl = n_ca.get('spl', 0)
        elif case_config and case_config.get('background_noise', {}).get('audio_id'):
            bg = case_config['background_noise']
            try:
                noise_audio = db.session.get(Audio, bg['audio_id'])
            except Exception:
                noise_audio = None
            noise_spl = bg.get('spl', 0)

        device_ids = []
        if case_config:
            device_ids = (case_config.get('background_noise') or {}).get('device_ids', [])
        all_noise_devices = []
        for did in device_ids:
            try:
                if isinstance(did, str):
                    dev = PlaybackDevice.query.filter_by(
                        device_unique_id=did, is_deleted=0
                    ).first()
                else:
                    dev = db.session.get(PlaybackDevice, did)
            except Exception:
                dev = None
            if dev:
                all_noise_devices.append(dev)

        noise_audio_info = None
        if noise_audio and all_noise_devices:
            noise_audio_info = (
                {'spl': noise_spl, 'audio_id': getattr(noise_audio, 'id', None)},
                noise_audio,
            )

        return dry_audios_info, noise_audio_info, dry_devices, all_noise_devices

    def _find_device_obj(self, device_id, device_info_list_or_objs):
        """兼容 dict 列表和 ORM 对象列表，按 ID 查找设备。"""
        for dev in device_info_list_or_objs or []:
            if dev is None:
                continue
            if isinstance(dev, dict):
                if dev.get('device_id') == device_id or dev.get('id') == device_id:
                    return dev
            else:
                dev_id = getattr(dev, 'id', None)
                if dev_id is not None and dev_id == device_id:
                    return dev
                if getattr(dev, 'device_id', None) == device_id:
                    return dev
        return None

    def _resolve_spl_gain(self, spl_mapping_id, target_spl):
        """通过 SPL mapping 把声压级转成软件增益。"""
        if not spl_mapping_id:
            return 1.0
        try:
            from backend.services.audio.spl_service import spl_service
            return spl_service.spl_to_gain(spl_mapping_id, target_spl, app=self._get_flask_app())
        except Exception:
            return 1.0

    def _extract_overlap_rate(self, case_config):
        if not case_config:
            return 0
        try:
            from backend.utils.algorithm.case_parameter_extractor import CaseParameterExtractor
            return CaseParameterExtractor.get_overlap_rate(case_config)
        except Exception:
            return 0

    def _extract_overlap_time(self, case_config):
        if not case_config:
            return 0
        try:
            from backend.utils.algorithm.case_parameter_extractor import CaseParameterExtractor
            return CaseParameterExtractor.get_overlap_time(case_config)
        except Exception:
            return 0

    def _get_flask_app(self):
        try:
            from flask import current_app
            return current_app._get_current_object()
        except Exception:
            return None

    def _log(self, level, content, task_id=None, **kwargs):
        log_and_emit(level, 'playback_orchestrator', content, task_id=task_id, category='audio')


# 模块级单例
playback_orchestrator = PlaybackOrchestrator()