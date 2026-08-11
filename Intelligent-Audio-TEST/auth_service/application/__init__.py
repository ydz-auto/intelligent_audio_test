# -*- coding: utf-8 -*-
"""auth_service 应用层（Application Layer）。

归属：auth_service（用户与权限上下文）

CQRS 分层：
- commands/  写操作命令（frozen dataclass）
- queries/   读操作查询（frozen dataclass）
- handlers/  命令/查询处理器，通过 repository 操作领域实体，
             不直接 import PO，保证应用层与持久化解耦。
"""
