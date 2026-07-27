"""
E2E Test Service 服务启动入口
职责：E2E 测试执行、设备通信、音频播放、SPL 映射
需要物理设备（USB/串口）
"""
from flask import Flask
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(current_dir)
sys.path.insert(0, project_dir)

from shared.models.database import init_db
from shared.utils.service_registry import RedisServiceRegistry
from e2e_test_service.core.e2e_service import e2e_service

app = None

def create_app(config_name='default'):
    global app
    app = Flask(__name__)
    DATABASE_URL = os.environ.get('DATABASE_URL')
    if not DATABASE_URL:
        raise RuntimeError('未配置 DATABASE_URL 环境变量')
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
    init_db(app, pool_size=5)
    e2e_service.init_app(app)

    @app.route('/health')
    def health():
        return {'status': 'ok', 'service': 'e2e_test_service'}

    @app.route('/internal/health')
    def internal_health():
        return {'status': 'ok'}

    # /internal/tasks/* 路由 - 供 Task Service 通过 HTTP 调用
    @app.route('/internal/tasks/<task_id>/start', methods=['POST'])
    def internal_start_task(task_id):
        from flask import request
        data = request.get_json(silent=True) or {}
        return e2e_service.start_task(
            task_id,
            data.get('case_ids', []),
            data.get('device_id')
        )

    @app.route('/internal/tasks/<task_id>/stop', methods=['POST'])
    def internal_stop_task(task_id):
        return e2e_service.stop_task(task_id)

    @app.route('/internal/tasks/<task_id>/status')
    def internal_task_status(task_id):
        return e2e_service.get_task_status(task_id)
    
    lab_name = os.environ.get('LAB_NAME', 'lab-a')
    registry = RedisServiceRegistry()
    registry.register('e2e_test_service', 
                      os.environ.get('SERVICE_HOST', '0.0.0.0'), 5002,
                      grpc_port=50051,
                      capabilities={'labs': [lab_name]})
    
    return app

if __name__ == '__main__':
    app = create_app()
    # 启动 gRPC server，与 Flask 服务并存
    from e2e_test_service.grpc.server import start_grpc_server
    grpc_server = start_grpc_server(port=int(os.environ.get('GRPC_PORT', 50051)))
    app.run(host='0.0.0.0', port=5002, debug=False)
