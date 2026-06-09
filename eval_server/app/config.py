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
        'ser': 1
    }
    DEFAULT_MAX_CONCURRENCY = 2

config = Config()
