"""
数据库初始化模块 - 共享层
"""
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def init_db(app, pool_size=10):
    """初始化数据库连接池"""
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config.get('SQLALCHEMY_DATABASE_URI') or \
        'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_size': pool_size,
        'pool_recycle': 3600,
        'pool_pre_ping': True,
        'max_overflow': 20,
    }
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    return db

def get_db_session():
    from shared.models.database import db
    return db.session
