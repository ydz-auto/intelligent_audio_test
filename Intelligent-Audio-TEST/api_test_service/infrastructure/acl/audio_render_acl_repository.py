# -*- coding: utf-8 -*-
"""混音渲染 ACL 仓储 — 进程内实现（原 audio_service.RenderService 已合入 api_test_service）。

混音 6 步在 `api_test_service` 进程内完成（本模块直接调用 shared.audio_mix），
不再经 gRPC 出站；并发由 AUDIO_MIX_MAX_CONCURRENCY 信号量限制，避免多轮
混音同时占满 CPU / 内存。
"""
from __future__ import annotations

import base64
import logging
import os
import threading
from typing import Iterator, Optional

from api_test_service.domain.repositories.acl.audio_render_acl_repository import (
    AudioRenderAclRepository,
    RenderChunkDTO,
    RenderedAudioDTO,
    route_render_mode,
)
from shared.audio_mix.orchestrator import audio_stream_orchestrator

logger = logging.getLogger(__name__)

# 进程内混音并发上限（PCM 缓存 + 混音线程都在本进程，必须设限）
_MIX_MAX_CONCURRENCY = max(1, int(os.environ.get('AUDIO_MIX_MAX_CONCURRENCY', '2')))
_MIX_SLOTS = threading.BoundedSemaphore(_MIX_MAX_CONCURRENCY)

_orchestrator = audio_stream_orchestrator


class AudioRenderACLRepositoryImpl(AudioRenderAclRepository):
    """进程内混音实现（替代原 RenderService gRPC 客户端）。"""

    @staticmethod
    def build_render_config(round_config: dict, case_config: dict,
                            target_format: Optional[dict] = None,
                            api_id=None, spl_mapping: Optional[dict] = None,
                            speakers_map: Optional[dict] = None,
                            overlap_rate: float = 0.0,
                            overlap_time: float = 0.0) -> dict:
        """组装渲染配置：audios + 两级噪声透传 + 目标格式 + SPL 映射数据。

        - 两级噪声仅透传（round_noise / case_noise），case 级优先于 round 级；
        - target_format 缺省时由混音模块回退默认 24kHz/s16/mono；
        - spl_mapping 为被测 API 的 ApiRmsSplMapping 数据 dict（消费端预载），
          混音模块不反向查库。
        """
        if not isinstance(round_config, dict):
            round_config = {}
        if not isinstance(case_config, dict):
            case_config = {}
        config = {
            'audios': round_config.get('audios') or [],
            'round_noise': round_config.get('background_noise') or None,
            'case_noise': case_config.get('background_noise') or None,
            'overlap_rate': overlap_rate,
            'overlap_time': overlap_time,
        }
        if target_format:
            config['target_format'] = target_format
        if api_id is not None:
            config['api_id'] = api_id
        if spl_mapping:
            config['spl_mapping'] = spl_mapping
        if speakers_map:
            config['speakers_map'] = speakers_map
        return config

    def render_audio_file(self, render_config: dict, task_id: str = '') -> Optional[RenderedAudioDTO]:
        """整段混音（非实时）：进程内一次渲染出完整 wav/pcm。"""
        try:
            with _MIX_SLOTS:
                data = _orchestrator.render(render_config or {}, mode='file') or {}
            audio_bytes = base64.b64decode(data.get('audio_base64', ''))
            if not audio_bytes:
                logger.warning("render_audio_file 产物为空: task=%s", task_id)
                return None
            return RenderedAudioDTO(
                audio_bytes=audio_bytes,
                container=data.get('container', 'pcm'),
                sample_rate=int(data.get('sample_rate', 24000)),
                bit_depth=data.get('bit_depth', 's16'),
                channels=int(data.get('channels', 1)),
                duration_ms=int(data.get('duration_ms', 0)),
            )
        except Exception as e:
            logger.warning("render_audio_file 进程内混音失败: %s", e)
            return None

    def render_audio_stream(self, render_config: dict, task_id: str = '') -> Iterator[RenderChunkDTO]:
        """流式混音（流式/Realtime）：进程内逐 chunk 迭代（失败以终止帧收口）。"""
        try:
            with _MIX_SLOTS:
                for chunk in _orchestrator.render(render_config or {}, mode='stream'):
                    yield RenderChunkDTO(
                        sequence=int(chunk.get('sequence', 0)),
                        data_b64=chunk.get('data', ''),
                        is_last=bool(chunk.get('is_last', False)),
                        message=chunk.get('message', ''),
                    )
        except Exception as e:
            logger.warning("render_audio_stream 进程内混音失败: %s", e)
            yield RenderChunkDTO(sequence=-1, data_b64='', is_last=True, message=str(e))


__all__ = [
    'AudioRenderACLRepositoryImpl',
    'route_render_mode',
]
