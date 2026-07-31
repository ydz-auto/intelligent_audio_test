# -*- coding: utf-8 -*-
"""task_service 应用层 (Application Layer) - CQRS 架构。

commands/ 处理写操作（创建、启动、停止、合并任务），委托给 ExecutionEngine。
queries/  处理读操作（查询任务状态、列表、进度），直接查 DB。
"""
