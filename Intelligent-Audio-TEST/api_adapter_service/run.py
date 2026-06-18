# -*- coding: utf-8 -*-
"""api_adapter_service entry point.

Starts the Flask server on port 8000 (configurable via application.yml).
"""

import os
import sys

# Ensure project root is on sys.path so imports work
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from api_adapter_service.app import create_app
from api_adapter_service.utils.config import config
from api_adapter_service.utils.logger import logger


def main():
    host = config.get('server.host', '0.0.0.0')
    port = config.get('server.port', 8000)
    dev_mode = config.get('server.dev_mode', False)

    app = create_app()

    logger.info(f'Starting api_adapter_service on {host}:{port} (dev={dev_mode})')
    app.run(host=host, port=port, debug=dev_mode, use_reloader=False)


if __name__ == '__main__':
    main()
