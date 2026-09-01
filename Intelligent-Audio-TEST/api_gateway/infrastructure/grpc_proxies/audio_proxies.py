"""音频服务代理门面：统一 re-export 全部音频相关代理类与模块级单例。

原 1117 行大文件已按域拆分至以下子模块，本文件作为门面保持历史 import 路径不变：
- audio_service_proxy.py       — audio_service（播放/停止/设备/播放器快照）及别名 AudioService
- spl_service_proxy.py         — spl_service（SPL 测量/启停/转增益）
- playback_orchestrator_proxy.py — playback_orchestrator（预览/轮次/声纹播放/停止）
- playback_config_proxy.py     — playback_config_service（播放设备 CRUD/扫描/状态/测试）
- spl_config_proxy.py          — spl_config_service（SPL 映射 CRUD/校准/历史/统计/测试音）
- audio_config_proxy.py        — audio_config_service（音频元数据/标注/上传/转换/预览，组合 mixin）

外部调用方无需改动，仍可使用：
    from api_gateway.infrastructure.grpc_proxies import audio_service, ...
    from .audio_proxies import AudioService, audio_service, ...
"""
from .audio_service_proxy import (
    _AudioServiceProxy,
    AudioService,
    audio_service,
)
from .spl_service_proxy import (
    _SplServiceProxy,
    spl_service,
)
from .playback_orchestrator_proxy import (
    _PlaybackOrchestratorProxy,
    playback_orchestrator,
)
from .playback_config_proxy import (
    _PlaybackConfigProxy,
    playback_config_service,
)
from .spl_config_proxy import (
    _SPLConfigProxy,
    spl_config_service,
)
from .audio_config_proxy import (
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
