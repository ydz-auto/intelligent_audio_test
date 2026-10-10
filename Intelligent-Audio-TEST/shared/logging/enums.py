# -*- coding: utf-8 -*-
"""日志体系枚举（INT-81）。

业务日志类型与环境标识全部枚举化，禁止魔法字符串路径拼接。
"""
from enum import Enum


class BusinessLogType(str, Enum):
    """业务日志类型 — 决定路径模板末段文件名前缀。

    四类业务日志（INT-81）：
    - execution: E2E 轮次日志 / API 用例执行日志
    - evaluation: 评估判定日志
    - device: 设备交互日志（含音频播放/采集等设备链路日志）
    """
    EXECUTION = 'execution'
    EVALUATION = 'evaluation'
    DEVICE = 'device'


class LogEnvironment(str, Enum):
    """运行环境标识 — prod 下 DEBUG 级日志不落业务文件。"""
    DEV = 'dev'
    PROD = 'prod'


# 日志 category → 业务日志类型映射（emit 分流后由写入侧消费）。
# 显式映射表替代魔法字符串 if/else 链；未列出的 category 一律视为执行日志。
CATEGORY_TO_LOG_TYPE = {
    'execution': BusinessLogType.EXECUTION,
    'evaluation': BusinessLogType.EVALUATION,
    'device': BusinessLogType.DEVICE,
    'audio': BusinessLogType.DEVICE,
}
DEFAULT_LOG_TYPE = BusinessLogType.EXECUTION


def log_type_for_category(category: str) -> BusinessLogType:
    """按日志 category 解析业务日志类型（未知名回退 EXECUTION）。"""
    return CATEGORY_TO_LOG_TYPE.get((category or '').lower(), DEFAULT_LOG_TYPE)
