# -*- coding: utf-8 -*-
"""音频入参归一（INT-71，api_adapter_service 迁移）：路径 / 存储引用 / 字节统一解析为字节。

执行侧（api_session_executor）经混音渲染产物引用下发音频（storage-ref/路径），
此处负责在内嵌适配器侧解析为真实字节：
- bytes / bytearray 原样返回
- local:// / oss:// 存储引用经 shared.infrastructure.storage 统一存储层读取
- 其余按本地文件路径读取

读取失败抛异常，由调用方收敛为轮次失败——禁止静默空音频发送（INT-71 语义保留）。
"""

_SCHEMES = ('local://', 'oss://')


def resolve_audio_bytes(audio_source) -> bytes:
    """将音频入参解析为 bytes；无效输入或读取失败抛 ValueError/OSError。"""
    if isinstance(audio_source, (bytes, bytearray)):
        return bytes(audio_source)
    if not isinstance(audio_source, str) or not audio_source:
        raise ValueError(f'音频输入无效: {type(audio_source).__name__}')
    if audio_source.startswith(_SCHEMES):
        from shared.infrastructure.storage import storage
        return storage.load_bytes(audio_source)
    with open(audio_source, 'rb') as f:
        return f.read()
