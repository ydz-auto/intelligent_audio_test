# -*- coding: utf-8 -*-
"""audio_service.RenderService 跨域 ACL 仓储接口（INT-67 混音下沉消费端）。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional

from shared.models.common_enums import DeviceType


@dataclass
class RenderedAudioDTO:
    """RenderAudioFile 整段混音产物 DTO

    audio_bytes 为解码后的完整音频（wav/pcm 按 target_format.container 包装），
    消费端直接作为被测 API 输入载荷一次性 POST。
    """

    audio_bytes: bytes = b''
    container: str = 'pcm'
    sample_rate: int = 24000
    bit_depth: str = 's16'
    channels: int = 1
    duration_ms: int = 0


@dataclass
class RenderChunkDTO:
    """RenderAudioStream 流式混音 chunk DTO（base64 PCM，消费端逐 chunk 推送）"""

    sequence: int = 0
    data_b64: str = ''
    is_last: bool = False
    message: str = ''


class AudioRenderAclRepository(ABC):
    """audio_service.RenderService 跨域调用接口。

    混音 6 步发生在 audio_service 进程内；执行器只经本端口
    「组装请求 + 消费产物」，不得直调 gRPC stub。
    """

    @staticmethod
    @abstractmethod
    def build_render_config(round_config: dict, case_config: dict,
                            target_format: Optional[dict] = None,
                            api_id=None, spl_mapping: Optional[dict] = None,
                            speakers_map: Optional[dict] = None,
                            overlap_rate: float = 0.0,
                            overlap_time: float = 0.0) -> dict:
        """组装混音渲染配置：audios 透传 + 两级噪声透传（合并归 audio_service）+ 目标格式。

        两级噪声仅透传（round_noise / case_noise），噪声合并优先级由
        audio_service 复用 build_noise_info 统一裁决，执行器不实现合并逻辑。
        """
        ...

    @abstractmethod
    def render_audio_file(self, render_config: dict, task_id: str = '') -> Optional[RenderedAudioDTO]:
        """整段混音（非实时）：RenderAudioFile unary，服务端聚合整文件返回。"""
        ...

    @abstractmethod
    def render_audio_stream(self, render_config: dict, task_id: str = '') -> Iterator[RenderChunkDTO]:
        """流式混音（流式/Realtime）：RenderAudioStream 逐 chunk 迭代。"""
        ...


def route_render_mode(streaming: bool) -> str:
    """按流式性路由混音出口（08 设计文档 §3.1 路由表的消费端镜像，INT-1799）：

    - streaming=False → 'file'（整段混音，RenderAudioFile）
    - streaming=True  → 'stream'（逐 chunk，RenderAudioStream）

    旧签名 `route_render_mode(device_type, stream)` 已废弃：混音出口只由被测
    API 的 `streaming` 决定（协议不参与）；physical 设备不经 RenderService，
    物理路径由 device_driver 承载，不在此表内。
    """
    if isinstance(streaming, bool):
        return 'stream' if streaming else 'file'
    # 兜底：仍按历史 device_type 值调用的调用方按亲和域令牌判定（确定性映射）
    legacy = str(streaming or '').strip().lower()
    if legacy == DeviceType.PHYSICAL.value:
        raise ValueError("physical 设备走 device_driver 物理混音路径，不经 RenderService")
    if legacy == DeviceType.WEBSOCKET_API.value:
        return 'stream'
    if legacy == DeviceType.HTTP_API.value:
        return 'file'
    raise ValueError(f"未知执行道/流式性: {streaming!r}")
