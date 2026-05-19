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

class Config:
    SECRET_KEY = _get_secret_key()
    BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, '..','..','..'))
    SQLALCHEMY_DATABASE_URI = _get_database_uri()
    # 禁用 SQLAlchemy 的修改跟踪，以提高性能
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # 配置JSON编码器使用UTF-8，直接输出中文而不是Unicode转义序列
    JSON_AS_ASCII = False
    
    # 数据库引擎配置
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_size': 20,
        'max_overflow': 40,
        'pool_timeout': 60,
        'pool_recycle': 1800,
    }
    
    # FFmpeg/FFprobe 路径配置
    FFMPEG_PATH = os.environ.get('FFMPEG_PATH', '')
    if FFMPEG_PATH:
        # 如果设置了环境变量，优先使用环境变量中的路径
        if not os.path.isfile(FFMPEG_PATH):
            # 如果指定的路径不存在，回退到默认路径
            FFMPEG_PATH = r'E:\02_code_build_envirenment\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe'
            if not os.path.isfile(FFMPEG_PATH):
                # 如果硬编码路径也不存在，使用系统 PATH 中的 ffmpeg
                FFMPEG_PATH = 'ffmpeg'
    else:
        # 没有设置环境变量，先尝试硬编码路径，再回退到系统 PATH
        hardcoded_path = r'E:\02_code_build_envirenment\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe'
        if os.path.isfile(hardcoded_path):
            FFMPEG_PATH = hardcoded_path
        else:
            FFMPEG_PATH = 'ffmpeg'
    
    # FFprobe 路径配置（与 ffmpeg 同目录）
    FFPROBE_PATH = os.environ.get('FFPROBE_PATH', '')
    if FFPROBE_PATH:
        if not os.path.isfile(FFPROBE_PATH):
            # 回退到 ffmpeg 同目录下的 ffprobe.exe
            ffprobe_in_ffmpeg_dir = os.path.join(os.path.dirname(FFMPEG_PATH), 'ffprobe.exe')
            if os.path.isfile(ffprobe_in_ffmpeg_dir):
                FFPROBE_PATH = ffprobe_in_ffmpeg_dir
            else:
                FFPROBE_PATH = 'ffprobe'
    else:
        # 尝试 ffmpeg 同目录下的 ffprobe.exe
        ffprobe_in_ffmpeg_dir = os.path.join(os.path.dirname(FFMPEG_PATH), 'ffprobe.exe')
        if os.path.isfile(ffprobe_in_ffmpeg_dir):
            FFPROBE_PATH = ffprobe_in_ffmpeg_dir
        else:
            FFPROBE_PATH = 'ffprobe'
    
    # 静态资源路径配置
    # 静态资源基础路径
    STATIC_BASE_PATH = os.path.join(PROJECT_ROOT, 'static')
    # 音频文件存储路径
    AUDIO_STORAGE_PATH = os.path.join(STATIC_BASE_PATH, 'audios')
    # 上传文件临时路径
    UPLOAD_TEMP_PATH = os.path.join(PROJECT_ROOT, 'temp_uploads')
    # 预重采样临时文件路径
    RESAMPLE_TEMP_PATH = os.path.join(AUDIO_STORAGE_PATH, 'temp_resample')
    # 静态资源URL前缀
    STATIC_URL_PREFIX = '/static/'
    # 音频文件URL前缀
    AUDIO_URL_PREFIX = '/static/audios/'
    
    # API执行配置
    # 最大等待时间（秒）
    API_MAX_WAIT_TIME = 43200
    # 轮询间隔（秒）
    API_POLL_INTERVAL = 30
    # API路径映射
    API_PATHS = {
        'health': '/health',
        'create_task': '/api/create_task',
        'get_status': '/api/get_status/{task_id}',
        'get_frame_results': '/api/get_frame_results/{task_id}',
        'get_final_result': '/api/get_final_result/{task_id}',
        'delete_task': '/api/delete_task/{task_id}'
    }
    
    # WebSocket配置
    # WebSocket消息推送节流间隔（秒），0表示关闭节流
    WEBSOCKET_MIN_UPDATE_INTERVAL = 0

    # 执行引擎配置
    # 任务调度器检查间隔（秒）
    EXECUTION_ENGINE_SCHEDULER_INTERVAL = 3
    # 等待测试用例执行完成的超时时间（秒）
    EXECUTION_ENGINE_TEST_CASE_WAIT_TIME = 300
    # 任务队列最大长度
    EXECUTION_ENGINE_MAX_QUEUE_SIZE = 100
    
    # API执行器配置（默认值，可被 concurrency_config.json 覆盖）
    API_EXECUTOR_MAX_QUEUE_SIZE = 10
    API_EXECUTOR_MAX_WAIT_TIME = 3000
    
    # 评估服务配置（默认值，可被 concurrency_config.json 覆盖）
    EVALUATION_SERVICE_MAX_QUEUE_SIZE = 10
    EVALUATION_SERVICE_MAX_WAIT_TIME = 300
     
    # 环境模式配置
    # 日志级别：DEBUG, INFO, WARNING, ERROR, CRITICAL
    LOG_LEVEL = 'INFO'
    # 是否启用控制台日志输出
    CONSOLE_LOG_ENABLED = True
    # SocketIO 调试模式
    SOCKETIO_DEBUG = False
    
# 开发环境配置
class DevelopmentConfig(Config):
    DEBUG = True
    LOG_LEVEL = 'DEBUG'
    CONSOLE_LOG_ENABLED = True
    SOCKETIO_DEBUG = False

# 生产环境配置
class ProductionConfig(Config):
    DEBUG = False
    LOG_LEVEL = 'INFO'
    CONSOLE_LOG_ENABLED = False
    SOCKETIO_DEBUG = False

# 测试环境配置
class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'  # 使用内存数据库进行测试
    DEBUG = True
    LOG_LEVEL = 'DEBUG'
    CONSOLE_LOG_ENABLED = True
    SOCKETIO_DEBUG = True
    SQLALCHEMY_ENGINE_OPTIONS = {
        "poolclass": StaticPool,
        "connect_args": {
            "check_same_thread": False
        }
    }

# 配置映射
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
