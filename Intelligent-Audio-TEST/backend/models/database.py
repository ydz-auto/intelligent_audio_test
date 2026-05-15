"""
数据库初始化模块 (Database Initialization Module)

该模块负责初始化 SQLAlchemy 实例，配置 PostgreSQL 数据库连接池参数。

架构层次: Flask Model Layer (MVC - Model)
"""
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
