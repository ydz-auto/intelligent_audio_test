"""
音频时间轴计算模块。

包含所有与时间轴、交叠播放、speaker感知相关的纯函数，
不依赖任何类实例，可独立测试。
"""

import wave
import numpy as np
from shared.utils.log_handler import log_and_emit


def get_audio_duration(file_path):
    """
    获取音频文件的时长

    Args:
        file_path: 音频文件路径

    Returns:
        float: 音频时长（秒），失败返回0
    """
    try:
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
        from shared.models.models import AudioAnnotation
        return AudioAnnotation.query.filter_by(
            audio_id=audio_id,
            deleted=False
        ).all()
    
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
    dry_configs = [c.copy() for c in audio_configs
                   if not c.get('is_noise', False) and c.get('type') != 'interferer']
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

    interferer_configs = [c.copy() for c in audio_configs if c.get('type') == 'interferer']
    for config in interferer_configs:
        audio_delays_with_config.append((config, config.get('delay', 0)))

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
    dry_configs = [c.copy() for c in audio_configs
                   if not c.get('is_noise', False) and c.get('type') != 'interferer']
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

    interferer_configs = [c.copy() for c in audio_configs if c.get('type') == 'interferer']
    for config in interferer_configs:
        audio_delays_with_config.append((config, config.get('delay', 0)))

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
        
        if device_obj and device_obj.current_spl_mapping_id:
            try:
                from e2e_test_service.audio.spl_service import spl_service
                target_spl = audio_config.get('spl', 65.0)
                gain = spl_service.spl_to_gain(device_obj.current_spl_mapping_id, target_spl, app=app)
                gain_db = 20 * np.log10(gain) if gain > 0 else -999
                log_and_emit('DEBUG', 'audio_engine', f"[get_audio_configs_for_offset] mapping_id={device_obj.current_spl_mapping_id}, target_spl={target_spl}, SPL gain={gain:.4f} ({gain_db:.2f} dB)", category='audio')
            except Exception as e:
                log_and_emit('ERROR', 'audio_engine', f"[get_audio_configs_for_offset] SPL mapping failed: mapping_id={device_obj.current_spl_mapping_id}, error={e}", category='audio')
                gain = device_info.get('gain', 1.0)
        else:
            gain = device_info.get('gain', 1.0)
            log_and_emit('DEBUG', 'audio_engine', f"[get_audio_configs_for_offset] No SPL mapping, using default gain={gain}", category='audio')
        
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
