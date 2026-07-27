"""
API Test Service - 服务接口层
接收 Task Service 的 HTTP 请求，执行 API 测试
"""
import threading

class APITestService:
    """API 测试服务"""
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
        # TODO: 初始化 API 执行器、并发管理器等

    def start_task(self, task_id, case_ids, api_ids):
        """启动 API 测试任务"""
        return {'success': True, 'task_id': task_id, 'message': 'API test task started'}

    def stop_task(self, task_id):
        """停止 API 测试任务"""
        return {'success': True, 'task_id': task_id, 'message': 'API test task stopped'}

    def get_task_status(self, task_id):
        """获取任务状态"""
        return {'task_id': task_id, 'status': 'idle'}

api_test_service = APITestService()
