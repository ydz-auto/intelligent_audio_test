# -*- coding: utf-8 -*-
"""algorithm_service.application — 应用层（CQRS）。

应用层职责：
- commands: 写操作命令（frozen dataclass）
- queries:  读操作查询（frozen dataclass）
- handlers: 命令/查询处理器，通过 repository 操作领域聚合根，
  不直接 import PO，隔离领域层与 ORM

说明：
- 本层不持有业务规则，业务规则由 domain 层聚合根/领域服务承载。
- Handler 通过模块级单例 repository（algorithm_group_repository /
  algorithm_definition_repository）访问数据。
"""
