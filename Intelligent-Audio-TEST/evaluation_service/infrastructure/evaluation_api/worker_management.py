# -*- coding: utf-8 -*-
"""Worker 管理混入：初始化、端点 Worker 创建/预加载、关闭（Infrastructure 层）

P0-1 DDD 改造：从 domain/services/ 移至 infrastructure/。
线程池、端点 Worker 生命周期管理是基础设施逻辑，不属于 Domain 层。
"""
import threading
from threading import Lock

from evaluation_service.domain.services.endpoint_helpers import get_endpoint_url, get_endpoint_field


class WorkerManagementMixin:
    """端点 Worker 的生命周期管理（初始化、创建、预加载、关闭）"""

    def __init__(self, **kwargs):
        self.current_test_case_id = None

        self._log(
            level='info',
            content='开始初始化评估服务',
            category='system'
        )

        self.api_cache = {}
        self.global_lock = Lock()

        from evaluation_service.infrastructure.evaluation_api.evaluation_api_client import evaluationApiClient
        from evaluation_service.infrastructure.persistence.evaluation_result_processor import EvaluationResultProcessor

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
        super().__init__(**kwargs)

    def _get_timeout_from_dim_config(self, dim_data, default_timeout=30):
        dim_type = dim_data.get('dimension_type', 'main')
        api_settings = dim_data.get('api_settings', {})

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
                endpoints = dim_data.get('api_endpoints', [])
                max_concurrent = 1
                if endpoints and isinstance(endpoints, list) and len(endpoints) > 0:
                    endpoint_item = endpoints[0]
                    max_concurrent = get_endpoint_field(endpoint_item, 'max_process', 'maxProcess', 1)
                if endpoint_url in self.api_client.endpoint_configs:
                    max_concurrent = self.api_client.endpoint_configs[endpoint_url]
                from evaluation_service.infrastructure.evaluation_api.endpoint_worker import EndpointWorker
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
            from evaluation_service.infrastructure.evaluation_api.endpoint_worker import EndpointWorker
            from evaluation_service.infrastructure.persistence.evaluation_dimension_repository import (
                evaluation_dimension_repository,
            )
            dimension_aggregates = evaluation_dimension_repository.list_all_endpoint_dimensions()
            self.api_client.load_endpoint_configs(dimension_aggregates)
            self._log(level='info', content=f"已从 Repository 加载 {len(dimension_aggregates)} 个维度的端点配置", category='system')

            for agg in dimension_aggregates:
                snap = agg.snapshot
                if snap.api_endpoints and isinstance(snap.api_endpoints, list):
                    for endpoint_item in snap.api_endpoints:
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
