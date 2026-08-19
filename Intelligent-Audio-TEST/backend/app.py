from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from config.config import config, Config
from backend.models.database import db

import logging
from logging.handlers import RotatingFileHandler

def _get_allowed_origins():
    origins = os.environ.get('ALLOWED_ORIGINS', '')
    if origins:
        return origins.split(',')
    if os.environ.get('FLASK_ENV') == 'production':
        return []
    return '*'

def _configure_pydub_ffmpeg():
    from pydub import AudioSegment
    ffmpeg_path = Config.FFMPEG_PATH
    ffprobe_path = Config.FFPROBE_PATH
    if ffmpeg_path and os.path.isfile(ffmpeg_path):
        AudioSegment.converter = ffmpeg_path
    if ffprobe_path and os.path.isfile(ffprobe_path):
        AudioSegment.ffprobe = ffprobe_path

_configure_pydub_ffmpeg()

_allowed_origins = _get_allowed_origins()
socketio = SocketIO(
    cors_allowed_origins=_allowed_origins,
    allow_credentials=True if _allowed_origins != '*' else False,
    async_mode='threading',
    ping_timeout=10,
    ping_interval=5,
    logger=False,
    engineio_logger=False,
)

# 全局应用实例，用于在后台线程中创建应用上下文
app = None

# 应用工厂函数：负责创建和配置 Flask 应用实例
def create_app(config_name='default'):
    global app
    app = Flask(__name__)
    from backend.utils.web.naming_middleware import NamingAliasMiddleware
    from backend.utils.web.naming_request import NamingRequest
    app.request_class = NamingRequest
    app.wsgi_app = NamingAliasMiddleware(app.wsgi_app)
    # 加载指定环境配置 (development/production)
    app.config.from_object(config[config_name])
    
    # 明确设置JSON_AS_ASCII为False，确保中文直接输出
    app.config['JSON_AS_ASCII'] = False
    
    # 配置日志系统
    # 避免在Flask重载器进程中重复配置日志处理器
    # 只有主进程（WERKZEUG_RUN_MAIN=true）才配置日志处理器
    is_main_process = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    
    # 配置日志格式化器，使用东八区时间
    from datetime import datetime, timezone, timedelta
    from logging import Formatter
    
    class UTC8Formatter(Formatter):
        def formatTime(self, record, datefmt=None):
            # 将时间戳转换为东八区时间
            dt = datetime.fromtimestamp(record.created, tz=timezone(timedelta(hours=8)))
            if datefmt:
                return dt.strftime(datefmt)
            return dt.isoformat()
    
    # 创建格式化器实例
    formatter = UTC8Formatter('[%(asctime)s] %(levelname)s in %(module)s: %(message)s')
    
    # 获取root_logger实例，在使用前先定义
    root_logger = logging.getLogger()
    
    if is_main_process:
        if not os.path.exists('logs'):
            os.makedirs('logs')
        
        # 不添加控制台日志处理器，避免打印过多HTTP请求日志
        # 如果需要调试，可以取消注释下面的代码
        # console_handler = logging.StreamHandler()
        # console_handler.setFormatter(formatter)
        # app.logger.addHandler(console_handler)
        # root_logger.addHandler(console_handler)
        
        # 使用循环文件处理器，防止单个日志文件过大，确保使用UTF-8编码
        # 添加delay=True参数，延迟打开日志文件，避免文件被占用
        handler = RotatingFileHandler(
            'logs/app.log', 
            maxBytes=10000000, 
            backupCount=10, 
            encoding='utf-8',
            delay=True  # 延迟打开文件，避免文件被占用
        )
        
        # 使用自定义的东八区日志格式化器
        handler.setFormatter(formatter)
        app.logger.addHandler(handler)
    
    # 添加自定义数据库日志处理器
    from backend.utils.web.log_handler import DatabaseLogHandler, get_db_handler, set_flask_app as set_log_flask_app
    set_log_flask_app(app)
    db_handler = get_db_handler()
    db_handler.setFormatter(formatter)
    
    # 只添加到app.logger，避免重复处理
    app.logger.addHandler(db_handler)
    # 设置propagate=False，防止日志向上传播到root_logger，避免重复处理
    app.logger.propagate = False
    
    # 移除已存在的db_handler，避免重复添加
    for handler in root_logger.handlers:
        if isinstance(handler, DatabaseLogHandler):
            root_logger.removeHandler(handler)
    
    # 从配置中获取日志级别
    log_level_name = app.config.get('LOG_LEVEL', 'INFO')
    log_level = getattr(logging, log_level_name, logging.INFO)
    
    # 设置root_logger的日志级别，避免捕获过多SocketIO内部日志
    root_logger.setLevel(log_level)
    
    root_logger.addHandler(db_handler)
    
    app.logger.setLevel(log_level)
    
    # 关键：在生产模式下，移除app.logger的所有默认处理器，只保留我们配置的
    if not app.debug:
        for handler in app.logger.handlers[:]:
            app.logger.removeHandler(handler)
        # 同时移除Flask的默认处理器
        flask_logger = logging.getLogger('flask')
        flask_logger.setLevel(log_level)
    
    # 验证UTF-8配置是否生效
    # 避免在Flask重载器进程中重复记录日志
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        app.logger.info(f'Task Manager 后端服务启动中... (Level: {logging.getLevelName(log_level)})')
        app.logger.info(f'JSON_AS_ASCII configuration: {app.config.get("JSON_AS_ASCII")}')
    
    # 初始化扩展
    CORS(app) # 开启跨域支持，允许 Electron 渲染进程访问
    db.init_app(app) # 初始化 SQLAlchemy 数据库连接
    
    # 初始化 SocketIO，确保使用Flask的JSON序列化器
    socketio.init_app(
        app,
        json=app.json,  # 明确设置使用Flask的JSON对象，包含dumps和loads方法
        cors_allowed_origins="*",  # 允许所有来源的WebSocket连接
        allow_credentials=True  # 允许携带凭证的连接
    )
    
    # 设置日志处理器的 SocketIO 实例
    from backend.utils.web.log_handler import set_socketio as set_log_socketio
    set_log_socketio(socketio)
    
    # 配置静态文件服务
    app.static_folder = app.config.get('STATIC_BASE_PATH')
    app.static_url_path = app.config.get('STATIC_URL_PREFIX')
    
    # 数据库表初始化
    with app.app_context():
        # 确保所有模型都已导入
        import backend.models.models
        import backend.models.algorithm_models
        
        db.create_all() # 创建所有定义的表 (如果不存在)
        
        try:
            # 服务重启时，将所有待执行和运行中的任务设置为失败状态
            from backend.models.models import Task, TaskCase, TestResult
            
            # 更新Task状态：将pending/queued/running/evaluating状态的任务设置为failed
            task_update_count = db.session.query(Task).filter(
                Task.status.in_(['pending', 'queued', 'running', 'evaluating', 'paused'])
            ).update({
                Task.status: 'failed',
                Task.completed_at: backend.models.models.utc8now()
            }, synchronize_session=False)
            
            # 更新TaskCase执行状态：将pending/queued/running/evaluating状态的执行设置为failed
            task_case_exec_update_count = db.session.query(TaskCase).filter(
                TaskCase.execution_status.in_(['pending', 'queued', 'running', 'evaluating'])
            ).update({
                TaskCase.execution_status: 'failed',
                TaskCase.status: 'failed',
                TaskCase.error_message: '服务重启导致任务中断',
                TaskCase.completed_at: backend.models.models.utc8now()
            }, synchronize_session=False)
            
            # 更新TaskCase评估状态：将pending/queued/running/evaluating状态的评估设置为failed
            task_case_eval_update_count = db.session.query(TaskCase).filter(
                TaskCase.evaluation_status.in_(['pending', 'queued', 'running', 'evaluating'])
            ).update({
                TaskCase.evaluation_status: 'failed',
                TaskCase.status: 'failed',
                TaskCase.error_message: '服务重启导致任务中断',
                TaskCase.completed_at: backend.models.models.utc8now()
            }, synchronize_session=False)
            
            # 更新TestResult执行状态：将pending/queued/running/evaluating状态的结果设置为failed
            test_result_update_count = db.session.query(TestResult).filter(
                TestResult.execution_status.in_(['pending', 'queued', 'running', 'evaluating'])
            ).update({
                TestResult.execution_status: 'failed',
                TestResult.error_message: '服务重启导致任务中断'
            }, synchronize_session=False)
            
            db.session.commit()
            
            app.logger.info(f"服务重启后任务状态更新：")
            app.logger.info(f"- 更新任务状态数: {task_update_count} (pending/queued/running/evaluating → failed)")
            app.logger.info(f"- 更新任务用例执行状态数: {task_case_exec_update_count} (pending/queued/running/evaluating → failed)")
            app.logger.info(f"- 更新任务用例评估状态数: {task_case_eval_update_count} (pending/queued/running/evaluating → failed)")
            app.logger.info(f"- 更新测试结果执行状态数: {test_result_update_count} (pending/queued/running/evaluating → failed)")
            
        except Exception as e:
            app.logger.error(f"服务重启时更新任务状态失败: {str(e)}")
            db.session.rollback()
        
        try:
            # 预置种子数据 (如果表为空)
            dimension_count = db.session.query(backend.models.models.Dimension).count()
            if dimension_count == 0:
                # dimensions = [
                #     backend.models.models.Dimension(name="ASR Accuracy", type="Accuracy", description="Word Error Rate for ASR", api_endpoints=[{"url": "http://localhost:5000/api/v1/eval/asr"}], rule={}, result_type=1),
                #     backend.models.models.Dimension(name="Translation Quality", type="Quality", description="BLEU score or manual rating", api_endpoints=[{"url": "http://localhost:5000/api/v1/eval/trans"}], rule={}, result_type=1),
                #     backend.models.models.Dimension(name="Latency", type="Performance", description="Response time in ms", api_endpoints=[{"url": "http://localhost:5000/api/v1/eval/latency"}], rule={}, result_type=1)
                # ]
                # db.session.bulk_save_objects(dimensions)
                # db.session.commit()
                app.logger.info("已预置默认评估维度数据")
        except Exception as e:
            app.logger.error(f"预置种子数据失败: {str(e)}")
            db.session.rollback()

        # 启动任务调度器
        from backend.services.execution.execution_engine import execution_engine
        from backend.utils.common.config_manager import config_manager
        config_manager.set_flask_config(app.config)
        execution_engine.set_scheduler_app(app)
        execution_engine._init_scheduler()
        app.logger.info("任务调度器初始化完成")

    # 注册各模块蓝图 (Blueprints)
    from blueprints.testcase_bp import testcase_bp
    from blueprints.group_bp import group_bp
    from blueprints.device_bp import device_bp
    from blueprints.playback_bp import playback_bp
    from blueprints.report_bp import report_bp
    from blueprints.task_bp import task_bp
    from blueprints.api_bp import api_bp
    from blueprints.execution_bp import execution_bp
    from blueprints.audio_bp import audio_bp
    from blueprints.evaluation_bp import evaluation_bp
    from blueprints.log_bp import log_bp
    from blueprints.spl_bp import spl_bp
    from blueprints.algorithm_bp import algorithm_bp
    from blueprints.tag_bp import tag_bp
    from controllers.home_controller import home_bp

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
    from controllers.log_controller import LogController
    socketio.on_event('connect', LogController.handle_connect, namespace='/ws/logs')
    socketio.on_event('disconnect', LogController.handle_disconnect, namespace='/ws/logs')
    socketio.on_event('set_filter', LogController.handle_set_filter, namespace='/ws/logs')

    # 任务状态推送：使用默认命名空间
    from controllers.task_controller import TaskController
    socketio.on_event('connect', lambda: print('Task client connected'))
    socketio.on_event('disconnect', lambda: print('Task client disconnected'))

    # 健康检查路由
    @app.route('/health')
    def health():
        from backend.utils.web.response import success_response
        return success_response(data={'status': 'ok'})

    @app.before_request
    def before_request():
        """
        统一请求拦截器 - 打印请求参数并记录开始时间
        """
        import json
        import time
        from flask import request
        from backend.utils.web.log_handler import log_and_emit
        from datetime import datetime, timezone, timedelta
        
        request._start_time = time.time()
        
        try:
            args = dict(request.args) if request.args else {}
            form = dict(request.form) if request.form else {}
            json_data = request.get_json(silent=True)
            
            log_content = f"API Request - URL: {request.path} | Method: {request.method}"
            
            if args:
                log_content += f" | Args: {json.dumps(args, ensure_ascii=False)[:500]}"
            if form:
                log_content += f" | Form: {json.dumps(form, ensure_ascii=False)[:500]}"
            if json_data:
                log_content += f" | Body: {json.dumps(json_data, ensure_ascii=False)[:500]}"
            
            log_and_emit(
                level='DEBUG',
                module='before_request',
                content=log_content,
                push_to_websocket=False
            )
        except Exception:
            pass

    @app.after_request
    def after_request(response):
        """
        统一响应拦截器
        1. 添加安全头
        2. 记录请求响应时间
        3. 确保响应格式一致性
        4. 打印响应内容到日志
        """
        import json
        import time
        from flask import request
        from backend.utils.web.log_handler import log_and_emit
        
        elapsed_ms = None
        if hasattr(request, '_start_time'):
            elapsed_ms = round((time.time() - request._start_time) * 1000, 2)
        
        try:
            content_type = response.headers.get('Content-Type', '')
            if 'zip' in content_type.lower() or 'octet-stream' in content_type.lower():
                pass
            else:
                elapsed_str = f" | Elapsed: {elapsed_ms}ms" if elapsed_ms else ""
                # 对错误响应记录响应体，方便排查问题
                body_str = ""
                if response.status_code >= 400 and 'application/json' in content_type:
                    try:
                        resp_data = response.get_json(silent=True)
                        if resp_data:
                            body_str = f" | Body: {json.dumps(resp_data, ensure_ascii=False)[:500]}"
                    except Exception:
                        pass
                log_and_emit(
                    level='INFO' if elapsed_ms and elapsed_ms > 1000 else 'DEBUG',
                    module='after_request',
                    content=f"API Response - URL: {request.path} | Method: {request.method} | Status: {response.status_code}{elapsed_str}{body_str}",
                    push_to_websocket=False
                )
        except Exception:
            pass
        
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        
        if elapsed_ms:
            response.headers['X-Elapsed-Time-Ms'] = str(elapsed_ms)
        
        from datetime import datetime as dt
        response.headers['X-Response-Time'] = dt.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        
        return response

    # 全局错误处理
    from utils.web.error_codes import ErrorCode
    from utils.web.response import format_response
    from flask import jsonify

    @app.errorhandler(Exception)
    def handle_exception(e):
        # 处理 HTTP 异常
        if hasattr(e, 'code') and hasattr(e, 'description'):
            code = e.code
            message = e.description
            if code == 404:
                error_code = ErrorCode.NOT_FOUND
            elif code == 400:
                error_code = ErrorCode.INVALID_PARAMS
            else:
                error_code = ErrorCode.BUSINESS_ERROR
        else:
            # 处理非 HTTP 异常
            app.logger.error(f"Unhandled Exception: {str(e)}", exc_info=True)
            error_code = ErrorCode.INTERNAL_SERVER_ERROR
            message = "Internal Server Error"
            code = 500

        return jsonify(format_response(
            code=error_code,
            message=message,
            detail=str(e) if app.debug else None
        )), code

    # 在主线程中预初始化 PyAudio 驱动
    # Pa_Initialize() 非线程安全，必须在服务启动前完成，避免子线程调用时卡死/崩溃
    try:
        from backend.services.audio.audio_engine import audio_service
        audio_service.init_driver()
    except Exception as e:
        app.logger.warning(f"PyAudio 驱动预初始化失败（音频功能可能不可用）: {e}")

    return app
