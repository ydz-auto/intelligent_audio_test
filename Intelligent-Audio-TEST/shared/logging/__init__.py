# -*- coding: utf-8 -*-
"""shared.logging — 日志体系基座（INT-81）。

服务运行日志（logs/{service_name}/，按天+大小双条件轮转）与业务日志
（logs/business/{task_id}/{device_id|api_id}/{evaluation_id|round}/{log_type}.log，
去库化落文件）的统一实现。各服务禁止自造日志 handler，一律复用本基座。

模块划分：
    config          配置快照（BaseConfig → LogSettings）
    enums           业务日志类型/环境枚举与 category 映射
    context         轮次/评估ID 线程上下文
    path_builder    业务日志路径模板（唯一权威实现）
    identity        写入进程唯一标识（hostname+pid，容器多副本安全）
    service_handler 服务运行日志处理器（双条件轮转）
    business_writer 业务日志 JSONL 写入器（超限切分、进程独立文件名）
    business_reader 业务日志读取器（按 task/device/evaluation 检索）
    retention       保留天数清扫
"""
from shared.logging.config import (
    LogSettings,
    get_log_settings,
    reset_log_settings,
    resolve_service_name,
)
from shared.logging.enums import (
    BusinessLogType,
    LogEnvironment,
    log_type_for_category,
)
from shared.logging.context import (
    get_current_evaluation_id,
    get_current_round,
    log_round,
    set_current_evaluation_id,
    set_current_round,
)
from shared.logging.path_builder import BusinessLogPathBuilder
from shared.logging.identity import process_identity
from shared.logging.service_handler import ServiceRotatingFileHandler, setup_service_file_logging
from shared.logging.business_writer import BusinessLogFileWriter
from shared.logging.business_reader import BusinessLogReader
from shared.logging.retention import sweep_expired_files, sweep_log_root

__all__ = [
    'LogSettings',
    'get_log_settings',
    'reset_log_settings',
    'resolve_service_name',
    'BusinessLogType',
    'LogEnvironment',
    'log_type_for_category',
    'get_current_round',
    'set_current_round',
    'get_current_evaluation_id',
    'set_current_evaluation_id',
    'log_round',
    'BusinessLogPathBuilder',
    'process_identity',
    'ServiceRotatingFileHandler',
    'setup_service_file_logging',
    'BusinessLogFileWriter',
    'BusinessLogReader',
    'sweep_expired_files',
    'sweep_log_root',
]
