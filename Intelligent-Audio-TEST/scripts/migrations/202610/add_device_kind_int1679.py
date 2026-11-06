# -*- coding: utf-8 -*-
"""迁移脚本：device_status_events 补设备类型列 device_kind（INT-1679）

背景（INT-1679 缺陷）：
- INT-1579 的播放设备 restart / reset-config / repair 按契约 §2.1 / §2.5 把控制动作
  写成 device_status_events 的 operation 事件，`device_id` 直接取**播放设备** id；
- 该表此前没有设备类型列，而查询侧按契约 §1.2「只统计测试设备」默认 device_id
  就是测试设备 id（devices 表）。两张表 id 各自自增、真实库已重叠，于是播放设备的
  控制事件会串进同 id 测试设备的状态历史与监控统计；
- 本迁移补 `device_kind`（test / playback），写入侧带 kind，查询侧按 test 过滤。

DDL 与 device_service/infrastructure/persistence/models/device_models.py 的
DeviceStatusEvent 元数据逐列对齐：
    device_kind VARCHAR(20) NOT NULL DEFAULT 'test'（枚举 DeviceKind，INT-1679）

不加索引（评估结论写在这里）：现有 ix_status_event_device_time(device_id, created_at)
已覆盖「按设备 + 时间」与全局按 created_at 排序两条访问路径，device_kind 只是在
同一批命中行上的布尔过滤；播放设备事件每日个位数、基数极低，新增索引没有收益。

步骤（幂等）：
    ① ALTER TABLE device_status_events ADD COLUMN IF NOT EXISTS device_kind
       VARCHAR(20) NOT NULL DEFAULT 'test'
    ② 回填：只修正 INT-1579 上线后写进来的播放设备控制事件
       （device_kind='test' AND source='operation' AND
         detail->>'operation' IN ('restart', 'reset-config', 're-enumerate')）
       依据：测试设备的 DeviceOperation 取值只有 connect / disconnect / reboot /
       shutdown / install_app / uninstall_app，与这三个播放动作值无交集，不会误伤。
       默认 dry-run 只报待回填行数。
    ③ 结构自检（information_schema 回读列类型 / NOT NULL / 默认值）

用法：
    python scripts/migrations/202610/add_device_kind_int1679.py            # 预览
    python scripts/migrations/202610/add_device_kind_int1679.py --apply    # 执行

幂等性：
    列已存在即 SKIP；回填只命中仍为 test 的播放动作行，重复执行命中 0 行。
"""
import argparse
import os
import sys

import psycopg2

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

if not os.environ.get('DATABASE_URL'):
    os.environ['DATABASE_URL'] = os.environ.get(
        'DATABASE_URI',
        'postgresql://intelligent_audio_test:intelligent_audio_test666'
        '@localhost:5432/intelligent_audio_test')

from shared.models.common_enums import (  # noqa: E402
    DeviceKind,
    PlaybackControlAction,
    PlaybackRepairAction,
)

TABLE = 'device_status_events'
COLUMN = 'device_kind'
DEFAULT_COLUMN_TYPE = 'VARCHAR(20)'

# 回填判定：三个播放设备控制动作（reopen-channel 复用 restart 实现，事件记为 restart）
PLAYBACK_CONTROL_OPERATIONS = (
    PlaybackControlAction.RESTART.value,
    PlaybackControlAction.RESET_CONFIG.value,
    PlaybackRepairAction.RE_ENUMERATE.value,
)

COLUMN_DDL = (f'ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS {COLUMN} '
              f"{DEFAULT_COLUMN_TYPE} NOT NULL DEFAULT '{DeviceKind.TEST.value}'")

_BACKFILL_WHERE = (
    f"{COLUMN} = '{DeviceKind.TEST.value}' "
    "AND source = 'operation' "
    "AND detail->>'operation' IN ("
    + ', '.join("'%s'" % value for value in PLAYBACK_CONTROL_OPERATIONS)
    + ')'
)
BACKFILL_SQL = (f"UPDATE {TABLE} SET {COLUMN} = '{DeviceKind.PLAYBACK.value}' "
                f"WHERE {_BACKFILL_WHERE}")
COUNT_SQL = f'SELECT COUNT(*) FROM {TABLE} WHERE {_BACKFILL_WHERE}'
# 列尚未创建时（存量库首次 dry-run）：存量行一律隐式 test，按「source + 动作值」报数
COUNT_SQL_PRE_COLUMN = (
    "SELECT COUNT(*) FROM %s WHERE source = 'operation' AND detail->>'operation' IN ("
    % TABLE
    + ', '.join("'%s'" % value for value in PLAYBACK_CONTROL_OPERATIONS)
    + ')'
)


def is_playback_control_event(event: dict) -> bool:
    """回填判定（纯函数，供单测与脚本共用）：能否确认是播放设备控制事件。

    只有 `source='operation'` 且 `detail.operation` 属于三个播放控制动作值的事件
    才会被回填成 playback —— 测试设备的 DeviceOperation 取值与之无交集。
    """
    if (event.get('source') or '') != 'operation':
        return False
    detail = event.get('detail') or {}
    if not isinstance(detail, dict):
        return False
    return detail.get('operation') in PLAYBACK_CONTROL_OPERATIONS


def _connect():
    from urllib.parse import urlparse
    parsed = urlparse(os.environ['DATABASE_URL'])
    return psycopg2.connect(
        host=parsed.hostname, port=parsed.port or 5432,
        dbname=parsed.path.lstrip('/'), user=parsed.username,
        password=parsed.password)


def _table_exists(cur) -> bool:
    cur.execute(
        'SELECT 1 FROM information_schema.tables WHERE table_name = %s', (TABLE,))
    return cur.fetchone() is not None


def _column_exists(cur) -> bool:
    cur.execute(
        'SELECT 1 FROM information_schema.columns '
        'WHERE table_name = %s AND column_name = %s', (TABLE, COLUMN))
    return cur.fetchone() is not None


def _verify(cur):
    cur.execute(
        'SELECT data_type, character_maximum_length, is_nullable, column_default '
        'FROM information_schema.columns '
        'WHERE table_name = %s AND column_name = %s', (TABLE, COLUMN))
    row = cur.fetchone()
    if not row:
        print(f'[VERIFY][FAIL] {TABLE}.{COLUMN} 不存在')
        return
    data_type, max_length, nullable, default = row
    print(f'[VERIFY] {TABLE}.{COLUMN}: {data_type}({max_length}) '
          f'{"NULL" if nullable == "YES" else "NOT NULL"} DEFAULT {default}')


def migrate(dry_run=True):
    conn = _connect()
    try:
        conn.autocommit = False
        cur = conn.cursor()
        if not _table_exists(cur):
            print(f'[SKIP] 表 {TABLE} 不存在（空库请先 create_all_tables.py）')
            return

        # ① 加列
        if _column_exists(cur):
            print(f'[SKIP] 列 {COLUMN} 已存在')
        else:
            print(f"[{'DRY' if dry_run else 'APPLY'}] {COLUMN_DDL}")
            if not dry_run:
                cur.execute(COLUMN_DDL)
                conn.commit()

        if not _column_exists(cur) and dry_run:
            # 列未创建：存量行一律隐式 test，先按「source + 三个播放动作值」报待回填行数
            cur.execute(COUNT_SQL_PRE_COLUMN)
            print(f'[DRY] 列未创建，跳过回填与自检；按播放控制动作预检待回填 '
                  f'{int(cur.fetchone()[0] or 0)} 行')
            return

        # ② 回填（dry-run 只报数）
        cur.execute(COUNT_SQL)
        pending = int(cur.fetchone()[0] or 0)
        print(f"[{'DRY' if dry_run else 'APPLY'}] 回填：待改 {pending} 行"
              f'（{", ".join(PLAYBACK_CONTROL_OPERATIONS)}）')
        if not dry_run and pending:
            cur.execute(BACKFILL_SQL)
            changed = cur.rowcount
            conn.commit()
            print(f'[APPLY] 回填完成：已改 {changed} 行')

        # ③ 结构自检
        if not dry_run:
            _verify(cur)
        cur.close()
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser(
        description='device_status_events 补设备类型列 device_kind（INT-1679）')
    ap.add_argument('--apply', action='store_true', help='执行（默认 dry-run 预览）')
    args = ap.parse_args()
    migrate(dry_run=not args.apply)


if __name__ == '__main__':
    main()
