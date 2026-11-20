# -*- coding: utf-8 -*-
"""长期记忆存储端口（INT-2490，方案 §8.6 / §8.6.1）。

application 只依赖本抽象；文件树实现（``rg`` 检索、路径守卫、审批占位）
在 ``infrastructure/memory``，组合根注入。

所有方法都以 ``tenant_id`` / ``owner_id`` 显式入参：调用方必须传登录身份，
端口内不提供「按路径查找」的方法，从接口层就杜绝模型传入任意路径。
"""
from abc import ABC, abstractmethod
from typing import Optional, Sequence

from agent_service.domain.model.memory import (
    MemoryMetadata, MemorySearchResult, MemoryWriteProposal,
)
from agent_service.domain.enums import MemoryScope, MemorySection


class MemoryStorePort(ABC):
    """文件式记忆树读写端口。"""

    # ------------------------------------------------------------ 读

    @abstractmethod
    def search(self, *, tenant_id: str, owner_id: int, query: str,
               scope: MemoryScope, project_id: Optional[str] = None,
               limit: int = 10) -> MemorySearchResult:
        """按关键词检索；跨用户 / 跨租户恒为空，不回报「存在但无权」。"""

    @abstractmethod
    def summary(self, *, tenant_id: str, owner_id: int,
                max_tokens: int) -> str:
        """会话开始注入的摘要：只有用户偏好与项目规则，不超过 token 上限。"""

    @abstractmethod
    def metadata(self, *, tenant_id: str, owner_id: int) -> MemoryMetadata:
        """只读元数据（条数 / 更新时间），不返回正文。"""

    @abstractmethod
    def read_file(self, *, tenant_id: str, owner_id: int,
                  relative_path: str) -> str:
        """break-glass 读取（调用方必须已校验权限并留审计）。"""

    # ------------------------------------------------------------ 写（提案占位）

    @abstractmethod
    def create_proposal(self, *, tenant_id: str, owner_id: int,
                        section: MemorySection, content: str,
                        project_id: Optional[str] = None,
                        reason: str = '') -> MemoryWriteProposal:
        """生成提案（敏感扫描 + 路径守卫），**不落盘**。"""

    @abstractmethod
    def pending_proposals(self, *, tenant_id: str,
                          owner_id: int) -> Sequence[MemoryWriteProposal]:
        """待审批提案列表（不含正文预览）。"""

    @abstractmethod
    def approve(self, *, tenant_id: str, owner_id: int,
                approval_id: str) -> MemoryWriteProposal:
        """批准：按提案预演内容落盘；文件已被改动则判冲突。"""

    @abstractmethod
    def reject(self, *, tenant_id: str, owner_id: int,
               approval_id: str) -> MemoryWriteProposal:
        """拒绝：无任何文件副作用。"""


__all__ = ['MemoryStorePort']
