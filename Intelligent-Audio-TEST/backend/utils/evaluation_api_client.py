import time
import traceback
import json
import requests
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from backend.controllers.log_controller import LogController
from backend.utils.evaluation_utils import render_body_template
from backend.utils.config_manager import config_manager


class evaluationApiClient:
    """
    评估API客户端，负责管理端点配置、并发控制和API请求
    """
    
    def _log(self, level, content, task_id=None, test_case_id=None, api_id=None, **kwargs):
        """统一日志记录方法"""
        LogController.log_and_emit(
            level=level,
            module='Evaluation',
            category=kwargs.pop('category', 'execution'),
            content=content,
            task_id=task_id,
            api_id=api_id,
            test_case_id=test_case_id,
            **kwargs
        )
    
    def __init__(self):
        self.endpoint_semaphores = {}  # 端点信号量 {endpoint: Semaphore}
        self.endpoint_configs = {}  # 端点配置缓存 {endpoint: max_process}
        self.thread_pool = None  # 全局线程池，动态创建
        self.global_lock = Lock()  # 全局锁，用于保护端点资源创建
        
        # 从统一配置文件加载并发配置
        self.max_queue_size = config_manager.get_value('evaluation_service', 'max_queue_size', 100)  # 每个端点的最大队列长度
        self.max_wait_time = config_manager.get_value('evaluation_service', 'max_wait_time', 30)  # 任务在队列中的最大等待时间（秒）
    
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
                    endpoint_url = endpoint_item.get('url') or endpoint_item.get('endpoint')
                    if endpoint_url:
                        # 如果端点已经存在配置，不覆盖，确保配置的一致性
                        if endpoint_url not in self.endpoint_configs:
                            # 获取该端点的max_process配置，同时支持驼峰式maxProcess和下划线式max_process，默认值为1
                            max_process = endpoint_item.get('max_process', endpoint_item.get('maxProcess', 1))
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
        import threading
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
                self.endpoint_configs[endpoint] = 1
        
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
        import random
        selected = random.choice(endpoints)
        return selected.get('url') or selected.get('endpoint')
    
    def make_api_request(self, url, method, headers, payload, timeout=10):
        """
        发起API请求，支持GET和POST方法
        """
        resp_data = None
        
        try:
            # 创建请求头副本，避免修改原始数据
            request_headers = headers.copy() if headers else {}
            
            if method == 'GET':
                resp = requests.get(url, params=payload, headers=request_headers, timeout=timeout)
            else:
                # 确保POST请求使用正确的Content-Type
                if 'Content-Type' not in request_headers:
                    request_headers['Content-Type'] = 'application/json'
                # 确保POST请求总是有有效的payload，避免JSON解析错误
                if payload is None:
                    payload = {}
                resp = requests.post(url, json=payload, headers=request_headers, timeout=timeout)
            
            # 尝试解析JSON响应，无论状态码是什么
            try:
                resp_data = resp.json()
            except json.JSONDecodeError as e:
                # 非JSON响应，直接返回响应文本
                resp_data = resp.text
            
            if resp.status_code != 200:
                # 记录错误信息，但仍然返回响应数据，以便后续处理
                error_msg = f"API 返回错误: {resp.status_code}，请求URL: {url}，请求方法: {method}，请求头: {request_headers}，请求体: {payload}，响应内容: {resp.text}"
                self._log(
                    level='ERROR',
                    category='execution',
                    content=error_msg
                )
                # 将错误信息添加到响应数据中，方便后续处理
                if isinstance(resp_data, dict):
                    resp_data['__error__'] = error_msg
                else:
                    resp_data = {'__error__': error_msg, '__raw_response__': resp_data}
        except Exception as e:
            # 网络错误等异常情况
            error_msg = str(e)
            self._log(
                level='ERROR',
                category='execution',
                content=f"API请求异常: {error_msg}"
            )
            # 返回异常信息作为响应数据
            resp_data = {'__error__': error_msg}
        
        return resp_data
    
    def create_task(self, url, payload, timeout=10):
        """
        创建WER/SER计算任务
        """
        headers = {'Content-Type': 'application/json'}
        create_task_url = f"{url}/api/create_task"
        return self.make_api_request(create_task_url, 'POST', headers, payload, timeout)
    
    def get_task_status(self, url, task_id, timeout=10):
        """
        查询任务状态
        """
        status_url = f"{url}/api/get_status/{task_id}"
        return self.make_api_request(status_url, 'GET', {}, {}, timeout)
    
    def get_task_result(self, url, task_id, timeout=10):
        """
        获取任务结果
        """
        result_url = f"{url}/api/get_final_result/{task_id}"
        return self.make_api_request(result_url, 'GET', {}, {}, timeout)
    
    def wait_for_task_completion(self, url, task_id, max_wait_time=300, poll_interval=5, test_case_id=None, api_id=None, app_task_id=None):
        """
        等待任务完成，定期查询状态
        """
        self._log('info', f'开始等待任务完成: task_id={task_id}, max_wait_time={max_wait_time}秒', task_id=app_task_id, test_case_id=test_case_id, api_id=api_id)
        
        start_time = time.time()
        poll_count = 0
        
        while time.time() - start_time < max_wait_time:
            poll_count += 1
            status_response = self.get_task_status(url, task_id)
            
            if isinstance(status_response, dict) and status_response.get('code') == 0:
                data = status_response.get('data', {})
                status = data.get('status', '')
                elapsed_time = int(time.time() - start_time)
                
                if status == 'completed':
                    self._log('info', f'任务完成: task_id={task_id}, 耗时={elapsed_time}秒', task_id=app_task_id, test_case_id=test_case_id, api_id=api_id)
                    result_response = self.get_task_result(url, task_id)
                    return result_response
                elif status == 'failed':
                    error_msg = data.get('error_msg', 'Task failed')
                    self._log('error', f'任务失败: task_id={task_id}, error={error_msg}', task_id=app_task_id, test_case_id=test_case_id, api_id=api_id)
                    return {'__error__': error_msg}
                else:
                    self._log('info', f'等待任务: task_id={task_id}, status={status}, 已等待={elapsed_time}秒, 第{poll_count}次查询', task_id=app_task_id, test_case_id=test_case_id, api_id=api_id)
            else:
                self._log('warning', f'查询任务状态失败: task_id={task_id}, response={status_response}', task_id=app_task_id, test_case_id=test_case_id, api_id=api_id)
            
            time.sleep(poll_interval)
        
        timeout_msg = f"任务超时: task_id={task_id}, 等待时间超过{max_wait_time}秒"
        self._log('error', timeout_msg, task_id=app_task_id, test_case_id=test_case_id, api_id=api_id)
        return {'__error__': timeout_msg}
    
    def make_api_request_with_fallback(self, endpoints, method, headers, payload, task_id, dim_names, api_url=None, test_case_id=None, api_id=None, dim_info=None):
        """
        发起API请求，支持失败时切换到备用端点
        同时支持同步API和异步任务API（WER/SER计算器服务）
        
        Args:
            endpoints: API端点列表
            method: 请求方法
            headers: 请求头
            payload: 请求体
            task_id: 任务ID
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
            # 尝试获取端点并发槽位，支持排队等待
            self._log(
                level='DEBUG',
                category='execution',
                content=f"尝试获取端点 {selected_url} 的并发槽位",
                task_id=task_id,
                test_case_id=test_case_id,
                api_id=api_id
            )
            
            # 使用带超时的acquire_endpoint_slot方法，支持排队等待
            if not self.acquire_endpoint_slot(selected_url):
                stack_trace = traceback.format_exc()
                self._log(
                    level='ERROR',
                    category='execution',
                    content=f"端点 {selected_url} 并发数已满，排队超时，无法获取槽位，跳过评估\n堆栈信息: {stack_trace}",
                    task_id=task_id,
                    test_case_id=test_case_id,
                    api_id=api_id
                )
                return None, None
            
            self._log(
                level='DEBUG',
                category='execution',
                content=f"成功获取端点 {selected_url} 的并发槽位",
                task_id=task_id,
                test_case_id=test_case_id,
                api_id=api_id
            )
            
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
                    
                    # 1. 创建任务
                    create_task_payload = payload.copy() if isinstance(payload, dict) else {}
                    
                    # 确保包含必需字段，如果 payload 中没有，则尝试从 context 中获取的值（如果有的话）
                    # 这里的 payload 通常已经是 build_payload 后的结果
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
                    if endpoints and api_url:
                        formatted_endpoints = []
                        for endpoint_item in endpoints:
                            endpoint_url = endpoint_item.get('url') or endpoint_item.get('endpoint')
                            if endpoint_url:
                                formatted_endpoints.append({
                                    "endpoint": endpoint_url,
                                    "name": endpoint_item.get('name', f"worker-{len(formatted_endpoints) + 1}"),
                                    "max_process": endpoint_item.get('max_process', endpoint_item.get('maxProcess', 5)),
                                    "max_timeout": endpoint_item.get('max_timeout', endpoint_item.get('maxTimeout', 30))
                                })
                        
                        if formatted_endpoints:
                            create_task_payload["endpoints"] = formatted_endpoints
                    
                    create_response = self.create_task(selected_url, create_task_payload)
                    
                    if isinstance(create_response, dict) and create_response.get('code') == 0:
                        api_task_id = create_response.get('data', {}).get('task_id')
                        if api_task_id:
                            self._log(
                                level='INFO',
                                category='execution',
                                content=f"成功创建异步任务: {api_task_id}",
                                task_id=task_id,
                                test_case_id=test_case_id,
                                api_id=api_id
                            )
                            
                            # 2. 等待任务完成
                            result_response = self.wait_for_task_completion(
                                selected_url, 
                                api_task_id,
                                test_case_id=test_case_id,
                                api_id=api_id,
                                app_task_id=task_id
                            )
                            
                            if isinstance(result_response, dict):
                                if result_response.get('code') == 0:
                                    # 任务成功完成，提取结果数据
                                    resp_data = result_response.get('data', {}).get('result', {})
                                    self._log(
                                        level='INFO',
                                        category='execution',
                                        content=f"异步任务 {api_task_id} 完成，结果: {str(resp_data)}",
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
                        error_msg = create_response.get('msg', '创建任务失败') if isinstance(create_response, dict) else str(create_response)
                        self._log(
                            level='ERROR',
                            category='execution',
                            content=f"创建异步任务失败: {error_msg}",
                            task_id=task_id,
                            test_case_id=test_case_id,
                            api_id=api_id
                        )
                        resp_data = {'__error__': error_msg}
                else:
                    # 使用传统同步API
                    resp_data = self.make_api_request(selected_url, method, headers, payload)
                
                self._log(
                    level='INFO',
                    category='execution',
                    content=f"端点 {selected_url} 调用成功，响应：{str(resp_data)}，获取评估结果",
                    task_id=task_id,
                    test_case_id=test_case_id,
                    api_id=api_id
                )
            finally:
                # 释放端点并发槽位
                self.release_endpoint_slot(selected_url)
                self._log(
                    level='DEBUG',
                    category='execution',
                    content=f"释放端点 {selected_url} 并发槽位",
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
                for i, endpoint_item in enumerate(endpoints):
                    # 检查当前端点是否与选中的端点相同，支持两种字段名
                    endpoint_item_url = endpoint_item.get('url') or endpoint_item.get('endpoint')
                    if endpoint_item_url == selected_url:
                        continue
                    
                    # 支持两种字段名：'url'（旧）和'endpoint'（新）
                    fallback_url = endpoint_item.get('url') or endpoint_item.get('endpoint')
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
                        # 尝试获取备用端点的并发槽位，支持排队等待
                        self._log(
                            level='DEBUG',
                            category='execution',
                            content=f"尝试获取备用端点 {fallback_url} 的并发槽位",
                            task_id=task_id,
                            test_case_id=test_case_id,
                            api_id=api_id
                        )
                        
                        if not self.acquire_endpoint_slot(fallback_url):
                            self._log(
                                level='WARNING',
                                category='execution',
                                content=f"备用端点 {fallback_url} 并发数已满，排队超时，跳过该端点",
                                task_id=task_id,
                                test_case_id=test_case_id,
                                api_id=api_id
                            )
                            continue
                        
                        self._log(
                            level='DEBUG',
                            category='execution',
                            content=f"成功获取备用端点 {fallback_url} 的并发槽位",
                            task_id=task_id,
                            test_case_id=test_case_id,
                            api_id=api_id
                        )
                    
                        try:
                            # 所有评测任务都需要使用异步任务
                            is_async_api = True
                            
                            if is_async_api:
                                # 使用异步任务API流程
                                create_task_payload = payload.copy() if isinstance(payload, dict) else {}
                                if "task_type" not in create_task_payload:
                                    if dim_info and dim_info.get('task_type_code'):
                                        create_task_payload["task_type"] = dim_info['task_type_code']
                                    else:
                                        create_task_payload["task_type"] = "wer"
                                
                                create_response = self.create_task(fallback_url, create_task_payload)
                                
                                if isinstance(create_response, dict) and create_response.get('code') == 0:
                                    api_task_id = create_response.get('data', {}).get('task_id')
                                    if api_task_id:
                                        result_response = self.wait_for_task_completion(
                                            fallback_url, 
                                            api_task_id,
                                            test_case_id=test_case_id,
                                            api_id=api_id,
                                            app_task_id=task_id
                                        )
                                        
                                        if isinstance(result_response, dict):
                                            if result_response.get('code') == 0:
                                                resp_data = result_response.get('data', {}).get('result', {})
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
                                                error_msg = result_response.get('msg', 'Unknown error')
                                                self._log(
                                                    level='WARNING',
                                                    content=f"备用端点 {fallback_url} 异步任务失败: {error_msg}",
                                                    task_id=task_id,
                                                    test_case_id=test_case_id,
                                                    api_id=api_id
                                                )
                                else:
                                    self._log(
                                        level='WARNING',
                                        content=f"备用端点 {fallback_url} 创建任务失败",
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
                        finally:
                            self.release_endpoint_slot(fallback_url)
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
    
    def _process_field_by_type(self, field_value, field_type):
        """
        根据字段类型处理字段值
        
        Args:
            field_value: 字段值
            field_type: 字段类型 (text, audio, file, reference, score, number等)
            
        Returns:
            处理后的字段值
        """
        if isinstance(field_value, dict):
            actual_value = field_value.get('value')
            actual_type = field_value.get('field_type', field_type)
            return self._process_field_by_type(actual_value, actual_type)
        
        if field_type in ('audio', 'file'):
            if not field_value:
                return None
            if isinstance(field_value, str):
                if field_value.startswith('data:') or ',' in field_value[:50]:
                    return field_value
                import os
                if os.path.isfile(field_value):
                    import base64
                    try:
                        with open(field_value, 'rb') as f:
                            return 'data:audio/wav;base64,' + base64.b64encode(f.read()).decode()
                    except Exception:
                        return field_value
                return field_value
            return field_value
        
        return field_value
    
    def build_payload(self, body_template, context, task_id=None, test_case_id=None, algorithm_type=None):
        """
        构建API请求的Payload
        """
        processed_context = {}

        special_fields = set()
        if algorithm_type:
            from backend.algorithm.algorithm_result_field_mapper import AlgorithmResultFieldMapper
            output_fields = AlgorithmResultFieldMapper.get_output_fields(algorithm_type)
            for field in output_fields:
                source_param = field.get('source_param', '')
                if source_param:
                    special_fields.add(source_param)

        for k, v in context.items():
            if special_fields and k in special_fields and isinstance(v, dict) and 'text' in v and 'json' in v:
                processed_context[k] = v
            elif isinstance(v, dict) and 'field_type' in v:
                processed_context[k] = self._process_field_by_type(v, v.get('field_type', 'text'))
            else:
                processed_context[k] = v
        
        self._log(
            level='DEBUG',
            content=f"[build_payload] body_template={body_template}, special_fields={special_fields}, processed_context keys={list(processed_context.keys())}, processed_context values={dict((k, str(v)[:100]) for k, v in processed_context.items())}",
            task_id=task_id,
            test_case_id=test_case_id
        )
        
        if body_template:
            if isinstance(body_template, str):
                return render_body_template(body_template, processed_context)
            elif isinstance(body_template, dict):
                result = {}
                for k, v in body_template.items():
                    if k in processed_context:
                        result[k] = processed_context[k]
                    elif isinstance(v, str) and v.startswith('{{') and v.endswith('}}'):
                        placeholder_key = v[2:-2]
                        if placeholder_key in processed_context:
                            result[k] = processed_context[placeholder_key]
                        else:
                            result[k] = v
                    else:
                        result[k] = v
                return result
        return processed_context
