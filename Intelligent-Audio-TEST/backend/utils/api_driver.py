import time
import json
from backend.utils.api_client import api_client
from backend.utils.log_handler import log_and_emit

class APIDriver:
    """
    API 驱动程序：封装 API 调用逻辑、参数渲染及响应解析
    """
    
    def __init__(self, api_config, case_config=None, endpoint=None, test_case_id=None, task_id=None):
        """
        :param api_config: API 模型实例 (包含 max_timeout 等配置)
        :param case_config: 用例级特定配置 (如特定的 body_template, headers)
        :param endpoint: 可选的端点 URL (优先使用此值，否则使用 api_config.endpoint)
        :param test_case_id: 测试用例ID
        :param task_id: 任务ID
        """
        self.api_config = api_config
        self.endpoint = endpoint or (api_config.endpoint if hasattr(api_config, 'endpoint') else None)
        self.meta = api_config.meta or {}
        self.case_config = case_config or {}
        self._test_case_id = test_case_id
        self._task_id = task_id
        
    def set_test_case_id(self, test_case_id):
        """设置测试用例ID"""
        self._test_case_id = test_case_id
        
    def set_task_id(self, task_id):
        """设置任务ID"""
        self._task_id = task_id
        
    def _log(self, level='INFO', content='', **kwargs):
        """记录日志"""
        log_and_emit(level=level, module='APIDriver', content=content, task_id=self._task_id, test_case_id=self._test_case_id, **kwargs)
        
    def execute(self, context_data, files=None, method=None):
        """
        执行 API 调用并解析结果
        :param context_data: 运行时上下文数据 (如 case_name, timestamp 等)
        :param files: 需要上传的文件字典 (如 {'file': (name, stream, type)})
        :param method: 请求方法 (优先级最高)
        :return: 结构化的结果字典
        """
        self._log(level='INFO', content=f"执行API调用, endpoint: {self.endpoint}, method: {method or 'POST'}", task_id=self._task_id, test_case_id=self._test_case_id)
        
        # 1. 准备请求参数 (合并 API 级与用例级配置)
        endpoint = self.endpoint
        
        # 确定请求方法（优先级：参数 > 用例配置 > 元数据 > 默认POST）
        method = method or self.case_config.get('method') or self.meta.get('method', 'POST').upper()
        
        # 合并 Headers
        headers = {**self.meta.get('headers', {}), **self.case_config.get('headers', {})}
        
        # 获取并渲染 Body 模板
        body_template = self.case_config.get('body_template') or self.meta.get('body_template') or self.meta.get('body', {})
        data = self._render_payload(body_template, context_data)
        
        # 2. 发起请求
        timeout = self.api_config.max_timeout or 30
        
        # 合并 API 级元数据与用例级配置作为调用参数
        call_meta = {**self.meta, **self.case_config}
        
        # 对于GET请求，确保params是可哈希的，只包含简单类型
        if method == 'GET':
            # 过滤掉值为字典或列表的键，只保留简单类型
            filtered_params = {}
            for key, value in data.items():
                # 只保留字符串、数字、布尔值等简单类型
                if isinstance(value, (str, int, float, bool, type(None))):
                    filtered_params[key] = value
                elif isinstance(value, (list, tuple)):
                    # 对于列表，确保所有元素都是简单类型
                    if all(isinstance(item, (str, int, float, bool, type(None))) for item in value):
                        filtered_params[key] = value
            # 使用过滤后的参数
            request_data = filtered_params
        else:
            # POST等其他请求使用原始数据
            request_data = data
        
        self._log(level='DEBUG', content=f"发起请求: endpoint={endpoint}, method={method}, timeout={timeout}", task_id=self._task_id, test_case_id=self._test_case_id)
        
        resp_info = api_client.call(
            endpoint=endpoint,
            method=method,
            headers=headers,
            data=request_data,
            files=files,
            timeout=timeout,
            meta=call_meta
        )
        
        # 3. 解析响应结果
        parsed_result = self._parse_response(resp_info)
        
        self._log(level='INFO', content=f"API调用完成, status_code: {resp_info['status_code']}, latency: {resp_info['latency']}ms", task_id=self._task_id, test_case_id=self._test_case_id)
        
        return {
            "success": (resp_info["status_code"] >= 200 and resp_info["status_code"] < 300) and not resp_info["error"],
            "latency": resp_info["latency"],
            "status_code": resp_info["status_code"],
            "raw_response": resp_info["raw_response"],
            "error": resp_info["error"],
            "json": resp_info["json"],
            **parsed_result
        }

    def _render_payload(self, template, context):
        """
        根据上下文渲染请求 Payload
        """
        if not template: 
            return context
        
        if isinstance(template, dict):
            # 深度合并或简单合并 (此处采用浅合并并支持顶级占位符替换)
            rendered = {}
            for k, v in template.items():
                if isinstance(v, str):
                    rendered[k] = self._replace_placeholders(v, context)
                else:
                    rendered[k] = v
            # 将 context 中未在 template 中定义的 key 也合并进去
            return {**context, **rendered}
            
        elif isinstance(template, str):
            # 字符串模板替换 (支持 JSON 字符串模板)
            rendered_str = self._replace_placeholders(template, context)
            try:
                return json.loads(rendered_str)
            except:
                return {"raw_body": rendered_str}
        
        return template

    def _replace_placeholders(self, text, context):
        """
        替换字符串中的 {{key}} 占位符
        """
        if not isinstance(text, str): return text
        for k, v in context.items():
            placeholder = "{{" + str(k) + "}}"
            if placeholder in text:
                text = text.replace(placeholder, str(v))
        return text

    def _parse_response(self, resp_info):
        """
        根据 meta 中的映射配置提取 ASR、翻译、结束标志等字段
        支持单次调用响应和流式调用多条响应的聚合
        """
        all_responses = resp_info.get("all_responses", [])
        
        # 获取配置的映射路径
        asr_mapping = self.meta.get('asr_mapping', 'asr_result')
        trans_mapping = self.meta.get('trans_mapping', 'translation_result')
        sentence_end_mapping = self.meta.get('sentence_end_mapping', 'is_sentence_end')
        session_end_mapping = self.meta.get('session_end_mapping', 'session_finished')

        # 错误信息提取路径 (对接 API 文档)
        error_code_mapping = self.meta.get('error_code_mapping', 'code')
        error_msg_mapping = self.meta.get('error_msg_mapping', 'msg')

        if not all_responses:
            # 处理单次响应 (HTTP)
            resp_json = resp_info.get("json", {})
            resp_text = resp_info.get("raw_response", "")
            
            # 提取业务错误信息
            biz_code = self._extract_by_path(resp_json, error_code_mapping)
            biz_msg = self._extract_by_path(resp_json, error_msg_mapping)
            
            # 如果业务码非0且非None，更新错误信息
            if biz_code is not None and str(biz_code) != '0':
                resp_info["error"] = f"BizError[{biz_code}]: {biz_msg or 'Unknown Error'}"

            # 处理标准API响应格式: {"code": 0, "msg": "success", "data": {...}}
            data = resp_json.get('data', resp_json)
            
            return {
                "asr": self._extract_by_path(data, asr_mapping) or (resp_text if not resp_json else ""),
                "trans": self._extract_by_path(data, trans_mapping) or "",
                "is_sentence_end": self._extract_by_path(data, sentence_end_mapping),
                "is_session_end": self._extract_by_path(data, session_end_mapping),
                "biz_code": biz_code,
                "biz_msg": biz_msg
            }
        
        # 处理流式响应 (WebSocket)
        # 聚合逻辑：通常 ASR/翻译结果需要根据语句结束标志进行拼接或保留最后一条
        final_asr = []
        final_trans = []
        latest_asr = ""
        latest_trans = ""
        is_session_end = False
        latest_biz_code = None
        latest_biz_msg = None
        
        append_mode = self.meta.get('append_mode', False)
        
        for msg in all_responses:
            try:
                msg_json = json.loads(msg)
                
                # 提取业务错误
                biz_code = self._extract_by_path(msg_json, error_code_mapping)
                if biz_code is not None and str(biz_code) != '0':
                    latest_biz_code = biz_code
                    latest_biz_msg = self._extract_by_path(msg_json, error_msg_mapping)

                # 处理标准API响应格式: {"code": 0, "msg": "success", "data": {...}}
                data = msg_json.get('data', msg_json)
                
                # 提取当前消息的 ASR/翻译
                asr_val = self._extract_by_path(data, asr_mapping)
                trans_val = self._extract_by_path(data, trans_mapping)
                is_sentence_end = self._extract_by_path(data, sentence_end_mapping)
                
                if asr_val:
                    if append_mode:
                        if is_sentence_end:
                            final_asr.append(asr_val)
                    else:
                        latest_asr = asr_val
                
                if trans_val:
                    if append_mode:
                        if is_sentence_end:
                            final_trans.append(trans_val)
                    else:
                        latest_trans = trans_val

                if self._extract_by_path(data, session_end_mapping) is True:
                    is_session_end = True
            except:
                continue
        
        # 组装最终结果
        asr_result = "".join(final_asr) if append_mode else latest_asr
        trans_result = "".join(final_trans) if append_mode else latest_trans

        return {
            "asr": asr_result,
            "trans": trans_result,
            "is_sentence_end": True, # 流式结束默认为整句结束
            "is_session_end": is_session_end,
            "biz_code": latest_biz_code,
            "biz_msg": latest_biz_msg
        }

    def _extract_by_path(self, data, path):
        """
        辅助方法：从字典/列表中根据路径提取值 (支持 a.b.c 或 a.0.b 格式)
        """
        if not path or not data: return None
        try:
            for key in path.split('.'):
                if isinstance(data, dict):
                    data = data.get(key)
                elif isinstance(data, list) and key.isdigit():
                    data = data[int(key)]
                else:
                    return None
            return data
        except:
            return None
