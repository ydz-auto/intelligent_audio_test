# -*- coding: utf-8 -*-
"""AudioStreamOrchestrator — 混音编排路由层（INT-67，08 设计文档 §3.1）

接收渲染模式，分发到具体混音路径；自身不实现混音，持有公共前置逻辑
（噪声合并 → 源加载 → 格式适配 → RMS/SPL 增益 → speaker 感知时间轴），
两条 API 路径共用，无重复代码：

- mode='file'   → RenderAudioFile（unary 整段混音，HTTP 非实时）
- mode='stream' → RenderAudioStream（100ms 窗口流式混音，HTTP 流式 / Realtime）
- physical      → device_driver（E2E 物理播放，不经此处，显式拒绝）

混音 6 步全部发生在 audio_service 进程内；消费端仅组装请求 + 消费产物。
噪声合并复用 build_noise_info（executor 侧仅透传两级配置）。
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from shared.utils.log_handler import log_and_emit
from shared.utils.config_manager import config_manager
from audio_service.domain.services.audio_format_adapter import (
    AudioFormat,
    AudioFormatAdapter,
    detect_source_format,
    parse_target_format,
)
from audio_service.domain.services.api_rms_spl_service import ApiRmsSplService
from audio_service.infrastructure.audio.audio_timeline import (
    calculate_speaker_aware_audio_delays,
)
from audio_service.infrastructure.audio.playback_config_builder import build_noise_info


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

    DEVICE_PHYSICAL = 'physical'

    def __init__(self):
        self._pcm_cache: Dict[int, Tuple[bytes, float]] = {}
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
        if device_type == AudioStreamOrchestrator.DEVICE_PHYSICAL:
            raise ValueError(
                "physical 设备走 device_driver 物理混音路径，不经 RenderService")
        if device_type == 'websocket_api' or (device_type == 'http_api' and stream):
            return 'stream'
        if device_type == 'http_api':
            return 'file'
        raise ValueError(f"未知执行设备类型: {device_type}")

    # ── 配置化参数 ──

    @staticmethod
    def chunk_duration_ms() -> int:
        return max(1, int(render_cfg('chunk_duration_ms', 100)))

    @staticmethod
    def _pcm_cache_ttl_seconds() -> float:
        return max(0.0, float(render_cfg('pcm_cache_ttl_seconds', 300)))

    # ── 渲染入口 ──

    def render(self, render_config: dict, mode: str):
        """公共前置（Step 1-4）→ 路径分发（Step 5/6）

        mode='file'   → RenderAudioFile.render(context) -> dict（整文件产物）
        mode='stream' → RenderAudioStream.render(context) -> Iterator[dict]（逐 chunk）
        """
        context = self.prepare(render_config)
        if mode == 'file':
            from audio_service.application.services.render_audio_file import RenderAudioFile
            return RenderAudioFile.render(context)
        if mode == 'stream':
            from audio_service.application.services.render_audio_stream import RenderAudioStream
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

        # Step 0：噪声合并（复用 build_noise_info，两级配置透传）→ 并入混音源
        noise_cfg = self._resolve_noise(render_config)
        entries = [cfg for cfg in audios if isinstance(cfg, dict) and cfg.get('audio_id')]
        if noise_cfg and noise_cfg.get('audio_id'):
            entries.append({
                'audio_id': noise_cfg['audio_id'],
                'type': AudioKind.NOISE,
                'spl': noise_cfg.get('spl'),
                'loop': noise_cfg.get('loop', False),
                'delay': noise_cfg.get('delay', 0),
            })
        if not entries:
            raise ValueError("render_config 缺少 audios 与噪声配置，无可混音内容")

        sources: List[RenderSource] = []

        # Step 1 + 2 + 3：加载 PCM → 格式适配 → RMS 补偿 + SPL 增益
        for cfg in entries:
            kind = str(cfg.get('type') or AudioKind.SPEAKER)
            if kind not in (AudioKind.SPEAKER, AudioKind.INTERFERER, AudioKind.NOISE):
                raise ValueError(f"未知音频类型: {kind}（可选 speaker/interferer/noise）")
            pcm, meta = self._load_source_pcm(cfg['audio_id'])
            src_fmt = detect_source_format(pcm, meta)
            adapted = AudioFormatAdapter.adapt(pcm, src_fmt, target_format)
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

    # ── 噪声合并（复用 build_noise_info，两级配置透传） ──

    @staticmethod
    def _resolve_noise(render_config: dict) -> Optional[dict]:
        """合并噪声配置：复用 build_noise_info（case 级 > round 级，与 E2E 共用同一语义）。

        executor 侧仅透传两级配置（round_noise / case_noise），合并发生在 audio_service；
        API 混音路径噪声不经物理设备，require_devices=False 仅解析音频。
        """
        round_bg = render_config.get('round_noise')
        case_bg = render_config.get('case_noise')
        if not round_bg and not case_bg:
            return None
        round_cfg = {'background_noise': round_bg} if round_bg else {}
        case_cfg = {'background_noise': case_bg} if case_bg else {}
        noise_info, _devices = build_noise_info(round_cfg, case_cfg, require_devices=False)
        if not noise_info:
            return None
        n_config, _n_audio = noise_info
        src_block = AudioStreamOrchestrator._match_noise_block(
            n_config.get('audio_id'), round_bg, case_bg)
        return {
            'audio_id': n_config.get('audio_id'),
            'spl': n_config.get('spl'),
            'loop': bool(src_block.get('loop', False)) if src_block else False,
            'delay': float(src_block.get('delay', 0) or 0) if src_block else 0.0,
        }

    @staticmethod
    def _match_noise_block(resolved_audio_id, round_bg, case_bg):
        """定位解析命中的噪声配置块（回填 loop/delay 透传字段）"""
        for block in (case_bg, round_bg):
            if isinstance(block, dict) and block.get('audio_id') == resolved_audio_id:
                return block
        return None

    # ── Step 1：源加载（库内直连，含 TTL 缓存） ──

    def _load_source_pcm(self, audio_id) -> Tuple[bytes, dict]:
        """按 audio_id 加载音频字节 + 元数据（audios 表归 audio_service 所有，进程内直连）"""
        audio_id = int(audio_id)
        ttl = self._pcm_cache_ttl_seconds()
        now = time.monotonic()
        if ttl > 0:
            with self._cache_lock:
                cached = self._pcm_cache.get(audio_id)
                if cached and now - cached[2] < ttl:
                    return cached[0], cached[1]
        pcm, meta = self._load_from_storage(audio_id)
        if ttl > 0:
            with self._cache_lock:
                self._pcm_cache[audio_id] = (pcm, meta, now)
        return pcm, meta

    def _load_from_storage(self, audio_id: int) -> Tuple[bytes, dict]:
        from audio_service.infrastructure.persistence.audio_repository import AudioRepository
        from shared.infrastructure.storage import storage
        audio = AudioRepository().get_audio(audio_id)
        if audio is None or not getattr(audio, 'file_path', ''):
            raise FileNotFoundError(f"音频 {audio_id} 不存在或缺少 file_path")
        file_path = audio.file_path
        path = file_path if file_path.startswith(('oss://', 'local://')) \
            else storage.build_path('audios', file_path)
        pcm = storage.load_bytes(path)
        meta = {
            'sample_rate': getattr(audio, 'sample_rate', 0) or 0,
            'channels': getattr(audio, 'channels', 0) or 0,
            'duration': getattr(audio, 'duration', 0.0) or 0.0,
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
