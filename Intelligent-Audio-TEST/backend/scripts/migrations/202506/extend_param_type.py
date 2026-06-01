# -*- coding: utf-8 -*-
"""
扩展 device_params/api_params 的 param_type 字段

功能：
1. 扩展 param_type 字段长度从 VARCHAR(20) 到 VARCHAR(30)
2. 根据 param_code 关键词自动推断并更新 param_type

支持的新类型：
- rttm: RTTM 格式的说话人标注
- stm: STM 格式的文本标注
- json: JSON 结构化数据

使用方法：
    python extend_param_type.py

依赖：
    pip install sqlalchemy psycopg2-binary

注意：此脚本可重复执行，不会造成数据丢失
"""

import sys
from sqlalchemy import create_engine, text

POSTGRES_URI = 'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'

# param_code 关键词 → param_type 映射规则（按优先级排列）
PARAM_TYPE_RULES = [
    (['rttm'], 'rttm'),
    (['stm'], 'stm'),
    (['json', 'segments', 'result_json'], 'json'),
]


def migrate_param_type():
    engine = create_engine(POSTGRES_URI)
    
    with engine.begin() as conn:
        # 1. 扩展字段长度
        print("=== Step 1: 扩展 param_type 字段长度 ===")
        
        for table_name in ['algorithm_device_params', 'algorithm_api_params']:
            try:
                conn.execute(text(
                    f"ALTER TABLE {table_name} ALTER COLUMN param_type TYPE VARCHAR(30)"
                ))
                print(f"  + {table_name}.param_type -> VARCHAR(30)")
            except Exception as e:
                msg = str(e).lower()
                if 'already' in msg or 'cannot' in msg or 'type' in msg:
                    print(f"  - {table_name}.param_type 已是 VARCHAR(30) 或更大")
                else:
                    print(f"  ! {table_name}: {e}")

        # 2. 根据 param_code 推断并更新 param_type
        print("\n=== Step 2: 根据 param_code 推断并更新 param_type ===")

        total_updated = 0

        for table_name in ['algorithm_device_params', 'algorithm_api_params']:
            print(f"\n  [{table_name}]")

            rows = conn.execute(text(
                f"SELECT id, param_code, param_type FROM {table_name} "
                f"WHERE direction = 'output' AND deleted = false"
            )).fetchall()

            updated_in_table = 0
            for row in rows:
                row_id, param_code, current_type = row[0], row[1], row[2]

                if current_type != 'text':
                    continue

                code_lower = param_code.lower()
                for keywords, target_type in PARAM_TYPE_RULES:
                    if any(kw in code_lower for kw in keywords):
                        conn.execute(text(
                            f"UPDATE {table_name} SET param_type = :t WHERE id = :id"
                        ), {'t': target_type, 'id': row_id})
                        print(f"    [{param_code}] text -> {target_type}")
                        updated_in_table += 1
                        total_updated += 1
                        break

            if updated_in_table == 0:
                print("    (无需更新)")
            else:
                print(f"    共更新 {updated_in_table} 条")

        print(f"\n=== 完成: 共更新 {total_updated} 条记录 ===")
        print("提示: 如有未自动识别的字段，请在算法配置页面手动修改 param_type")


if __name__ == '__main__':
    print("=" * 60)
    print("扩展 device_params/api_params 的 param_type 字段")
    print("=" * 60)
    print()
    print(f"数据库: {POSTGRES_URI[:POSTGRES_URI.rindex('@')]}@localhost/...")
    print()
    print("此脚本将：")
    print("1. ALTER COLUMN param_type TYPE VARCHAR(30)")
    print("2. 根据 param_code 关键词推断 param_type:")
    for keywords, ptype in PARAM_TYPE_RULES:
        print(f"   - 包含 {keywords} -> {ptype}")
    print()

    confirm = input("是否继续？(y/N): ").strip().lower()
    if confirm != 'y':
        print("已取消")
        sys.exit(0)

    try:
        migrate_param_type()
    except Exception as e:
        print(f"\n迁移失败: {e}")
        sys.exit(1)
