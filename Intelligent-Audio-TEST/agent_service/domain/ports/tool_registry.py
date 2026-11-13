# -*- coding: utf-8 -*-
"""工具注册表与回源传输端口（INT-2453，方案 §6.1 / §6.2 / §6.3）。

分层约定（§12.1）：application 只依赖 domain 端口，具体共享注册表读取
（``shared/agent_tools``）与 HTTP 回源在 infrastructure 实现，由组合根注入。
domain 零依赖（仅标准库 + 本包类型）。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence, Tuple

from agent_service.domain.enums import ToolRisk
from agent_service.domain.ports.tool_gateway import ToolDescriptor


@dataclass(frozen=True)
class ToolTransportResult:
    """一次工具回源结果（status=0 表示网络层失败）。"""

    status: int
    payload: Any = None
    text: str = ''
    error: str = ''

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


class ToolRegistryPort(ABC):
    """工具注册表读取端口（意图工具 + 长尾 MCP 工具）。"""

    @abstractmethod
    def descriptors(self) -> Sequence[ToolDescriptor]:
        """全部意图工具描述（含预留项，``enabled=False``）。"""

    @abstractmethod
    def describe(self, name: str) -> Optional[ToolDescriptor]:
        """按名取意图工具描述；非意图工具返回 None。"""

    @abstractmethod
    def permissions_of(self, name: str) -> Optional[Tuple[str, ...]]:
        """工具所需权限（OR 语义）；未知工具返回 None。"""

    @abstractmethod
    def risk_of(self, name: str) -> Optional[ToolRisk]:
        """工具风险；未知工具返回 None。"""

    @abstractmethod
    def validate(self, name: str, arguments: Any) -> Optional[str]:
        """参数 Schema 校验；返回错误文本或 None。"""

    @abstractmethod
    def resolve_rest(self, name: str, arguments: Dict[str, Any]
                     ) -> Tuple[Optional[dict], Optional[dict], Optional[str]]:
        """解析为 ``(目标工具定义, 合并参数, 错误文本)``（只读 REST 映射）。"""

    @abstractmethod
    def search(self, query: str, permissions: Sequence[str],
               limit: int) -> dict:
        """tool_search：按关键词返回子集 Schema（权限过滤）。"""

    @abstractmethod
    def platform_contract(self, query: str, section: str) -> dict:
        """platform_contract：平台口径事实查询。"""

    @abstractmethod
    def diagnosis_log_levels(self) -> Tuple[str, ...]:
        """失败诊断关注的日志级别（与诊断聚合模块同一事实源）。"""

    @abstractmethod
    def diagnosis_sample_limit(self) -> int:
        """失败诊断默认取样的日志行数（同一事实源，禁止应用层写死）。"""

    @abstractmethod
    def action_arguments(self, name: str, action: str
                         ) -> Optional[Tuple[str, ...]]:
        """动作级参数白名单；没有白名单的工具 / 动作返回 None。"""

    @abstractmethod
    def diagnose_task(self, sources: Dict[str, Any]) -> Dict[str, Any]:
        """任务失败诊断聚合（纯函数；输入是已取回的真实接口数据）。"""

    @abstractmethod
    def diagnose_logs(self, sources: Dict[str, Any]) -> Dict[str, Any]:
        """日志诊断聚合（纯函数；输入是已取回的真实接口数据）。"""


class ToolTransportPort(ABC):
    """只读工具回源传输端口（网关 REST）。"""

    @abstractmethod
    def call(self, tool: dict, arguments: Dict[str, Any], *,
             authorization: Optional[str],
             user_id: int, tenant_id: str,
             permissions: Sequence[str]) -> ToolTransportResult:
        """执行一次 REST 调用。网络层失败返回 status=0，不抛异常。"""


class RunCredentialPort(ABC):
    """run 级调用方凭证读取端口（进程内暂存，不落库）。"""

    @abstractmethod
    def get(self, run_id: str) -> Optional[str]:
        """返回该 run 的 Authorization 头；不存在 / 过期返回 None。"""


__all__ = [
    'RunCredentialPort', 'ToolRegistryPort', 'ToolTransportPort',
    'ToolTransportResult',
]
