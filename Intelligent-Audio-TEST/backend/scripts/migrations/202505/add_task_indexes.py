"""
数据库迁移脚本：为 Task 表添加索引
解决历史报告页面按算法类型筛选时加载慢的问题

运行方式：
python backend/scripts/migrations/202505/add_task_indexes.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from backend.models.database import db
from backend.app import app


def add_task_indexes():
    """为 Task 表添加索引"""
    indexes_to_add = [
        ("idx_task_status", "status"),
        ("idx_task_algorithm_type", "algorithm_type"),
        ("idx_task_created_at", "created_at"),
        ("idx_task_status_deleted", ["status", "deleted"]),
    ]
    
    with app.app_context():
        engine = db.engine
        dialect = engine.dialect.name
        
        existing_indexes = []
        try:
            if dialect == 'postgresql':
                result = db.session.execute(
                    db.text("SELECT indexname FROM pg_indexes WHERE tablename = 'test_tasks'")
                )
                existing_indexes = [row[0] for row in result.fetchall()]
            elif dialect == 'mysql':
                result = db.session.execute(
                    db.text("SHOW INDEX FROM test_tasks")
                )
                existing_indexes = [row[2] for row in result.fetchall()]
            elif dialect == 'sqlite':
                result = db.session.execute(
                    db.text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='test_tasks'")
                )
                existing_indexes = [row[0] for row in result.fetchall()]
        except Exception as e:
            print(f"获取现有索引失败: {e}")
            existing_indexes = []
        
        print(f"现有索引: {existing_indexes}")
        
        added_count = 0
        for index_name, columns in indexes_to_add:
            if index_name in existing_indexes:
                print(f"索引 {index_name} 已存在，跳过")
                continue
            
            if isinstance(columns, list):
                cols_str = ", ".join(columns)
            else:
                cols_str = columns
            
            sql = f"CREATE INDEX {index_name} ON test_tasks ({cols_str})"
            
            try:
                db.session.execute(db.text(sql))
                db.session.commit()
                print(f"成功创建索引: {index_name} ({cols_str})")
                added_count += 1
            except Exception as e:
                db.session.rollback()
                print(f"创建索引 {index_name} 失败: {e}")
        
        print(f"\n迁移完成，共添加 {added_count} 个索引")
        
        if dialect == 'postgresql':
            print("\n建议运行: ANALYZE test_tasks; 以更新统计信息")
            try:
                db.session.execute(db.text("ANALYZE test_tasks"))
                db.session.commit()
                print("已执行 ANALYZE test_tasks")
            except Exception as e:
                print(f"执行 ANALYZE 失败: {e}")


if __name__ == "__main__":
    add_task_indexes()