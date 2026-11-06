# -*- coding: utf-8 -*-
"""迁移脚本：把被测设备与播放设备（音箱）统一关联到同一个实验室

背景：
    ``add_laboratory_tables.py``（202608）只补了 ``laboratories`` 表与各表
    ``lab_id`` 列，从不写数据；``migrate_cases_to_speaker_groups.py``（202610）
    又依赖「逻辑音箱组绑实验室设备」才能完成绑定。存量库里若 ``laboratories``
    为空，``devices`` / ``playback_devices`` 的 ``lab_id`` 全是 NULL，结果：

      - 实验室管理页无数据，设备详情 ``lab_name`` 为 null；
      - 逻辑音箱组只能建组，无法把播放设备绑进组（组内条目 0 条）；
      - 任务按实验室路由/并发执行时无实验室可选。

    本脚本按 ``LAB_NAME``（与 e2e_test_service 注册口径一致，缺省 ``lab-a``）
    确保存在一个可用实验室，并把未归属的设备/播放设备/音箱组条目挂到该实验室。

写入范围（均只改 ``lab_id IS NULL`` 的行，不覆盖人工已分配的实验室）：
    1. ``devices.lab_id``                        未删除设备
    2. ``playback_devices.lab_id``               未删除播放设备
    3. ``playback_speaker_group_items.lab_id``   列 NOT NULL，仅当对应播放设备
       已归属本实验室、且该组内尚无同实验室条目时改写（避免触发
       ``uq_playback_speaker_item_group_lab``）

幂等性：实验室已存在则复用；三类 UPDATE 命中 0 行即 [SKIP]；重复执行无副作用。

用法：
    python scripts/migrations/202611/associate_devices_to_default_lab.py            # 预览
    python scripts/migrations/202611/associate_devices_to_default_lab.py --apply    # 执行
    python scripts/migrations/202611/associate_devices_to_default_lab.py --apply --lab-code lab-b --lab-name LAB-B

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

# 实验室缺省口径：与 docker-compose / .env 的 LAB_NAME 对齐，避免两处漂移
DEFAULT_LAB_CODE = os.environ.get('LAB_NAME', 'lab-a')
DEFAULT_LAB_NAME = os.environ.get('LAB_NAME', 'lab-a').upper()
LAB_STATUS_ACTIVE = 'active'
LAB_DESCRIPTION = '迁移脚本创建：设备与播放设备统一归属实验室'

# 前置对象（表.列）：缺任意一项说明结构迁移未落地，直接失败而不是静默跳过
REQUIRED_COLUMNS = (
    'laboratories.code',
    'devices.lab_id',
    'playback_devices.lab_id',
    'playback_speaker_group_items.lab_id',
)

_UPSERT_LAB_SQL = """
    INSERT INTO laboratories (code, name, status, deleted, description)
    VALUES (%s, %s, %s, false, %s)
    ON CONFLICT DO NOTHING
"""

_GET_LAB_SQL = """
    SELECT id FROM laboratories
     WHERE code = %s AND deleted = false
     ORDER BY id LIMIT 1
"""

_ASSIGN_DEVICES_SQL = """
    UPDATE devices
       SET lab_id = %s, updated_at = now()
     WHERE lab_id IS NULL AND deleted = false
"""

_ASSIGN_PLAYBACK_SQL = """
    UPDATE playback_devices
       SET lab_id = %s, updated_at = now()
     WHERE lab_id IS NULL AND is_deleted = 0
"""

_ASSIGN_SPEAKER_ITEMS_SQL = """
    UPDATE playback_speaker_group_items i
       SET lab_id = %s, updated_at = now()
      FROM playback_devices d
     WHERE i.playback_device_id = d.id
       AND d.lab_id = %s
       AND i.lab_id <> %s
       AND NOT EXISTS (
           SELECT 1 FROM playback_speaker_group_items x
            WHERE x.group_id = i.group_id AND x.lab_id = %s)
"""

_COUNT_SQL = {
    'devices(未归属)': 'SELECT count(*) FROM devices WHERE lab_id IS NULL AND deleted = false',
    'devices(已归属其它实验室)': 'SELECT count(*) FROM devices WHERE lab_id IS NOT NULL AND deleted = false',
    'playback_devices(未归属)': 'SELECT count(*) FROM playback_devices WHERE lab_id IS NULL AND is_deleted = 0',
    'playback_devices(已归属其它实验室)': 'SELECT count(*) FROM playback_devices WHERE lab_id IS NOT NULL AND is_deleted = 0',
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


def _ensure_lab(cur, code, name):
    """返回实验室 id；不存在则创建（并发下以唯一索引兜底再查一次）。"""
    cur.execute(_UPSERT_LAB_SQL, (code, name, LAB_STATUS_ACTIVE, LAB_DESCRIPTION))
    cur.execute(_GET_LAB_SQL, (code,))
    row = cur.fetchone()
    if not row:
        raise RuntimeError(f'实验室 {code!r} 创建后仍查不到（请检查 laboratories 表）')
    return row[0]


def apply(conn, code, name):
    with conn.cursor() as cur:
        cur.execute(f"SET lock_timeout = '{LOCK_TIMEOUT}'")
        lab_id = _ensure_lab(cur, code, name)

        cur.execute(_ASSIGN_DEVICES_SQL, (lab_id,))
        devices = cur.rowcount

        cur.execute(_ASSIGN_PLAYBACK_SQL, (lab_id,))
        playback = cur.rowcount

        cur.execute(_ASSIGN_SPEAKER_ITEMS_SQL, (lab_id, lab_id, lab_id, lab_id))
        speaker_items = cur.rowcount

    conn.commit()
    print(f"[ok] 实验室 code={code!r} name={name!r} id={lab_id}")
    print(f"[ok] devices 更新 {devices} 行 / playback_devices 更新 {playback} 行"
          f" / playback_speaker_group_items 更新 {speaker_items} 行")


def main():
    parser = argparse.ArgumentParser(
        description='设备与播放设备统一关联到同一实验室（默认 dry-run）')
    parser.add_argument('--apply', action='store_true', help='执行迁移')
    parser.add_argument('--lab-code', default=DEFAULT_LAB_CODE,
                        help=f'实验室代码（缺省取 LAB_NAME，当前 {DEFAULT_LAB_CODE!r}）')
    parser.add_argument('--lab-name', default=DEFAULT_LAB_NAME,
                        help=f'实验室名称（缺省 {DEFAULT_LAB_NAME!r}）')
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
        print(f"目标实验室：code={args.lab_code!r} name={args.lab_name!r}")
        _print_counts(conn)

        if not args.apply:
            print('[dry-run] 未修改数据库；加 --apply 执行')
            return 0

        apply(conn, args.lab_code, args.lab_name)
        print('--- 执行后 ---')
        _print_counts(conn)
        return 0
    finally:
        conn.close()


if __name__ == '__main__':
    sys.exit(main())
