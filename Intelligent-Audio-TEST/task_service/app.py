"""
Task Service 服务启动入口
职责：任务调度、分发、进度管理、结果汇总、评估计算
"""
from flask import Flask
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(current_dir)
sys.path.insert(0, project_dir)

from shared.models.database import init_db
from shared.utils.service_registry import RedisServiceRegistry

app = None

def create_app(config_name='default'):
    global app
    app = Flask(__name__)
    DATABASE_URL = os.environ.get('DATABASE_URL')
    if not DATABASE_URL:
        raise RuntimeError('未配置 DATABASE_URL 环境变量')
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
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
    registry.register('task_service', os.environ.get('SERVICE_HOST', '0.0.0.0'), 5001)

    return app

if __name__ == '__main__':
    app = create_app()
    # 启动 gRPC server，与 Flask 服务并存
    from task_service.grpc.server import start_grpc_server
    grpc_server = start_grpc_server(port=int(os.environ.get('GRPC_PORT', 50061)))
    app.run(host='0.0.0.0', port=5001, debug=False)
