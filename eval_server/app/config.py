import os

# 加载 .env 文件
from pathlib import Path
env_path = Path(__file__).resolve().parent.parent / '.env'
if env_path.exists():
    with open(env_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())


class Config:
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    # 项目根目录（与 Intelligent-Audio-TEST 保持一致）
    PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, '..', '..'))

    # 静态资源根目录（与主项目共享）
    STATIC_BASE_PATH = os.environ.get('STATIC_BASE_PATH', os.path.join(PROJECT_ROOT, 'static'))

    # 文件存储路径（替代 SQLite）
    DATA_DIR = os.path.join(BASE_DIR, 'database')
    TASKS_DIR = os.path.join(DATA_DIR, 'tasks')          # 按日分文件夹
    ENDPOINTS_FILE = os.path.join(DATA_DIR, 'endpoints.json')

    # 上传文件临时目录
    UPLOAD_DIR = os.path.join(DATA_DIR, 'uploads')

    # 日志配置（归档到 static 目录下）
    LOG_DIR = os.path.join(STATIC_BASE_PATH, 'logs', 'eval_server')
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
        'api_base_url': 'https://az.gptplus5.com/v1',
        'api_key': os.environ.get('LLM_JUDGE_API_KEY', ''),
        'default_model': 'deepseek-r1',
        'timeout': 120,
        'prompt_template': (
            '你是一个严格的语言逻辑专家，你需要结合上下文并逐字逐词分析【用户提问】、【助手回答】与【历史对话】三者之间的逻辑是否正确，你需要按照【评价规则】进行打分，并给出打分理由；\n\n'
            '【评价规则】\n'
            '<A>回答时有以下表现之一为1分\n'
            '逻辑混乱，表达没有条理\n\n'
            '【当前用户问题】：{query}\n\n'
            '【当前助手回答】：{hypothesis}\n\n'
            '输出结果严格按照如下json形式，包含两个参数（score、reason）：\n'
            '【自动评测开始】\n'
            '{{"score":"XXX","reason":"XXX"}}\n'
            '【自动评测结束】'
        ),
    }

config = Config()
