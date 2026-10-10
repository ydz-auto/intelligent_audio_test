# -*- coding: utf-8 -*-
"""音频入参归一（INT-71）：路径 / 存储引用 / 字节 统一解析为字节。

执行侧经 SendRoundRequest.input_data 下发音频引用（proto 约定：
text 内容 或 audio_path），此处负责在 adapter 侧解析为真实字节：
- bytes / bytearray 原样返回
- local:// / oss:// 存储引用经 shared.infrastructure.storage 统一存储层读取
- 其余按本地文件路径读取

读取失败抛异常，由调用方收敛为轮次失败——禁止静默空音频发送。
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
