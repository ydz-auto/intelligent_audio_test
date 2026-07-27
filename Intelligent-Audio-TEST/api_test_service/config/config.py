"""API Test Service 配置"""
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class APITestServiceConfig:
    PORT = int(os.environ.get('PORT', 5003))
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')
    DATABASE_URL = os.environ.get('DATABASE_URL',
        'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test')

    # OSS
    OSS_ENDPOINT = os.environ.get('OSS_ENDPOINT', 'http://localhost:9000')
    OSS_ACCESS_KEY = os.environ.get('OSS_ACCESS_KEY', 'minio')
    OSS_SECRET_KEY = os.environ.get('OSS_SECRET_KEY', 'minio123')

    # 日志
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
    CONSOLE_LOG_ENABLED = os.environ.get('CONSOLE_LOG_ENABLED', 'true').lower() in ('true', '1', 'yes')
