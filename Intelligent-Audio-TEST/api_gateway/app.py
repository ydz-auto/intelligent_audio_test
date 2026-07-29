"""
API Gateway 服务启动入口
职责：HTTP 路由、认证、限流、WebSocket 聚合、静态文件
"""
from flask import Flask
from flask_socketio import SocketIO
import os
import sys
import logging
from concurrent.futures import ThreadPoolExecutor

# 确保能找到 shared 包
current_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(current_dir)
sys.path.insert(0, project_dir)

from shared.models.database import init_db
from shared.utils.service_registry import RedisServiceRegistry
from api_gateway.config.config import Config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 自定义 Werkzeug WSGI Server：用固定大小线程池替代默认的"每请求新建线程"
# ---------------------------------------------------------------------------
# Werkzeug 的 ThreadedWSGIServer 继承 socketserver.ThreadingMixIn，
# 默认为每个请求创建一个新线程，无上限。在高并发场景下会导致线程爆炸。
# 这里重写 process_request，用 ThreadPoolExecutor 限制最大并发线程数。
#
# 线程数计算依据（1U4G 服务器，100 并发用户场景）：
#   - 100 用户中约 60% 同时在线，其中约 30-40 个并发 HTTP 请求
#   - 其余为 WebSocket 长连接（由 Socket.IO 内部管理，不占 WSGI 线程）
#   - 预留余量，默认 40 个线程上限（可通过 Config.WSGI_MAX_THREADS 调整）


class ThreadPoolWSGIServer:
    """Mixin：用 ThreadPoolExecutor 替代 ThreadingMixIn 的动态线程创建。

    通过 monkey-patch 替换 werkzeug.serving.ThreadedWSGIServer 的 process_request，
    使 socketio.run() → run_simple() → make_server() 返回的 ThreadedWSGIServer
    实例使用固定线程池，而非"每请求新建线程"。

    注意：不覆盖 shutdown_request，让继承的 BaseWSGIServer.shutdown_request
    正常处理 SSL teardown 等清理工作。
    """

    _max_workers = 40  # 默认值，由 patch_threaded_wsgi_server 覆盖

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 实例级线程池，避免跨实例共享；server_close 时可独立清理
        self._pool = ThreadPoolExecutor(
            max_workers=self._max_workers,
            thread_name_prefix='wsgi-'
        )

    def process_request(self, request, client_address):
        """将请求处理提交到固定大小线程池。

        当线程池满时，新请求在线程池内部队列排队等待，
        而不是无限创建新线程。
        """
        self._pool.submit(self._process_request_in_pool, request, client_address)

    def _process_request_in_pool(self, request, client_address):
        """在线程池中执行实际请求处理，并确保 shutdown_request 被调用。"""
        try:
            self.finish_request(request, client_address)
        except Exception:
            self.handle_error(request, client_address)
        finally:
            # 委托给继承链的 shutdown_request（BaseWSGIServer.shutdown_request）
            # 以正确处理 SSL teardown → close_request
            self.shutdown_request(request)

    def server_close(self):
        """关闭服务器时清理线程池，确保在途请求处理完成。"""
        super().server_close()
        self._pool.shutdown(wait=True)


def patch_threaded_wsgi_server(max_workers):
    """Monkey-patch werkzeug 的 ThreadedWSGIServer，注入固定线程池。

    必须在 socketio.run() / run_simple() 调用之前执行。
    """
    from werkzeug import serving

    # 获取原始 ThreadedWSGIServer（此时还未被 patch）
    OriginalThreadedWSGIServer = serving.ThreadedWSGIServer

    # 动态创建子类，继承原始 ThreadedWSGIServer 和我们的 ThreadPool mixin
    # 注意：MIXIN 必须在前，以便其 process_request 覆盖 ThreadingMixIn 的
    class PatchedThreadedWSGIServer(ThreadPoolWSGIServer, OriginalThreadedWSGIServer):
        _max_workers = max_workers

    # 替换 werkzeug 模块中的引用
    # make_server() 在 threaded=True 时会引用 serving.ThreadedWSGIServer
    serving.ThreadedWSGIServer = PatchedThreadedWSGIServer

    logger.info(
        "Werkzeug ThreadedWSGIServer patched: max_workers=%d (fixed thread pool)",
        max_workers
    )
    return PatchedThreadedWSGIServer


app = None
socketio = None

def create_app(config_name='default'):
    global app, socketio
    Config.validate()  # 启动前校验必填环境变量
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = Config.DATABASE_URL
    # 本地文件存储路径（音频上传分片、合并、转码中间文件等）
    app.config['AUDIO_STORAGE_PATH'] = Config.AUDIO_STORAGE_PATH

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
    registry.register('api_gateway', Config.SERVICE_HOST, Config.PORT)
    
    return app, socketio

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    app, socketio = create_app()

    # -----------------------------------------------------------------------
    # 线程上限：monkey-patch Werkzeug 的 ThreadedWSGIServer
    # -----------------------------------------------------------------------
    # Flask-SocketIO threading 模式底层用 Werkzeug 的 ThreadedWSGIServer，
    # 该类继承 socketserver.ThreadingMixIn，默认为每个请求创建新线程，无上限。
    # 这里替换为固定大小线程池，防止高并发下线程爆炸。
    #
    # 线程数 = 40（100 并发用户场景，并发 HTTP 请求约 30-40）
    # 可通过环境变量 WSGI_MAX_THREADS 调整
    patch_threaded_wsgi_server(Config.WSGI_MAX_THREADS)

    # Flask-SocketIO 使用 threading 模式（兼容 Windows，eventlet 已弃用）
    # 已通过 patch_threaded_wsgi_server 注入固定线程池上限
    socketio.run(app, host='0.0.0.0', port=Config.PORT, debug=False, allow_unsafe_werkzeug=True)
