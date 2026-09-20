# -*- coding: utf-8 -*-
"""
新增 dimensions.agg_denominator 列（比率统计分母口径: round=按轮次 / case=按用例）。
幂等，可重复执行。

用法:
    cd Intelligent-Audio-TEST
    python backend/scripts/migrations/202609/add_agg_denominator_column.py

    # 另一个库：
    DATABASE_URI=postgresql://user:pwd@host:5432/db \
        python backend/scripts/migrations/202609/add_agg_denominator_column.py
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
        if _col_exists(conn, 'dimensions', 'agg_denominator'):
            print("[SKIP] dimensions.agg_denominator 列已存在")
            return
        conn.execute(text(
            "ALTER TABLE dimensions ADD COLUMN agg_denominator VARCHAR(20) "
            "NOT NULL DEFAULT 'case'"
        ))
        print("[OK] 新增列: dimensions.agg_denominator (默认 'case'=按用例)")


def reset_default_to_case():
    """存量库：列默认值对齐为 'case'，并把现有行重置为 'case'（需在重跑 seed 前执行，
    seed 会把打断数量类维度设为 'round'）。"""
    engine = create_engine(POSTGRES_URI)
    with engine.begin() as conn:
        if not _col_exists(conn, 'dimensions', 'agg_denominator'):
            print("[SKIP] 列不存在，先执行 main()")
            return
        conn.execute(text(
            "ALTER TABLE dimensions ALTER COLUMN agg_denominator SET DEFAULT 'case'"
        ))
        # 全量重置为 'case'（本轮新功能仅打断数量类维度用 'round'，由 seed 重写）
        conn.execute(text(
            "UPDATE dimensions SET agg_denominator = 'case'"
        ))
        print("[OK] 存量行重置为 'case'（打断数量类维度请在之后重跑 seed 置为 'round'）")


if __name__ == '__main__':
    print("=" * 60)
    print("新增 dimensions.agg_denominator 列迁移")
    print("=" * 60)
    print(f"数据库: {POSTGRES_URI[:POSTGRES_URI.rindex('@')]}@...")
    main()
    reset_default_to_case()
