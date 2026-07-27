"""
API Gateway 服务启动入口
职责：HTTP 路由、认证、限流、WebSocket 聚合、静态文件
"""
from flask import Flask
from flask_socketio import SocketIO
import os
import sys

# 确保能找到 shared 包
current_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(current_dir)
sys.path.insert(0, project_dir)

from shared.models.database import init_db
from shared.utils.service_registry import RedisServiceRegistry

app = None
socketio = None

def create_app(config_name='default'):
    global app, socketio
    app = Flask(__name__)
    DATABASE_URL = os.environ.get('DATABASE_URL')
    if not DATABASE_URL:
        raise RuntimeError('未配置 DATABASE_URL 环境变量')
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL

    init_db(app, pool_size=5)
    
    socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading')

    # 注册各模块蓝图 (Blueprints)
    from api_gateway.routes.testcase_bp import testcase_bp
    from api_gateway.routes.group_bp import group_bp
    from api_gateway.routes.device_bp import device_bp
    from api_gateway.routes.playback_bp import playback_bp
    from api_gateway.routes.report_bp import report_bp
    from api_gateway.routes.task_bp import task_bp
    from api_gateway.routes.api_bp import api_bp
    from api_gateway.routes.execution_bp import execution_bp
    from api_gateway.routes.audio_bp import audio_bp
    from api_gateway.routes.evaluation_bp import evaluation_bp
    from api_gateway.routes.log_bp import log_bp
    from api_gateway.routes.spl_bp import spl_bp
    from api_gateway.routes.algorithm_bp import algorithm_bp
    from api_gateway.routes.tag_bp import tag_bp
    from api_gateway.controllers.home_controller import home_bp

    # 注册 API 路由前缀
    if app.debug:
        app.logger.debug("Registering blueprints...")
    app.register_blueprint(testcase_bp, url_prefix='/api/v1/testcases')
    app.register_blueprint(group_bp, url_prefix='/api/v1/groups')
    app.register_blueprint(device_bp, url_prefix='/api/v1/test-devices')
    app.register_blueprint(playback_bp, url_prefix='/api/v1/playback-devices')
    app.register_blueprint(report_bp, url_prefix='/api/v1/reports')
    app.register_blueprint(task_bp, url_prefix='/api/v1/tasks')
    app.register_blueprint(api_bp, url_prefix='/api/v1/apis')
    app.register_blueprint(execution_bp, url_prefix='/api/v1/execution')
    app.register_blueprint(audio_bp, url_prefix='/api/v1/audios')
    app.register_blueprint(evaluation_bp, url_prefix='/api/v1/evaluation')
    app.register_blueprint(log_bp, url_prefix='/api/v1/logs')
    app.register_blueprint(spl_bp, url_prefix='/api/v1/spl')
    app.register_blueprint(algorithm_bp, url_prefix='/api/v1/algorithm')
    app.register_blueprint(tag_bp, url_prefix='/api/v1/tags')
    app.register_blueprint(home_bp, url_prefix='/api/v1/home')

    # 注册 WebSocket 事件处理器
    from api_gateway.controllers.log_controller import LogController
    from shared.utils.log_handler import set_socketio
    set_socketio(socketio)
    socketio.on_event('connect', LogController.handle_connect, namespace='/ws/logs')
    socketio.on_event('disconnect', LogController.handle_disconnect, namespace='/ws/logs')
    socketio.on_event('set_filter', LogController.handle_set_filter, namespace='/ws/logs')
    socketio.on_event('subscribe_task', LogController.handle_subscribe_task, namespace='/ws/logs')
    socketio.on_event('unsubscribe_task', LogController.handle_unsubscribe_task, namespace='/ws/logs')

    # 健康检查
    @app.route('/health')
    def health():
        return {'status': 'ok', 'service': 'api_gateway'}
    
    # 服务注册
    registry = RedisServiceRegistry()
    registry.register('api_gateway', os.environ.get('SERVICE_HOST', '0.0.0.0'), 5000)
    
    return app, socketio

if __name__ == '__main__':
    app, socketio = create_app()
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
