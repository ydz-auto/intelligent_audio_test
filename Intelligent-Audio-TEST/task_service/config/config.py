"""Task Service 配置"""
import os

class TaskServiceConfig:
    PORT = int(os.environ.get('PORT', 5001))
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')
    DATABASE_URL = os.environ.get('DATABASE_URL',
        'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test')
    E2E_TEST_SERVICE_HOST = os.environ.get('E2E_TEST_SERVICE_HOST', 'localhost')
    E2E_TEST_SERVICE_PORT = int(os.environ.get('E2E_TEST_SERVICE_PORT', 5002))
    API_TEST_SERVICE_HOST = os.environ.get('API_TEST_SERVICE_HOST', 'localhost')
    API_TEST_SERVICE_PORT = int(os.environ.get('API_TEST_SERVICE_PORT', 5003))
    EVALUATION_SERVICE_HOST = os.environ.get('EVALUATION_SERVICE_HOST', 'localhost')
    EVALUATION_SERVICE_PORT = int(os.environ.get('EVALUATION_SERVICE_PORT', 5004))
