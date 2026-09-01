# -*- coding: utf-8 -*-
"""兼容层：音频代理已整合至 audio/ 子包（P7-4）。

历史 import 路径 `api_gateway.infrastructure.grpc_proxies.audio_proxies` 仍可使用，
新代码请直接使用：
    from api_gateway.infrastructure.grpc_proxies.audio import AudioService, audio_service, ...
"""
from api_gateway.infrastructure.grpc_proxies.audio import (
    _AudioServiceProxy,
    AudioService,
    audio_service,
    _SplServiceProxy,
    spl_service,
    _PlaybackOrchestratorProxy,
    playback_orchestrator,
    _PlaybackConfigProxy,
    playback_config_service,
    _SPLConfigProxy,
    spl_config_service,
    _AudioConfigProxy,
    audio_config_service,
)

__all__ = [
    'AudioService',
    'audio_service',
    'spl_service',
    'playback_orchestrator',
    'playback_config_service',
    'spl_config_service',
    'audio_config_service',
]
