"""
Evaluation Service - 服务接口层
接收 Task Service 的 HTTP 请求，执行评估计算
"""
import threading

class EvalService:
    """评估服务"""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def init_app(self, app):
        """初始化服务"""
        self.app = app
        self._initialized = True
        # TODO: 初始化评估引擎

    def evaluate(self, task_id, dimension_config):
        """执行评估"""
        return {'success': True, 'task_id': task_id, 'message': 'Evaluation completed'}

    def get_status(self, task_id):
        """获取评估状态"""
        return {'task_id': task_id, 'status': 'idle'}

eval_service = EvalService()
