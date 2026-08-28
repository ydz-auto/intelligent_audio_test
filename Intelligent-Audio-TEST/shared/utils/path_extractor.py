"""嵌套数据路径提取工具"""


def extract_by_path(data: dict, path: str, default=None):
    """按 a.b.c 路径从嵌套 dict/list 中提取值。

    支持点分路径，如 'rounds.0.output.question'
    """
    if not path or not data:
        return default
    val = data
    for part in path.split('.'):
        if isinstance(val, dict):
            val = val.get(part)
        elif isinstance(val, list):
            try:
                idx = int(part)
                val = val[idx] if 0 <= idx < len(val) else None
            except (ValueError, IndexError):
                return default
        else:
            return default
        if val is None:
            return default
    return val
