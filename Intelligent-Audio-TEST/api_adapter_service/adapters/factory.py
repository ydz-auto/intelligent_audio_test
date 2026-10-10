# -*- coding: utf-8 -*-
"""Adapter factory — 根据协议/vendor 选择对应 adapter"""

from api_adapter_service.adapters.base import BaseAdapter
from api_adapter_service.adapters.http_adapter import HttpAdapter
from api_adapter_service.adapters.mock_adapter import MockDialogAdapter
from api_adapter_service.adapters.sse_adapter import SseAdapter
from api_adapter_service.utils.logger import logger


def select_adapter(vendor: str, vendor_config: dict,
                   is_dialog: bool = False) -> BaseAdapter:
    """选择 adapter

    Args:
        vendor: vendor 标识(如 voice_llm / volc_ast / qwen / openai / mock)
        vendor_config: vendor 配置 dict
        is_dialog: 是否对话模式

    Returns:
        BaseAdapter 实例
    """
    protocol = vendor_config.get('protocol', '')

    # Mock
    if vendor == 'mock' or protocol == 'mock':
        logger.info('Using MockDialogAdapter')
        return MockDialogAdapter(vendor_config)

    # HTTP (voice_llm)
    if protocol == 'http':
        logger.info(f'Using HttpAdapter for vendor={vendor}')
        return HttpAdapter(vendor_config)

    # SSE (ChatGPT / OpenAI)
    if protocol == 'sse':
        logger.info(f'Using SseAdapter for vendor={vendor}')
        return SseAdapter(vendor_config)

    # WebSocket + Protobuf (火山 AST)
    if protocol == 'websocket' and vendor in ('volc_ast', 'volc'):
        logger.info(f'Using VolcAstAdapter for vendor={vendor}')
        from api_adapter_service.adapters.volc_ast_adapter import VolcAstAdapter
        return VolcAstAdapter(vendor_config)

    # WebSocket + JSON (Qwen3)
    if protocol == 'websocket' and vendor in ('qwen', 'qwen3'):
        logger.info(f'Using QwenAdapter for vendor={vendor}')
        from api_adapter_service.adapters.qwen_adapter import QwenAdapter
        return QwenAdapter(vendor_config)

    # Default
    logger.warning(
        f'Unknown vendor={vendor}, protocol={protocol}, '
        f'defaulting to HttpAdapter'
    )
    return HttpAdapter(vendor_config)
