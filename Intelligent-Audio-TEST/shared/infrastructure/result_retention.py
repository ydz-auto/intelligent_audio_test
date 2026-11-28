# -*- coding: utf-8 -*-
"""执行产物冷/热存储保留清扫（2026-11-28 裁定）。

策略：
- 本地冷存（执行机 / 容器本地 `RESULT_LOCAL_ROOT`）：保留 365 天；
- 对象存储：只有 `RESULT_OSS_HOT_RETENTION_CATEGORIES`（默认 `case_result`）
  保留最近 30 天；`ref_params` 是参考参数源文件，长期保留、不参与过期删除。

调度：
- 复用 log worker 的周期触发（600s）与「当日首次执行」日期戳；
- 本地清扫在**每个节点**各自执行（本地冷存不共享）；
- 对象存储清扫只在 `LOG_SWEEP_SERVICE`（默认 api_gateway）执行一次，
  避免多进程并发删同一批对象。
"""
import os
import time

from shared.infrastructure.config import BaseConfig
from shared.logging.retention import (
    acquire_sweep_stamp_lock,
    read_sweep_stamp,
    today_segment,
    write_sweep_stamp,
)

_RESULT_SWEEP_STAMP = '.result_sweep_stamp'


def _categories() -> list:
    raw = getattr(BaseConfig, 'RESULT_DUAL_WRITE_CATEGORIES', '') or ''
    return [part.strip() for part in raw.split(',') if part.strip()]


def _oss_expiring_categories() -> list:
    """只允许这些 category 参与 OSS 30 天过期删除（ref_params 长期保留）。"""
    raw = getattr(BaseConfig, 'RESULT_OSS_HOT_RETENTION_CATEGORIES', '') or ''
    return [part.strip() for part in raw.split(',') if part.strip()]


def _cold_root() -> str:
    explicit = (os.environ.get('RESULT_LOCAL_ROOT') or '').strip()
    return explicit or BaseConfig.STORAGE_LOCAL_ROOT


def sweep_local_results() -> dict:
    """删除超过 RESULT_LOCAL_RETENTION_DAYS 的本地冷存文件。"""
    stats = {'deleted': 0, 'dirs': 0}
    root = _cold_root()
    if not os.path.isdir(root):
        return stats
    cutoff = time.time() - max(1, BaseConfig.RESULT_LOCAL_RETENTION_DAYS) * 86400
    for category in _categories():
        cat_root = os.path.join(root, category)
        if not os.path.isdir(cat_root):
            continue
        for cur, _dirs, files in os.walk(cat_root, topdown=False):
            for name in files:
                path = os.path.join(cur, name)
                try:
                    if os.path.getmtime(path) < cutoff:
                        os.remove(path)
                        stats['deleted'] += 1
                except OSError:
                    continue
            if cur != cat_root:
                try:
                    os.rmdir(cur)
                    stats['dirs'] += 1
                except OSError:
                    pass
    return stats


def sweep_oss_results() -> dict:
    """删除对象存储中超过 RESULT_OSS_HOT_RETENTION_DAYS 的执行产物。

    安全闸门：只有执行器能确认「本地冷副本存在」的对象才允许删除 OSS；
    执行器不可达 / 冷写失败 / 旧版本无 ArtifactService 时一律跳过，
    保证「绝不先删后传」。
    """
    stats = {'deleted': 0, 'failed': 0, 'skipped': 0}
    if getattr(BaseConfig, 'STORAGE_BACKEND', 'auto') == 'local':
        return stats
    cutoff = time.time() - max(1, BaseConfig.RESULT_OSS_HOT_RETENTION_DAYS) * 86400
    cap = max(1, BaseConfig.RESULT_RETENTION_MAX_DELETES_PER_RUN)
    from shared.clients.oss_client import oss
    from shared.clients.artifact_client import stat_artifact
    for category in _oss_expiring_categories():
        try:
            items = oss.list_objects_with_meta(category)
        except Exception:
            continue
        for item in items:
            if stats['deleted'] >= cap:
                return stats
            last_modified = item.get('lastModified')
            if not last_modified:
                continue
            try:
                ts = last_modified.timestamp()
            except Exception:
                continue
            if ts >= cutoff:
                continue
            key = item.get('key')
            if not key:
                continue
            # 冷副本确认：拿不到确认就保留 OSS，宁可多占空间
            if stat_artifact(category, key) is None:
                stats['skipped'] += 1
                continue
            try:
                oss.delete_object(category, key)
                stats['deleted'] += 1
            except Exception:
                stats['failed'] += 1
    return stats


def _stamp_path() -> str:
    return os.path.join(_cold_root(), _RESULT_SWEEP_STAMP)


def run_result_maintenance() -> dict:
    """当日首次执行：本地冷存清扫（每节点）+ OSS 热存清扫（单清扫者）。"""
    if not getattr(BaseConfig, 'RESULT_RETENTION_ENABLED', False):
        return {}
    root = _cold_root()
    if not os.path.isdir(root):
        return {}
    stamp = _stamp_path()
    today = today_segment()
    if read_sweep_stamp(stamp) == today:
        return {}
    lock = acquire_sweep_stamp_lock(stamp)
    if lock is None:
        return {}
    try:
        if read_sweep_stamp(stamp) == today:
            return {}
        stats = {'local': sweep_local_results()}
        try:
            from shared.logging.retention import is_sweep_owner
            if is_sweep_owner():
                stats['oss'] = sweep_oss_results()
        except Exception:
            pass
        write_sweep_stamp(stamp, today)
        return stats
    finally:
        try:
            lock.close()
        except Exception:
            pass
