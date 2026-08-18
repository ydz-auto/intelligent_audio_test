# -*- coding: utf-8 -*-
"""查看指向已删除维度和已删除参数的映射"""
import os
from sqlalchemy import create_engine, text

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'
)

def main():
    engine = create_engine(POSTGRES_URI)
    conn = engine.connect()

    print("=== 指向已删除维度的映射 ===")
    rows = conn.execute(text(
        "SELECT pm.id, pm.source, pm.source_param, pm.dimension_id, pm.target_param, "
        "d.name as dim_name, d.deleted as dim_deleted "
        "FROM param_mappings pm "
        "JOIN dimensions d ON pm.dimension_id = d.id "
        "WHERE pm.deleted = false AND pm.algorithm_type = 'voice_llm' "
        "AND d.deleted = true ORDER BY pm.dimension_id, pm.id"
    )).fetchall()
    for r in rows:
        print(f"  pm_id={r[0]} source={r[1]} sp={r[2]} dim_id={r[3]} tp={r[4]} dim_name={r[5]}")
    print(f"  共 {len(rows)} 条\n")

    print("=== target_param 在维度参数表中被软删除的映射 ===")
    rows = conn.execute(text(
        "SELECT pm.id, pm.source, pm.source_param, pm.dimension_id, pm.target_param, "
        "edp.id as param_id, edp.param_name, edp.deleted as param_deleted "
        "FROM param_mappings pm "
        "JOIN evaluation_dimension_params edp "
        "  ON edp.dimension_id = pm.dimension_id AND edp.param_code = pm.target_param "
        "WHERE pm.deleted = false AND pm.algorithm_type = 'voice_llm' "
        "AND edp.deleted = true ORDER BY pm.dimension_id, pm.id"
    )).fetchall()
    for r in rows:
        print(f"  pm_id={r[0]} source={r[1]} sp={r[2]} dim_id={r[3]} "
              f"tp={r[4]} param_id={r[5]} param_name={r[6]}")
    print(f"  共 {len(rows)} 条\n")

    print("=== target_param 在维度参数表中完全不存在的映射 ===")
    rows = conn.execute(text(
        "SELECT pm.id, pm.source, pm.source_param, pm.dimension_id, pm.target_param "
        "FROM param_mappings pm "
        "WHERE pm.deleted = false AND pm.algorithm_type = 'voice_llm' "
        "AND NOT EXISTS ("
        "  SELECT 1 FROM evaluation_dimension_params edp "
        "  WHERE edp.dimension_id = pm.dimension_id AND edp.param_code = pm.target_param"
        ") ORDER BY pm.dimension_id, pm.id"
    )).fetchall()
    for r in rows:
        print(f"  pm_id={r[0]} source={r[1]} sp={r[2]} dim_id={r[3]} tp={r[4]}")
    print(f"  共 {len(rows)} 条\n")

    conn.close()

if __name__ == '__main__':
    main()
