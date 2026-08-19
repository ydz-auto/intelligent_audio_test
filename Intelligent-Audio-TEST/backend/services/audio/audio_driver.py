"""
音频驱动层。

包含 AudioDriver 抽象基类和 PyAudioDriver 实现，
负责底层的 PyAudio 流操作、重采样和回调管理。
"""

import pyaudio
import wave
import threading
import time
import numpy as np
import os
import traceback
import ctypes
from abc import ABC, abstractmethod
from pydub import AudioSegment
from backend.utils.web.log_handler import log_and_emit


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
            # 对输入信号做边缘扩展 padding，消除 resample_poly 滤波器的启动瞬态，
            # 避免音频开头第一个字被衰减/畸变。
            pad_len = 2 * max(up, down)
            padded = np.pad(audio_data, (pad_len, pad_len), mode='edge')
            resampled = signal.resample_poly(padded, up, down)
            # 裁掉 padding 产生的多余样本，保持与原信号时间对齐
            trim_before = int(round(pad_len * up / down))
            resampled = resampled[trim_before:trim_before + int(round(len(audio_data) * up / down))]
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

    # ------------------------------------------------------------------ #
    #                    play_multi 子方法                                #
    # ------------------------------------------------------------------ #

    def _load_audio_files(self, audio_configs):
        """打开音频文件并提取元数据。

        Returns:
            tuple: (audio_files, audio_channels, audio_gains, audio_file_channels,
                   audio_file_rates, audio_is_noise, audio_loops, audio_delays)
            若无有效文件则返回 None。
        """
        audio_files = []
        audio_channels = []
        audio_gains = []
        audio_file_channels = []
        audio_file_rates = []
        audio_is_noise = []
        audio_loops = []
        audio_delays = []

        for config in audio_configs:
            file_path = config.get('file')
            channel = config.get('channel', 0)
            gain = config.get('gain', 1.0)
            is_noise = config.get('is_noise', False)
            audio_loop = config.get('loop', False)
            delay = config.get('delay', 0)

            audio_delays.append(delay)

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
                audio_channels.append(channel)
                audio_gains.append(gain)
                audio_file_channels.append(wf.getnchannels())
                audio_file_rates.append(wf.getframerate())
                audio_is_noise.append(is_noise)
                audio_loops.append(audio_loop)
                log_and_emit('DEBUG', 'audio_engine', f"[play_multi] Opened audio file: {file_path}, channel={channel}, delay={delay}, is_noise={is_noise}, loop={audio_loop}, rate={wf.getframerate()}", category='audio')
            except Exception as e:
                log_and_emit('ERROR', 'audio_engine', f"Failed to open audio file {file_path}: {e}", category='audio')

        log_and_emit('DEBUG', 'audio_engine', f"[play_multi] audio_configs count: {len(audio_configs)}, audio_files count after loop: {len(audio_files)}, audio_is_noise={audio_is_noise}, audio_delays={audio_delays}", category='audio')

        if not audio_files:
            return None

        return (audio_files, audio_channels, audio_gains, audio_file_channels,
                audio_file_rates, audio_is_noise, audio_loops, audio_delays)

    def _pre_resample(self, audio_files, audio_file_rates, audio_file_channels, target_rate, app=None):
        """预重采样：将采样率不一致的音频统一到 target_rate。

        Returns:
            tuple: (resampled_files, resampled_rates, temp_files_to_clean)
        """
        default_resample_temp_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'temp_resample')
        if app:
            resample_temp_dir = app.config.get('RESAMPLE_TEMP_PATH', default_resample_temp_dir)
        else:
            resample_temp_dir = default_resample_temp_dir

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
                    sampwidth = wf.getsampwidth()
                    # 根据采样宽度选择 dtype，统一归一化到 int16 幅度范围 [-32768, 32767]
                    if sampwidth == 1:
                        audio_np = np.frombuffer(audio_data, dtype=np.uint8).astype(np.float32)
                        audio_np = (audio_np - 128.0) * 256.0  # uint8 中心在128，转到 int16 范围
                    elif sampwidth == 2:
                        audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
                    elif sampwidth == 4:
                        audio_np = np.frombuffer(audio_data, dtype=np.int32).astype(np.float32)
                        audio_np = audio_np / 65536.0  # int32 -> int16 范围
                    else:
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

        log_and_emit('DEBUG', 'audio_engine', f"[play_multi] Pre-resampling completed, all files now at rate {target_rate}", category='audio')
        return resampled_audio_files, resampled_audio_rates, resampled_temp_files

    def _create_multi_callback(self, stream_channels, stream_rate, audio_gains, gain_compensations,
                               file_channels_list, file_rates_list, channel_indices,
                               wave_files, parent_stop_event, loop,
                               audio_is_noise_list, audio_delays, audio_loops_list):
        """创建多音频回调函数（闭包方式，保持状态隔离）。"""

        thread_name = threading.current_thread().name
        log_and_emit('DEBUG', 'audio_engine', f"[play_multi] Creating callback: thread={thread_name}, wave_files_count={len(wave_files)}, audio_delays={audio_delays}", category='audio')

        dry_finished_list = [False] * len(wave_files)
        log_and_emit('DEBUG', 'audio_engine', f"[play_multi] dry_finished_list initialized with length: {len(wave_files)}, wave_files: {len(wave_files)}, audio_is_noise_list: {audio_is_noise_list}, audio_is_noise_list_len: {len(audio_is_noise_list) if audio_is_noise_list else 'None'}, audio_delays: {audio_delays}", category='audio')

        # 预取每个文件的采样宽度，用于正确解析原始字节数据
        file_sampwidths = []
        for wf in wave_files:
            try:
                file_sampwidths.append(wf.getsampwidth())
            except Exception:
                file_sampwidths.append(2)

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
                    audio_loop = audio_loops_list[i] if (audio_loops_list and i < len(audio_loops_list)) else False
                    use_loop = is_noise or audio_loop

                    delay = audio_delays[i] if i < len(audio_delays) else 0
                    if delay > 0:
                        elapsed_time = frame_count / stream_rate
                        audio_delays[i] = max(0, delay - elapsed_time)

                    current_delay = audio_delays[i] if i < len(audio_delays) else 0
                    sampwidth = file_sampwidths[i] if i < len(file_sampwidths) else 2
                    if current_delay > 0:
                        data = bytes(frame_count * sampwidth * file_channels_list[i])
                    else:
                        data = wf.readframes(frame_count)

                    if len(data) == 0 and current_delay <= 0:
                        if use_loop:
                            wf.rewind()
                            data = wf.readframes(frame_count)
                            if len(data) == 0:
                                continue
                        elif not use_loop:
                            if dry_finished_list[i]:
                                data = bytes(frame_count * sampwidth * file_channels_list[i])
                                continue
                            dry_finished_list[i] = True
                            data = bytes(frame_count * sampwidth * file_channels_list[i])
                            continue

                    if not is_noise and not use_loop:
                        all_empty = False

                    # 根据采样宽度正确解析字节数据，统一归一化到 int16 幅度范围
                    if sampwidth == 1:
                        audio_data = np.frombuffer(data, dtype=np.uint8).astype(np.float32)
                        audio_data = (audio_data - 128.0) * 256.0
                    elif sampwidth == 2:
                        audio_data = np.frombuffer(data, dtype=np.int16).astype(np.float32)
                    elif sampwidth == 4:
                        audio_data = np.frombuffer(data, dtype=np.int32).astype(np.float32)
                        audio_data = audio_data / 65536.0  # int32 -> int16 范围
                    else:
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

                all_dry_finished = all(dry_finished_list[i] for i in range(len(wave_files)) if not audio_is_noise_list[i] and not (audio_loops_list[i] if audio_loops_list and i < len(audio_loops_list) else False)) if audio_is_noise_list and any(not audio_is_noise_list[i] and not (audio_loops_list[i] if audio_loops_list and i < len(audio_loops_list) else False) for i in range(len(wave_files))) else False

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

    def _try_open_stream(self, device_index, configs, formats_to_try,
                         callback_factory_kwargs):
        """尝试用不同 ch/rate/format 组合打开流。

        Args:
            device_index: 设备索引
            configs: [(channels, rate), ...] 候选配置
            formats_to_try: [pyaudio.paInt16, ...] 格式列表
            callback_factory_kwargs: 传给 _create_multi_callback 的 kwargs dict

        Returns:
            (stream, None) 成功 / (None, error) 失败
        """
        for ch, rate in configs:
            for fmt in formats_to_try:
                try:
                    log_and_emit('DEBUG', 'audio_engine', f"[play_multi] Attempting: device={device_index}, ch={ch}, rate={rate}, format={fmt}", category='audio')

                    current_callback = self._create_multi_callback(
                        stream_channels=ch,
                        stream_rate=rate,
                        **callback_factory_kwargs,
                    )

                    stream = self.pa.open(
                        format=fmt,
                        channels=ch,
                        rate=rate,
                        output=True,
                        output_device_index=device_index,
                        stream_callback=current_callback
                    )
                    log_and_emit('DEBUG', 'audio_engine', f"[play_multi] SUCCESS: device={device_index}, ch={ch}, rate={rate}, format={fmt}", category='audio')
                    return stream, None
                except Exception as e:
                    log_and_emit('ERROR', 'audio_engine', f"[play_multi] Attempt failed: device={device_index}, ch={ch}, rate={rate}, format={fmt}, error={e}", category='audio')
                    continue
        return None, Exception("All stream open attempts failed")

    # ------------------------------------------------------------------ #
    #                    主入口                                          #
    # ------------------------------------------------------------------ #

    def play_multi(self, audio_configs, device_index=0, stop_event=None, offset=0, loop=False, app=None, playback_started_event=None, playback_finished_event=None):
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
            playback_started_event: 播放真正开始事件（流打开后 set）
            playback_finished_event: 播放完成事件（流结束/停止后 set）
        """
        if not audio_configs or len(audio_configs) < 1:
            return

        # WASAPI 需要线程内 COM 初始化，线程池工作线程默认不初始化
        _com_initialized = False
        try:
            ole32 = ctypes.windll.ole32
            hr = ole32.CoInitializeEx(None, 0x0)  # COINIT_MULTITHREADED
            # S_OK=0x00000000, S_FALSE=0x00000001（已初始化也算成功）
            if hr in (0, 1):
                _com_initialized = True
        except Exception:
            pass

        caller_info = traceback.format_stack()[-3].strip() if len(traceback.format_stack()) > 2 else 'unknown'
        log_and_emit('DEBUG', 'audio_engine', f"[play_multi] ENTRY: device={device_index}, configs={len(audio_configs)}, caller={caller_info}", category='audio')

        # 1. 加载音频文件
        loaded = self._load_audio_files(audio_configs)
        if not loaded:
            return
        (audio_files, audio_channels, audio_gains, audio_file_channels,
         audio_file_rates, audio_is_noise, audio_loops, audio_delays) = loaded

        file_channels = audio_files[0].getnchannels()
        original_rate = audio_files[0].getframerate()
        log_and_emit('DEBUG', 'audio_engine', f"[play_multi] Audio file info: channels={file_channels}, rate={original_rate}", category='audio')

        # 2. 计算增益补偿
        audio_gain_compensations = [self.calculate_gain_compensation(c['file']) for c in audio_configs]

        # 3. 获取设备信息
        dev_info = self.pa.get_device_info_by_index(device_index)
        max_channels = int(dev_info.get('maxOutputChannels', 2))
        default_sample_rate = int(dev_info.get('defaultSampleRate', 44100))
        log_and_emit('DEBUG', 'audio_engine', f"[play_multi] Device info: device={device_index}, name={dev_info.get('name', 'N/A')}, max_channels={max_channels}, default_sample_rate={default_sample_rate}", category='audio')

        # 4. 预重采样
        resampled_temp_files = []
        stream = None
        try:
            dev_lock = self._get_device_lock(device_index)
            # dev_lock 只保护 stream 的 open/close，不保护 while stream.is_active() 循环
            # 否则背景噪声等长时间播放会持有锁，导致同设备的其他播放永久阻塞
            with dev_lock:
                target_rate = default_sample_rate
                needs_resample = any(file_rate != target_rate for file_rate in audio_file_rates)

                if needs_resample:
                    audio_files, audio_file_rates, resampled_temp_files = self._pre_resample(
                        audio_files, audio_file_rates, audio_file_channels, target_rate, app=app
                    )
                    original_rate = target_rate

                # 5. 尝试打开流
                candidate_configs = {(max_channels, target_rate), (2, target_rate)}
                configs = list(candidate_configs)
                log_and_emit('DEBUG', 'audio_engine', f"[play_multi] Trying {len(configs)} unique configurations: {configs}", category='audio')

                formats_to_try = [pyaudio.paInt16, pyaudio.paFloat32, pyaudio.paInt32]

                callback_factory_kwargs = {
                    'audio_gains': audio_gains,
                    'gain_compensations': audio_gain_compensations,
                    'file_channels_list': audio_file_channels,
                    'file_rates_list': audio_file_rates,
                    'channel_indices': audio_channels,
                    'wave_files': audio_files,
                    'parent_stop_event': stop_event,
                    'loop': loop,
                    'audio_is_noise_list': audio_is_noise,
                    'audio_delays': audio_delays if audio_delays is not None else [0] * len(audio_configs),
                    'audio_loops_list': audio_loops,
                }

                stream, last_err = self._try_open_stream(
                    device_index, configs, formats_to_try, callback_factory_kwargs
                )

            if not stream:
                log_and_emit('ERROR', 'audio_engine', f"Failed to open multi audio stream after all attempts: {last_err}", category='audio')
                # 流打开失败时仍需设置 started 事件，否则 play_round 会永久等待
                if playback_started_event:
                    playback_started_event.set()
                return

            log_and_emit('DEBUG', 'audio_engine', f"[play_multi] Stream opened successfully, starting playback", category='audio')

            if playback_started_event:
                playback_started_event.set()

            while stream.is_active():
                if stop_event and stop_event.is_set():
                    break
                threading.Event().wait(0.1)

        finally:
            if stream:
                try:
                    dev_lock = self._get_device_lock(device_index)
                    with dev_lock:
                        stream.stop_stream()
                        stream.close()
                except:
                    pass
            # 通知播放已完成（无论正常结束还是被停止）
            if playback_finished_event:
                playback_finished_event.set()
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
            # 释放 COM
            if _com_initialized:
                try:
                    ctypes.windll.ole32.CoUninitialize()
                except Exception:
                    pass
