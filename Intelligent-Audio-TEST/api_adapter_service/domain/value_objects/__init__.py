# -*- coding: utf-8 -*-
"""值对象：不可变领域对象。

追加导出 adapter_config 模块的 DialogContext。
adapter_config.VendorConfig 字段偏向 HTTP 适配场景，与下方 frozen
VendorConfig（供 AdapterSelector 使用）语义不同，故不在此顶层 re-export，
需通过 ``from api_adapter_service.domain.value_objects.adapter_config import VendorConfig``
显式访问，避免遮蔽既有符号。
"""

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass(frozen=True)
class TranslationDirection:
    """翻译方向值对象。"""
    source_lang: str = 'zh'
    target_lang: str = 'en'

    def __post_init__(self):
        if not self.source_lang or not self.target_lang:
            raise ValueError('source_lang and target_lang must not be empty')

    def is_same_direction(self) -> bool:
        return self.source_lang == self.target_lang

    def reverse(self) -> 'TranslationDirection':
        return TranslationDirection(
            source_lang=self.target_lang,
            target_lang=self.source_lang,
        )


@dataclass(frozen=True)
class VendorConfig:
    """Vendor 配置值对象（不可变）。"""
    vendor: str
    protocol: str
    config: Dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)


@dataclass(frozen=True)
class RoundResult:
    """单轮对话结果值对象。"""
    asr_text: str = ''
    trans_text: str = ''
    output: str = ''
    session_id: str = ''
    latency: float = 0.0
    raw_response: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            'asr_text': self.asr_text,
            'trans_text': self.trans_text,
            'output': self.output,
            'session_id': self.session_id,
            'latency': self.latency,
            'raw_response': self.raw_response,
        }


# 追加 re-export：HTTP 适配场景的对话上下文（不与 frozen VendorConfig 冲突）
from api_adapter_service.domain.value_objects.adapter_config import DialogContext  # noqa: E402,F401
