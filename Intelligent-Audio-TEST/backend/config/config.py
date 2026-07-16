import os
import secrets
from pathlib import Path
from dotenv import load_dotenv

_config_dir = Path(__file__).parent
_env_file = _config_dir / '.env'
if _env_file.exists():
    load_dotenv(_env_file)
else:
    _root_env_file = _config_dir.parent / '.env'
    if _root_env_file.exists():
        load_dotenv(_root_env_file)

from sqlalchemy.pool import StaticPool

def _get_secret_key():
    key = os.environ.get('SECRET_KEY')
    if key:
        return key
    if os.environ.get('FLASK_ENV') == 'production':
        raise RuntimeError('SECRET_KEY environment variable must be set in production')
    return secrets.token_hex(32)

def _get_database_uri():
    uri = os.environ.get('DATABASE_URI')
    if uri:
        return uri
    db_user = os.environ.get('DB_USER', 'intelligent_audio_test')
    db_password = os.environ.get('DB_PASSWORD', '')
    db_host = os.environ.get('DB_HOST', 'localhost')
    db_port = os.environ.get('DB_PORT', '5432')
    db_name = os.environ.get('DB_NAME', 'intelligent_audio_test')
    if not db_password:
        if os.environ.get('FLASK_ENV') == 'production':
            raise RuntimeError('DB_PASSWORD environment variable must be set in production')
        db_password = 'intelligent_audio_test666'
    return f'postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}'

def _get_ffmpeg_path():
    ffmpeg_path = os.environ.get('FFMPEG_PATH', '').strip()
    if ffmpeg_path and os.path.isfile(ffmpeg_path):
        return ffmpeg_path
    elif ffmpeg_path:
        pass
    hardcoded_path = r'E:\02_code_build_envirenment\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe'
    if os.path.isfile(hardcoded_path):
        return hardcoded_path
    return 'ffmpeg'

def _get_ffprobe_path(ffmpeg_path):
    ffprobe_path = os.environ.get('FFPROBE_PATH', '').strip()
    if ffprobe_path and os.path.isfile(ffprobe_path):
        return ffprobe_path
    if ffmpeg_path and ffmpeg_path != 'ffmpeg':
        ffprobe_in_ffmpeg_dir = os.path.join(os.path.dirname(ffmpeg_path), 'ffprobe.exe')
        if os.path.isfile(ffprobe_in_ffmpeg_dir):
            return ffprobe_in_ffmpeg_dir
    hardcoded_ffprobe = r'E:\02_code_build_envirenment\ffmpeg-master-latest-win64-gpl\bin\ffprobe.exe'
    if os.path.isfile(hardcoded_ffprobe):
        return hardcoded_ffprobe
    return 'ffprobe'

def _get_log_level():
    return os.environ.get('LOG_LEVEL', 'INFO').upper()

def _get_console_log_enabled():
    val = os.environ.get('CONSOLE_LOG_ENABLED', 'true').lower()
    return val in ('true', '1', 'yes', 'on')

def _get_path_env(key, default_path):
    path = os.environ.get(key, '').strip()
    return path if path else default_path

def _get_int_env(key, default):
    val = os.environ.get(key)
    if val:
        try:
            return int(val)
        except ValueError:
            pass
    return default

class Config:
    SECRET_KEY = _get_secret_key()
    BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    PROJECT_ROOT = r'C:\S2TT\auto_test\ver8\202604231600\Intelligent-Audio-TEST'
    SQLALCHEMY_DATABASE_URI = _get_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_COMMIT_ON_TEARDOWN = False
    SQLALCHEMY_ECHO = os.environ.get('SQLALCHEMY_ECHO', 'false').lower() in ('true', '1', 'yes')
    JSON_AS_ASCII = False
    
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_size': 20,
        'max_overflow': 40,
        'pool_timeout': 60,
        'pool_recycle': 1800,
    }
    
    FFMPEG_PATH = _get_ffmpeg_path()
    FFPROBE_PATH = _get_ffprobe_path(FFMPEG_PATH)
    
    STATIC_BASE_PATH = _get_path_env('STATIC_BASE_PATH', os.path.join(PROJECT_ROOT, 'static'))
    ARCHIVE_PATH = _get_path_env('ARCHIVE_PATH', os.path.join(STATIC_BASE_PATH, 'archives'))
    AUDIO_STORAGE_PATH = _get_path_env('AUDIO_STORAGE_PATH', os.path.join(STATIC_BASE_PATH, 'audios'))
    REF_PARAMS_STORAGE_PATH = _get_path_env('REF_PARAMS_STORAGE_PATH', os.path.join(STATIC_BASE_PATH, 'ref_params'))
    UPLOAD_TEMP_PATH = _get_path_env('UPLOAD_TEMP_PATH', os.path.join(PROJECT_ROOT, 'temp_uploads'))
    RESAMPLE_TEMP_PATH = _get_path_env('RESAMPLE_TEMP_PATH', os.path.join(AUDIO_STORAGE_PATH, 'temp_resample'))
    STATIC_URL_PREFIX = '/static/'
    AUDIO_URL_PREFIX = '/static/audios/'
    
    API_MAX_WAIT_TIME = _get_int_env('API_MAX_WAIT_TIME', 43200)
    API_POLL_INTERVAL = _get_int_env('API_POLL_INTERVAL', 30)
    API_PATHS = {
        'health': '/health',
        'create_task': '/api/create_task',
        'get_status': '/api/get_status/{task_id}',
        'get_frame_results': '/api/get_frame_results/{task_id}',
        'get_final_result': '/api/get_final_result/{task_id}',
        'delete_task': '/api/delete_task/{task_id}'
    }
    
    WEBSOCKET_MIN_UPDATE_INTERVAL = 0

    EXECUTION_ENGINE_SCHEDULER_INTERVAL = _get_int_env('EXECUTION_ENGINE_SCHEDULER_INTERVAL', 3)
    EXECUTION_ENGINE_TEST_CASE_WAIT_TIME = _get_int_env('EXECUTION_ENGINE_TEST_CASE_WAIT_TIME', 300)
    EXECUTION_ENGINE_MAX_QUEUE_SIZE = _get_int_env('EXECUTION_ENGINE_MAX_QUEUE_SIZE', 100)
    
    API_EXECUTOR_MAX_QUEUE_SIZE = _get_int_env('API_EXECUTOR_MAX_QUEUE_SIZE', 10)
    API_EXECUTOR_MAX_WAIT_TIME = _get_int_env('API_EXECUTOR_MAX_WAIT_TIME', 3000)
    
    EVALUATION_SERVICE_MAX_QUEUE_SIZE = _get_int_env('EVALUATION_SERVICE_MAX_QUEUE_SIZE', 10)
    EVALUATION_SERVICE_MAX_WAIT_TIME = _get_int_env('EVALUATION_SERVICE_MAX_WAIT_TIME', 300)
     
    LOG_LEVEL = _get_log_level()
    CONSOLE_LOG_ENABLED = _get_console_log_enabled()
    SOCKETIO_DEBUG = False
    
class DevelopmentConfig(Config):
    DEBUG = True
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'DEBUG').upper()
    CONSOLE_LOG_ENABLED = _get_console_log_enabled()
    SOCKETIO_DEBUG = False

class ProductionConfig(Config):
    DEBUG = False
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
    CONSOLE_LOG_ENABLED = _get_console_log_enabled()
    SOCKETIO_DEBUG = False

class TestingConfig(Config):
    TESTING = True
    DEBUG = True
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'DEBUG').upper()
    CONSOLE_LOG_ENABLED = _get_console_log_enabled()
    SOCKETIO_DEBUG = True
    SQLALCHEMY_ENGINE_OPTIONS = {
        "poolclass": StaticPool,
    }

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}