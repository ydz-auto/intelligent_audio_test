# -*- coding: utf-8 -*-
"""Agent 总开关 + 灰度白名单判定（INT-2456 总闸 / INT-2478 灰度扩展）。

**``AGENT_ENABLED`` 仍是唯一总闸**（缺省关闭），本模块只在它之上加按
租户 / 用户的灰度白名单，不新增第二个开关名、不改总闸语义。判定顺序：

1. 总闸关闭 → ``DISABLED``（与 INT-2456 完全一致）；
2. 总闸开启且两个白名单都为空 → ``ENABLED``（**向后兼容**：现役
   ``AGENT_ENABLED=true`` 的部署不会因为没配灰度而整体关闭）；
3. 总闸开启且配置了白名单 → 租户命中或用户命中才 ``ENABLED``，
   否则 ``NOT_IN_GRAY``。

对调用方而言 ``DISABLED`` 与 ``NOT_IN_GRAY`` **表现完全相同**：网关统一
返回既有 ``AGENT_DISABLED`` 机器码、不转发上游、不产生后台 run。区分只
用于运维排障与单元测试断言，不进响应体（否则非灰度用户可借此探测灰度
名单是否存在）。

配置（逗号 / 分号 / 空白分隔，空项忽略；每次调用重新求值，便于灰度切换）：

- ``AGENT_GRAY_TENANTS``：放行的租户 ID 列表，如 ``default``；
- ``AGENT_GRAY_USERS``：放行的用户 ID 列表，如 ``1,42``。

执行点仍在网关（``api_gateway/routes/agent_guard.py``）：agent_service 不
发布宿主端口，网关是唯一外部入口，在两处各判一次会形成「网关开了、服务
关了」的配置漂移（方案 07 §13-1 的既有裁定）。
"""
from enum import Enum
from typing import Iterable, Optional

#: 总闸环境变量名（唯一开关，不得改名）
ENV_AGENT_ENABLED = 'AGENT_ENABLED'
#: 灰度租户白名单环境变量名
ENV_AGENT_GRAY_TENANTS = 'AGENT_GRAY_TENANTS'
#: 灰度用户白名单环境变量名
ENV_AGENT_GRAY_USERS = 'AGENT_GRAY_USERS'

_GRAY_VALUE_SEPARATORS = ',;，；'


class AgentAccessDecision(str, Enum):
    """Agent 入口判定结果（枚举化，禁止调用方比较魔法字符串）。"""

    #: 放行
    ENABLED = 'enabled'
    #: 总闸关闭
    DISABLED = 'disabled'
    #: 总闸开启但未命中灰度白名单
    NOT_IN_GRAY = 'not_in_gray'

    @property
    def allowed(self) -> bool:
        return self is AgentAccessDecision.ENABLED


def parse_gray_values(raw: Optional[str]) -> frozenset:
    """把白名单环境变量解析成集合（逗号 / 分号 / 空白分隔，去空项）。

    非法内容不报错也不猜测：只做字符串等价匹配，避免启动期因为一条
    笔误把整个 Agent 入口拒死（fail-closed 由「配置了白名单」本身保证）。
    """
    if not raw:
        return frozenset()
    normalized = raw
    for separator in _GRAY_VALUE_SEPARATORS:
        normalized = normalized.replace(separator, ' ')
    return frozenset(item for item in normalized.split() if item)


def evaluate_agent_access(
    *, master_enabled: bool,
    tenant_id: Optional[str] = None,
    user_id: Optional[object] = None,
    gray_tenants: Iterable[str] = (),
    gray_users: Iterable[str] = (),
) -> AgentAccessDecision:
    """按总闸 + 租户/用户白名单给出入口判定。

    ``gray_tenants`` / ``gray_users`` 均为空 = 不做灰度（全员放行）；
    任一非空即进入灰度模式。用户 ID 为 ``0`` / ``None``（AUTH_MODE=off 的
    匿名空态）在没有显式列出时一律不命中。
    """
    if not master_enabled:
        return AgentAccessDecision.DISABLED
    tenants = frozenset(gray_tenants or ())
    users = frozenset(gray_users or ())
    if not tenants and not users:
        return AgentAccessDecision.ENABLED
    # 租户是网关下发的身份头（现为 AGENT_DEFAULT_TENANT_ID），用户是登录身份；
    # 两者是 OR 关系：按租户整片放行、或单独放行若干用户。
    if tenant_id and str(tenant_id) in tenants:
        return AgentAccessDecision.ENABLED
    if user_id and str(user_id) in users:
        return AgentAccessDecision.ENABLED
    return AgentAccessDecision.NOT_IN_GRAY


__all__ = [
    'ENV_AGENT_ENABLED',
    'ENV_AGENT_GRAY_TENANTS',
    'ENV_AGENT_GRAY_USERS',
    'AgentAccessDecision',
    'evaluate_agent_access',
    'parse_gray_values',
]
