# -*- coding: utf-8 -*-
"""
数据库迁移脚本：将 test_case_groups 表的 name 列唯一约束
改为 (name, algorithm_type) 联合唯一约束

使用方法：
    python change_group_name_unique_to_composite.py
"""

import sys
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
project_root = os.path.dirname(backend_dir)

sys.path.insert(0, project_root)
sys.path.insert(0, backend_dir)

from sqlalchemy import text
from backend.models.database import db
from flask import Flask

POSTGRES_URI = 'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'


def main():
    print("=" * 60)
    print("迁移脚本：test_case_groups 唯一约束 name -> (name, algorithm_type)")
    print("=" * 60)

    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = POSTGRES_URI
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)

    with app.app_context():
        try:
            # 1. 检查并删除旧的 name 列唯一约束
            print("\n[1/2] 检查旧约束 test_case_groups_name_key ...")
            result = db.session.execute(text("""
                SELECT conname
                FROM pg_constraint
                WHERE conrelid = 'test_case_groups'::regclass
                AND conname = 'test_case_groups_name_key'
                AND contype = 'u'
            """))
            old_constraint = result.fetchone()

            if old_constraint:
                print(f"  发现旧约束: {old_constraint[0]}，正在删除...")
                db.session.execute(text("""
                    ALTER TABLE test_case_groups
                    DROP CONSTRAINT test_case_groups_name_key
                """))
                db.session.commit()
                print("  旧约束已删除")
            else:
                print("  旧约束不存在，跳过")

            # 2. 检查并添加新的联合唯一约束
            print("\n[2/2] 检查新约束 uq_group_name_algorithm ...")
            result = db.session.execute(text("""
                SELECT conname
                FROM pg_constraint
                WHERE conrelid = 'test_case_groups'::regclass
                AND conname = 'uq_group_name_algorithm'
                AND contype = 'u'
            """))
            new_constraint = result.fetchone()

            if new_constraint:
                print(f"  新约束已存在: {new_constraint[0]}，无需迁移")
            else:
                print("  正在添加联合唯一约束 (name, algorithm_type)...")
                db.session.execute(text("""
                    ALTER TABLE test_case_groups
                    ADD CONSTRAINT uq_group_name_algorithm
                    UNIQUE (name, algorithm_type)
                """))
                db.session.commit()
                print("  联合唯一约束已创建")

            print("\n迁移完成！")

        except Exception as e:
            db.session.rollback()
            print(f"\n迁移失败: {e}")
            raise


if __name__ == '__main__':
    main()
