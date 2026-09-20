# -*- coding: utf-8 -*-
"""
新增 dimensions.sort_order 列（评估维度在报告页的展示顺序，数值越小越靠前）。
幂等，可重复执行。

用法:
    cd Intelligent-Audio-TEST
    python backend/scripts/migrations/202609/add_dimension_sort_order.py

    # 另一个库：
    DATABASE_URI=postgresql://user:pwd@host:5432/db \
        python backend/scripts/migrations/202609/add_dimension_sort_order.py
"""
import os
from sqlalchemy import create_engine, text

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'
)


def _col_exists(conn, table, column):
    row = conn.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :t AND column_name = :c"
    ), {'t': table, 'c': column}).fetchone()
    return row is not None


def main():
    engine = create_engine(POSTGRES_URI)
    with engine.begin() as conn:
        if _col_exists(conn, 'dimensions', 'sort_order'):
            print("[SKIP] dimensions.sort_order 列已存在")
            return
        conn.execute(text(
            "ALTER TABLE dimensions ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0"
        ))
        # 存量数据按 id 顺序补齐 sort_order，保证顺序稳定且与现有展示一致
        rows = conn.execute(text(
            "SELECT id FROM dimensions WHERE deleted = false ORDER BY id"
        )).fetchall()
        for idx, (dim_id,) in enumerate(rows):
            conn.execute(text(
                "UPDATE dimensions SET sort_order = :so WHERE id = :id"
            ), {'so': idx, 'id': dim_id})
        print(f"[OK] 新增列: dimensions.sort_order，并按 id 顺序初始化 {len(rows)} 条存量维度")


if __name__ == '__main__':
    print("=" * 60)
    print("新增 dimensions.sort_order 列迁移")
    print("=" * 60)
    print(f"数据库: {POSTGRES_URI[:POSTGRES_URI.rindex('@')]}@...")
    main()
