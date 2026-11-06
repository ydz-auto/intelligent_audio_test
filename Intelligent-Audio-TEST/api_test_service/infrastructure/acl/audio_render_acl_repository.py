# -*- coding: utf-8 -*-
"""audio_service.RenderService ACL 仓储 — gRPC 实现（INT-67 混音下沉消费端）。

执行器不得直调 stub：混音请求经本实现出站（get_render_service_stub），
产物以 DTO 返回（整文件 bytes / 逐 chunk 迭代器）。
"""
from __future__ import annotations

import base64
import logging
from typing import Iterator, Optional

from api_test_service.domain.repositories.acl.audio_render_acl_repository import (
    AudioRenderAclRepository,
    RenderChunkDTO,
    RenderedAudioDTO,
    route_render_mode,
)

logger = logging.getLogger(__name__)


class AudioRenderACLRepositoryImpl(AudioRenderAclRepository):
    """audio_service.RenderService 跨域混音 gRPC 实现。"""

    @staticmethod
    def build_render_config(round_config: dict, case_config: dict,
                            target_format: Optional[dict] = None,
                            api_id=None, spl_mapping: Optional[dict] = None,
                            speakers_map: Optional[dict] = None,
                            overlap_rate: float = 0.0,
                            overlap_time: float = 0.0) -> dict:
        """组装渲染配置：audios + 两级噪声透传 + 目标格式 + SPL 映射数据。

        - 两级噪声仅透传（round_noise / case_noise），合并在 audio_service 侧复用
          build_noise_info 裁决；
        - target_format 缺省时不传（audio_service 回退默认 24kHz/s16/mono）；
        - spl_mapping 为被测 API 的 ApiRmsSplMapping 数据 dict（消费端预载），
          audio_service 不反向查库。
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
        """整段混音（非实时）：unary 返回完整 wav/pcm。

        显式放宽 deadline（INT-54 模式）：整段混音耗时随时长增长，
        默认 60s 会误杀合法慢调用，超时上限进 audio_render 配置。
        """
        import json

        from shared.clients.grpc_clients import get_render_service_stub
        from shared.proto import audio_service_pb2 as e2e_pb
        from shared.utils.config_manager import config_manager
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_render_service_stub()
            timeout = float(config_manager.get_value(
                'audio_render', 'render_file_timeout_seconds', 600))
            resp = stub.RenderAudioFile(e2e_pb.RenderAudioFileRequest(
                task_id=str(task_id),
                render_config=json.dumps(render_config or {}, ensure_ascii=False, default=str),
            ), timeout=timeout)
            if not resp.success:
                logger.warning("render_audio_file failed: %s", resp.message)
                return None
            data = _loads(resp.data, {}) or {}
            return RenderedAudioDTO(
                audio_bytes=base64.b64decode(data.get('audio_base64', '')),
                container=data.get('container', 'pcm'),
                sample_rate=int(data.get('sample_rate', 24000)),
                bit_depth=data.get('bit_depth', 's16'),
                channels=int(data.get('channels', 1)),
                duration_ms=int(data.get('duration_ms', 0)),
            )
        except Exception as e:
            logger.warning("render_audio_file gRPC failed: %s", e)
            return None

    def render_audio_stream(self, render_config: dict, task_id: str = '') -> Iterator[RenderChunkDTO]:
        """流式混音（流式/Realtime）：逐 chunk 迭代（失败以 message+is_last 终止帧收口）。"""
        import json

        from shared.clients.grpc_clients import get_render_service_stub
        from shared.proto import audio_service_pb2 as e2e_pb
        try:
            stub = get_render_service_stub()
            chunks = stub.RenderAudioStream(e2e_pb.RenderAudioStreamRequest(
                task_id=str(task_id),
                render_config=json.dumps(render_config or {}, ensure_ascii=False, default=str),
            ))
            for chunk in chunks:
                yield RenderChunkDTO(
                    sequence=int(chunk.sequence),
                    data_b64=chunk.data,
                    is_last=bool(chunk.is_last),
                    message=chunk.message,
                )
        except Exception as e:
            logger.warning("render_audio_stream gRPC failed: %s", e)
            yield RenderChunkDTO(sequence=-1, data_b64='', is_last=True, message=str(e))


__all__ = [
    'AudioRenderACLRepositoryImpl',
    'route_render_mode',
]
