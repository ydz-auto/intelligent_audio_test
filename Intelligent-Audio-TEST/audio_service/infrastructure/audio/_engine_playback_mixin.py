# -*- coding: utf-8 -*-
"""音频引擎 - 播放控制 Mixin

从 audio_engine.py 拆分出的职责：
- play_audio：单文件播放
- _play_device_audios：单设备多音频播放（线程池任务函数）
- play_overlap：重叠/交叠播放编排
- stop_task_audio / stop_task_audio_by_pattern：停止播放控制
"""
import threading
import wave

from shared.utils.log_handler import log_and_emit
from audio_service.infrastructure.audio.audio_timeline import (
    calculate_overlap_time,
    calculate_speaker_aware_audio_delays,
    calculate_audio_delays,
    is_overlap_playback,
)


class EnginePlaybackMixin:
    """多通道播放控制与停止职责"""

    def play_audio(self, task_id, file_path, device_index=None, channel_index=0, gain=1.0, loop=False, player_type='dry', offset=0, parent_stop_event=None):
        task_id = str(task_id)
        player_type = str(player_type) if player_type is not None else "dry"
        stop_event = threading.Event()

        audio_configs = [{
            'file': file_path,
            'channel': channel_index,
            'gain': gain,
            'offset': offset,
            'is_noise': False
        }]

        pool = self._get_audio_pool()
        future = pool.submit(
            self._get_driver().play_multi,
            audio_configs, device_index, stop_event, offset, loop
        )

        if task_id not in self.active_players:
            self.active_players[task_id] = {}

        self.active_players[task_id][player_type] = {
            "future": future,
            "stop_event": stop_event
        }

        # 播放完成后自动清理注册表，避免任务结束后条目常驻导致内存泄漏
        def _cleanup_after_done(_fut, _task_id=task_id, _player_type=player_type):
            players = self.active_players.get(_task_id)
            if players is not None:
                entry = players.get(_player_type)
                if entry is not None and entry.get('future') is _fut:
                    players.pop(_player_type, None)
                    if not players:
                        self.active_players.pop(_task_id, None)

        future.add_done_callback(_cleanup_after_done)

        return future

    def _play_device_audios(self, device_index, audio_list_with_delays, initial_delay,
                            offset=0, loop=False, stop_event=None, is_overlap=False, app=None,
                            playback_started_event=None, playback_finished_event=None):
        """在单个设备上播放多个音频（线程池任务函数）。"""
        try:
            audio_list = [c for c, d in audio_list_with_delays]

            log_and_emit('DEBUG', 'audio_engine', f"[play_device_audios] Device {device_index} ENTRY: total={len(audio_list)}, initial_delay={initial_delay}, offset={offset}, loop={loop}, is_overlap={is_overlap}", category='audio')
            for i, c in enumerate(audio_list):
                delay_val = audio_list_with_delays[i][1] if i < len(audio_list_with_delays) else 0
                log_and_emit('DEBUG', 'audio_engine', f"[play_device_audios]   audio[{i}]: file={c.get('file', '')}, is_noise={c.get('is_noise')}, delay={delay_val}, channel={c.get('channel')}, gain={c.get('gain', 1.0)}", category='audio')

            log_and_emit('DEBUG', 'audio_engine', f"[play_device_audios] Device {device_index}: total={len(audio_list)}, initial_delay={initial_delay}, loop={loop}", category='audio')

            multi_configs = []
            for config, delay in audio_list_with_delays:
                is_noise = config.get('is_noise', False)
                audio_offset = offset if is_noise else 0

                log_and_emit('DEBUG', 'audio_engine', f"[play_device_audios] Audio: file={config['file']}, is_noise={is_noise}, delay={delay}, audio_offset={audio_offset}", category='audio')

                multi_configs.append({
                    'file': config['file'],
                    'channel': config.get('channel', 0),
                    'gain': config.get('gain', 1.0),
                    'offset': audio_offset,
                    'is_noise': is_noise,
                    'delay': delay
                })

            log_and_emit('DEBUG', 'audio_engine', f"[play_device_audios] Before play_multi: configs count={len(multi_configs)}, delays={[c.get('delay') for c in multi_configs]}, files={[c.get('file', '').split('\\\\')[-1] for c in multi_configs]}", category='audio')
            self._get_driver().play_multi(multi_configs, device_index, stop_event, loop=loop, app=app, playback_started_event=playback_started_event, playback_finished_event=playback_finished_event)

            log_and_emit('DEBUG', 'audio_engine', f"[play_device_audios] Device {device_index} done")
        except Exception as e:
            log_and_emit('ERROR', 'audio_engine', f"[play_device_audios] Error: {e}")

    def play_overlap(self, task_id, audio_configs, overlap_rate=0.5, overlap_time=0, offset=0, loop=False, speakers_map=None, app=None):
        """
        重叠播放多个音频文件

        Args:
            task_id: 任务ID
            audio_configs: 音频配置列表，每个元素为 dict:
                {
                    'file': 文件路径,
                    'device_index': 设备索引,
                    'channel': 通道索引,
                    'gain': 音量增益,
                    'is_noise': 是否为噪声音频（噪声强制循环播放）
                }
            overlap_time: 重叠时间（秒），优先级高于 overlap_rate
            overlap_rate: 重叠率 (0.0-1.0)，当 overlap_time > 0 时被忽略
            offset: 播放起始位置（秒）
            loop: 干声是否循环播放（默认 False，噪声不受此参数影响）
            speakers_map: speaker集合映射 {audio_id: set(speakers)}，用于speaker感知交叠播放
            app: Flask应用实例，用于在后台线程中获取配置
        """
        if not audio_configs or len(audio_configs) < 1:
            return [], [], []

        dry_audio_files = [c for c in audio_configs
                           if not c.get('is_noise', False) and c.get('type') != 'interferer']
        if not dry_audio_files:
            return [], [], []

        overlap_time_value = calculate_overlap_time(
            dry_audio_files[0]['file'],
            overlap_time,
            overlap_rate
        )

        if overlap_time_value < 0:
            return [], [], []

        is_overlap = is_overlap_playback(overlap_time, overlap_rate)

        dry_audio_durations = []
        dry_audio_files_sorted = sorted(dry_audio_files, key=lambda x: x.get('play_order', 0))
        for config in dry_audio_files_sorted:
            try:
                with wave.open(config['file'], 'rb') as wf:
                    duration = wf.getnframes() / wf.getframerate()
                    dry_audio_durations.append(duration)
            except:
                dry_audio_durations.append(0)

        log_and_emit('DEBUG', 'audio_engine', f"[play_overlap] CALCULATED: overlap_time={overlap_time}, overlap_rate={overlap_rate}, overlap_time_value={overlap_time_value}, is_overlap={is_overlap}, audio_count={len(audio_configs)}, dry_durations={dry_audio_durations}", category='audio')

        task_id = str(task_id)

        if task_id not in self.active_players:
            self.active_players[task_id] = {}

        # 计算 delay
        if speakers_map is not None:
            audio_delays_with_config = calculate_speaker_aware_audio_delays(
                audio_configs, overlap_rate, is_overlap, offset, overlap_time_value, speakers_map=speakers_map
            )
        else:
            audio_delays_with_config = calculate_audio_delays(
                audio_configs, overlap_rate, is_overlap, offset, overlap_time_value
            )

        # 按设备分组
        device_audio_map = {}
        for config, delay in audio_delays_with_config:
            dev_idx = config['device_index']
            if dev_idx not in device_audio_map:
                device_audio_map[dev_idx] = []
            device_audio_map[dev_idx].append((config, delay))

        log_and_emit('DEBUG', 'audio_engine', f"[play_overlap] device_audio_map: {[(f'dev{k}', [(c.get('file', '').split('\\\\')[-1], c.get('is_noise'), d) for c, d in v]) for k, v in device_audio_map.items()]}", category='audio')

        # 提交到线程池
        futures = []
        playback_started_events = []
        playback_finished_events = []
        pool = self._get_audio_pool()

        for dev_idx in device_audio_map:
            audio_list_with_delays = device_audio_map[dev_idx]

            device_stop_event = threading.Event()
            playback_started_event = threading.Event()
            playback_finished_event = threading.Event()
            future = pool.submit(
                self._play_device_audios,
                dev_idx, audio_list_with_delays, 0, offset, loop, device_stop_event, is_overlap, app,
                playback_started_event, playback_finished_event
            )

            self.active_players[task_id][f'device_{dev_idx}'] = {
                "future": future,
                "stop_event": device_stop_event,
                "playback_started_event": playback_started_event,
                "playback_finished_event": playback_finished_event,
            }

            # 播放完成后自动清理注册表，避免 device_* 条目任务结束后常驻导致内存泄漏
            def _cleanup_after_done(_fut, _dev_idx=dev_idx):
                players = self.active_players.get(task_id)
                if players is not None:
                    entry = players.get(f'device_{_dev_idx}')
                    if entry is not None and entry.get('future') is _fut:
                        players.pop(f'device_{_dev_idx}', None)
                        if not players:
                            self.active_players.pop(task_id, None)

            future.add_done_callback(_cleanup_after_done)

            futures.append(future)
            playback_started_events.append(playback_started_event)
            playback_finished_events.append(playback_finished_event)

        return futures, playback_started_events, playback_finished_events

    def stop_task_audio(self, task_id, player_type=None):
        log_and_emit('DEBUG', 'audio_engine', f"[stop_task_audio] Called: task_id={task_id}, player_type={player_type}", category='audio')

        task_id_key = task_id
        if task_id_key not in self.active_players and task_id is not None:
            task_id_key = str(task_id)
        if task_id_key not in self.active_players and isinstance(task_id, str) and task_id.isdigit():
            int_key = int(task_id)
            if int_key in self.active_players:
                task_id_key = int_key

        log_and_emit('DEBUG', 'audio_engine', f"[stop_task_audio] task_id_key={task_id_key}, active_players keys={list(self.active_players.keys()) if hasattr(self, 'active_players') else 'N/A'}", category='audio')

        if task_id_key in self.active_players:
            log_and_emit('DEBUG', 'audio_engine', f"[stop_task_audio] Found active_players[{task_id_key}], keys={list(self.active_players[task_id_key].keys())}", category='audio')

            if player_type:
                player_type = str(player_type)
                if player_type.endswith('*'):
                    prefix = player_type[:-1]
                    for p_type in list(self.active_players[task_id_key].keys()):
                        if p_type.startswith(prefix):
                            self.active_players[task_id_key][p_type]["stop_event"].set()
                            del self.active_players[task_id_key][p_type]
                    if not self.active_players[task_id_key]:
                        del self.active_players[task_id_key]
                elif player_type in self.active_players[task_id_key]:
                    self.active_players[task_id_key][player_type]["stop_event"].set()
                    del self.active_players[task_id_key][player_type]
                    if not self.active_players[task_id_key]:
                        del self.active_players[task_id_key]
                else:
                    for p_type in list(self.active_players[task_id_key].keys()):
                        if 'noise' in p_type.lower():
                            self.active_players[task_id_key][p_type]["stop_event"].set()
                            del self.active_players[task_id_key][p_type]
                    if not self.active_players[task_id_key]:
                        del self.active_players[task_id_key]
            else:
                for p_type in list(self.active_players[task_id_key].keys()):
                    self.active_players[task_id_key][p_type]["stop_event"].set()
                del self.active_players[task_id_key]

    def stop_task_audio_by_pattern(self, task_id_pattern, player_type_pattern=None):
        """根据任务ID模式停止音频播放"""
        import re
        log_and_emit('DEBUG', 'audio_engine', f"[stop_task_audio_by_pattern] Called with pattern: {task_id_pattern}, active_players: {list(self.active_players.keys())}", category='audio')

        task_id_pattern = str(task_id_pattern) if task_id_pattern is not None else "*"
        player_type_pattern = str(player_type_pattern) if player_type_pattern is not None else None

        # 如果 pattern 不包含通配符，但以 _ 结尾，视为前缀匹配
        if '*' not in task_id_pattern and task_id_pattern.endswith('_'):
            pattern = f"^{re.escape(task_id_pattern)}.*$"
        else:
            pattern = f"^{re.escape(task_id_pattern).replace(r'\*', '.*')}$"

        matched_task_ids = []
        for task_id_key in self.active_players.keys():
            if re.match(pattern, str(task_id_key)):
                matched_task_ids.append(task_id_key)

        log_and_emit('DEBUG', 'audio_engine', f"[stop_task_audio_by_pattern] Pattern: {pattern}, Matched: {matched_task_ids}", category='audio')

        stopped_count = 0
        for task_id_key in matched_task_ids:
            if player_type_pattern:
                if player_type_pattern.endswith('*'):
                    prefix = player_type_pattern[:-1]
                    for p_type in list(self.active_players[task_id_key].keys()):
                        if p_type.startswith(prefix):
                            self.active_players[task_id_key][p_type]["stop_event"].set()
                            del self.active_players[task_id_key][p_type]
                            stopped_count += 1
                    # 如果该task_id下没有更多player_type，删除整个task_id
                    if not self.active_players[task_id_key]:
                        del self.active_players[task_id_key]
                else:
                    if player_type_pattern in self.active_players[task_id_key]:
                        self.active_players[task_id_key][player_type_pattern]["stop_event"].set()
                        del self.active_players[task_id_key][player_type_pattern]
                        stopped_count += 1
                        if not self.active_players[task_id_key]:
                            del self.active_players[task_id_key]
            else:
                for p_type in list(self.active_players[task_id_key].keys()):
                    self.active_players[task_id_key][p_type]["stop_event"].set()
                del self.active_players[task_id_key]
                stopped_count += 1

        log_and_emit('DEBUG', 'audio_engine', f"[stop_task_audio_by_pattern] Stopped: {stopped_count}, remaining: {list(self.active_players.keys())}", category='audio')
        return stopped_count
