import pyaudio
import wave
import threading
import time
import numpy as np
import os
from abc import ABC, abstractmethod
from flask import current_app
import sounddevice as sd
from pydub import AudioSegment
from backend.utils.log_handler import log_and_emit, log_not_emit


def get_audio_duration(file_path):
    """
    获取音频文件的时长

    Args:
        file_path: 音频文件路径

    Returns:
        float: 音频时长（秒），失败返回0
    """
    try:
        import wave
        with wave.open(file_path, 'rb') as wf:
            return wf.getnframes() / wf.getframerate()
    except:
        return 0


def calculate_overlap_time(audio_file, overlap_time, overlap_rate):
    """
    计算交叠时间（overlap_time）

    交叠时间是指两个音频同时播放的时间段。

    Args:
        audio_file: 音频文件路径（用于获取音频时长）
        overlap_time: 重叠时间（秒），优先级高于 overlap_rate
        overlap_rate: 重叠率 (0.0-1.0)

    Returns:
        float: 交叠时间（秒）
            - overlap_time > 0: 使用 overlap_time
            - overlap_rate > 0: 使用 duration * overlap_rate
            - overlap_rate == 0: 返回 0
            - 两者都为0或None: 返回 0
    """
    if overlap_time and overlap_time > 0:
        return overlap_time

    if overlap_rate is not None:
        duration = get_audio_duration(audio_file)
        if duration > 0:
            if overlap_rate == 0:
                return 0
            elif overlap_rate > 0:
                return duration * overlap_rate

    return 0


def calculate_sequential_delay(device_index, device_dry_duration, overlap_rate):
    """
    计算顺序播放时的设备延迟时间

    延迟时间是指第n个设备比第1个设备晚开始的时间。

    Args:
        device_index: 设备索引（0-based）
        device_dry_duration: 当前设备的干声时长
        overlap_rate: 重叠率 (0.0-1.0)，用于计算延迟

    Returns:
        float: 延迟时间（秒）
            - device_index == 0: 返回 0（第1个设备立即播放）
            - 其他: 返回 device_dry_duration * (1 - overlap_rate)
    """
    if device_index == 0:
        return 0

    delay = device_dry_duration * (1 - overlap_rate)
    return max(0, delay)


def extract_speakers_from_annotations(audio_id, app=None):
    """
    从音频的diarization标注中提取所有speaker集合
    
    Args:
        audio_id: 音频ID
        app: Flask应用实例
        
    Returns:
        set: speaker标签集合，如 {'spk9', 'spk8'}
    """
    if not audio_id:
        return set()
    
    speakers = set()
    
    def _query_annotations():
        from backend.models.models import AudioAnnotation
        return AudioAnnotation.query.filter_by(
            audio_id=audio_id,
            deleted=False
        ).all()
    
    if app:
        with app.app_context():
            annotations = _query_annotations()
    else:
        annotations = _query_annotations()
    
    for ann in annotations:
        if not ann.data:
            continue
        
        if isinstance(ann.data, dict):
            segments = ann.data.get('segments', [])
            for seg in segments:
                if 'speaker' in seg and seg['speaker']:
                    speakers.add(seg['speaker'])
        elif isinstance(ann.data, list):
            for seg in ann.data:
                if isinstance(seg, dict) and 'speaker' in seg and seg['speaker']:
                    speakers.add(seg['speaker'])
    
    log_and_emit('DEBUG', 'audio_engine', 
        f'[extract_speakers_from_annotations] audio_id={audio_id}, speakers={speakers}', 
        category='audio')
    
    return speakers


def build_speakers_map_from_dry_audios(dry_audios_info, app=None):
    """
    从干声信息列表构建speakers_map
    
    Args:
        dry_audios_info: 干声列表 [(audio_config, audio_obj), ...]
        app: Flask应用实例
        
    Returns:
        dict: {audio_id: set(speakers)}
    """
    speakers_map = {}
    
    for audio_config, audio_obj in dry_audios_info:
        audio_id = audio_config.get('audio_id') if isinstance(audio_config, dict) else getattr(audio_config, 'id', None)
        if audio_id:
            speakers_map[audio_id] = extract_speakers_from_annotations(audio_id, app=app)
    
    log_and_emit('DEBUG', 'audio_engine', 
        f'[build_speakers_map_from_dry_audios] speakers_map={speakers_map}', 
        category='audio')
    
    return speakers_map


def calculate_speaker_aware_audio_delays(audio_configs, overlap_rate, is_overlap, global_offset=0, overlap_time=0, speakers_map=None):
    """
    计算每个音频的开始时间（speaker感知版本）

    规则：
    - 相邻音频有共同speaker → 顺序播放（start_time = prev_end_time）
    - 相邻音频无共同speaker → 按overlap_time或overlap_rate交叠

    每个声道（playback_device）都有独立的 delay，通过填充静音控制开始时间

    Args:
        audio_configs: 音频配置列表
        overlap_rate: 重叠率 (0.0-1.0)
        is_overlap: 是否为重叠播放模式
        global_offset: 全局偏移量
        overlap_time: 重叠时间（秒），优先级高于 overlap_rate
        speakers_map: {audio_id: set(speakers)}，从diarization标注提取的speaker集合

    Returns:
        list: [(config, start_time), ...] 按 play_order 排序
    """
    dry_configs = [c.copy() for c in audio_configs if not c.get('is_noise', False)]
    sorted_dry = sorted(dry_configs, key=lambda x: x.get('play_order', 0))

    audio_delays_with_config = []

    log_and_emit('DEBUG', 'audio_engine', f"[calculate_speaker_aware_audio_delays] ENTRY: overlap_rate={overlap_rate}, is_overlap={is_overlap}, overlap_time={overlap_time}, speakers_map={speakers_map}", category='audio')

    prev_end_time = 0
    for i, config in enumerate(sorted_dry):
        audio_offset = config.get('offset', 0)
        total_duration = config.get('duration', 0) or get_audio_duration(config['file'])
        effective_duration = max(0, total_duration - audio_offset)
        
        audio_id = config.get('audio_id')
        curr_speakers = speakers_map.get(audio_id, set()) if speakers_map else set()
        
        if i == 0:
            start_time = 0
            log_and_emit('DEBUG', 'audio_engine', f"[calculate_speaker_aware_audio_delays] i={i}: first audio, start_time=0, audio_id={audio_id}, speakers={curr_speakers}", category='audio')
        else:
            prev_audio_id = sorted_dry[i-1].get('audio_id')
            prev_speakers = speakers_map.get(prev_audio_id, set()) if speakers_map else set()
            
            has_common_speaker = len(curr_speakers & prev_speakers) > 0
            
            log_and_emit('DEBUG', 'audio_engine', f"[calculate_speaker_aware_audio_delays] i={i}: prev_audio_id={prev_audio_id}, prev_speakers={prev_speakers}, curr_audio_id={audio_id}, curr_speakers={curr_speakers}, has_common_speaker={has_common_speaker}", category='audio')
            
            if has_common_speaker:
                start_time = prev_end_time
                log_and_emit('DEBUG', 'audio_engine', f"[calculate_speaker_aware_audio_delays] i={i}: Has common speaker, sequential playback: start_time=prev_end_time={prev_end_time}", category='audio')
            else:
                if overlap_time and overlap_time > 0:
                    start_time = prev_end_time - overlap_time
                    if start_time < 0:
                        log_and_emit('WARNING', 'audio_engine', f"[calculate_speaker_aware_audio_delays] i={i}: overlap_time={overlap_time} > prev_end_time={prev_end_time}, clamping start_time to 0", category='audio')
                        start_time = 0
                    log_and_emit('DEBUG', 'audio_engine', f"[calculate_speaker_aware_audio_delays] i={i}: using overlap_time={overlap_time}, prev_end_time={prev_end_time}, start_time={start_time}", category='audio')
                elif overlap_rate is not None and overlap_rate > 0:
                    start_time = prev_end_time * (1 - overlap_rate)
                    log_and_emit('DEBUG', 'audio_engine', f"[calculate_speaker_aware_audio_delays] i={i}: using overlap_rate={overlap_rate}, prev_end_time={prev_end_time}, start_time={start_time}", category='audio')
                else:
                    start_time = prev_end_time
                    log_and_emit('DEBUG', 'audio_engine', f"[calculate_speaker_aware_audio_delays] i={i}: no overlap, start_time=prev_end_time={prev_end_time}", category='audio')

        log_and_emit('DEBUG', 'audio_engine', f"[calculate_speaker_aware_audio_delays] i={i}: config_play_order={config.get('play_order')}, audio_id={audio_id}, start_time={start_time}", category='audio')

        audio_delays_with_config.append((config, start_time))
        prev_end_time = start_time + effective_duration

    noise_configs = [c.copy() for c in audio_configs if c.get('is_noise', False)]
    for config in noise_configs:
        audio_delays_with_config.append((config, 0))

    return audio_delays_with_config


def calculate_audio_delays(audio_configs, overlap_rate, is_overlap, global_offset=0, overlap_time=0):
    """
    计算每个音频的开始时间（相对于第一个音频开始的时间）

    全局链式交叠公式（按全局 play_order 排序）：
    - overlap_time > 0: start_time = prev_end_time - overlap_time
    - overlap_rate > 0: start_time = prev_end_time * (1 - overlap_rate)
    - 否则: start_time = prev_end_time（顺序播放）

    每个声道（playback_device）都有独立的 delay，通过填充静音控制开始时间

    Args:
        audio_configs: 音频配置列表
        overlap_rate: 重叠率 (0.0-1.0)
        is_overlap: 是否为重叠播放模式
        global_offset: 全局偏移量
        overlap_time: 重叠时间（秒），优先级高于 overlap_rate

    Returns:
        list: [(config, start_time), ...] 按 play_order 排序
    """
    dry_configs = [c.copy() for c in audio_configs if not c.get('is_noise', False)]
    sorted_dry = sorted(dry_configs, key=lambda x: x.get('play_order', 0))

    audio_delays_with_config = []

    log_and_emit('DEBUG', 'audio_engine', f"[calculate_audio_delays] ENTRY: overlap_rate={overlap_rate}, is_overlap={is_overlap}, overlap_time={overlap_time}", category='audio')

    prev_end_time = 0
    for i, config in enumerate(sorted_dry):
        audio_offset = config.get('offset', 0)
        total_duration = config.get('duration', 0) or get_audio_duration(config['file'])
        effective_duration = max(0, total_duration - audio_offset)

        if i == 0:
            start_time = 0
            log_and_emit('DEBUG', 'audio_engine', f"[calculate_audio_delays] i={i}: first audio, start_time=0", category='audio')
        else:
            if overlap_time and overlap_time > 0:
                start_time = prev_end_time - overlap_time
                if start_time < 0:
                    log_and_emit('WARNING', 'audio_engine', f"[calculate_audio_delays] i={i}: overlap_time={overlap_time} > prev_end_time={prev_end_time}, clamping start_time to 0", category='audio')
                    start_time = 0
                log_and_emit('DEBUG', 'audio_engine', f"[calculate_audio_delays] i={i}: using overlap_time={overlap_time}, prev_end_time={prev_end_time}, start_time={start_time}", category='audio')
            elif overlap_rate is not None and overlap_rate > 0:
                start_time = prev_end_time * (1 - overlap_rate)
                log_and_emit('DEBUG', 'audio_engine', f"[calculate_audio_delays] i={i}: using overlap_rate={overlap_rate}, prev_end_time={prev_end_time}, start_time={start_time}", category='audio')
            else:
                start_time = prev_end_time
                log_and_emit('DEBUG', 'audio_engine', f"[calculate_audio_delays] i={i}: no overlap, start_time={start_time}", category='audio')

        log_and_emit('DEBUG', 'audio_engine', f"[calculate_audio_delays] i={i}: config_play_order={config.get('play_order')}, start_time={start_time}", category='audio')

        audio_delays_with_config.append((config, start_time))
        prev_end_time = start_time + effective_duration

    noise_configs = [c.copy() for c in audio_configs if c.get('is_noise', False)]
    for config in noise_configs:
        audio_delays_with_config.append((config, 0))

    return audio_delays_with_config


def is_overlap_playback(overlap_time, overlap_rate):
    """
    判断是否为重叠播放模式

    Args:
        overlap_time: 重叠时间（秒）
        overlap_rate: 重叠率 (0.0-1.0)

    Returns:
        True: 重叠播放（parallel）
        False: 非重叠播放
    """
    if overlap_time and overlap_time > 0:
        return True

    if overlap_rate is not None and overlap_rate > 0:
        return True

    return False


def build_audio_timelines(dry_audios_info, overlap_rate, overlap_time=0, speakers_map=None):
    """
    构建音频时间轴 - 公共方法，供 testcase_controller 和 e2e_executor 使用

    Speaker感知交叠公式：
    - 相邻音频有共同speaker → 顺序播放（start_time = prev_end_time）
    - 相邻音频无共同speaker 且 overlap_time > 0 → 交叠（start_time = prev_end_time - overlap_time）
    - 相邻音频无共同speaker 且 overlap_rate > 0 → 交叠（start_time = prev_end_time * (1 - overlap_rate)）
    - 否则 → 顺序播放（start_time = prev_end_time）

    Args:
        dry_audios_info: 干声列表 [(audio_config, audio_obj), ...]
        overlap_rate: 重叠率
        overlap_time: 重叠时间（秒），优先级高于 overlap_rate
        speakers_map: {audio_id: set(speakers)}，speaker集合映射

    Returns:
        list: 音频时间轴列表
    """
    log_and_emit('DEBUG', 'audio_engine', f"[build_audio_timelines] dry_audios_info count={len(dry_audios_info)}, overlap_rate={overlap_rate}, overlap_time={overlap_time}, speakers_map={speakers_map}", category='audio')

    audio_timelines = []
    cumulative_duration = 0
    prev_end_time = 0

    for i, (audio_config, audio) in enumerate(dry_audios_info):
        duration = audio.duration or 0
        file_path = audio.file_path

        audio_id = audio_config.get('audio_id') if isinstance(audio_config, dict) else getattr(audio_config, 'id', None)
        curr_speakers = speakers_map.get(audio_id, set()) if speakers_map else set()

        if i == 0:
            start_time = 0
            log_and_emit('DEBUG', 'audio_engine', f"[build_audio_timelines] audio[{i}] first, start_time=0, audio_id={audio_id}, speakers={curr_speakers}", category='audio')
        else:
            prev_audio_id = dry_audios_info[i-1][0].get('audio_id') if isinstance(dry_audios_info[i-1][0], dict) else getattr(dry_audios_info[i-1][0], 'id', None)
            prev_speakers = speakers_map.get(prev_audio_id, set()) if speakers_map else set()

            has_common_speaker = len(curr_speakers & prev_speakers) > 0

            log_and_emit('DEBUG', 'audio_engine', f"[build_audio_timelines] audio[{i}] prev_audio_id={prev_audio_id}, prev_speakers={prev_speakers}, curr_audio_id={audio_id}, curr_speakers={curr_speakers}, has_common_speaker={has_common_speaker}", category='audio')

            if has_common_speaker:
                start_time = prev_end_time
                log_and_emit('DEBUG', 'audio_engine', f"[build_audio_timelines] audio[{i}] Has common speaker, sequential: start_time=prev_end_time={prev_end_time}", category='audio')
            else:
                if overlap_time and overlap_time > 0:
                    start_time = prev_end_time - overlap_time
                    if start_time < 0:
                        log_and_emit('WARNING', 'audio_engine', f"[build_audio_timelines] audio[{i}] overlap_time={overlap_time} > prev_end_time={prev_end_time}, clamping to 0", category='audio')
                        start_time = 0
                    log_and_emit('DEBUG', 'audio_engine', f"[build_audio_timelines] audio[{i}] using overlap_time={overlap_time}, prev_end_time={prev_end_time}, start_time={start_time}", category='audio')
                elif overlap_rate is not None and overlap_rate > 0:
                    start_time = prev_end_time * (1 - overlap_rate)
                    log_and_emit('DEBUG', 'audio_engine', f"[build_audio_timelines] audio[{i}] using overlap_rate={overlap_rate}, prev_end_time={prev_end_time}, start_time={start_time}", category='audio')
                else:
                    start_time = prev_end_time
                    log_and_emit('DEBUG', 'audio_engine', f"[build_audio_timelines] audio[{i}] no overlap, start_time=prev_end_time={prev_end_time}", category='audio')

        audio_timelines.append({
            'config': audio_config,
            'audio': audio,
            'file': file_path,
            'start': start_time,
            'end': start_time + duration,
            'timeline_duration': duration
        })

        prev_end_time = start_time + duration
        cumulative_duration += duration

    log_and_emit('DEBUG', 'audio_engine', f"[build_audio_timelines] Result timelines: {[(t.get('file') or t.get('file_path'), t.get('start'), t.get('end')) for t in audio_timelines]}", category='audio')

    return audio_timelines


def get_audio_configs_for_offset(audio_timelines, global_offset, playback_devices_map, noise_audio_info=None, noise_devices=None, audio_service=None, app=None):
    """
    根据全局 offset 获取需要播放的音频配置
    
    Args:
        audio_timelines: 音频时间轴列表
        global_offset: 全局偏移量（秒）
        playback_devices_map: 播放设备映射 {device_id: device_info}
        noise_audio_info: 噪声音频信息 (audio_config, audio_obj) 或 None
        noise_devices: 噪声设备列表
        audio_service: AudioService 实例，用于获取设备索引
        app: Flask 应用实例，用于在子线程中提供数据库上下文
    
    Returns:
        list: 音频配置列表，可以直接传给 play_overlap
    """
    audio_to_play = []
    
    for item in audio_timelines:
        audio_config = item['config']
        audio_obj = item['audio']
        file_path = item.get('file') or item.get('file_path', '')
        start_time = item['start']
        end_time = item['end']
        timeline_duration = item.get('timeline_duration', audio_obj.duration)
        
        if global_offset >= end_time:
            continue
        
        if global_offset >= start_time:
            local_offset = global_offset - start_time
        else:
            local_offset = 0
        
        playback_dev_id = audio_config.get('playback_device_id')
        if not playback_dev_id:
            log_and_emit('DEBUG', 'audio_engine', f"[get_audio_configs_for_offset] SKIP no playback_dev_id: audio_id={audio_config.get('audio_id')}, play_order={audio_config.get('play_order')}", category='audio')
            continue

        playback_dev_id_int = int(playback_dev_id) if playback_dev_id else None
        device_info = playback_devices_map.get(playback_dev_id_int) or playback_devices_map.get(playback_dev_id)
        if not device_info:
            log_and_emit('DEBUG', 'audio_engine', f"[get_audio_configs_for_offset] SKIP device not in playback_devices_map: playback_dev_id={playback_dev_id} (type={type(playback_dev_id)}), available_keys={list(playback_devices_map.keys())}", category='audio')
            continue  
        
        device_obj = device_info.get('device_obj')
        log_and_emit('DEBUG', 'audio_engine', f"[get_audio_configs_for_offset] device_id={playback_dev_id}, device_obj={device_obj}, current_spl_mapping_id={device_obj.current_spl_mapping_id if device_obj else 'N/A'}", category='audio')
        
        _audio_id = audio_config.get('audio_id')
        _play_order = audio_config.get('play_order', 0)
        _raw_spl = audio_config.get('spl')
        
        if device_obj and device_obj.current_spl_mapping_id:
            try:
                from backend.utils.spl_service import spl_service
                target_spl = audio_config.get('spl', 65.0)
                gain = spl_service.spl_to_gain(device_obj.current_spl_mapping_id, target_spl, app=app)
                gain_db = 20 * np.log10(gain) if gain > 0 else -999
                log_and_emit('DEBUG', 'audio_engine', f"[get_audio_configs_for_offset] audio_id={_audio_id}, play_order={_play_order}, raw_spl={_raw_spl}, target_spl={target_spl}, mapping_id={device_obj.current_spl_mapping_id}, SPL gain={gain:.4f} ({gain_db:.2f} dB)", category='audio')
            except Exception as e:
                log_and_emit('ERROR', 'audio_engine', f"[get_audio_configs_for_offset] SPL mapping failed: audio_id={_audio_id}, play_order={_play_order}, mapping_id={device_obj.current_spl_mapping_id}, error={e}", category='audio')
                gain = device_info.get('gain', 1.0)
        else:
            gain = device_info.get('gain', 1.0)
            log_and_emit('DEBUG', 'audio_engine', f"[get_audio_configs_for_offset] No SPL mapping: audio_id={_audio_id}, play_order={_play_order}, raw_spl={_raw_spl}, default gain={gain}", category='audio')
        
        audio_to_play.append({
            'file': file_path,
            'device_index': device_info.get('device_index'),
            'channel': device_info.get('channel_index', 0),
            'gain': gain,
            'offset': local_offset,
            'duration': timeline_duration,
            'play_order': audio_config.get('play_order', 0),
            'loop': False,
            'is_noise': False,
            'timeline_start': start_time,
            'config': audio_config,
            'audio': audio_obj,
            'audio_id': audio_config.get('audio_id')
        })
    
    return audio_to_play


def prepare_audio_playback_info(audio_configs, case_config, db_session):
    """
    准备音频播放所需的信息 - 公共方法，供 testcase_controller 和 e2e_executor 使用
    
    处理：
    - 从音频配置中分类干声和噪声
    - 收集干声播放设备
    - 获取噪声设备和噪声音频信息
    
    Args:
        audio_configs: 音频配置列表 [{'audio_id': xxx, 'playback_device_id': xxx, ...}, ...]
        case_config: 用例配置 dict，包含 background_noise 配置
        db_session: 数据库会话
    
    Returns:
        dict: {
            'dry_audios_info': [(audio_config, audio_obj), ...],
            'dry_devices': [device_obj, ...],
            'noise_audio_info': (audio_config, audio_obj) or None,
            'noise_devices': [device_obj, ...]
        }
    """
    from backend.models.models import Audio, PlaybackDevice
    
    dry_audios_info = []
    noise_case_audio_info = None
    
    for audio_config in audio_configs:
        audio = db_session.get(Audio, audio_config.get('audio_id'))
        if not audio:
            continue
        if audio.audio_type == 'noise':
            noise_case_audio_info = (audio_config, audio)
        else:
            dry_audios_info.append((audio_config, audio))
    
    if not dry_audios_info:
        return None
    
    dry_audios_info.sort(key=lambda x: x[0].get('play_order', 0))
    
    device_ids_seen = set()
    dry_devices = []
    for audio_config, _ in dry_audios_info:
        playback_device_id = audio_config.get('playback_device_id')
        if playback_device_id and playback_device_id not in device_ids_seen:
            dev = db_session.get(PlaybackDevice, playback_device_id)
            if dev:
                dry_devices.append(dev)
                device_ids_seen.add(playback_device_id)
    
    noise_audio = None
    noise_spl = 0
    if noise_case_audio_info:
        n_ca, n_audio = noise_case_audio_info
        noise_audio = n_audio
        noise_spl = n_ca.get('spl', 0)
    elif case_config and case_config.get('background_noise', {}).get('audio_id'):
        bg_noise_id = case_config['background_noise']['audio_id']
        noise_audio = db_session.get(Audio, bg_noise_id)
        noise_spl = case_config['background_noise'].get('spl', 0)
    
    noise_configured_device_ids = []
    if case_config:
        noise_configured_device_ids = case_config.get('background_noise', {}).get('device_ids', [])
    
    all_noise_devices = []
    for device_id in noise_configured_device_ids:
        if isinstance(device_id, str):
            device = PlaybackDevice.query.filter_by(device_unique_id=device_id, is_deleted=0).first()
        else:
            device = db_session.get(PlaybackDevice, device_id)
        if device:
            all_noise_devices.append(device)
    
    noise_audio_info_for_playback = None
    if noise_audio and all_noise_devices:
        noise_config = {
            'spl': noise_spl,
            'audio_id': noise_audio.id if hasattr(noise_audio, 'id') else None
        }
        noise_audio_info_for_playback = (noise_config, noise_audio)
    
    return {
        'dry_audios_info': dry_audios_info,
        'dry_devices': dry_devices,
        'noise_audio_info': noise_audio_info_for_playback,
        'noise_devices': all_noise_devices
    }


def execute_audio_playback(
    task_id,
    dry_audios_info,
    noise_audio_info,
    noise_devices,
    dry_devices,
    overlap_rate=0,
    overlap_time=0,
    global_offset=0,
    loop=False,
    audio_service=None,
    wait_for_completion=False,
    stop_noise_after_dry=False,
    app=None
):
    """
    执行音频播放 - 统一方法，供 testcase_controller 和 e2e_executor 使用
    
    统一处理：
    - 噪声和干声一起播放
    - 支持顺序播放和重叠播放
    - 支持 offset（预览时的进度条拖动）
    
    Args:
        task_id: 任务ID
        dry_audios_info: 干声列表 [(audio_config, audio_obj), ...]
        noise_audio_info: 噪声音频信息 (audio_config, audio_obj) 或 None
        noise_devices: 噪声设备列表 [device_obj, ...]
        dry_devices: 干声播放设备列表 [device_obj, ...]
        overlap_rate: 重叠率 (0.0-1.0)
        overlap_time: 重叠时间（秒），优先级高于 overlap_rate
        global_offset: 全局偏移量（秒），0 表示从头播放
        loop: 是否循环播放（仅对干声有效）
        audio_service: AudioService 实例，如果传入会使用该实例，否则使用全局 audio_service
        wait_for_completion: 是否等待播放完成（同步模式），默认 False（异步）
        app: Flask 应用实例，用于在子线程中提供数据库上下文
    
    Returns:
        bool or dict: 成功时返回包含 audio_timelines 的字典，失败时返回 False
    """
    if not audio_service:
        audio_service = globals().get('audio_service')
    
    if not audio_service:
        log_and_emit('ERROR', 'audio_engine', 'execute_audio_playback: audio_service not found', category='audio')
        return False
    
    playback_start_time = time.time()
    
    playback_devices_map = {}
    for dev in dry_devices:
        dev_id = dev.id if hasattr(dev, 'id') else dev.get('id')
        device_index = audio_service.get_device_index(dev.device_unique_id) if hasattr(dev, 'device_unique_id') else audio_service.get_device_index(dev.get('device_unique_id'))
        playback_devices_map[dev_id] = {
            'device_obj': dev,
            'device_index': device_index,
            'channel_index': dev.channel_index if hasattr(dev, 'channel_index') else dev.get('channel_index', 0),
            'gain': 1.0,
            'name': dev.name if hasattr(dev, 'name') else dev.get('name', ''),
            'current_spl_mapping_id': dev.current_spl_mapping_id if hasattr(dev, 'current_spl_mapping_id') else dev.get('current_spl_mapping_id')
        }
    
    log_and_emit('DEBUG', 'audio_engine', f"[execute_audio_playback] playback_devices_map: {[(k, v.get('device_index'), v.get('channel_index')) for k, v in playback_devices_map.items()]}", category='audio')
    
    log_and_emit('DEBUG', 'audio_engine', f"[execute_audio_playback] RECEIVED: overlap_rate={overlap_rate}, overlap_time={overlap_time}", category='audio')
    
    speakers_map = build_speakers_map_from_dry_audios(dry_audios_info, app=app)
    
    audio_timelines = build_audio_timelines(dry_audios_info, overlap_rate, overlap_time, speakers_map)
    
    audio_to_play = []
    
    log_and_emit('DEBUG', 'audio_engine', f"[execute_audio_playback] noise_audio_info={noise_audio_info is not None}, noise_devices={len(noise_devices) if noise_devices else 0}, dry_audios_info count={len(dry_audios_info) if dry_audios_info else 0}", category='audio')
    
    if noise_audio_info and noise_devices:
        n_config, n_audio = noise_audio_info
        noise_file_path = n_audio.file_path if hasattr(n_audio, 'file_path') else n_audio.get('file_path')
        noise_spl = n_config.get('spl', 60) if n_config else 60
        
        for n_dev in noise_devices:
            n_dev_unique_id = n_dev.device_unique_id if hasattr(n_dev, 'device_unique_id') else n_dev.get('device_unique_id')
            n_channel_index = n_dev.channel_index if hasattr(n_dev, 'channel_index') else n_dev.get('channel_index', 0)
            n_spl_mapping_id = n_dev.current_spl_mapping_id if hasattr(n_dev, 'current_spl_mapping_id') else n_dev.get('current_spl_mapping_id')
            
            n_gain = 1.0
            if n_spl_mapping_id:
                try:
                    from backend.utils.spl_service import spl_service
                    n_gain = spl_service.spl_to_gain(n_spl_mapping_id, noise_spl, app=app)
                except:
                    n_gain = 1.0
            
            n_device_index = audio_service.get_device_index(n_dev_unique_id)
            log_and_emit('DEBUG', 'audio_engine', f"[execute_audio_playback] noise: device={n_dev_unique_id}, index={n_device_index}", category='audio')
            if n_device_index is not None:
                audio_to_play.append({
                    'file': noise_file_path,
                    'device_index': n_device_index,
                    'channel': n_channel_index,
                    'gain': n_gain,
                    'offset': global_offset,
                    'duration': n_audio.duration if hasattr(n_audio, 'duration') else 0,
                    'play_order': 0,
                    'loop': True,
                    'is_noise': True
                })
    
    # 获取 Flask app 用于数据库访问（在后台线程中需要显式传递）
    if app is None:
        try:
            from flask import current_app
            app = current_app._get_current_object()
        except RuntimeError:
            app = None
    
    dry_configs = get_audio_configs_for_offset(
        audio_timelines, 
        global_offset, 
        playback_devices_map,
        audio_service=audio_service,
        app=app
    )
    log_and_emit('DEBUG', 'audio_engine', f'[execute_audio_playback] dry_configs from get_audio_configs_for_offset: count={len(dry_configs) if dry_configs else 0}, playback_devices_map keys={list(playback_devices_map.keys())}', category='audio')
    
    audio_to_play.extend(dry_configs)
    
    audio_list_str = ', '.join([f"{{file={c.get('file', '')}, is_noise={c.get('is_noise')}, device={c.get('device_index')}, delay={c.get('delay', 0)}}}" for c in audio_to_play])
    
    if not audio_to_play:
        log_and_emit('WARNING', 'audio_engine', 'execute_audio_playback: no audio to play', category='audio')
        return False
    
    try:
        threads = audio_service.play_overlap(
            task_id=task_id,
            audio_configs=audio_to_play,
            overlap_time=overlap_time,
            overlap_rate=overlap_rate,
            offset=global_offset,
            loop=loop,
            speakers_map=speakers_map,
            app=app
        )
        
        if wait_for_completion and threads:
            if stop_noise_after_dry and noise_audio_info and noise_devices:
                total_duration = 0
                audio_timelines = build_audio_timelines(dry_audios_info, overlap_rate, overlap_time, speakers_map)
                if audio_timelines:
                    total_duration = max(t.get('end', 0) for t in audio_timelines)
                else:
                    total_duration = sum(audio.duration or 0 for _, audio in dry_audios_info)
                
                log_and_emit('DEBUG', 'audio_engine', f"[execute_audio_playback] Waiting {total_duration}s for dry audio to finish, then stopping noise", category='audio')
                time.sleep(total_duration)
                log_and_emit('DEBUG', 'audio_engine', f"[execute_audio_playback] Sleep done, calling stop_task_audio", category='audio')
                audio_service.stop_task_audio(task_id)
            else:
                for future in threads:
                    try:
                        future.result()
                    except Exception as e:
                        log_and_emit('ERROR', 'audio_engine', f"[execute_audio_playback] Audio playback error: {e}", category='audio')
        
        audio_delays = calculate_speaker_aware_audio_delays(
            audio_to_play, 
            overlap_rate, 
            overlap_time > 0,
            global_offset,
            overlap_time,
            speakers_map=speakers_map
        )
        
        delay_map = {}
        for config, delay in audio_delays:
            play_order = config.get('play_order', 0)
            delay_map[play_order] = delay
        
        log_and_emit('DEBUG', 'audio_engine', f'[execute_audio_playback] delay_map={delay_map}, timelines_count={len(audio_timelines)}, audio_to_play_count={len(audio_to_play)}, audio_to_play_play_orders={[c.get("play_order") for c in audio_to_play]}', category='audio')
        
        for timeline in audio_timelines:
            play_order = timeline.get('config', {}).get('play_order', 0)
            delay = delay_map.get(play_order, 0)
            timeline['delay'] = delay
            timeline['actual_play_time'] = playback_start_time + delay
            # log_and_emit('DEBUG', 'audio_engine', f'[execute_audio_playback] timeline play_order={play_order}, delay={delay}, actual_play_time={timeline["actual_play_time"]}', category='audio')
        
        return {'success': True, 'audio_timelines': audio_timelines}
    except Exception as e:
        log_and_emit('ERROR', 'audio_engine', f'execute_audio_playback failed: {e}', category='audio')
        return False


class AudioDriver(ABC):
    """音频驱动基类"""
    
    def play_multi(self, audio_configs, device_index=0, stop_event=None, offset=0, loop=False):
        pass
    
    def calculate_gain_compensation(self, file_path):
        """计算增益补偿（根据音频实际 RMS 调整增益，确保达到预期的 SPL）"""
        try:
            audio_seg = AudioSegment.from_file(file_path)
            current_rms_db = audio_seg.dBFS
            gain_db = -30.0 - current_rms_db
            gain_compensation = 10 ** (gain_db / 20)
            log_and_emit('DEBUG', 'audio_engine', f"[calculate_gain_compensation] file={os.path.basename(file_path)}, current_rms_db={current_rms_db:.2f} dBFS, target=-30 dBFS, gain_db={gain_db:.2f} dB, gain_compensation={gain_compensation:.4f} (linear)", category='audio')
            return gain_compensation
        except Exception as e:
            log_and_emit('WARNING', 'audio_engine', f"Failed to calculate RMS for gain adjustment: {e}", category='audio')
            return 1.0

    def resample_audio_data(self, audio_data, orig_rate, target_rate):
        """对音频数据进行重采样

        Args:
            audio_data: numpy array of audio samples
            orig_rate: 原始采样率
            target_rate: 目标采样率

        Returns:
            numpy array: 重采样后的音频数据
        """
        if orig_rate == target_rate:
            return audio_data

        try:
            from scipy import signal
            gcd = self._gcd(orig_rate, target_rate)
            up = target_rate // gcd
            down = orig_rate // gcd
            resampled = signal.resample_poly(audio_data, up, down)
            log_and_emit('DEBUG', 'audio_engine', f"[resample_audio_data] Resampled from {orig_rate} to {target_rate} (up={up}, down={down}), frames: {len(audio_data)} -> {len(resampled)}", category='audio')
            return resampled
        except Exception as e:
            log_and_emit('WARNING', 'audio_engine', f"[resample_audio_data] scipy resampling failed, fallback to numpy: {e}", category='audio')
            ratio = target_rate / orig_rate
            num_samples = int(len(audio_data) * ratio)
            x_old = np.arange(len(audio_data))
            x_new = np.arange(num_samples) / ratio
            x_new = np.clip(x_new, 0, len(audio_data) - 1)
            resampled = np.interp(x_new, x_old, audio_data)
            log_and_emit('DEBUG', 'audio_engine', f"[resample_audio_data] numpy interp: frames {len(audio_data)} -> {num_samples}, ratio={ratio:.4f}", category='audio')
            return resampled

    def _gcd(self, a, b):
        """计算最大公约数"""
        while b:
            a, b = b, a % b
        return a


    @abstractmethod
    def get_devices(self):
        pass

class PyAudioDriver(AudioDriver):
    """基于 PyAudio 的音频驱动实现"""
    def __init__(self):
        self.pa = pyaudio.PyAudio()
        self._lock = threading.Lock()
        self._device_locks = {}
        self._device_locks_lock = threading.Lock()
        # 全局安全增益系数 (0.0 - 1.0)
        # 设置为 0.5 意味着即使请求 1.0 的增益，实际输出也只有 50% 的幅值
        self.GLOBAL_SAFE_GAIN = 1
    
    def _get_device_lock(self, device_index):
        with self._device_locks_lock:
            if device_index not in self._device_locks:
                self._device_locks[device_index] = threading.Lock()
            return self._device_locks[device_index]

    def get_devices(self):
        devices = []
        
        for i in range(self.pa.get_device_count()):
            dev_info = self.pa.get_device_info_by_index(i)
            host_api_info = self.pa.get_host_api_info_by_index(dev_info.get('hostApi'))
            if dev_info.get('maxOutputChannels') > 0:
                devices.append({
                    "index": i,
                    "name": dev_info.get('name'),
                    "channels": dev_info.get('maxOutputChannels'),
                    "sample_rate": int(dev_info.get('defaultSampleRate')),
                    "host_api": host_api_info.get('name')
                })
        return devices

    def play_multi(self, audio_configs, device_index=0, stop_event=None, offset=0, loop=False, app=None):
        """
        在同一个流中播放多个音频文件
        
        Args:
            audio_configs: 音频配置列表，每个元素为 dict:
                {
                    'file': 文件路径,
                    'channel': 输出通道索引,
                    'gain': 音量增益,
                    'offset': 播放偏移量(秒),
                    'delay': 延迟播放时间(秒)
                }
            device_index: 设备索引
            stop_event: 停止事件
            loop: 是否循环播放
            app: Flask应用实例，用于获取配置路径
        """
        if not audio_configs or len(audio_configs) < 1:
            return
        
        import traceback
        import wave
        import numpy as np
        import threading
        
        caller_info = traceback.format_stack()[-3].strip() if len(traceback.format_stack()) > 2 else 'unknown'
        log_and_emit('DEBUG', 'audio_engine', f"[play_multi] ENTRY: device={device_index}, configs={len(audio_configs)}, caller={caller_info}", category='audio')
        
        audio_files = []
        audio_file_paths = []
        audio_channels = []
        audio_gains = []
        audio_file_channels = []
        audio_file_rates = []
        audio_is_noise = []
        audio_delays = []

        for config in audio_configs:
            file_path = config.get('file')
            channel = config.get('channel', 0)
            gain = config.get('gain', 1.0)
            is_noise = config.get('is_noise', False)
            delay = config.get('delay', 0)

            if not os.path.exists(file_path):
                log_and_emit('ERROR', 'audio_engine', f"File not found: {file_path}", category='audio')
                continue

            try:
                wf = wave.open(file_path, 'rb')
                audio_offset = config.get('offset', 0)
                if audio_offset > 0:
                    try:
                        offset_frames = int(audio_offset * wf.getframerate())
                        total_frames = wf.getnframes()
                        if offset_frames >= total_frames:
                            offset_frames = total_frames - 1
                            log_and_emit('WARNING', 'audio_engine', f"Offset {audio_offset}s exceeds audio duration, adjusting to {offset_frames / wf.getframerate():.2f}s", category='audio')
                        wf.setpos(offset_frames)
                    except Exception as e:
                        log_and_emit('WARNING', 'audio_engine', f"Failed to set position {audio_offset}s for {file_path}: {e}", category='audio')
                audio_files.append(wf)
                audio_file_paths.append(file_path)
                audio_channels.append(channel)
                audio_gains.append(gain)
                audio_file_channels.append(wf.getnchannels())
                audio_file_rates.append(wf.getframerate())
                audio_is_noise.append(is_noise)
                audio_delays.append(delay)
                log_and_emit('DEBUG', 'audio_engine', f"[play_multi] Opened audio file: {file_path}, channel={channel}, delay={delay}, is_noise={is_noise}, rate={wf.getframerate()}", category='audio')
            except Exception as e:
                log_and_emit('ERROR', 'audio_engine', f"Failed to open audio file {file_path}: {e}", category='audio')
        
        log_and_emit('DEBUG', 'audio_engine', f"[play_multi] audio_configs count: {len(audio_configs)}, audio_files count after loop: {len(audio_files)}, audio_is_noise={audio_is_noise}, audio_delays={audio_delays}", category='audio')

        if not audio_files:
            return

        file_channels = audio_files[0].getnchannels()
        original_rate = audio_files[0].getframerate()

        log_and_emit('DEBUG', 'audio_engine', f"[play_multi] Audio file info: channels={file_channels}, rate={original_rate}", category='audio')

        audio_gain_compensations = []
        for file_path in audio_file_paths:
            gain_compensation = self.calculate_gain_compensation(file_path)
            audio_gain_compensations.append(gain_compensation)

        for _i in range(len(audio_files)):
            _spl_gain = audio_gains[_i] if _i < len(audio_gains) else 'N/A'
            _comp = audio_gain_compensations[_i] if _i < len(audio_gain_compensations) else 'N/A'
            _final = (_spl_gain * self.GLOBAL_SAFE_GAIN * _comp) if isinstance(_spl_gain, (int, float)) and isinstance(_comp, (int, float)) else 'N/A'
            _fname = os.path.basename(audio_file_paths[_i]) if _i < len(audio_file_paths) else 'N/A'
            log_and_emit('DEBUG', 'audio_engine', f"[play_multi] gain_chain[{_i}]: file={_fname}, spl_gain={_spl_gain}, compensation={_comp:.4f}, final={_final:.4f}", category='audio')

        dev_info = self.pa.get_device_info_by_index(device_index)
        max_channels = int(dev_info.get('maxOutputChannels', 2))
        default_sample_rate = int(dev_info.get('defaultSampleRate', 44100))

        log_and_emit('DEBUG', 'audio_engine', f"[play_multi] Device info: device={device_index}, name={dev_info.get('name', 'N/A')}, max_channels={max_channels}, default_sample_rate={default_sample_rate}", category='audio')

        stream = None
        try:
            dev_lock = self._get_device_lock(device_index)
            with dev_lock:
                target_rate = default_sample_rate

                # 预重采样：如果有音频的采样率与设备采样率不一致，提前进行重采样
                needs_resample = any(file_rate != target_rate for file_rate in audio_file_rates)

                if needs_resample:
                    if app:
                        resample_temp_dir = app.config.get('RESAMPLE_TEMP_PATH', os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'temp_resample'))
                    else:
                        try:
                            from flask import current_app
                            resample_temp_dir = current_app.config.get('RESAMPLE_TEMP_PATH', os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'temp_resample'))
                        except RuntimeError as e:
                            resample_temp_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'temp_resample')
                            log_and_emit('WARNING', 'audio_engine', f"[play_multi] current_app.config.get('RESAMPLE_TEMP_PATH') failed: {e}, using fallback: {resample_temp_dir}", category='audio')

                    os.makedirs(resample_temp_dir, exist_ok=True)
                    log_and_emit('DEBUG', 'audio_engine', f"[play_multi] Pre-resampling audio files to target rate {target_rate}, temp_dir={resample_temp_dir}", category='audio')

                    resampled_audio_files = []
                    resampled_audio_rates = []
                    resampled_temp_files = []

                    for i, wf in enumerate(audio_files):
                        file_rate = audio_file_rates[i]
                        if file_rate == target_rate:
                            resampled_audio_files.append(wf)
                            resampled_audio_rates.append(target_rate)
                        else:
                            try:
                                wf.rewind()
                                audio_data = wf.readframes(wf.getnframes())
                                audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)

                                resampled_np = self.resample_audio_data(audio_np, file_rate, target_rate)
                                resampled_np = np.clip(resampled_np, -32768, 32767).astype(np.int16)

                                temp_file = os.path.join(resample_temp_dir, f'resampled_{i}_{os.getpid()}_{threading.current_thread().ident}.wav')
                                log_and_emit('DEBUG', 'audio_engine', f"[play_multi] Resampled temp file path: {temp_file}", category='audio')
                                with wave.open(temp_file, 'wb') as resampled_wf:
                                    resampled_wf.setnchannels(audio_file_channels[i])
                                    resampled_wf.setsampwidth(2)
                                    resampled_wf.setframerate(target_rate)
                                    resampled_wf.writeframes(resampled_np.tobytes())

                                resampled_temp_files.append(temp_file)
                                resampled_wf_new = wave.open(temp_file, 'rb')
                                resampled_audio_files.append(resampled_wf_new)
                                resampled_audio_rates.append(target_rate)
                                log_and_emit('DEBUG', 'audio_engine', f"[play_multi] Pre-resampled audio {i}: {file_rate} -> {target_rate}, frames: {len(audio_np)} -> {len(resampled_np)}", category='audio')
                            except Exception as e:
                                log_and_emit('WARNING', 'audio_engine', f"[play_multi] Pre-resample failed for audio {i}, using original: {e}", category='audio')
                                resampled_audio_files.append(wf)
                                resampled_audio_rates.append(file_rate)

                    # 关闭原始文件
                    for wf in audio_files:
                        try:
                            wf.close()
                        except:
                            pass

                    audio_files = resampled_audio_files
                    audio_file_rates = resampled_audio_rates
                    original_rate = target_rate

                    log_and_emit('DEBUG', 'audio_engine', f"[play_multi] Pre-resampling completed, all files now at rate {target_rate}", category='audio')

                # 只尝试 max_channels 和 2（因为所有音频都已转为 default_sample_rate）
                candidate_configs = set()
                candidate_configs.add((max_channels, target_rate))
                candidate_configs.add((2, target_rate))
                configs = list(candidate_configs)

                log_and_emit('DEBUG', 'audio_engine', f"[play_multi] Trying {len(configs)} unique configurations: {configs}", category='audio')

                success = False
                last_err = None

                formats_to_try = [pyaudio.paInt16, pyaudio.paFloat32, pyaudio.paInt32]

                for ch, rate in configs:
                    for fmt in formats_to_try:
                        try:
                            _stream_audio_delays = audio_delays if audio_delays is not None else [0] * len(audio_configs)
                            log_and_emit('DEBUG', 'audio_engine', f"[play_multi] Attempting: device={device_index}, ch={ch}, rate={rate}, format={fmt}", category='audio')

                            def create_multi_callback(stream_channels, stream_rate, audio_gains, gain_compensations, file_channels_list, file_rates_list, channel_indices, wave_files, parent_stop_event, loop, audio_is_noise_list, audio_delays):

                                import threading
                                thread_name = threading.current_thread().name
                                log_and_emit('DEBUG', 'audio_engine', f"[play_multi] Creating callback: thread={thread_name}, wave_files_count={len(wave_files)}, audio_delays={audio_delays}", category='audio')

                                dry_finished_list = [False] * len(wave_files)
                                log_and_emit('DEBUG', 'audio_engine', f"[play_multi] dry_finished_list initialized with length: {len(wave_files)}, wave_files: {len(wave_files)}, audio_is_noise_list: {audio_is_noise_list}, audio_is_noise_list_len: {len(audio_is_noise_list) if audio_is_noise_list else 'None'}, audio_delays: {audio_delays}", category='audio')

                                def callback(in_data, frame_count, time_info, status):
                                    try:
                                        if parent_stop_event and parent_stop_event.is_set():
                                            log_and_emit('DEBUG', 'audio_engine', f"[play_multi] Stop event set, returning paComplete", category='audio')
                                            return (None, pyaudio.paComplete)

                                        out_buffer = np.zeros(frame_count * stream_channels, dtype=np.float32)

                                        all_empty = True
                                        dry_audio_count = sum(1 for i, n in enumerate(audio_is_noise_list) if not n) if audio_is_noise_list else len(wave_files)

                                        for i, wf in enumerate(wave_files):
                                            is_noise = audio_is_noise_list[i] if i < len(audio_is_noise_list) else False
                                            use_loop = is_noise

                                            delay = audio_delays[i] if i < len(audio_delays) else 0
                                            if delay > 0:
                                                elapsed_time = frame_count / stream_rate
                                                audio_delays[i] = max(0, delay - elapsed_time)

                                            current_delay = audio_delays[i] if i < len(audio_delays) else 0
                                            if current_delay > 0:
                                                data = bytes(frame_count * 2)
                                            else:
                                                data = wf.readframes(frame_count)

                                            if len(data) == 0 and current_delay <= 0:
                                                if use_loop:
                                                    wf.rewind()
                                                    data = wf.readframes(frame_count)
                                                    if len(data) == 0:
                                                        continue
                                                elif not is_noise:
                                                    if dry_finished_list[i]:
                                                        data = bytes(frame_count * 2)
                                                        continue
                                                    dry_finished_list[i] = True
                                                    data = bytes(frame_count * 2)
                                                    continue

                                            if not is_noise:
                                                all_empty = False

                                            audio_data = np.frombuffer(data, dtype=np.int16).astype(np.float32)
                                            file_ch = file_channels_list[i]
                                            actual_frames = len(audio_data) // file_ch

                                            effective_gain = audio_gains[i] * self.GLOBAL_SAFE_GAIN * gain_compensations[i]
                                            effective_gain_db = 20 * np.log10(effective_gain) if effective_gain > 0 else -999
                                            audio_data = audio_data * effective_gain

                                            ch_idx = channel_indices[i]

                                            if file_ch == 1:
                                                if ch_idx < stream_channels:
                                                    limit = min(actual_frames, frame_count)
                                                    out_buffer[ch_idx:limit*stream_channels:stream_channels] += audio_data[:limit]
                                            elif file_ch == 2:
                                                limit = min(actual_frames, frame_count)
                                                if ch_idx < stream_channels:
                                                    out_buffer[ch_idx:limit*stream_channels:stream_channels] += audio_data[0:limit*2:2]
                                                if ch_idx + 1 < stream_channels:
                                                    out_buffer[ch_idx+1:limit*stream_channels:stream_channels] += audio_data[1:limit*2:2]

                                        all_dry_finished = all(dry_finished_list[i] for i in range(len(wave_files)) if not audio_is_noise_list[i]) if audio_is_noise_list and any(not n for n in audio_is_noise_list) else False

                                        all_delays_zero = all(audio_delays[i] <= 0 for i in range(len(audio_delays)))

                                        if all_dry_finished and all_delays_zero and dry_audio_count > 0:
                                            log_and_emit('DEBUG', 'audio_engine', f"[play_multi] *** RETURNING paComplete: all_dry_finished={all_dry_finished}, all_delays_zero={all_delays_zero}, dry_audio_count={dry_audio_count}, dry_finished_list={dry_finished_list}", category='audio')
                                            return (None, pyaudio.paComplete)

                                        out_buffer = np.clip(out_buffer, -32768, 32767).astype(np.int16)

                                        return (out_buffer.tobytes(), pyaudio.paContinue)
                                    except Exception as e:
                                        log_and_emit('ERROR', 'audio_engine', f"Multi callback error: {e}", category='audio')
                                        return (None, pyaudio.paAbort)
                                return callback
                            
                            current_callback = create_multi_callback(
                                ch, rate, audio_gains, audio_gain_compensations, audio_file_channels, audio_file_rates, audio_channels, audio_files, stop_event, loop, audio_is_noise, _stream_audio_delays
                            )
                            
                            stream = self.pa.open(
                                format=fmt,
                                channels=ch,
                                rate=rate,
                                output=True,
                                output_device_index=device_index,
                                stream_callback=current_callback
                            )
                            success = True
                            log_and_emit('DEBUG', 'audio_engine', f"[play_multi] SUCCESS: device={device_index}, ch={ch}, rate={rate}, format={fmt}", category='audio')
                            break
                        except Exception as e:
                            last_err = e
                            log_and_emit('ERROR', 'audio_engine', f"[play_multi] Attempt failed: device={device_index}, ch={ch}, rate={rate}, format={fmt}, error={e}", category='audio')
                            continue
                    if success:
                        break
 
                
                if not success:
                    log_and_emit('ERROR', 'audio_engine', f"Failed to open multi audio stream after all attempts: {last_err}", category='audio')
                    return
                
                log_and_emit('DEBUG', 'audio_engine', f"[play_multi] Stream opened successfully, starting playback", category='audio')
                
                while stream.is_active():
                    if stop_event and stop_event.is_set():
                        break
                    threading.Event().wait(0.1)
        
        finally:
            if stream:
                try:
                    stream.stop_stream()
                    stream.close()
                except:
                    pass
            for wf in audio_files:
                try:
                    wf.close()
                except:
                    pass
            for temp_file in resampled_temp_files:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                        log_and_emit('DEBUG', 'audio_engine', f"[play_multi] Deleted resampled temp file: {temp_file}", category='audio')
                except Exception as e:
                    log_and_emit('WARNING', 'audio_engine', f"[play_multi] Failed to delete temp file {temp_file}: {e}", category='audio')
            log_and_emit('DEBUG', 'audio_engine', "Multi audio playback resources released", category='audio')


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
                from backend.utils.execution_engine import execution_engine
                self._audio_pool = execution_engine.audio_playback_pool
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

    def get_device_index(self, unique_id):
        """根据唯一标识获取物理设备索引 - 增强版"""
        if not unique_id:
            log_and_emit('ERROR', 'audio_engine', "get_device_index called with empty unique_id", category='audio')
            return None
        
        devices = self._get_cached_devices()
        log_and_emit('DEBUG', 'audio_engine', f"get_device_index: unique_id={unique_id}, available_devices={len(devices)}", category='audio')
        
        # # 增强：记录所有可用设备信息，便于调试
        # for i, dev in enumerate(devices):
        #     log_and_emit('DEBUG', 'audio_engine', f"Device {i}: name='{dev['name']}', api='{dev['host_api']}', index={dev['index']}, channels={dev['channels']}", category='audio')
        
        # 归一化比较：去除引号、特殊字符、多余空格，统一为小写
        def normalize(name):
            return name.replace("'", "").replace('"', '').strip().lower()
        
        # 清理输入的unique_id：去除多余空格
        clean_unique_id = unique_id.strip()
        normalized_unique_id = normalize(clean_unique_id)
        log_and_emit('DEBUG', 'audio_engine', f"Clean unique_id: '{clean_unique_id}', Normalized: '{normalized_unique_id}'", category='audio')
        
        # 1. 首先尝试精确匹配 (在所有 API 中找)
        exact_matches = []
        for dev in devices:
            if (clean_unique_id == dev['name'] or 
                clean_unique_id == str(dev['index']) or 
                normalize(dev['name']) == normalized_unique_id):
                exact_matches.append(dev)
        log_and_emit('DEBUG', 'audio_engine', f"Exact matches: {len(exact_matches)}", category='audio')
        
        # 2. 如果没有精确匹配，尝试更灵活的匹配
        matches = exact_matches if exact_matches else []
        
        if not matches:
            # 尝试匹配通道格式，如 "设备名 [Ch X]" -> "设备名"
            base_unique_id = clean_unique_id.split(' [Ch')[0] if ' [Ch' in clean_unique_id else clean_unique_id
            normalized_base = normalize(base_unique_id)
            log_and_emit('DEBUG', 'audio_engine', f"Trying base unique_id: '{base_unique_id}' (normalized: '{normalized_base}')", category='audio')
            
            # 精确匹配基础设备名
            base_matches = []
            for dev in devices:
                if normalize(dev['name']) == normalized_base:
                    base_matches.append(dev)
            
            if base_matches:
                matches = base_matches
                log_and_emit('DEBUG', 'audio_engine', f"Base name matches: {len(matches)}", category='audio')
            else:
                # 3. 尝试包含"扬声器"前缀的匹配（处理缺少前缀的情况）
                if "扬声器" not in clean_unique_id:
                    log_and_emit('DEBUG', 'audio_engine', "Trying to match with '扬声器' prefix...", category='audio')
                    speaker_unique_id = f"扬声器 {clean_unique_id}"
                    normalized_speaker = normalize(speaker_unique_id)
                    
                    speaker_matches = []
                    for dev in devices:
                        if normalize(dev['name']) == normalized_speaker or normalized_speaker in normalize(dev['name']):
                            speaker_matches.append(dev)
                    
                    if speaker_matches:
                        matches = speaker_matches
                        log_and_emit('DEBUG', 'audio_engine', f"Speaker prefix matches: {len(matches)}", category='audio')
                
                # 4. 尝试更加灵活的模糊匹配 - 包含关系
                if not matches:
                    log_and_emit('DEBUG', 'audio_engine', "Trying flexible fuzzy matching...", category='audio')
                    fuzzy_matches = []
                    for dev in devices:
                        dev_norm = normalize(dev['name'])
                        # 检查输入的unique_id是否是设备名的一部分，或者设备名是否是输入的一部分
                        if normalized_unique_id in dev_norm or dev_norm in normalized_unique_id:
                            fuzzy_matches.append(dev)
                    
                    if fuzzy_matches:
                        matches = fuzzy_matches
                        log_and_emit('DEBUG', 'audio_engine', f"Fuzzy matches: {len(matches)}", category='audio')
                    else:
                        # 5. 尝试只匹配括号内的部分（如 (2- RME Fireface UCX II)）
                        log_and_emit('DEBUG', 'audio_engine', "Trying to match content in parentheses...", category='audio')
                        import re
                        # 提取括号内的内容
                        bracket_content = re.findall(r'\(([^)]+)\)', clean_unique_id)
                        if bracket_content:
                            bracket_matches = []
                            for content in bracket_content:
                                normalized_bracket = normalize(content)
                                for dev in devices:
                                    if normalized_bracket in normalize(dev['name']):
                                        bracket_matches.append(dev)
                            
                            if bracket_matches:
                                matches = bracket_matches
                                log_and_emit('DEBUG', 'audio_engine', f"Bracket content matches: {len(matches)}", category='audio')
        
        if not matches:
            # 最终兜底：返回第一个可用设备
            if devices:
                selected_dev = devices[0]
                log_and_emit('WARNING', 'audio_engine', f"No matches found for '{unique_id}', returning first available device: '{selected_dev['name']}' (Index: {selected_dev['index']})", category='audio')
                return selected_dev['index']
            else:
                log_and_emit('ERROR', 'audio_engine', f"No device matches found for unique_id='{unique_id}' and no devices available", category='audio')
                return None
        
        # 优先级逻辑 (解决 RME 多通道在 MME 下降混到 1/2 的问题)
        priority_apis = ["Windows WDM-KS", "Windows DirectSound", "Windows WASAPI", "MME"]
        
        for api in priority_apis:
            # 在匹配的设备中寻找当前优先级的 API
            api_matches = [dev for dev in matches if dev['host_api'] == api]
            if api_matches:
                log_and_emit('DEBUG', 'audio_engine', f"API matches for {api}: {len(api_matches)}", category='audio')
                
                # 针对 RME 优化：优先选择不带"扬声器"字样的设备
                pure_devices = [dev for dev in api_matches if "扬声器" not in dev['name'] and "Speaker" not in dev['name']]
                if pure_devices:
                    selected_dev = pure_devices[0]
                    log_and_emit('INFO', 'audio_engine', f"Selected device: {selected_dev['name']} (API: {selected_dev['host_api']}, Index: {selected_dev['index']})", category='audio')
                    return selected_dev['index']
                # 否则返回该 API 下的第一个匹配
                selected_dev = api_matches[0]
                log_and_emit('INFO', 'audio_engine', f"Selected device (fallback): {selected_dev['name']} (API: {selected_dev['host_api']}, Index: {selected_dev['index']})", category='audio')
                return selected_dev['index']
                
        # 所有优先级都没有找到，返回第一个匹配
        selected_dev = matches[0]
        log_and_emit('INFO', 'audio_engine', f"Selected device (final fallback): {selected_dev['name']} (API: {selected_dev['host_api']}, Index: {selected_dev['index']})", category='audio')
        return selected_dev['index']

    def get_all_physical_devices(self):
        """扫描所有可用的物理输出设备及通道 - 按声卡聚合并去重"""
        devices = self._get_cached_devices()
        candidates = []
        
        all_devices = {}
        
        # 第一步：枚举所有WASAPI设备
        for dev_idx in range(len(devices)):
            dev = devices[dev_idx]
            
            # 只处理WASAPI设备
            if dev['host_api'] != 'Windows WASAPI':
                continue
            
            dev_name = dev['name']
            max_output = dev['channels']
            sample_rate = dev['sample_rate']
            host_api = dev['host_api']
            
            # 提取声卡前缀（支持所有设备类型）
            # 移除动态枚举索引，生成稳定的唯一标识
            import re
            # 提取括号内的内容 (X- 设备名) -> 提取出 "设备名"
            bracket_match = re.search(r'\(([^)]+)\)', dev_name)
            if bracket_match:
                bracket_content = bracket_match.group(1)
                # 检查是否是 X- 设备名 格式
                if re.match(r'^\d+-\s*', bracket_content):
                    # 移除数字和短横线前缀
                    stable_card_name = re.sub(r'^\d+-\s*', '', bracket_content)
                else:
                    stable_card_name = bracket_content
            else:
                stable_card_name = None
            
            if 'RME' in dev_name:
                # 处理RME设备
                if '802' in dev_name:
                    card_key = 'RME Fireface 802'
                elif 'UCX' in dev_name:
                    card_key = 'RME Fireface UCX II'
                elif 'Fireface' in dev_name:
                    card_key = 'RME Fireface'
                else:
                    card_key = 'Unknown RME'
                # 生成稳定的设备名称，移除动态索引
                if stable_card_name:
                    stable_dev_name = dev_name.replace(bracket_match.group(0), f"({stable_card_name})")
                else:
                    stable_dev_name = dev_name
            else:
                # 处理非RME设备，提取设备前缀作为分组key
                # 对于非RME设备，使用设备名称的前20个字符或直到第一个括号作为分组key
                try:
                    if ' (' in dev_name:
                        card_key = dev_name.split(' (')[0].strip()
                    else:
                        card_key = dev_name[:20].strip() if len(dev_name) > 20 else dev_name.strip()
                except:
                    card_key = dev_name.strip()
                # 生成稳定的设备名称
                if stable_card_name:
                    stable_dev_name = dev_name.replace(bracket_match.group(0), f"({stable_card_name})")
                else:
                    stable_dev_name = dev_name
            
            # 初始化声卡分组
            if card_key not in all_devices:
                all_devices[card_key] = {
                    'sub_devices_dedup': {},  # 去重后的子设备：key=声道范围，value=设备信息
                    'all_sub_devices': []  # 原始未去重列表（用于对比）
                }
            
            # 区分子设备和主设备
            if 'Analog (' in dev_name:
                # 提取声道范围（如1+2/3+4）
                try:
                    channel_range = dev_name.split('(')[1].split(')')[0].strip()
                except:
                    # 如果解析失败，使用完整名称作为声道范围
                    channel_range = dev_name
                
                # 存储原始设备信息
                all_devices[card_key]['all_sub_devices'].append({
                    'index': dev['index'],
                    'name': dev_name,
                    'channels': max_output,
                    'channel_range': channel_range
                })
                
                # 去重逻辑：仅保留每个声道范围的首个设备（索引最小）
                if channel_range not in all_devices[card_key]['sub_devices_dedup']:
                    all_devices[card_key]['sub_devices_dedup'][channel_range] = {
                        'index': dev['index'],
                        'name': dev_name,
                        'channels': max_output,
                        'channel_range': channel_range,
                        'sample_rate': sample_rate,
                        'host_api': host_api
                    }
            # 处理主设备（如"扬声器 (RME Fireface 802)"）
            elif '扬声器' in dev_name or 'Speaker' in dev_name:
                # 主设备作为单独的设备处理
                channel_range = 'Main'
                all_devices[card_key]['all_sub_devices'].append({
                    'index': dev['index'],
                    'name': dev_name,
                    'channels': max_output,
                    'channel_range': channel_range
                })
                
                if channel_range not in all_devices[card_key]['sub_devices_dedup']:
                    all_devices[card_key]['sub_devices_dedup'][channel_range] = {
                        'index': dev['index'],
                        'name': dev_name,
                        'channels': max_output,
                        'channel_range': channel_range,
                        'sample_rate': sample_rate,
                        'host_api': host_api
                    }
            else:
                # 处理其他类型设备，使用完整设备名称作为声道范围
                channel_range = 'Main'
                all_devices[card_key]['all_sub_devices'].append({
                    'index': dev['index'],
                    'name': dev_name,
                    'channels': max_output,
                    'channel_range': channel_range
                })
                
                if channel_range not in all_devices[card_key]['sub_devices_dedup']:
                    all_devices[card_key]['sub_devices_dedup'][channel_range] = {
                        'index': dev['index'],
                        'name': dev_name,
                        'channels': max_output,
                        'channel_range': channel_range,
                        'sample_rate': sample_rate,
                        'host_api': host_api
                    }
        
        # 第二步：处理去重结果，计算总声道数
        for card_name, info in all_devices.items():
            # 去重后子设备列表（转成有序列表，按声道范围排序）
            def sort_key(sub_dev):
                channel_range = sub_dev['channel_range']
                # 处理主设备（Main）
                if channel_range == 'Main':
                    return 0
                # 处理Analog声道（1+2, 3+4等）
                try:
                    return int(channel_range.split('+')[0])
                except:
                    # 其他情况，使用最大值
                    return 999
            
            dedup_subs = sorted(
                info['sub_devices_dedup'].values(),
                key=sort_key  # 按声道范围排序，Main在最前面
            )
            info['dedup_sub_list'] = dedup_subs
            
            # 重新计算总声道数（去重后）
            info['total_channels_dedup'] = sum([sub['channels'] for sub in dedup_subs])
            
            # 删除临时字典，简化输出
            del info['sub_devices_dedup']
            
            # 为每个子设备的每个通道生成候选设备
            for sub_dev in info['dedup_sub_list']:
                for ch in range(sub_dev['channels']):
                    # 生成唯一ID，包含设备完整名称+通道号，确保唯一性
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
            return

        dry_audio_files = [c for c in audio_configs if not c.get('is_noise', False)]
        if not dry_audio_files:
            return

        overlap_time_value = calculate_overlap_time(
            dry_audio_files[0]['file'],
            overlap_time,
            overlap_rate
        )

        if overlap_time_value < 0:
            return

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
        
        def play_device_audios(device_index, audio_list_with_delays, initial_delay, offset=0, loop=False, stop_event=None, is_overlap=False, app=None):
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
                self.driver.play_multi(multi_configs, device_index, stop_event, loop=loop, app=app)
                
                log_and_emit('DEBUG', 'audio_engine', f"[play_device_audios] Device {device_index} done")
            except Exception as e:
                log_and_emit('ERROR', 'audio_engine', f"[play_device_audios] Error: {e}")

        threads = []

        if task_id not in self.active_players:
            self.active_players[task_id] = {}

        if speakers_map is not None:
            audio_delays_with_config = calculate_speaker_aware_audio_delays(
                audio_configs, overlap_rate, is_overlap, offset, overlap_time_value, speakers_map=speakers_map
            )
        else:
            audio_delays_with_config = calculate_audio_delays(
                audio_configs, overlap_rate, is_overlap, offset, overlap_time_value
            )

        device_audio_map = {}
        for config, delay in audio_delays_with_config:
            dev_idx = config['device_index']
            if dev_idx not in device_audio_map:
                device_audio_map[dev_idx] = []
            device_audio_map[dev_idx].append((config, delay))
        
        log_and_emit('DEBUG', 'audio_engine', f"[play_overlap] device_audio_map: {[(f'dev{k}', [(c.get('file', '').split('\\\\')[-1], c.get('is_noise'), d) for c, d in v]) for k, v in device_audio_map.items()]}", category='audio')
        
        dev_indices = list(device_audio_map.keys())

        futures = []
        pool = self._get_audio_pool()

        for dev_idx in dev_indices:
            audio_list_with_delays = device_audio_map[dev_idx]
            audio_list = [c for c, d in audio_list_with_delays]

            device_stop_event = threading.Event()
            future = pool.submit(
                play_device_audios,
                dev_idx, audio_list_with_delays, 0, offset, loop, device_stop_event, is_overlap, app
            )

            self.active_players[task_id][f'device_{dev_idx}'] = {
                "future": future,
                "stop_event": device_stop_event
            }

            futures.append(future)
        
        return futures

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
