# -*- coding: utf-8 -*-
"""日志体系配置（INT-81）。

统一从 BaseConfig（环境变量）读取日志体系设置，快照为不可变 LogSettings，
供服务文件日志与业务日志写入/读取侧共享。所有阈值/开关/路径根均在
BaseConfig 中配置化，本模块只做快照与归一化（MB → 字节、枚举化环境）。
"""
import threading
from dataclasses import dataclass

from shared.infrastructure.config import BaseConfig
from shared.logging.enums import LogEnvironment

_SETTINGS = None
_SETTINGS_LOCK = threading.Lock()


@dataclass(frozen=True)
class LogSettings:
    """日志体系设置快照（进程内不可变）。"""

    root_dir: str
    environment: LogEnvironment
    service_max_bytes: int
    service_retention_days: int
    business_enabled: bool
    business_db_enabled: bool
    business_max_bytes: int
    business_retention_days: int
    # 读取侧单次查询最大物化条数（0 = 不限）；默认远高于常规任务量，
    # 仅在大任务轮询场景兜底（total 变下界语义）
    business_max_scan_entries: int = 100_000

    @property
    def is_prod(self) -> bool:
        return self.environment == LogEnvironment.PROD


def _build_settings() -> LogSettings:
    return LogSettings(
        root_dir=BaseConfig.LOG_ROOT_DIR,
        environment=LogEnvironment(BaseConfig.LOG_ENVIRONMENT),
        service_max_bytes=max(1, BaseConfig.LOG_SERVICE_MAX_MB) * 1024 * 1024,
        service_retention_days=max(1, BaseConfig.LOG_SERVICE_RETENTION_DAYS),
        business_enabled=BaseConfig.LOG_BUSINESS_ENABLED,
        business_db_enabled=BaseConfig.LOG_BUSINESS_DB_ENABLED,
        business_max_bytes=max(1, BaseConfig.LOG_BUSINESS_MAX_MB) * 1024 * 1024,
        business_retention_days=max(1, BaseConfig.LOG_BUSINESS_RETENTION_DAYS),
        business_max_scan_entries=max(0, BaseConfig.LOG_BUSINESS_MAX_SCAN_ENTRIES),
    )


def get_log_settings() -> LogSettings:
    """获取进程级配置快照（首次调用后缓存）。"""
    global _SETTINGS
    if _SETTINGS is None:
        with _SETTINGS_LOCK:
            if _SETTINGS is None:
                _SETTINGS = _build_settings()
    return _SETTINGS


def reset_log_settings() -> None:
    """清空快照（仅供测试注入临时环境后重建）。"""
    global _SETTINGS
    with _SETTINGS_LOCK:
        _SETTINGS = None


def resolve_service_name() -> str:
    """解析当前服务名（日志目录名），无 SERVICE_NAME 环境时归入 unknown。"""
    import os
    return (os.environ.get('SERVICE_NAME') or BaseConfig.SERVICE_NAME or 'unknown').strip() or 'unknown'
