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
import logging
from abc import ABC, abstractmethod
from pydub import AudioSegment
from shared.utils.log_handler import log_and_emit
from shared.infrastructure.storage import storage
from audio_service.domain.services.audio_format_adapter import AudioFormatAdapter

logger = logging.getLogger(__name__)


# INT-593 P1 播放启动阻塞优化：增益补偿结果按 (文件路径, mtime, size) 签名缓存。
# 同一文件重复播放（E2E 多轮、重复试听）不再整文件分块 RMS 扫描，缩短起播延迟；
# 文件被替换（mtime/size 变化）自动失效；容量超限淘汰最早条目，防无限增长。
_GAIN_COMPENSATION_CACHE: dict = {}
_GAIN_COMPENSATION_CACHE_LOCK = threading.Lock()
_GAIN_COMPENSATION_CACHE_MAX = 512


def clear_gain_compensation_cache():
    """清空增益补偿缓存（测试隔离用）。"""
    with _GAIN_COMPENSATION_CACHE_LOCK:
        _GAIN_COMPENSATION_CACHE.clear()


class AudioDriver(ABC):
    """音频驱动基类"""

    def play_multi(self, audio_configs, device_index=0, stop_event=None, offset=0, loop=False):
        pass

    def calculate_gain_compensation(self, file_path):
        """计算增益补偿（根据音频实际 RMS 调整增益，确保达到预期的 SPL）

        INT-593 P1：结果按文件签名缓存，命中时直接返回（跳过整文件 RMS 扫描）。
        实际计算委托 _compute_gain_compensation（原实现主体）。
        """
        cache_key = self._gain_cache_key(file_path)
        if cache_key is not None:
            with _GAIN_COMPENSATION_CACHE_LOCK:
                cached = _GAIN_COMPENSATION_CACHE.get(cache_key)
            if cached is not None:
                return cached
        gain = self._compute_gain_compensation(file_path)
        if cache_key is not None:
            with _GAIN_COMPENSATION_CACHE_LOCK:
                if len(_GAIN_COMPENSATION_CACHE) >= _GAIN_COMPENSATION_CACHE_MAX:
                    _GAIN_COMPENSATION_CACHE.pop(next(iter(_GAIN_COMPENSATION_CACHE)))
                _GAIN_COMPENSATION_CACHE[cache_key] = gain
        return gain

    @staticmethod
    def _gain_cache_key(file_path):
        """增益缓存签名：绝对路径 + mtime_ns + size（文件被替换即失效）。"""
        try:
            st = os.stat(file_path)
            return (os.path.abspath(file_path), st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    def _compute_gain_compensation(self, file_path):
        """原 calculate_gain_compensation 主体（无缓存）。"""
        try:
            import math
            try:
                # 优先使用 wave 分块读取计算 RMS，避免整文件解码（内存优化）
                with wave.open(file_path, 'rb') as wf:
                    sampwidth = wf.getsampwidth()
                    framerate = wf.getframerate() or 44100
                    # 分块大小：1 秒音频
                    chunk_frames = framerate

                    sum_sq = 0.0
                    total_samples = 0
                    while True:
                        frames = wf.readframes(chunk_frames)
                        if not frames:
                            break
                        # 按采样宽度解析并统一归一化到 int16 幅度范围（含 24bit 逐字节重组，
                        # INT-67 防误解析：走 AudioFormatAdapter 共享解析器，无 int16 兜底）
                        audio_np = AudioFormatAdapter.to_int16_scale(frames, sampwidth)
                        sum_sq += float(np.sum(audio_np * audio_np))
                        total_samples += len(audio_np)

                    if total_samples <= 0:
                        return 1.0

                    max_amplitude = 32768.0
                    rms = math.sqrt(sum_sq / total_samples)
                    current_rms_db = 20 * math.log10(rms / max_amplitude) if rms > 0 else -999.0
                    gain_db = -30.0 - current_rms_db
                    gain_compensation = 10 ** (gain_db / 20)
                    log_and_emit('DEBUG', 'audio_engine', f"[calculate_gain_compensation] file={os.path.basename(file_path)}, current_rms_db={current_rms_db:.2f} dBFS, target=-30 dBFS, gain_db={gain_db:.2f} dB, gain_compensation={gain_compensation:.4f} (linear)", category='audio')
                    return gain_compensation
            except wave.Error:
                # 非 PCM WAV（mp3 等）wave 模块不支持，回退 pydub 整文件解码
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
            # 避免音频开头第一个字被衰减/畸变（迁移自 V9.7.10 audio_driver）。
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
        # PyAudio 流 open/close 的句柄线程安全护栏（进程内）：仅串行化驱动的
        # 流打开/关闭操作，播放期间不持有（同设备噪声/主音频并发播放不受影响）。
        # 物理设备的任务级占用互斥统一由 task_service 派发层
        # DistributedLock（RedisKeyPrefix.TASK_PHYSICAL_LOCK）承担（UC-0903 4a /
        # 附录A #4），此处不再维护 per-device 进程内互斥。
        self._stream_lifecycle_lock = threading.Lock()
        # 全局安全增益系数 (0.0 - 1.0)
        # 设置为 0.5 意味着即使请求 1.0 的增益，实际输出也只有 50% 的幅值
        self.GLOBAL_SAFE_GAIN = 1

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

    def terminate(self):
        """终止 PortAudio 会话（INT-2086 优雅停止入口）。

        强停带流的 audio_service 会把 WASAPI 会话锁在 RME Fireface 等驱动里，
        下一个进程 Pa_Initialize 撞锁挂死（越重启越死）。退出前必须先停止全部
        播放、等流在 play_multi finally 中 stop_stream + close，再调本方法
        pa.terminate()（Pa_Terminate）释放端点会话。

        调用后 self.pa 置 None：_get_driver 再次触发会重新 Pa_Initialize，
        但正常退出路径不会走到（进程即将结束）。
        """
        pa = getattr(self, 'pa', None)
        if pa is None:
            log_and_emit('INFO', 'audio_engine',
                         "PyAudio terminate skipped (pa 已为 None)", category='audio')
            return
        try:
            pa.terminate()
            self.pa = None
            log_and_emit('INFO', 'audio_engine',
                         "PyAudio PortAudio 会话已终止 (pa.terminate) — WASAPI 端点已释放",
                         category='audio')
        except Exception as e:
            log_and_emit('WARNING', 'audio_engine',
                         f"pa.terminate() 失败: {e}（进程退出时由解释器回收）",
                         category='audio')

    # ------------------------------------------------------------------ #
    #                    play_multi 子方法                                #
    # ------------------------------------------------------------------ #

    def _load_audio_files(self, audio_configs):
        """打开音频文件并提取元数据。

        若 config['file'] 不是本地存在的路径，则视作 OSS key（audios bucket），
        先下载到本地临时文件再打开。下载的临时源文件会返回给调用方，
        以便播放结束后清理。

        Returns:
            tuple: (audio_files, audio_channels, audio_gains, audio_file_channels,
                   audio_file_rates, audio_is_noise, audio_loops, audio_delays,
                   downloaded_temp_sources, audio_file_paths)
            其中 audio_file_paths 与 audio_files 等长对齐（仅成功打开的文件，
            INT-593 修复：增益补偿按文件对齐计算，避免失败 config 造成索引错位）。
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
        downloaded_temp_sources = []
        audio_file_paths = []

        for config in audio_configs:
            file_path = config.get('file')
            channel = config.get('channel', 0)
            gain = config.get('gain', 1.0)
            is_noise = config.get('is_noise', False)
            audio_loop = config.get('loop', False)
            delay = config.get('delay', 0)

            audio_delays.append(delay)

            # 源文件读取改造：若本地不存在，则通过 storage 抽象层下载
            # storage.load_file 会自动解析 oss:// / local:// scheme 前缀，
            # 并在 OSS 下载失败时回退到本地降级副本
            if not os.path.exists(file_path):
                try:
                    file_path = storage.load_file(file_path)
                    downloaded_temp_sources.append(file_path)
                    # 回写 config['file'] 为本地临时路径，供后续增益补偿等环节使用
                    config['file'] = file_path
                    log_and_emit('DEBUG', 'audio_engine', f"[play_multi] Downloaded audio via storage to temp: {file_path}", category='audio')
                except Exception as e:
                    log_and_emit('ERROR', 'audio_engine', f"Failed to load audio via storage (key={config.get('file')}): {e}", category='audio')
                    continue

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
                audio_file_paths.append(file_path)
                log_and_emit('DEBUG', 'audio_engine', f"[play_multi] Opened audio file: {file_path}, channel={channel}, delay={delay}, is_noise={is_noise}, loop={audio_loop}, rate={wf.getframerate()}", category='audio')
            except Exception as e:
                log_and_emit('ERROR', 'audio_engine', f"Failed to open audio file {file_path}: {e}", category='audio')

        log_and_emit('DEBUG', 'audio_engine', f"[play_multi] audio_configs count: {len(audio_configs)}, audio_files count after loop: {len(audio_files)}, audio_is_noise={audio_is_noise}, audio_delays={audio_delays}", category='audio')

        if not audio_files:
            # 无有效文件时也要清理已下载的临时源文件
            for tmp in downloaded_temp_sources:
                try:
                    if os.path.exists(tmp):
                        os.remove(tmp)
                except Exception:
                    logger.debug("清理已下载的临时源文件失败: %s", tmp, exc_info=True)
            return None

        return (audio_files, audio_channels, audio_gains, audio_file_channels,
                audio_file_rates, audio_is_noise, audio_loops, audio_delays,
                downloaded_temp_sources, audio_file_paths)

    def _pre_resample(self, audio_files, audio_file_rates, audio_file_channels, target_rate, app=None):
        """预重采样：将采样率不一致的音频统一到 target_rate。

        Returns:
            tuple: (resampled_files, resampled_rates, temp_files_to_clean)
        """
        default_resample_temp_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'temp_resample')
        if app:
            resample_temp_dir = getattr(app, 'config', {}).get('RESAMPLE_TEMP_PATH', os.environ.get('RESAMPLE_TEMP_PATH', default_resample_temp_dir))
        else:
            resample_temp_dir = os.environ.get('RESAMPLE_TEMP_PATH', default_resample_temp_dir)

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
                    sampwidth = wf.getsampwidth()
                    # 分块大小：源采样率对应 1 秒音频
                    chunk_frames = file_rate if file_rate else 44100

                    temp_file = os.path.join(resample_temp_dir, f'resampled_{i}_{os.getpid()}_{threading.current_thread().ident}.wav')
                    log_and_emit('DEBUG', 'audio_engine', f"[play_multi] Resampled temp file path: {temp_file}", category='audio')
                    total_in = 0
                    total_out = 0
                    with wave.open(temp_file, 'wb') as resampled_wf:
                        resampled_wf.setnchannels(audio_file_channels[i])
                        resampled_wf.setsampwidth(2)
                        resampled_wf.setframerate(target_rate)

                        while True:
                            audio_data = wf.readframes(chunk_frames)
                            if not audio_data:
                                break
                            # 根据采样宽度选择 dtype，统一归一化到 int16 幅度范围 [-32768, 32767]
                            # 块内变量作用域自然释放，避免多份 numpy 副本长期驻留
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
                            total_in += len(audio_np)
                            total_out += len(resampled_np)
                            resampled_wf.writeframes(resampled_np.tobytes())

                    resampled_temp_files.append(temp_file)
                    resampled_wf_new = wave.open(temp_file, 'rb')
                    resampled_audio_files.append(resampled_wf_new)
                    resampled_audio_rates.append(target_rate)
                    log_and_emit('DEBUG', 'audio_engine', f"[play_multi] Pre-resampled audio {i}: {file_rate} -> {target_rate}, frames: {total_in} -> {total_out}", category='audio')
                except Exception as e:
                    log_and_emit('WARNING', 'audio_engine', f"[play_multi] Pre-resample failed for audio {i}, using original: {e}", category='audio')
                    resampled_audio_files.append(wf)
                    resampled_audio_rates.append(file_rate)

        # 关闭原始文件
        for wf in audio_files:
            try:
                wf.close()
            except Exception:
                logger.debug("关闭预重采样前的原始音频文件失败", exc_info=True)

        log_and_emit('DEBUG', 'audio_engine', f"[play_multi] Pre-resampling completed, all files now at rate {target_rate}", category='audio')
        return resampled_audio_files, resampled_audio_rates, resampled_temp_files

    def _predecode_audio_buffers(self, audio_files, effective_gains, max_total_bytes=None):
        """预解码音频文件为 float32 交织数组并预乘有效增益（INT-593 P1 回调实时性）。

        把「每回调逐帧解析 + 整数组增益乘」前移到流打开前一次性完成，
        实时回调内仅做切片拷贝与混音，缩短回调 GIL 占用，免疫调度抢占。

        Args:
            audio_files: _load_audio_files/_pre_resample 返回的 wave 读句柄
            effective_gains: 与 audio_files 等长的有效增益（gain × safe × 补偿）
            max_total_bytes: 预解码总内存上限，超限回退每回调解析（防大文件 OOM）

        Returns:
            list: 与 audio_files 等长的 float32 交织数组；任一文件解码失败或
            总内存超限返回 None（调用方回退每回调解析路径）。
            返回 None 时所有 wave 句柄位置保持原样（本方法只读不推进）。
        """
        import time
        if max_total_bytes is None:
            max_total_bytes = int(os.environ.get(
                'PLAYBACK_PREDECODE_MAX_BYTES', 192 * 1024 * 1024))
        # 先预算内存：全部成功解码的 float32 字节数，超限直接回退（不动 wave 句柄）
        try:
            budget = 0
            for wf in audio_files:
                remaining = wf.getnframes() - wf.tell()
                budget += max(0, remaining) * wf.getnchannels() * 4
        except Exception:
            return None
        if budget > max_total_bytes:
            log_and_emit('DEBUG', 'audio_engine',
                         f"[play_multi] predecode budget {budget} > {max_total_bytes} bytes, "
                         f"fallback to per-callback parse", category='audio')
            return None

        t0 = time.monotonic()
        buffers = []
        for i, wf in enumerate(audio_files):
            try:
                start_pos = wf.tell()
                remaining = wf.getnframes() - start_pos
                audio_np = AudioFormatAdapter.to_int16_scale(
                    wf.readframes(remaining), wf.getsampwidth())
                # 预乘有效增益（回调内不再逐帧乘）
                buffers.append(audio_np * effective_gains[i])
                # 复位句柄位置，供回退路径/复用安全
                wf.rewind()
                wf.setpos(start_pos)
            except Exception as e:
                log_and_emit('WARNING', 'audio_engine',
                             f"[play_multi] predecode failed for file {i}, fallback: {e}",
                             category='audio')
                return None
        log_and_emit('DEBUG', 'audio_engine',
                     f"[play_multi] predecode done: {len(buffers)} files, "
                     f"{budget / 1024 / 1024:.1f} MiB, {time.monotonic() - t0:.3f}s",
                     category='audio')
        return buffers

    def _create_multi_callback(self, stream_channels, stream_rate, audio_gains, gain_compensations,
                               file_channels_list, file_rates_list, channel_indices,
                               wave_files, parent_stop_event, loop,
                               audio_is_noise_list, audio_delays, audio_loops_list,
                               effective_gains=None, decoded_buffers=None, play_metrics=None):
        """创建多音频回调函数（闭包方式，保持状态隔离）。

        INT-593 P1 回调实时性优化：
        - 传入有效增益 effective_gains（流打开前一次性算好），回调内不再重复计算；
        - 传入预解码缓冲 decoded_buffers（含预乘增益），回调内仅做切片拷贝与混音，
          省略每回调逐帧解析 + 整数组增益乘，缩短 GIL 占用；
        - 删除每文件每回调死代码 effective_gain_db = 20*log10(...)；
        - play_metrics（dict）量化采集：overflow 计数、回调最大耗时。
        预解码路径（decoded_buffers 非 None 且该项非 None）与原始每回调解析路径
        行为等价（逐帧输出一致），原路径作为大文件/解码失败的兜底。
        """
        thread_name = threading.current_thread().name
        log_and_emit('DEBUG', 'audio_engine', f"[play_multi] Creating callback: thread={thread_name}, wave_files_count={len(wave_files)}, audio_delays={audio_delays}, predecoded={decoded_buffers is not None}", category='audio')

        dry_finished_list = [False] * len(wave_files)
        log_and_emit('DEBUG', 'audio_engine', f"[play_multi] dry_finished_list initialized with length: {len(wave_files)}, wave_files: {len(wave_files)}, audio_is_noise_list: {audio_is_noise_list}, audio_is_noise_list_len: {len(audio_is_noise_list) if audio_is_noise_list else 'None'}, audio_delays: {audio_delays}", category='audio')

        # 预取每个文件的采样宽度，用于正确解析原始字节数据（兜底路径用）
        file_sampwidths = []
        for wf in wave_files:
            try:
                file_sampwidths.append(wf.getsampwidth())
            except Exception:
                file_sampwidths.append(2)

        # 预解码路径的读位置游标（与 wave 句柄 position 等价）
        positions = [0] * len(wave_files)
        if play_metrics is None:
            play_metrics = {'overflows': 0, 'callback_max_ms': 0.0, 'start_latency_ms': None}

        def callback(in_data, frame_count, time_info, status):
            cb_t0 = time.monotonic()
            try:
                if parent_stop_event and parent_stop_event.is_set():
                    log_and_emit('DEBUG', 'audio_engine', f"[play_multi] Stop event set, returning paComplete", category='audio')
                    return (None, pyaudio.paComplete)

                # 量化采集：PortAudio 回调 status 溢出/欠载计数（paOutputOverflow）
                overflow_flag = getattr(pyaudio, 'paOutputOverflow', 0)
                if status and overflow_flag and (status & overflow_flag):
                    play_metrics['overflows'] += 1

                out_buffer = np.zeros(frame_count * stream_channels, dtype=np.float32)

                all_empty = True
                dry_audio_count = sum(1 for i, n in enumerate(audio_is_noise_list) if not n) if audio_is_noise_list else len(wave_files)

                for i, wf in enumerate(wave_files):
                    is_noise = audio_is_noise_list[i] if i < len(audio_is_noise_list) else False
                    audio_loop = audio_loops_list[i] if (audio_loops_list and i < len(audio_loops_list)) else False
                    use_loop = is_noise or audio_loop
                    file_ch = file_channels_list[i]

                    delay = audio_delays[i] if i < len(audio_delays) else 0
                    if delay > 0:
                        elapsed_time = frame_count / stream_rate
                        audio_delays[i] = max(0, delay - elapsed_time)

                    current_delay = audio_delays[i] if i < len(audio_delays) else 0
                    # 延迟中的源输出静音（预解码/兜底两路等价，直接跳过混音）
                    if current_delay > 0:
                        continue

                    if decoded_buffers is not None and decoded_buffers[i] is not None:
                        # 预解码路径：仅切片拷贝 + 混音，无字节解析/无增益乘
                        buf = decoded_buffers[i]
                        n = buf.size
                        if n == 0:
                            continue
                        if not use_loop and positions[i] >= n:
                            # 与 wave.readframes 返回空一致：首次置 dry_finished，此后静音
                            if dry_finished_list[i]:
                                continue
                            dry_finished_list[i] = True
                            continue
                        start = positions[i] % n if use_loop else positions[i]
                        # INT-593 审计 P1-1 修复：游标为样本计数（交织），PortAudio 回调
                        # frame_count 为帧计数——mono 1帧=1样本恰好相等；stereo/多声道
                        # 每回调须取 frame_count * file_ch 个样本，否则只混入 1/file_ch
                        # 内容（播放拉伸 + 输出块剩余静音），且源按 1/file_ch 速度推进。
                        take = min(frame_count * file_ch, n - start)
                        audio_data = buf[start:start + take]
                        positions[i] += take
                        if take == 0:
                            continue
                        if not is_noise and not use_loop:
                            all_empty = False
                    else:
                        sampwidth = file_sampwidths[i] if i < len(file_sampwidths) else 2
                        data = wf.readframes(frame_count)

                        if len(data) == 0:
                            if use_loop:
                                wf.rewind()
                                data = wf.readframes(frame_count)
                                if len(data) == 0:
                                    continue
                            elif not use_loop:
                                if dry_finished_list[i]:
                                    continue
                                dry_finished_list[i] = True
                                continue

                        if not is_noise and not use_loop:
                            all_empty = False

                        # 按采样宽度正确解析字节数据，统一归一化到 int16 幅度范围
                        # （含 24bit 逐字节重组，INT-67 防误解析：共享解析器，无 int16 兜底）
                        audio_data = AudioFormatAdapter.to_int16_scale(data, sampwidth)
                        # 增益优先用流打开前算好的 effective_gains（回调内仅乘一次）；
                        # 未传入时按旧语义现算（外部直接调用的兼容兜底）
                        if effective_gains is not None:
                            audio_data = audio_data * effective_gains[i]
                        else:
                            audio_data = audio_data * (
                                audio_gains[i] * self.GLOBAL_SAFE_GAIN * gain_compensations[i])

                    actual_frames = len(audio_data) // file_ch
                    if actual_frames <= 0:
                        continue

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

                # 量化采集：回调最大耗时（GIL 抢占/调度抖动代理指标）
                cb_ms = (time.monotonic() - cb_t0) * 1000.0
                if cb_ms > play_metrics['callback_max_ms']:
                    play_metrics['callback_max_ms'] = cb_ms

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

    def play_multi(self, audio_configs, device_index=0, stop_event=None, offset=0, loop=False, app=None, playback_started_event=None, playback_finished_event=None, started_monotonic=None):
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
            started_monotonic: 任务提交时刻的 time.monotonic()（INT-593 量化采集），
                起播延迟 = 流打开时刻 - 提交时刻（含线程池排队等待）。
        """
        _play_entry_t0 = time.monotonic()
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
         audio_file_rates, audio_is_noise, audio_loops, audio_delays,
         downloaded_temp_sources, audio_file_paths) = loaded

        file_channels = audio_files[0].getnchannels()
        original_rate = audio_files[0].getframerate()
        log_and_emit('DEBUG', 'audio_engine', f"[play_multi] Audio file info: channels={file_channels}, rate={original_rate}", category='audio')

        # 2. 计算增益补偿（按成功打开的文件对齐，INT-593 修复索引错位；
        #    结果按文件签名缓存，同一文件重复播放不再整文件 RMS 全扫）
        audio_gain_compensations = [
            self.calculate_gain_compensation(p) for p in audio_file_paths
        ]
        # 有效增益一次算好（回调内不再逐次计算）
        effective_gains = [
            audio_gains[i] * self.GLOBAL_SAFE_GAIN * audio_gain_compensations[i]
            for i in range(len(audio_files))
        ]

        # 3. 获取设备信息
        dev_info = self.pa.get_device_info_by_index(device_index)
        max_channels = int(dev_info.get('maxOutputChannels', 2))
        default_sample_rate = int(dev_info.get('defaultSampleRate', 44100))
        log_and_emit('DEBUG', 'audio_engine', f"[play_multi] Device info: device={device_index}, name={dev_info.get('name', 'N/A')}, max_channels={max_channels}, default_sample_rate={default_sample_rate}", category='audio')

        # 4. 预重采样
        resampled_temp_files = []
        stream = None
        play_metrics = {'overflows': 0, 'callback_max_ms': 0.0, 'start_latency_ms': None}
        try:
            target_rate = default_sample_rate
            needs_resample = any(file_rate != target_rate for file_rate in audio_file_rates)

            if needs_resample:
                audio_files, audio_file_rates, resampled_temp_files = self._pre_resample(
                    audio_files, audio_file_rates, audio_file_channels, target_rate, app=app
                )
                original_rate = target_rate

            # 4.5 预解码 + 预乘增益（INT-593 P1：回调内仅切片拷贝，缩短 GIL 占用）
            # 大文件/解码失败返回 None → 回调走每回调解析兜底路径
            decoded_buffers = self._predecode_audio_buffers(audio_files, effective_gains)

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
                'effective_gains': effective_gains,
                'decoded_buffers': decoded_buffers,
                'play_metrics': play_metrics,
            }

            # _stream_lifecycle_lock 只保护 stream 的 open/close（句柄线程安全），
            # 不保护 while stream.is_active() 循环——否则背景噪声等长时间播放
            # 会持有锁，导致同设备的其他播放永久阻塞
            with self._stream_lifecycle_lock:
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

            # 量化采集：起播延迟 = 流打开时刻 - 提交时刻（含线程池排队 + 加载/RMS/重采样）
            play_metrics['start_latency_ms'] = (
                time.monotonic() - (started_monotonic or _play_entry_t0)) * 1000.0
            log_and_emit('INFO', 'audio_engine',
                         f"[play_metrics] start_latency_ms={play_metrics['start_latency_ms']:.1f}",
                         category='audio')

            while stream.is_active():
                if stop_event and stop_event.is_set():
                    break
                threading.Event().wait(0.1)

        finally:
            if stream:
                try:
                    with self._stream_lifecycle_lock:
                        stream.stop_stream()
                        stream.close()
                except Exception:
                    logger.debug("关闭音频流失败", exc_info=True)
            # 通知播放已完成（无论正常结束还是被停止）
            if playback_finished_event:
                playback_finished_event.set()
            for wf in audio_files:
                try:
                    wf.close()
                except Exception:
                    logger.debug("关闭音频文件句柄失败", exc_info=True)
            for temp_file in resampled_temp_files:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                        log_and_emit('DEBUG', 'audio_engine', f"[play_multi] Deleted resampled temp file: {temp_file}", category='audio')
                except Exception as e:
                    log_and_emit('WARNING', 'audio_engine', f"[play_multi] Failed to delete temp file {temp_file}: {e}", category='audio')
            # 清理从 OSS 下载的源文件临时副本（重采样的临时文件仍保持本地，已在上面清理）
            for src_temp in downloaded_temp_sources:
                try:
                    if os.path.exists(src_temp):
                        os.remove(src_temp)
                        log_and_emit('DEBUG', 'audio_engine', f"[play_multi] Deleted downloaded source temp file: {src_temp}", category='audio')
                except Exception as e:
                    log_and_emit('WARNING', 'audio_engine', f"[play_multi] Failed to delete downloaded source temp file {src_temp}: {e}", category='audio')
            log_and_emit('DEBUG', 'audio_engine', "Multi audio playback resources released", category='audio')
            # INT-593 量化采集：播放质量指标打点（underrun/overflow、回调最大耗时、起播延迟）
            log_and_emit('INFO', 'audio_engine',
                         f"[play_metrics] overflows={play_metrics['overflows']}, "
                         f"callback_max_ms={play_metrics['callback_max_ms']:.2f}, "
                         f"start_latency_ms={play_metrics['start_latency_ms']}",
                         category='audio')
            # 释放 COM
            if _com_initialized:
                try:
                    ctypes.windll.ole32.CoUninitialize()
                except Exception:
                    pass
