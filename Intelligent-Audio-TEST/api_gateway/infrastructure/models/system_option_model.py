# -*- coding: utf-8 -*-
"""api_gateway 系统选项 KV PO 定义（INT-620）

归属：api_gateway（站点/系统选项上下文；无独立 config 微服务，表由网关直管）。
表：system_options

对位 newAPI `/api/option/` KV 通道：key = `域.分区.字段`，value 为 JSON
标量/数组（string / number / boolean / string[]，与前端
domain/models/option.ts SystemOptionValue 一致）。value 用可移植 JSON
列类型（Postgres 迁移落 JSONB，见 scripts/migrations/202610/
add_system_options_table.py），SQLite 测试环境原生可用。
"""
from sqlalchemy import Column, DateTime, JSON, String, func

from shared.models.database import Base, utc8now


class SystemOption(Base):
    """系统选项 KV 记录（键为主键，PUT 单键 upsert）。"""

    __tablename__ = 'system_options'
    key = Column(String(255), primary_key=True, comment='选项键（域.分区.字段）')
    value = Column(JSON, nullable=False, comment='选项值（string/number/boolean/string[]）')
    updated_at = Column(
        DateTime, default=utc8now, server_default=func.now(),
        onupdate=utc8now, nullable=False, comment='更新时间',
    )
