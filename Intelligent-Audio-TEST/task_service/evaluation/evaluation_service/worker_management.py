"""Worker 管理混入：初始化、端点 Worker 创建/预加载、关闭"""
import threading
from threading import Lock

from shared.models.models import Dimension
from shared.models.database import db
from task_service.evaluation.evaluation_api_client import evaluationApiClient
from task_service.evaluation.evaluation_result_processor import EvaluationResultProcessor
from task_service.evaluation.endpoint_worker import EndpointWorker
from task_service.evaluation.evaluation_mixin import get_endpoint_url, get_endpoint_field


class WorkerManagementMixin:
    """端点 Worker 的生命周期管理（初始化、创建、预加载、关闭）"""

    def __init__(self):
        self.current_test_case_id = None

        self._log(
            level='info',
            content='开始初始化评估服务',
            category='system'
        )

        self.api_cache = {}
        self.global_lock = Lock()

        self.api_client = evaluationApiClient()
        self.result_processor = EvaluationResultProcessor()

        self.endpoint_workers = {}
        self.endpoint_workers_lock = Lock()
        self.stop_event = threading.Event()

        self._load_all_endpoint_configs()

        self.api_client.init_thread_pool()

        self._log(
            level='info',
            content='评估服务初始化完成 (多端点Worker架构)',
            category='system'
        )

    def _get_timeout_from_dim_config(self, dim_data, default_timeout=30):
        dim_type = dim_data.get('dimension_type', 'main')
        api_settings = dim_data.get('api_settings', {})

        # llm_judge dimensions need longer timeout (LLM inference is slower)
        if dim_type == 'llm_judge':
            return api_settings.get('timeout', 120)

        timeout = api_settings.get('timeout')
        if timeout:
            return timeout

        endpoints = dim_data.get('api_endpoints', [])
        if endpoints and isinstance(endpoints, list) and len(endpoints) > 0:
            endpoint_item = endpoints[0]
            timeout = get_endpoint_field(endpoint_item, 'max_timeout', 'maxTimeout')
            if timeout:
                return timeout

        api_url = dim_data.get('api_url')
        if api_url:
            for endpoint_url, worker in self.endpoint_workers.items():
                if endpoint_url == api_url:
                    return worker.max_timeout

        return default_timeout

    def _get_or_create_worker(self, endpoint_url, dim_data):
        with self.endpoint_workers_lock:
            if endpoint_url not in self.endpoint_workers:
                max_timeout = self._get_timeout_from_dim_config(dim_data, 30)
                # 从端点配置获取 max_process（并发消费线程数）
                endpoints = dim_data.get('api_endpoints', [])
                max_concurrent = 1
                if endpoints and isinstance(endpoints, list) and len(endpoints) > 0:
                    endpoint_item = endpoints[0]
                    max_concurrent = get_endpoint_field(endpoint_item, 'max_process', 'maxProcess', 1)
                # 也从 api_client.endpoint_configs 获取
                if endpoint_url in self.api_client.endpoint_configs:
                    max_concurrent = self.api_client.endpoint_configs[endpoint_url]
                worker = EndpointWorker(endpoint_url, self, max_timeout=max_timeout, max_concurrent=max_concurrent)
                self.endpoint_workers[endpoint_url] = worker
                worker.start()
                self._log(
                    level='INFO',
                    content=f"为端点创建新Worker: {endpoint_url}, 超时: {max_timeout}秒, 并发: {max_concurrent}"
                )
            return self.endpoint_workers[endpoint_url]

    def _load_all_endpoint_configs(self):
        try:
            local_db_session = db.session()
            try:
                dimensions = local_db_session.query(Dimension).all()
                self.api_client.load_endpoint_configs(dimensions)
                self._log(level='info', content=f"已从数据库加载 {len(dimensions)} 个维度的端点配置", category='system')

                for dim in dimensions:
                    if dim.api_endpoints and isinstance(dim.api_endpoints, list):
                        for endpoint_item in dim.api_endpoints:
                            endpoint_url = get_endpoint_url(endpoint_item)
                            if endpoint_url:
                                timeout = get_endpoint_field(endpoint_item, 'max_timeout', 'maxTimeout', 30)
                                if endpoint_url not in self.endpoint_workers:
                                    worker = EndpointWorker(endpoint_url, self, max_timeout=timeout)
                                    self.endpoint_workers[endpoint_url] = worker
                                    worker.start()
                                    self._log(
                                        level='INFO',
                                        content=f"预创建端点Worker: {endpoint_url}, 超时: {timeout}秒"
                                    )
            finally:
                local_db_session.close()
        except Exception as e:
            self._log(level='error', content=f"加载维度配置失败: {str(e)}", category='system')

    def shutdown(self):
        self._log(level='info', content='开始关闭评估服务', category='system')

        self.stop_event.set()

        with self.endpoint_workers_lock:
            for endpoint_url, worker in self.endpoint_workers.items():
                worker.stop()
            self.endpoint_workers.clear()

        if self.api_client.thread_pool and not self.api_client.thread_pool._shutdown:
            try:
                self.api_client.thread_pool.shutdown(wait=True)
                self._log(level='info', content='评估服务线程池已关闭', category='system')
            except Exception as e:
                self._log(level='ERROR', content=f'关闭线程池失败: {str(e)}', category='system')

        self._log(level='info', content='评估服务已关闭', category='system')
