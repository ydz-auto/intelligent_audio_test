"""嵌套数据路径提取工具"""
import re

# 一段路径 = 键名 + 若干 [n] 下标（如 ``events[0]``、``events[0][1]``）。
# 非法写法（``a[x]`` / ``a[-1]``）整体不匹配，按「路径无效」返回 default。
_BRACKET_SEGMENT = re.compile(r'^([^\[\]]*)((?:\[\d+\])*)$')
_BRACKET_INDEX = re.compile(r'\[(\d+)\]')


def _segment_tokens(part: str):
    """把一段路径拆成取值令牌序列（键名 / 整数下标），非法返回 None。

    - ``events``      → ['events']
    - ``events[0]``   → ['events', 0]
    - ``[0]``         → [0]
    """
    match = _BRACKET_SEGMENT.match(part)
    if not match:
        return None
    tokens = []
    key, brackets = match.group(1), match.group(2)
    if key:
        tokens.append(key)
    tokens.extend(int(index) for index in _BRACKET_INDEX.findall(brackets))
    return tokens or None


def extract_by_path(data: dict, path: str, default=None):
    """按 a.b.c 路径从嵌套 dict/list 中提取值。

    支持点分路径，如 'rounds.0.output.question'；
    数组下标可写点号数字（``data.events.0.text``）或方括号
    （``data.events[0].text``），两种写法等价（INT-1747 / C0 §9.3）。
    路径不存在、经非 dict/list 中间层、或下标非法时返回 default。
    """
    if not path or not data:
        return default
    val = data
    for part in path.split('.'):
        tokens = _segment_tokens(part)
        if not tokens:
            return default
        for token in tokens:
            if isinstance(val, dict):
                # 点号数字段沿用旧语义：dict 上按字符串键查（{'0': ...} 可被 .0 取到）
                val = val.get(token if isinstance(token, str) else str(token))
            elif isinstance(val, list):
                if isinstance(token, str):
                    # 点号数字段（rounds.0.output）在 list 上按整数下标解释
                    if not token.isdigit():
                        return default
                    token = int(token)
                val = val[token] if 0 <= token < len(val) else None
            else:
                return default
            if val is None:
                return default
    return val
