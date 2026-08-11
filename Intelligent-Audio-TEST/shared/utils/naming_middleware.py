from urllib.parse import parse_qsl, urlencode

import re

from pydantic.alias_generators import to_camel, to_snake
from starlette.middleware.base import BaseHTTPMiddleware


_SNAKE_LIKE_KEY_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")


def add_case_aliases_to_query_string(query_string: str) -> str:
    if not query_string:
        return query_string

    pairs = parse_qsl(query_string, keep_blank_values=True)
    if not pairs:
        return query_string

    out = []
    existing = set()

    for k, v in pairs:
        out.append((k, v))
        existing.add(k)

    for k, v in pairs:
        snake_key = (
            k
            if isinstance(k, str) and _SNAKE_LIKE_KEY_RE.fullmatch(k)
            else (to_snake(k) if isinstance(k, str) else k)
        )
        if snake_key and snake_key not in existing:
            out.append((snake_key, v))
            existing.add(snake_key)

        camel_key = to_camel(k) if isinstance(k, str) else k
        if camel_key and camel_key not in existing:
            out.append((camel_key, v))
            existing.add(camel_key)

    return urlencode(out, doseq=True)


class NamingAliasMiddleware(BaseHTTPMiddleware):
    """为查询参数添加驼峰/蛇形别名，使前端 camelCase 与后端 snake_case 兼容。

    请求体由 Pydantic APIModel 的 alias_generator 处理；
    本中间件补齐原生查询参数（非 Pydantic 解析的 query params）的命名转换。
    """

    async def dispatch(self, request, call_next):
        qs = request.url.query
        if qs:
            new_qs = add_case_aliases_to_query_string(qs)
            if new_qs != qs:
                request.scope['query_string'] = new_qs.encode('utf-8')
        return await call_next(request)
