#!/usr/bin/env python3
"""
迁移脚本：创建 service_registry 表 + logs.service_name 字段

对应 SQL：scripts/migrations/202607/create_service_registry.sql

用法：
  # 使用默认 DB 连接
  python scripts/migrations/202607/create_service_registry.py

  # 指定数据库 URL
  DATABASE_URL=postgresql://user:pass@host:5432/dbname \
    python scripts/migrations/202607/create_service_registry.py

  # 干跑（只打印 SQL，不执行）
  python scripts/migrations/202607/create_service_registry.py --dry-run

环境变量：
  DATABASE_URL            数据库连接字符串
                         （默认 postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test）
"""
import os
import sys
import argparse
import logging
from pathlib import Path

# 添加项目根目录到 path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(PROJECT_ROOT / 'migration_service_registry.log', encoding='utf-8'),
    ]
)
logger = logging.getLogger(__name__)


# ============================================================
# SQL 语句
# ============================================================
SQL_CREATE_SERVICE_REGISTRY = """
CREATE TABLE IF NOT EXISTS service_registry (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    type VARCHAR(50) NOT NULL,
    host VARCHAR(255) NOT NULL,
    port INTEGER NOT NULL,
    grpc_port INTEGER,
    status VARCHAR(20) DEFAULT 'offline',
    capabilities JSONB,
    metadata JSONB,
    running_tasks INTEGER DEFAULT 0,
    cpu_load FLOAT DEFAULT 0.0,
    last_dispatch_at TIMESTAMP,
    last_heartbeat TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
""".strip()

SQL_CREATE_INDEX_TYPE = """
CREATE INDEX IF NOT EXISTS idx_service_registry_type
    ON service_registry(type);
""".strip()

SQL_CREATE_INDEX_STATUS = """
CREATE INDEX IF NOT EXISTS idx_service_registry_status
    ON service_registry(status);
""".strip()

SQL_ADD_SERVICE_NAME = """
ALTER TABLE logs ADD COLUMN IF NOT EXISTS service_name VARCHAR(50)
    NOT NULL DEFAULT 'backend';
""".strip()

SQL_CREATE_INDEX_LOG_SERVICE = """
CREATE INDEX IF NOT EXISTS idx_logs_service_name
    ON logs(service_name);
""".strip()

# 迁移后验证查询
SQL_VERIFY_SERVICE_REGISTRY = """
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'service_registry'
ORDER BY ordinal_position;
""".strip()

SQL_VERIFY_LOGS_SERVICE_NAME = """
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'logs' AND column_name = 'service_name';
""".strip()

SQL_COUNT_LOGS_BY_SERVICE = """
SELECT service_name, COUNT(*) as cnt
FROM logs
GROUP BY service_name
ORDER BY cnt DESC;
""".strip()

SQL_COUNT_SERVICES = "SELECT COUNT(*) FROM service_registry;".strip()


# ============================================================
# 迁移主流程
# ============================================================
def run_migration(dry_run: bool = False):
    """执行迁移"""
    from sqlalchemy import create_engine, text

    db_url = os.environ.get(
        'DATABASE_URL',
        'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'
    )

    logger.info("=" * 60)
    logger.info("迁移：创建 service_registry 表 + logs.service_name 字段")
    logger.info("=" * 60)
    logger.info(f"数据库: {db_url.split('@')[-1] if '@' in db_url else db_url}")
    logger.info(f"模式: {'DRY-RUN（只打印 SQL）' if dry_run else '实际执行'}")

    if dry_run:
        # 干跑：只打印 SQL
        logger.info("\n--- 将执行的 SQL ---\n")
        for label, sql in [
            ("1. 创建 service_registry 表", SQL_CREATE_SERVICE_REGISTRY),
            ("2. 创建索引 idx_service_registry_type", SQL_CREATE_INDEX_TYPE),
            ("3. 创建索引 idx_service_registry_status", SQL_CREATE_INDEX_STATUS),
            ("4. logs 表添加 service_name 字段", SQL_ADD_SERVICE_NAME),
            ("5. 创建索引 idx_logs_service_name", SQL_CREATE_INDEX_LOG_SERVICE),
        ]:
            logger.info(f"\n[{label}]")
            print(sql)
            print(";")
        logger.info("\n--- DRY-RUN 结束，未实际执行 ---\n")
        return

    # 实际执行
    engine = create_engine(db_url, pool_pre_ping=True)

    with engine.connect() as conn:
        # 1. 创建 service_registry 表
        logger.info("1/5  创建 service_registry 表...")
        conn.execute(text(SQL_CREATE_SERVICE_REGISTRY))
        conn.execute(text("COMMIT;"))
        logger.info("     ✓ service_registry 表已创建")

        # 2. 创建索引
        logger.info("2/5  创建索引 idx_service_registry_type...")
        conn.execute(text(SQL_CREATE_INDEX_TYPE))
        conn.execute(text("COMMIT;"))
        logger.info("     ✓ idx_service_registry_type 已创建")

        logger.info("3/5  创建索引 idx_service_registry_status...")
        conn.execute(text(SQL_CREATE_INDEX_STATUS))
        conn.execute(text("COMMIT;"))
        logger.info("     ✓ idx_service_registry_status 已创建")

        # 4. logs 添加 service_name 字段
        logger.info("4/5  logs 表添加 service_name 字段...")
        conn.execute(text(SQL_ADD_SERVICE_NAME))
        conn.execute(text("COMMIT;"))
        logger.info("     ✓ logs.service_name 字段已添加（默认值 'backend'）")

        # 5. logs service_name 索引
        logger.info("5/5  创建索引 idx_logs_service_name...")
        conn.execute(text(SQL_CREATE_INDEX_LOG_SERVICE))
        conn.execute(text("COMMIT;"))
        logger.info("     ✓ idx_logs_service_name 已创建")

    # 验证
    logger.info("\n" + "=" * 60)
    logger.info("验证迁移结果")
    logger.info("=" * 60)

    with engine.connect() as conn:
        # 验证 service_registry 表结构
        logger.info("\n[service_registry 表结构]")
        rows = conn.execute(text(SQL_VERIFY_SERVICE_REGISTRY)).fetchall()
        for row in rows:
            nullable = "NULL" if row[2] == "YES" else "NOT NULL"
            default = row[3] or "-"
            logger.info(f"  {row[0]:25s} {row[1]:20s} {nullable:8s} default={default}")

        # 验证 service_registry 记录数
        count = conn.execute(text(SQL_COUNT_SERVICES)).scalar()
        logger.info(f"\n  service_registry 记录数: {count}")

        # 验证 logs.service_name 字段
        logger.info("\n[logs.service_name 字段]")
        rows = conn.execute(text(SQL_VERIFY_LOGS_SERVICE_NAME)).fetchall()
        if rows:
            logger.info(f"  字段名: {rows[0][0]}, 类型: {rows[0][1]}")
        else:
            logger.warning("  ⚠ 未找到 service_name 字段")

        # 验证 logs 按 service_name 分组统计
        logger.info("\n[logs 按 service_name 分组统计]")
        rows = conn.execute(text(SQL_COUNT_LOGS_BY_SERVICE)).fetchall()
        if rows:
            for row in rows:
                logger.info(f"  {row[0]:20s} {row[1]} 条")
        else:
            logger.info("  （logs 表为空）")

    logger.info("\n" + "=" * 60)
    logger.info("迁移完成！")
    logger.info("=" * 60)
    logger.info("\n后续步骤：")
    logger.info("  1. 启动各服务后，它们会自动注册到 service_registry 表")
    logger.info("  2. logs 表新增的 service_name 字段默认值为 'backend'，")
    logger.info("     各服务启动后新写入的日志会带上对应的 service_name")
    logger.info("  3. 如需回填历史日志的 service_name，可执行：")
    logger.info("     UPDATE logs SET service_name = 'api_gateway' WHERE service_name = 'backend';")


def main():
    parser = argparse.ArgumentParser(
        description='创建 service_registry 表 + logs.service_name 字段'
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='只打印 SQL，不实际执行'
    )
    args = parser.parse_args()

    try:
        run_migration(dry_run=args.dry_run)
    except Exception as e:
        logger.error(f"迁移失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
