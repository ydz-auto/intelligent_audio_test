# -*- coding: utf-8 -*-
"""大工具结果外置存储端口（§8.2 L1_TRIM）。

上下文压缩把超过阈值的工具结果落对象存储，模型侧只保留「摘要 + 关键字段 +
artifact 引用」。端口在 domain 定义，infrastructure 复用仓库的 OSS 客户端实现。
"""
from abc import ABC, abstractmethod


class ArtifactStore(ABC):
    """按 run 保存大文本产物，返回可回放的 URI。"""

    @abstractmethod
    def put(self, content: str, *, run_id: str, name: str,
            content_type: str = 'application/json') -> str:
        """保存内容并返回 URI（如 ``oss://archives/agent-context/...``）。"""


class NullArtifactStore(ArtifactStore):
    """未配置对象存储时的空实现：不落盘，调用方降级为直接截断。"""

    def put(self, content: str, *, run_id: str, name: str,
            content_type: str = 'application/json') -> str:
        raise RuntimeError('未配置对象存储，无法外置大工具结果')


__all__ = ['ArtifactStore', 'NullArtifactStore']
