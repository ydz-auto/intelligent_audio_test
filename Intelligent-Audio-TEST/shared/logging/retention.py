# -*- coding: utf-8 -*-
"""日志保留清扫（INT-81 / INT-1793）。

三棵树各自按期清扫，保留天数统一继承 `LOG_FILE_RETENTION_DAYS`（负责人
2026-10-24 裁定：全部日志文件 30 天，细分类别只能显式覆盖）：

- 服务运行日志：`logs/{service}/`，排除 business/ 与 audit/ 子树，
  否则业务/审计日志实际保留 = min(三者)，配置大于默认时失效
- 业务日志：`logs/business/`，按 mtime
- 审计日志：`logs/audit/{YYYY-MM-DD}/`，按**目录日期**判定（进程重启后追加写
  会刷新 mtime，日期段不会）；到期先归档到存储 `archives/audit/{date}/`，
  归档失败保留本地并告警（绝不先删后传）

单清扫者（契约 §3.4 `LOG_SWEEP_SERVICE`）：只有该服务执行清扫。此前每个进程
各自 sweep 同一共享日志卷，审计涉及外部存储上传，多进程并发会重复上传并互相
删除对方刚写的文件。
"""
import os
import time
from datetime import datetime, timedelta

from shared.logging.config import LogSettings, get_log_settings, resolve_service_name
from shared.logging.enums import AUDIT_DIR
from shared.logging.path_builder import BUSINESS_DIR

# 审计归档类目（存储层 category）与前缀：完整键 = archives/audit/{date}/{filename}
AUDIT_ARCHIVE_CATEGORY = 'archives'
AUDIT_ARCHIVE_PREFIX = AUDIT_DIR
_AUDIT_DATE_FORMAT = '%Y-%m-%d'


def _warning(message: str) -> None:
    """清扫告警（后台线程，stdout 可能不可用，失败静默）。"""
    print(f"[sweep] WARN - {message}")


def _excluded_prefixes(exclude_dir) -> tuple:
    """归一排除子树（接受单个相对路径或列表）。"""
    if not exclude_dir:
        return ()
    values = (exclude_dir,) if isinstance(exclude_dir, str) else tuple(exclude_dir)
    return tuple(str(item).strip('/\\') + os.sep for item in values if str(item).strip())


def sweep_expired_files(root_dir: str, retention_days: int,
                        exclude_dir=None) -> int:
    """删除 root_dir 下 mtime 超过保留期的 *.log* / *.jsonl 文件，返回删除数。

    只清理日志文件（*.log / *.log.NNN / *.jsonl 轮转名），不触碰其他文件；
    exclude_dir 给定时跳过这些相对子树（文件与空目录回收均不触碰）；
    清空后的空目录一并移除（不含 root_dir 本身）。
    """
    if not root_dir or not os.path.isdir(root_dir):
        return 0
    cutoff = time.time() - max(1, retention_days) * 86400
    excluded_prefixes = _excluded_prefixes(exclude_dir)
    deleted = 0
    for root, dirs, names in os.walk(root_dir, topdown=False):
        if excluded_prefixes:
            rel_root = os.path.relpath(root, root_dir)
            if any(rel_root == prefix.rstrip(os.sep) or rel_root.startswith(prefix)
                   for prefix in excluded_prefixes):
                # 排除子树：不删文件、不回收其空目录
                continue
        for name in names:
            if not _is_log_file(name):
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


def _is_log_file(name: str) -> bool:
    """日志文件名判定：服务/业务 .log（含轮转/切分）与审计 .jsonl（含切分）。"""
    return (name.endswith('.log') or '.log.' in name
            or name.endswith('.jsonl') or '-00' in name)


def audit_cutoff_date(retention_days: int, today=None) -> datetime.date:
    """审计过期日期边界：目录日期早于本日期即到期。"""
    base = today or datetime.now().date()
    return base - timedelta(days=max(1, retention_days))


def sweep_audit_dates(settings: LogSettings = None) -> dict:
    """按日期目录清扫审计子树（到期先归档、归档失败保留本地）。

    Returns:
        {'archived': 成功归档文件数, 'deleted': 删除文件数, 'failed': 归档失败数}
    """
    resolved = settings or get_log_settings()
    stats = {'archived': 0, 'deleted': 0, 'failed': 0}
    audit_root = os.path.join(resolved.root_dir, AUDIT_DIR)
    if not os.path.isdir(audit_root):
        return stats
    cutoff = audit_cutoff_date(resolved.audit_retention_days)
    for entry in sorted(os.listdir(audit_root)):
        day_dir = os.path.join(audit_root, entry)
        if not os.path.isdir(day_dir):
            continue
        try:
            day = datetime.strptime(entry, _AUDIT_DATE_FORMAT).date()
        except ValueError:
            # 非日期目录（手工排查残留等）不按审计保留期回收
            continue
        if day >= cutoff:
            continue
        for filename in sorted(os.listdir(day_dir)):
            path = os.path.join(day_dir, filename)
            if not os.path.isfile(path):
                continue
            if resolved.audit_archive_enabled:
                try:
                    from shared.infrastructure.storage import storage
                    storage.save_file(
                        path, AUDIT_ARCHIVE_CATEGORY,
                        f'{AUDIT_ARCHIVE_PREFIX}/{entry}/{filename}',
                    )
                    stats['archived'] += 1
                except Exception as e:
                    # 归档失败：保留本地、下轮重试，绝不先删后传
                    stats['failed'] += 1
                    _warning(f'audit archive failed, kept locally: {path} ({e})')
                    continue
            try:
                os.remove(path)
                stats['deleted'] += 1
            except OSError as e:
                _warning(f'audit delete failed: {path} ({e})')
        try:
            os.rmdir(day_dir)
        except OSError:
            pass
    return stats


def is_sweep_owner(settings: LogSettings = None) -> bool:
    """当前进程是否为唯一清扫者（LOG_SWEEP_SERVICE）。"""
    resolved = settings or get_log_settings()
    owner = (resolved.sweep_service or '').strip()
    if not owner:
        return False
    return resolve_service_name() == owner


def sweep_log_root(settings: LogSettings = None) -> int:
    """按配置清扫日志根目录（服务 / 业务 / 审计三棵树，单清扫者）。"""
    resolved = settings or get_log_settings()
    if not is_sweep_owner(resolved):
        return 0
    # 第一遍只清服务日志：排除 business/ 与 audit/ 子树，三套保留天数互不叠加
    total = sweep_expired_files(resolved.root_dir, resolved.service_retention_days,
                                exclude_dir=(BUSINESS_DIR, AUDIT_DIR))
    total += sweep_expired_files(
        os.path.join(resolved.root_dir, BUSINESS_DIR),
        resolved.business_retention_days,
    )
    total += sweep_audit_dates(resolved)['deleted']
    return total
