# -*- coding: utf-8 -*-
"""HTTP + SSE 流式 adapter

支持 OpenAI ChatGPT 等 HTTP + Server-Sent Events 流式 API。
"""
import json
import time
import requests
from typing import Optional

from api_adapter_service.adapters.base import BaseAdapter
from api_adapter_service.utils.logger import logger


class SseAdapter(BaseAdapter):
    """HTTP + SSE 流式 adapter

    vendor_config 需要:
    - base_url: API 基础 URL
    - api_key: Bearer token
    - model: 模型名(如 gpt-4o)
    - endpoint: 聊天端点(默认 /v1/chat/completions)
    """

    def __init__(self, vendor_config: dict):
        super().__init__(vendor_config)
        self.base_url = vendor_config.get('base_url', '')
        self.api_key = vendor_config.get('api_key', '')
        self.model = vendor_config.get('model', 'gpt-4o')
        self.endpoint = vendor_config.get('endpoint', '/v1/chat/completions')
        self.timeout = vendor_config.get('timeout', 60)

    def send_request(self, task_id, session_id, input_type, input_data,
                     source_lang='zh', target_lang='en',
                     context=None, context_for_request=None, **kwargs) -> dict:
        """发送 SSE 流式请求"""
        start_time = time.time()
        try:
            url = f'{self.base_url.rstrip("/")}{self.endpoint}'
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json',
            }

            messages = []
            if context_for_request:
                messages.extend(context_for_request)
            elif context:
                messages.extend(context)
            messages.append({
                'role': 'user',
                'content': input_data if input_type == 'text' else '[audio]',
            })

            payload = {
                'model': self.model,
                'messages': messages,
                'stream': True,
            }

            # SSE 流式接收
            full_text = ''
            response = requests.post(
                url, json=payload, headers=headers,
                timeout=self.timeout, stream=True,
            )
            response.raise_for_status()

            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        data_str = line_str[6:]
                        if data_str == '[DONE]':
                            break
                        chunk = json.loads(data_str)
                        delta = chunk.get('choices', [{}])[0].get('delta', {})
                        content = delta.get('content', '')
                        if content:
                            full_text += content

            latency = time.time() - start_time
            logger.info(
                f'SseAdapter: task={task_id}, session={session_id}, '
                f'model={self.model}, latency={round(latency, 3)}s'
            )
            return {
                'asr_text': full_text,
                'trans_text': full_text,
                'output': full_text,
                'session_id': session_id,
                'latency': round(latency, 3),
                'raw_response': {'model': self.model, 'stream': True},
            }
        except Exception as e:
            logger.error(f'SseAdapter error: {e}', exc_info=True)
            return {
                'asr_text': '', 'trans_text': '', 'output': '',
                'session_id': session_id,
                'latency': round(time.time() - start_time, 3),
                'raw_response': {'error': str(e)},
            }
