# -*- coding: utf-8 -*-
"""种子/恢复：voice_llm 用例专属参数定义（INT-2095）

背景（INT-2095，方案一致性审计员 2026-10-27 契约通过）：
- 批量设置算法参数弹窗渲染「该算法暂无参数配置」——真实库 `case_algorithm_params`
  里 voice_llm 的 10 行全被 `scripts/migrations/202609/seed_voice_llm.py` Step 3
  软删（注释称「用例参数已迁移到其他表管理」，实际并未迁移）。
- 契约：form-schema 的数据源恒为 `case_algorithm_params`（用例专属参数**定义**，
  `deleted=false`）；取值才写 `test_cases.algorithm_params`（按轮）。删除定义表
  → form-schema 空 → 批量弹窗空态（前端渲染正确，非前端 bug）。
- 本脚本幂等恢复这 10 行：自然键 `(algorithm_type, param_code)`。软删行
  `deleted=false` 回拨并按 §接口 表对齐字段；活行已一致即 SKIP；行被硬删则按
  §接口 表重插。seed_voice_llm.py Step 3 的软删陷阱由 INT-2095 同步修订
  （不再软删 case_params），本脚本补充 2026-10-22 之前已软删的存量数据。

字段口径（与真实库软删行逐字段核对一致，2026-10-27 快照
`scratch/int2095_case_params_before.json`）：
- `annotation_code='voice_llm'`、`field_path='interferers'` 仅 interferers 行有值，
  其余为空（NULL）；min/max/step/unit 全空（NULL）；required/hidden 全 false。

用法：
    python scripts/migrations/202610/seed_voice_llm_case_params_int2095.py           # 预览
    python scripts/migrations/202610/seed_voice_llm_case_params_int2095.py --apply   # 执行

幂等性：重复执行全 SKIP / 0 变更（活行已与 §接口 表一致即不动；软删行只回拨一次）。
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
TABLE = 'case_algorithm_params'

# §接口 表：10 个用例专属参数（自然键 algorithm_type + param_code）。
# 取值来源：真实库软删行（2026-10-27 快照），与 INT-2095 卡面 §接口 表一致；
# label / help_text 取自真实行（重插路径保持展示口径与既有数据一致）。
TARGET_CASE_PARAMS = [
    {
        'param_code': 'interferers',
        'param_name': '干扰人列表',
        'label': '干扰人',
        'param_type': 'json',
        'required': False,
        'default_value': '{}',
        'help_text': '干扰人配置列表',
        'ui_order': 0,
        'hidden': False,
        'scope': 'e2e',
        'min_value': None,
        'max_value': None,
        'step': None,
        'unit': None,
        'annotation_code': 'voice_llm',
        'field_path': 'interferers',
    },
    {
        'param_code': 'record_mode',
        'param_name': '录屏模式',
        'label': '',
        'param_type': 'text',
        'required': False,
        'default_value': '0',
        'help_text': '',
        'ui_order': 1,
        'hidden': False,
        'scope': 'common',
        'min_value': None,
        'max_value': None,
        'step': None,
        'unit': None,
        'annotation_code': None,
        'field_path': None,
    },
    {
        'param_code': 'type',
        'param_name': '拒识场景',
        'label': '拒识场景类型',
        'param_type': 'text',
        'required': False,
        'default_value': None,
        'help_text': '拒识场景(非目标人拒识/目标人非交互意图/环境噪声/用户BC)，按轮从用例取',
        'ui_order': 2,
        'hidden': False,
        'scope': 'common',
        'min_value': None,
        'max_value': None,
        'step': None,
        'unit': None,
        'annotation_code': None,
        'field_path': None,
    },
    {
        'param_code': 'timing',
        'param_name': '拒识时机',
        'label': '拒识发生时机',
        'param_type': 'text',
        'required': False,
        'default_value': None,
        'help_text': '拒识发生时机(回复过程中/静默)，决定行为类别定义和rate计算规则',
        'ui_order': 3,
        'hidden': False,
        'scope': 'common',
        'min_value': None,
        'max_value': None,
        'step': None,
        'unit': None,
        'annotation_code': None,
        'field_path': None,
    },
    {
        'param_code': 'is_interruption',
        'param_name': '是否打断',
        'label': '',
        'param_type': 'text',
        'required': False,
        'default_value': None,
        'help_text': '',
        'ui_order': 4,
        'hidden': False,
        'scope': 'common',
        'min_value': None,
        'max_value': None,
        'step': None,
        'unit': None,
        'annotation_code': None,
        'field_path': None,
    },
    {
        'param_code': 'stop_intent',
        'param_name': '停止指令意图',
        'label': '是否为停止指令轮',
        'param_type': 'switch',
        'required': False,
        'default_value': None,
        'help_text': '显式停止指令标记；模型停止原内容输出即遵从，只回复"好的/我明白了"等确认语同样算遵从',
        'ui_order': 5,
        'hidden': False,
        'scope': 'common',
        'min_value': None,
        'max_value': None,
        'step': None,
        'unit': None,
        'annotation_code': None,
        'field_path': None,
    },
    {
        'param_code': 'is_return_to_topic',
        'param_name': '是否回到原话题',
        'label': '是否回到原话题',
        'param_type': 'switch',
        'required': False,
        'default_value': None,
        'help_text': '标注该轮是否回到原话题（用户打断后模型是否拉回原话题），供 interruption_metrics 评估',
        'ui_order': 6,
        'hidden': False,
        'scope': 'common',
        'min_value': None,
        'max_value': None,
        'step': None,
        'unit': None,
        'annotation_code': None,
        'field_path': None,
    },
    {
        'param_code': 'is_reject',
        'param_name': '是否为拒识内容',
        'label': '是否为拒识内容',
        'param_type': 'switch',
        'required': False,
        'default_value': 'true',
        'help_text': 'True=该轮为拒识内容，参与拒识评估统计；False=非拒识轮，跳过不统计',
        'ui_order': 7,
        'hidden': False,
        'scope': 'common',
        'min_value': None,
        'max_value': None,
        'step': None,
        'unit': None,
        'annotation_code': None,
        'field_path': None,
    },
    {
        'param_code': 'is_single_round',
        'param_name': '单轮拒识',
        'label': '是否为单轮拒识模式',
        'param_type': 'switch',
        'required': False,
        'default_value': 'false',
        'help_text': 'True=单轮拒识(user_wav直接为拒识内容)，False=多轮拒识(user_wav包含意图交互+拒识干扰)',
        'ui_order': 8,
        'hidden': False,
        'scope': 'common',
        'min_value': None,
        'max_value': None,
        'step': None,
        'unit': None,
        'annotation_code': None,
        'field_path': None,
    },
    {
        'param_code': 'correctAnswer',
        'param_name': '参考答案',
        'label': '参考答案',
        'param_type': 'text',
        'required': False,
        'default_value': None,
        'help_text': '环境理解评估的标准答案（如"开关门"），从用例配置读取',
        'ui_order': 9,
        'hidden': False,
        'scope': 'common',
        'min_value': None,
        'max_value': None,
        'step': None,
        'unit': None,
        'annotation_code': None,
        'field_path': None,
    },
]

# 参与「字段是否已与 §接口 表一致」比对的列（不含 deleted / id / created_at / updated_at）
_SPEC_COLUMNS = [
    'param_name', 'label', 'param_type', 'required', 'default_value', 'help_text',
    'ui_order', 'hidden', 'scope', 'min_value', 'max_value', 'step', 'unit',
    'annotation_code', 'field_path',
]


def _same(a, b):
    """NULL 感知相等（NULL == NULL 视为一致；'' 与 NULL 不同）。"""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return a == b


def _row_matches_spec(row, spec):
    return all(_same(row.get(col), spec.get(col)) for col in _SPEC_COLUMNS)


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
        'SELECT id, algorithm_type, param_code, param_name, label, param_type, '
        'required, default_value, help_text, ui_order, hidden, scope, '
        'min_value, max_value, step, unit, annotation_code, field_path, deleted '
        'FROM case_algorithm_params WHERE algorithm_type = %s ORDER BY ui_order, id',
        (ALGORITHM_TYPE,))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def plan_case_params_changes(existing_rows):
    """纯函数：按现存行给出待执行操作（供脚本与单测共用）。

    Args:
        existing_rows: `case_algorithm_params` 里 voice_llm 的全部行（含软删），
            每行是 dict，至少含 param_code / deleted / id 与 _SPEC_COLUMNS。

    Returns:
        list[dict]：`{'op': 'insert'|'restore'|'update'|'skip', 'param_code', ...}`
        - insert：自然键不存在（已被硬删 / 全新库）
        - restore：存在但仅软删（回拨 deleted=false，并按 §接口 表对齐字段）
        - update：存在活行但字段与 §接口 表不一致
        - skip：活行字段已与 §接口 表一致
    """
    by_code = {}
    for row in existing_rows or []:
        code = row.get('param_code')
        if not code:
            continue
        current = by_code.get(code)
        if current is None:
            by_code[code] = row
            continue
        # 同键多行：优先活行；活行已存在时保留首见活行（部分唯一索引保证不重复）
        if current.get('deleted') and not row.get('deleted'):
            by_code[code] = row

    ops = []
    for spec in TARGET_CASE_PARAMS:
        code = spec['param_code']
        row = by_code.get(code)
        if row is None:
            ops.append({'op': 'insert', 'param_code': code})
        elif row.get('deleted'):
            ops.append({'op': 'restore', 'param_code': code, 'id': row.get('id')})
        elif _row_matches_spec(row, spec):
            ops.append({'op': 'skip', 'param_code': code, 'id': row.get('id')})
        else:
            ops.append({'op': 'update', 'param_code': code, 'id': row.get('id')})
    return ops


def _print_rows(title, rows):
    print(f'\n== {title}（case_algorithm_params / {ALGORITHM_TYPE}）==')
    if not rows:
        print('  （空）')
        return
    print(f"  {'id':>4} {'param_code':<16} {'param_type':<7} {'scope':<7} "
          f"{'deleted':<8} {'ui_order':>4} param_name")
    for r in rows:
        print(f"  {r['id']:>4} {r['param_code']:<16} {str(r['param_type']):<7} "
              f"{str(r['scope']):<7} {str(r['deleted']):<8} {str(r['ui_order']):>4} "
              f"{r['param_name']}")


def _apply_ops(cur, ops):
    specs = {s['param_code']: s for s in TARGET_CASE_PARAMS}
    changed = 0
    for op in ops:
        spec = specs[op['param_code']]
        if op['op'] == 'skip':
            print(f"  [SKIP] {op['param_code']} 活行已与 §接口 表一致（id={op.get('id')}）")
            continue
        if op['op'] == 'insert':
            cur.execute(
                'INSERT INTO case_algorithm_params '
                '  (algorithm_type, param_code, param_name, label, param_type, required, '
                '   default_value, help_text, ui_order, hidden, scope, '
                '   min_value, max_value, step, unit, annotation_code, field_path, '
                '   deleted, created_at, updated_at) '
                'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
                'false, NOW(), NOW())',
                (ALGORITHM_TYPE, spec['param_code'], spec['param_name'], spec['label'],
                 spec['param_type'], spec['required'], spec['default_value'],
                 spec['help_text'], spec['ui_order'], spec['hidden'], spec['scope'],
                 spec['min_value'], spec['max_value'], spec['step'], spec['unit'],
                 spec['annotation_code'], spec['field_path']))
            print(f"  [APPLY] INSERT {op['param_code']}（{spec['param_type']}, "
                  f"scope={spec['scope']}, ui_order={spec['ui_order']}）")
            changed += 1
            continue
        # restore / update：字段对齐 + deleted=false
        cur.execute(
            'UPDATE case_algorithm_params '
            'SET param_name = %s, label = %s, param_type = %s, required = %s, '
            '    default_value = %s, help_text = %s, ui_order = %s, hidden = %s, '
            '    scope = %s, min_value = %s, max_value = %s, step = %s, unit = %s, '
            '    annotation_code = %s, field_path = %s, deleted = false, updated_at = NOW() '
            'WHERE id = %s',
            (spec['param_name'], spec['label'], spec['param_type'], spec['required'],
             spec['default_value'], spec['help_text'], spec['ui_order'], spec['hidden'],
             spec['scope'], spec['min_value'], spec['max_value'], spec['step'],
             spec['unit'], spec['annotation_code'], spec['field_path'], op['id']))
        print(f"  [APPLY] {'RESTORE' if op['op'] == 'restore' else 'UPDATE'} "
              f"{op['param_code']}（id={op['id']}）")
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

        ops = plan_case_params_changes(before)
        print(f"\n[{'DRY' if dry_run else 'APPLY'}] 计划 {len(ops)} 项（目标 10 个参数）：")
        for op in ops:
            if op['op'] == 'skip':
                print(f"  - skip {op['param_code']}（活行已一致）")
            elif op['op'] == 'insert':
                print(f"  - insert {op['param_code']}")
            elif op['op'] == 'restore':
                print(f"  - restore {op['param_code']}（软删回拨，id={op.get('id')}）")
            else:
                print(f"  - update {op['param_code']}（活行字段对齐，id={op.get('id')}）")

        if dry_run:
            print('\n[DRY] 未写入；加 --apply 执行')
            return

        changed = _apply_ops(cur, ops)
        conn.commit()
        after = _load_rows(cur)
        _print_rows('执行后', after)
        active = [r for r in after if not r['deleted']]
        print(f'\n[APPLY] 变更 {changed} 行；voice_llm 未删除用例参数 {len(active)} 条'
              f'（幂等：重复执行应全 SKIP / 0 变更）')
        cur.close()
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser(
        description='voice_llm 用例专属参数定义恢复种子（INT-2095）')
    ap.add_argument('--apply', action='store_true', help='执行（默认 dry-run 预览）')
    args = ap.parse_args()
    migrate(dry_run=not args.apply)


if __name__ == '__main__':
    main()
