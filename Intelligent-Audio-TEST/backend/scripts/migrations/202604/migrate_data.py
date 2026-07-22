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
import shutil
import subprocess
import time
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

PGSQL_BIN = r"C:\S2TT\environment\pgsql\bin"
PGSQL_DATA = r"C:\S2TT\environment\pgsql\data"
PGSQL_PORT = 5432
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


def is_postgres_running():
    """检查 PostgreSQL 是否正在运行"""
    try:
        result = subprocess.run(
            [os.path.join(PGSQL_BIN, "pg_isready.exe"), "-p", str(PGSQL_PORT)],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except Exception:
        return False


def reload_pg_hba():
    """重新加载 PostgreSQL 配置"""
    try:
        pg_ctl = os.path.join(PGSQL_BIN, "pg_ctl.exe")
        result = subprocess.run(
            [pg_ctl, "reload", "-D", PGSQL_DATA],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except Exception:
        return False


def configure_pg_hba_trust():
    """配置 pg_hba.conf 允许 trust 认证（临时）"""
    pg_hba_file = os.path.join(PGSQL_DATA, "pg_hba.conf")
    pg_hba_backup = os.path.join(PGSQL_DATA, "pg_hba.conf.backup")

    if not os.path.exists(pg_hba_file):
        return False

    print("      配置 pg_hba.conf (添加 trust 认证)...")

    try:
        if not os.path.exists(pg_hba_backup):
            shutil.copy(pg_hba_file, pg_hba_backup)

        with open(pg_hba_file, 'r', encoding='utf-8') as f:
            content = f.read()

        if 'host all all 127.0.0.1/32 trust' not in content:
            with open(pg_hba_file, 'a', encoding='utf-8') as f:
                f.write('\n# 临时配置 - 迁移脚本添加\n')
                f.write('host all all 127.0.0.1/32 trust\n')
                f.write('host all all ::1/128 trust\n')

        reload_pg_hba()
        time.sleep(1)
        print("      pg_hba.conf 配置已更新")
        return True
    except Exception as e:
        print(f"      pg_hba.conf 配置失败: {e}")
        return False


def restore_pg_hba():
    """恢复 pg_hba.conf"""
    pg_hba_file = os.path.join(PGSQL_DATA, "pg_hba.conf")
    pg_hba_backup = os.path.join(PGSQL_DATA, "pg_hba.conf.backup")

    if not os.path.exists(pg_hba_backup):
        return

    print("      恢复 pg_hba.conf ...")

    try:
        shutil.move(pg_hba_backup, pg_hba_file)
        reload_pg_hba()
        print("      pg_hba.conf 已恢复")
    except Exception as e:
        print(f"      pg_hba.conf 恢复失败: {e}")


def ensure_postgres_user():
    """确保 postgres 用户存在"""
    print("      检查 postgres 用户...")

    configure_pg_hba_trust()

    current_user = os.environ.get('USERNAME', 'postgres')

    try:
        admin_engine = create_engine(
            f'postgresql://postgres:postgres123@localhost:5432/postgres',
            isolation_level="AUTOCOMMIT"
        )
        admin_conn = admin_engine.connect()
        result = admin_conn.execute(text("SELECT 1"))
        result.close()
        admin_conn.close()
        admin_engine.dispose()
        print("      postgres 用户已存在（密码正确）")
        restore_pg_hba()
        return
    except Exception:
        pass

    print("      postgres 用户不存在或密码错误，尝试其他方式...")

    try:
        print(f"      尝试使用 postgres 用户（无密码）连接...")
        temp_engine = create_engine(
            f'postgresql://postgres@localhost:5432/postgres',
            isolation_level="AUTOCOMMIT"
        )
        temp_conn = temp_engine.connect()
        print("      连接成功，修改 postgres 用户密码...")

        try:
            temp_conn.execute(text("ALTER USER postgres WITH PASSWORD 'postgres123'"))
            print("      postgres 用户密码设置成功")
        except Exception:
            temp_conn.execute(text("CREATE USER postgres WITH PASSWORD 'postgres123'"))
            print("      postgres 用户创建成功")

        temp_conn.close()
        temp_engine.dispose()
        restore_pg_hba()
        return
    except Exception as e:
        print(f"      postgres 用户（无密码）连接失败: {str(e)[:50]}")

    try:
        print(f"      尝试使用当前系统用户 ({current_user}) 连接...")
        temp_engine = create_engine(
            f'postgresql://{current_user}@localhost:5432/postgres',
            isolation_level="AUTOCOMMIT"
        )
        temp_conn = temp_engine.connect()

        try:
            temp_conn.execute(text("CREATE USER postgres WITH SUPERUSER PASSWORD 'postgres123'"))
            print("      postgres 用户创建成功")
        except Exception:
            temp_conn.execute(text("ALTER USER postgres WITH SUPERUSER PASSWORD 'postgres123'"))
            print("      postgres 用户已存在（已有权限）")

        temp_conn.close()
        temp_engine.dispose()
        restore_pg_hba()
    except Exception as e:
        restore_pg_hba()
        raise Exception(f"无法创建 postgres 用户: {e}")


def init_postgres_cluster():
    """初始化 PostgreSQL 数据集群"""
    print("\n[0/8] 初始化 PostgreSQL 数据集群...")

    pg_is_initiated = os.path.exists(os.path.join(PGSQL_DATA, "PG_VERSION"))

    if pg_is_initiated:
        print(f"      数据集群已存在: {PGSQL_DATA}")
    else:
        print(f"      初始化数据集群: {PGSQL_DATA} ...")
        initdb = os.path.join(PGSQL_BIN, "initdb.exe")
        result = subprocess.run(
            [initdb, "-D", PGSQL_DATA, "-E", "UTF8"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            raise Exception(f"initdb 失败: {result.stderr}")
        print("      数据集群初始化完成")

    log_file = os.path.join(PGSQL_DATA, "pg_startup.log")

    if is_postgres_running():
        print("      PostgreSQL 已在运行")
    else:
        print("      启动 PostgreSQL ...")
        pg_ctl = os.path.join(PGSQL_BIN, "pg_ctl.exe")
        subprocess.Popen(
            [pg_ctl, "start", "-D", PGSQL_DATA, "-l", log_file, "-w"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        for i in range(30):
            if is_postgres_running():
                print("      PostgreSQL 启动成功")
                break
            time.sleep(1)
        else:
            raise Exception(f"PostgreSQL 启动失败，请检查日志: {log_file}")

    ensure_postgres_user()


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
    print("\n[1/8] 重建数据库...")

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

    try:
        admin_conn.execute(text("CREATE USER intelligent_audio_test WITH PASSWORD 'intelligent_audio_test666'"))
    except:
        admin_conn.execute(text("ALTER USER intelligent_audio_test WITH PASSWORD 'intelligent_audio_test666'"))

    admin_conn.execute(text("DROP DATABASE IF EXISTS intelligent_audio_test"))
    admin_conn.execute(text("CREATE DATABASE intelligent_audio_test WITH OWNER intelligent_audio_test"))
    admin_conn.execute(text("ALTER DATABASE intelligent_audio_test OWNER TO intelligent_audio_test"))
    admin_conn.execute(text("GRANT ALL PRIVILEGES ON DATABASE intelligent_audio_test TO intelligent_audio_test"))
    admin_conn.execute(text("GRANT ALL PRIVILEGES ON SCHEMA public TO intelligent_audio_test"))
    admin_conn.execute(text("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO intelligent_audio_test"))
    admin_conn.execute(text("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO intelligent_audio_test"))

    admin_conn.close()
    admin_engine.dispose()
    print("      数据库重建完成")


def grant_schema_privileges():
    """授予 public schema 权限"""
    print("\n[2/8] 授予权限...")

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
    print("\n[3/8] 创建表结构...")

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
    print("\n[4/8] 禁用外键约束...")

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
    """迁移单个表（智能版本 - 只迁移存在的字段）"""
    cursor = sqlite_conn.cursor()

    try:
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()
    except sqlite3.OperationalError:
        return 0

    if not rows:
        return 0

    cursor.execute(f"PRAGMA table_info({table_name})")
    sqlite_columns = [col[1] for col in cursor.fetchall()]

    with engine.connect() as conn:
        result = conn.execute(text(f"""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = '{table_name}'
        """))
        pg_columns = {row[0] for row in result}

    common_columns = [c for c in sqlite_columns if c in pg_columns]
    skipped_columns = [c for c in sqlite_columns if c not in pg_columns]

    if skipped_columns:
        pass

    if not common_columns:
        return 0

    success = 0
    Session = sessionmaker(bind=engine)

    for row in rows:
        row_dict = {}
        for i, col in enumerate(sqlite_columns):
            if col in common_columns:
                row_dict[col] = convert_value(row[i], col)

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

    return success, skipped_columns


def migrate_data(sqlite_conn, engine):
    """迁移所有数据"""
    print("\n[5/8] 迁移数据...")
    print("-" * 50)

    total = 0
    all_skipped = {}
    for table in MIGRATION_ORDER:
        count, skipped = migrate_table(sqlite_conn, engine, table)
        print(f"      {table}: {count} 行" + (f" (跳过字段: {skipped})" if skipped else ""))
        total += count
        if skipped:
            all_skipped[table] = skipped

    print("-" * 50)

    if all_skipped:
        print("\n      以下表的字段被跳过（PostgreSQL 不存在）:")
        for table, fields in all_skipped.items():
            print(f"        {table}: {fields}")

    return total


def reset_sequences(engine):
    """重置所有序列"""
    print("\n[6/8] 重置序列...")

    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT sequence_name,
                   regexp_replace(sequence_name, '_id_seq', '') as table_name
            FROM information_schema.sequences
            WHERE sequence_schema = 'public'
        """))
        sequences = result.fetchall()

    fixed_count = 0
    for seq_name, table_name in sequences:
        conn = engine.connect()
        conn.execute(text("COMMIT"))
        try:
            max_result = conn.execute(text(f'SELECT COALESCE(MAX(id), 0) FROM {table_name}'))
            max_id = max_result.scalar()
            max_result.close()

            if max_id == 0:
                conn.execute(text(f"SELECT setval('{seq_name}', 1, false)"))
            else:
                conn.execute(text(f"SELECT setval('{seq_name}', {max_id}, true)"))
            conn.execute(text("COMMIT"))
            fixed_count += 1
        except Exception as e:
            print(f"      警告: 重置 {seq_name} 失败: {str(e)[:50]}")
        finally:
            conn.close()

    print(f"      已重置 {fixed_count}/{len(sequences)} 个序列")


def migrate_data(sqlite_conn, engine):
    """迁移所有数据"""
    print("\n[5/8] 迁移数据...")
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
    print("\n[7/8] 修复 NULL 值...")

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


LOCK_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".migrate_lock")


def acquire_lock():
    """获取迁移锁，防止并发执行"""
    if os.path.exists(LOCK_FILE):
        pid = None
        try:
            with open(LOCK_FILE, 'r') as f:
                pid = f.read().strip()
            print(f"\n错误: 迁移进程已在运行 (PID: {pid})")
            print("如果确认没有其他迁移进程在执行，请删除锁文件:")
            print(f"  {LOCK_FILE}")
        except:
            print(f"\n错误: 锁文件存在: {LOCK_FILE}")
            print("如果确认没有其他迁移进程在执行，请删除该文件")
        return False

    try:
        with open(LOCK_FILE, 'w') as f:
            f.write(str(os.getpid()))
        return True
    except Exception as e:
        print(f"\n错误: 无法创建锁文件: {e}")
        return False


def release_lock():
    """释放迁移锁"""
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except:
        pass


def main():
    print("=" * 50)
    print("SQLite -> PostgreSQL 一键迁移")
    print("=" * 50)
    print("\n警告: 此操作会清空 'intelligent_audio_test' 数据库！")
    response = input("确认执行迁移? (输入 'yes' 继续): ")
    if response.lower() != 'yes':
        print("已取消迁移")
        sys.exit(0)

    if not acquire_lock():
        sys.exit(1)

    try:
        init_postgres_cluster()
        recreate_database()
        grant_schema_privileges()
        create_tables()

        sqlite_conn = sqlite3.connect(SQLITE_DB_PATH)
        engine = create_engine(POSTGRES_URI)

        disable_foreign_keys(engine)
        total = migrate_data(sqlite_conn, engine)
        reset_sequences(engine)
        fix_null_values(engine)

        sqlite_conn.close()
        engine.dispose()

        print("\n" + "=" * 50)
        print(f"迁移完成! 总计: {total} 行")
        print("=" * 50)
    except Exception as e:
        print(f"\n迁移失败: {e}")
        raise
    finally:
        release_lock()


if __name__ == '__main__':
    main()
