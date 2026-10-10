# -*- coding: utf-8 -*-
"""迁移脚本：设备管理 5 表 + 索引（INT-80 设备管理缺口包）

功能：
- 建 device_groups 表（设备分组，区别于用例分组 test_case_groups）+ 组名部分唯一索引（并发重名兜底）
- 建 device_group_members 表（分组-设备成员关联，(group_id, device_id) 唯一）
- 建 device_status_events 表（状态历史：在线/离线/健康检查/操作事件落库）
- 建 device_alarm_rules 表（告警规则：离线时长/健康失败次数/CPU/内存/电池阈值）
- 建 device_alarms 表（告警记录：触发→确认→恢复）

DDL 与 device_service/infrastructure/persistence/models/device_models.py 的 ORM 元数据
逐列对齐（client-side default 不入 DDL，server_default 仅 func.now() 时间戳列），
保证全新库（create_all_tables.py）与既有库（本脚本）结构一致。

幂等，可重复执行（表/索引已存在即 SKIP）。

用法:
    python scripts/migrations/202610/add_device_management_tables.py [--dry-run]

依赖:
    pip install psycopg2-binary python-dotenv
"""
import os
import sys
import argparse

from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    print('未配置 DATABASE_URL 环境变量（.env 或环境）', file=sys.stderr)
    sys.exit(1)
parsed = urlparse(DATABASE_URL)
DB_HOST = parsed.hostname
DB_PORT = parsed.port or 5432
DB_NAME = parsed.path.lstrip('/')
DB_USER = parsed.username
DB_PASS = parsed.password


def _table_exists(cur, table):
    cur.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = %s", (table,)
    )
    return cur.fetchone() is not None


def _index_exists(cur, index):
    cur.execute("SELECT 1 FROM pg_indexes WHERE indexname = %s", (index,))
    return cur.fetchone() is not None


TABLE_DDL = {
    'device_groups': """
        CREATE TABLE device_groups (
            id VARCHAR(50) PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            description TEXT,
            group_type VARCHAR(20) NOT NULL,
            created_by_user_id BIGINT,
            updated_by_user_id BIGINT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            deleted BOOLEAN NOT NULL,
            deleted_at TIMESTAMP
        )
    """,
    'device_group_members': """
        CREATE TABLE device_group_members (
            id SERIAL PRIMARY KEY,
            group_id VARCHAR(50) NOT NULL,
            device_id INTEGER NOT NULL,
            created_by_user_id BIGINT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """,
    'device_status_events': """
        CREATE TABLE device_status_events (
            id BIGSERIAL PRIMARY KEY,
            device_id INTEGER NOT NULL,
            event_type VARCHAR(20) NOT NULL,
            from_status VARCHAR(20),
            to_status VARCHAR(20),
            source VARCHAR(50),
            success BOOLEAN,
            detail JSON,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """,
    'device_alarm_rules': """
        CREATE TABLE device_alarm_rules (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            metric_type VARCHAR(30) NOT NULL,
            threshold_value DOUBLE PRECISION NOT NULL,
            severity VARCHAR(20) NOT NULL,
            notify_email BOOLEAN NOT NULL,
            enabled BOOLEAN NOT NULL,
            created_by_user_id BIGINT,
            updated_by_user_id BIGINT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            deleted BOOLEAN NOT NULL
        )
    """,
    'device_alarms': """
        CREATE TABLE device_alarms (
            id SERIAL PRIMARY KEY,
            rule_id INTEGER,
            rule_name VARCHAR(100),
            device_id INTEGER NOT NULL,
            device_name VARCHAR(100),
            metric_type VARCHAR(30) NOT NULL,
            severity VARCHAR(20) NOT NULL,
            status VARCHAR(20) NOT NULL,
            trigger_value DOUBLE PRECISION,
            threshold_value DOUBLE PRECISION,
            content TEXT,
            email_sent BOOLEAN NOT NULL,
            email_error TEXT,
            triggered_at TIMESTAMP NOT NULL DEFAULT NOW(),
            acknowledged_at TIMESTAMP,
            acknowledged_by VARCHAR(100),
            resolved_at TIMESTAMP
        )
    """,
}

INDEX_DDL = [
    # device_groups（ix_* 对齐 ORM index=True 自动命名）
    ('ix_device_groups_name',
     'CREATE INDEX ix_device_groups_name ON device_groups (name)'),
    ('ix_device_groups_created_by_user_id',
     'CREATE INDEX ix_device_groups_created_by_user_id ON device_groups (created_by_user_id)'),
    # 组名并发重名兜底：仅约束未删除分组（软删除后组名可复用）
    ('uq_device_group_name_active',
     'CREATE UNIQUE INDEX uq_device_group_name_active ON device_groups (name) WHERE deleted = false'),
    # device_group_members
    ('uq_device_group_member',
     'CREATE UNIQUE INDEX uq_device_group_member ON device_group_members (group_id, device_id)'),
    ('ix_device_group_members_group_id',
     'CREATE INDEX ix_device_group_members_group_id ON device_group_members (group_id)'),
    ('ix_device_group_members_device_id',
     'CREATE INDEX ix_device_group_members_device_id ON device_group_members (device_id)'),
    # device_status_events
    ('ix_status_event_device_time',
     'CREATE INDEX ix_status_event_device_time ON device_status_events (device_id, created_at)'),
    ('ix_device_status_events_device_id',
     'CREATE INDEX ix_device_status_events_device_id ON device_status_events (device_id)'),
    ('ix_device_status_events_created_at',
     'CREATE INDEX ix_device_status_events_created_at ON device_status_events (created_at)'),
    # device_alarm_rules
    ('ix_device_alarm_rules_metric_type',
     'CREATE INDEX ix_device_alarm_rules_metric_type ON device_alarm_rules (metric_type)'),
    # device_alarms
    ('ix_alarm_status_time',
     'CREATE INDEX ix_alarm_status_time ON device_alarms (status, triggered_at)'),
    ('ix_device_alarms_device_id',
     'CREATE INDEX ix_device_alarms_device_id ON device_alarms (device_id)'),
    ('ix_device_alarms_status',
     'CREATE INDEX ix_device_alarms_status ON device_alarms (status)'),
]


def main(dry_run=False):
    import psycopg2
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS,
    )
    cur = conn.cursor()
    total_steps = 0

    # 1. 建表
    for table, ddl in TABLE_DDL.items():
        if _table_exists(cur, table):
            print(f'SKIP: 表 {table} 已存在')
            continue
        print(f'APPLY: 创建表 {table}')
        if not dry_run:
            cur.execute(ddl)
        total_steps += 1

    # 2. 建索引
    for index, ddl in INDEX_DDL:
        if _index_exists(cur, index):
            print(f'SKIP: 索引 {index} 已存在')
            continue
        print(f'APPLY: 创建索引 {index}')
        if not dry_run:
            cur.execute(ddl)
        total_steps += 1

    if dry_run:
        conn.rollback()
        print(f'[DRY-RUN] 共 {total_steps} 步待执行')
    else:
        conn.commit()
        print(f'完成：共执行 {total_steps} 步')
    cur.close()
    conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='设备管理 5 表 + 索引迁移（INT-80）')
    parser.add_argument('--dry-run', action='store_true', help='只检查不执行')
    args = parser.parse_args()
    main(dry_run=args.dry_run)
