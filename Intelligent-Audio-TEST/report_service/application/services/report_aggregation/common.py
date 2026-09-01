# -*- coding: utf-8 -*-
"""报告聚合统计 — 公共辅助（P4-5 大文件拆分）。

提供各聚合 Mixin 共用的取值辅助函数，消除跨模块重复定义。
"""
from __future__ import annotations


def _r_get(r, key, default=None):
    """从 dict 或对象中安全取值。"""
    if isinstance(r, dict):
        return r.get(key, default)
    return getattr(r, key, default)
