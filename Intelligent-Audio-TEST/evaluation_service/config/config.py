"""Evaluation Service 配置"""
import os

class EvaluationServiceConfig:
    PORT = int(os.environ.get('PORT', 5004))
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')
    DATABASE_URL = os.environ.get('DATABASE_URL',
        'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test')
