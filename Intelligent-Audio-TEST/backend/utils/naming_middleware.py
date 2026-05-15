from urllib.parse import parse_qsl, urlencode

import re

from pydantic.alias_generators import to_camel, to_snake


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


class NamingAliasMiddleware:
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        query_string = environ.get("QUERY_STRING", "")
        if query_string:
            environ["QUERY_STRING"] = add_case_aliases_to_query_string(query_string)
        return self.app(environ, start_response)
