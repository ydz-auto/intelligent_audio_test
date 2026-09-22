# -*- coding: utf-8 -*-
"""
清理指向已删除维度的孤儿映射/关联数据

背景：
- 历史迁移/软删维度时，部分 param_mappings 与 algorithm_dimension_relations
  未同步置 deleted=TRUE，导致算法配置弹窗里"目标评估维度/目标参数"显示为空。
- 运行时删除走 EvaluationController._soft_delete_tree（会同步清理），此处
  只清理历史遗留数据。

执行：python -m backend.scripts.migrations.202609.cleanup_orphan_dimension_refs
"""
import os
from sqlalchemy import create_engine, text

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'
)


def main():
    engine = create_engine(POSTGRES_URI)
    with engine.connect() as conn:
        print("=== 清理前：映射指向已删维度 ===")
        before = conn.execute(text("""
            SELECT count(*) FROM param_mappings pm
            JOIN dimensions d ON d.id = pm.dimension_id
            WHERE pm.deleted = false AND d.deleted = true
        """)).scalar()
        print(f"  映射 {before} 条")

        print("=== 清理前：关联关系指向已删维度 ===")
        before2 = conn.execute(text("""
            SELECT count(*) FROM algorithm_dimension_relations adr
            JOIN dimensions d ON d.id = adr.dimension_id
            WHERE adr.deleted = false AND d.deleted = true
        """)).scalar()
        print(f"  关联 {before2} 条")

        # 软删指向已删维度的映射
        r1 = conn.execute(text("""
            UPDATE param_mappings SET deleted = TRUE, updated_at = NOW()
            WHERE deleted = FALSE AND dimension_id IN (
                SELECT id FROM dimensions WHERE deleted = TRUE
            )
        """))
        # 软删指向已删维度的关联关系
        r2 = conn.execute(text("""
            UPDATE algorithm_dimension_relations SET deleted = TRUE, updated_at = NOW()
            WHERE deleted = FALSE AND dimension_id IN (
                SELECT id FROM dimensions WHERE deleted = TRUE
            )
        """))
        conn.commit()
        print(f"\n已软删映射 {r1.rowcount} 条，关联 {r2.rowcount} 条")

        print("\n=== 清理后：映射指向已删维度 ===")
        after = conn.execute(text("""
            SELECT count(*) FROM param_mappings pm
            JOIN dimensions d ON d.id = pm.dimension_id
            WHERE pm.deleted = false AND d.deleted = true
        """)).scalar()
        print(f"  剩余 {after} 条")

    engine.dispose()
    print("\n完成。")


if __name__ == '__main__':
    main()
