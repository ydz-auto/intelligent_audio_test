# -*- coding: utf-8 -*-
"""第三方评估出站端口（Domain 层端口接口）+ 请求/结果值对象。

B→C 第三方评估的统一抽象 ThirdPartyEvalPort（设计文档 09_跨区网络传输方案 §4.3）：
具体适配器（multipart / feature_extract / presigned_url）在 Infrastructure ACL 层实现，
Domain 层只依赖本端口，不感知 HTTP 协议细节。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class ThirdPartyEvalFile:
    """EVAL_REQUEST 中的文件部件（字段名 + 文件名 + 内容字节 + Content-Type）。"""
    name: str
    filename: str
    content: bytes
    content_type: str = 'application/octet-stream'


@dataclass
class ThirdPartyEvalRequest:
    """第三方评估请求值对象 — EVAL_REQUEST 打包产物（8 步流程之①请求打包）。"""
    transfer_id: str
    form_fields: Dict = field(default_factory=dict)
    files: Dict[str, ThirdPartyEvalFile] = field(default_factory=dict)
    eval_params: Dict = field(default_factory=dict)
    src_zone: str = 'B'
    dst_zone: str = 'C'

    @property
    def files_bytes(self) -> Dict[str, tuple]:
        """requests multipart files 形态: {name: (filename, bytes, content_type)}。"""
        return {
            f.name: (f.filename, f.content, f.content_type)
            for f in self.files.values()
        }


@dataclass
class ThirdPartyEvalResult:
    """第三方评估结果值对象 — EVAL_RESULT（C 同步响应回传）。"""
    ok: bool
    transfer_id: str
    data: Optional[Dict] = None
    error: Optional[str] = None
    status_code: Optional[int] = None


class ThirdPartyEvalPort(ABC):
    """B→C 第三方评估端口（策略形态由配置选择，运行时可切换）。"""

    @abstractmethod
    def evaluate(self, request: ThirdPartyEvalRequest) -> ThirdPartyEvalResult:
        """执行一次第三方评估调用，返回 EVAL_RESULT 值对象（不抛网络异常，错误进 result）。"""
