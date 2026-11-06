# -*- coding: utf-8 -*-
"""跨服务 ID 类型归一。

proto string 契约边界（evaluation_service.proto 的 task_id/result_id 均为
string）与下游 protobuf int 字段之间统一归一；归一失败必须抛 ValueError
由调用方透出，禁止静默吞成空结果掩盖故障（INT-115）。
"""


def to_int_id(field: str, value) -> int:
    """把跨服务传入的 ID 归一为 int；空值/非数字抛 ValueError。"""
    if value is None or value == '':
        raise ValueError(f'{field} 不能为空')
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f'{field} 无法转换为整数: {value!r}')
