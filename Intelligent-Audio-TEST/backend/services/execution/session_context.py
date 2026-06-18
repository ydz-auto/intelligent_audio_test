# -*- coding: utf-8 -*-
"""
API 多轮会话上下文管理器

管理 API 多轮会话的生命周期：
- 创建会话
- 维护对话上下文
- 收集轮次结果
- 销毁会话
"""

import time
import uuid
from typing import Optional


class SessionContext:
    """API 多轮会话上下文管理器"""
    
    def __init__(
        self,
        session_id: Optional[str] = None,
        config: Optional[dict] = None
    ):
        """
        初始化会话
        
        Args:
            session_id: 会话唯一标识（UUID），如果未提供则自动生成
            config: 会话配置
                - session_timeout: int — 单轮超时时间（秒），默认 60
                - context_mode: str — 上下文模式：'full' | 'sliding_window'
                - max_history_rounds: int — 滑动窗口模式下保留的历史轮次数
        """
        if session_id is None:
            session_id = str(uuid.uuid4())
        
        if config is None:
            config = {}
        
        self.session_id = session_id
        self.session_timeout = config.get('session_timeout', 60)
        self.context_mode = config.get('context_mode', 'full')
        self.max_history_rounds = config.get('max_history_rounds', 5)
        
        # 内部状态
        self._history: list[dict] = []  # 对话历史
        self._round_results: list[dict] = []  # 轮次结果
        self._created_at = time.time()
        self._is_active = True

    @property
    def is_active(self) -> bool:
        """会话是否处于活跃状态"""
        return self._is_active

    def add_history(self, round_number: int, input_text: str, output_text: str):
        """
        添加一轮对话历史
        
        Args:
            round_number: 轮次编号
            input_text: 输入文本
            output_text: 输出文本
        """
        self._history.append({
            'round': round_number,
            'input': input_text,
            'output': output_text,
            'timestamp': time.time()
        })

    def get_context(self) -> list[dict]:
        """
        获取当前上下文历史
        
        根据 context_mode 返回全量或滑动窗口的历史：
        - 'full': 返回全部历史
        - 'sliding_window': 返回最近 N 轮历史
        
        Returns:
            list[dict]: 对话历史列表
        """
        if self.context_mode == 'sliding_window':
            return self._history[-self.max_history_rounds:]
        return self._history  # 'full' 模式返回全部

    def get_context_for_request(self) -> list[dict]:
        """
        获取用于请求的上下文格式
        
        Returns:
            list[dict]: 简化的上下文格式 [{role, content}, ...]
        """
        context = self.get_context()
        result = []
        for h in context:
            # 用户输入
            result.append({
                'role': 'user',
                'content': h.get('input', '')
            })
            # 系统输出
            result.append({
                'role': 'assistant',
                'content': h.get('output', '')
            })
        return result

    def add_round_result(self, round_result: dict):
        """
        记录本轮结果
        
        Args:
            round_result: 轮次结果字典
        """
        self._round_results.append(round_result)

    def get_round_results(self) -> list[dict]:
        """
        获取所有轮次结果
        
        Returns:
            list[dict]: 轮次结果列表
        """
        return self._round_results

    def get_summary(self) -> dict:
        """
        获取会话摘要
        
        Returns:
            dict: 会话摘要信息
        """
        total_latency = sum(r.get('latency', 0) for r in self._round_results)
        return {
            'session_id': self.session_id,
            'round_count': len(self._round_results),
            'total_latency': total_latency,
            'context_mode': self.context_mode,
            'history_count': len(self._history),
            'error': None,
            'rounds': self._round_results,
            'duration': time.time() - self._created_at
        }

    def destroy(self):
        """销毁会话，释放资源"""
        self._is_active = False
        self._history.clear()

    def __repr__(self):
        return (
            f"SessionContext(id={self.session_id}, "
            f"rounds={len(self._round_results)}, "
            f"history={len(self._history)}, "
            f"active={self._is_active})"
        )
