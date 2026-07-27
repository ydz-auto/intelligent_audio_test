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

app = None

def create_app(config_name='default'):
    global app
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
        'DATABASE_URL',
        'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'
    )
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
                      os.environ.get('SERVICE_HOST', '0.0.0.0'), 5003)
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5003, debug=False)
