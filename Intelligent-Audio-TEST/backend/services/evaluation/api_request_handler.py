import os
import time
import json
import requests
import traceback
from backend.services.evaluation.evaluation_mixin import EvaluationLoggerMixin


class ApiRequestHandler(EvaluationLoggerMixin):
    """
    负责发起HTTP请求、管理异步任务流程（创建、轮询、获取结果）
    """

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
            except json.JSONDecodeError:
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

    def create_task(self, url, payload, timeout=10, task_id=None):
        """
        创建WER/SER计算任务
        """
        headers = {'Content-Type': 'application/json'}
        create_task_url = f"{url}/api/create_task"
        if task_id:
            payload = {**payload, 'task_id': task_id}
        return self.make_api_request(create_task_url, 'POST', headers, payload, timeout)

    def _extract_files_from_payload(self, payload):
        """
        从 payload 中提取 data URI 格式的值，转为文件上传字段。

        Returns:
            (form_fields, files) 元组
            - form_fields: 不含 data URI 的标量字段（dict/list 转 JSON 字符串）
            - files: {field_name: (filename, bytes, content_type)} 字典
        """
        form_fields = {}
        files = {}

        for key, value in payload.items():
            if isinstance(value, str) and value.startswith('data:') and ',' in value:
                try:
                    header, data = value.split(',', 1)
                    mime = header.split(':')[1].split(';')[0] if ':' in header else 'application/octet-stream'
                    import base64
                    file_bytes = base64.b64decode(data)

                    ext_map = {
                        'audio/wav': '.wav', 'audio/x-wav': '.wav',
                        'audio/mpeg': '.mp3', 'audio/mp3': '.mp3',
                        'audio/flac': '.flac', 'audio/ogg': '.ogg',
                        'audio/mp4': '.m4a', 'audio/aac': '.aac',
                    }
                    ext = ext_map.get(mime, '.bin')
                    filename = f"{key}{ext}"
                    files[key] = (filename, file_bytes, mime)
                except Exception:
                    form_fields[key] = value
            elif isinstance(value, str) and len(value) < 4096 and os.path.isabs(value) and os.path.exists(value):
                # 是文件路径，读取文件内容用于 multipart 上传
                try:
                    with open(value, 'rb') as f:
                        file_bytes = f.read()
                    filename = os.path.basename(value)
                    files[key] = (filename, file_bytes, 'application/octet-stream')
                except Exception:
                    form_fields[key] = value
            elif isinstance(value, (dict, list)):
                form_fields[key] = json.dumps(value)
            else:
                form_fields[key] = value

        return form_fields, files

    def create_task_upload(self, url, form_fields, files, timeout=30, task_id=None):
        """
        通过 multipart/form-data 创建评估任务（支持文件上传）
        """
        create_task_url = f"{url}/api/create_task_upload"

        if task_id:
            form_fields['task_id'] = task_id

        multipart_files = {}
        for field_name, (filename, file_bytes, content_type) in files.items():
            multipart_files[field_name] = (filename, file_bytes, content_type)

        try:
            resp = requests.post(create_task_url, data=form_fields, files=multipart_files, timeout=timeout)
            try:
                resp_data = resp.json()
            except json.JSONDecodeError:
                resp_data = resp.text

            if resp.status_code != 200:
                self._log(
                    level='ERROR',
                    category='execution',
                    content=f"上传API返回错误: {resp.status_code}, URL: {create_task_url}, 响应: {resp.text}"
                )
                if isinstance(resp_data, dict):
                    resp_data['__error__'] = f"HTTP {resp.status_code}"
                else:
                    resp_data = {'__error__': f"HTTP {resp.status_code}", '__raw_response__': resp_data}

            return resp_data
        except Exception as e:
            self._log(
                level='ERROR',
                category='execution',
                content=f"上传API请求异常: {str(e)}"
            )
            return {'__error__': str(e)}

    def get_task_status(self, url, eval_task_id, timeout=30):
        """
        查询评估任务状态
        """
        status_url = f"{url}/api/get_status/{eval_task_id}"
        return self.make_api_request(status_url, 'GET', {}, {}, timeout)

    def get_task_result(self, url, eval_task_id, timeout=30):
        """
        获取评估任务结果
        """
        result_url = f"{url}/api/get_final_result/{eval_task_id}"
        return self.make_api_request(result_url, 'GET', {}, {}, timeout)

    def wait_for_task_completion(self, url, eval_task_id, max_wait_time=300, poll_interval=5, test_case_id=None, api_id=None, task_id=None):
        """
        等待评估任务完成，定期查询状态
        """
        self._log('info', f'开始等待评估任务完成: eval_task_id={eval_task_id}, max_wait_time={max_wait_time}秒', task_id=task_id, test_case_id=test_case_id, api_id=api_id)

        start_time = time.time()
        poll_count = 0

        while time.time() - start_time < max_wait_time:
            poll_count += 1
            status_response = self.get_task_status(url, eval_task_id)

            if isinstance(status_response, dict) and status_response.get('code') == 0:
                data = status_response.get('data', {})
                status = data.get('status', '')
                elapsed_time = int(time.time() - start_time)

                if status == 'completed':
                    self._log('info', f'评估任务完成: eval_task_id={eval_task_id}, 耗时={elapsed_time}秒', task_id=task_id, test_case_id=test_case_id, api_id=api_id)
                    result_response = self.get_task_result(url, eval_task_id)
                    return result_response
                elif status == 'failed':
                    error_msg = data.get('error_msg', 'Task failed')
                    self._log('error', f'评估任务失败: eval_task_id={eval_task_id}, error={error_msg}', task_id=task_id, test_case_id=test_case_id, api_id=api_id)
                    return {'__error__': error_msg}
                else:
                    self._log('info', f'等待评估任务: eval_task_id={eval_task_id}, status={status}, 已等待={elapsed_time}秒, 第{poll_count}次查询', task_id=task_id, test_case_id=test_case_id, api_id=api_id)
            else:
                self._log('warning', f'查询评估任务状态失败: eval_task_id={eval_task_id}, response={status_response}', task_id=task_id, test_case_id=test_case_id, api_id=api_id)

            time.sleep(poll_interval)

        timeout_msg = f"评估任务超时: eval_task_id={eval_task_id}, 等待时间超过{max_wait_time}秒"
        self._log('error', timeout_msg, task_id=task_id, test_case_id=test_case_id, api_id=api_id)
        return {'__error__': timeout_msg}
