"""
API Test Service 服务启动入口
职责：API 测试执行、并发控制、健康监控
不需要物理设备，可水平扩展
"""
from flask import Flask
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(current_dir)
sys.path.insert(0, project_dir)

from shared.models.database import init_db
from shared.utils.service_registry import RedisServiceRegistry
from api_test_service.core.api_test_service import api_test_service
from api_test_service.config.config import Config

app = None

def create_app(config_name='default'):
    global app
    Config.validate()  # 启动前校验必填环境变量
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = Config.DATABASE_URL
    init_db(app, pool_size=5)
    api_test_service.init_app(app)

    @app.route('/health')
    def health():
        return {'status': 'ok', 'service': 'api_test_service'}

    @app.route('/internal/health')
    def internal_health():
        return {'status': 'ok'}

    # /internal/tasks/* 路由 - 供 Task Service 通过 HTTP 调用
    @app.route('/internal/tasks/<task_id>/start', methods=['POST'])
    def internal_start_task(task_id):
        from flask import request
        data = request.get_json(silent=True) or {}
        return api_test_service.start_task(
            task_id,
            data.get('case_ids', []),
            data.get('api_ids', [])
        )

    @app.route('/internal/tasks/<task_id>/stop', methods=['POST'])
    def internal_stop_task(task_id):
        return api_test_service.stop_task(task_id)

    @app.route('/internal/tasks/<task_id>/status')
    def internal_task_status(task_id):
        return api_test_service.get_task_status(task_id)
    
    registry = RedisServiceRegistry()
    registry.register('api_test_service',
                      Config.SERVICE_HOST, Config.PORT,
                      grpc_port=Config.GRPC_PORT)

    # 启动 gRPC server（在 create_app 内启动，确保任何调用方式都会启动）
    # 持有引用到 app.config 防止被 GC 回收
    from api_test_service.grpc.server import start_grpc_server
    try:
        app.config['_grpc_server'] = start_grpc_server(port=Config.GRPC_PORT)
        app.logger.info("gRPC server started on port %s", Config.GRPC_PORT)
    except Exception as e:
        app.logger.warning("gRPC server failed to start: %s", e)

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5003, debug=False)
