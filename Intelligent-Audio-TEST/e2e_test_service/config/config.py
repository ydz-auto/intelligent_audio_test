"""E2E Test Service 配置"""
import os

class E2ETestServiceConfig:
    PORT = int(os.environ.get('PORT', 5002))
    GRPC_PORT = int(os.environ.get('GRPC_PORT', 50051))
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')
    DATABASE_URL = os.environ.get('DATABASE_URL',
        'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test')
    LAB_NAME = os.environ.get('LAB_NAME', 'lab-a')
