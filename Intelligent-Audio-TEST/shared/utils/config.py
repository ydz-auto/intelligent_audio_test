"""共享配置"""
import os

class SharedConfig:
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')
    DATABASE_URL = os.environ.get('DATABASE_URL', 
        'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test')
    SERVICE_NAME = os.environ.get('SERVICE_NAME', 'unknown')
    SERVICE_HOST = os.environ.get('SERVICE_HOST', '0.0.0.0')
