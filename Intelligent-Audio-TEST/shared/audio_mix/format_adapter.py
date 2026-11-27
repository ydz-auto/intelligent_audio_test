# -*- coding: utf-8 -*-
"""AudioFormatAdapter — 音频格式适配器（INT-67 混音下沉，08 设计文档 §2）

不同被测 API 的采样率/位深/通道数不同，混音前必须把所有源统一适配到
api.audio_config 声明的目标格式（不同采样率的样本无法直接叠加）。

转换顺序固定为「位深 → 采样率 → 通道」（设计契约，不得调换）：
1. 位深归一化 → float32 [-1.0, 1.0]（先归一化再量化，避免截断误差累积）
2. 重采样 src_rate → dst_rate（resample_poly 有理分数重采样，抗混叠）
3. 通道转换 src_ch → dst_ch（下混发生在重采样之后，省一半算力）
4. 按目标位深度化

24bit 防误解析：3 字节小端有符号整数逐字节重组，绝不落入 int16 兜底分支。
"""
from __future__ import annotations

import enum
import io
import math
import wave
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np


class BitDepth(enum.Enum):
    """位深枚举：(名称, 每样本字节数, 满量程)"""

    S16 = ('s16', 2, 32768)
    S24 = ('s24', 3, 8388608)
    S32 = ('s32', 4, 2147483648)

    def __init__(self, name_str, bytes_per_sample, full_scale):
        self.name_str = name_str
        self.bytes_per_sample = bytes_per_sample
        self.full_scale = full_scale

    @classmethod
    def from_str(cls, value) -> 'BitDepth':
        for bd in cls:
            if bd.name_str == str(value):
                return bd
        raise ValueError(f"不支持的位深: {value}（可选 s16/s24/s32）")


@dataclass(frozen=True)
class AudioFormat:
    """不可变音频格式（audio_config 值对象）"""

    sample_rate: int = 24000
    bit_depth: str = 's16'
    channels: int = 1
    container: str = 'pcm'

    @property
    def bit_depth_enum(self) -> BitDepth:
        return BitDepth.from_str(self.bit_depth)

    @property
    def bytes_per_sample(self) -> int:
        return self.bit_depth_enum.bytes_per_sample

    @property
    def full_scale(self) -> float:
        return float(self.bit_depth_enum.full_scale)

    def to_dict(self) -> dict:
        return {
            'sample_rate': int(self.sample_rate),
            'bit_depth': self.bit_depth,
            'channels': int(self.channels),
            'container': self.container,
        }


def parse_target_format(fmt: Optional[dict]) -> AudioFormat:
    """解析 api.audio_config（dict），未配置/缺字段回退默认值（24kHz/s16/mono/pcm）"""
    merged = dict(AudioFormatAdapter.DEFAULT_FORMAT)
    if isinstance(fmt, dict):
        for key in ('sample_rate', 'bit_depth', 'channels', 'container'):
            if fmt.get(key) is not None:
                merged[key] = fmt[key]
    BitDepth.from_str(merged['bit_depth'])   # 位深枚举化：非法值立即拒绝，不静默兜底
    return AudioFormat(
        sample_rate=int(merged['sample_rate']),
        bit_depth=str(merged['bit_depth']),
        channels=int(merged['channels']),
        container=str(merged.get('container', 'pcm')),
    )


def detect_source_format(pcm: bytes, audio_meta: Optional[dict] = None) -> AudioFormat:
    """源格式探测，优先级（设计 §2.3，实现差异记录见文档补记）：

    1. WAV 头解析（真实容器，最高置信）
    2. 库内元数据（audios 表 sample_rate/channels，bit_depth 无列默认 s16）
    3. 库内默认（24kHz/s16/mono）
    """
    wav_fmt = _parse_wav_header(pcm)
    if wav_fmt is not None:
        return wav_fmt
    meta = audio_meta or {}
    if meta.get('sample_rate') or meta.get('channels'):
        return AudioFormat(
            sample_rate=int(meta.get('sample_rate') or 24000),
            bit_depth='s16',
            channels=int(meta.get('channels') or 1),
        )
    return parse_target_format(None)


def unwrap_source_pcm(pcm: bytes, audio_meta: Optional[dict] = None) -> Tuple[bytes, AudioFormat]:
    """源载入统一入口：WAV 容器剥离头部取数据段，裸 PCM 原样返回。

    容器头部字节不得进入样本解析——44B RIFF 头按 int16 解析混入 22 个垃圾
    样本并使时间轴整体偏移；24bit 因 44%3=2 持续 1 字节错位致数据段全样本
    损毁。WAV 源格式以头部声明为准（库内无 bit_depth 列，元数据不可信）；
    非 WAV 源按 元数据 > 库内默认 探测。返回 (数据段 PCM, 源格式)。
    """
    wav_fmt = _parse_wav_header(pcm)
    if wav_fmt is None:
        return pcm, detect_source_format(pcm, audio_meta)
    with wave.open(io.BytesIO(pcm), 'rb') as w:
        return w.readframes(w.getnframes()), wav_fmt


def _parse_wav_header(pcm: bytes) -> Optional[AudioFormat]:
    try:
        with wave.open(io.BytesIO(pcm), 'rb') as w:
            sampwidth = w.getsampwidth()
            if sampwidth not in (1, 2, 3, 4):
                return None
            bit_depth = {1: 's16', 2: 's16', 3: 's24', 4: 's32'}[sampwidth]
            return AudioFormat(
                sample_rate=w.getframerate(),
                bit_depth=bit_depth,
                channels=w.getnchannels(),
            )
    except (wave.Error, EOFError):
        return None


class AudioFormatAdapter:
    """音频格式适配器：位深转换 → 重采样 → 通道上下混（顺序固定）"""

    DEFAULT_FORMAT = {'sample_rate': 24000, 'bit_depth': 's16', 'channels': 1, 'container': 'pcm'}

    # ---------- 位深（Step 1 / Step 4） ----------

    @staticmethod
    def parse_to_float32(pcm: bytes, bit_depth: str) -> np.ndarray:
        """任意位深线性 PCM bytes → float32 [-1, 1]（交织排列）。

        24bit：3 字节小端有符号数逐字节重组（防 int16 误解析）。
        8bit：WAV 约定无符号，中心 128。
        """
        bd = BitDepth.from_str(bit_depth)
        if bd is BitDepth.S16:
            usable = pcm[: len(pcm) // 2 * 2]
            return np.frombuffer(usable, dtype='<i2').astype(np.float32) / 32768.0
        if bd is BitDepth.S24:
            usable = pcm[: len(pcm) // 3 * 3]
            raw = np.frombuffer(usable, dtype=np.uint8)
            if raw.size == 0:
                return np.zeros(0, dtype=np.float32)
            raw = raw.reshape(-1, 3).astype(np.int32)
            vals = raw[:, 0] | (raw[:, 1] << 8) | (raw[:, 2] << 16)
            vals = np.where(vals >= 1 << 23, vals - (1 << 24), vals)
            return vals.astype(np.float32) / float(1 << 23)
        # S32
        usable = pcm[: len(pcm) // 4 * 4]
        return np.frombuffer(usable, dtype='<i4').astype(np.float32) / 2147483648.0

    @staticmethod
    def to_int16_scale(frames: bytes, sampwidth: int) -> np.ndarray:
        """WAV 帧字节 → float32（int16 幅度约定，物理播放链路用）。

        E2E 驱动链路全部按 int16 幅度混音：u8 (x-128)*256、s16 原值、
        s24 /256、s32 /65536。24bit 逐字节重组，绝不落 int16 兜底分支。
        """
        if sampwidth == 1:
            arr = np.frombuffer(frames, dtype=np.uint8).astype(np.float32)
            return (arr - 128.0) * 256.0
        if sampwidth == 2:
            usable = frames[: len(frames) // 2 * 2]
            return np.frombuffer(usable, dtype='<i2').astype(np.float32)
        if sampwidth == 3:
            usable = frames[: len(frames) // 3 * 3]
            raw = np.frombuffer(usable, dtype=np.uint8)
            if raw.size == 0:
                return np.zeros(0, dtype=np.float32)
            raw = raw.reshape(-1, 3).astype(np.int32)
            vals = raw[:, 0] | (raw[:, 1] << 8) | (raw[:, 2] << 16)
            vals = np.where(vals >= 1 << 23, vals - (1 << 24), vals)
            return vals.astype(np.float32) / 256.0
        if sampwidth == 4:
            usable = frames[: len(frames) // 4 * 4]
            return np.frombuffer(usable, dtype='<i4').astype(np.float32) / 65536.0
        raise ValueError(f"不支持的采样宽度: {sampwidth}")

    @staticmethod
    def quantize(samples: np.ndarray, bit_depth: str) -> bytes:
        """float32 [-1, 1] → 目标位深 PCM bytes（防削波裁剪到满量程）"""
        bd = BitDepth.from_str(bit_depth)
        clipped = np.clip(samples, -1.0, 1.0 - 1.0 / bd.full_scale)
        scaled = clipped * bd.full_scale
        if bd is BitDepth.S16:
            return scaled.astype('<i2').tobytes()
        if bd is BitDepth.S24:
            vals = scaled.astype('<i4')
            out = np.empty((vals.size, 3), dtype=np.uint8)
            out[:, 0] = vals.view(np.uint8).reshape(-1, 4)[:, 0]
            out[:, 1] = vals.view(np.uint8).reshape(-1, 4)[:, 1]
            out[:, 2] = vals.view(np.uint8).reshape(-1, 4)[:, 2]
            return out.tobytes()
        return scaled.astype('<i4').tobytes()

    # ---------- 采样率（Step 2） ----------

    @staticmethod
    def resample(samples: np.ndarray, src_rate: int, dst_rate: int,
                 channels: int = 1) -> np.ndarray:
        """resample_poly 有理分数重采样（gcd 化简，抗混叠）；同率直返。

        交织多声道按帧维度（axis=0）逐声道重采样，禁止把交织流当一维信号。
        边缘扩展 padding 消除滤波器启动瞬态（对齐 audio_driver.resample_audio_data）。
        """
        if samples.size == 0 or src_rate == dst_rate:
            return samples
        src_rate, dst_rate = int(src_rate), int(dst_rate)
        channels = max(1, int(channels))
        gcd = math.gcd(src_rate, dst_rate)
        up, down = dst_rate // gcd, src_rate // gcd
        # 懒加载（对齐 audio_driver：scipy 缺失时由调用方回退线性插值）
        from scipy.signal import resample_poly
        pad_len = 2 * max(up, down)
        if channels > 1:
            frames = samples[: len(samples) // channels * channels].reshape(-1, channels)
            padded = np.pad(frames, ((pad_len, pad_len), (0, 0)), mode='edge')
            resampled = resample_poly(padded, up, down, axis=0).astype(np.float32)
            trim_before = int(round(pad_len * up / down))
            out_frames = int(round(len(frames) * up / down))
            return resampled[trim_before:trim_before + out_frames].reshape(-1)
        padded = np.pad(samples, (pad_len, pad_len), mode='edge')
        resampled = resample_poly(padded, up, down).astype(np.float32)
        trim_before = int(round(pad_len * up / down))
        out_len = int(round(len(samples) * up / down))
        return resampled[trim_before:trim_before + out_len]

    # ---------- 通道（Step 3） ----------

    @staticmethod
    def convert_channels(samples: np.ndarray, src_ch: int, dst_ch: int) -> np.ndarray:
        """通道转换：stereo→mono 下混均值；mono→stereo 复制；其余组合抛配置错误"""
        if src_ch == dst_ch:
            return samples
        if src_ch == 2 and dst_ch == 1:
            frames = samples[: len(samples) // 2 * 2].reshape(-1, 2)
            return frames.mean(axis=1).astype(np.float32)
        if src_ch == 1 and dst_ch == 2:
            return np.repeat(samples, 2).astype(np.float32)
        raise ValueError(f"不支持的通道转换: {src_ch} → {dst_ch}（配置错误不静默兜底）")

    # ---------- 组合入口 ----------

    @staticmethod
    def adapt(pcm: bytes, src: AudioFormat, dst: AudioFormat) -> bytes:
        """src → dst 转换（固定顺序：位深 → 采样率 → 通道 → 目标位深度化）

        重采样在源声道布局下进行（设计契约：下混发生在重采样之后），
        交织多声道经 resample(channels=src.channels) 按帧维度处理。
        """
        samples = AudioFormatAdapter.parse_to_float32(pcm, src.bit_depth)
        if src.sample_rate != dst.sample_rate:
            samples = AudioFormatAdapter.resample(
                samples, src.sample_rate, dst.sample_rate, channels=src.channels)
        if src.channels != dst.channels:
            samples = AudioFormatAdapter.convert_channels(samples, src.channels, dst.channels)
        return AudioFormatAdapter.quantize(samples, dst.bit_depth)

    @staticmethod
    def wrap_container(pcm_bytes: bytes, fmt: AudioFormat, container: Optional[str] = None) -> bytes:
        """按容器格式包装：wav → wave 头 + PCM；pcm → 裸流直返"""
        target = (container or fmt.container or 'pcm').lower()
        if target == 'pcm':
            return pcm_bytes
        if target != 'wav':
            raise ValueError(f"不支持的容器格式: {target}（可选 pcm/wav）")
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as w:
            w.setnchannels(fmt.channels)
            w.setsampwidth(fmt.bytes_per_sample)
            w.setframerate(fmt.sample_rate)
            w.writeframes(pcm_bytes)
        return buf.getvalue()
