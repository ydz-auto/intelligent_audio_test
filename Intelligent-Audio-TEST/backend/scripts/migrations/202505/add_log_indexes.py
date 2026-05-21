"""
日志表索引优化迁移脚本
为 logs 表添加新的索引以优化查询性能

使用方法:
    cd backend
    python migrations/add_log_indexes.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

DB_URI = 'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'

NEW_INDEXES = [
    ("idx_level", "CREATE INDEX IF NOT EXISTS idx_level ON logs (level)"),
    ("idx_category", "CREATE INDEX IF NOT EXISTS idx_category ON logs (category)"),
    ("idx_module", "CREATE INDEX IF NOT EXISTS idx_module ON logs (module)"),
    ("idx_level_time", "CREATE INDEX IF NOT EXISTS idx_level_time ON logs (level, time)"),
    ("idx_category_time", "CREATE INDEX IF NOT EXISTS idx_category_time ON logs (category, time)"),
]

def get_existing_indexes(conn):
    result = conn.execute(text("""
        SELECT indexname 
        FROM pg_indexes 
        WHERE tablename = 'logs'
    """))
    return {row[0] for row in result.fetchall()}

def create_archive_dirs():
    archive_dir = os.path.join(os.getcwd(), 'archives')
    task_dir = os.path.join(archive_dir, 'tasks')
    case_dir = os.path.join(archive_dir, 'cases')
    other_dir = os.path.join(archive_dir, 'other')
    
    for d in [archive_dir, task_dir, case_dir, other_dir]:
        if not os.path.exists(d):
            os.makedirs(d)
            print(f"    [创建目录] {d}")

def main():
    print("=" * 60)
    print("日志表索引优化迁移")
    print("=" * 60)
    
    engine = create_engine(DB_URI)
    
    with engine.connect() as conn:
        print("\n[1] 检查现有索引...")
        existing = get_existing_indexes(conn)
        print(f"    当前索引: {existing}")
        
        print("\n[2] 创建新索引...")
        for idx_name, sql in NEW_INDEXES:
            if idx_name in existing:
                print(f"    [跳过] {idx_name} 已存在")
            else:
                try:
                    conn.execute(text(sql))
                    conn.commit()
                    print(f"    [成功] {idx_name} 创建完成")
                except Exception as e:
                    print(f"    [错误] {idx_name} 创建失败: {e}")
        
        print("\n[3] 验证索引创建结果...")
        final_indexes = get_existing_indexes(conn)
        print(f"    最终索引列表:")
        for idx in sorted(final_indexes):
            if idx.startswith('idx_'):
                print(f"      - {idx}")
        
        print("\n[4] 统计日志表信息...")
        result = conn.execute(text("SELECT COUNT(*) FROM logs"))
        count = result.scalar()
        print(f"    当前日志总数: {count:,}")
        
        if count > 100000:
            print(f"\n    [提示] 日志数量较多 ({count:,} 条)，建议执行归档:")
            print(f"           POST /logs/archive {{\"days\": 7}}")
    
    print("\n[5] 创建归档目录结构...")
    create_archive_dirs()
    
    print("\n" + "=" * 60)
    print("迁移完成!")
    print("=" * 60)
    print("\n归档目录结构:")
    print("  archives/")
    print("  ├── tasks/     # 按任务ID归档 (task_123.json)")
    print("  ├── cases/     # 按用例ID归档 (case_xxx.json)")
    print("  └── other/     # 其他日志归档")
    print("\n查询冷数据接口:")
    print("  GET /logs/archive/logs?task_id=123")
    print("  GET /logs/archive/logs?test_case_id=xxx")

if __name__ == '__main__':
    main()
