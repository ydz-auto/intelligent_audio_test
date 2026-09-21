# -*- coding: utf-8 -*-
"""
将 dimensions.sort_order 归一化为主/子分段编码（幂等，可重复执行）：
- 主维度 sort_order = SORT_STEP * k（0, 1000, 2000...）
- 子维度 sort_order = 父主维度段值 + 组内序号（1001, 1002...）

由此 order_by(sort_order, id) 天然得到「先主维度、组内子维度紧随」的层级顺序。

用法:
    cd Intelligent-Audio-TEST
    python backend/scripts/migrations/202609/normalize_dimension_sort_order.py

    # 另一个库：
    DATABASE_URI=postgresql://user:pwd@host:5432/db \
        python backend/scripts/migrations/202609/normalize_dimension_sort_order.py
"""
import os
from sqlalchemy import create_engine, text

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'
)

# 与 backend/controllers/evaluation_controller.py 中 SORT_STEP 保持一致
SORT_STEP = 1000


def main():
    engine = create_engine(POSTGRES_URI)
    with engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT id, parent_dimension_id FROM dimensions "
            "WHERE deleted = false ORDER BY sort_order, id"
        )).fetchall()

        if not rows:
            print("[SKIP] 没有存量维度")
            return

        # 第一遍：主维度分配独立段（SORT_STEP 的整数倍）
        sort_map = {}
        main_order = 0
        for dim_id, parent_id in rows:
            if not parent_id:
                sort_map[dim_id] = main_order * SORT_STEP
                main_order += 1

        # 第二遍：子维度挂到父主维度段内（父段 + 组内序号）
        sub_counters = {}
        for dim_id, parent_id in rows:
            if parent_id:
                base = sort_map.get(parent_id, 0)
                sub_counters[parent_id] = sub_counters.get(parent_id, 0) + 1
                sort_map[dim_id] = base + sub_counters[parent_id]

        for dim_id, new_so in sort_map.items():
            conn.execute(text(
                "UPDATE dimensions SET sort_order = :so WHERE id = :id"
            ), {'so': new_so, 'id': dim_id})

        print(f"[OK] 已归一化 {len(rows)} 条维度 sort_order（主维度段数: {main_order}）")


if __name__ == '__main__':
    print("=" * 60)
    print("dimensions.sort_order 主/子分段归一化迁移")
    print("=" * 60)
    print(f"数据库: {POSTGRES_URI[:POSTGRES_URI.rindex('@')]}@...")
    main()
