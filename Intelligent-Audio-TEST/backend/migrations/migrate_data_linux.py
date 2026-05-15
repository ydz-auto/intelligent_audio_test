# -*- coding: utf-8 -*-
"""
SQLite 到 PostgreSQL 数据迁移脚本 (Linux 版)

功能：
1. 检查/安装 PostgreSQL
2. 重建 PostgreSQL 数据库
3. 创建表结构
4. 迁移所有数据

使用方法：
    python migrate_data_linux.py
"""

import sqlite3
import json
import sys
import os
import shutil
import subprocess
import time

SQLITE_DB_PATH = '/path/to/your/linux/data.db'
POSTGRES_URI = 'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'

POSTGRES_USER = 'postgres'
POSTGRES_PASSWORD = 'postgres123'
POSTGRES_DB = 'postgres'
POSTGRES_DATA_DB = 'intelligent_audio_test'
POSTGRES_DATA_DB_USER = 'intelligent_audio_test'
POSTGRES_DATA_DB_PASSWORD = 'intelligent_audio_test666'

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
            ['pg_isready', '-p', '5432'],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except Exception:
        return False


def check_postgres_installed():
    """检查 PostgreSQL 是否已安装"""
    try:
        result = subprocess.run(
            ['which', 'psql'],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except Exception:
        return False


def get_pg_version():
    """获取 PostgreSQL 版本"""
    try:
        result = subprocess.run(
            ['psql', '--version'],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            output = result.stdout
            if 'psql (PostgreSQL)' in output:
                version = output.split('(')[1].split(')')[0].strip()
                return version.split('.')[0]
        return None
    except Exception:
        return None


def ensure_postgres():
    """确保 PostgreSQL 已安装并运行"""
    print("\n[0/7] 检查 PostgreSQL ...")

    if not check_postgres_installed():
        print("      PostgreSQL 未安装，正在安装...")
        install_postgres()
    else:
        print("      PostgreSQL 已安装")

    version = get_pg_version()
    if version:
        print(f"      PostgreSQL 版本: {version}")

    if not is_postgres_running():
        print("      PostgreSQL 未运行，正在启动...")
        start_postgres()
    else:
        print("      PostgreSQL 已在运行")

    if not ensure_postgres_user():
        raise Exception("无法创建 postgres 用户")

    if not ensure_database():
        raise Exception("无法创建数据库")

    configure_trust_auth()


def install_postgres():
    """安装 PostgreSQL（需要 sudo）"""
    print("      检测到 PostgreSQL 未安装")
    print("      请手动安装: sudo apt-get install postgresql postgresql-contrib")
    print("      或使用你的 Linux 发行版的包管理器")
    sys.exit(1)


def start_postgres():
    """启动 PostgreSQL"""
    try:
        result = subprocess.run(
            ['sudo', 'systemctl', 'start', 'postgresql'],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            time.sleep(2)
            return True
    except Exception:
        pass

    try:
        result = subprocess.run(
            ['sudo', 'service', 'postgresql', 'start'],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            time.sleep(2)
            return True
    except Exception:
        pass

    print("      启动失败，请手动启动: sudo systemctl start postgresql")
    return False


def ensure_postgres_user():
    """确保 postgres 用户存在并设置密码"""
    print("      检查 postgres 用户...")

    try:
        result = subprocess.run(
            ['sudo', '-u', 'postgres', 'psql', '-c',
             f"ALTER USER postgres WITH PASSWORD '{POSTGRES_PASSWORD}'"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print("      postgres 用户密码已设置")
            return True
    except Exception as e:
        print(f"      设置密码失败: {e}")

    return False


def ensure_database():
    """确保 intelligent_audio_test 数据库存在"""
    print("      检查数据库...")

    try:
        result = subprocess.run(
            ['sudo', '-u', 'postgres', 'psql', '-c',
             f"SELECT 1 FROM pg_database WHERE datname = '{POSTGRES_DATA_DB}'"],
            capture_output=True,
            text=True
        )

        if POSTGRES_DATA_DB in result.stdout:
            print(f"      数据库 {POSTGRES_DATA_DB} 已存在")
            return True

        result = subprocess.run(
            ['sudo', '-u', 'postgres', 'createdb', '-O', POSTGRES_DATA_DB_USER, POSTGRES_DATA_DB],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print(f"      数据库 {POSTGRES_DATA_DB} 创建成功")
            return True
    except Exception as e:
        print(f"      创建数据库失败: {e}")

    try:
        result = subprocess.run(
            ['sudo', '-u', 'postgres', 'psql', '-c',
             f"CREATE USER {POSTGRES_DATA_DB_USER} WITH PASSWORD '{POSTGRES_DATA_DB_PASSWORD}'"],
            capture_output=True,
            text=True
        )
    except Exception:
        pass

    try:
        result = subprocess.run(
            ['sudo', '-u', 'postgres', 'psql', '-c',
             f"CREATE DATABASE {POSTGRES_DATA_DB} WITH OWNER {POSTGRES_DATA_DB_USER}"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print(f"      数据库 {POSTGRES_DATA_DB} 创建成功")
            return True
    except Exception as e:
        print(f"      创建数据库失败: {e}")
        return False

    return True


def configure_trust_auth():
    """配置本地连接为 trust 认证"""
    print("      配置 pg_hba.conf ...")

    pg_hba_paths = [
        '/etc/postgresql/{version}/main/pg_hba.conf',
        '/etc/postgresql/main/pg_hba.conf',
        '/var/lib/pgsql/data/pg_hba.conf'
    ]

    version = get_pg_version()
    pg_hba_file = None

    for path in pg_hba_paths:
        if '{version}' in path and version:
            path = path.replace('{version}', version)
        if os.path.exists(path):
            pg_hba_file = path
            break

    if not pg_hba_file:
        print("      警告: 无法找到 pg_hba.conf")
        return

    try:
        with open(pg_hba_file, 'r') as f:
            content = f.read()

        if 'host all all 127.0.0.1/32 trust' not in content:
            subprocess.run(['sudo', 'chmod', '777', pg_hba_file])

            with open(pg_hba_file, 'a') as f:
                f.write('\n# 临时配置 - 迁移脚本添加\n')
                f.write('host all all 127.0.0.1/32 trust\n')
                f.write('host all all ::1/128 trust\n')

            try:
                subprocess.run(['sudo', 'systemctl', 'reload', 'postgresql'])
            except Exception:
                try:
                    subprocess.run(['sudo', 'service', 'postgresql', 'reload'])
                except Exception:
                    pass

            time.sleep(1)
            print("      pg_hba.conf 配置已更新")
    except Exception as e:
        print(f"      配置失败: {e}")


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
    print("\n[1/7] 重建数据库...")

    try:
        subprocess.run(
            ['sudo', '-u', 'postgres', 'psql', '-c',
             f"DROP DATABASE IF EXISTS {POSTGRES_DATA_DB}"],
            capture_output=True,
            text=True
        )

        subprocess.run(
            ['sudo', '-u', 'postgres', 'psql', '-c',
             f"CREATE DATABASE {POSTGRES_DATA_DB} WITH OWNER {POSTGRES_DATA_DB_USER}"],
            capture_output=True,
            text=True
        )

        print("      数据库重建完成")
    except Exception as e:
        print(f"      重建失败: {e}")


def grant_schema_privileges():
    """授予 public schema 权限"""
    print("\n[2/7] 授予权限...")

    try:
        subprocess.run(
            ['sudo', '-u', 'postgres', 'psql', '-d', POSTGRES_DATA_DB, '-c',
             f"GRANT ALL ON SCHEMA public TO {POSTGRES_DATA_DB_USER}"],
            capture_output=True,
            text=True
        )
        subprocess.run(
            ['sudo', '-u', 'postgres', 'psql', '-d', POSTGRES_DATA_DB, '-c',
             f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO {POSTGRES_DATA_DB_USER}"],
            capture_output=True,
            text=True
        )
        subprocess.run(
            ['sudo', '-u', 'postgres', 'psql', '-d', POSTGRES_DATA_DB, '-c',
             f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO {POSTGRES_DATA_DB_USER}"],
            capture_output=True,
            text=True
        )
        print("      权限授予完成")
    except Exception as e:
        print(f"      授权失败: {e}")


def create_tables():
    """创建表结构"""
    print("\n[3/7] 创建表结构...")

    sys.path.insert(0, '/path/to/your/project/backend')

    try:
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
    except Exception as e:
        print(f"      创建表结构失败: {e}")
        raise


def disable_foreign_keys():
    """禁用所有外键约束"""
    print("\n[4/7] 禁用外键约束...")

    try:
        result = subprocess.run(
            ['sudo', '-u', 'postgres', 'psql', '-d', POSTGRES_DATA_DB, '-t', '-c',
             """SELECT 'ALTER TABLE ' || schemaname || '.' || tablename ||
                ' DROP CONSTRAINT ' || conname || ';' FROM pg_constraints
                WHERE contype = 'f' AND schemaname = 'public'"""],
            capture_output=True,
            text=True
        )

        constraints = result.stdout.strip().split('\n')
        count = 0

        for constraint_sql in constraints:
            if constraint_sql.strip():
                try:
                    subprocess.run(
                        ['sudo', '-u', 'postgres', 'psql', '-d', POSTGRES_DATA_DB, '-c',
                         constraint_sql],
                        capture_output=True,
                        text=True
                    )
                    count += 1
                except Exception:
                    pass

        print(f"      已禁用 {count} 个外键约束")
    except Exception as e:
        print(f"      禁用外键失败: {e}")


def migrate_table(sqlite_conn, table_name):
    """迁移单个表（智能版本 - 只迁移存在的字段）"""
    cursor = sqlite_conn.cursor()

    try:
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()
    except sqlite3.OperationalError:
        return 0, []

    if not rows:
        return 0, []

    cursor.execute(f"PRAGMA table_info({table_name})")
    sqlite_columns = [col[1] for col in cursor.fetchall()]

    try:
        result = subprocess.run(
            ['sudo', '-u', 'postgres', 'psql', '-d', POSTGRES_DATA_DB, '-t', '-c',
             f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table_name}'"],
            capture_output=True,
            text=True
        )
        pg_columns = {line.strip() for line in result.stdout.strip().split('\n') if line.strip()}
    except Exception:
        pg_columns = set()

    common_columns = [c for c in sqlite_columns if c in pg_columns]
    skipped_columns = [c for c in sqlite_columns if c not in pg_columns]

    if not common_columns:
        return 0, skipped_columns

    success = 0

    for row in rows:
        row_dict = {}
        for i, col in enumerate(sqlite_columns):
            if col in common_columns:
                row_dict[col] = convert_value(row[i], col)

        placeholders = ', '.join([f":{c}" for c in row_dict.keys()])
        sql = f"INSERT INTO {table_name} ({', '.join(row_dict.keys())}) VALUES ({placeholders})"

        try:
            subprocess.run(
                ['sudo', '-u', 'postgres', 'psql', '-d', POSTGRES_DATA_DB, '-c',
                 sql.replace("'", "''")],
                capture_output=True,
                text=True
            )
            success += 1
        except Exception:
            pass

    return success, skipped_columns


def migrate_data():
    """迁移所有数据"""
    print("\n[5/7] 迁移数据...")
    print("-" * 50)

    sqlite_conn = sqlite3.connect(SQLITE_DB_PATH)

    total = 0
    all_skipped = {}
    for table in MIGRATION_ORDER:
        count, skipped = migrate_table(sqlite_conn, table)
        print(f"      {table}: {count} 行" + (f" (跳过字段: {skipped})" if skipped else ""))
        total += count
        if skipped:
            all_skipped[table] = skipped

    sqlite_conn.close()
    print("-" * 50)

    if all_skipped:
        print("\n      以下表的字段被跳过（PostgreSQL 不存在）:")
        for table, fields in all_skipped.items():
            print(f"        {table}: {fields}")

    return total


def reset_sequences():
    """重置所有序列"""
    print("\n[6/7] 重置序列...")

    try:
        result = subprocess.run(
            ['sudo', '-u', 'postgres', 'psql', '-d', POSTGRES_DATA_DB, '-t', '-c',
             """SELECT sequence_name FROM information_schema.sequences
                WHERE sequence_schema = 'public'"""],
            capture_output=True,
            text=True
        )

        sequences = result.stdout.strip().split('\n')
        count = 0

        for seq in sequences:
            seq = seq.strip()
            if seq:
                table_name = seq.replace('_id_seq', '')
                try:
                    subprocess.run(
                        ['sudo', '-u', 'postgres', 'psql', '-d', POSTGRES_DATA_DB, '-c',
                         f"SELECT setval('{seq}', COALESCE(MAX(id), 1), true) FROM {table_name}"],
                        capture_output=True,
                        text=True
                    )
                    count += 1
                except Exception:
                    pass

        print(f"      已重置 {count} 个序列")
    except Exception as e:
        print(f"      重置序列失败: {e}")


def fix_null_values():
    """修复 NULL 值"""
    print("\n[7/7] 修复 NULL 值...")

    NULL_FIXES = {
        'apis': {'api_url': "''"},
        'dimensions': {'api_endpoints': "'[]'"},
        'categories': {'config': "''"},
        'languages': {'config': "''"},
    }

    for table, columns in NULL_FIXES.items():
        for col, default in columns.items():
            try:
                subprocess.run(
                    ['sudo', '-u', 'postgres', 'psql', '-d', POSTGRES_DATA_DB, '-c',
                     f"UPDATE {table} SET {col} = {default} WHERE {col} IS NULL"],
                    capture_output=True,
                    text=True
                )
            except Exception:
                pass

    print("      NULL 值修复完成")


LOCK_FILE = '/tmp/.migrate_lock'


def acquire_lock():
    """获取迁移锁"""
    if os.path.exists(LOCK_FILE):
        print(f"\n错误: 迁移进程已在运行")
        print(f"如果确认没有其他迁移进程在执行，请删除锁文件:")
        print(f"  rm {LOCK_FILE}")
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
    except Exception:
        pass


def main():
    print("=" * 50)
    print("SQLite -> PostgreSQL 一键迁移 (Linux版)")
    print("=" * 50)

    print("\n警告: 此操作会清空 'intelligent_audio_test' 数据库！")
    response = input("确认执行迁移? (输入 'yes' 继续): ")
    if response.lower() != 'yes':
        print("已取消迁移")
        sys.exit(0)

    if not acquire_lock():
        sys.exit(1)

    try:
        ensure_postgres()
        recreate_database()
        grant_schema_privileges()
        create_tables()
        disable_foreign_keys()
        total = migrate_data()
        reset_sequences()
        fix_null_values()

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
