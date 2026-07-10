"""
迁移脚本: algorithm_params / reference_params 从 config.rounds[] 迁移到独立列
===========================================================================

将 TestCase 的算法参数和参考参数从 config.rounds[] 剥离到独立列：
1. 新增 test_cases.algorithm_params 列（JSON）— 按轮分组 [{round_number, params:[{field_code, field_value}]}]
2. 新增 test_cases.reference_params 列（JSON）— 按轮分组 [{round_number, reference_params_path}]
3. 把 config.rounds[].algorithmParams / algorithm_params 迁移到 algorithm_params 列
4. 把 config.rounds[].referenceParamsPath / reference_params_path 迁移到 reference_params 列
5. 从 config.rounds[] 中移除这两个字段

可重复执行（幂等），支持 --dry-run 预览。

用法:
    python migrate_algo_ref_to_columns.py              # 正式执行
    python migrate_algo_ref_to_columns.py --dry-run    # 仅预览，不修改数据库
"""

import json
import os
import sys

from sqlalchemy import create_engine, text

# ========================================================================
# 配置
# ========================================================================

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666'
    '@localhost:5432/intelligent_audio_test'
)

# ========================================================================
# 辅助函数
# ========================================================================

def ensure_columns(engine):
    """确保 test_cases 表有 algorithm_params 和 reference_params 列"""
    with engine.connect() as conn:
        # 检查列是否存在
        result = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'test_cases'
            AND column_name IN ('algorithm_params', 'reference_params')
        """))
        existing = {row[0] for row in result}

        if 'algorithm_params' not in existing:
            conn.execute(text("ALTER TABLE test_cases ADD COLUMN algorithm_params JSON"))
            print("[INFO] 新增列: test_cases.algorithm_params")
        else:
            print("[INFO] 列已存在: test_cases.algorithm_params")

        if 'reference_params' not in existing:
            conn.execute(text("ALTER TABLE test_cases ADD COLUMN reference_params JSON"))
            print("[INFO] 新增列: test_cases.reference_params")
        else:
            print("[INFO] 列已存在: test_cases.reference_params")

        conn.commit()


def migrate_test_case(tc_row):
    """迁移单个 TestCase，返回 (new_config, algorithm_params_col, reference_params_col)"""
    tc_id = tc_row[0]
    config = tc_row[1] or {}
    old_algo_col = tc_row[2] if len(tc_row) > 2 else None
    old_ref_col = tc_row[3] if len(tc_row) > 3 else None

    if not isinstance(config, dict):
        return config, None, None

    rounds = config.get('rounds', [])
    if not rounds:
        return config, None, None

    algo_params_col = []
    ref_params_col = []
    config_changed = False

    for round_item in rounds:
        if not isinstance(round_item, dict):
            continue
        round_number = round_item.get('round_number') or round_item.get('roundNumber') or 1

        # 剥离 algorithm_params / algorithmParams
        round_ap = round_item.pop('algorithm_params', None) or round_item.pop('algorithmParams', None)
        if round_ap:
            params_list = []
            if isinstance(round_ap, dict):
                params_list = [{'field_code': k, 'field_value': v} for k, v in round_ap.items()]
            elif isinstance(round_ap, list):
                for p in round_ap:
                    if isinstance(p, dict):
                        fc = p.get('field_code') or p.get('fieldCode')
                        fv = p.get('field_value', p.get('fieldValue'))
                        if fc:
                            params_list.append({'field_code': fc, 'field_value': fv})
            if params_list:
                algo_params_col.append({'round_number': round_number, 'params': params_list})
            config_changed = True

        # 剥离 reference_params_path / referenceParamsPath
        ref_path = round_item.pop('reference_params_path', None) or round_item.pop('referenceParamsPath', None)
        if ref_path:
            ref_params_col.append({'round_number': round_number, 'reference_params_path': ref_path})
            config_changed = True

    # 如果独立列已有旧数据（旧迁移脚本清空过），保留
    if not algo_params_col and old_algo_col:
        # 旧 algorithm_params 列可能是 dict 或 list 格式，包装为按轮分组
        if isinstance(old_algo_col, dict):
            params_list = [{'field_code': k, 'field_value': v} for k, v in old_algo_col.items()]
            if params_list:
                algo_params_col = [{'round_number': 1, 'params': params_list}]
        elif isinstance(old_algo_col, list) and old_algo_col:
            first = old_algo_col[0]
            if isinstance(first, dict) and 'field_code' in first:
                # 旧平面格式
                algo_params_col = [{'round_number': 1, 'params': old_algo_col}]
            elif isinstance(first, dict) and 'round_number' in first:
                # 已是按轮分组
                algo_params_col = old_algo_col

    return config if config_changed else None, algo_params_col if algo_params_col else None, ref_params_col if ref_params_col else None


# ========================================================================
# 主流程
# ========================================================================

def main():
    dry_run = '--dry-run' in sys.argv

    engine = create_engine(POSTGRES_URI)

    if dry_run:
        print("[DRY-RUN] 仅预览，不修改数据库")

    # 1. 确保列存在
    if not dry_run:
        ensure_columns(engine)

    # 2. 查询所有 TestCase
    with engine.connect() as conn:
        # 使用 * 读取所有列，包括可能已存在的旧 algorithm_params / reference_params
        result = conn.execute(text("""
            SELECT id, config, algorithm_params, reference_params
            FROM test_cases
            WHERE deleted = false
        """))
        tc_rows = result.fetchall()

    print(f"[INFO] 找到 {len(tc_rows)} 个用例")

    migrated = 0
    skipped = 0

    for tc_row in tc_rows:
        tc_id = tc_row[0]
        new_config, algo_params_col, ref_params_col = migrate_test_case(tc_row)

        if new_config is None and algo_params_col is None and ref_params_col is None:
            skipped += 1
            continue

        if dry_run:
            print(f"[DRY-RUN] 用例 {tc_id}:")
            if new_config:
                print(f"  config: 移除 rounds 中的 algorithmParams/referenceParamsPath")
            if algo_params_col:
                print(f"  algorithm_params 列: {len(algo_params_col)} 轮")
            if ref_params_col:
                print(f"  reference_params 列: {len(ref_params_col)} 轮")
            migrated += 1
            continue

        # 更新数据库
        with engine.begin() as conn:
            set_clauses = []
            params = {'tc_id': tc_id}

            if new_config is not None:
                set_clauses.append("config = :config")
                params['config'] = json.dumps(new_config, ensure_ascii=False)

            if algo_params_col is not None:
                set_clauses.append("algorithm_params = :algo")
                params['algo'] = json.dumps(algo_params_col, ensure_ascii=False)
            elif old_algo_col := tc_row[2]:
                # 清空旧列数据（已迁移到按轮分组格式）
                set_clauses.append("algorithm_params = :algo")
                params['algo'] = None

            if ref_params_col is not None:
                set_clauses.append("reference_params = :ref")
                params['ref'] = json.dumps(ref_params_col, ensure_ascii=False)

            if set_clauses:
                sql = f"UPDATE test_cases SET {', '.join(set_clauses)} WHERE id = :tc_id"
                conn.execute(text(sql), params)

        migrated += 1
        print(f"[OK] 用例 {tc_id}: 迁移完成")

    print(f"\n[完成] 迁移 {migrated} 个用例，跳过 {skipped} 个（无需迁移）")


if __name__ == '__main__':
    main()
