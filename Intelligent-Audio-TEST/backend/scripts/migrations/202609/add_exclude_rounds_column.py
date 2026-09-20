# -*- coding: utf-8 -*-
"""
新增 dimensions.exclude_rounds 列（按轮次统计时排除的轮次，JSON 数组，如 [0, 2]）。
幂等，可重复执行。

用法:
    cd Intelligent-Audio-TEST
    python backend/scripts/migrations/202609/add_exclude_rounds_column.py

    # 另一个库：
    DATABASE_URI=postgresql://user:pwd@host:5432/db \
        python backend/scripts/migrations/202609/add_exclude_rounds_column.py
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
        if _col_exists(conn, 'dimensions', 'exclude_rounds'):
            print("[SKIP] dimensions.exclude_rounds 列已存在")
            return
        conn.execute(text(
            "ALTER TABLE dimensions ADD COLUMN exclude_rounds JSON DEFAULT '[]'::json"
        ))
        print("[OK] 新增列: dimensions.exclude_rounds (JSON 数组，默认 [])")


if __name__ == '__main__':
    print("=" * 60)
    print("新增 dimensions.exclude_rounds 列迁移")
    print("=" * 60)
    print(f"数据库: {POSTGRES_URI[:POSTGRES_URI.rindex('@')]}@...")
    main()
