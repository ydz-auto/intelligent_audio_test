"""
音频引擎模块 - AudioService 与模块级单例。

时间轴纯函数已拆分到 audio_timeline.py，
驱动层（AudioDriver / PyAudioDriver）已拆分到 audio_driver.py。
播放控制/设备通信/音频预准备/设备枚举已拆分到各 Engine*Mixin，
本文件仅保留 AudioService 组合类定义和模块级单例 audio_service。

职责拆分（Mixin 组合模式）：
- _engine_device_comm_mixin.EngineDeviceCommMixin：驱动初始化/设备缓存/多策略匹配/API 优先级选择
- _engine_playback_mixin.EnginePlaybackMixin：播放控制（play_audio/play_overlap/stop_*)
- _engine_audio_prepare_mixin.EngineAudioPrepareMixin：音频预下载与按设备采样率重采样
- _engine_device_enumeration_mixin.EngineDeviceEnumerationMixin：物理设备按声卡聚合去重枚举
"""

import threading
from audio_service.infrastructure.audio._engine_device_comm_mixin import EngineDeviceCommMixin
from audio_service.infrastructure.audio._engine_playback_mixin import EnginePlaybackMixin
from audio_service.infrastructure.audio._engine_audio_prepare_mixin import EngineAudioPrepareMixin
from audio_service.infrastructure.audio._engine_device_enumeration_mixin import EngineDeviceEnumerationMixin


class AudioService(EngineDeviceCommMixin,
                   EnginePlaybackMixin,
                   EngineAudioPrepareMixin,
                   EngineDeviceEnumerationMixin):
    """音频管理服务：支持多通道播放控制"""
    # 全局统一的播放 API，保证同一物理设备不会跨 API 打开流
    # DirectSound 优先：WASAPI 对设备独占/格式限制过多，DirectSound 更宽松
    _api_fallback_chain = ["Windows DirectSound", "Windows WDM-KS", "Windows WASAPI", "MME"]
    _resolved_api = None  # 运行时确定的可用品 API（首次成功打开后固定）

    def __init__(self):
        # 延迟初始化 PyAudio 驱动，避免模块导入时调用 pyaudio.PyAudio() 导致启动卡死
        # 注意：Pa_Initialize() 非线程安全，必须由 init_driver() 在主线程预初始化
        self.driver = None
        self.active_players = {} # taskId -> {player_type: thread}
        self._device_cache = None
        self._cache_time = 0
        self._cache_duration = 5.0 # 缓存5秒
        self._lock = threading.Lock()
        self._audio_pool = None

    def _get_audio_pool(self):
        """获取音频播放专用线程池（延迟初始化）

        微服务化后：音频播放完全由 audio_service 本地管理，
        不再通过 gRPC 向 task_service 请求线程池大小。
        扩容至 10 个线程：全局背景噪声（最多4设备）+ 轮次内 play_round
        （主讲人/干扰人/噪声，最多4-6设备）需要足够容量避免排队死锁。
        """
        if self._audio_pool is None:
            from concurrent.futures import ThreadPoolExecutor
            self._audio_pool = ThreadPoolExecutor(max_workers=10, thread_name_prefix='audio_play_')
        return self._audio_pool


audio_service = AudioService()
