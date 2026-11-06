# -*- coding: utf-8 -*-
"""迁移脚本：voice_llm 参考参数定义口径订正（INT-2040）

背景：
- `GenerateReferenceParams` 在真实数据上恒生成 0 条参考参数。两层原因：
  1. 生成器按 `annotation_code` / `annotation_format` 键读 audio_service 的标注，
     而 audio_service 实返键是 `code` / `format`（已在本卡改为 ACL 层归一）；
  2. `algorithm_reference_params` 里 voice_llm 的 7 行定义口径错位。
- 口径依据 `doc/功能设计文档/08_算法配置/参考参数生成器设计文档.md`「AlgorithmReferenceParam /
  AudioAnnotation 字段表」：
    `annotation_code`   = 标注整体 code → AudioAnnotation.code（主库 voice_llm）
    `annotation_format` = 标注载荷格式  → AudioAnnotation.format（主库 json）
    segment 内取哪个字段由 `field_path`（`segments[].<字段>`）承担。
- 库内现值把「segment 里的字段名」当 annotation_code（correct_answer / pause /
  input_lastword / is_return_to_topic），把「segment 字段值类型」当
  annotation_format（text / boolean），两列语义都被混用，导致按 format=json、
  code=voice_llm 过滤时行行不匹配。
- 种子 `scripts/migrations/202609/seed_voice_llm.py` Step 6 有同样的错位、且缺
  `env_type` / `is_reject` 两行；其「已存在则跳过」逻辑对老库无效，因此老库必须由
  本脚本订正（种子只管全新库）。

订正内容（只改这三列，param_type / merge_mode / name / help_text 保留现值）：
    annotation_code   → 'voice_llm'
    annotation_format → 'json'
    field_path        → 'segments[].<code>'

用法：
    python scripts/migrations/202610/fix_voice_llm_reference_params_definitions.py
        # 预览（事务内 UPDATE + 回读 + ROLLBACK，不落库）
    python scripts/migrations/202610/fix_voice_llm_reference_params_definitions.py --apply
        # 真正执行 UPDATE

幂等性：
    按 (algorithm_type, code) 定位这 7 行，只处理取值与目标不一致的行（WHERE 里带
    现值不等判定），订正后重复执行命中 0 行；不新增行、不动 deleted 行、不改其他列。
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

ALGORITHM_TYPE = 'voice_llm'
TARGET_ANNOTATION_CODE = 'voice_llm'
TARGET_ANNOTATION_FORMAT = 'json'

# 7 行定义：(code, field_path)。annotation_code / annotation_format 统一取上面的目标值。
TARGET_ROWS = [
    ('query', 'segments[].query'),
    ('is_reject', 'segments[].is_reject'),
    ('env_type', 'segments[].env_type'),
    ('correct_answer', 'segments[].correct_answer'),
    ('pause', 'segments[].pause'),
    ('input_lastword', 'segments[].input_lastword'),
    ('is_return_to_topic', 'segments[].is_return_to_topic'),
]

SELECT_SQL = """
SELECT id, code, annotation_code, annotation_format, field_path, param_type, merge_mode
FROM algorithm_reference_params
WHERE algorithm_type = %(at)s AND code = %(code)s AND deleted = false
ORDER BY id
"""

UPDATE_SQL = """
UPDATE algorithm_reference_params
SET annotation_code = %(ac)s,
    annotation_format = %(af)s,
    field_path = %(fp)s,
    updated_at = NOW()
WHERE id = %(id)s AND deleted = false
"""


def _needs_fix(row):
    _id, _code, ac, af, fp = row[:5]
    return (ac, af, fp) != (TARGET_ANNOTATION_CODE, TARGET_ANNOTATION_FORMAT, _field_path(_code))


def _field_path(code):
    for row_code, field_path in TARGET_ROWS:
        if row_code == code:
            return field_path
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='INT-2040 voice_llm 参考参数定义口径订正')
    parser.add_argument('--apply', action='store_true',
                        help='真正执行 UPDATE（默认 dry-run，事务内执行后回滚）')
    args = parser.parse_args(argv)

    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    conn.autocommit = True
    cur = conn.cursor()
    try:
        missing = []
        pending = []
        print(f'[{"EXEC" if args.apply else "DRY-RUN"}] 目标行 {len(TARGET_ROWS)} 条（{ALGORITHM_TYPE}）')
        for code, field_path in TARGET_ROWS:
            cur.execute(SELECT_SQL, {'at': ALGORITHM_TYPE, 'code': code})
            rows = cur.fetchall()
            if not rows:
                missing.append(code)
                continue
            for row in rows:
                cur_row = row[:5]
                if _needs_fix(cur_row):
                    pending.append((row, field_path))

        if missing:
            print(f'  未找到（跳过，不新增）：{", ".join(missing)}')

        if not pending:
            print('  待订正行：0（已符合口径，重复执行无变更）')
        else:
            print(f'  待订正行：{len(pending)}')
            print('  id | code | annotation_code → 目标 | annotation_format → 目标 | field_path → 目标 | param_type/merge_mode')
            for row, field_path in pending:
                rid, code, ac, af, fp = row[:5]
                print(f'  {rid} | {code} | {ac!r} → {TARGET_ANNOTATION_CODE!r} | '
                      f'{af!r} → {TARGET_ANNOTATION_FORMAT!r} | {fp!r} → {field_path!r} | '
                      f'{row[5]}/{row[6]}')

        if args.apply:
            changed = 0
            for row, field_path in pending:
                cur.execute(UPDATE_SQL, {
                    'ac': TARGET_ANNOTATION_CODE,
                    'af': TARGET_ANNOTATION_FORMAT,
                    'fp': field_path,
                    'id': row[0],
                })
                changed += cur.rowcount
            print(f'[EXEC] 已更新 {changed} 行')
        else:
            # 显式 BEGIN：psycopg2 在 autocommit=True 下执行 UPDATE 会真正落库，
            # 预览必须先开显式事务再回滚。
            cur.execute('BEGIN')
            try:
                for row, field_path in pending:
                    cur.execute(UPDATE_SQL, {
                        'ac': TARGET_ANNOTATION_CODE,
                        'af': TARGET_ANNOTATION_FORMAT,
                        'fp': field_path,
                        'id': row[0],
                    })
                if pending:
                    cur.execute(
                        'SELECT id, code, annotation_code, annotation_format, field_path '
                        'FROM algorithm_reference_params WHERE id = ANY(%s) ORDER BY id',
                        ([row[0][0] for row in pending],))
                    for r in cur.fetchall():
                        print(f'  [DRY-RUN 事务内回读] {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]}')
            finally:
                cur.execute('ROLLBACK')
            print('[DRY-RUN] 已回滚，未落库（--apply 执行）')
    finally:
        cur.close()
        conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
