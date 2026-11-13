# -*- coding: utf-8 -*-
"""写意图工具的共用解析层（INT-2468，M2 用例 / 标签 / 任务域）。

三个域写工具（``testcase_write`` / ``tag_group_manage`` / ``task_run``）都是
「一个意图工具 → 多个动作 → 多个既有 REST 写接口」的形态，动作表、参数白名单、
条件必填、动作级权限与动作级风险的判定口径完全一致，集中在本模块：

- ``WriteAction``：一个动作的目标工具名 + 允许参数 + 必填参数 + 默认权限 / 风险；
- ``resolve_domain``：按 ``action`` 取动作定义 → 拒绝动作不支持的参数
  （网关写接口的 pydantic 基类多为 ``extra='ignore'`` 或直接忽略多余字段，
  放过去会让模型以为「参数生效了」）→ 校验必填 → 交给 ``prepare`` 做域内
  归一（注入 body / 展开批量载荷）→ 返回可直接回源的 ``(工具项, 合并参数)``。

**只做映射，不复制 Schema**：目标工具项一律取自 ``mcp_registry``（对外 207 项
的单源），本包只补网关有路由但 MCP 表未登记的内部写入口（例如用例批量接口
``POST /api/v1/testcases/batch``）。

风险口径：工具级风险由 ``intent_tools`` 声明（与方案 §6.1 表一致，均为 WRITE），
**删除类动作**在动作层升为 ``DESTRUCTIVE``（``WriteAction.risk``），由
``intent_tools.risk_for`` 解析后在审批单 / 审计里如实记录；审批门禁对
WRITE / DESTRUCTIVE 一视同仁（``ToolRisk.requires_approval``），升档只影响
展示与审计，不改变「先提案、后执行」。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Tuple

from shared.agent_tools.mcp_registry import get_tool

# ------------------------------------------------------------------ 风险

RISK_WRITE = 'WRITE'
RISK_DESTRUCTIVE = 'DESTRUCTIVE'

# 空值判定：必填参数给了空串 / 空数组 / 空对象都算缺参（不是「合法空值」）
_EMPTY_VALUES = (None, '', [], {})


@dataclass(frozen=True)
class WriteAction:
    """一个写动作的映射定义。

    - ``tool``：目标工具名（``mcp_registry`` 项，或 ``tools`` 里的内部写入口）；
    - ``params``：动作允许的参数（不含 ``action`` 本身）；
    - ``required``：动作必填参数（Schema 无法表达的静态必填）；
    - ``permissions``：动作所需权限码（OR 语义，与网关路由 ``require_permission``
      一致）；
    - ``risk``：动作级风险；缺省沿用工具级 ``WRITE``，删除 / 改名类动作显式
      标 ``DESTRUCTIVE``。
    """

    tool: str
    params: Tuple[str, ...] = ()
    required: Tuple[str, ...] = ()
    permissions: Tuple[str, ...] = ()
    risk: str = RISK_WRITE


# ``prepare`` 钩子：动作级归一后的合并参数；返回错误文本表示参数不合法。
PrepareHook = Callable[[str, Dict[str, Any]], Optional[str]]


def _missing(merged: Mapping[str, Any], names: Sequence[str]) -> Tuple[str, ...]:
    return tuple(name for name in names if merged.get(name) in _EMPTY_VALUES)


def resolve_domain(actions: Mapping[str, WriteAction],
                   arguments: Optional[Mapping[str, Any]],
                   *, label: str,
                   tools: Optional[Mapping[str, dict]] = None,
                   prepare: Optional[PrepareHook] = None
                   ) -> Tuple[Optional[dict], Optional[Dict[str, Any]],
                              Optional[str]]:
    """把意图写动作解析成 ``(目标工具项, 合并参数, 错误文本)``。

    - ``action`` 必须是动作表里的值（错误文案列出全部可选动作）；
    - 动作不支持的参数直接拒绝：网关写接口对多余字段不报错，静默丢弃会让模型
      把「没生效」当成「已经改了」；
    - 必填参数为空串 / 空数组 / 空对象同样视为缺参；
    - ``prepare`` 只做域内归一（注入 body、展开批量载荷），不访问网络、不落库。
    """
    values = dict(arguments or {})
    action = values.get('action')
    spec = actions.get(str(action)) if isinstance(action, str) else None
    if spec is None:
        return None, None, (
            f'action 取值必须是 {"/".join(actions)} 之一')

    merged = {key: value for key, value in values.items()
              if key != 'action' and value is not None}
    unknown = sorted(set(merged) - set(spec.params))
    if unknown:
        return None, None, (
            f'action={action} 不支持参数：{"、".join(unknown)}'
            f'（允许的参数：{"/".join(spec.params) or "无"}）')
    missing = _missing(merged, spec.required)
    if missing:
        return None, None, f'action={action} 缺少必填参数：{"、".join(missing)}'

    if prepare is not None:
        error = prepare(action, merged)
        if error:
            return None, None, error

    tool = (tools or {}).get(spec.tool) or get_tool(spec.tool)
    if tool is None:  # pragma: no cover - 动作表内部一致性防御
        return None, None, f'工具映射失效：{label}.{action} → {spec.tool}'
    return tool, merged, None


def require_text(value: Any, field_name: str,
                 action: Optional[str] = None) -> Optional[str]:
    """正文类参数必须是非空字符串（名称 / 标签名 / 标签分类名等）。"""
    if isinstance(value, str) and value.strip():
        return None
    prefix = f'action={action} 的' if action else ''
    return f'{prefix}参数 {field_name} 必须是非空字符串'


def require_body(merged: Mapping[str, Any], *, action: str,
                 required_fields: Sequence[str] = ()) -> Optional[str]:
    """``body`` 必须是对象；``required_fields`` 里的字段必须非空。"""
    body = merged.get('body')
    if not isinstance(body, dict) or not body:
        return f'action={action} 的 body 必须是非空对象'
    for name in required_fields:
        error = require_text(body.get(name), f'body.{name}', action)
        if error:
            return error
    return None


def require_string_list(value: Any, field_name: str,
                        action: Optional[str] = None) -> Optional[str]:
    """字符串数组参数：非空、逐项非空字符串、去重后保持数量一致。"""
    if not isinstance(value, list) or not value:
        return f'参数 {field_name} 必须是非空字符串数组'
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            return (f'参数 {field_name}[{index}] 必须是非空字符串')
    if len(set(value)) != len(value):
        return f'参数 {field_name} 含重复项'
    return None


def require_positive_int(value: Any, field_name: str,
                         action: Optional[str] = None) -> Optional[str]:
    """正整数 ID：排除 bool / 浮点 / 字符串（ID 类型错了网关会 422）。"""
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return None
    return f'参数 {field_name} 必须是正整数'


def require_identifier(value: Any, field_name: str,
                       action: Optional[str] = None) -> Optional[str]:
    """字符串标识（用例 ID / 分组 ID 都是 UUID 字符串）。"""
    return require_text(value, field_name, action)


__all__ = [
    'PrepareHook', 'RISK_DESTRUCTIVE', 'RISK_WRITE', 'WriteAction',
    'require_body', 'require_identifier', 'require_positive_int',
    'require_string_list', 'require_text', 'resolve_domain',
]
