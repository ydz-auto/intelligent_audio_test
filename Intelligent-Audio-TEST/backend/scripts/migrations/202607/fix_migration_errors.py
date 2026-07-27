# -*- coding: utf-8 -*-
"""
修复 202606/202607 迁移脚本的错误
===================================

问题汇总：
1. migrate_config_to_rounds.py:
   - 把 algorithm_params / reference_params 塞进 config.rounds[] 里
     但新模型中这两个是独立列，不在 config 中
   - 把独立列 algorithm_params / reference_params 设为 NULL，数据丢失
   - 参考参数文件路径用 static/ref_params/{case_id}_round_{n}.json
     但新代码用 static/case_result/{case_id}/round_{n}.json

2. migrate_algo_ref_to_columns.py:
   - 试图从 config.rounds[] 剥离回独立列，方向正确但路径格式不对
   - 参考参数文件路径仍用旧的 static/ref_params/ 格式

3. drop_testcase_deprecated_columns.py:
   - 删除了 algorithm_params 和 reference_params 列
     但新模型中这两个列仍然存在且是核心字段

4. update_ref_params_paths.py:
   - 路径替换目标错误，应为 static/case_result/{case_id}/round_{n}.json

5. split_testcase_by_type.py:
   - 用 CAST(:config AS jsonb) 但列类型是 JSON
   - INSERT 语句引用了新模型中不存在的列

修复策略（按顺序执行）：
Step 1: 恢复 test_cases.algorithm_params 和 reference_params 列（如被删除）
Step 2: 从 config.rounds[] 中剥离 algorithmParams / referenceParamsPath 回独立列
Step 3: 修正参考参数文件路径格式
Step 4: 清理 config.rounds[] 中的残留字段
Step 5: 修正 test_type 列（如缺失则补建）

用法:
    python fix_migration_errors.py              # 正式执行
    python fix_migration_errors.py --dry-run    # 仅预览
    python fix_migration_errors.py --step 3     # 仅执行第 3 步

依赖:
    pip install sqlalchemy psycopg2-binary
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta

from sqlalchemy import create_engine, text

# ========================================================================
# 配置
# ========================================================================

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666'
    '@localhost:5432/intelligent_audio_test'
)

UTC8 = timezone(timedelta(hours=8))

# 参考参数文件新路径根目录（与 reference_params_generator.py 一致）
REF_PARAMS_BASE_DIR = os.path.join('static', 'case_result')


# ========================================================================
# 辅助函数
# ========================================================================

def _col_exists(conn, table, column):
    """检查列是否已存在"""
    result = conn.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :table AND column_name = :column"
    ), {"table": table, "column": column})
    return result.fetchone() is not None


def _index_exists(conn, index_name):
    """检查索引是否已存在"""
    result = conn.execute(text(
        "SELECT 1 FROM pg_indexes WHERE indexname = :name"
    ), {"name": index_name})
    return result.fetchone() is not None


def _exec_ddl(conn, sql, success_msg, skip_msg):
    """在独立 SAVEPOINT 中执行 DDL"""
    savepoint = conn.begin_nested()
    try:
        conn.execute(text(sql))
        savepoint.commit()
        print(f"  [OK] {success_msg}")
    except Exception as e:
        savepoint.rollback()
        msg = str(e).lower()
        if 'already' in msg or 'duplicate' in msg or 'exists' in msg:
            print(f"  [SKIP] {skip_msg}")
        else:
            raise


def _new_ref_path(case_id, round_number):
    """生成新的参考参数文件路径（与 reference_params_generator.py 一致）"""
    return os.path.join(REF_PARAMS_BASE_DIR, case_id, f'round_{round_number}.json')


def _old_to_new_path(old_path, case_id, round_number):
    """将旧路径转换为新路径"""
    if not old_path:
        return None
    # 如果已经是新格式，直接返回
    if 'case_result' in old_path:
        return old_path
    # 旧格式: static/ref_params/{case_id}_round_{n}.json 或 backend/data/ref_params/...
    return _new_ref_path(case_id, round_number)


# ========================================================================
# Step 1: 恢复独立列
# ========================================================================

def step1_restore_columns(engine, dry_run=False):
    """恢复 test_cases.algorithm_params 和 reference_params 列"""
    print("\n" + "=" * 60)
    print("Step 1: 恢复 test_cases.algorithm_params 和 reference_params 列")
    print("=" * 60)

    if dry_run:
        with engine.connect() as conn:
            algo_exists = _col_exists(conn, 'test_cases', 'algorithm_params')
            ref_exists = _col_exists(conn, 'test_cases', 'reference_params')
            print(f"  [DRY-RUN] algorithm_params 列存在: {algo_exists}")
            print(f"  [DRY-RUN] reference_params 列存在: {ref_exists}")
            return

    with engine.begin() as conn:
        # 检查并恢复 algorithm_params 列
        if not _col_exists(conn, 'test_cases', 'algorithm_params'):
            conn.execute(text(
                "ALTER TABLE test_cases ADD COLUMN algorithm_params JSON"
            ))
            print("  [OK] 新增列: test_cases.algorithm_params (JSON)")
        else:
            print("  [SKIP] algorithm_params 列已存在")

        # 检查并恢复 reference_params 列
        if not _col_exists(conn, 'test_cases', 'reference_params'):
            conn.execute(text(
                "ALTER TABLE test_cases ADD COLUMN reference_params JSON"
            ))
            print("  [OK] 新增列: test_cases.reference_params (JSON)")
        else:
            print("  [SKIP] reference_params 列已存在")


# ========================================================================
# Step 2: 从 config.rounds[] 剥离到独立列
# ========================================================================

def step2_extract_from_rounds(engine, dry_run=False):
    """从 config.rounds[] 中剥离 algorithm_params / reference_params_path 到独立列"""
    print("\n" + "=" * 60)
    print("Step 2: 从 config.rounds[] 剥离 algorithm_params / reference_params_path")
    print("=" * 60)

    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT id, config, algorithm_params, reference_params "
            "FROM test_cases WHERE deleted = false"
        )).fetchall()

    total = len(rows)
    migrated = 0
    skipped = 0
    errors = 0

    print(f"  共 {total} 条用例待检查\n")

    for row in rows:
        case_id = row[0]
        config = row[1]
        existing_algo = row[2]
        existing_ref = row[3]

        if not isinstance(config, dict):
            skipped += 1
            continue

        rounds = config.get('rounds', [])
        if not rounds or not isinstance(rounds, list):
            skipped += 1
            continue

        algo_params_col = existing_algo if existing_algo else []
        ref_params_col = existing_ref if existing_ref else []
        config_changed = False

        for round_item in rounds:
            if not isinstance(round_item, dict):
                continue

            round_number = (
                round_item.get('round_number')
                or round_item.get('roundNumber')
                or 1
            )

            # 剥离 algorithm_params
            round_ap = (
                round_item.pop('algorithm_params', None)
                or round_item.pop('algorithmParams', None)
            )
            if round_ap:
                params_list = []
                if isinstance(round_ap, dict):
                    params_list = [
                        {'field_code': k, 'field_value': v}
                        for k, v in round_ap.items()
                    ]
                elif isinstance(round_ap, list):
                    for p in round_ap:
                        if isinstance(p, dict):
                            fc = p.get('field_code') or p.get('fieldCode')
                            fv = p.get('field_value', p.get('fieldValue'))
                            if fc:
                                params_list.append({
                                    'field_code': fc,
                                    'field_value': fv
                                })

                if params_list:
                    # 检查是否已存在该轮的数据
                    found = False
                    for existing in algo_params_col:
                        if isinstance(existing, dict) and \
                           existing.get('round_number') == round_number:
                            found = True
                            break
                    if not found:
                        algo_params_col.append({
                            'round_number': round_number,
                            'params': params_list
                        })
                config_changed = True

            # 剥离 reference_params_path
            ref_path = (
                round_item.pop('reference_params_path', None)
                or round_item.pop('referenceParamsPath', None)
            )
            if ref_path:
                new_path = _old_to_new_path(ref_path, case_id, round_number)
                # 检查是否已存在
                found = False
                for existing in ref_params_col:
                    if isinstance(existing, dict) and \
                       existing.get('round_number') == round_number:
                        found = True
                        break
                if not found and new_path:
                    ref_params_col.append({
                        'round_number': round_number,
                        'reference_params_path': new_path
                    })
                config_changed = True

        if not config_changed and not algo_params_col and not ref_params_col:
            skipped += 1
            continue

        if dry_run:
            print(f"  [DRY-RUN] {case_id}:")
            if config_changed:
                print(f"    config: 移除 rounds 中的 algorithm_params/reference_params_path")
            if algo_params_col and not existing_algo:
                print(f"    algorithm_params 列: {len(algo_params_col)} 轮")
            if ref_params_col and not existing_ref:
                print(f"    reference_params 列: {len(ref_params_col)} 轮")
            migrated += 1
            continue

        try:
            with engine.begin() as conn:
                set_clauses = []
                params = {'tc_id': case_id}

                if config_changed:
                    set_clauses.append("config = :config")
                    params['config'] = json.dumps(config, ensure_ascii=False)

                if algo_params_col and not existing_algo:
                    set_clauses.append("algorithm_params = :algo")
                    params['algo'] = json.dumps(algo_params_col, ensure_ascii=False)

                if ref_params_col and not existing_ref:
                    set_clauses.append("reference_params = :ref")
                    params['ref'] = json.dumps(ref_params_col, ensure_ascii=False)

                set_clauses.append("updated_at = :now")
                params['now'] = datetime.now(UTC8)

                if set_clauses:
                    sql = f"UPDATE test_cases SET {', '.join(set_clauses)} WHERE id = :tc_id"
                    conn.execute(text(sql), params)

            migrated += 1
        except Exception as e:
            errors += 1
            print(f"  [FAIL] {case_id}: {e}")

    print(f"\n  迁移: {migrated}, 跳过: {skipped}, 失败: {errors}")


# ========================================================================
# Step 3: 修正参考参数文件路径
# ========================================================================

def step3_fix_ref_paths(engine, dry_run=False):
    """修正 reference_params 中的文件路径格式"""
    print("\n" + "=" * 60)
    print("Step 3: 修正参考参数文件路径")
    print("=" * 60)

    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT id, reference_params "
            "FROM test_cases "
            "WHERE deleted = false AND reference_params IS NOT NULL"
        )).fetchall()

    total = len(rows)
    fixed = 0
    skipped = 0
    errors = 0

    print(f"  共 {total} 条用例有待修正的 reference_params\n")

    for row in rows:
        case_id = row[0]
        ref_params = row[1]

        if not ref_params or not isinstance(ref_params, list):
            skipped += 1
            continue

        changed = False
        for item in ref_params:
            if not isinstance(item, dict):
                continue
            old_path = item.get('reference_params_path', '')
            if not old_path:
                continue

            # 已经是新格式
            if 'case_result' in old_path:
                continue

            round_number = item.get('round_number', 1)
            new_path = _new_ref_path(case_id, round_number)
            if new_path != old_path:
                if not dry_run:
                    print(f"  [{case_id}] round {round_number}:")
                    print(f"    OLD: {old_path}")
                    print(f"    NEW: {new_path}")
                item['reference_params_path'] = new_path
                changed = True

        if not changed:
            skipped += 1
            continue

        if dry_run:
            fixed += 1
            continue

        try:
            with engine.begin() as conn:
                conn.execute(text(
                    "UPDATE test_cases SET reference_params = :ref, "
                    "updated_at = :now WHERE id = :id"
                ), {
                    'ref': json.dumps(ref_params, ensure_ascii=False),
                    'now': datetime.now(UTC8),
                    'id': case_id,
                })
            fixed += 1
        except Exception as e:
            errors += 1
            print(f"  [FAIL] {case_id}: {e}")

    print(f"\n  修正: {fixed}, 跳过: {skipped}, 失败: {errors}")


# ========================================================================
# Step 4: 清理 config.rounds[] 残留字段
# ========================================================================

def step4_clean_config_rounds(engine, dry_run=False):
    """清理 config.rounds[] 中残留的 algorithm_params / reference_params_path"""
    print("\n" + "=" * 60)
    print("Step 4: 清理 config.rounds[] 残留字段")
    print("=" * 60)

    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT id, config FROM test_cases WHERE deleted = false"
        )).fetchall()

    total = len(rows)
    cleaned = 0
    skipped = 0
    errors = 0

    print(f"  共 {total} 条用例待检查\n")

    for row in rows:
        case_id = row[0]
        config = row[1]

        if not isinstance(config, dict):
            skipped += 1
            continue

        rounds = config.get('rounds', [])
        if not rounds or not isinstance(rounds, list):
            skipped += 1
            continue

        changed = False
        for round_item in rounds:
            if not isinstance(round_item, dict):
                continue
            for key in ['algorithmParams', 'algorithm_params',
                        'referenceParamsPath', 'reference_params_path']:
                if key in round_item:
                    round_item.pop(key, None)
                    changed = True

        if not changed:
            skipped += 1
            continue

        if dry_run:
            print(f"  [DRY-RUN] {case_id}: 清理 rounds 中的残留字段")
            cleaned += 1
            continue

        try:
            with engine.begin() as conn:
                conn.execute(text(
                    "UPDATE test_cases SET config = :config, "
                    "updated_at = :now WHERE id = :id"
                ), {
                    'config': json.dumps(config, ensure_ascii=False),
                    'now': datetime.now(UTC8),
                    'id': case_id,
                })
            cleaned += 1
        except Exception as e:
            errors += 1
            print(f"  [FAIL] {case_id}: {e}")

    print(f"\n  清理: {cleaned}, 跳过: {skipped}, 失败: {errors}")


# ========================================================================
# Step 5: 确保 test_type 列存在
# ========================================================================

def step5_ensure_test_type(engine, dry_run=False):
    """确保 test_cases.test_type 列存在且有索引"""
    print("\n" + "=" * 60)
    print("Step 5: 确保 test_type 列存在")
    print("=" * 60)

    if dry_run:
        with engine.connect() as conn:
            exists = _col_exists(conn, 'test_cases', 'test_type')
            idx_exists = _index_exists(conn, 'ix_test_cases_test_type')
            print(f"  [DRY-RUN] test_type 列存在: {exists}")
            print(f"  [DRY-RUN] 索引存在: {idx_exists}")
            return

    with engine.begin() as conn:
        if not _col_exists(conn, 'test_cases', 'test_type'):
            conn.execute(text(
                "ALTER TABLE test_cases "
                "ADD COLUMN test_type VARCHAR(10) NOT NULL DEFAULT 'api'"
            ))
            print("  [OK] 新增列: test_cases.test_type")
        else:
            print("  [SKIP] test_type 列已存在")

        if not _index_exists(conn, 'ix_test_cases_test_type'):
            conn.execute(text(
                "CREATE INDEX ix_test_cases_test_type "
                "ON test_cases (test_type)"
            ))
            print("  [OK] 创建索引: ix_test_cases_test_type")
        else:
            print("  [SKIP] 索引已存在")


# ========================================================================
# Step 6: 确保旧库独有表被处理（translation_directions / prompt_audio_relations / languages）
# ========================================================================

def step6_drop_deprecated_tables(engine, dry_run=False):
    """删除新模型中已不存在的表（旧库独有）"""
    print("\n" + "=" * 60)
    print("Step 6: 删除新模型中已不存在的表")
    print("=" * 60)

    deprecated_tables = [
        'translation_directions',
        'prompt_audio_relations',
        'languages',
    ]

    for table_name in deprecated_tables:
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_name = :name"
            ), {"name": table_name})
            exists = result.fetchone() is not None

        if not exists:
            print(f"  [SKIP] 表 {table_name} 不存在，跳过")
            continue

        if dry_run:
            print(f"  [DRY-RUN] 将删除表 {table_name}")
            continue

        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {table_name} CASCADE"))
            print(f"  [OK] 删除表: {table_name}")


# ========================================================================
# Step 7: 确保 case_algorithm_params 表字段与新模型一致
# ========================================================================

def step7_fix_case_algorithm_params(engine, dry_run=False):
    """修正 case_algorithm_params 表字段"""
    print("\n" + "=" * 60)
    print("Step 7: 修正 case_algorithm_params 表字段")
    print("=" * 60)

    if dry_run:
        with engine.connect() as conn:
            for col in ['scope', 'min_value', 'max_value', 'step',
                        'unit', 'annotation_code', 'field_path']:
                exists = _col_exists(conn, 'case_algorithm_params', col)
                print(f"  [DRY-RUN] {col}: {'存在' if exists else '缺失'}")
            for col in ['options_source', 'options_field', 'options_label_field']:
                exists = _col_exists(conn, 'case_algorithm_params', col)
                print(f"  [DRY-RUN] {col}（旧）: {'存在' if exists else '已删除'}")
        return

    with engine.begin() as conn:
        # 新增列（如不存在）
        new_columns = [
            ('scope', "VARCHAR(10) NOT NULL DEFAULT 'common'",
             '参数适用范围 (common/api/e2e)'),
            ('min_value', 'FLOAT', '最小值 (slider/number)'),
            ('max_value', 'FLOAT', '最大值 (slider/number)'),
            ('step', 'FLOAT', '步长 (slider/number)'),
            ('unit', 'VARCHAR(20)', '单位显示 (如 cm, dB, s)'),
            ('annotation_code', 'VARCHAR(100)', '关联的音频标注代码'),
            ('field_path', 'VARCHAR(255)', '标注数据字段路径'),
        ]

        for col_name, col_type, comment in new_columns:
            if not _col_exists(conn, 'case_algorithm_params', col_name):
                conn.execute(text(
                    f"ALTER TABLE case_algorithm_params "
                    f"ADD COLUMN {col_name} {col_type}"
                ))
                print(f"  [OK] 新增列: case_algorithm_params.{col_name}")
            else:
                print(f"  [SKIP] {col_name} 列已存在")

        # 删除旧列（如存在）
        old_columns = ['options_source', 'options_field', 'options_label_field']
        for col_name in old_columns:
            if _col_exists(conn, 'case_algorithm_params', col_name):
                conn.execute(text(
                    f"ALTER TABLE case_algorithm_params "
                    f"DROP COLUMN {col_name}"
                ))
                print(f"  [OK] 删除旧列: case_algorithm_params.{col_name}")
            else:
                print(f"  [SKIP] {col_name} 列已不存在")

        # 扩展 param_type（新模型注释含 audio_select, device_select, json）
        try:
            conn.execute(text(
                "ALTER TABLE case_algorithm_params "
                "ALTER COLUMN param_type TYPE VARCHAR(30)"
            ))
            print("  [OK] 扩展 param_type -> VARCHAR(30)")
        except Exception as e:
            if 'already' in str(e).lower():
                print("  [SKIP] param_type 已是 VARCHAR(30) 或更大")
            else:
                print(f"  [WARN] param_type 扩展失败: {e}")


# ========================================================================
# Step 8: 确保 evaluation_dimension_params 表字段与新模型一致
# ========================================================================

def step8_fix_evaluation_dimension_params(engine, dry_run=False):
    """修正 evaluation_dimension_params 表字段和约束"""
    print("\n" + "=" * 60)
    print("Step 8: 修正 evaluation_dimension_params 表字段")
    print("=" * 60)

    if dry_run:
        with engine.connect() as conn:
            for col in ['param_direction', 'field_path', 'agg_role',
                        'output_role', 'visible_in_report']:
                exists = _col_exists(conn, 'evaluation_dimension_params', col)
                print(f"  [DRY-RUN] {col}: {'存在' if exists else '缺失'}")
        return

    with engine.begin() as conn:
        new_columns = [
            ('param_direction', "VARCHAR(10) NOT NULL DEFAULT 'input'",
             '参数方向 (input/output)'),
            ('field_path', 'VARCHAR(200)', '结果提取路径'),
            ('agg_role', 'VARCHAR(20)', '聚合角色'),
            ('output_role', 'VARCHAR(10)', '输出字段角色'),
            ('visible_in_report', 'BOOLEAN DEFAULT TRUE', '是否在报告中显示'),
        ]

        for col_name, col_type, comment in new_columns:
            if not _col_exists(conn, 'evaluation_dimension_params', col_name):
                conn.execute(text(
                    f"ALTER TABLE evaluation_dimension_params "
                    f"ADD COLUMN {col_name} {col_type}"
                ))
                print(f"  [OK] 新增列: evaluation_dimension_params.{col_name}")
            else:
                print(f"  [SKIP] {col_name} 列已存在")

        # 删除旧唯一约束 uq_dimension_param_code（如果存在）
        result = conn.execute(text(
            "SELECT 1 FROM information_schema.table_constraints "
            "WHERE constraint_name = 'uq_dimension_param_code'"
        ))
        if result.fetchone():
            conn.execute(text(
                "ALTER TABLE evaluation_dimension_params "
                "DROP CONSTRAINT uq_dimension_param_code"
            ))
            print("  [OK] 删除旧约束: uq_dimension_param_code")
        else:
            print("  [SKIP] 旧约束 uq_dimension_param_code 不存在")

        # 创建新唯一约束 uq_dimension_param_code_direction
        result = conn.execute(text(
            "SELECT 1 FROM information_schema.table_constraints "
            "WHERE constraint_name = 'uq_dimension_param_code_direction'"
        ))
        if not result.fetchone():
            conn.execute(text(
                "ALTER TABLE evaluation_dimension_params "
                "ADD CONSTRAINT uq_dimension_param_code_direction "
                "UNIQUE (dimension_id, param_code, param_direction)"
            ))
            print("  [OK] 创建约束: uq_dimension_param_code_direction")
        else:
            print("  [SKIP] 约束已存在")

        # 为现有 output 记录设置 output_role 默认值
        result = conn.execute(text(
            "UPDATE evaluation_dimension_params SET output_role = 'main' "
            "WHERE param_direction = 'output' "
            "AND (output_role IS NULL OR output_role = '')"
        ))
        if result.rowcount > 0:
            print(f"  [OK] 为 {result.rowcount} 条 output 记录设置 output_role = 'main'")


# ========================================================================
# Step 9: 确保 algorithm_reference_params 表字段与新模型一致
# ========================================================================

def step9_fix_algorithm_reference_params(engine, dry_run=False):
    """修正 algorithm_reference_params 表字段"""
    print("\n" + "=" * 60)
    print("Step 9: 修正 algorithm_reference_params 表字段")
    print("=" * 60)

    if dry_run:
        with engine.connect() as conn:
            for col in ['field_path', 'merge_mode']:
                exists = _col_exists(conn, 'algorithm_reference_params', col)
                print(f"  [DRY-RUN] {col}: {'存在' if exists else '缺失'}")
        return

    with engine.begin() as conn:
        new_columns = [
            ('field_path', 'VARCHAR(255)', '标注数据字段路径'),
            ('merge_mode', "VARCHAR(20) DEFAULT 'join'", '多音频合并方式'),
        ]

        for col_name, col_type, comment in new_columns:
            if not _col_exists(conn, 'algorithm_reference_params', col_name):
                conn.execute(text(
                    f"ALTER TABLE algorithm_reference_params "
                    f"ADD COLUMN {col_name} {col_type}"
                ))
                print(f"  [OK] 新增列: algorithm_reference_params.{col_name}")
            else:
                print(f"  [SKIP] {col_name} 列已存在")

        # 设置默认值
        result = conn.execute(text(
            "UPDATE algorithm_reference_params "
            "SET merge_mode = 'join' WHERE merge_mode IS NULL"
        ))
        if result.rowcount > 0:
            print(f"  [OK] 为 {result.rowcount} 条记录设置 merge_mode = 'join'")


# ========================================================================
# Step 10: 确保 test_results / test_result_dimensions 表字段与新模型一致
# ========================================================================

def step10_fix_test_results(engine, dry_run=False):
    """修正 test_results 和 test_result_dimensions 表字段"""
    print("\n" + "=" * 60)
    print("Step 10: 修正 test_results / test_result_dimensions 表字段")
    print("=" * 60)

    if dry_run:
        with engine.connect() as conn:
            for table, col in [
                ('test_results', 'result_data_path'),
                ('test_result_dimensions', 'round_number'),
            ]:
                exists = _col_exists(conn, table, col)
                print(f"  [DRY-RUN] {table}.{col}: {'存在' if exists else '缺失'}")
        return

    with engine.begin() as conn:
        # test_results.result_data_path
        if not _col_exists(conn, 'test_results', 'result_data_path'):
            conn.execute(text(
                "ALTER TABLE test_results "
                "ADD COLUMN result_data_path VARCHAR(500)"
            ))
            print("  [OK] 新增列: test_results.result_data_path")
        else:
            print("  [SKIP] result_data_path 列已存在")

        # result_data 改为可空
        try:
            conn.execute(text(
                "ALTER TABLE test_results "
                "ALTER COLUMN result_data DROP NOT NULL"
            ))
            print("  [OK] result_data 改为可空")
        except Exception as e:
            if 'already' in str(e).lower() or 'cannot' in str(e).lower():
                print("  [SKIP] result_data 已是可空")
            else:
                print(f"  [WARN] result_data 改空失败: {e}")

        # test_result_dimensions.round_number
        if not _col_exists(conn, 'test_result_dimensions', 'round_number'):
            conn.execute(text(
                "ALTER TABLE test_result_dimensions "
                "ADD COLUMN round_number INTEGER DEFAULT NULL"
            ))
            print("  [OK] 新增列: test_result_dimensions.round_number")
        else:
            print("  [SKIP] round_number 列已存在")

        # 创建复合索引
        if not _index_exists(conn, 'idx_trd_round'):
            conn.execute(text(
                "CREATE INDEX idx_trd_round "
                "ON test_result_dimensions(test_result_id, round_number)"
            ))
            print("  [OK] 创建索引: idx_trd_round")
        else:
            print("  [SKIP] 索引 idx_trd_round 已存在")


# ========================================================================
# 主流程
# ========================================================================

def main():
    dry_run = '--dry-run' in sys.argv
    step_only = None

    # 解析 --step N 参数
    for i, arg in enumerate(sys.argv):
        if arg == '--step' and i + 1 < len(sys.argv):
            step_only = int(sys.argv[i + 1])

    print("=" * 60)
    print(f"{'[DRY-RUN] ' if dry_run else ''}修复迁移脚本错误")
    print("=" * 60)
    print(f"数据库: {POSTGRES_URI[:POSTGRES_URI.rindex('@')]}@localhost/...")
    print()

    engine = create_engine(POSTGRES_URI)

    steps = [
        (1, step1_restore_columns),
        (2, step2_extract_from_rounds),
        (3, step3_fix_ref_paths),
        (4, step4_clean_config_rounds),
        (5, step5_ensure_test_type),
        (6, step6_drop_deprecated_tables),
        (7, step7_fix_case_algorithm_params),
        (8, step8_fix_evaluation_dimension_params),
        (9, step9_fix_algorithm_reference_params),
        (10, step10_fix_test_results),
    ]

    for step_num, step_func in steps:
        if step_only and step_only != step_num:
            continue
        step_func(engine, dry_run=dry_run)

    print("\n" + "=" * 60)
    print(f"{'[DRY-RUN] ' if dry_run else ''}修复完成")
    print("=" * 60)


if __name__ == '__main__':
    main()
