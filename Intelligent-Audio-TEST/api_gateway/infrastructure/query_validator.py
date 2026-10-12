# -*- coding: utf-8 -*-
"""ACL 边界 query 参数类型校验与清洗（INT-165）。

列表端点的 page/per_page/api_id 等 query 参数原以散落的 int() 强转解析，
非法输入（如 ?per_page=abc）触发未捕获 ValueError → 500。本模块提供
统一的声明式清洗：合法值 int 化并钳制到声明区间，非法值抛
QueryParamValidationError，由服务层转 400 + INVALID_TYPE 结构化错误。
"""
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence


class QueryParamValidationError(ValueError):
    """query 参数类型非法（ACL 边界清洗失败）。

    继承 ValueError 以兼容上游既有的宽泛 except ValueError；
    param/value 供服务层组装结构化错误 detail。
    """

    def __init__(self, message: str, param: str, value: Any = None):
        super().__init__(message)
        self.param = param
        self.value = value


@dataclass(frozen=True)
class IntParamRule:
    """整型 query 参数清洗规则：key/缺省值/钳制区间集中声明，拒绝散落魔法数字。"""
    key: str
    default: Optional[int] = None
    min_value: Optional[int] = None
    max_value: Optional[int] = None


def parse_int_args(args: Any, rules: Sequence[IntParamRule]) -> Dict[str, Optional[int]]:
    """按规则清洗一组整型 query 参数。

    - 缺省或空串 → default（与原 ``int(args.get(key, d) or d)`` 的空值语义一致）
    - 非整数 → QueryParamValidationError（服务层转 400）
    - 越界 → 钳制到 [min_value, max_value]

    :param args: 任何提供 ``.get(key)`` 的 query 集合（request.args / dict）
    :return: ``{rule.key: 清洗后的 int 或 default}``
    """
    parsed: Dict[str, Optional[int]] = {}
    for rule in rules:
        raw = args.get(rule.key)
        if raw is None or raw == '':
            parsed[rule.key] = rule.default
            continue
        try:
            value = int(raw)
        except (ValueError, TypeError):
            raise QueryParamValidationError(
                f"参数 {rule.key} 非法：期望整数，实际值 '{raw}'",
                param=rule.key, value=raw,
            ) from None
        if rule.min_value is not None and value < rule.min_value:
            value = rule.min_value
        if rule.max_value is not None and value > rule.max_value:
            value = rule.max_value
        parsed[rule.key] = value
    return parsed
