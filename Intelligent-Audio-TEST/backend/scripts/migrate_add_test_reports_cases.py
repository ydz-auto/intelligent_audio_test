"""
数据库迁移脚本：添加 test_reports_cases 字段到 test_reports 表

功能：
- 为 test_reports 表添加 test_reports_cases JSON 字段
- 用于存储报告用例列表信息，支持用例搜索和二次对比报告
"""
import os
import sys
from sqlalchemy import create_engine, text

# 获取数据库路径
db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data.db')

# 创建数据库引擎
engine = create_engine(f'sqlite:///{db_path}')

def migrate_test_reports_cases():
    """添加 test_reports_cases 字段"""
    print(f"数据库路径: {db_path}")
    
    try:
        # 检查字段是否已存在
        with engine.connect() as conn:
            result = conn.execute(
                text("PRAGMA table_info(test_reports)")
            )
            columns = [row[1] for row in result]
            
            if 'test_reports_cases' in columns:
                print("字段 test_reports_cases 已存在，跳过迁移")
                return True
            
            # 添加字段 (SQLite 使用 ALTER TABLE ADD COLUMN)
            conn.execute(
                text("ALTER TABLE test_reports ADD COLUMN test_reports_cases TEXT COMMENT '存储报告用例列表信息 (JSON)，用于用例搜索和二次对比'")
            )
            conn.commit()
            print("成功添加 test_reports_cases 字段")
            return True
            
    except Exception as e:
        print(f"迁移失败: {e}")
        return False

if __name__ == '__main__':
    success = migrate_test_reports_cases()
    sys.exit(0 if success else 1)
