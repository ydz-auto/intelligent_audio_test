# -*- coding: utf-8 -*-
"""
清理"主维度已软删但子维度残留"的孤儿子维度数据。

背景：
    删除评分维度接口（evaluation_controller.delete）此前只软删单个维度，
    不会级联删除子维度，导致已删主维度（dimensions.deleted=true, dimension_type='main'）
    下仍残留未删除的子维度及从属数据（params/mappings/relations）。

功能：
    1. 找出所有已软删的主维度（deleted=true AND dimension_type='main'）
    2. 递归软删其下未删除的子维度（parent_dimension_id 指向该主维度）
    3. 一并软删子维度的 evaluation_dimension_params / param_mappings / algorithm_dimension_relations

使用方法：
    cd Intelligent-Audio-TEST
    python -m backend.scripts.migrations.202609.cleanup_orphan_sub_dimensions

可重复执行（幂等）。
"""
import os
from sqlalchemy import create_engine, text

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'
)


def _collect_tree(conn, dim_id, acc):
    """递归收集 dim_id 下所有未删除的子维度 id。"""
    subs = conn.execute(text(
        "SELECT id FROM dimensions "
        "WHERE parent_dimension_id = :pid AND deleted = FALSE"
    ), {'pid': dim_id}).fetchall()
    for (sub_id,) in subs:
        acc.append(sub_id)
        _collect_tree(conn, sub_id, acc)


def _soft_delete_dim(conn, dim_id):
    """软删单个维度及其从属数据。"""
    conn.execute(text(
        "UPDATE dimensions SET deleted = TRUE, updated_at = NOW() "
        "WHERE id = :did AND deleted = FALSE"
    ), {'did': dim_id})
    conn.execute(text(
        "UPDATE evaluation_dimension_params SET deleted = TRUE, updated_at = NOW() "
        "WHERE dimension_id = :did AND deleted = FALSE"
    ), {'did': dim_id})
    conn.execute(text(
        "UPDATE param_mappings SET deleted = TRUE, updated_at = NOW() "
        "WHERE dimension_id = :did AND deleted = FALSE"
    ), {'did': dim_id})
    conn.execute(text(
        "UPDATE algorithm_dimension_relations SET deleted = TRUE, updated_at = NOW() "
        "WHERE dimension_id = :did AND deleted = FALSE"
    ), {'did': dim_id})


def main():
    engine = create_engine(POSTGRES_URI)
    conn = engine.connect()
    trans = conn.begin()

    try:
        # ============================================================
        # Step 1: 找出已软删的主维度
        # ============================================================
        print("=== Step 1: 查找已软删的主维度 ===")
        deleted_mains = conn.execute(text(
            "SELECT id, name, task_type_code FROM dimensions "
            "WHERE dimension_type = 'main' AND deleted = TRUE"
        )).fetchall()
        if not deleted_mains:
            print("  无已软删的主维度，无需清理")
        for dim_id, name, tc in deleted_mains:
            print(f"  main id={dim_id}, name={name}, task_type_code={tc}")
        print()

        # ============================================================
        # Step 2: 收集所有需要软删的孤儿子维度（递归）
        # ============================================================
        print("=== Step 2: 收集孤儿子维度 ===")
        to_delete = []
        for dim_id, name, tc in deleted_mains:
            children = []
            _collect_tree(conn, dim_id, children)
            if children:
                print(f"  main id={dim_id} ({name}) 下残留 {len(children)} 个子维度: {children}")
                to_delete.extend(children)
            else:
                print(f"  main id={dim_id} ({name}) 下无残留子维度")
        print(f"  共需软删 {len(to_delete)} 个子维度\n")

        # ============================================================
        # Step 3: 递归软删子维度及其从属数据
        # ============================================================
        if to_delete:
            print("=== Step 3: 软删孤儿子维度 ===")
            for sub_id in to_delete:
                _soft_delete_dim(conn, sub_id)
                print(f"  软删子维度 id={sub_id}（dimensions/params/mappings/relations 已置 deleted=TRUE）")
            print(f"  共软删 {len(to_delete)} 个子维度\n")

        trans.commit()
        print("=== 清理完成，已提交 ===")

        # ============================================================
        # 验证：仍存在指向已删主维度的未删子维度？
        # ============================================================
        print("\n=== 验证：残留孤儿子维度 ===")
        remaining = conn.execute(text(
            "SELECT d.id, d.name, d.parent_dimension_id FROM dimensions d "
            "JOIN dimensions p ON d.parent_dimension_id = p.id "
            "WHERE d.deleted = FALSE AND p.deleted = TRUE"
        )).fetchall()
        if remaining:
            print(f"  仍有 {len(remaining)} 个孤儿子维度：")
            for r in remaining:
                print(f"  sub id={r[0]}, name={r[1]}, parent={r[2]}")
        else:
            print("  无残留孤儿子维度，全部正常！")

    except Exception as e:
        trans.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    main()
