# -*- coding: utf-8 -*-
"""迁移脚本：为每个播放设备（音箱）补建同名逻辑音箱组并绑定到其实验室

背景：
    ``playback_speaker_groups``（逻辑音箱）是"物理位置"的抽象，用例只引用
    逻辑音箱，不再直接引用实体播放设备。存量库常见两种缺口：

      - 有播放设备但一个逻辑音箱组都没有；
      - 组建了但 ``playback_speaker_group_items`` 为空（播放设备没 ``lab_id``
        时无法落"组—实验室—设备"条目），组无法被任务解析到实体音箱。

    本脚本按"组名 = 播放设备名"补齐：每个未删除的播放设备，确保存在同名
    逻辑音箱组，并写入 ``(group_id, lab_id, playback_device_id)`` 组内条目。
    同名设备（不同实验室的同一物理位置）共用一个逻辑音箱组，与
    ``migrate_cases_to_speaker_groups.py`` 的建组口径一致。

前置：
    播放设备需先归属实验室（``playback_devices.lab_id`` 非空），否则无法写
    组内条目（``playback_speaker_group_items.lab_id`` NOT NULL）。缺省实验室
    关联见 ``202611/associate_devices_to_default_lab.py``。

幂等性：
    - 组按名称复用（已有同名组则不再新建）；
    - 设备已有组内条目则 [SKIP]；``uq_playback_speaker_item_device`` 保证一台
      设备只在一个组里；
    - 若同名组在该实验室已有其它设备条目（``uq_playback_speaker_item_group_lab``），
      跳过并报告，不覆盖既有绑定；
    - 重复执行命中 0 行，无副作用。

用法：
    python scripts/migrations/202611/seed_playback_speaker_groups.py            # 预览
    python scripts/migrations/202611/seed_playback_speaker_groups.py --apply    # 执行

退出码：0 完成/无需变更；1 前置缺失或执行失败。
"""
import argparse
import os
import sys

import psycopg2

if not os.environ.get('DATABASE_URL'):
    os.environ['DATABASE_URL'] = os.environ.get(
        'DATABASE_URI',
        'postgresql://intelligent_audio_test:intelligent_audio_test666'
        '@localhost:5432/intelligent_audio_test')

LOCK_TIMEOUT = '10s'

# 与播放设备名同口径；playback_speaker_groups.name 为 VARCHAR(100)
GROUP_NAME_MAX_LEN = 100
AUTO_GROUP_DESCRIPTION = '由播放设备名称自动创建'

REQUIRED_COLUMNS = (
    'playback_devices.lab_id',
    'playback_devices.is_deleted',
    'playback_speaker_groups.name',
    'playback_speaker_group_items.group_id',
    'playback_speaker_group_items.lab_id',
    'playback_speaker_group_items.playback_device_id',
)

_SELECT_DEVICES_SQL = """
    SELECT id, name, lab_id
      FROM playback_devices
     WHERE is_deleted = 0
     ORDER BY lab_id NULLS LAST, id
"""

_SELECT_GROUP_BY_NAME_SQL = """
    SELECT id FROM playback_speaker_groups
     WHERE name = %s ORDER BY id LIMIT 1
"""

_INSERT_GROUP_SQL = """
    INSERT INTO playback_speaker_groups (name, description, created_at, updated_at)
    VALUES (%s, %s, now(), now())
    RETURNING id
"""

_SELECT_ITEM_BY_DEVICE_SQL = """
    SELECT group_id, lab_id FROM playback_speaker_group_items
     WHERE playback_device_id = %s
"""

_SELECT_ITEM_BY_GROUP_LAB_SQL = """
    SELECT id FROM playback_speaker_group_items
     WHERE group_id = %s AND lab_id = %s
"""

_INSERT_ITEM_SQL = """
    INSERT INTO playback_speaker_group_items
        (group_id, lab_id, playback_device_id, created_at, updated_at)
    VALUES (%s, %s, %s, now(), now())
"""

_COUNT_SQL = {
    'playback_devices(在用)': 'SELECT count(*) FROM playback_devices WHERE is_deleted = 0',
    'playback_devices(无 lab_id)': 'SELECT count(*) FROM playback_devices WHERE is_deleted = 0 AND lab_id IS NULL',
    'playback_speaker_groups(总)': 'SELECT count(*) FROM playback_speaker_groups',
    'playback_speaker_group_items(总)': 'SELECT count(*) FROM playback_speaker_group_items',
}


def _connect():
    return psycopg2.connect(os.environ['DATABASE_URL'])


def _missing_columns(cur):
    cur.execute(
        """
        SELECT table_name || '.' || column_name
          FROM information_schema.columns
         WHERE table_schema = 'public'
           AND (table_name || '.' || column_name) = ANY(%s)
        """,
        (list(REQUIRED_COLUMNS),))
    present = {row[0] for row in cur.fetchall()}
    return [c for c in REQUIRED_COLUMNS if c not in present]


def _print_counts(conn):
    with conn.cursor() as cur:
        for label, sql in _COUNT_SQL.items():
            cur.execute(sql)
            print(f"[state] {label}: {cur.fetchone()[0]}")


def _ensure_group(cur, name, stats):
    cur.execute(_SELECT_GROUP_BY_NAME_SQL, (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(_INSERT_GROUP_SQL, (name, AUTO_GROUP_DESCRIPTION))
    stats['groups_created'] += 1
    return cur.fetchone()[0]


def apply(conn):
    stats = {'groups_created': 0, 'items_created': 0, 'items_skipped': 0,
             'unbound': [], 'nameless': [], 'conflicts': []}
    with conn.cursor() as cur:
        cur.execute(f"SET lock_timeout = '{LOCK_TIMEOUT}'")
        cur.execute(_SELECT_DEVICES_SQL)
        devices = cur.fetchall()

        for device_id, raw_name, lab_id in devices:
            name = (raw_name or '').strip()[:GROUP_NAME_MAX_LEN]
            if not name:
                stats['nameless'].append(device_id)
                continue
            if lab_id is None:
                stats['unbound'].append(device_id)
                continue

            group_id = _ensure_group(cur, name, stats)

            cur.execute(_SELECT_ITEM_BY_DEVICE_SQL, (device_id,))
            existing = cur.fetchone()
            if existing:
                stats['items_skipped'] += 1
                if existing[1] != lab_id:
                    stats['conflicts'].append((device_id, group_id, existing[1]))
                continue

            cur.execute(_SELECT_ITEM_BY_GROUP_LAB_SQL, (group_id, lab_id))
            if cur.fetchone():
                # 同名组在该实验室已被别的设备占用：uq_playback_speaker_item_group_lab
                # 冲突，不覆盖既有绑定
                stats['conflicts'].append((device_id, group_id, lab_id))
                continue

            cur.execute(_INSERT_ITEM_SQL, (group_id, lab_id, device_id))
            stats['items_created'] += 1

    conn.commit()

    print(f"[ok] 新建逻辑音箱组 {stats['groups_created']} 个；"
          f"新增组内条目 {stats['items_created']} 条；已存在跳过 {stats['items_skipped']} 条")
    if stats['nameless']:
        print(f"[WARN] 无名播放设备跳过（id）: {stats['nameless']}")
    if stats['unbound']:
        print(f"[WARN] 未归属实验室的播放设备跳过（id）: {stats['unbound']}；"
              "先执行 202611/associate_devices_to_default_lab.py")
    if stats['conflicts']:
        print(f"[WARN] 组内实验室/设备占用冲突跳过（device_id, group_id, lab_id）: "
              f"{stats['conflicts']}")


def main():
    parser = argparse.ArgumentParser(
        description='播放设备 → 同名逻辑音箱组绑定（默认 dry-run）')
    parser.add_argument('--apply', action='store_true', help='执行迁移')
    args = parser.parse_args()

    conn = _connect()
    try:
        with conn.cursor() as cur:
            missing = _missing_columns(cur)
        if missing:
            print(f"[ABORT] 缺少结构对象：{', '.join(missing)}；"
                  "请先执行 scripts/migrations/202608/add_laboratory_tables.py")
            return 1

        print(f"目标库：{os.environ['DATABASE_URL'].rsplit('@', 1)[-1]}")
        _print_counts(conn)

        if not args.apply:
            with conn.cursor() as cur:
                cur.execute(_SELECT_DEVICES_SQL)
                devices = cur.fetchall()
            pending = [d for d in devices if (d[1] or '').strip() and d[2] is not None]
            print(f"[dry-run] 参与绑定 {len(pending)} 台播放设备；未修改数据库，"
                  "加 --apply 执行")
            return 0

        apply(conn)
        print('--- 执行后 ---')
        _print_counts(conn)
        return 0
    finally:
        conn.close()


if __name__ == '__main__':
    sys.exit(main())
