# -*- coding: utf-8 -*-
"""Adapter 抽象基类

所有协议 adapter 继承此基类,统一 send_request 接口。
内部消化协议差异(WebSocket/HTTP/SSE/gRPC),对外暴露同步接口。
"""
from abc import ABC, abstractmethod
from typing import Optional
import time

from api_adapter_service.utils.logger import logger


class BaseAdapter(ABC):
    """被测算法适配器基类"""

    def __init__(self, vendor_config: dict):
        self.vendor_config = vendor_config
        self.connected = False

    @abstractmethod
    def send_request(
        self,
        task_id: str,
        session_id: str,
        input_type: str,
        input_data,
        source_lang: str = 'zh',
        target_lang: str = 'en',
        context: Optional[list] = None,
        context_for_request: Optional[list] = None,
        algorithm_params: Optional[list] = None,
        case_algorithm_params: Optional[dict] = None,
        translation_direction: Optional[str] = None,
        round_number: int = 0,
        total_rounds: int = 1,
        task_type: str = 'voice_llm',
    ) -> dict:
        """发送请求,返回统一格式结果

        Returns:
            {
                'asr_text': str,
                'trans_text': str,
                'output': str,
                'session_id': str,
                'latency': float,
                'raw_response': dict,
            }
        """
        pass

    def destroy_session(self, session_id: str):
        """清理会话资源(默认空实现)"""
        pass
