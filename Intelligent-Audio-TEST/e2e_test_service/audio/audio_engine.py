"""
音频引擎模块 - AudioService 与单例实例。

时间轴纯函数已拆分到 audio_timeline.py，
驱动层（AudioDriver / PyAudioDriver）已拆分到 audio_driver.py。
本文件保留 AudioService 和模块级单例 audio_service，
并 re-export 所有公开接口以保持向后兼容。
"""

import pyaudio
import wave
import threading
import time
import numpy as np
import os
from flask import current_app
from shared.utils.log_handler import log_and_emit, log_not_emit

# 从拆分模块 re-export，保持向后兼容
from e2e_test_service.audio.audio_timeline import (
    get_audio_duration,
    calculate_overlap_time,
    calculate_sequential_delay,
    extract_speakers_from_annotations,
    build_speakers_map_from_dry_audios,
    calculate_speaker_aware_audio_delays,
    calculate_audio_delays,
    is_overlap_playback,
    build_audio_timelines,
    get_audio_configs_for_offset,
)
from e2e_test_service.audio.audio_driver import (
    AudioDriver,
    PyAudioDriver,
)




class AudioService:
    """音频管理服务：支持多通道播放控制"""
    def __init__(self):
        self.driver = PyAudioDriver()
        self.active_players = {} # taskId -> {player_type: thread}
        self._device_cache = None
        self._cache_time = 0
        self._cache_duration = 5.0 # 缓存5秒
        self._lock = threading.Lock()
        self._audio_pool = None

    def _get_audio_pool(self):
        """获取音频播放专用线程池（延迟初始化，避免循环导入）"""
        if self._audio_pool is None:
            try:
                # 跨服务调用：通过 gRPC ExecutionService 获取引擎信息（原 execution_engine.audio_playback_pool）
                from shared.clients.grpc_clients import get_execution_service_stub
                from shared.proto import task_service_pb2
                import json as _json
                _stub = get_execution_service_stub()
                _resp = _stub.GetEngineInfo(task_service_pb2.GetEngineInfoRequest(task_id=''))
                if _resp.success and _resp.data:
                    _info = _json.loads(_resp.data)
                    pool_size = _info.get('audio_playback_pool_size', 3)
                else:
                    pool_size = 3
                # gRPC 无法返回线程池对象，本地创建对应大小的线程池
                from concurrent.futures import ThreadPoolExecutor
                self._audio_pool = ThreadPoolExecutor(max_workers=pool_size, thread_name_prefix='audio_play_')
            except Exception as e:
                log_and_emit('WARNING', 'audio_engine', f"无法获取音频线程池，使用本地线程池: {e}", category='audio')
                from concurrent.futures import ThreadPoolExecutor
                self._audio_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix='audio_play_')
        return self._audio_pool

    def _get_cached_devices(self):
        """获取带缓存的设备列表，避免频繁扫描导致驱动崩溃"""
        import time
        with self._lock:
            current_time = time.time()
            if self._device_cache is None or (current_time - self._cache_time) > self._cache_duration:
                log_and_emit('DEBUG', 'audio_engine', "Cache expired or empty, scanning devices...", category='audio')
                self._device_cache = self.driver.get_devices()
                self._cache_time = current_time
            else:
                log_and_emit('DEBUG', 'audio_engine', f"Using cached device list (age: {round(current_time - self._cache_time, 2)}s)", category='audio')
            return self._device_cache

    @staticmethod
    def _normalize_name(name):
        """归一化设备名：去除引号、特殊字符、多余空格，统一为小写"""
        return name.replace("'", "").replace('"', '').strip().lower()

    def _find_device_matches(self, clean_unique_id, normalized_unique_id, devices):
        """多策略设备匹配：精确 → 基础名 → 扬声器前缀 → 模糊 → 括号内容。

        Returns:
            list: 匹配的设备列表（可能为空）
        """
        normalize = self._normalize_name

        # 1. 精确匹配
        exact_matches = [
            dev for dev in devices
            if (clean_unique_id == dev['name']
                or clean_unique_id == str(dev['index'])
                or normalize(dev['name']) == normalized_unique_id)
        ]
        log_and_emit('DEBUG', 'audio_engine', f"Exact matches: {len(exact_matches)}", category='audio')
        if exact_matches:
            return exact_matches

        # 2. 基础名匹配（去掉 [Ch X] 后缀）
        base_unique_id = clean_unique_id.split(' [Ch')[0] if ' [Ch' in clean_unique_id else clean_unique_id
        normalized_base = normalize(base_unique_id)
        log_and_emit('DEBUG', 'audio_engine', f"Trying base unique_id: '{base_unique_id}' (normalized: '{normalized_base}')", category='audio')

        base_matches = [dev for dev in devices if normalize(dev['name']) == normalized_base]
        if base_matches:
            log_and_emit('DEBUG', 'audio_engine', f"Base name matches: {len(base_matches)}", category='audio')
            return base_matches

        # 3. 扬声器前缀匹配
        if "扬声器" not in clean_unique_id:
            log_and_emit('DEBUG', 'audio_engine', "Trying to match with '扬声器' prefix...", category='audio')
            normalized_speaker = normalize(f"扬声器 {clean_unique_id}")
            speaker_matches = [
                dev for dev in devices
                if normalize(dev['name']) == normalized_speaker
                or normalized_speaker in normalize(dev['name'])
            ]
            if speaker_matches:
                log_and_emit('DEBUG', 'audio_engine', f"Speaker prefix matches: {len(speaker_matches)}", category='audio')
                return speaker_matches

        # 4. 模糊匹配（包含关系）
        log_and_emit('DEBUG', 'audio_engine', "Trying flexible fuzzy matching...", category='audio')
        fuzzy_matches = [
            dev for dev in devices
            if normalized_unique_id in normalize(dev['name'])
            or normalize(dev['name']) in normalized_unique_id
        ]
        if fuzzy_matches:
            log_and_emit('DEBUG', 'audio_engine', f"Fuzzy matches: {len(fuzzy_matches)}", category='audio')
            return fuzzy_matches

        # 5. 括号内容匹配
        log_and_emit('DEBUG', 'audio_engine', "Trying to match content in parentheses...", category='audio')
        import re
        bracket_content = re.findall(r'\(([^)]+)\)', clean_unique_id)
        if bracket_content:
            bracket_matches = []
            for content in bracket_content:
                normalized_bracket = normalize(content)
                bracket_matches.extend(
                    dev for dev in devices
                    if normalized_bracket in normalize(dev['name'])
                )
            if bracket_matches:
                log_and_emit('DEBUG', 'audio_engine', f"Bracket content matches: {len(bracket_matches)}", category='audio')
                return bracket_matches

        return []

    @staticmethod
    def _select_by_api_priority(matches):
        """按 API 优先级从匹配列表中选择最佳设备。

        Returns:
            dict: 选中的设备 dict，或 None
        """
        priority_apis = ["Windows WDM-KS", "Windows DirectSound", "Windows WASAPI", "MME"]

        for api in priority_apis:
            api_matches = [dev for dev in matches if dev['host_api'] == api]
            if api_matches:
                log_and_emit('DEBUG', 'audio_engine', f"API matches for {api}: {len(api_matches)}", category='audio')

                # 优先选择不带"扬声器"字样的设备
                pure_devices = [
                    dev for dev in api_matches
                    if "扬声器" not in dev['name'] and "Speaker" not in dev['name']
                ]
                selected = pure_devices[0] if pure_devices else api_matches[0]
                tag = "" if pure_devices else " (fallback)"
                log_and_emit('INFO', 'audio_engine', f"Selected device{tag}: {selected['name']} (API: {selected['host_api']}, Index: {selected['index']})", category='audio')
                return selected

        # 所有优先级都没有，返回第一个匹配
        selected = matches[0]
        log_and_emit('INFO', 'audio_engine', f"Selected device (final fallback): {selected['name']} (API: {selected['host_api']}, Index: {selected['index']})", category='audio')
        return selected

    def get_device_index(self, unique_id):
        """根据唯一标识获取物理设备索引 - 增强版"""
        if not unique_id:
            log_and_emit('ERROR', 'audio_engine', "get_device_index called with empty unique_id", category='audio')
            return None

        devices = self._get_cached_devices()
        log_and_emit('DEBUG', 'audio_engine', f"get_device_index: unique_id={unique_id}, available_devices={len(devices)}", category='audio')

        clean_unique_id = unique_id.strip()
        normalized_unique_id = self._normalize_name(clean_unique_id)
        log_and_emit('DEBUG', 'audio_engine', f"Clean unique_id: '{clean_unique_id}', Normalized: '{normalized_unique_id}'", category='audio')

        # 多策略匹配
        matches = self._find_device_matches(clean_unique_id, normalized_unique_id, devices)

        if not matches:
            # 兜底：返回第一个可用设备
            if devices:
                selected = devices[0]
                log_and_emit('WARNING', 'audio_engine', f"No matches found for '{unique_id}', returning first available device: '{selected['name']}' (Index: {selected['index']})", category='audio')
                return selected['index']
            else:
                log_and_emit('ERROR', 'audio_engine', f"No device matches found for unique_id='{unique_id}' and no devices available", category='audio')
                return None

        # 按 API 优先级选择
        selected = self._select_by_api_priority(matches)
        return selected['index']

    @staticmethod
    def _extract_card_key_and_stable_name(dev_name):
        """从设备名提取声卡分组 key 和稳定设备名。

        Returns:
            (card_key, stable_dev_name)
        """
        import re
        bracket_match = re.search(r'\(([^)]+)\)', dev_name)
        if bracket_match:
            bracket_content = bracket_match.group(1)
            if re.match(r'^\d+-\s*', bracket_content):
                stable_card_name = re.sub(r'^\d+-\s*', '', bracket_content)
            else:
                stable_card_name = bracket_content
        else:
            stable_card_name = None

        if 'RME' in dev_name:
            if '802' in dev_name:
                card_key = 'RME Fireface 802'
            elif 'UCX' in dev_name:
                card_key = 'RME Fireface UCX II'
            elif 'Fireface' in dev_name:
                card_key = 'RME Fireface'
            else:
                card_key = 'Unknown RME'
        else:
            try:
                if ' (' in dev_name:
                    card_key = dev_name.split(' (')[0].strip()
                else:
                    card_key = dev_name[:20].strip() if len(dev_name) > 20 else dev_name.strip()
            except:
                card_key = dev_name.strip()

        if stable_card_name and bracket_match:
            stable_dev_name = dev_name.replace(bracket_match.group(0), f"({stable_card_name})")
        else:
            stable_dev_name = dev_name

        return card_key, stable_dev_name

    @staticmethod
    def _classify_and_add_device(all_devices, card_key, dev, dev_name):
        """将设备分类（Analog子设备 / 主设备 / 其他）并添加到去重字典。"""
        max_output = dev['channels']
        sample_rate = dev['sample_rate']
        host_api = dev['host_api']

        if card_key not in all_devices:
            all_devices[card_key] = {
                'sub_devices_dedup': {},
                'all_sub_devices': []
            }

        # 确定声道范围
        if 'Analog (' in dev_name:
            try:
                channel_range = dev_name.split('(')[1].split(')')[0].strip()
            except:
                channel_range = dev_name
        elif '扬声器' in dev_name or 'Speaker' in dev_name:
            channel_range = 'Main'
        else:
            channel_range = 'Main'

        # 存储原始设备
        all_devices[card_key]['all_sub_devices'].append({
            'index': dev['index'],
            'name': dev_name,
            'channels': max_output,
            'channel_range': channel_range
        })

        # 去重：仅保留首个
        if channel_range not in all_devices[card_key]['sub_devices_dedup']:
            all_devices[card_key]['sub_devices_dedup'][channel_range] = {
                'index': dev['index'],
                'name': dev_name,
                'channels': max_output,
                'channel_range': channel_range,
                'sample_rate': sample_rate,
                'host_api': host_api
            }

    @staticmethod
    def _dedup_sort_key(sub_dev):
        """子设备排序 key：Main 最前，Analog 按通道号。"""
        channel_range = sub_dev['channel_range']
        if channel_range == 'Main':
            return 0
        try:
            return int(channel_range.split('+')[0])
        except:
            return 999

    def get_all_physical_devices(self):
        """扫描所有可用的物理输出设备及通道 - 按声卡聚合并去重"""
        devices = self._get_cached_devices()
        all_devices = {}

        # 第一步：枚举所有 WASAPI 设备，按声卡分组并去重
        for dev in devices:
            if dev['host_api'] != 'Windows WASAPI':
                continue

            dev_name = dev['name']
            card_key, stable_dev_name = self._extract_card_key_and_stable_name(dev_name)
            self._classify_and_add_device(all_devices, card_key, dev, stable_dev_name)

        # 第二步：处理去重结果，生成候选设备列表
        candidates = []
        for info in all_devices.values():
            dedup_subs = sorted(
                info['sub_devices_dedup'].values(),
                key=self._dedup_sort_key
            )
            info['dedup_sub_list'] = dedup_subs
            info['total_channels_dedup'] = sum(sub['channels'] for sub in dedup_subs)
            del info['sub_devices_dedup']

            for sub_dev in dedup_subs:
                for ch in range(sub_dev['channels']):
                    unique_id = f"{sub_dev['name']} [Ch {ch+1}]"
                    candidates.append({
                        "name": unique_id,
                        "unique_id": unique_id,
                        "device_index": sub_dev['index'],
                        "channel_index": ch,
                        "sample_rate": sub_dev['sample_rate'],
                        "host_api": sub_dev['host_api']
                    })

        return candidates

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
            self.driver.play_multi,
            audio_configs, device_index, stop_event, offset, loop
        )
        
        if task_id not in self.active_players:
            self.active_players[task_id] = {}
        
        self.active_players[task_id][player_type] = {
            "future": future,
            "stop_event": stop_event
        }
        
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
            self.driver.play_multi(multi_configs, device_index, stop_event, loop=loop, app=app, playback_started_event=playback_started_event, playback_finished_event=playback_finished_event)

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
                elif player_type in self.active_players[task_id_key]:
                    self.active_players[task_id_key][player_type]["stop_event"].set()
                    del self.active_players[task_id_key][player_type]
                else:
                    for p_type in list(self.active_players[task_id_key].keys()):
                        if 'noise' in p_type.lower():
                            self.active_players[task_id_key][p_type]["stop_event"].set()
                            del self.active_players[task_id_key][p_type]
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

audio_service = AudioService()
