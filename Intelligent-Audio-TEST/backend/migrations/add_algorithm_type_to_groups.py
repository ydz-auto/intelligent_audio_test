# -*- coding: utf-8 -*-
"""
数据库迁移脚本：为 test_case_groups 表添加 algorithm_type 字段

使用方法：
    python add_algorithm_type_to_groups.py
"""

import sys
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(script_dir)
project_root = os.path.dirname(backend_dir)

sys.path.insert(0, project_root)
sys.path.insert(0, backend_dir)

from sqlalchemy import text
from backend.models.database import db
from flask import Flask

POSTGRES_URI = 'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'


def main():
    print("=" * 50)
    print("迁移脚本：为 test_case_groups 添加 algorithm_type 字段")
    print("=" * 50)

    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = POSTGRES_URI
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)

    with app.app_context():
        try:
            result = db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'test_case_groups' 
                AND column_name = 'algorithm_type'
            """))
            
            if result.fetchone():
                print("字段 algorithm_type 已存在，无需迁移")
                return
            
            print("正在添加 algorithm_type 字段...")
            db.session.execute(text("""
                ALTER TABLE test_case_groups 
                ADD COLUMN algorithm_type VARCHAR(50)
            """))
            db.session.commit()
            print("迁移完成！algorithm_type 字段已添加到 test_case_groups 表")
            
        except Exception as e:
            db.session.rollback()
            print(f"迁移失败: {e}")
            raise


if __name__ == '__main__':
    main()
