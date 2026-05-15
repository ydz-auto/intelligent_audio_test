# -*- coding: utf-8 -*-
"""
单独迁移 task_case_relations 表（智能版本）

功能：
- 自动检测 PostgreSQL 表结构
- 只迁移目标表存在的字段
- 跳过不存在的字段

使用方法：
    python migrate_task_case_relations.py
"""

import sqlite3
import json
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

SQLITE_DB_PATH = r'c:\S2TT\auto_test\ver8\202601292330\Intelligent-Audio-TEST\backend\data.db'
POSTGRES_URI = 'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'


def convert_value(value, column_name):
    """转换值以适配 PostgreSQL"""
    if value is None:
        return None

    if isinstance(value, bool):
        return value

    if column_name in ('status', 'execution_status', 'evaluation_status'):
        if value in (0, '0', 'false', 'False', False):
            return False
        if value in (1, '1', 'true', 'True', True):
            return True

    if isinstance(value, (int, float, str)):
        return value

    if isinstance(value, bytes):
        return value

    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)

    if hasattr(value, 'isoformat'):
        return value.isoformat()

    return str(value)


def get_postgres_columns(engine, table_name):
    """获取 PostgreSQL 表的列名"""
    with engine.connect() as conn:
        result = conn.execute(text(f"""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = '{table_name}'
        """))
        return {row[0] for row in result}


def migrate_task_case_relations():
    """迁移 task_case_relations 表"""
    print("=" * 50)
    print("单独迁移 task_case_relations 表")
    print("=" * 50)

    sqlite_conn = sqlite3.connect(SQLITE_DB_PATH)
    cursor = sqlite_conn.cursor()

    try:
        cursor.execute("SELECT * FROM task_case_relations")
        rows = cursor.fetchall()
    except sqlite3.OperationalError as e:
        print(f"读取 SQLite 失败: {e}")
        return 0

    if not rows:
        print("没有数据需要迁移")
        return 0

    cursor.execute("PRAGMA table_info(task_case_relations)")
    sqlite_columns = [col[1] for col in cursor.fetchall()]
    print(f"SQLite 表列: {sqlite_columns}")

    engine = create_engine(POSTGRES_URI)
    pg_columns = get_postgres_columns(engine, 'task_case_relations')
    print(f"PostgreSQL 表列: {pg_columns}")

    common_columns = [c for c in sqlite_columns if c in pg_columns]
    print(f"共同字段: {common_columns}")
    print(f"总行数: {len(rows)}")

    if not common_columns:
        print("没有共同的字段，无法迁移")
        return 0

    skipped_columns = [c for c in sqlite_columns if c not in pg_columns]
    if skipped_columns:
        print(f"将跳过不存在的字段: {skipped_columns}")

    Session = sessionmaker(bind=engine)

    count = 0
    error_count = 0
    errors = []

    for row in rows:
        row_dict = {}
        for i, col in enumerate(sqlite_columns):
            if col in common_columns:
                row_dict[col] = convert_value(row[i], col)

        session = Session()

        try:
            placeholders = ', '.join([f":{c}" for c in row_dict.keys()])
            sql = f"INSERT INTO task_case_relations ({', '.join(row_dict.keys())}) VALUES ({placeholders})"
            session.execute(text(sql), row_dict)
            session.commit()
            count += 1
        except Exception as e:
            session.rollback()
            error_count += 1
            if len(errors) < 5:
                errors.append(str(e)[:100])
        finally:
            session.close()

        if count % 100 == 0:
            print(f"  已迁移 {count} 行...")

    sqlite_conn.close()
    engine.dispose()

    print(f"\n迁移完成:")
    print(f"  成功: {count} 行")
    print(f"  失败: {error_count} 行")

    if errors:
        print(f"\n前几个错误:")
        for err in errors[:5]:
            print(f"  - {err}")

    return count

if __name__ == '__main__':
    migrate_task_case_relations()
