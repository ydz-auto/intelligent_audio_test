from flask import Request as FlaskRequest

import re

from pydantic.alias_generators import to_snake


_SNAKE_LIKE_KEY_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")


def normalize_keys_to_snake(data, depth=0):
    indent = "  " * depth
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


class NamingRequest(FlaskRequest):
    def get_json(self, *args, **kwargs):
        data = super().get_json(*args, **kwargs)
        return normalize_keys_to_snake(data)
