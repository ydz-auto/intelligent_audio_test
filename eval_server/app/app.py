from flask import Flask
from .config import config
from .controllers.api import api_bp
from .controllers.health import health_bp
from .models.task import TaskModel
from .services.task_service import TaskService
import os
import logging


def setup_logging():
    """配置日志：控制台 + 按时间/大小分卷的文件"""
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    formatter = logging.Formatter(log_format)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # 控制台
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 文件（按时间+大小分卷）
    os.makedirs(config.LOG_DIR, exist_ok=True)
    from .utils.log_rotation import SizeTimeRotatingFileHandler
    file_handler = SizeTimeRotatingFileHandler(
        config.LOG_FILE,
        maxBytes=config.LOG_MAX_BYTES,
        backupCount=config.LOG_BACKUP_COUNT,
        when='midnight',
        interval=1,
        encoding='utf-8',
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)


def create_app():
    setup_logging()

    app = Flask(__name__)
    app.config.from_object(config)

    # 初始化文件存储目录
    TaskModel.init_db()

    # 恢复上次重启前卡死的任务
    TaskModel.reset_processing_tasks()

    # 注册蓝图
    app.register_blueprint(health_bp)
    app.register_blueprint(api_bp)

    # 启动后台 worker
    TaskService.start_worker()

    return app
