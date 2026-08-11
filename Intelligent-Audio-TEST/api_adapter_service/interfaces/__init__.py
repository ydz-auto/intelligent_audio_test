# -*- coding: utf-8 -*-
"""接口层（interfaces）。

本层的实际实现由已有模块构成：
- gRPC 接口 → api_adapter_service.interfaces.grpc（server.py）+ api_adapter_service.infrastructure.grpc（servicers.py）
- HTTP/FastAPI 接口 → api_adapter_service.routes.api（APIRouter）

应用层入口：
- 命令：api_adapter_service.application.commands.handlers
- 查询：api_adapter_service.application.queries.handlers
"""
