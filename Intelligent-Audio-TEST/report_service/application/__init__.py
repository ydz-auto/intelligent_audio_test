# -*- coding: utf-8 -*-
"""report_service 应用层 (Application Layer)

CQRS 分层入口，协调领域层与基础设施：
- commands/   命令对象（写模型意图）
- queries/    查询对象（读模型意图）
- handlers/   命令/查询处理器（编排领域逻辑与仓储）

应用层不直接依赖 ORM/PO，仅通过 repository 操作聚合根。
"""
