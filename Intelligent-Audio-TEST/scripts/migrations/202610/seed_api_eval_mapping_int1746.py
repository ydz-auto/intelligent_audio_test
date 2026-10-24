# -*- coding: utf-8 -*-
"""种子：voice_llm 的 API 评估映射 + API 输出声明（INT-1746 / C1）

背景（C0 = INT-1745 裁定 1/3，2026-10-24）：
评估侧只按 ``rounds[i].output.get(target_param)`` 取值，映射责任在执行侧。
但 voice_llm 在真实库上**两件配置都缺**，所以 API 用例走 llm_judge 维度时
入参恒空：

1. ``algorithm_api_params``（direction=output）没有文本输出声明 ——
   执行侧 ``shared/utils/api_output_extractor.py`` 声明表优先，voice_llm 只有
   ``response_audio``（audio_file），提取不出回复文本；
2. ``param_mappings`` 没有 ``source='api'`` 的评估映射 ——
   voice_llm 只有 ``reference``（correct_answer / query）与 ``device``
   （question / answer）两类，API 链执行侧拿不到 target_param。

``FieldMappingQueryHandler.get_field_definitions`` 只把「source_param 能在某个
参数表里查到」的映射放进 ``original.evaluation.output``，所以两者缺一不可：
只补映射（无声明）→ 提取不到值；只补声明（无映射）→ 全等兜底出的是
param_code 键，不等于维度的 target_param。

本脚本补的配置
--------------
A. ``algorithm_api_params``：(voice_llm, answer, text, output)
   —— ``field_path`` 留空（NULL）。文本型 + 空路径的字段在响应里取不到时，
   执行侧按轮次规范文本（HTTP 链 ``answer_text`` / WS 聚合 ``text``）兜底，
   三条 API 链共用这一份声明。
B. ``param_mappings``：(voice_llm, source=api, source_param=answer,
   target_param=answer, transform_type=none)，逐条写给所有未删除的
   ``task_type_code='llm_judge'`` 维度（param_mappings 的 dimension_id 作用域
   是维度，不是算法）。

不动的部分
----------
``question`` / ``query`` / ``correct_answer`` 仍走既有 reference（correct_answer
/ query）与 device（question）映射，本脚本不新增它们的 api 映射——避免同一
target_param 被两个来源争用。

幂等性：按 ``uq_algorithm_api_param_direction`` / ``uq_algorithm_source_to_dimension``
的自然键比对，已存在即 SKIP；重复执行不报错、不产生重复行。

用法：
    python scripts/migrations/202610/seed_api_eval_mapping_int1746.py            # 预览
    python scripts/migrations/202610/seed_api_eval_mapping_int1746.py --apply    # 执行

前置：``dimensions`` 里必须已有未删除的 llm_judge 维度
（``202609/seed_llm_judge_dimension.py``）。没有该维度时本脚本只补 A 段并提示。
"""
import argparse
import os
import sys

from sqlalchemy import create_engine, text

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

ALGORITHM_TYPE = 'voice_llm'

# A 段：API 输出声明（文本型、field_path 留空 → 空值时按轮次规范文本兜底）
API_OUTPUT_DECL = {
    'algorithm_type': ALGORITHM_TYPE,
    'param_code': 'answer',
    'param_name': '回复文本',
    'param_type': 'text',
    'direction': 'output',
    'required': False,
    'ui_order': 22,
    'hidden': False,
}

# B 段：评估映射（source='api'）
EVAL_MAPPING = {
    'algorithm_type': ALGORITHM_TYPE,
    'source': 'api',
    'source_direction': 'output',
    'source_param': 'answer',
    'target_param': 'answer',
    'transform_type': 'none',
}


def _database_url():
    return os.environ.get('DATABASE_URL') or os.environ.get(
        'DATABASE_URI',
        'postgresql://intelligent_audio_test:intelligent_audio_test666'
        '@localhost:5432/intelligent_audio_test')


def _table_exists(conn, name):
    return conn.execute(text(
        'SELECT 1 FROM information_schema.tables WHERE table_name = :name'
    ), {'name': name}).fetchone() is not None


def _seed_api_output_decl(conn, dry_run):
    """A 段：algorithm_api_params(direction=output) 补 voice_llm.answer"""
    if not _table_exists(conn, 'algorithm_api_params'):
        print('[SKIP] 表 algorithm_api_params 不存在（空库请先 create_all_tables.py）')
        return False

    decl = API_OUTPUT_DECL
    existing = conn.execute(text(
        'SELECT id, param_type, deleted FROM algorithm_api_params '
        'WHERE algorithm_type = :at AND param_code = :pc AND direction = :dir '
        '  AND deleted = false'
    ), {'at': decl['algorithm_type'], 'pc': decl['param_code'],
        'dir': decl['direction']}).fetchone()

    if existing:
        print(f"[SKIP] 输出声明 {decl['algorithm_type']}.{decl['param_code']}"
              f"（{decl['direction']}）已存在 id={existing[0]} "
              f"param_type={existing[1]}")
        if existing[1] != decl['param_type']:
            print(f"  [WARN] 存量 param_type={existing[1]} 与种子 "
                  f"{decl['param_type']} 不一致；不改写存量行，请人工确认")
        return False

    print(f"[{'DRY' if dry_run else 'APPLY'}] INSERT algorithm_api_params "
          f"{decl['algorithm_type']}.{decl['param_code']} "
          f"({decl['param_type']}, {decl['direction']})")
    if dry_run:
        return False

    conn.execute(text(
        'INSERT INTO algorithm_api_params '
        '  (algorithm_type, param_code, param_name, param_type, direction, '
        '   required, ui_order, hidden, deleted, created_at, updated_at) '
        'VALUES '
        '  (:at, :pc, :pn, :pt, :dir, :req, :uo, :hidden, false, NOW(), NOW())'
    ), {'at': decl['algorithm_type'], 'pc': decl['param_code'],
        'pn': decl['param_name'], 'pt': decl['param_type'],
        'dir': decl['direction'], 'req': decl['required'],
        'uo': decl['ui_order'], 'hidden': decl['hidden']})
    return True


def _seed_param_mappings(conn, dry_run):
    """B 段：param_mappings 补 voice_llm 的 source='api' 映射（逐维度）"""
    if not _table_exists(conn, 'param_mappings') or not _table_exists(conn, 'dimensions'):
        print('[SKIP] 表 param_mappings / dimensions 不存在')
        return 0

    dimension_ids = [row[0] for row in conn.execute(text(
        "SELECT id FROM dimensions "
        "WHERE task_type_code = 'llm_judge' AND deleted = false "
        "ORDER BY id"
    )).fetchall()]

    if not dimension_ids:
        print("[SKIP] 未找到未删除的 llm_judge 维度；先执行 "
              "202609/seed_llm_judge_dimension.py 再重跑本脚本")
        return 0

    m = EVAL_MAPPING
    inserted = 0
    for dim_id in dimension_ids:
        existing = conn.execute(text(
            'SELECT id FROM param_mappings '
            'WHERE algorithm_type = :at AND source = :src '
            '  AND source_param = :sp AND dimension_id = :did AND deleted = false'
        ), {'at': m['algorithm_type'], 'src': m['source'],
            'sp': m['source_param'], 'did': dim_id}).fetchone()

        if existing:
            print(f"[SKIP] 映射 {m['source']}.{m['source_param']} → "
                  f"{m['target_param']}（dimension_id={dim_id}）已存在 "
                  f"id={existing[0]}")
            continue

        print(f"[{'DRY' if dry_run else 'APPLY'}] INSERT param_mappings "
              f"{m['source']}.{m['source_param']} → {m['target_param']} "
              f"（dimension_id={dim_id}）")
        if dry_run:
            continue

        conn.execute(text(
            'INSERT INTO param_mappings '
            '  (algorithm_type, source, source_direction, source_param, '
            '   dimension_id, target_param, transform_type, '
            '   deleted, created_at, updated_at) '
            'VALUES '
            '  (:at, :src, :sd, :sp, :did, :tp, :tt, false, NOW(), NOW())'
        ), {'at': m['algorithm_type'], 'src': m['source'],
            'sd': m['source_direction'], 'sp': m['source_param'],
            'did': dim_id, 'tp': m['target_param'], 'tt': m['transform_type']})
        inserted += 1
    return inserted


def migrate(dry_run=True):
    engine = create_engine(_database_url())
    with engine.begin() as conn:
        print(f"=== A 段：voice_llm API 输出声明 ({'DRY' if dry_run else 'APPLY'}) ===")
        _seed_api_output_decl(conn, dry_run)
        print(f"\n=== B 段：voice_llm source=api 评估映射 ({'DRY' if dry_run else 'APPLY'}) ===")
        inserted = _seed_param_mappings(conn, dry_run)
        if not dry_run:
            print(f"\n[APPLY] param_mappings 新增 {inserted} 条")
        else:
            print("\n[DRY] 未写入；加 --apply 执行")


def main():
    ap = argparse.ArgumentParser(
        description='voice_llm 的 API 评估映射 + API 输出声明种子（INT-1746）')
    ap.add_argument('--apply', action='store_true', help='执行（默认 dry-run 预览）')
    args = ap.parse_args()
    migrate(dry_run=not args.apply)


if __name__ == '__main__':
    main()
