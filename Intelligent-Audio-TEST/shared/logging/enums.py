# -*- coding: utf-8 -*-
"""日志体系枚举（INT-81 / INT-1793）。

业务日志类型与环境标识全部枚举化，禁止魔法字符串路径拼接。
审计事件的 category 枚举复用 `shared.models.common_enums.AuditLogCategory`
（五值，唯一来源），此处只做日志体系内的转出与审计目录常量。
"""
from enum import Enum

from shared.models.common_enums import (
    AUDIT_LOG_CATEGORIES,
    AuditLogCategory,
)

# 审计文件子树（相对 LOG_ROOT_DIR）：logs/audit/{YYYY-MM-DD}/...
AUDIT_DIR = 'audit'

# 审计 JSONL 扩展名（与业务/服务日志的 .log 区分，读侧按树区分）
AUDIT_FILE_SUFFIX = '.jsonl'


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


# 业务日志文件条目的统一时间格式（INT-81 审计修复：写入侧固定 strftime，
# 拒绝 str(datetime) 的微秒+时区后缀形态——固定宽度保证字符串排序与
# DB/WS 侧时间可比，前端统一按可解析时间渲染）。
LOG_TIME_FORMAT = '%Y-%m-%d %H:%M:%S.%f'


def log_type_for_category(category: str) -> BusinessLogType:
    """按日志 category 解析业务日志类型（未知名回退 EXECUTION）。"""
    return CATEGORY_TO_LOG_TYPE.get((category or '').lower(), DEFAULT_LOG_TYPE)
