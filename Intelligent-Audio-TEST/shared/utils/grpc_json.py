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


def fold_business_code(data, code):
    """失败响应的业务错误码折进 data JSON（INT-566 P1-5）。

    服务侧 handler 返回的失败信封常为 {success:False, message, data, code}（code 在
    顶层）；gRPC Response 仅 success/message/data 三字段，网关代理按
    `data.code`（JSON dict）提升到顶层映射 HTTP 状态（INT-141 F2 口径）。
    本函数把顶层 code 折进 data：
      - data 为 None → {'code': code}
      - data 为 dict  → 浅拷贝并附加 code 键（避免污染调用方对象）
      - 其余类型（list/标量）→ 原样返回（网关无法从非 dict 提取 code）
    调用方仅在失败响应时调用，避免污染成功载荷。
    """
    if code is None or code == 0:
        return data
    if data is None:
        return {'code': code}
    if isinstance(data, dict):
        merged = dict(data)
        merged['code'] = code
        return merged
    return data
