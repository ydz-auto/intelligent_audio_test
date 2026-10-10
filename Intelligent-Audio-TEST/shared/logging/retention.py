# -*- coding: utf-8 -*-
"""日志保留清扫（INT-81）。

按保留天数（mtime）清理过期日志文件：服务运行日志与业务日志共用
同一清扫入口，由 log worker 后台线程周期触发。

服务日志与业务日志保留天数相互独立（审计问题 3 修复）：按 root 清扫时
排除 business/ 子树，业务日志只按 business_retention_days 清扫——否则
业务日志实际保留 = min(service, business) 天，business 配置大于 service
配置时失效。
"""
import os
import time

from shared.logging.config import LogSettings, get_log_settings
from shared.logging.path_builder import BUSINESS_DIR


def sweep_expired_files(root_dir: str, retention_days: int,
                        exclude_dir: str = None) -> int:
    """删除 root_dir 下 mtime 超过保留期的 *.log* 文件，返回删除数。

    只清理日志文件（*.log / *.log.NNN / 轮转名），不触碰其他文件；
    exclude_dir 给定时跳过该相对子树（文件与空目录回收均不触碰）；
    清空后的空目录一并移除（不含 root_dir 本身）。
    """
    if not root_dir or not os.path.isdir(root_dir):
        return 0
    cutoff = time.time() - max(1, retention_days) * 86400
    excluded_prefix = None
    if exclude_dir:
        excluded_prefix = exclude_dir.strip('/\\') + os.sep
    deleted = 0
    for root, dirs, names in os.walk(root_dir, topdown=False):
        rel_root = None
        if excluded_prefix:
            rel_root = os.path.relpath(root, root_dir)
            if rel_root == exclude_dir or rel_root.startswith(excluded_prefix):
                # 排除子树：不删文件、不回收其空目录
                continue
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
    # 第一遍只清服务日志：排除 business/ 子树，两套保留天数互不叠加
    total = sweep_expired_files(resolved.root_dir, resolved.service_retention_days,
                                exclude_dir=BUSINESS_DIR)
    total += sweep_expired_files(
        os.path.join(resolved.root_dir, BUSINESS_DIR),
        resolved.business_retention_days,
    )
    return total
