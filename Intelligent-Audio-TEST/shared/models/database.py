"""
数据库初始化模块 - 共享层
"""
from flask_sqlalchemy import SQLAlchemy

from shared.infrastructure.config import BaseConfig

db = SQLAlchemy()

def init_db(app, pool_size=10):
    """初始化数据库连接池"""
    uri = app.config.get('SQLALCHEMY_DATABASE_URI') or BaseConfig.DATABASE_URL
    if not uri:
        raise RuntimeError('未配置 DATABASE_URL 或 SQLALCHEMY_DATABASE_URI 环境变量')
    app.config['SQLALCHEMY_DATABASE_URI'] = uri
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
