"""Task Service 配置"""
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class TaskServiceConfig:
    PORT = int(os.environ.get('PORT', 5001))
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')
    DATABASE_URL = os.environ.get('DATABASE_URL')
    if not DATABASE_URL:
        raise RuntimeError('未配置 DATABASE_URL 环境变量')

    # OSS
    OSS_ENDPOINT = os.environ.get('OSS_ENDPOINT', 'http://localhost:9000')
    OSS_ACCESS_KEY = os.environ.get('OSS_ACCESS_KEY')
    OSS_SECRET_KEY = os.environ.get('OSS_SECRET_KEY')

    # 执行服务地址
    E2E_TEST_SERVICE_HOST = os.environ.get('E2E_TEST_SERVICE_HOST', 'localhost')
    E2E_TEST_SERVICE_PORT = int(os.environ.get('E2E_TEST_SERVICE_PORT', 5002))
    API_TEST_SERVICE_HOST = os.environ.get('API_TEST_SERVICE_HOST', 'localhost')
    API_TEST_SERVICE_PORT = int(os.environ.get('API_TEST_SERVICE_PORT', 5003))

    # FFmpeg
    FFMPEG_PATH = os.environ.get('FFMPEG_PATH', 'ffmpeg')
    FFPROBE_PATH = os.environ.get('FFPROBE_PATH', 'ffprobe')

    # 日志
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
    CONSOLE_LOG_ENABLED = os.environ.get('CONSOLE_LOG_ENABLED', 'true').lower() in ('true', '1', 'yes')
