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

    def _extract_files_from_payload(self, payload, audio_field_names=None):
        """
        从 payload 中提取文件（data URI 或文件路径），转为 multipart 上传字段。

        遍历顶层字段和 rounds 列表里的字段。对于 ``audio_field_names`` 集合中的
        字段（field_mapper 中 type='audio' 的字段），会尝试提取为文件上传。
        单轮时，rounds[0] 里的音频字段会被提到顶层上传，rounds 里删掉该字段。
        多轮时，每轮的音频字段提取为 ``rounds_{index}_{field_name}`` 上传，
        rounds JSON 里对应值替换为 ``__MULTIPART__:rounds_{index}_{field_name}`` 占位符。

        支持的文件值形式：
        - data URI（``data:audio/wav;base64,...``）
        - 绝对路径（本地存在）
        - 相对路径（基于 STATIC_BASE_PATH 配置目录解析，本地存在）

        Args:
            payload: 请求体字典
            audio_field_names: set/list，需要作为文件上传的字段名集合。
                               为 None 时默认使用 {'record_file'}。

        Returns:
            (form_fields, files) 元组
            - form_fields: 不含文件的标量字段（dict/list 转 JSON 字符串）
            - files: {field_name: (filename, bytes, content_type)} 字典
        """
        if audio_field_names is None:
            audio_field_names = {'record_file'}
        audio_field_names = set(audio_field_names)

        form_fields = {}
        files = {}

        for key, value in payload.items():
            if key == 'rounds' and isinstance(value, list):
                # 深拷贝，避免修改原始 payload
                rounds_copy = json.loads(json.dumps(value))
                if len(rounds_copy) == 1 and isinstance(rounds_copy[0], dict):
                    # 单轮：把音频字段提到顶层上传，rounds 里删掉该字段
                    rd = rounds_copy[0]
                    for field_name in list(audio_field_names):
                        field_value = rd.pop(field_name, None)
                        if isinstance(field_value, str) and field_value:
                            self._extract_single_file(field_name, field_value, files,
                                                      form_fields_fallback=form_fields,
                                                      fallback_key=field_name, fallback_value=field_value)
                else:
                    # 多轮：每轮的音频字段提取为 rounds_{idx}_{field_name}
                    for idx, rd in enumerate(rounds_copy):
                        if not isinstance(rd, dict):
                            continue
                        for field_name in audio_field_names:
                            field_value = rd.get(field_name)
                            if isinstance(field_value, str) and field_value:
                                upload_field_name = f'rounds_{idx}_{field_name}'
                                extracted = self._extract_single_file(upload_field_name, field_value, files)
                                if extracted:
                                    rd[field_name] = f'__MULTIPART__:{upload_field_name}'
                form_fields[key] = json.dumps(rounds_copy)
            elif isinstance(value, str) and self._is_file_value(value):
                self._extract_single_file(key, value, files, form_fields_fallback=form_fields, fallback_key=key, fallback_value=value)
            elif isinstance(value, (dict, list)):
                form_fields[key] = json.dumps(value)
            else:
                form_fields[key] = value

        return form_fields, files

    @staticmethod
    def _is_file_value(value):
        """判断字符串值是否可能是文件（data URI 或本地可解析路径）。"""
        if not isinstance(value, str) or not value:
            return False
        if value.startswith('data:') and ',' in value:
            return True
        if len(value) >= 4096:
            return False
        # 绝对路径
        if os.path.isabs(value):
            return os.path.exists(value)
        # 相对路径：尝试多种方式解析
        return ApiRequestHandler._resolve_relative_path(value) is not None

    @classmethod
    def _extract_single_file(cls, field_name, value, files, form_fields_fallback=None, fallback_key=None, fallback_value=None):
        """提取单个文件到 files 字典。成功返回 True，失败时回退到 form_fields。"""
        try:
            if isinstance(value, str) and value.startswith('data:') and ',' in value:
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
                filename = f"{field_name}{ext}"
                files[field_name] = (filename, file_bytes, mime)
                return True
            elif isinstance(value, str) and len(value) < 4096:
                # 绝对路径直接用；相对路径解析
                resolved = value if os.path.isabs(value) else cls._resolve_relative_path(value)
                if resolved and os.path.exists(resolved):
                    with open(resolved, 'rb') as f:
                        file_bytes = f.read()
                    filename = os.path.basename(resolved)
                    files[field_name] = (filename, file_bytes, 'application/octet-stream')
                    return True
        except Exception:
            pass
        # 回退
        if form_fields_fallback is not None and fallback_key is not None:
            form_fields_fallback[fallback_key] = fallback_value
        return False

    @staticmethod
    def _resolve_relative_path(value):
        """
        将相对路径解析为本地存在的绝对路径。尝试多种方式：
        1. 基于当前工作目录直接解析
        2. 基于 STATIC_BASE_PATH 解析（处理路径前缀重复问题）
        返回第一个存在的绝对路径，都不存在则返回 None。
        """
        norm = value.replace('\\', os.sep).replace('/', os.sep)

        # 1. 直接基于当前工作目录
        if os.path.exists(norm):
            return os.path.abspath(norm)

        # 2. 基于 STATIC_BASE_PATH 解析
        try:
            from backend.config.config import Config
            base_path = getattr(Config, 'STATIC_BASE_PATH', None)
        except Exception:
            base_path = None
        if not base_path:
            return None

        base_norm = base_path.replace('\\', os.sep).replace('/', os.sep)
        # 如果 value 已经以 base_path 开头，直接用 value（避免重复拼接）
        if norm.startswith(base_norm):
            if os.path.exists(norm):
                return os.path.abspath(norm)
        # 否则拼接 base_path + value
        joined = os.path.join(base_norm, norm)
        if os.path.exists(joined):
            return os.path.abspath(joined)

        return None

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
