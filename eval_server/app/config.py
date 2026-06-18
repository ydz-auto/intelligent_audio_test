import os

class Config:
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    DATABASE_PATH = os.path.join(BASE_DIR, 'database', 'wer_tasks.db')
    SCHEMA_PATH = os.path.join(BASE_DIR, 'database', 'schema.sql')
    
    # Flask settings
    DEBUG = True
    PORT = 5001
    HOST = '0.0.0.0'
    
    # Local concurrency control
    LOCAL_MAX_CONCURRENCY = 10
    
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
