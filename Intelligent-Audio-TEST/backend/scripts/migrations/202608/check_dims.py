# -*- coding: utf-8 -*-
"""查看所有维度（含已删除）的状态"""
import os
from sqlalchemy import create_engine, text

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'
)

def main():
    engine = create_engine(POSTGRES_URI)
    conn = engine.connect()

    print("=== 所有维度 ===")
    rows = conn.execute(text(
        "SELECT id, name, dimension_type, parent_dimension_id, deleted, task_type_code "
        "FROM dimensions ORDER BY id"
    )).fetchall()
    for r in rows:
        print(f"  id={r[0]} name={r[1]} type={r[2]} parent={r[3]} deleted={r[4]} task={r[5]}")

    print("\n=== dim_id=2 的参数 ===")
    rows = conn.execute(text(
        "SELECT id, param_code, param_name, field_type, param_direction, deleted "
        "FROM evaluation_dimension_params WHERE dimension_id=2 ORDER BY id"
    )).fetchall()
    for r in rows:
        print(f"  id={r[0]} code={r[1]} name={r[2]} type={r[3]} dir={r[4]} deleted={r[5]}")
    print(f"  共 {len(rows)} 条")

    print("\n=== dim_id=3 的参数 ===")
    rows = conn.execute(text(
        "SELECT id, param_code, param_name, field_type, param_direction, deleted "
        "FROM evaluation_dimension_params WHERE dimension_id=3 ORDER BY id"
    )).fetchall()
    for r in rows:
        print(f"  id={r[0]} code={r[1]} name={r[2]} type={r[3]} dir={r[4]} deleted={r[5]}")
    print(f"  共 {len(rows)} 条")

    conn.close()

if __name__ == '__main__':
    main()
