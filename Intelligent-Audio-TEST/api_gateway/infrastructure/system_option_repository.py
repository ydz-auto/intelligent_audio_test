# -*- coding: utf-8 -*-
"""系统选项 KV 仓储实现（SQLAlchemy，INT-620）。

api_gateway 直管 system_options 表（无独立 config 微服务），表结构由
scripts/migrations/202610/add_system_options_table.py 落库、create_all_tables.py
登记建表。DB session 走 shared get_db_session()（HTTP 请求级 scope，INT-90）。
"""
from typing import Dict

from shared.models.database import get_db_session
from api_gateway.domain.entities.system_option import SystemOptionValue
from api_gateway.domain.repositories.system_option_repository import SystemOptionRepository
from api_gateway.infrastructure.models.system_option_model import SystemOption


class SystemOptionRepositoryImpl(SystemOptionRepository):
    """SQLAlchemy 实现（读侧只读、写侧显式 commit，CQRS 边界）。"""

    def get_all(self) -> Dict[str, SystemOptionValue]:
        session = get_db_session()
        rows = session.query(SystemOption).all()
        return {row.key: row.value for row in rows}

    def upsert(self, key: str, value: SystemOptionValue) -> None:
        session = get_db_session()
        row = session.query(SystemOption).filter_by(key=key).one_or_none()
        if row is None:
            session.add(SystemOption(key=key, value=value))
        else:
            row.value = value
        session.commit()
