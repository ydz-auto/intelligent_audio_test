# -*- coding: utf-8 -*-
"""适配器注册表键枚举（UC-1003 / 设计文档 04_类设计 §5.5）。

注册表 (protocol, vendor) 键的词汇表，注册与自动匹配共用同一套归一化
规则，杜绝魔法字符串。新增厂商：在此扩展 ``Vendor`` 枚举成员后由具体
适配器模块自注册；或在 API 配置（apis.adapter_class）显式指定类名，
无需扩枚举。
"""
from enum import Enum


class AdapterProtocol(str, Enum):
    """适配器传输协议（注册表 protocol 键）"""
    MOCK = 'mock'
    HTTP = 'http'
    SSE = 'sse'
    WEBSOCKET = 'websocket'


class Vendor(str, Enum):
    """注册表已登记厂商（注册表 vendor 键）"""
    MOCK = 'mock'
    VOICE_LLM = 'voice_llm'
    VOLC_AST = 'volc_ast'
    QWEN = 'qwen'


# 配置中的历史别名 → 注册表 vendor 键
VENDOR_ALIASES = {
    'volc': Vendor.VOLC_AST.value,
    'qwen3': Vendor.QWEN.value,
}

# 未指定 vendor 时的协议级兜底注册键（http/sse/mock 各自回退到此）
DEFAULT_REGISTRY_VENDOR = 'default'


def normalize_protocol(protocol) -> str:
    """协议值归一化（枚举取值、大小写/空白容错），未指定返回空串"""
    if isinstance(protocol, Enum):
        protocol = protocol.value
    return str(protocol or '').strip().lower()


def normalize_vendor(vendor) -> str:
    """vendor 值归一化（枚举取值、别名折叠、大小写/空白容错），未指定返回空串"""
    if isinstance(vendor, Enum):
        vendor = vendor.value
    v = str(vendor or '').strip().lower()
    return VENDOR_ALIASES.get(v, v)
