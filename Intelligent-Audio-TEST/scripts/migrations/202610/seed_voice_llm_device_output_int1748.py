# -*- coding: utf-8 -*-
"""种子：voice_llm 设备输出声明修正（INT-1748 / C3）

背景（C0 = INT-1745 裁定 2/3，需求规划师 2026-10-24 种子分工）：

`rounds` 轮内子键的 `param_type` 与音频路径归一由设备输出声明
（`algorithm_device_params(direction=output)`）解析（设备声明打底、API 声明覆盖）。
主库 voice_llm 的设备声明有两处缺口，导致改造后结果展示与改造前硬编码口径不一致：

1. **缺 `record_file`**：改造前轮内键的类型取 `shared/constants/device_fields.py`
   的 `DEVICE_FIELDS`（`record_file: audio_file`）；声明表里没有该参数，
   策略按「键集合来自配置」跳过它，4467 条历史结果的完整录音路径整段丢失。
2. **`user_wav` / `ai_wav` 的 `param_type` 是 `text`**：改造前 `DEVICE_FIELDS`
   是 `audio_file`，类型不同还会跳过音频路径归一（`normalize_audio_path_fn`），
   同一批结果的价值与类型双降级。

本脚本只动这一张表（`source='api'` 评估映射与 `algorithm_api_params` 的 7 条
输出声明归 C1 / INT-1746，本脚本不重复占，避免同表两份种子）。

本脚本的配置
------------
A. 新增 `(voice_llm, record_file, output)`：`param_type=audio_file`，
   `ui_order=15`（排在 user_wav 13 / ai_wav 14 之后，不插队既有声明）。
B. 改 `(voice_llm, user_wav|ai_wav, output)` 的 `param_type`：`text` → `audio_file`。

`label` 一律留空（NULL）：轮内展示名按策略回落为 `{param_code} (第N轮)`，
与改造前硬编码口径一致；`param_name` 保持既有中文显示名不动。

幂等性：按 `(algorithm_type, param_code, direction)` 自然键比对（含软删行）——
已存在且类型正确即 SKIP；软删行恢复 `deleted=false` 并按目标类型改写；
重复执行不报错、不产生重复行。默认 dry-run，`--apply` 才写库。

用法：
    python scripts/migrations/202610/seed_voice_llm_device_output_int1748.py           # 预览
    python scripts/migrations/202610/seed_voice_llm_device_output_int1748.py --apply   # 执行
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

ALGORITHM_TYPE = 'voice_llm'
DIRECTION = 'output'
TABLE = 'algorithm_device_params'

# A 段：新增的设备输出声明（record_file 在改造前由 DEVICE_FIELDS 提供类型）
NEW_DEVICE_OUTPUT = [
    {
        'param_code': 'record_file',
        'param_name': '录音文件路径',
        'label': None,
        'param_type': 'audio_file',
        'ui_order': 15,
        'required': False,
        'hidden': False,
    },
]

# B 段：参数类型修正（改造前 DEVICE_FIELDS: user_wav / ai_wav = audio_file）
TYPE_FIXES = {
    'user_wav': 'audio_file',
    'ai_wav': 'audio_file',
}


def plan_device_output_changes(existing_rows):
    """纯函数：按现存声明行给出待执行操作（供脚本与单测共用）。

    Args:
        existing_rows: 每行是 dict，至少含 param_code / param_type / deleted
            （`algorithm_device_params` 在 (voice_llm, *, output) 下的全部行，含软删）

    Returns:
        list[dict]：`{'op': 'insert'|'update'|'restore'|'skip', 'param_code', ...}`
        - insert：声明不存在
        - restore：存在但已软删（恢复并按目标类型改写）
        - update：存在但 param_type 与目标不一致
        - skip：已存在且类型正确
    """
    by_code = {}
    for row in existing_rows or []:
        code = row.get('param_code')
        if not code:
            continue
        # 同键多行时优先活行，避免把软删行当成主行
        current = by_code.get(code)
        if current is None or (current.get('deleted') and not row.get('deleted')):
            by_code[code] = row

    ops = []
    for decl in NEW_DEVICE_OUTPUT:
        code = decl['param_code']
        row = by_code.get(code)
        if row is None:
            ops.append({'op': 'insert', 'param_code': code, 'param_type': decl['param_type']})
        elif row.get('deleted'):
            ops.append({'op': 'restore', 'param_code': code, 'param_type': decl['param_type'],
                        'id': row.get('id')})
        elif (row.get('param_type') or '') != decl['param_type']:
            ops.append({'op': 'update', 'param_code': code, 'param_type': decl['param_type'],
                        'from_param_type': row.get('param_type'), 'id': row.get('id')})
        else:
            ops.append({'op': 'skip', 'param_code': code, 'param_type': decl['param_type'],
                        'id': row.get('id')})

    for code, target_type in TYPE_FIXES.items():
        row = by_code.get(code)
        if row is None:
            # 声明缺失：不在这里凭空造行（param_name / ui_order 属数据侧口径），
            # 只提示，避免脚本猜测既有声明的展示名
            ops.append({'op': 'missing', 'param_code': code, 'param_type': target_type})
        elif row.get('deleted'):
            ops.append({'op': 'restore', 'param_code': code, 'param_type': target_type,
                        'id': row.get('id')})
        elif (row.get('param_type') or '') != target_type:
            ops.append({'op': 'update', 'param_code': code, 'param_type': target_type,
                        'from_param_type': row.get('param_type'), 'id': row.get('id')})
        else:
            ops.append({'op': 'skip', 'param_code': code, 'param_type': target_type,
                        'id': row.get('id')})
    return ops


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


def _load_rows(cur):
    cur.execute(
        'SELECT id, param_code, param_name, label, param_type, ui_order, deleted '
        'FROM algorithm_device_params '
        'WHERE algorithm_type = %s AND direction = %s '
        'ORDER BY ui_order, id', (ALGORITHM_TYPE, DIRECTION))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _print_rows(title, rows):
    print(f'\n== {title}（algorithm_device_params / {ALGORITHM_TYPE} / {DIRECTION}）==')
    if not rows:
        print('  （空）')
        return
    print(f"  {'id':>4} {'param_code':<14} {'param_type':<11} {'ui_order':>8} "
          f"{'deleted':<8} param_name")
    for r in rows:
        print(f"  {r['id']:>4} {r['param_code']:<14} {str(r['param_type']):<11} "
              f"{str(r['ui_order']):>8} {str(r['deleted']):<8} {r['param_name']}")


def _apply_ops(cur, ops):
    changed = 0
    decls = {d['param_code']: d for d in NEW_DEVICE_OUTPUT}
    for op in ops:
        kind = op['op']
        if kind == 'skip':
            print(f"  [SKIP] {op['param_code']} 已是 {op['param_type']}（id={op.get('id')}）")
            continue
        if kind == 'missing':
            print(f"  [WARN] {op['param_code']} 声明缺失，本脚本不新增（需人工确认展示名）")
            continue
        if kind == 'insert':
            decl = decls[op['param_code']]
            cur.execute(
                'INSERT INTO algorithm_device_params '
                '  (algorithm_type, param_code, param_name, label, param_type, direction, '
                '   required, ui_order, hidden, deleted, created_at, updated_at) '
                'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, false, NOW(), NOW())',
                (ALGORITHM_TYPE, decl['param_code'], decl['param_name'], decl['label'],
                 decl['param_type'], DIRECTION, decl['required'], decl['ui_order'],
                 decl['hidden']))
            print(f"  [APPLY] INSERT {op['param_code']} ({op['param_type']}, "
                  f"ui_order={decl['ui_order']})")
            changed += 1
            continue
        # update / restore
        cur.execute(
            'UPDATE algorithm_device_params '
            'SET param_type = %s, deleted = false, updated_at = NOW() '
            'WHERE id = %s', (op['param_type'], op['id']))
        if kind == 'restore':
            print(f"  [APPLY] RESTORE {op['param_code']} → {op['param_type']}（id={op['id']}）")
        else:
            print(f"  [APPLY] UPDATE {op['param_code']} param_type "
                  f"{op.get('from_param_type')} → {op['param_type']}（id={op['id']}）")
        changed += 1
    return changed


def migrate(dry_run=True):
    conn = _connect()
    try:
        cur = conn.cursor()
        if not _table_exists(cur):
            print(f'[SKIP] 表 {TABLE} 不存在（空库请先 create_all_tables.py）')
            return

        before = _load_rows(cur)
        _print_rows('执行前', before)

        ops = plan_device_output_changes(before)
        print(f"\n[{'DRY' if dry_run else 'APPLY'}] 计划 {len(ops)} 项：")
        for op in ops:
            if op['op'] == 'update':
                print(f"  - update {op['param_code']}: "
                      f"{op.get('from_param_type')} → {op['param_type']}")
            elif op['op'] == 'insert':
                print(f"  - insert {op['param_code']}: {op['param_type']}")
            elif op['op'] == 'restore':
                print(f"  - restore {op['param_code']}: {op['param_type']}")
            elif op['op'] == 'missing':
                print(f"  - [WARN] missing {op['param_code']}（脚本不新增）")
            else:
                print(f"  - skip {op['param_code']}（已是 {op['param_type']}）")

        if dry_run:
            print('\n[DRY] 未写入；加 --apply 执行')
            return

        changed = _apply_ops(cur, ops)
        conn.commit()
        after = _load_rows(cur)
        _print_rows('执行后', after)
        print(f'\n[APPLY] 变更 {changed} 行（幂等：重复执行为 0）')
        cur.close()
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser(
        description='voice_llm 设备输出声明修正种子（INT-1748）')
    ap.add_argument('--apply', action='store_true', help='执行（默认 dry-run 预览）')
    args = ap.parse_args()
    migrate(dry_run=not args.apply)


if __name__ == '__main__':
    main()
