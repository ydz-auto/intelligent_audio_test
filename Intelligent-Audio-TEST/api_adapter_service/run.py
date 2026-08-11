# -*- coding: utf-8 -*-
"""api_adapter_service entry point.

Starts both:
- FastAPI HTTP server (port 5008)
- gRPC server (port 50081)
"""

import logging
import sys
import os
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))
except ImportError:
    pass

from api_adapter_service.utils.logger import logger
from api_adapter_service.interfaces.grpc.server import start_grpc_server


def main():
    # 启动 gRPC server
    grpc_port = int(os.environ.get('ADAPTER_SERVICE_GRPC_PORT', '50081'))
    try:
        server = start_grpc_server(port=grpc_port)
        logger.info(f'api_adapter_service gRPC server started on port {grpc_port}')
    except Exception as e:
        logger.error(f'gRPC server failed to start: {e}')
        server = None

    # 启动 FastAPI
    import uvicorn
    http_port = int(os.environ.get('ADAPTER_SERVICE_HTTP_PORT', '5008'))
    uvicorn.run(
        "api_adapter_service.app:app",
        host="0.0.0.0",
        port=http_port,
        workers=1,
        log_level="info",
    )

    if server:
        server.wait_for_termination()


if __name__ == '__main__':
    main()
