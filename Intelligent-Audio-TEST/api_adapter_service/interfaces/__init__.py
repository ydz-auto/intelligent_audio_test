# -*- coding: utf-8 -*-
"""接口层（interfaces）。

本层的实际实现由已有模块构成，未移动以保持导入路径稳定：
- gRPC 接口 → api_adapter_service.grpc（server.py / servicers.py）
- HTTP/FastAPI 接口 → api_adapter_service.routes.api（APIRouter）

应用层入口：
- 命令：api_adapter_service.application.commands.handlers
- 查询：api_adapter_service.application.queries.handlers
"""
