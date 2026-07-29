"""
Task Service 服务启动入口
职责：任务调度、分发、进度管理、结果汇总、评估计算
"""
from flask import Flask
import os
import sys
import logging

current_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(current_dir)
sys.path.insert(0, project_dir)

from shared.models.database import init_db
from shared.utils.service_registry import RedisServiceRegistry
from task_service.config.config import Config

app = None

def create_app(config_name='default'):
    global app
    Config.validate()  # 启动前校验必填环境变量
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = Config.DATABASE_URL
    init_db(app, pool_size=20)

    # 健康检查
    @app.route('/health')
    def health():
        return {'status': 'ok', 'service': 'task_service'}

    @app.route('/internal/health')
    def internal_health():
        return {'status': 'ok'}

    # 初始化任务调度器（参考原 backend/app.py 第 250-256 行）
    from task_service.core.execution_engine import execution_engine
    execution_engine.set_scheduler_app(app)
    execution_engine._init_scheduler()
    app.logger.info("任务调度器初始化完成")

    # 初始化评估服务
    from task_service.evaluation.evaluation_service import EvaluationService, evaluation_service
    app.logger.info("评估服务初始化完成")

    # 任务相关 API 路由占位
    @app.route('/api/v1/tasks/start', methods=['POST'])
    def start_task():
        """启动测试任务"""
        return {'status': 'ok', 'message': 'task start placeholder'}

    @app.route('/api/v1/tasks/<task_id>/stop', methods=['POST'])
    def stop_task(task_id):
        """停止测试任务"""
        return {'status': 'ok', 'message': f'task {task_id} stop placeholder'}

    @app.route('/api/v1/tasks/<task_id>/status', methods=['GET'])
    def get_task_status(task_id):
        """查询任务状态"""
        return {'status': 'ok', 'task_id': task_id, 'message': 'task status placeholder'}

    registry = RedisServiceRegistry()
    registry.register('task_service', Config.SERVICE_HOST, Config.PORT)

    # 启动 gRPC server（在 create_app 内启动，确保任何调用方式都会启动）
    from task_service.grpc.server import start_grpc_server
    try:
        app.config['_grpc_server'] = start_grpc_server(port=Config.GRPC_PORT)
        app.logger.info("gRPC server started on port %s", Config.GRPC_PORT)
    except Exception as e:
        app.logger.warning("gRPC server failed to start: %s", e)

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5001, debug=False)
