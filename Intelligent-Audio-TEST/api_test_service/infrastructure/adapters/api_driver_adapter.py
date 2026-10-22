# -*- coding: utf-8 -*-
"""内置 HTTP/WS 协议适配器（INT-62 首个注册适配器）。

自 api_test_service/clients/api_driver.py 原样迁移为 ApiVendorAdapter
Port 实现（设计文档 §3.6 生命周期语义：pre_process 渲染 + execute 调用
与响应解析），协议传输经同包 api_client（HTTP/WS 枚举分派）。
请求渲染、模板占位符与响应字段映射逻辑行为不变。

INT-1169/INT-1176 迁移：独立服务 api_adapter_service 删除后，voice_llm
多轮会话默认路径（use_adapter=True）由本适配器内嵌执行——`execute_voice_llm_chat`
对齐 HttpAdapter 请求/响应契约（URL=/chat 拼接、rendered_headers 合入 +
X-Session-Id、text json / audio multipart payload、result_parser 解析），
`execute`（body_template 渲染）保留为非 voice_llm 用例的另一执行路径。
"""
import json
from typing import Optional

from shared.utils.log_handler import log_and_emit
from shared.utils.path_extractor import extract_by_path
from shared.utils.config_manager import config_manager
from shared.utils.api_key_provider import (
    endpoint_rotation_key,
    resolver_from_config,
)
from shared.models.common_enums import VendorAdapterType

from api_test_service.domain.ports import ApiVendorAdapter
from api_test_service.infrastructure.adapters.transport import api_client
from api_test_service.infrastructure.adapters.audio_input import resolve_audio_bytes
from api_test_service.infrastructure.adapters.registry import register_vendor_adapter

# 密钥链解析器（UC-0901 扩展流程 3a）：各级键名/环境变量名经
# config_manager secrets 段配置，默认 case_config.api_key → meta.api_key
# → env OPENAI_API_KEY 逐级回退
_key_resolver = resolver_from_config(config_manager.get_value)


@register_vendor_adapter
class ApiDriverAdapter(ApiVendorAdapter):
    """
    API 驱动适配器：封装 API 调用逻辑、参数渲染及响应解析
    """

    adapter_type = VendorAdapterType.API_DRIVER

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
        """记录日志（调用方传参优先，实例属性兜底）"""
        kwargs.setdefault('task_id', self._task_id)
        kwargs.setdefault('test_case_id', self._test_case_id)
        log_and_emit(level=level, module='APIDriver', content=content, **kwargs)

    def _current_endpoint(self) -> Optional[dict]:
        """当前端点 dict：self.endpoint（含 path，api_task_runner 拼
        `/api/create_task` 等）base 前缀匹配回 api_config.api_endpoints 条目
        （INT-1230 审计 D3'：端点身份用 base URL，增删端点不漂移）。
        未匹配（main url 单端点 / 未配端点）返回 None → 回退单值链。"""
        eps = list(getattr(self.api_config, 'api_endpoints', None) or [])
        ep_url = str(self.endpoint or '').rstrip('/')
        best = None
        best_len = -1
        for ep in eps:
            if not isinstance(ep, dict):
                continue
            base = str(ep.get('endpoint') or '').rstrip('/')
            if not base:
                continue
            if ep_url == base or ep_url.startswith(base + '/'):
                if len(base) > best_len:
                    best = ep
                    best_len = len(base)
        return best

    def _merge_headers(self) -> dict:
        """合并 Headers：meta.headers + case_config.headers，并按密钥链
        （case_config → 当前端点 api_keys 池轮换 → meta → env，UC-0901 扩展
        流程 3a + INT-1177 endpoint 级轮换）注入 Bearer —— 解析到密钥且未
        显式配置 Authorization 头时才注入，显式头优先"""
        headers = {**self.meta.get('headers', {}), **self.case_config.get('headers', {})}
        endpoint = self._current_endpoint()
        api_key = _key_resolver.resolve_rotating(
            rotation_key=endpoint_rotation_key(
                getattr(self.api_config, 'id', None),
                (endpoint or {}).get('endpoint', '') or ''),
            endpoint=endpoint,
            case_config=self.case_config if isinstance(self.case_config, dict) else None,
            meta=self.meta if isinstance(self.meta, dict) else None)
        if api_key and not any(k.lower() == 'authorization' for k in headers):
            headers['Authorization'] = f'Bearer {api_key}'
        return headers

    # ── 密钥池失败降级重试（INT-1178，HTTP 内嵌路径）────────────────

    def _bearer_key_of(self, headers) -> str:
        """提取 Authorization 头中的 Bearer key（无 Bearer 前缀/无头返回 ''）。"""
        auth = next((v for k, v in (headers or {}).items()
                     if k.lower() == 'authorization'), '')
        if isinstance(auth, str) and auth.startswith('Bearer '):
            return auth[len('Bearer '):].strip()
        return ''

    def _rotate_bearer_headers(self, headers, rotation_key, endpoint_obj) -> dict:
        """重解析下一「非冷却」key 并替换 Authorization（其余头保持不变）。

        仅替换 Authorization：渲染头（render_request_parts 占位符替换结果）与
        X-Session-Id 等其余头原样保留，轮换不影响请求其余部分。
        """
        api_key = _key_resolver.resolve_rotating(
            rotation_key=rotation_key, endpoint=endpoint_obj,
            case_config=self.case_config if isinstance(self.case_config, dict) else None,
            meta=self.meta if isinstance(self.meta, dict) else None)
        new_headers = dict(headers)
        if api_key:
            new_headers['Authorization'] = f'Bearer {api_key}'
        return new_headers

    def _call_api_with_key_rotation(self, *, endpoint, method, headers,
                                    data=None, files=None, timeout=30, meta=None,
                                    proxy_type=None, proxy_url=None,
                                    log_prefix=''):
        """api_client.call + 密钥池失败降级重试（INT-1178）。

        仅当响应状态码 ∈ {401,403,429} 时触发轮换：将当前 Authorization 携带的
        key 报告失败（置冷却，冷却期不选），再经 resolve_rotating 解析下一
        「非冷却」key 重试；重试上限 = 当前端点池内 key 总数（有界）。
        5xx / 网络错误（status_code 0 / error 非空）不轮换。池全冷却立即失败
        （不空转等待）；全失败返回最后响应（success=False 携带最后错误）。
        未配置 api_keys（无池）退化为单次调用，行为与迁移前完全一致——
        执行器层只见解析结果，不感知轮换。
        """
        endpoint_obj = self._current_endpoint()
        rotation_key = endpoint_rotation_key(
            getattr(self.api_config, 'id', None),
            (endpoint_obj or {}).get('endpoint', '') or '')
        pool = _key_resolver.rotating_pool(endpoint_obj)
        max_attempts = max(len(pool), 1)

        current_headers = dict(headers or {})
        last_resp = None
        for attempt in range(max_attempts):
            last_resp = api_client.call(
                endpoint=endpoint, method=method, headers=current_headers,
                data=data, files=files, timeout=timeout, meta=meta,
                proxy_type=proxy_type, proxy_url=proxy_url,
            )
            if last_resp.get('status_code') not in (401, 403, 429):
                break
            current_key = self._bearer_key_of(current_headers)
            # 仅池内 key 触发轮换；case 单值 / 显式 Authorization / 无池不轮换
            if not pool or current_key not in pool:
                break
            self._log(level='WARNING',
                      content=f"{log_prefix}HTTP {last_resp['status_code']}，"
                              f"切换下一非冷却 key 重试"
                              f"（attempt {attempt + 1}/{max_attempts}）",
                      task_id=self._task_id, test_case_id=self._test_case_id)
            _key_resolver.report_failure(rotation_key, current_key)
            current_headers = self._rotate_bearer_headers(
                current_headers, rotation_key, endpoint_obj)
            if self._bearer_key_of(current_headers) == current_key:
                break  # 池全冷却（解析不到下一非冷却 key）→ 立即失败，不空转
        return last_resp

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

        # 合并 Headers（密钥链 Bearer 注入见 _merge_headers）
        headers = self._merge_headers()

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

        # INT-839：被测 API 网络代理透传（apis.proxy_type / proxy_url），
        # 无代理时两者为空，api_client 回退与改动前完全一致。
        # INT-1178：内包密钥池失败降级重试（401/403/429 切下一非冷却 key）。
        resp_info = self._call_api_with_key_rotation(
            endpoint=endpoint, method=method, headers=headers,
            data=request_data, files=files, timeout=timeout, meta=call_meta,
            proxy_type=getattr(self.api_config, 'proxy_type', None),
            proxy_url=getattr(self.api_config, 'proxy_url', None),
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

    def render_request_parts(self, context_data):
        headers = self._merge_headers()
        rendered_headers = {}
        for k, v in headers.items():
            if isinstance(v, str):
                rendered_headers[k] = self._replace_placeholders(v, context_data)
            else:
                rendered_headers[k] = v

        body_template = self.case_config.get('body_template') or self.meta.get('body_template') or self.meta.get('body', {})
        rendered_body = self._render_payload(body_template, context_data)

        return rendered_headers, rendered_body

    # ── voice_llm chat 等价能力（INT-1169/1176，对齐 HttpAdapter 契约） ──

    def execute_voice_llm_chat(self, *, session_id, input_type, input_data,
                               source_lang='zh', target_lang='en',
                               context=None, context_for_request=None,
                               algorithm_params=None, case_algorithm_params=None,
                               translation_direction=None, round_number=0,
                               total_rounds=1, task_type='voice_llm',
                               headers=None, timeout=None):
        """voice_llm chat payload 等价能力（api_adapter_service 迁移）。

        多轮会话默认路径（use_adapter=True）由本方法内嵌执行，逐字段对齐
        HttpAdapter.send_request：URL={base}/chat、rendered_headers 合入 +
        X-Session-Id、text 走 json payload / audio 走 multipart、显式
        timeout（session.session_timeout，不用 max_timeout 默认）、
        result_parser + 通用 fallback 解析。

        返回 execute 同形结果（success/latency/status_code/raw_response/
        error/json + asr/trans/output），供 _send_via_adapter 结果字段映射层
        消费；内嵌 _parse_response（asr_mapping/trans_mapping 体系）保留为
        非 voice_llm 用例的另一解析路径。
        """
        base_url = self._resolve_base_url()
        url = f'{base_url.rstrip("/")}/chat' if base_url else ''
        # 调用方（api_session_executor 内嵌路径）已先 render_request_parts 渲染
        # 头（含轮换解析后的 Authorization）——直接合入 X-Session-Id，避免二次
        # _merge_headers 推进轮换游标（INT-1178：每轮请求只消费一个 key）。
        # 独立调用未传 headers 时再经 _merge_headers 自建（含 Bearer 注入）。
        if headers:
            merged_headers = {**headers, 'X-Session-Id': session_id}
        else:
            merged_headers = {**self._merge_headers(), 'X-Session-Id': session_id}
        call_meta = {**self.meta, **self.case_config}
        # 显式超时优先（调用方恒传 session.session_timeout，默认 60）；兜底对齐
        # HttpAdapter 原默认 60——不得用 30 击杀 60s 慢调用（INT-54 deadline 回归）
        effective_timeout = timeout if timeout is not None else 60
        proxy_type = getattr(self.api_config, 'proxy_type', None)
        proxy_url = getattr(self.api_config, 'proxy_url', None)

        if input_type == 'text':
            payload = self._build_voice_llm_text_payload(
                session_id, input_data, source_lang, target_lang,
                context_for_request or context,
                algorithm_params, case_algorithm_params,
                translation_direction, round_number, total_rounds, task_type,
            )
            resp_info = self._call_api_with_key_rotation(
                endpoint=url, method='POST', headers=merged_headers,
                data=payload, timeout=effective_timeout, meta=call_meta,
                proxy_type=proxy_type, proxy_url=proxy_url,
                log_prefix='voice_llm chat: ',
            )
        else:
            # 音频引用（storage-ref/路径）统一解析为真实字节；解析失败抛错
            # 由调用方收敛为轮次失败，禁止静默空音频（INT-71 语义保留）
            audio_bytes = resolve_audio_bytes(input_data)
            files = {'audio': ('audio.wav', audio_bytes, 'audio/wav')}
            data = self._build_voice_llm_audio_data(
                session_id, input_data, source_lang, target_lang,
                context_for_request or context,
                algorithm_params, case_algorithm_params,
                translation_direction, round_number, total_rounds, task_type,
            )
            # multipart 请求移除 Content-Type（requests 自动设置）
            multipart_headers = {
                k: v for k, v in merged_headers.items()
                if k.lower() != 'content-type'
            }
            resp_info = self._call_api_with_key_rotation(
                endpoint=url, method='POST', headers=multipart_headers,
                files=files, data=data, timeout=effective_timeout,
                meta=call_meta, proxy_type=proxy_type, proxy_url=proxy_url,
                log_prefix='voice_llm chat: ',
            )

        self._log(level='DEBUG',
                  content=f"voice_llm chat: session={session_id}, "
                          f"round={round_number}, status={resp_info['status_code']}, "
                          f"latency={resp_info['latency']}ms",
                  task_id=self._task_id, test_case_id=self._test_case_id)

        parsed = self._parse_voice_llm_response(resp_info)
        # raw_response 保留结构化 JSON（HTTP 路径无 output_audio_path → None，
        # 契约保留，INT-300 输出 SPL 证据依赖）
        raw_response = resp_info['json'] \
            if isinstance(resp_info['json'], dict) else resp_info['raw_response']
        return {
            "success": (resp_info["status_code"] >= 200
                        and resp_info["status_code"] < 300)
            and not resp_info["error"],
            "latency": resp_info["latency"],
            "status_code": resp_info["status_code"],
            "raw_response": raw_response,
            "error": resp_info["error"],
            "json": resp_info["json"],
            **parsed,
        }

    def _resolve_base_url(self) -> str:
        """解析 voice_llm chat base URL：endpoint > api_endpoints 首项 > api_url。"""
        if self.endpoint:
            return self.endpoint
        api_config = self.api_config
        for source in (getattr(api_config, 'api_endpoints', None) or [],):
            for ep in source:
                url = (ep.get('endpoint') or '') if isinstance(ep, dict) else str(ep)
                if url:
                    return url
        for attr in ('api_url', 'endpoint'):
            val = getattr(api_config, attr, None)
            if isinstance(val, str) and val:
                return val
        return ''

    def _build_voice_llm_text_payload(self, session_id, text, source_lang,
                                      target_lang, context, algorithm_params,
                                      case_algorithm_params, translation_direction,
                                      round_number, total_rounds, task_type):
        return {
            'session_id': session_id,
            'task_type': task_type,
            'round': round_number,
            'total_rounds': total_rounds,
            'input': {
                'type': 'text',
                'text': text,
            },
            'source_lang': source_lang,
            'target_lang': target_lang,
            'translation_direction': translation_direction,
            'context': context or [],
            'algorithm_params': algorithm_params or [],
            'case_algorithm_params': case_algorithm_params or {},
        }

    def _build_voice_llm_audio_data(self, session_id, audio_data, source_lang,
                                    target_lang, context, algorithm_params,
                                    case_algorithm_params, translation_direction,
                                    round_number, total_rounds, task_type):
        return {
            'session_id': session_id,
            'task_type': task_type,
            'round': str(round_number),
            'total_rounds': str(total_rounds),
            'input_type': 'audio',
            'source_lang': source_lang,
            'target_lang': target_lang,
            'translation_direction': translation_direction or '',
            'context': json.dumps(context or []),
            'algorithm_params': json.dumps(algorithm_params or []),
            'case_algorithm_params': json.dumps(case_algorithm_params or {}),
        }

    def _parse_voice_llm_response(self, resp_info):
        """voice_llm chat 响应解析：result_parser 路径 + 通用 fallback。

        对齐 http_adapter._parse_response（asr_text_path / trans_text_path /
        session_id_path 逐级读取，空则回退 asr_text / output_content / output /
        trans_text / translation 通用字段名）。
        """
        response_data = resp_info.get('json', {})
        if not isinstance(response_data, dict):
            response_data = {}
        parser = self.meta.get('result_parser', {})

        def extract(data, path, default=''):
            if not path:
                return default
            keys = path.split('.')
            value = data
            for key in keys:
                if isinstance(value, dict):
                    value = value.get(key)
                else:
                    return default
            return value if value is not None else default

        asr_text = extract(response_data, parser.get('asr_text_path', ''), '')
        trans_text = extract(response_data, parser.get('trans_text_path', ''), '')
        session_id = extract(response_data, parser.get('session_id_path', ''), '')

        # Fallback: try common field names if parser paths are empty
        if not asr_text:
            asr_text = (response_data.get('asr_text')
                        or response_data.get('output_content')
                        or response_data.get('output', ''))
        if not trans_text:
            trans_text = (response_data.get('trans_text')
                          or response_data.get('translation', ''))

        return {
            'asr': asr_text,
            'trans': trans_text,
            'output': asr_text or trans_text or response_data.get('output', ''),
            'session_id': session_id,
        }

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
            biz_code = extract_by_path(resp_json, error_code_mapping)
            biz_msg = extract_by_path(resp_json, error_msg_mapping)

            # 如果业务码非0且非None，更新错误信息
            if biz_code is not None and str(biz_code) != '0':
                resp_info["error"] = f"BizError[{biz_code}]: {biz_msg or 'Unknown Error'}"

            # 处理标准API响应格式: {"code": 0, "msg": "success", "data": {...}}
            data = resp_json.get('data', resp_json)

            return {
                "asr": extract_by_path(data, asr_mapping) or (resp_text if not resp_json else ""),
                "trans": extract_by_path(data, trans_mapping) or "",
                "is_sentence_end": extract_by_path(data, sentence_end_mapping),
                "is_session_end": extract_by_path(data, session_end_mapping),
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
                biz_code = extract_by_path(msg_json, error_code_mapping)
                if biz_code is not None and str(biz_code) != '0':
                    latest_biz_code = biz_code
                    latest_biz_msg = extract_by_path(msg_json, error_msg_mapping)

                # 处理标准API响应格式: {"code": 0, "msg": "success", "data": {...}}
                data = msg_json.get('data', msg_json)

                # 提取当前消息的 ASR/翻译
                asr_val = extract_by_path(data, asr_mapping)
                trans_val = extract_by_path(data, trans_mapping)
                is_sentence_end = extract_by_path(data, sentence_end_mapping)

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

                if extract_by_path(data, session_end_mapping) is True:
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
