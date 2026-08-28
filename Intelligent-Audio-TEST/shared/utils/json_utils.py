"""共享 JSON 工具函数"""
import json
from typing import Any


def deserialize_algorithm_result(data: Any) -> dict:
    """反序列化 algorithm_result，兼容双重序列化的历史数据。

    历史数据中 algorithm_result 可能被存为 JSON 字符串（甚至多层嵌套），
    此函数循环反序列化直到得到 dict。
    """
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (json.JSONDecodeError, TypeError, ValueError):
            return {}
    if not isinstance(data, dict):
        return {}
    return data


def safe_json_loads(data: Any, default: Any = None) -> Any:
    """安全 json.loads，失败返回默认值"""
    if default is None:
        default = {}
    if isinstance(data, (dict, list)):
        return data
    if isinstance(data, str):
        try:
            return json.loads(data)
        except (json.JSONDecodeError, TypeError, ValueError):
            return default
    return default
