# -*- coding: utf-8 -*-
"""日志保留清扫（INT-81 / INT-1793）。

三棵树各自按期清扫，保留天数统一继承 `LOG_FILE_RETENTION_DAYS`（负责人
2026-10-24 裁定：全部日志文件 30 天，细分类别只能显式覆盖）：

- 服务运行日志：`logs/{service}/{YYYY-MM-DD}/`，排除 business/ 与 audit/ 子树，
  否则业务/审计日志实际保留 = min(三者)，配置大于默认时失效
- 业务日志：`logs/business/`，按 mtime
- 审计日志：`logs/audit/{YYYY-MM-DD}/`，按**目录日期**判定（进程重启后追加写
  会刷新 mtime，日期段不会）；到期先归档到存储 `archives/audit/{date}/`，
  归档失败保留本地并告警（绝不先删后传）

单清扫者（契约 §3.4 `LOG_SWEEP_SERVICE`）：只有该服务执行清扫。此前每个进程
各自 sweep 同一共享日志卷，审计涉及外部存储上传，多进程并发会重复上传并互相
删除对方刚写的文件。

每日一次（契约 §Q5 调度落点）：log worker 仍按 600s 周期触发，但清扫体只在
**当日首次触发**时执行——`{LOG_ROOT_DIR}/.sweep_stamp` 记日期戳（原子写），
非当日已执行即跳过。审计件到期归档失败时会保留本地重试，无条件每 600s 重扫
等于每 10 分钟重付一次存储探活与上传超时；日期戳把三棵树的清扫收敛为每日一次，
与「单清扫者」「幂等」三项同时成立。
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
# 归档是否真的落进对象存储：存储层 save_file 在 OSS 不可达 / 未配置时会静默
# 降级写容器本地目录并返回 `local://`（INT-1785 P1-1 同类语义）。审计原件是
# 唯一持久副本，只有 `oss://` 才算归档成功，其余一律按失败保留本地重试。
_ARCHIVE_WRITTEN_SCHEME = 'oss://'


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


def _archive_written_to_object_storage(location) -> bool:
    """归档写入是否真落对象存储（`oss://`）；本地降级 / 空值一律不算。"""
    return isinstance(location, str) and location.startswith(_ARCHIVE_WRITTEN_SCHEME)


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
                    location = storage.save_file(
                        path, AUDIT_ARCHIVE_CATEGORY,
                        f'{AUDIT_ARCHIVE_PREFIX}/{entry}/{filename}',
                    )
                except Exception as e:
                    # 归档失败：保留本地、下轮重试，绝不先删后传
                    stats['failed'] += 1
                    _warning(f'audit archive failed, kept locally: {path} ({e})')
                    continue
                if not _archive_written_to_object_storage(location):
                    # 降级写本地（local://）不算归档：副本不持久，保留原件
                    stats['failed'] += 1
                    _warning(
                        'audit archive not persisted to object storage, '
                        f'kept locally: {path} (location={location})')
                    continue
                stats['archived'] += 1
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


# ---- 当日首次触发标记（契约 §Q5 调度落点：logs/.sweep_stamp）----
# 只记日期戳（YYYY-MM-DD），不加任何依赖库；跨进程用文件锁做 single-flight，
# 拿不到锁的进程本轮直接跳过（另一个进程正在扫），不重复执行。
SWEEP_STAMP_FILENAME = '.sweep_stamp'
_SWEEP_STAMP_LOCK_SUFFIX = '.lock'


def sweep_stamp_path(root_dir: str) -> str:
    """日期戳文件路径：{LOG_ROOT_DIR}/.sweep_stamp。"""
    return os.path.join(root_dir, SWEEP_STAMP_FILENAME)


def today_segment() -> str:
    """当日日期戳文本（本地日期，YYYY-MM-DD）。"""
    return datetime.now().date().isoformat()


def read_sweep_stamp(stamp_path: str) -> str:
    """读取日期戳；文件不存在 / 不可读 / 内容非日期一律返回空串。"""
    try:
        with open(stamp_path, 'r', encoding='utf-8') as fh:
            return fh.read().strip()
    except OSError:
        return ''


def write_sweep_stamp(stamp_path: str, day_seg: str) -> bool:
    """原子写日期戳（tmp + os.replace）：任一读者只看到完整内容。"""
    tmp_path = f'{stamp_path}.tmp-{os.getpid()}'
    try:
        os.makedirs(os.path.dirname(stamp_path) or '.', exist_ok=True)
        with open(tmp_path, 'w', encoding='utf-8') as fh:
            fh.write(f'{day_seg}\n')
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, stamp_path)
        return True
    except OSError as e:
        _warning(f'sweep stamp write failed: {stamp_path} ({e})')
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        return False


def _lock_handle_nonblocking(handle) -> bool:
    """非阻塞独占锁（POSIX fcntl / Windows msvcrt），拿不到返回 False。"""
    try:
        import fcntl
    except ImportError:
        fcntl = None
    if fcntl is not None:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False
    try:
        import msvcrt
    except ImportError:
        # 无可用锁原语：退化为进程内 single-flight（worker 线程本身不重叠）
        return True
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write('\0')
            handle.flush()
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return True
    except OSError:
        return False


def _unlock_handle(handle) -> None:
    """释放文件锁并关闭句柄（失败静默——锁随进程退出自动释放）。"""
    try:
        try:
            import fcntl
        except ImportError:
            fcntl = None
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        else:
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    except Exception:
        pass
    finally:
        try:
            handle.close()
        except Exception:
            pass


def acquire_sweep_stamp_lock(stamp_path: str):
    """取跨进程 single-flight 锁；返回句柄，拿不到（已有人在扫）返回 None。"""
    lock_path = stamp_path + _SWEEP_STAMP_LOCK_SUFFIX
    try:
        os.makedirs(os.path.dirname(lock_path) or '.', exist_ok=True)
        handle = open(lock_path, 'a+')
    except OSError as e:
        _warning(f'sweep stamp lock unavailable: {lock_path} ({e})')
        return None
    if not _lock_handle_nonblocking(handle):
        handle.close()
        return None
    return handle


def _sweep_all_trees(resolved: LogSettings) -> int:
    """三棵树各按保留期清扫（服务 / 业务 / 审计）。"""
    # 第一遍只清服务日志：排除 business/ 与 audit/ 子树，三套保留天数互不叠加
    total = sweep_expired_files(resolved.root_dir, resolved.service_retention_days,
                                exclude_dir=(BUSINESS_DIR, AUDIT_DIR))
    total += sweep_expired_files(
        os.path.join(resolved.root_dir, BUSINESS_DIR),
        resolved.business_retention_days,
    )
    total += sweep_audit_dates(resolved)['deleted']
    return total


def sweep_log_root(settings: LogSettings = None) -> int:
    """按配置清扫日志根目录（服务 / 业务 / 审计三棵树，单清扫者，每日一次）。

    返回本次删除的文件数。三种情况返回 0 且不执行清扫体：
    非清扫者进程、当日已执行过（`.sweep_stamp` 日期戳为今天）、
    另一个进程正持有清扫锁。
    """
    resolved = settings or get_log_settings()
    if not is_sweep_owner(resolved):
        return 0
    stamp_path = sweep_stamp_path(resolved.root_dir)
    day_seg = today_segment()
    if read_sweep_stamp(stamp_path) == day_seg:
        return 0
    lock = acquire_sweep_stamp_lock(stamp_path)
    if lock is None:
        # 另一进程正在清扫（共享日志卷）：本轮跳过，由它写日期戳
        return 0
    try:
        # 取锁后重读：等锁期间别的进程可能已完成当日清扫
        if read_sweep_stamp(stamp_path) == day_seg:
            return 0
        total = _sweep_all_trees(resolved)
        # 清扫体跑完才写日期戳：中途异常不落戳，下一轮重试；
        # 根目录不存在时不建目录、不落戳（无清扫对象）
        if os.path.isdir(resolved.root_dir):
            write_sweep_stamp(stamp_path, day_seg)
        return total
    finally:
        _unlock_handle(lock)
