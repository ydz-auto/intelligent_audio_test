# -*- coding: utf-8 -*-
"""
翻译算法参数映射初始化脚本

为翻译(translation)算法添加完整的参数映射配置，包括：
- device: 设备驱动参数映射
- api: API调用参数映射
- evaluation: 评估参数映射
"""

import os
import sys

db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data.db')

from sqlalchemy import create_engine, text
engine = create_engine(f'sqlite:///{db_path}')


def insert_translation_mappings():
    """插入翻译算法的参数映射数据"""

    with engine.connect() as conn:
        # 检查是否已有翻译算法的参数映射
        result = conn.execute(text("""
            SELECT COUNT(*) FROM param_mappings
            WHERE algorithm_type = 'translation'
        """))
        existing_count = result.fetchone()[0]

        if existing_count > 0:
            print(f"翻译算法参数映射已存在 ({existing_count} 条)，跳过插入")
            # 显示现有映射
            existing = conn.execute(text("""
                SELECT component_type, source_param, target_key, transform_type
                FROM param_mappings
                WHERE algorithm_type = 'translation'
            """))
            print("\n现有映射:")
            for row in existing:
                print(f"  {row[0]}: {row[1]} -> {row[2]} (transform: {row[3]})")
            return

        # 定义翻译算法的参数映射
        mappings = [
            # Device参数映射 - 设备驱动需要的参数
            # (algorithm_type, component_type, source_param, target_key, transform_type)
            ('translation', 'device', 'source_language', 'source_language', 'none'),
            ('translation', 'device', 'target_language', 'target_language', 'none'),
            ('translation', 'device', 'model', 'model', 'none'),

            # API参数映射 - API调用需要的参数
            ('translation', 'api', 'source_language', 'source_lang', 'none'),
            ('translation', 'api', 'target_language', 'target_lang', 'none'),
            ('translation', 'api', 'model', 'model', 'none'),
            ('translation', 'api', 'trans_direction', 'trans_direction', 'none'),

            # Evaluation参数映射 - 评估需要的参数
            ('translation', 'evaluation', 'source_language', 'source_lang', 'none'),
            ('translation', 'evaluation', 'target_language', 'target_lang', 'none'),
            ('translation', 'evaluation', 'dimension_ids', 'dimension_ids', 'none'),
        ]

        print(f"开始插入翻译算法参数映射 ({len(mappings)} 条)...")

        for algorithm_type, component_type, source_param, target_key, transform_type in mappings:
            conn.execute(text("""
                INSERT INTO param_mappings
                (algorithm_type, component_type, source_param, target_key, transform_type, deleted)
                VALUES (:algorithm_type, :component_type, :source_param, :target_key, :transform_type, 0)
            """), {
                'algorithm_type': algorithm_type,
                'component_type': component_type,
                'source_param': source_param,
                'target_key': target_key,
                'transform_type': transform_type
            })
            print(f"  插入: {component_type} - {source_param} -> {target_key}")

        conn.commit()
        print("\n翻译算法参数映射插入完成!")


def verify_translation_config():
    """验证翻译算法配置"""
    with engine.connect() as conn:
        # 检查算法定义
        result = conn.execute(text("""
            SELECT id, type, name, status FROM algorithm_definitions
            WHERE type = 'translation'
        """))
        algo = result.fetchone()

        if algo:
            print(f"\n算法定义: ID={algo[0]}, type={algo[1]}, name={algo[2]}, status={algo[3]}")
        else:
            print("\n警告: 未找到 translation 算法定义!")
            return

        # 检查算法参数
        result = conn.execute(text("""
            SELECT param_code, param_name, param_type, default_value
            FROM algorithm_params
            WHERE algorithm_type = 'translation'
        """))
        params = result.fetchall()

        print(f"\n算法参数 ({len(params)} 条):")
        for p in params:
            print(f"  {p[0]}: {p[1]} (type={p[2]}, default={p[3]})")

        # 检查参数映射
        result = conn.execute(text("""
            SELECT component_type, source_param, target_key, transform_type
            FROM param_mappings
            WHERE algorithm_type = 'translation'
        """))
        mappings = result.fetchall()

        print(f"\n参数映射 ({len(mappings)} 条):")
        for m in mappings:
            print(f"  [{m[0]}] {m[1]} -> {m[2]} (transform: {m[3]})")


if __name__ == '__main__':
    print("=" * 60)
    print("翻译算法参数映射初始化")
    print("=" * 60)

    insert_translation_mappings()
    verify_translation_config()

    print("\n" + "=" * 60)
    print("初始化完成!")
    print("=" * 60)
