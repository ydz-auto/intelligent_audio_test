import threading
import requests
import time
import json
import os
from typing import List, Dict, Optional
from ..models.task import TaskModel
from ..config import config
from datetime import datetime

class RemoteService:
    def __init__(self):
        # 跟踪每个端点每种任务类型的当前并发数 {endpoint_url: {task_type: current_concurrency}}
        self._endpoint_concurrency = {}
        self._lock = threading.Lock()

    def create_remote_task(self, task_type: str, task_params: dict = None,
                          endpoints: Optional[List[Dict]] = None, caller_task_id: str = None) -> str:
        """
        在合适的远程端点上创建任务，并返回任务ID
        支持多对多指标分配，每个端点可以配置处理多种指标及其并发限制
        如果endpoints参数为空，则从数据库获取配置的端点
        """
        # 获取可用端点配置：优先使用传入的endpoints，否则从数据库获取
        available_endpoints = endpoints if endpoints else TaskModel.get_all_endpoints()
        
        # 寻找可用端点
        selected_endpoint = None
        selected_endpoint_config = None
        
        with self._lock:
            for ep_config in available_endpoints:
                # 处理不同类型的端点配置（字典或数据库模型）
                if isinstance(ep_config, dict):
                    # 传入的endpoints配置
                    url = ep_config.get('endpoint')
                    db_config = TaskModel.get_endpoint(url)  # 检查是否有数据库配置
                    
                    # 优先使用数据库配置，否则使用传入的配置
                    config_to_use = db_config if db_config else ep_config
                else:
                    # 数据库模型
                    url = ep_config.get('url')
                    # 转换数据库模型为字典格式，与传入的endpoints配置格式一致
                    config_to_use = {
                        'endpoint': ep_config['url'],
                        'name': ep_config.get('name'),
                        'capabilities': ep_config.get('capabilities', {}),
                        'task_types': ep_config.get('task_types', []),
                        'max_process': ep_config.get('max_process', 1)
                    }
                    url = config_to_use['endpoint']
                
                # 获取该端点对该任务类型的支持情况和并发限制
                capabilities = config_to_use.get('capabilities', {})
                supported_types = config_to_use.get('task_types', [])
                
                limit = 0
                is_supported = False
                
                if task_type in capabilities:
                    limit = capabilities[task_type].get('max_process', 1)
                    is_supported = True
                elif task_type in supported_types:
                    limit = config_to_use.get('max_process', 1)
                    is_supported = True
                elif not capabilities and not supported_types:
                    limit = config_to_use.get('max_process', 1)
                    is_supported = True
                
                if not is_supported:
                    continue
                
                # 检查该端点该类型的并发限制
                if url not in self._endpoint_concurrency:
                    self._endpoint_concurrency[url] = {}
                
                current_count = self._endpoint_concurrency[url].get(task_type, 0)
                if current_count < limit:
                    selected_endpoint = url
                    selected_endpoint_config = config_to_use
                    self._endpoint_concurrency[url][task_type] = current_count + 1
                    break
        
        if not selected_endpoint:
            raise RuntimeError(f"没有可用的远程端点可以处理类型为 '{task_type}' 的任务（并发已满或不支持）")

        # 转发请求
        try:
            payload = {"task_type": task_type}
            if task_params:
                payload.update(task_params)

            timeout = selected_endpoint_config.get('max_timeout', 30)
            if task_type == 'llm_judge':
                timeout = max(timeout, 180)

            # 检测 task_params 中是否有文件路径（来自 create_task_upload 的二进制文件）
            file_fields = {}
            form_fields = {}
            if task_params:
                for key, value in task_params.items():
                    if isinstance(value, str) and os.path.isabs(value) and os.path.exists(value):
                        # 是文件路径，读取文件内容用于 multipart 上传
                        try:
                            with open(value, 'rb') as f:
                                file_bytes = f.read()
                            filename = os.path.basename(value)
                            file_fields[key] = (filename, file_bytes, 'application/octet-stream')
                        except Exception:
                            form_fields[key] = value
                    elif isinstance(value, (dict, list)):
                        form_fields[key] = json.dumps(value)
                    else:
                        form_fields[key] = value

            if file_fields:
                # 有文件，使用 multipart 上传端点
                form_fields['task_type'] = task_type
                if caller_task_id:
                    form_fields['task_id'] = caller_task_id
                response = requests.post(
                    f"{selected_endpoint.rstrip('/')}/api/create_task_upload",
                    data=form_fields,
                    files=file_fields,
                    timeout=timeout
                )
            else:
                # 无文件，使用 JSON 端点
                if caller_task_id:
                    payload['task_id'] = caller_task_id
                response = requests.post(
                    f"{selected_endpoint.rstrip('/')}/api/create_task",
                    json=payload,
                    timeout=timeout
                )
            
            if response.status_code != 200:
                raise RuntimeError(f"远程端点响应错误 ({response.status_code}): {response.text}")
            
            result = response.json()
            if result.get('code') != 0:
                raise RuntimeError(f"远程端点业务错误: {result.get('msg')}")
            
            task_data = result.get('data', {})
            remote_eval_task_id = task_data.get('eval_task_id')
            
            if not remote_eval_task_id:
                raise RuntimeError("远程端点未返回有效的 eval_task_id")

            source_lang = task_params.get('source_lang') if task_params else None
            target_lang = task_params.get('target_lang') if task_params else None
            translate_direct = task_params.get('translate_direct') if task_params else None
            TaskModel.create_task(
                eval_task_id=remote_eval_task_id,
                task_type=task_type,
                source_lang=source_lang,
                target_lang=target_lang,
                translate_direct=translate_direct,
                task_params=task_params,
                endpoints=endpoints,
                endpoint_url=selected_endpoint,
                task_id=caller_task_id
            )
            
            TaskModel.update_task_status(remote_eval_task_id, 'processing', started_at=datetime.now().isoformat())

            thread = threading.Thread(
                target=self._poll_task_status,
                args=(selected_endpoint, remote_eval_task_id, task_type)
            )
            thread.daemon = True
            thread.start()
            
            return remote_eval_task_id

        except Exception as e:
            if selected_endpoint:
                self._decrement_concurrency(selected_endpoint, task_type)
            raise e

    def _decrement_concurrency(self, endpoint_url: str, task_type: str):
        """减少端点特定任务类型的并发计数"""
        with self._lock:
            if endpoint_url in self._endpoint_concurrency:
                if task_type in self._endpoint_concurrency[endpoint_url]:
                    self._endpoint_concurrency[endpoint_url][task_type] = max(
                        0, self._endpoint_concurrency[endpoint_url][task_type] - 1
                    )

    def get_endpoints_stats(self) -> Dict:
        """获取端点并发统计信息"""
        with self._lock:
            return self._endpoint_concurrency.copy()

    def _poll_task_status(self, endpoint_url: str, eval_task_id: str, task_type: str):
        """轮询任务状态，完成后释放并发并同步结果"""
        poll_interval = 5 if task_type == 'llm_judge' else 2
        max_attempts = 60 if task_type == 'llm_judge' else 30

        try:
            status_url = f"{endpoint_url.rstrip('/')}/api/get_status/{eval_task_id}"
            result_url = f"{endpoint_url.rstrip('/')}/api/get_final_result/{eval_task_id}"
            
            for _attempt in range(max_attempts):
                time.sleep(poll_interval)
                try:
                    resp = requests.get(status_url, timeout=5)
                    if resp.status_code == 200:
                        data = resp.json()
                        status = data.get('data', {}).get('status')
                        if status in ['completed', 'failed']:
                            if status == 'completed':
                                try:
                                    res_resp = requests.get(result_url, timeout=5)
                                    if res_resp.status_code == 200:
                                        res_data = res_resp.json().get('data', {})
                                        TaskModel.update_task_status(
                                            eval_task_id,
                                            'completed',
                                            completed_at=datetime.now().isoformat(),
                                            result=res_data.get('result')
                                        )
                                    else:
                                        TaskModel.update_task_status(eval_task_id, 'failed', error_msg="无法获取远程结果")
                                except Exception as e:
                                    TaskModel.update_task_status(eval_task_id, 'failed', error_msg=f"同步结果失败: {str(e)}")
                            else:
                                error_msg = data.get('data', {}).get('error_msg', '远程任务失败')
                                TaskModel.update_task_status(eval_task_id, 'failed', error_msg=error_msg)
                            break
                    elif resp.status_code == 404:
                        TaskModel.update_task_status(eval_task_id, 'failed', error_msg="任务在远程端点不存在")
                        break
                except Exception as e:
                    print(f"Polling error for {eval_task_id}: {e}")
            else:
                TaskModel.update_task_status(
                    eval_task_id, 'failed',
                    error_msg=f"Remote task timeout after {max_attempts * poll_interval}s"
                )
                    
        finally:
            self._decrement_concurrency(endpoint_url, task_type)

remote_service = RemoteService()
