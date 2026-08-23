# -*- coding: utf-8 -*-
"""
测试用例数据导出脚本

功能：
  将当前数据库中的用例相关数据（test_case_groups, test_cases, test_case_tags,
  tags, tag_categories）导出为 SQL 文件，同时打包参考参数文件，
  方便导入到另一个环境的数据库。

使用方法：
  python backend/scripts/export_testcases.py
  python backend/scripts/export_testcases.py --db-uri "postgresql://user:pass@host:port/dbname"

输出：
  backend/scripts/testcase_export/testcase_export_<timestamp>.sql   — SQL 插入语句
  backend/scripts/testcase_export/ref_params_<timestamp>/            — 参考参数文件目录
"""

import os
import sys
import json
import argparse
import shutil
from datetime import datetime, timezone, timedelta

# 把项目根目录加入 sys.path，使 backend.* 等包可导入
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_SCRIPT_DIR))
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, os.path.dirname(os.path.dirname(_SCRIPT_DIR)))  # backend/

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# 东八区
def now_cst():
    return datetime.now(timezone(timedelta(hours=8)))

# 默认数据库连接（与 config.py 一致）
DEFAULT_DB_USER = os.environ.get('DB_USER', 'intelligent_audio_test')
DEFAULT_DB_PASSWORD = os.environ.get('DB_PASSWORD', 'intelligent_audio_test666')
DEFAULT_DB_HOST = os.environ.get('DB_HOST', 'localhost')
DEFAULT_DB_PORT = os.environ.get('DB_PORT', '5432')
DEFAULT_DB_NAME = os.environ.get('DB_NAME', 'intelligent_audio_test')

# 参考参数文件存储路径（与 config.py 中 Config.REF_PARAMS_STORAGE_PATH 一致）
# 优先使用环境变量，否则使用 Config 中的默认路径
_PROJECT_ROOT_CONFIG = r'C:\S2TT\auto_test\ver8\202604231600\Intelligent-Audio-TEST'
DEFAULT_REF_PARAMS_PATH = os.path.join(_PROJECT_ROOT_CONFIG, 'static', 'ref_params')
REF_PARAMS_STORAGE_PATH = os.environ.get('REF_PARAMS_STORAGE_PATH', DEFAULT_REF_PARAMS_PATH)

# 用例相关表及导出顺序（依赖关系）
EXPORT_TABLES = [
    'tag_categories',
    'tags',
    'test_case_groups',
    'test_cases',
    'test_case_tags',
]


def get_engine(db_uri):
    """创建 SQLAlchemy 引擎"""
    engine = create_engine(db_uri, isolation_level='AUTOCOMMIT')
    return engine


def escape_sql_value(val):
    """将 Python 值转义为 SQL 字面量"""
    if val is None:
        return 'NULL'
    if isinstance(val, bool):
        return 'TRUE' if val else 'FALSE'
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, str):
        escaped = val.replace("'", "''")
        return f"'{escaped}'"
    if isinstance(val, (list, dict)):
        # JSON 类型，序列化为字符串
        s = json.dumps(val, ensure_ascii=False)
        escaped = s.replace("'", "''")
        return f"'{escaped}'::jsonb"
    # bytes
    if isinstance(val, bytes):
        # 尝试解码
        try:
            s = val.decode('utf-8')
            escaped = s.replace("'", "''")
            return f"'{escaped}'"
        except UnicodeDecodeError:
            return f"'{val.hex()}'"
    return 'NULL'


def table_columns(engine, table_name):
    """获取表的列名列表"""
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = :tname AND table_schema = 'public' "
            "ORDER BY ordinal_position"
        ), {"tname": table_name})
        return [(row[0], row[1]) for row in result]


def table_row_count(engine, table_name):
    """获取表的行数"""
    with engine.connect() as conn:
        result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
        return result.scalar()


def export_table_to_sql(engine, table_name, output_file):
    """将表数据导出为 SQL INSERT 语句"""
    columns = table_columns(engine, table_name)
    col_names = [c[0] for c in columns]

    with engine.connect() as conn:
        result = conn.execute(text(f"SELECT {', '.join(col_names)} FROM {table_name} ORDER BY 1"))
        rows = result.fetchall()

    if not rows:
        print(f"  [跳过] 表 {table_name} 无数据")
        return 0

    with open(output_file, 'a', encoding='utf-8') as f:
        f.write(f"\n-- ============================================\n")
        f.write(f"-- Table: {table_name}  ({len(rows)} rows)\n")
        f.write(f"-- ============================================\n")

        # 先清空目标表（导入时使用）
        f.write(f"DELETE FROM {table_name};\n")

        for row in rows:
            values = [escape_sql_value(row[i]) for i in range(len(col_names))]
            f.write(
                f"INSERT INTO {table_name} ({', '.join(col_names)}) "
                f"VALUES ({', '.join(values)});\n"
            )

    print(f"  [完成] 表 {table_name}: {len(rows)} 行")
    return len(rows)


def export_ref_params_files(test_cases, export_dir):
    """导出参考参数文件"""
    ref_params_dir = os.path.join(export_dir, 'ref_params')
    os.makedirs(ref_params_dir, exist_ok=True)

    found_count = 0
    missing_count = 0

    for tc in test_cases:
        tc_id = tc[0]
        config = tc[1] if isinstance(tc[1], dict) else {}
        if config is None:
            config = {}

        # 检查 rounds 中的 referenceParamsPath
        rounds = config.get('rounds', [])
        for r in rounds:
            if isinstance(r, dict):
                ref_path = r.get('referenceParamsPath') or r.get('reference_params_path')
                if ref_path:
                    # ref_path 可能是相对路径或绝对路径
                    src_path = ref_path
                    if not os.path.isabs(src_path):
                        src_path = os.path.join(_PROJECT_ROOT_CONFIG, src_path.lstrip('/\\'))
                        src_path = os.path.normpath(src_path)

                    if os.path.isfile(src_path):
                        # 保持目录结构，用 tc_id 做子目录
                        dest_subdir = os.path.join(ref_params_dir, tc_id)
                        os.makedirs(dest_subdir, exist_ok=True)
                        dest_path = os.path.join(dest_subdir, os.path.basename(src_path))
                        shutil.copy2(src_path, dest_path)
                        found_count += 1
                    else:
                        print(f"  [警告] 参考参数文件不存在: {src_path} (用例 {tc_id})")
                        missing_count += 1

        # 同时检查 algorithm_params 列中的 reference_params_path
        # (已在 tc.reference_params 列中，但那个列存的是路径不是内容)

    print(f"  参考参数文件: 复制 {found_count} 个, 缺失 {missing_count} 个")
    return found_count


def get_all_test_cases(engine):
    """获取所有用例的 id 和 config（用于查找参考参数文件）"""
    with engine.connect() as conn:
        result = conn.execute(text("SELECT id, config FROM test_cases WHERE deleted = false ORDER BY id"))
        return result.fetchall()


def main():
    parser = argparse.ArgumentParser(description='导出测试用例数据')
    parser.add_argument('--db-uri', type=str, default=None,
                        help='数据库连接URI (如: postgresql://user:pass@host:port/dbname)')
    parser.add_argument('--output-dir', type=str, default=None,
                        help='输出目录 (默认: backend/scripts/testcase_export/)')
    args = parser.parse_args()

    # 构建数据库 URI
    if args.db_uri:
        db_uri = args.db_uri
    else:
        db_uri = f'postgresql://{DEFAULT_DB_USER}:{DEFAULT_DB_PASSWORD}@{DEFAULT_DB_HOST}:{DEFAULT_DB_PORT}/{DEFAULT_DB_NAME}'

    print(f"数据库: {db_uri.replace(DEFAULT_DB_PASSWORD, '****') if DEFAULT_DB_PASSWORD in db_uri else db_uri}")
    print(f"参考参数路径: {REF_PARAMS_STORAGE_PATH}")

    # 输出目录
    timestamp = now_cst().strftime('%Y%m%d_%H%M%S')
    export_dir = args.output_dir or os.path.join(_SCRIPT_DIR, 'testcase_export')
    os.makedirs(export_dir, exist_ok=True)

    sql_file = os.path.join(export_dir, f'testcase_export_{timestamp}.sql')

    print(f"\n开始导出用例数据...")

    engine = get_engine(db_uri)

    # 导出各表数据
    total_rows = 0
    for table in EXPORT_TABLES:
        count = table_row_count(engine, table)
        print(f"  表 {table}: {count} 行")
        rows = export_table_to_sql(engine, table, sql_file)
        total_rows += rows

    # 添加序列重置语句
    with open(sql_file, 'a', encoding='utf-8') as f:
        f.write(f"\n-- 重置序列 (PostgreSQL)\n")
        for table in EXPORT_TABLES:
            # 尝试重置序列
            f.write(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {table}), 0) + 1, false);\n")

    print(f"\n数据库导出完成: {sql_file}")
    print(f"总行数: {total_rows}")

    # 导出参考参数文件
    print(f"\n导出参考参数文件...")
    test_cases = get_all_test_cases(engine)
    found = export_ref_params_files(test_cases, export_dir)

    # 生成导入说明
    readme_file = os.path.join(export_dir, 'README_IMPORT.txt')
    with open(readme_file, 'w', encoding='utf-8') as f:
        f.write("=" * 60 + "\n")
        f.write("测试用例数据导入说明\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"导出时间: {now_cst().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"数据库表行数: {total_rows}\n")
        f.write(f"参考参数文件数: {found}\n\n")
        f.write("导入步骤:\n")
        f.write("1. 确保目标数据库已创建表结构 (运行 flask app 初始化)\n")
        f.write("2. 执行 SQL 文件导入数据:\n")
        f.write(f"   psql -h <host> -U <user> -d <dbname> -f {os.path.basename(sql_file)}\n")
        f.write("   或使用 pgAdmin / DBeaver 等工具执行 SQL 文件\n\n")
        f.write("3. 复制参考参数文件到目标环境的 static/ref_params/ 目录\n")
        f.write(f"   将 ref_params/ 目录下的内容复制到目标服务器的 static/ref_params/\n")
        f.write(f"   保持子目录结构 (用例ID/文件名)\n\n")
        f.write("注意:\n")
        f.write("- SQL 文件包含 DELETE FROM 语句，会先清空目标表再插入\n")
        f.write("- 如果目标数据库已有同ID数据，将被覆盖\n")
        f.write("- 参考参数文件路径在 config.rounds[].referenceParamsPath 中记录\n")
        f.write("  导入后需确保文件路径在目标环境可访问\n")

    print(f"\n导入说明: {readme_file}")
    print(f"\n{'=' * 60}")
    print(f"导出完成! 文件位于: {export_dir}")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    main()
