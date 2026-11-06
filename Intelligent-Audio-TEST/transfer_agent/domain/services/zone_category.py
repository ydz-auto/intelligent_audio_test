# -*- coding: utf-8 -*-
"""传输内容类别枚举 — 传输包 category 字段的合法取值。

category 决定目的区落桶位置；TRANSIT 为中转暂存（ephemeral 包或未完成包的分片）。
"""
from enum import Enum


class TransferCategory(str, Enum):
    CASE_RESULT = 'case-result'
    AUDIOS = 'audios'
    REPORTS = 'reports'
    TRANSIT = 'transit'
