# -*- coding: utf-8 -*-
"""Flask application factory for api_adapter_service."""

import threading
from flask import Flask
from flask_cors import CORS

from api_adapter_service.routes.api import api_bp
from api_adapter_service.services.session_store import session_store
from api_adapter_service.utils.config import config
from api_adapter_service.utils.logger import logger


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    CORS(app)

    app.register_blueprint(api_bp)

    # Periodic cleanup of expired sessions (background thread)
    def _cleanup_loop():
        import time
        while True:
            time.sleep(120)  # every 2 minutes
            try:
                cleaned = session_store.cleanup_expired()
                if cleaned:
                    logger.info(f'Cleaned up {cleaned} expired sessions')
            except Exception as e:
                logger.error(f'Session cleanup error: {e}')

    cleanup_thread = threading.Thread(target=_cleanup_loop, daemon=True)
    cleanup_thread.start()

    logger.info('api_adapter_service Flask app created')
    return app
