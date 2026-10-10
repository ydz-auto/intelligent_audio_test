# -*- coding: utf-8 -*-
"""单轮任务命令定义（INT-106）。

单轮（非 session）API 用例执行链的标准被测协议（见
tests/integration/test_task_execute_real_chain.py 契约）：异步建任务 →
轮询状态 → 查询最终结果。本命令承载建任务请求的平铺参数。
"""

from dataclasses import dataclass


@dataclass
class CreateSingleTurnTaskCommand:
    """创建单轮（非会话）任务命令。

    请求体为 api_test_service 单轮执行器按字段映射平铺的参数：
    audio_path / audio_url / vendor / max_process / max_timeout 等。
    """
    audio_path: str = ''
    vendor: str = 'mock'

    @classmethod
    def from_request(cls, data: dict) -> 'CreateSingleTurnTaskCommand':
        if not isinstance(data, dict) or not data:
            raise ValueError('request body is required')
        audio_path = data.get('audio_path') or data.get('audio_url') or ''
        if not audio_path:
            raise ValueError('audio_path is required')
        return cls(
            audio_path=str(audio_path),
            vendor=str(data.get('vendor') or 'mock'),
        )
