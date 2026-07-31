"""
命名转换请求工具 —— FastAPI 兼容版

原 Flask NamingRequest 继承 Flask.Request，在 FastAPI 下不再适用。
改为纯函数工具，对 dict 做键名转换。
"""
import re
from pydantic.alias_generators import to_snake

_SNAKE_LIKE_KEY_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")


def normalize_keys_to_snake(data, depth=0):
    if isinstance(data, list):
        result = []
        for i, item in enumerate(data):
            result.append(normalize_keys_to_snake(item, depth + 1))
        return result
    if isinstance(data, dict):
        out = {}
        for k, v in data.items():
            if isinstance(k, str):
                key = k if _SNAKE_LIKE_KEY_RE.fullmatch(k) else to_snake(k)
            else:
                key = k
            out[key] = normalize_keys_to_snake(v, depth + 1)
        return out
    return data


def naming_get_json(data):
    """对 JSON 数据做 snake_case 键名转换（替代原 NamingRequest.get_json）"""
    return normalize_keys_to_snake(data)
