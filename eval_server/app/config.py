import os

class Config:
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))

    # 文件存储路径（替代 SQLite）
    DATA_DIR = os.path.join(BASE_DIR, 'database')
    TASKS_DIR = os.path.join(DATA_DIR, 'tasks')          # 按日分文件夹
    ENDPOINTS_FILE = os.path.join(DATA_DIR, 'endpoints.json')

    # 上传文件临时目录
    UPLOAD_DIR = os.path.join(DATA_DIR, 'uploads')

    # 日志配置
    LOG_DIR = os.path.join(BASE_DIR, 'logs')
    LOG_FILE = os.path.join(LOG_DIR, 'eval_server.log')
    LOG_MAX_BYTES = 10 * 1024 * 1024   # 10MB
    LOG_BACKUP_COUNT = 30              # 保留 30 个历史文件

    # Flask settings
    DEBUG = False
    PORT = 5001
    HOST = '0.0.0.0'

    # Local concurrency control
    LOCAL_MAX_CONCURRENCY = 10

    # WSGI 服务器线程数（waitress 固定线程池）
    # None = 自动计算（LOCAL_MAX_CONCURRENCY * 2 + 4，上限 32）
    WSGI_THREADS = None

    # Task settings
    CONCURRENCY_LIMITS = {
        'wer': 2,
        'ser': 1,
        'der': 1,
        'cpwer': 2,
        'tcpwer': 2,
        'stm_wer': 2,
        'llm_judge': 2,
    }
    DEFAULT_MAX_CONCURRENCY = 2

    # LLM Judge configuration
    LLM_JUDGE = {
        'api_base_url': os.environ.get('LLM_JUDGE_API_BASE', ''),
        'api_key': os.environ.get('LLM_JUDGE_API_KEY', ''),
        'default_model': 'gpt-4',
        'timeout': 120,
    }

config = Config()
