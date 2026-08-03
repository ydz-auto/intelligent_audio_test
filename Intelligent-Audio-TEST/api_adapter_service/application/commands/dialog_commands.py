# -*- coding: utf-8 -*-
"""对话相关命令定义。"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CreateDialogTaskCommand:
    """创建/执行一轮对话任务命令。

    封装单轮多轮对话所需的全部输入参数。
    """
    session_id: str
    round: int = 0
    total_rounds: int = 1
    task_type: str = 'voice_llm'
    vendor: str = 'mock'

    # 输入
    input_type: str = 'text'
    input_text: str = ''
    input_audio_path: Optional[str] = None

    # 上下文 / 算法参数
    context: List[Dict[str, Any]] = field(default_factory=list)
    context_for_request: List[Dict[str, Any]] = field(default_factory=list)
    algorithm_params: List[Any] = field(default_factory=list)
    case_algorithm_params: Dict[str, Any] = field(default_factory=dict)

    # 翻译方向
    translation_direction: Optional[str] = None
    source_lang: str = 'zh'
    target_lang: str = 'en'

    # Vendor 配置覆盖
    vendor_config_override: Dict[str, Any] = field(default_factory=dict)

    @property
    def actual_input(self) -> str:
        """实际输入数据（音频优先）。"""
        if self.input_type == 'audio' and self.input_audio_path:
            return self.input_audio_path
        return self.input_text

    @property
    def display_input(self) -> str:
        """用于存储到 session 的展示文本。"""
        if self.input_type == 'audio' and self.input_audio_path:
            return f'[audio:{self.input_audio_path}]'
        return self.input_text

    @classmethod
    def from_request(cls, data: dict) -> 'CreateDialogTaskCommand':
        """从 routes/api.py 的请求 dict 构建命令。"""
        session_id = data.get('session_id')
        if not session_id:
            raise ValueError('session_id is required')

        input_data = data.get('input', {}) or {}
        input_type = input_data.get('type', 'text')
        input_text = input_data.get('text', '')
        input_audio_path = input_data.get('audio_path')

        translation_direction = data.get('translation_direction')
        source_lang, target_lang = 'zh', 'en'
        if translation_direction:
            if '2en' in translation_direction:
                source_lang = translation_direction.split('2')[0] or 'zh'
                target_lang = 'en'
            elif '2zh' in translation_direction:
                source_lang = translation_direction.split('2')[0] or 'en'
                target_lang = 'zh'

        return cls(
            session_id=session_id,
            round=data.get('round', 0),
            total_rounds=data.get('total_rounds', 1),
            task_type=data.get('task_type', 'voice_llm'),
            vendor=data.get('vendor', 'mock'),
            input_type=input_type,
            input_text=input_text,
            input_audio_path=input_audio_path,
            context=data.get('context', []) or [],
            context_for_request=data.get('context_for_request', []) or [],
            algorithm_params=data.get('algorithm_params', []) or [],
            case_algorithm_params=data.get('case_algorithm_params', {}) or {},
            translation_direction=translation_direction,
            source_lang=source_lang,
            target_lang=target_lang,
            vendor_config_override=data.get('vendor_config', {}) or {},
        )


@dataclass
class CloseSessionCommand:
    """关闭/销毁会话命令。"""
    session_id: str
