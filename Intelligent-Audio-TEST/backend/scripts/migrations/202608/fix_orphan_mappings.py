# -*- coding: utf-8 -*-
"""
修复 param_mappings 中三类无效引用：

1. 24条映射指向已删除维度 id=2（小艺指标）→ dimension_id 迁移到 dim=3（话轮接管）
2. 29条映射的 target_param 对应参数被软删除 → 恢复参数的 deleted=false
3. 1条映射（is_return_to_topic, dim=10）target_param 不存在 → 软删此映射

根因：seed 脚本重做维度时，旧维度和旧参数被软删除，但映射还指向它们。
"""
import os
from sqlalchemy import create_engine, text

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'
)

# 维度 id=2（小艺指标）→ 迁移到 dim=3（话轮接管）
MIGRATE_FROM_DIM = 2
MIGRATE_TO_DIM = 3


def main():
    engine = create_engine(POSTGRES_URI)
    conn = engine.connect()
    trans = conn.begin()

    try:
        # ============================================================
        # Step 1: 迁移指向已删除维度 id=2 的映射到 dim=3
        # ============================================================
        print("=== Step 1: 迁移 dim_id=2 → dim_id=3 ===")

        # 先找出 dim=2 中在 dim=3 已存在的映射（重复项），直接软删 dim=2 的
        duplicates = conn.execute(text(
            "SELECT pm2.id, pm2.source, pm2.source_param "
            "FROM param_mappings pm2 "
            "JOIN param_mappings pm3 "
            "  ON pm3.algorithm_type = pm2.algorithm_type "
            "  AND pm3.source = pm2.source "
            "  AND pm3.source_param = pm2.source_param "
            "  AND pm3.dimension_id = :to_dim AND pm3.deleted = false "
            "WHERE pm2.dimension_id = :from_dim AND pm2.deleted = false "
            "AND pm2.algorithm_type = 'voice_llm'"
        ), {'from_dim': MIGRATE_FROM_DIM, 'to_dim': MIGRATE_TO_DIM}).fetchall()
        dup_ids = [d[0] for d in duplicates]
        for d in duplicates:
            print(f"  pm_id={d[0]} source={d[1]} sp={d[2]} dim=3 已存在 → 软删 dim=2 记录")
        if dup_ids:
            conn.execute(text(
                "UPDATE param_mappings SET deleted = true, updated_at = NOW() "
                "WHERE id = ANY(:ids)"
            ), {'ids': dup_ids})
        print(f"  软删重复 {len(dup_ids)} 条")

        # 迁移剩余的（不重复的）
        result = conn.execute(text(
            "UPDATE param_mappings SET dimension_id = :to_dim, updated_at = NOW() "
            "WHERE deleted = false AND algorithm_type = 'voice_llm' "
            "AND dimension_id = :from_dim "
            "RETURNING id, source_param"
        ), {'from_dim': MIGRATE_FROM_DIM, 'to_dim': MIGRATE_TO_DIM})
        migrated = result.fetchall()
        for r in migrated:
            print(f"  pm_id={r[0]} source_param={r[1]} dim_id {MIGRATE_FROM_DIM}→{MIGRATE_TO_DIM}")
        print(f"  迁移 {len(migrated)} 条\n")

        # ============================================================
        # Step 2: 恢复被软删除的维度参数（映射的 target_param 指向它们）
        # ============================================================
        print("=== Step 2: 恢复被软删除的维度参数 ===")
        result = conn.execute(text(
            "UPDATE evaluation_dimension_params edp "
            "SET deleted = false, updated_at = NOW() "
            "WHERE edp.deleted = true "
            "AND EXISTS ("
            "  SELECT 1 FROM param_mappings pm "
            "  WHERE pm.dimension_id = edp.dimension_id "
            "  AND pm.target_param = edp.param_code "
            "  AND pm.deleted = false AND pm.algorithm_type = 'voice_llm'"
            ") "
            "RETURNING edp.id, edp.dimension_id, edp.param_code, edp.param_name"
        ))
        restored = result.fetchall()
        for r in restored:
            print(f"  param_id={r[0]} dim_id={r[1]} code={r[2]} name={r[3]}")
        print(f"  恢复 {len(restored)} 个参数\n")

        # ============================================================
        # Step 3: 软删 target_param 不存在的映射
        # ============================================================
        print("=== Step 3: 软删无效映射（target_param 不存在）===")
        result = conn.execute(text(
            "UPDATE param_mappings pm SET deleted = true, updated_at = NOW() "
            "WHERE pm.deleted = false AND pm.algorithm_type = 'voice_llm' "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM evaluation_dimension_params edp "
            "  WHERE edp.dimension_id = pm.dimension_id "
            "  AND edp.param_code = pm.target_param"
            ") "
            "RETURNING pm.id, pm.source_param, pm.dimension_id, pm.target_param"
        ))
        deleted = result.fetchall()
        for r in deleted:
            print(f"  pm_id={r[0]} source_param={r[1]} dim_id={r[2]} tp={r[3]} → 软删")
        print(f"  软删 {len(deleted)} 条\n")

        trans.commit()
        print("=== 全部完成，已提交 ===")

        # ============================================================
        # 验证
        # ============================================================
        print("\n=== 验证：修复后仍有空白的映射 ===")
        rows = conn.execute(text(
            "SELECT pm.id, pm.source, pm.source_param, pm.dimension_id, pm.target_param, "
            "d.name as dim_name, d.deleted as dim_deleted, "
            "edp.id as param_id, edp.deleted as param_deleted "
            "FROM param_mappings pm "
            "LEFT JOIN dimensions d ON pm.dimension_id = d.id "
            "LEFT JOIN evaluation_dimension_params edp "
            "  ON edp.dimension_id = pm.dimension_id AND edp.param_code = pm.target_param "
            "WHERE pm.deleted = false AND pm.algorithm_type = 'voice_llm' "
            "AND (d.deleted = true OR d.id IS NULL OR edp.deleted = true OR edp.id IS NULL) "
            "ORDER BY pm.dimension_id, pm.id"
        )).fetchall()
        if rows:
            print(f"  仍有 {len(rows)} 条无效映射：")
            for r in rows:
                print(f"  pm_id={r[0]} sp={r[2]} dim_id={r[3]} tp={r[4]} "
                      f"dim_deleted={r[6]} param_id={r[7]} param_deleted={r[8]}")
        else:
            print("  无无效映射，全部正常！")

    except Exception as e:
        trans.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    main()
