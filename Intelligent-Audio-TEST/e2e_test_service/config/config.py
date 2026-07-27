"""E2E Test Service 配置"""
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class E2ETestServiceConfig:
    PORT = int(os.environ.get('PORT', 5002))
    GRPC_PORT = int(os.environ.get('GRPC_PORT', 50051))
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')
    DATABASE_URL = os.environ.get('DATABASE_URL',
        'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test')

    # OSS
    OSS_ENDPOINT = os.environ.get('OSS_ENDPOINT', 'http://localhost:9000')
    OSS_ACCESS_KEY = os.environ.get('OSS_ACCESS_KEY', 'minio')
    OSS_SECRET_KEY = os.environ.get('OSS_SECRET_KEY', 'minio123')

    LAB_NAME = os.environ.get('LAB_NAME', 'lab-a')

    # FFmpeg
    FFMPEG_PATH = os.environ.get('FFMPEG_PATH', 'ffmpeg')
    FFPROBE_PATH = os.environ.get('FFPROBE_PATH', 'ffprobe')

    # 日志
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
    CONSOLE_LOG_ENABLED = os.environ.get('CONSOLE_LOG_ENABLED', 'true').lower() in ('true', '1', 'yes')

# 别名，兼容旧代码中的 `from config.config import Config`
Config = E2ETestServiceConfig
