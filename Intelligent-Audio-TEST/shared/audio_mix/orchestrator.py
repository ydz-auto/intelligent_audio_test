# -*- coding: utf-8 -*-
"""AudioStreamOrchestrator — 混音编排路由层（INT-67，08 设计文档 §3.1）

接收渲染模式，分发到具体混音路径；自身不实现混音，持有公共前置逻辑
（噪声合并 → 源加载 → 格式适配 → RMS/SPL 增益 → speaker 感知时间轴），
两条 API 路径共用，无重复代码：

- mode='file'   → RenderAudioFile（unary 整段混音，HTTP 非实时）
- mode='stream' → RenderAudioStream（100ms 窗口流式混音，HTTP 流式 / Realtime）
- physical      → device_driver（E2E 物理播放，不经此处，显式拒绝）

混音 6 步发生在 `api_test_service` 进程内；消费端仅组装请求 + 消费产物。
源文件元数据（file_path / sample_rate / channels / duration）由消费端
经 audio ACL 补齐后随 render_config 传入，本模块只做 storage 读取。
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from shared.models.common_enums import DeviceType
from shared.utils.log_handler import log_and_emit
from shared.utils.config_manager import config_manager
from shared.audio_mix.format_adapter import (
    AudioFormat,
    AudioFormatAdapter,
    parse_target_format,
    unwrap_source_pcm,
)
from shared.audio_mix.spl_gain import ApiRmsSplService
from shared.audio_mix.timeline import (
    calculate_speaker_aware_audio_delays,
)


def render_cfg(key: str, default):
    return config_manager.get_value('audio_render', key, default)


@dataclass
class RenderSource:
    """混音源（Step 1-3 产物）：已适配到目标格式的 float32 交织采样 + 有效增益"""

    audio_id: Optional[int]
    kind: str                     # dry | interferer | noise（枚举语义，见 AudioKind）
    samples: Optional[np.ndarray] = None  # float32 交织（目标采样率/通道）
    gain_linear: float = 1.0
    loop: bool = False            # 噪声：铺满整个混音缓冲
    delay_frames: int = 0         # 干扰人/噪声：起始帧偏移（audios_config.delay ms → 帧）
    play_order: int = 0
    target_spl: Optional[float] = None


class AudioKind:
    """混音源类型常量（对应 08 文档 audios_config.type）"""

    SPEAKER = 'speaker'
    INTERFERER = 'interferer'
    NOISE = 'noise'


@dataclass
class RenderContext:
    """Step 1-4 公共前置产物，交由 RenderAudioFile / RenderAudioStream 完成 Step 5/6"""

    task_id: str
    target_format: AudioFormat
    sources: List[RenderSource] = field(default_factory=list)
    placements: List[Tuple[int, int]] = field(default_factory=list)  # (source 下标, 起始帧)
    total_frames: int = 0


class AudioStreamOrchestrator:
    """混音编排路由：公共前置（噪声合并/加载/适配/增益/时间轴）+ 路径分发"""

    def __init__(self):
        self._pcm_cache: Dict[int, Tuple[bytes, dict, float]] = {}
        self._cache_lock = threading.Lock()

    # ── 路由 ──

    @staticmethod
    def route(device_type: str, stream: bool = False) -> str:
        """编排路由（设计 §3.1 路由表）：返回混音路径标识

        - http_api 且 stream=False    → 'file'（RenderAudioFile）
        - http_api 且 stream=True     → 'stream'（RenderAudioStream）
        - websocket_api               → 'stream'
        - physical                    → ValueError（E2E 走 device_driver，不经此处）
        """
        if device_type == DeviceType.PHYSICAL:
            raise ValueError(
                "physical 设备走 device_driver 物理混音路径，不经 RenderService")
        if device_type == DeviceType.WEBSOCKET_API or (device_type == DeviceType.HTTP_API and stream):
            return 'stream'
        if device_type == DeviceType.HTTP_API:
            return 'file'
        raise ValueError(f"未知执行设备类型: {device_type}")

    # ── 配置化参数 ──

    @staticmethod
    def chunk_duration_ms() -> int:
        return max(1, int(render_cfg('chunk_duration_ms', 100)))

    @staticmethod
    def _pcm_cache_ttl_seconds() -> float:
        # AUDIO_PCM_CACHE_TTL（秒，0=关闭缓存）优先；否则取 audio_render 配置（默认 300s）
        raw = os.environ.get('AUDIO_PCM_CACHE_TTL')
        if raw is not None and raw.strip():
            try:
                return max(0.0, float(raw))
            except ValueError:
                pass
        return max(0.0, float(render_cfg('pcm_cache_ttl_seconds', 300)))

    @staticmethod
    def _pcm_cache_max_items() -> int:
        return max(1, int(render_cfg('pcm_cache_max_items', 64)))

    # ── 渲染入口 ──

    def render(self, render_config: dict, mode: str):
        """公共前置（Step 1-4）→ 路径分发（Step 5/6）

        mode='file'   → RenderAudioFile.render(context) -> dict（整文件产物）
        mode='stream' → RenderAudioStream.render(context) -> Iterator[dict]（逐 chunk）
        """
        context = self.prepare(render_config)
        if mode == 'file':
            from shared.audio_mix.render_file import RenderAudioFile
            return RenderAudioFile.render(context)
        if mode == 'stream':
            from shared.audio_mix.render_stream import RenderAudioStream
            return RenderAudioStream.render(context)
        raise ValueError(f"未知混音路径: {mode}（可选 file/stream）")

    # ── Step 1-4 公共前置 ──

    def prepare(self, render_config: dict) -> RenderContext:
        if not isinstance(render_config, dict):
            raise ValueError("render_config 必须为 dict")
        task_id = str(render_config.get('task_id', ''))
        target_format = parse_target_format(render_config.get('target_format'))
        spl_mapping = render_config.get('spl_mapping') or None
        audios = render_config.get('audios') or []

        # Step 0：噪声合并（case 级 > round 级）→ 并入混音源
        noise_cfg = self._resolve_noise(render_config)
        entries = [cfg for cfg in audios if isinstance(cfg, dict) and cfg.get('audio_id')]
        if noise_cfg:
            entries.append({**noise_cfg, 'type': AudioKind.NOISE})
        if not entries:
            raise ValueError("render_config 缺少 audios 与噪声配置，无可混音内容")

        sources: List[RenderSource] = []

        # Step 1 + 2 + 3：加载 PCM → 格式适配 → RMS 补偿 + SPL 增益
        for cfg in entries:
            kind = str(cfg.get('type') or AudioKind.SPEAKER)
            if kind not in (AudioKind.SPEAKER, AudioKind.INTERFERER, AudioKind.NOISE):
                raise ValueError(f"未知音频类型: {kind}（可选 speaker/interferer/noise）")
            pcm, meta = self._load_source_pcm(cfg)
            payload, src_fmt = unwrap_source_pcm(pcm, meta)
            adapted = AudioFormatAdapter.adapt(payload, src_fmt, target_format)
            samples = AudioFormatAdapter.parse_to_float32(adapted, target_format.bit_depth)
            target_spl = cfg.get('spl')
            gain = ApiRmsSplService.compute_source_gain(
                samples, target_spl, mapping=spl_mapping) if target_spl is not None else 1.0
            # delay 统一毫秒（08 文档 §五 输入契约），转目标采样率帧偏移
            delay_frames = int(round(float(cfg.get('delay', 0) or 0)
                                     * target_format.sample_rate / 1000.0))
            sources.append(RenderSource(
                audio_id=cfg.get('audio_id'),
                kind=kind,
                samples=samples,
                gain_linear=gain,
                loop=bool(cfg.get('loop', False)),
                delay_frames=delay_frames,
                play_order=int(cfg.get('play_order', 0) or 0),
                target_spl=target_spl,
            ))

        # Step 4：时间轴编排（speaker 感知交叠；噪声不参与，单独按 loop/delay 混入）
        context = RenderContext(task_id=task_id, target_format=target_format, sources=sources)
        self._build_timeline(context, render_config)
        return context

    # ── 噪声合并（case 级 > round 级；执行器已解析为 audio_id 并补齐资源字段） ──

    @staticmethod
    def _resolve_noise(render_config: dict) -> Optional[dict]:
        """选取噪声配置（case 级 > round 级），返回带资源字段的混音条目。"""
        for block in (render_config.get('case_noise'), render_config.get('round_noise')):
            if not isinstance(block, dict) or not block.get('audio_id'):
                continue
            return {
                'audio_id': block.get('audio_id'),
                'spl': block.get('spl'),
                'loop': bool(block.get('loop', False)),
                'delay': float(block.get('delay', 0) or 0),
                'file_path': block.get('file_path'),
                'sample_rate': block.get('sample_rate'),
                'channels': block.get('channels'),
                'duration': block.get('duration'),
            }
        return None

    # ── Step 1：源加载（渲染配置已带 file_path，含 TTL/条数上限缓存） ──

    def _load_source_pcm(self, cfg: dict) -> Tuple[bytes, dict]:
        """按混音条目加载音频字节 + 元数据（元数据由消费端经 audio ACL 补齐）"""
        audio_id = int(cfg['audio_id'])
        ttl = self._pcm_cache_ttl_seconds()
        now = time.monotonic()
        if ttl > 0:
            with self._cache_lock:
                cached = self._pcm_cache.get(audio_id)
                if cached and now - cached[2] < ttl:
                    return cached[0], cached[1]
        pcm, meta = self._load_from_storage(cfg)
        if ttl > 0:
            with self._cache_lock:
                if audio_id not in self._pcm_cache and \
                        len(self._pcm_cache) >= self._pcm_cache_max_items():
                    # 逐出最早插入条目，避免大文件长期驻留顶爆进程内存
                    self._pcm_cache.pop(next(iter(self._pcm_cache)), None)
                self._pcm_cache[audio_id] = (pcm, meta, now)
        return pcm, meta

    def _load_from_storage(self, cfg: dict) -> Tuple[bytes, dict]:
        from shared.infrastructure.storage import storage
        audio_id = cfg.get('audio_id')
        file_path = cfg.get('file_path')
        if not isinstance(file_path, str) or not file_path:
            raise FileNotFoundError(f"音频 {audio_id} 的 render_config 缺少 file_path")
        path = file_path if file_path.startswith(('oss://', 'local://')) \
            else storage.build_path('audios', file_path)
        pcm = storage.load_bytes(path)
        meta = {
            'sample_rate': cfg.get('sample_rate') or 0,
            'channels': cfg.get('channels') or 0,
            'duration': cfg.get('duration') or 0.0,
        }
        return pcm, meta

    # ── Step 4：时间轴（复用 E2E speaker 感知交叠计算） ──

    def _build_timeline(self, context: RenderContext, render_config: dict) -> None:
        """speaker 感知时间轴：play_order 排序 → 共同 speaker 判定 → overlap 交叠 →
        干扰人 startDelay 插入（复用 audio_timeline.calculate_speaker_aware_audio_delays）。

        时间轴以「帧」为单位承载到目标采样率；噪声条目由混音步骤单独按 loop/delay 处理。
        """
        rate = context.target_format.sample_rate
        channels = max(1, context.target_format.channels)
        speakers_map = {
            str(k): set(v) for k, v in (render_config.get('speakers_map') or {}).items()
        }
        timeline_configs = []
        for idx, src in enumerate(context.sources):
            frames = len(src.samples) // channels if src.samples is not None else 0
            timeline_configs.append({
                '_src_idx': idx,
                # speakers_map 键经 JSON 往返为字符串，统一以 str 归一化查找
                'audio_id': str(src.audio_id),
                'type': src.kind,
                'is_noise': src.kind == AudioKind.NOISE,
                'duration': frames / rate if rate else 0.0,
                'offset': 0,
                'delay': src.delay_frames / rate if rate else 0.0,
                'play_order': src.play_order,
                'file': '',   # duration 已按适配后帧数给出，时间轴不再读文件
            })
        overlap_rate = float(render_config.get('overlap_rate', 0) or 0)
        overlap_time = float(render_config.get('overlap_time', 0) or 0)
        delays = calculate_speaker_aware_audio_delays(
            timeline_configs, overlap_rate=overlap_rate, is_overlap=True,
            global_offset=0, overlap_time=overlap_time, speakers_map=speakers_map or None)

        total_frames = 0
        for cfg, start_time in delays:
            src_idx = cfg.get('_src_idx')
            if src_idx is None:
                continue
            src = context.sources[src_idx]
            if src.kind == AudioKind.NOISE:
                # 噪声不参与时间轴：起始帧 = delay（loop 铺满由混音步骤处理）
                start_frame = src.delay_frames
            else:
                # 干扰人 startDelay 已由时间轴以 start_time 返回（秒），
                # speaker 顺序/交叠起点同理，统一换算目标采样率帧
                start_frame = int(round(start_time * rate))
            end_frame = start_frame + len(src.samples) // channels
            if src.kind != AudioKind.NOISE or not src.loop:
                total_frames = max(total_frames, end_frame)
            context.placements.append((src_idx, start_frame))
        # loop 噪声铺满全缓冲；仅噪声时缓冲取噪声时长
        noise_frames = max(
            (src.delay_frames + len(src.samples) // channels
             for src in context.sources if src.kind == AudioKind.NOISE),
            default=0)
        total_frames = max(total_frames, noise_frames)
        min_frames = max(1, int(rate * self.chunk_duration_ms() / 1000))
        context.total_frames = max(total_frames, min_frames)
        log_and_emit('DEBUG', 'render_orchestrator',
                     f"[prepare] task_id={context.task_id} sources={len(context.sources)} "
                     f"total_frames={context.total_frames} rate={rate} ch={channels}",
                     category='audio')


# 进程内单例（servicer 委托入口）
audio_stream_orchestrator = AudioStreamOrchestrator()
