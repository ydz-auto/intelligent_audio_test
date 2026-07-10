import re
from typing import Optional
from datetime import datetime, timedelta, timezone

# 中国标准时区 UTC+8
_CST = timezone(timedelta(hours=8))

def now_cst() -> datetime:
    """返回当前中国标准时间（UTC+8）"""
    return datetime.now(_CST)

def escape_like_pattern(pattern: str, escape_char: str = '\\') -> str:
    """
    转义 SQL LIKE 查询中的特殊字符
    
    Args:
        pattern: 原始搜索模式
        escape_char: 转义字符，默认为 '\\'
    
    Returns:
        转义后的安全模式
    """
    if not pattern:
        return pattern
    
    special_chars = ['%', '_', escape_char]
    escaped = pattern
    for char in special_chars:
        escaped = escaped.replace(char, f'{escape_char}{char}')
    return escaped

def safe_like_pattern(pattern: str) -> str:
    """
    创建安全的 LIKE 模式，转义特殊字符并添加通配符
    
    Args:
        pattern: 原始搜索字符串
    
    Returns:
        安全的 LIKE 模式字符串
    """
    if not pattern:
        return pattern
    escaped = escape_like_pattern(pattern)
    return f"%{escaped}%"

def sanitize_keyword(keyword: Optional[str], max_length: int = 255) -> Optional[str]:
    """
    清理和验证搜索关键字
    
    Args:
        keyword: 原始关键字
        max_length: 最大长度限制
    
    Returns:
        清理后的关键字，如果无效则返回 None
    """
    if not keyword:
        return None
    
    keyword = keyword.strip()
    
    if not keyword:
        return None
    
    if len(keyword) > max_length:
        keyword = keyword[:max_length]
    
    return keyword

def normalize_sort_field(field: str, allowed_fields: list, default: str = 'created_at') -> str:
    """
    规范化排序字段，防止 SQL 注入
    
    Args:
        field: 原始字段名
        allowed_fields: 允许的字段列表
        default: 默认字段
    
    Returns:
        安全的字段名
    """
    if not field:
        return default
    
    field_lower = field.lower().replace('-', '_')
    
    for allowed in allowed_fields:
        if field_lower == allowed.lower():
            return allowed
    
    return default

def normalize_sort_order(order: str, default: str = 'desc') -> str:
    """
    规范化排序方向
    
    Args:
        order: 原始排序方向
        default: 默认方向
    
    Returns:
        安全的排序方向 ('asc' 或 'desc')
    """
    if not order:
        return default
    
    order_lower = order.lower().strip()
    if order_lower in ('asc', 'desc'):
        return order_lower
    
    return default
