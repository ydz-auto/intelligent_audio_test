"""API Gateway 领域配置"""
import os
from shared.infrastructure.config import BaseConfig


class Config(BaseConfig):
    PORT = int(os.environ.get('PORT', 5000))
    # 本地音频上传临时存储路径（分片上传、合并、转码中间文件）
    AUDIO_STORAGE_PATH = os.environ.get(
        'AUDIO_STORAGE_PATH',
        os.path.join(os.environ.get('LOCAL_STORAGE_ROOT', './storage'), 'audios')
    )

    # WSGI 线程池上限（Werkzeug ThreadedWSGIServer monkey-patch）
    # 100 并发用户场景下，并发 HTTP 请求约 30-40，其余为 WebSocket 长连接
    # None = 使用默认值 40；可通过环境变量 WSGI_MAX_THREADS 覆盖
    WSGI_MAX_THREADS = int(os.environ.get('WSGI_MAX_THREADS', 40))


# 兼容旧代码中的 GatewayConfig 引用
GatewayConfig = Config
