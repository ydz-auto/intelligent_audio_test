"""
Evaluation Service 服务启动入口
职责：评估计算、指标计算、报告生成
可独立部署或合并到 Task Service
"""
from flask import Flask
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(current_dir)
sys.path.insert(0, project_dir)

from shared.models.database import init_db
from shared.utils.service_registry import RedisServiceRegistry
from evaluation_service.core.eval_service import eval_service

app = None

def create_app(config_name='default'):
    global app
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
        'DATABASE_URL',
        'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'
    )
    init_db(app, pool_size=10)
    eval_service.init_app(app)

    @app.route('/health')
    def health():
        return {'status': 'ok', 'service': 'evaluation_service'}

    @app.route('/internal/health')
    def internal_health():
        return {'status': 'ok'}

    # /internal/tasks/* 路由 - 供 Task Service 通过 HTTP 调用
    @app.route('/internal/tasks/<task_id>/evaluate', methods=['POST'])
    def internal_evaluate(task_id):
        from flask import request
        data = request.get_json(silent=True) or {}
        return eval_service.evaluate(task_id, data.get('dimension_config'))

    @app.route('/internal/tasks/<task_id>/status')
    def internal_task_status(task_id):
        return eval_service.get_status(task_id)
    
    registry = RedisServiceRegistry()
    registry.register('evaluation_service', 
                      os.environ.get('SERVICE_HOST', '0.0.0.0'), 5004)
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5004, debug=False)
