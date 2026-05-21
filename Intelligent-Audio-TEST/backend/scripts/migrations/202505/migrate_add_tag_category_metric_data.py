"""
数据库迁移脚本：为 report_detail_data 表添加 tag_category_metric_data 字段

功能：
- 检查 report_detail_data 表是否存在 tag_category_metric_data 字段
- 如果不存在，则添加该字段

使用方法：
    python migrate_add_tag_category_metric_data.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy import inspect


def migrate():
    print("=" * 60)
    print("开始迁移：添加 tag_category_metric_data 字段")
    print("=" * 60)
    print(f"数据库: {Config.SQLALCHEMY_DATABASE_URI}")
    
    engine = create_engine(Config.SQLALCHEMY_DATABASE_URI)
    
    try:
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        
        if 'report_detail_data' not in existing_tables:
            print("\n❌ report_detail_data 表不存在，请先运行 migrate_split_report_summary.py")
            return False
        
        columns = [col['name'] for col in inspector.get_columns('report_detail_data')]
        
        if 'tag_category_metric_data' not in columns:
            print("\n[1/1] 为 report_detail_data 表添加 tag_category_metric_data 字段...")
            with engine.connect() as conn:
                conn.execute(text("""
                    ALTER TABLE report_detail_data 
                    ADD COLUMN tag_category_metric_data JSONB
                """))
                conn.commit()
            print("✓ tag_category_metric_data 字段添加成功")
        else:
            print("\n[1/1] tag_category_metric_data 字段已存在，跳过添加")
        
        print("\n" + "=" * 60)
        print("迁移完成！")
        print("=" * 60)
        
        columns = [col['name'] for col in inspector.get_columns('report_detail_data')]
        print("\nreport_detail_data 表当前字段：")
        for col in columns:
            print(f"  - {col}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 迁移失败: {str(e)}")
        raise


if __name__ == '__main__':
    migrate()
