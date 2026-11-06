# -*- coding: utf-8 -*-
"""一次性历史日志清理（INT-1785）。

背景（2026-10-24 实测主库）：`logs` 304,743 行 / 249MB（heap 127MB + 索引 60MB
+ TOAST 62MB），无保留策略。业务日志自 10-22 起已去库化（INT-81），10-23 之前
的 273,106 行全部是历史存量；10-23 起写入的几乎都是审计事件
（auth/device/benchmark），按合规要求保留在库里。

本脚本对「截止时间之前的非审计类日志」做**分批归档 → 分批删除**：
归档格式与日志页读侧完全一致（`archives/{tasks|cases|other}/.../{date}.json`，
元素字段同 `_log_po_to_dict`，按 time 升序），否则归档后 UI 读不到。

安全要点：
- 归档写成功之后才删该批；归档只认真 OSS 落盘（`ArchiveStore` 严格语义，OSS 写
  失败不会静默降级到本地磁盘），写后回查对象确实在 OSS；
- 读既有归档时「读失败」不当「文件不存在」，一律中止该批（旧归档不被覆盖）；
- 合并同名归档文件按 id 去重，重跑不会重复（上一轮「已归档未删成」的行）；
- DB 中断（连接拒绝 / 库启动中）也走失败出口：打印已完成批次、以 2 退出，该批
  未删除，重跑幂等续上；
- `--vacuum-full` 是显式开关（默认关）：VACUUM FULL 取 ACCESS EXCLUSIVE 锁，
  由执行者确认低峰窗口后再开；
- 已标记行默认保留（契约 §Q5.1，INT-1903）：归档与删除同一条件只触碰
  `mark IS NULL OR mark = ''` 的行；确需整类清时显式加 `--include-marked`；
- `--dry-run` 只统计不写不删。

用法（隔离库/主库均由环境卡执行）：
    python scripts/maintenance/purge_legacy_logs_int1785.py --dry-run
    python scripts/maintenance/purge_legacy_logs_int1785.py
    python scripts/maintenance/purge_legacy_logs_int1785.py --cutoff 2026-10-20T00:00:00 --batch-size 5000
    python scripts/maintenance/purge_legacy_logs_int1785.py --vacuum-full

退出码：0 = 成功（含 dry-run）；2 = 归档失败/参数错误，该批未删除。
"""
import argparse
import os
import sys
import traceback
from datetime import datetime

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

if not os.environ.get('DATABASE_URL'):
    os.environ['DATABASE_URL'] = os.environ.get(
        'DATABASE_URI',
        'postgresql://intelligent_audio_test:intelligent_audio_test666'
        '@localhost:5432/intelligent_audio_test')

# 10-23 之前为历史存量（10-23 起写入的绝大多数是审计事件，由保留策略管）
DEFAULT_CUTOFF = '2026-10-23T00:00:00'
DEFAULT_BATCH_SIZE = 2000

# 脚本退出码
EXIT_OK = 0
EXIT_ARCHIVE_FAILED = 2


def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='logs 历史日志流式归档清理（INT-1785）')
    parser.add_argument('--cutoff', default=DEFAULT_CUTOFF,
                        help=f'清理截止时间（含时区无关的 CST 墙钟），默认 {DEFAULT_CUTOFF}')
    parser.add_argument('--batch-size', type=int, default=DEFAULT_BATCH_SIZE,
                        help=f'单批行数（内存上界），默认 {DEFAULT_BATCH_SIZE}')
    parser.add_argument('--dry-run', action='store_true',
                        help='只统计将归档/删除的条数，不写归档文件也不删数据')
    parser.add_argument('--categories', default='',
                        help='参与清理的分类（逗号分隔）；默认全部非审计类')
    parser.add_argument('--vacuum-full', action='store_true',
                        help='清理完成后执行 VACUUM FULL logs（ACCESS EXCLUSIVE 锁，需低峰）')
    parser.add_argument('--include-marked', action='store_true',
                        help='连同已标记行一起清（默认保留，契约 §Q5.1；整类清须显式开）')
    return parser.parse_args(argv)


def _parse_cutoff(raw: str) -> datetime:
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        raise SystemExit(f'--cutoff 非法 ISO 时间: {raw!r}')


def _table_size_bytes(session):
    """pg_total_relation_size('logs')；非 PostgreSQL 返回 None。"""
    if session.get_bind().dialect.name != 'postgresql':
        return None
    from sqlalchemy import text
    return session.execute(text("SELECT pg_total_relation_size('logs')")).scalar()


def _format_size(size) -> str:
    if size is None:
        return 'N/A（非 PostgreSQL）'
    return f'{size / 1024 / 1024:.1f} MB'


def _vacuum_full() -> None:
    """VACUUM FULL logs（回收 heap 空洞与 TOAST）；必须在事务外执行。"""
    from sqlalchemy import text
    from shared.models.database import get_engine
    engine = get_engine()
    if engine.dialect.name != 'postgresql':
        print('[VACUUM FULL] 跳过：当前库不是 PostgreSQL')
        return
    print('[VACUUM FULL] 开始（ACCESS EXCLUSIVE 锁，审计写入会短暂阻塞）...', flush=True)
    with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as conn:
        conn.execute(text('VACUUM FULL logs'))
    print('[VACUUM FULL] 完成', flush=True)


def _print_failure(reason: str, result) -> None:
    """失败出口：打印失败原因、已完成批次与统计（DB 中断 / 归档失败共用）。"""
    print(f'[失败] {reason}', flush=True)
    if result is None:
        print('已完成批次: 无', flush=True)
        print('未删除任何数据；修复后可重跑（幂等，同名归档按 id 去重）', flush=True)
        return
    done = ', '.join(f"批 {b['batch']}(归档 {b['archived']}/删除 {b['deleted']})"
                     for b in result.completed_batches) or '无'
    print(f'已完成批次: {done}', flush=True)
    print(f'已归档 {result.archived_count} 条 / 已删除 {result.deleted_count} 条', flush=True)
    if result.remaining_count is not None:
        print(f'剩余条数: {result.remaining_count}', flush=True)
    print('已完成批次保持已归档/已删除状态；失败批次未删除，修复后可重跑'
          '（幂等，同名归档按 id 去重）', flush=True)


def main(argv=None) -> int:
    """脚本入口：任何异常（DB 中断、存储不可用）都以 2 退出并打印已完成批次。"""
    args = _parse_args(argv)
    ctx = {}
    try:
        return _execute(args, ctx)
    except Exception as e:  # noqa: BLE001 - DB/存储中断也要给出统计与非零退出
        _print_failure(f'执行中断（{type(e).__name__}）: {e}', ctx.get('result'))
        traceback.print_exc(file=sys.stderr)
        return EXIT_ARCHIVE_FAILED


def _execute(args, ctx) -> int:
    cutoff = _parse_cutoff(args.cutoff)

    from shared.models.database import init_db, get_db_session
    from task_service.infrastructure.persistence.log_db_archive import (
        AUDIT_LOG_CATEGORIES, ArchiveStore, LogArchivePurger, parse_categories,
    )

    init_db()
    categories = parse_categories(args.categories)
    if categories:
        overlap = sorted(set(categories) & set(AUDIT_LOG_CATEGORIES))
        if overlap:
            print(f'[WARN] --categories 显式包含审计类 {overlap}：这些行将从库里清走',
                  flush=True)

    session = get_db_session()
    try:
        size_before = _table_size_bytes(session)
    finally:
        session.close()

    print(f'数据库: {os.environ.get("DATABASE_URL", "").rsplit("@", 1)[-1]}', flush=True)
    print(f'截止时间: {cutoff.isoformat()}　批次: {args.batch_size}　'
          f'分类: {categories or "全部非审计类"}', flush=True)
    print(f'清理前 pg_total_relation_size(logs): {_format_size(size_before)}', flush=True)

    purger = LogArchivePurger(
        # 严格存储端口：归档只认真 OSS 落盘，读失败不当「不存在」（不得走 Storage）
        store=ArchiveStore(),
        batch_size=args.batch_size,
        categories=categories,
        exclude_audit=True,
        # 契约 §Q5.1（INT-1903）：自动清理默认保留已标记行，整类清须显式 --include-marked
        keep_marked=not args.include_marked,
        dry_run=args.dry_run,
        on_batch=lambda idx, archived, deleted: print(
            f'  批 {idx}: 归档 {archived} 条 / 删除 {deleted} 条', flush=True),
    )
    result = purger.run(cutoff)
    ctx['result'] = result

    if args.dry_run:
        if result.failed:
            _print_failure(result.failure_reason, result)
            return EXIT_ARCHIVE_FAILED
        print(f'[DRY-RUN] 将归档/删除 {result.archived_count} 条；'
              f'当前剩余 {result.remaining_count} 条；未写文件、未删数据', flush=True)
        return EXIT_OK

    print(f'归档条数: {result.archived_count}'
          f'（{result.archived_file_count} 个归档文件，写入 {result.archive_write_count} 次）',
          flush=True)
    print(f'删除条数: {result.deleted_count}', flush=True)
    print(f'剩余条数: {result.remaining_count}', flush=True)
    print(f'耗时: {result.elapsed_seconds:.2f}s', flush=True)

    if result.failed:
        _print_failure(result.failure_reason, result)
        return EXIT_ARCHIVE_FAILED

    if args.vacuum_full:
        _vacuum_full()

    session = get_db_session()
    try:
        size_after = _table_size_bytes(session)
    finally:
        session.close()
    print(f'清理后 pg_total_relation_size(logs): {_format_size(size_after)}'
          f'（清理前 {_format_size(size_before)}）', flush=True)
    if not args.vacuum_full:
        print('未执行 VACUUM FULL：删除只留下 dead tuple，空间不会立刻还给 OS；'
              '如需回收 62MB TOAST 与 heap 空洞，低峰期加 --vacuum-full 重跑', flush=True)

    return EXIT_OK


if __name__ == '__main__':
    sys.exit(main())
