# -*- coding: utf-8 -*-
"""日志保留清扫（INT-81）。

按保留天数（mtime）清理过期日志文件：服务运行日志与业务日志共用
同一清扫入口，由 log worker 后台线程周期触发。
"""
import os
import time

from shared.logging.config import LogSettings, get_log_settings


def sweep_expired_files(root_dir: str, retention_days: int) -> int:
    """删除 root_dir 下 mtime 超过保留期的 *.log* 文件，返回删除数。

    只清理日志文件（*.log / *.log.NNN / 轮转名），不触碰其他文件；
    清空后的空目录一并移除（不含 root_dir 本身）。
    """
    if not root_dir or not os.path.isdir(root_dir):
        return 0
    cutoff = time.time() - max(1, retention_days) * 86400
    deleted = 0
    for root, dirs, names in os.walk(root_dir, topdown=False):
        for name in names:
            if not name.endswith('.log') and '.log.' not in name and '-00' not in name:
                continue
            path = os.path.join(root, name)
            try:
                if os.path.getmtime(path) < cutoff:
                    os.remove(path)
                    deleted += 1
            except OSError:
                continue
        if root != root_dir:
            try:
                os.rmdir(root)
            except OSError:
                pass
    return deleted


def sweep_log_root(settings: LogSettings = None) -> int:
    """按配置清扫日志根目录（服务日志与业务日志各自的保留天数）。"""
    resolved = settings or get_log_settings()
    total = sweep_expired_files(resolved.root_dir, resolved.service_retention_days)
    total += sweep_expired_files(
        os.path.join(resolved.root_dir, 'business'),
        resolved.business_retention_days,
    )
    return total
