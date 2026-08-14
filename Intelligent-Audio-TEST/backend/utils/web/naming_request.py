from flask import Request as FlaskRequest

import re


_SNAKE_LIKE_KEY_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
_HAS_UPPER_RE = re.compile(r"[A-Z]")


def _camel_to_snake(name):
    """将驼峰命名转为蛇形命名，保留连字符不变。

    仅处理 camelCase/PascalCase，不修改 kebab-case 中的连字符。
    """
    # 先处理连续大写字母的情况（如 WEREn -> wer_en）
    s1 = re.sub('([a-z0-9])([A-Z])', r'\1_\2', name)
    s2 = re.sub('([A-Z]+)([A-Z][a-z])', r'\1_\2', s1)
    return s2.lower()


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
                # 已经是 snake_case 的保留原样
                if _SNAKE_LIKE_KEY_RE.fullmatch(k):
                    key = k
                # 含连字符的 kebab-case 保留原样（仅处理驼峰）
                elif '-' in k and not _HAS_UPPER_RE.search(k):
                    key = k
                else:
                    key = _camel_to_snake(k)
            else:
                key = k
            out[key] = normalize_keys_to_snake(v, depth + 1)
        return out
    return data


class NamingRequest(FlaskRequest):
    def get_json(self, *args, **kwargs):
        data = super().get_json(*args, **kwargs)
        return normalize_keys_to_snake(data)
