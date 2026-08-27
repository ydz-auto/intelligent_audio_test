import os
import time
import traceback
import json
import random
import threading
import requests
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from backend.services.evaluation.evaluation_utils import render_body_template
from backend.services.evaluation.api_request_handler import ApiRequestHandler
from backend.services.evaluation.payload_builder import PayloadBuilder
from backend.services.evaluation.evaluation_mixin import EvaluationLoggerMixin, get_endpoint_url, get_endpoint_field
from backend.utils.common.config_manager import config_manager


class evaluationApiClient(ApiRequestHandler, PayloadBuilder, EvaluationLoggerMixin):
    """
    评估API客户端，负责管理端点配置、并发控制和API请求

    继承 ApiRequestHandler（HTTP请求+异步任务流程）和 PayloadBuilder（Payload构建），
    对外保持原有接口不变。
    """

    def __init__(self):
        self.endpoint_semaphores = {}  # 端点信号量 {endpoint: Semaphore}
        self.endpoint_configs = {}  # 端点配置缓存 {endpoint: max_process}
        self.thread_pool = None  # 全局线程池，动态创建
        self.global_lock = Lock()  # 全局锁，用于保护端点资源创建

        # 从统一配置文件加载并发配置
        self.max_queue_size = config_manager.get_value('evaluation_service', 'max_queue_size', 100)  # 每个端点的最大队列长度
        self.max_wait_time = config_manager.get_value('evaluation_service', 'max_wait_time', 30)  # 任务在队列中的最大等待时间（秒）
        self.default_max_concurrent = config_manager.get_value('evaluation_service', 'default_max_concurrent', 10)  # 端点未配置时的默认并发数

    def load_endpoint_configs(self, dimensions):
        """
        从维度数据加载端点配置
        """
        try:
            all_endpoints = []
            for dim in dimensions:
                if dim.api_endpoints and isinstance(dim.api_endpoints, list):
                    all_endpoints.extend(dim.api_endpoints)

            with self.global_lock:
                for endpoint_item in all_endpoints:
                    endpoint_url = get_endpoint_url(endpoint_item)
                    if endpoint_url:
                        # 如果端点已经存在配置，不覆盖，确保配置的一致性
                        if endpoint_url not in self.endpoint_configs:
                            max_process = get_endpoint_field(endpoint_item, 'max_process', 'maxProcess', self.default_max_concurrent)
                            self.endpoint_configs[endpoint_url] = max_process
                            self._log(
                                level='debug',
                                category='system',
                                content=f'加载端点配置: {endpoint_url} | 最大并发数: {max_process}'
                            )
        except Exception as e:
            stack_trace = traceback.format_exc()
            self._log(
                level='ERROR',
                category='system',
                content=f'加载端点配置失败: {str(e)} 堆栈信息: {stack_trace}'
            )

    def init_thread_pool(self):
        """
        初始化线程池，使用加载的端点配置
        """
        try:
            with self.global_lock:
                # 检查解释器是否正在关闭
                import sys
                if hasattr(sys, 'is_finalizing') and sys.is_finalizing():
                    return

                # 计算总并发数
                total_concurrent = sum(self.endpoint_configs.values()) if self.endpoint_configs else 10

                # 仅当线程池不存在或已关闭时创建新线程池
                if self.thread_pool is None or self.thread_pool._shutdown:
                    self.thread_pool = ThreadPoolExecutor(
                        max_workers=total_concurrent,
                        thread_name_prefix="EvaluationThread-"
                    )
                    self._log(
                        level='info',
                        category='system',
                        content=f'初始化线程池，最大工作线程数: {total_concurrent}'
                    )
        except Exception as e:
            stack_trace = traceback.format_exc()
            self._log(
                level='ERROR',
                category='system',
                content=f'初始化线程池失败: {str(e)} 堆栈信息: {stack_trace}'
            )

    def _get_or_create_semaphore(self, endpoint, max_process):
        """
        获取或创建端点的信号量

        Args:
            endpoint: 端点URL
            max_process: 最大并发数

        Returns:
            threading.Semaphore: 端点信号量
        """
        with self.global_lock:
            if endpoint not in self.endpoint_semaphores:
                self.endpoint_semaphores[endpoint] = threading.Semaphore(max_process)
                self._log(
                    level='DEBUG',
                    category='system',
                    content=f'为端点 {endpoint} 创建信号量，最大并发数: {max_process}'
                )
            return self.endpoint_semaphores[endpoint]

    def acquire_endpoint_slot(self, endpoint, timeout=None):
        """
        获取端点的并发槽位，使用信号量实现

        Args:
            endpoint: 端点URL
            timeout: 最大等待时间（秒），None表示使用默认值

        Returns:
            bool: 是否成功获取槽位
        """
        wait_timeout = timeout or self.max_wait_time

        with self.global_lock:
            if endpoint not in self.endpoint_configs:
                self.endpoint_configs[endpoint] = self.default_max_concurrent

        max_process = self.endpoint_configs[endpoint]
        semaphore = self._get_or_create_semaphore(endpoint, max_process)

        start_time = time.time()
        remaining_time = wait_timeout

        while remaining_time > 0:
            try:
                acquired = semaphore.acquire(blocking=True, timeout=min(0.5, remaining_time))
                if acquired:
                    return True

                elapsed_time = time.time() - start_time
                remaining_time = wait_timeout - elapsed_time
            except Exception:
                return False

        return False

    def release_endpoint_slot(self, endpoint):
        """
        释放端点的并发槽位
        """
        if endpoint in self.endpoint_semaphores:
            try:
                self.endpoint_semaphores[endpoint].release()
            except ValueError:
                self._log(
                    level='WARNING',
                    category='system',
                    content=f'端点 {endpoint} 信号量释放失败（可能已超过最大值）'
                )

    def select_endpoint(self, endpoints):
        """
        从多个端点中选择一个
        注意：服务端已具备分布式调度能力，客户端仅需随机选择一个入口
        """
        if not endpoints or not isinstance(endpoints, list):
            return None

        # 随机选择一个入口
        selected = random.choice(endpoints)
        return selected.get('url') or selected.get('endpoint')

    def _execute_async_api_flow(self, selected_url, payload, dim_info, endpoints, api_url,
                                task_id, test_case_id, api_id, dim_names, audio_field_names=None):
        """
        执行异步任务API流程：创建任务 -> 轮询等待 -> 获取结果

        Returns:
            dict: 响应数据
        """
        # 1. 创建任务
        create_task_payload = payload.copy() if isinstance(payload, dict) else {}

        # 确保包含必需字段
        if "task_type" not in create_task_payload:
            if dim_info and dim_info.get('task_type_code'):
                create_task_payload["task_type"] = dim_info['task_type_code']
            else:
                create_task_payload["task_type"] = "wer"

        # 记录创建任务的 Payload
        self._log(
            level='DEBUG',
            category='execution',
            content=f"创建异步任务 Payload: {str(create_task_payload)}",
            task_id=task_id,
            test_case_id=test_case_id,
            api_id=api_id
        )

        # 如果有endpoints且使用api_url，添加endpoints参数用于分布式调度
        # 注意：当 api_url 就是评估服务自身时，不传 endpoints，避免远程分发到自身形成循环
        if endpoints and api_url and api_url != selected_url:
            formatted_endpoints = []
            for endpoint_item in endpoints:
                endpoint_url = get_endpoint_url(endpoint_item)
                if endpoint_url:
                    formatted_endpoints.append({
                        "endpoint": endpoint_url,
                        "name": endpoint_item.get('name', f"worker-{len(formatted_endpoints) + 1}"),
                        "max_process": get_endpoint_field(endpoint_item, 'max_process', 'maxProcess', 5),
                        "max_timeout": get_endpoint_field(endpoint_item, 'max_timeout', 'maxTimeout', 30)
                    })

            if formatted_endpoints:
                create_task_payload["endpoints"] = formatted_endpoints

        form_fields, files = self._extract_files_from_payload(create_task_payload, audio_field_names=audio_field_names)
        if files:
            create_response = self.create_task_upload(selected_url, form_fields, files, task_id=task_id)
        else:
            create_response = self.create_task(selected_url, create_task_payload, task_id=task_id)

        self._log(
            level='DEBUG',
            category='execution',
            content=f"create_task 请求已发送，开始处理响应",
            task_id=task_id,
            test_case_id=test_case_id,
            api_id=api_id
        )

        resp_data = None

        if isinstance(create_response, dict) and create_response.get('code') == 0:
            eval_task_id = create_response.get('data', {}).get('eval_task_id')
            if eval_task_id:
                self._log(
                    level='INFO',
                    category='execution',
                    content=f"成功创建异步任务: {eval_task_id}",
                    task_id=task_id,
                    test_case_id=test_case_id,
                    api_id=api_id
                )

                # 2. 等待任务完成
                result_response = self.wait_for_task_completion(
                    selected_url,
                    eval_task_id,
                    test_case_id=test_case_id,
                    api_id=api_id,
                    task_id=task_id
                )

                if isinstance(result_response, dict):
                    if result_response.get('code') == 0:
                        # 任务成功完成，提取结果数据
                        resp_data = result_response.get('data', {}).get('result', {})
                        self._log(
                            level='INFO',
                            category='execution',
                            content=f"异步任务 {eval_task_id} 完成，结果: {str(resp_data)}",
                            task_id=task_id,
                            test_case_id=test_case_id,
                            api_id=api_id
                        )
                    else:
                        # 任务失败
                        error_msg = result_response.get('msg', 'Unknown error')
                        self._log(
                            level='ERROR',
                            category='execution',
                            content=f"异步任务执行失败: {error_msg}",
                            task_id=task_id,
                            test_case_id=test_case_id,
                            api_id=api_id
                        )
                        resp_data = {'__error__': error_msg}
                else:
                    resp_data = {'__error__': f"Invalid response format: {str(result_response)}"}
            else:
                error_msg = "创建任务失败: 未返回task_id"
                self._log(
                    level='ERROR',
                    category='execution',
                    content=error_msg,
                    task_id=task_id,
                    test_case_id=test_case_id,
                    api_id=api_id
                )
                resp_data = {'__error__': error_msg}
        else:
            if isinstance(create_response, dict):
                # 优先取 __error__（网络异常等场景），其次取 msg，最后兜底
                error_msg = create_response.get('__error__') or create_response.get('msg', '创建任务失败')
            else:
                error_msg = str(create_response)
            self._log(
                level='ERROR',
                category='execution',
                content=f"创建异步任务失败: {error_msg}",
                task_id=task_id,
                test_case_id=test_case_id,
                api_id=api_id
            )
            resp_data = {'__error__': error_msg}

        return resp_data

    def make_api_request_with_fallback(self, endpoints, method, headers, payload, task_id, dim_names, api_url=None, test_case_id=None, api_id=None, dim_info=None, audio_field_names=None):
        """
        发起API请求，支持失败时切换到备用端点
        同时支持同步API和异步任务API（WER/SER计算器服务）

        Args:
            endpoints: API端点列表
            method: 请求方法
            headers: 请求头
            payload: 请求体
            task_id: 应用任务ID
            dim_names: 维度名称列表
            api_url: Master节点入口URL（分布式架构）
            test_case_id: 用例ID
            api_id: API ID
            dim_info: 维度详细信息字典，包含 dimension_type, task_type_code 等
        """
        # 选择URL：优先使用api_url，否则从endpoints中选择
        selected_url = api_url if api_url else self.select_endpoint(endpoints)
        if not selected_url:
            return None, None

        resp_data = None

        try:
            self._log(
                level='INFO',
                category='execution',
                content=f"调用API端点评估: {selected_url} | 维度: {dim_names} | 有效载荷: {str(payload)}",
                task_id=task_id,
                test_case_id=test_case_id,
                api_id=api_id
            )

            # 所有评测任务都需要使用异步任务
            is_async_api = True

            if is_async_api:
                # 使用异步任务API流程
                self._log(
                    level='INFO',
                    category='execution',
                    content=f"使用异步任务API评估 {dim_names} 维度",
                    task_id=task_id,
                    test_case_id=test_case_id,
                    api_id=api_id
                )

                resp_data = self._execute_async_api_flow(
                    selected_url, payload, dim_info, endpoints, api_url,
                    task_id, test_case_id, api_id, dim_names,
                    audio_field_names=audio_field_names
                )
            else:
                # 使用传统同步API
                resp_data = self.make_api_request(selected_url, method, headers, payload)

            self._log(
                level='INFO',
                category='execution',
                content=f"端点 {selected_url} 请求完成，响应：{str(resp_data)}",
                task_id=task_id,
                test_case_id=test_case_id,
                api_id=api_id
            )
        except Exception as e:
            self._log(
                level='WARNING',
                category='execution',
                content=f"端点 {selected_url} 返回错误: {str(e)}，尝试其他端点",
                task_id=task_id,
                test_case_id=test_case_id,
                api_id=api_id
            )

            # 只有当没有使用api_url时，才尝试其他端点
            if not api_url:
                selected_url, resp_data = self._try_fallback_endpoints(
                    endpoints, selected_url, method, headers, payload,
                    task_id, test_case_id, api_id, dim_names, dim_info,
                    audio_field_names=audio_field_names
                )

        return selected_url, resp_data

    def _try_fallback_endpoints(self, endpoints, selected_url, method, headers, payload,
                                 task_id, test_case_id, api_id, dim_names, dim_info, audio_field_names=None):
        """
        尝试备用端点

        Returns:
            (selected_url, resp_data) 元组
        """
        resp_data = None

        for i, endpoint_item in enumerate(endpoints):
            fallback_url = get_endpoint_url(endpoint_item)
            if fallback_url == selected_url:
                continue
            if not fallback_url or not fallback_url.startswith(('http://', 'https://')):
                self._log(
                    level='WARNING',
                    category='execution',
                    content=f"跳过无效备用端点: {fallback_url}",
                    task_id=task_id,
                    test_case_id=test_case_id,
                    api_id=api_id
                )
                continue

            try:
                # 所有评测任务都需要使用异步任务
                is_async_api = True

                if is_async_api:
                    resp_data = self._execute_async_api_flow(
                        fallback_url, payload, dim_info, endpoints, None,
                        task_id, test_case_id, api_id, dim_names,
                        audio_field_names=audio_field_names
                    )

                    if resp_data and '__error__' not in resp_data:
                        selected_url = fallback_url
                        self._log(
                            level='INFO',
                            content=f"切换到备用端点 {fallback_url} 成功，异步任务完成",
                            task_id=task_id,
                            test_case_id=test_case_id,
                            api_id=api_id
                        )
                        break
                    else:
                        error_msg = resp_data.get('__error__', 'Unknown error') if isinstance(resp_data, dict) else 'Unknown error'
                        self._log(
                            level='WARNING',
                            content=f"备用端点 {fallback_url} 异步任务失败: {error_msg}",
                            task_id=task_id,
                            test_case_id=test_case_id,
                            api_id=api_id
                        )
                else:
                    # 使用传统同步API
                    resp_data = self.make_api_request(fallback_url, method, headers, payload)
                    selected_url = fallback_url
                    self._log(
                        level='INFO',
                        content=f"切换到备用端点 {fallback_url} 成功",
                        task_id=task_id,
                        test_case_id=test_case_id,
                        api_id=api_id
                    )
                    break
            except Exception as fallback_e:
                self._log(
                    level='WARNING',
                    content=f"备用端点 {fallback_url} 调用失败: {str(fallback_e)}",
                    task_id=task_id,
                    test_case_id=test_case_id,
                    api_id=api_id
                )
                continue

        return selected_url, resp_data
