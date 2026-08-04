"""
数据模型基础模块 (Models Base)

提供所有模型子模块共享的基础导入：db 命名空间、SQLAlchemy 列类型、
relationship 工具以及东八区时间辅助函数 utc8now。

仅用于被 models 包内子模块导入，不应被业务代码直接使用。
"""
from datetime import datetime, timezone, timedelta

from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, DateTime, ForeignKey,
    Boolean, Float, JSON, Index, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from ..database import db


# 东八区时间辅助函数
def utc8now():
    return datetime.now(timezone(timedelta(hours=8)))
