# -*- coding: utf-8 -*-
"""快速查看 param_mappings 中 dimension_id 为空或 target_param 为空的记录"""
import os
from sqlalchemy import create_engine, text

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'
)

def main():
    engine = create_engine(POSTGRES_URI)
    conn = engine.connect()

    print("=== dimension_id IS NULL 的记录 ===")
    rows = conn.execute(text(
        "SELECT id, source, source_param, dimension_id, target_param "
        "FROM param_mappings WHERE deleted=false AND algorithm_type='voice_llm' "
        "AND dimension_id IS NULL ORDER BY id"
    )).fetchall()
    for r in rows:
        print(f"  id={r[0]} source={r[1]} sp={r[2]} dim_id={r[3]} tp={r[4]}")
    print(f"  共 {len(rows)} 条\n")

    print("=== target_param 为空但 dimension_id 有值的记录 ===")
    rows = conn.execute(text(
        "SELECT id, source, source_param, dimension_id, target_param "
        "FROM param_mappings WHERE deleted=false AND algorithm_type='voice_llm' "
        "AND dimension_id IS NOT NULL AND (target_param IS NULL OR target_param='') "
        "ORDER BY dimension_id, id"
    )).fetchall()
    for r in rows:
        print(f"  id={r[0]} source={r[1]} sp={r[2]} dim_id={r[3]} tp={r[4]}")
    print(f"  共 {len(rows)} 条\n")

    print("=== source 分布 ===")
    rows = conn.execute(text(
        "SELECT source, COUNT(*) FROM param_mappings "
        "WHERE deleted=false GROUP BY source ORDER BY source"
    )).fetchall()
    for r in rows:
        print(f"  {r[0]}: {r[1]} 条")

    conn.close()

if __name__ == '__main__':
    main()
