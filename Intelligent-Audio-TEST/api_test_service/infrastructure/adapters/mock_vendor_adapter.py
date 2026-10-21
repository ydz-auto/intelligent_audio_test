# -*- coding: utf-8 -*-
"""mock 厂商适配器（INT-62 扩展性验证 / 测试替身）。

演示「新增厂商适配器仅需注册不改核心链路」：本类经
@register_vendor_adapter 装饰注册进 vendor_adapter_registry，
用例配置 vendor_adapter='mock' 即分发到本适配器，执行链零改动。

行为：文本输入回显为 ASR，翻译结果按预设/配置返回，延迟可配置
（默认 0 保证测试速度），不发起真实网络调用。

INT-1169/1176 迁移：独立服务 api_adapter_service 删除后，mock 适配器
补齐 MockDialogAdapter 行为（轮询预设 / 随机 200-800ms 延迟 / 每会话
轮次计数，对齐 api_adapter_service/adapters/mock_adapter.py），
`execute_voice_llm_chat` 供多轮会话默认路径（use_adapter=True）消费，
保冒烟行为现状（vendor=mock + adapter_class=MockDialogAdapter）。
"""
import random
import time

from shared.models.common_enums import VendorAdapterType

from api_test_service.domain.ports import ApiVendorAdapter
from api_test_service.infrastructure.adapters.registry import register_vendor_adapter


@register_vendor_adapter
class MockVendorAdapter(ApiVendorAdapter):
    """mock 厂商协议适配器 — 不出网，回显输入 + 预设输出"""

    adapter_type = VendorAdapterType.MOCK

    DEFAULT_TRANS = 'mock translation'

    # MockDialogAdapter 轮询预设（对齐 api_adapter_service/adapters/mock_adapter.py）
    MOCK_RESPONSES = {
        'zh': [
            '你好，有什么可以帮助你的？',
            '好的，我明白了。',
            '今天的天气不错。',
            '让我帮你查一下。',
            '已经为你设置好了。',
            '抱歉，我没有听懂，请再说一遍。',
            '好的，正在为你处理。',
            '还有其他需要帮助的吗？',
        ],
        'en': [
            'Hello, how can I help you?',
            'OK, I understand.',
            'The weather is nice today.',
            'Let me check that for you.',
            'It has been set up for you.',
            "Sorry, I didn't catch that. Could you repeat?",
            'OK, processing your request.',
            'Is there anything else I can help with?',
        ],
    }

    def __init__(self, api_config, case_config=None, endpoint=None,
                 test_case_id=None, task_id=None):
        self.api_config = api_config
        self.endpoint = endpoint or (getattr(api_config, 'endpoint', None))
        self.meta = (getattr(api_config, 'meta', None) or {}) \
            if api_config is not None else {}
        self.case_config = case_config or {}
        self._test_case_id = test_case_id
        self._task_id = task_id
        self._round_counter: dict = {}  # session_id -> round count

    def execute(self, context_data, files=None, method=None):
        """回显输入并返回统一结构化结果（与 ApiDriverAdapter 结果契约同形）"""
        text = ''
        if isinstance(context_data, dict):
            text = str(context_data.get('input_text', ''))
        latency_ms = int(self._mock_latency() * 1000)
        if latency_ms > 0:
            time.sleep(latency_ms / 1000)

        return {
            "success": True,
            "latency": latency_ms,
            "status_code": 200,
            "raw_response": {"mock": True, "endpoint": self.endpoint},
            "error": None,
            "json": {"code": 0, "msg": "success", "data": {}},
            "asr": text,
            "trans": self.meta.get('mock_trans', self.DEFAULT_TRANS),
            "is_sentence_end": True,
            "is_session_end": True,
            "biz_code": 0,
            "biz_msg": 'success',
        }

    def render_request_parts(self, context_data):
        """mock 渲染：headers 原样透传，body 回显上下文"""
        headers = {**self.meta.get('headers', {}), **self.case_config.get('headers', {})}
        return headers, dict(context_data or {})

    def execute_voice_llm_chat(self, *, session_id, input_type, input_data,
                               source_lang='zh', target_lang='en',
                               context=None, context_for_request=None,
                               algorithm_params=None, case_algorithm_params=None,
                               translation_direction=None, round_number=0,
                               total_rounds=1, task_type='voice_llm',
                               headers=None, timeout=None):
        """MockDialogAdapter 行为等价（INT-1169/1176 迁移默认路径）。

        轮询预设 zh/en 逐轮取模、文本输入回显为 ASR、随机 200-800ms 延迟、
        每会话轮次计数（session_id → idx），保冒烟行为现状。
        """
        # 每会话轮次计数
        if session_id not in self._round_counter:
            self._round_counter[session_id] = 0
        idx = self._round_counter[session_id]
        self._round_counter[session_id] += 1

        zh_responses = self.MOCK_RESPONSES['zh']
        en_responses = self.MOCK_RESPONSES['en']

        asr_text = zh_responses[idx % len(zh_responses)]
        trans_text = en_responses[idx % len(en_responses)]

        # Echo mode: text input -> ASR returns input text
        if input_type == 'text' and isinstance(input_data, str) and input_data:
            asr_text = input_data

        # 模拟延迟（200ms - 800ms）
        simulated_latency = random.uniform(0.2, 0.8)
        time.sleep(simulated_latency)

        raw_response = {
            'mock': True,
            'round': round_number,
            'input_type': input_type,
            'session_id': session_id,
        }
        return {
            "success": True,
            "latency": int(simulated_latency * 1000),
            "status_code": 200,
            "raw_response": raw_response,
            "error": None,
            "json": {
                'asr_text': asr_text,
                'trans_text': trans_text,
                'output': asr_text,
                'session_id': session_id,
            },
            "asr": asr_text,
            "trans": trans_text,
            "output": asr_text,
            "is_sentence_end": True,
            "is_session_end": True,
            "biz_code": 0,
            "biz_msg": 'success',
        }

    def _mock_latency(self):
        """模拟延迟（秒）：case_config > meta 配置，默认 0"""
        for source in (self.case_config, self.meta):
            value = source.get('mock_latency')
            if value is not None:
                return float(value)
        return 0.0
