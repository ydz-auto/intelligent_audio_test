from flask import Flask
from .config import config
from .controllers.api import api_bp
from .controllers.health import health_bp
from .models.task import TaskModel
from .services.task_service import TaskService
import os

def create_app():
    app = Flask(__name__)
    app.config.from_object(config)

    # Ensure database directory exists
    os.makedirs(os.path.dirname(config.DATABASE_PATH), exist_ok=True)
    
    # Initialize database
    TaskModel.init_db()

    # Register blueprints
    app.register_blueprint(health_bp)
    app.register_blueprint(api_bp)

    # Start background worker
    TaskService.start_worker()

    return app
