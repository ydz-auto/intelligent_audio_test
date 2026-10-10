# -*- coding: utf-8 -*-
"""api_adapter_service entry point.

Starts both:
- FastAPI HTTP server (port 5008)
- gRPC server (port 50081) —— 由 app lifespan 启动（INT-114），
  本入口只负责 uvicorn，不再手动拉起 gRPC（避免同端口双重绑定）。
"""

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))
except ImportError:
    logging.getLogger(__name__).debug("python-dotenv 未安装，跳过 .env 加载")


def main():
    # 启动 FastAPI（lifespan 内自启 gRPC server）
    import uvicorn
    http_port = int(os.environ.get('ADAPTER_SERVICE_HTTP_PORT', '5008'))
    uvicorn.run(
        "api_adapter_service.app:app",
        host="0.0.0.0",
        port=http_port,
        workers=1,
        log_level="info",
    )


if __name__ == '__main__':
    main()
