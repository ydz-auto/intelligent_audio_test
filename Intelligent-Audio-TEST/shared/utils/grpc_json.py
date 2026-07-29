# -*- coding: utf-8 -*-
"""gRPC JSON 辅助函数

供各服务 servicers.py 共用，避免重复定义。
"""
import json


def loads(s, default):
    """安全 JSON 解析，空字符串返回默认值"""
    if not s:
        return default
    if isinstance(s, bytes):
        s = s.decode('utf-8')
    return json.loads(s)


def dumps(obj):
    """JSON 序列化，None/不可序列化对象返回空字符串"""
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return ""
