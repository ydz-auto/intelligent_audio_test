# -*- coding: utf-8 -*-
"""api_adapter_service entry point.

Starts the gRPC server on port 50081 (configurable via ADAPTER_SERVICE_GRPC_PORT).
"""

import logging
import sys
import os

# Ensure project root is on sys.path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_adapter_service.utils.logger import logger
from api_adapter_service.grpc.server import start_grpc_server


def main():
    port = int(os.environ.get('ADAPTER_SERVICE_GRPC_PORT', '50081'))
    server = start_grpc_server(port=port)
    logger.info(f'api_adapter_service gRPC server started on port {port}')
    server.wait_for_termination()


if __name__ == '__main__':
    main()
