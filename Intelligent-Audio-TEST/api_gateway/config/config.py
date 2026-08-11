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

    # ===== 认证配置 =====
    # 认证模式: dev(本地OAuth) / prod(华为云OAuth) / off(无认证)
    AUTH_MODE = os.environ.get('AUTH_MODE', 'off')

    # JWT 配置
    JWT_SECRET = os.environ.get('JWT_SECRET', 'dev-secret-change-in-production')
    JWT_EXPIRE_HOURS = int(os.environ.get('JWT_EXPIRE_HOURS', '24'))
    JWT_ALGORITHM = os.environ.get('JWT_ALGORITHM', 'HS256')

    # 开发模式 - 本地 OAuth
    DEV_OAUTH_CLIENT_ID = os.environ.get('DEV_OAUTH_CLIENT_ID', 'local_dev_client')
    DEV_OAUTH_CLIENT_SECRET = os.environ.get('DEV_OAUTH_CLIENT_SECRET', 'local_dev_secret')
    DEV_OAUTH_REDIRECT_URI = os.environ.get(
        'DEV_OAUTH_REDIRECT_URI', 'http://localhost:8000/api/v1/auth/callback'
    )
    DEV_DEFAULT_USERNAME = os.environ.get('DEV_DEFAULT_USERNAME', 'dev_user')
    DEV_DEFAULT_PASSWORD = os.environ.get('DEV_DEFAULT_PASSWORD', 'dev_password')
    DEV_DEFAULT_ROLE = os.environ.get('DEV_DEFAULT_ROLE', 'admin')

    # 生产模式 - 华为云 OAuth
    HW_OAUTH_CLIENT_ID = os.environ.get('HW_OAUTH_CLIENT_ID', '')
    HW_OAUTH_CLIENT_SECRET = os.environ.get('HW_OAUTH_CLIENT_SECRET', '')
    HW_OAUTH_REDIRECT_URI = os.environ.get(
        'HW_OAUTH_REDIRECT_URI', 'http://localhost:8000/api/v1/auth/callback'
    )
    HW_OAUTH_AUTHORIZE_URL = os.environ.get(
        'HW_OAUTH_AUTHORIZE_URL', 'https://oauth.huaweicloud.com/oauth2/authorize'
    )
    HW_OAUTH_TOKEN_URL = os.environ.get(
        'HW_OAUTH_TOKEN_URL', 'https://oauth.huaweicloud.com/oauth2/token'
    )
    HW_OAUTH_USERINFO_URL = os.environ.get(
        'HW_OAUTH_USERINFO_URL', 'https://oauth.huaweicloud.com/oauth2/userinfo'
    )


# 兼容旧代码中的 GatewayConfig 引用
GatewayConfig = Config
