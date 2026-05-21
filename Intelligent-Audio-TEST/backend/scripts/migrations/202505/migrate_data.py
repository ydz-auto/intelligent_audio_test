# -*- coding: utf-8 -*-
"""
SQLite 到 PostgreSQL 数据迁移脚本 (一键版)

功能：
1. 重建 PostgreSQL 数据库
2. 创建表结构
3. 迁移所有数据

使用方法：
    python migrate_data.py
"""

import sqlite3
import json
import sys
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

SQLITE_DB_PATH = r'c:\S2TT\auto_test\ver8\202601292330\Intelligent-Audio-TEST\backend\data.db'
POSTGRES_URI = 'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'

BOOLEAN_COLUMNS = {
    'deleted', 'is_default', 'required', 'is_active', 'is_visible',
    'needs_prompt_audio', 'is_noisy', 'is_calibrated', 'is_enabled',
    'force_overwrite', 'use_cache', 'is_builtin', 'is_system',
    'force_synchronization', 'allow_overwrite', 'auto_fill',
    'is_default_mapping', 'is_primary', 'is_final', 'is_builtin',
    'force_preload', 'keep_audio', 'auto_delete', 'compressed',
    'enable_monitor', 'enable_recording', 'enable_subtitle',
    'enable_audio_extract', 'low_latency', 'hw_acceleration',
    'is_stereo', 'is_noisegate_enabled', 'is_loudness_normalization_enabled',
    'is_sound_trigger_enabled', 'hidden', 'status'
}

MIGRATION_ORDER = [
    'users', 'permissions', 'user_permissions',
    'tags',
    'categories', 'dimensions',
    'translation_directions', 'languages',
    'test_case_groups', 'test_cases', 'test_case_tags',
    'algorithm_groups', 'algorithm_definitions',
    'algorithm_device_params', 'algorithm_api_params', 'algorithm_reference_params',
    'evaluation_dimension_params', 'param_mappings', 'algorithm_dimension_relations',
    'case_algorithm_params',
    'devices', 'device_tags', 'playback_devices', 'spl_mappings', 'calibration_history',
    'audios', 'audio_annotations', 'audio_tags', 'prompt_audio_relations',
    'apis',
    'test_tasks', 'task_tags', 'task_case_relations', 'task_device_relations',
    'task_api_relations', 'task_merge_relations',
    'test_results', 'test_result_dimensions', 'test_reports',
    'logs',
    'upload_tasks', 'upload_files', 'upload_chunks',
    'stats_cache'
]


def convert_value(value, column_name):
    """转换值以适配 PostgreSQL"""
    if value is None:
        return None

    if isinstance(value, bool):
        return value

    if column_name in BOOLEAN_COLUMNS:
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


def recreate_database():
    """重建数据库"""
    print("\n[1/5] 重建数据库...")

    admin_engine = create_engine('postgresql://postgres:postgres123@localhost:5432/postgres')
    admin_conn = admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT")

    result = admin_conn.execute(text("""
        SELECT pid
        FROM pg_stat_activity
        WHERE datname = 'intelligent_audio_test'
    """))
    connections = result.fetchall()

    for (pid,) in connections:
        try:
            admin_conn.execute(text(f"SELECT pg_terminate_backend({pid})"))
        except:
            pass

    admin_conn.execute(text("DROP DATABASE IF EXISTS intelligent_audio_test"))
    admin_conn.execute(text("CREATE DATABASE intelligent_audio_test WITH OWNER intelligent_audio_test"))
    admin_conn.execute(text("ALTER DATABASE intelligent_audio_test OWNER TO intelligent_audio_test"))

    try:
        admin_conn.execute(text("CREATE USER intelligent_audio_test WITH PASSWORD 'intelligent_audio_test666'"))
    except:
        admin_conn.execute(text("ALTER USER intelligent_audio_test WITH PASSWORD 'intelligent_audio_test666'"))
    admin_conn.execute(text("GRANT ALL PRIVILEGES ON DATABASE intelligent_audio_test TO intelligent_audio_test"))
    admin_conn.execute(text("GRANT ALL PRIVILEGES ON SCHEMA public TO intelligent_audio_test"))
    admin_conn.execute(text("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO intelligent_audio_test"))
    admin_conn.execute(text("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO intelligent_audio_test"))

    admin_conn.close()
    admin_engine.dispose()
    print("      数据库重建完成")


def grant_schema_privileges():
    """授予 public schema 权限"""
    print("\n[1.5/5] 授予权限...")

    admin_engine = create_engine('postgresql://postgres:postgres123@localhost:5432/postgres')
    with admin_engine.connect() as conn:
        conn.execute(text("GRANT ALL PRIVILEGES ON SCHEMA public TO intelligent_audio_test"))
        conn.execute(text("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO intelligent_audio_test"))
        conn.execute(text("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO intelligent_audio_test"))
        conn.execute(text("GRANT USAGE ON SCHEMA public TO intelligent_audio_test"))
        conn.execute(text("GRANT CREATE ON SCHEMA public TO intelligent_audio_test"))
    admin_engine.dispose()
    print("      权限授予完成")


def create_tables():
    """创建表结构"""
    print("\n[2/5] 创建表结构...")

    script_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.dirname(script_dir)
    project_root = os.path.dirname(backend_dir)

    sys.path.insert(0, project_root)
    sys.path.insert(0, backend_dir)

    from flask import Flask
    from backend.models.database import db
    import backend.models.models
    import backend.models.algorithm_models

    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = POSTGRES_URI
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)

    with app.app_context():
        db.create_all()
    print("      表结构创建完成 (44 张表)")


def disable_foreign_keys(engine):
    """禁用所有外键约束"""
    print("\n[3/4] 禁用外键约束...")

    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT conname, conrelid::regclass::text
            FROM pg_constraint
            WHERE contype = 'f'
            AND connamespace = 'public'::regnamespace
        """))
        constraints = result.fetchall()

        for conname, tablename in constraints:
            try:
                conn.execute(text(f"ALTER TABLE {tablename} DROP CONSTRAINT {conname}"))
            except:
                pass

        conn.commit()
        print(f"      已禁用 {len(constraints)} 个外键约束")


def migrate_table(sqlite_conn, engine, table_name):
    """迁移单个表"""
    cursor = sqlite_conn.cursor()

    try:
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()
    except sqlite3.OperationalError:
        return 0

    if not rows:
        return 0

    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [col[1] for col in cursor.fetchall()]

    success = 0
    Session = sessionmaker(bind=engine)

    for row in rows:
        row_dict = {columns[i]: convert_value(row[i], columns[i]) for i in range(len(columns))}
        session = Session()

        try:
            placeholders = ', '.join([f':{c}' for c in row_dict.keys()])
            sql = f"INSERT INTO {table_name} ({', '.join(row_dict.keys())}) VALUES ({placeholders})"
            session.execute(text(sql), row_dict)
            session.commit()
            success += 1
        except Exception:
            session.rollback()
        finally:
            session.close()

    return success


def reset_sequences(engine):
    """重置所有序列"""
    print("\n[3.5/5] 重置序列...")

    result = engine.connect().execute(text("""
        SELECT sequence_name,
               regexp_replace(sequence_name, '_id_seq', '') as table_name
        FROM information_schema.sequences
        WHERE sequence_schema = 'public'
    """))
    sequences = result.fetchall()
    result.close()

    fixed_count = 0
    for seq_name, table_name in sequences:
        try:
            max_result = engine.connect().execute(text(f'SELECT COALESCE(MAX(id), 0) FROM {table_name}'))
            max_id = max_result.scalar()
            max_result.close()

            engine.connect().execute(text("COMMIT"))
            if max_id == 0:
                engine.connect().execute(text(f"SELECT setval('{seq_name}', 1, false)"))
            else:
                engine.connect().execute(text(f"SELECT setval('{seq_name}', {max_id}, true)"))
            fixed_count += 1
        except Exception as e:
            print(f"      警告: 重置 {seq_name} 失败: {str(e)[:50]}")

    print(f"      已重置 {fixed_count}/{len(sequences)} 个序列")


def migrate_data(sqlite_conn, engine):
    """迁移所有数据"""
    print("\n[5/5] 迁移数据...")
    print("-" * 50)

    total = 0
    for table in MIGRATION_ORDER:
        count = migrate_table(sqlite_conn, engine, table)
        print(f"      {table}: {count} 行")
        total += count

    print("-" * 50)
    return total


def fix_null_values(engine):
    """修复迁移后可能存在的 NULL 值问题"""
    print("\n[5.5/5] 修复 NULL 值...")

    NULL_FIXES = {
        'apis': {'api_url': "''"},
        'dimensions': {'api_endpoints': "'[]'"},
        'categories': {'config': "''"},
        'languages': {'config': "''"},
    }

    with engine.connect() as conn:
        for table, columns in NULL_FIXES.items():
            for col, default in columns.items():
                try:
                    conn.execute(text(f"UPDATE {table} SET {col} = {default} WHERE {col} IS NULL"))
                    conn.commit()
                except:
                    pass

    print("      NULL 值修复完成")


def main():
    print("=" * 50)
    print("SQLite -> PostgreSQL 一键迁移")
    print("=" * 50)

    recreate_database()
    grant_schema_privileges()
    create_tables()

    sqlite_conn = sqlite3.connect(SQLITE_DB_PATH)
    engine = create_engine(POSTGRES_URI)

    disable_foreign_keys(engine)
    reset_sequences(engine)
    total = migrate_data(sqlite_conn, engine)
    fix_null_values(engine)

    sqlite_conn.close()
    engine.dispose()

    print("\n" + "=" * 50)
    print(f"迁移完成! 总计: {total} 行")
    print("=" * 50)


if __name__ == '__main__':
    main()
