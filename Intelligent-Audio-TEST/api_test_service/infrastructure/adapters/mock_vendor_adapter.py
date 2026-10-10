# -*- coding: utf-8 -*-
"""mock 厂商适配器（INT-62 扩展性验证 / 测试替身）。

演示「新增厂商适配器仅需注册不改核心链路」：本类经
@register_vendor_adapter 装饰注册进 vendor_adapter_registry，
用例配置 vendor_adapter='mock' 即分发到本适配器，执行链零改动。

行为：文本输入回显为 ASR，翻译结果按预设/配置返回，延迟可配置
（默认 0 保证测试速度），不发起真实网络调用。
"""
import time

from shared.models.common_enums import VendorAdapterType

from api_test_service.domain.ports import ApiVendorAdapter
from api_test_service.infrastructure.adapters.registry import register_vendor_adapter


@register_vendor_adapter
class MockVendorAdapter(ApiVendorAdapter):
    """mock 厂商协议适配器 — 不出网，回显输入 + 预设输出"""

    adapter_type = VendorAdapterType.MOCK

    DEFAULT_TRANS = 'mock translation'

    def __init__(self, api_config, case_config=None, endpoint=None,
                 test_case_id=None, task_id=None):
        self.api_config = api_config
        self.endpoint = endpoint or (getattr(api_config, 'endpoint', None))
        self.meta = (getattr(api_config, 'meta', None) or {}) \
            if api_config is not None else {}
        self.case_config = case_config or {}
        self._test_case_id = test_case_id
        self._task_id = task_id

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

    def _mock_latency(self):
        """模拟延迟（秒）：case_config > meta 配置，默认 0"""
        for source in (self.case_config, self.meta):
            value = source.get('mock_latency')
            if value is not None:
                return float(value)
        return 0.0
