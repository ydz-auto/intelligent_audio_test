# -*- coding: utf-8 -*-
"""
实验室扩展：新建实验室表 + 给现有表加 lab_id
===================================

目标：
1. 创建 laboratories 实验室主表
2. 创建 task_laboratory_relations 任务-实验室关联表（N:M）
3. 给 devices / playback_devices / test_results / task_case_relations / logs 表加 lab_id 列
4. 给 task_device_relations 表加 lab_id 列（冗余，便于按实验室查询任务设备）
5. 添加 lab_id 相关索引

注意：
- spl_mappings 不加 lab_id（用户明确不需要）
- test_cases 不加列，lab_id 存 config JSONB（为空=通用用例，有值=专属用例）
- calibration_history 不加列，通过 mapping_id 间接关联

幂等性：脚本可重复执行，已完成的操作会被跳过。

用法:
    python add_laboratory_tables.py              # 正式执行
    python add_laboratory_tables.py --dry-run    # 仅预览
    python add_laboratory_tables.py --step 2     # 仅执行第 2 步

依赖:
    pip install sqlalchemy psycopg2-binary
"""

import os
import sys

from sqlalchemy import create_engine, text

# ========================================================================
# 配置
# ========================================================================

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666'
    '@localhost:5432/intelligent_audio_test'
)


# ========================================================================
# 辅助函数
# ========================================================================

def _table_exists(conn, table_name):
    """检查表是否存在"""
    result = conn.execute(text(
        "SELECT to_regclass(:t)"
    ), {"t": f'public.{table_name}'})
    return result.scalar() is not None


def _column_exists(conn, table, column):
    """检查列是否已存在"""
    result = conn.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :table AND column_name = :column"
    ), {"table": table, "column": column})
    return result.fetchone() is not None


def _index_exists(conn, index_name):
    """检查索引是否已存在"""
    result = conn.execute(text(
        "SELECT 1 FROM pg_indexes WHERE indexname = :name"
    ), {"name": index_name})
    return result.fetchone() is not None


def _exec_ddl(conn, sql, success_msg, skip_msg):
    """在独立 SAVEPOINT 中执行 DDL，失败时按消息判断是否跳过"""
    savepoint = conn.begin_nested()
    try:
        conn.execute(text(sql))
        savepoint.commit()
        print(f"  [OK] {success_msg}")
    except Exception as e:
        savepoint.rollback()
        msg = str(e).lower()
        if 'already' in msg or 'duplicate' in msg or 'exists' in msg \
                or 'does not exist' in msg or 'not found' in msg:
            print(f"  [SKIP] {skip_msg}")
        else:
            raise


# ========================================================================
# Step 1: 创建 laboratories 实验室主表
# ========================================================================

def step1_create_laboratories(engine, dry_run=False):
    """创建 laboratories 实验室主表"""
    print("\n" + "=" * 60)
    print("Step 1: 创建 laboratories 实验室主表")
    print("=" * 60)

    if dry_run:
        with engine.connect() as conn:
            exists = _table_exists(conn, 'laboratories')
            print(f"  [DRY-RUN] laboratories 表存在: {exists}")
        return

    with engine.begin() as conn:
        _exec_ddl(
            conn,
            """
            CREATE TABLE IF NOT EXISTS laboratories (
                id SERIAL PRIMARY KEY,
                code VARCHAR(50) UNIQUE NOT NULL,
                name VARCHAR(100) NOT NULL,
                building VARCHAR(50),
                floor VARCHAR(20),
                room_number VARCHAR(50),
                description TEXT,
                status VARCHAR(20) DEFAULT 'active',
                deleted BOOLEAN DEFAULT FALSE,
                deleted_at TIMESTAMP,
                created_by_user_id BIGINT,
                updated_by_user_id BIGINT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
            """,
            "创建表: laboratories",
            "laboratories 表已存在",
        )
        _exec_ddl(
            conn,
            "CREATE INDEX IF NOT EXISTS idx_laboratories_code ON laboratories(code)",
            "创建索引: idx_laboratories_code",
            "索引 idx_laboratories_code 已存在",
        )
        _exec_ddl(
            conn,
            "CREATE INDEX IF NOT EXISTS idx_laboratories_status ON laboratories(status)",
            "创建索引: idx_laboratories_status",
            "索引 idx_laboratories_status 已存在",
        )


# ========================================================================
# Step 2: 创建 task_laboratory_relations 任务-实验室关联表
# ========================================================================

def step2_create_task_laboratory_relations(engine, dry_run=False):
    """创建 task_laboratory_relations 任务-实验室关联表（N:M）"""
    print("\n" + "=" * 60)
    print("Step 2: 创建 task_laboratory_relations 任务-实验室关联表")
    print("=" * 60)

    if dry_run:
        with engine.connect() as conn:
            exists = _table_exists(conn, 'task_laboratory_relations')
            print(f"  [DRY-RUN] task_laboratory_relations 表存在: {exists}")
        return

    with engine.begin() as conn:
        _exec_ddl(
            conn,
            """
            CREATE TABLE IF NOT EXISTS task_laboratory_relations (
                id BIGSERIAL PRIMARY KEY,
                task_id INTEGER NOT NULL,
                lab_id INTEGER NOT NULL,
                priority INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(task_id, lab_id)
            )
            """,
            "创建表: task_laboratory_relations",
            "task_laboratory_relations 表已存在",
        )
        _exec_ddl(
            conn,
            "CREATE INDEX IF NOT EXISTS idx_task_lab_relations_task_id ON task_laboratory_relations(task_id)",
            "创建索引: idx_task_lab_relations_task_id",
            "索引 idx_task_lab_relations_task_id 已存在",
        )
        _exec_ddl(
            conn,
            "CREATE INDEX IF NOT EXISTS idx_task_lab_relations_lab_id ON task_laboratory_relations(lab_id)",
            "创建索引: idx_task_lab_relations_lab_id",
            "索引 idx_task_lab_relations_lab_id 已存在",
        )


# ========================================================================
# Step 3: 给 devices 表加 lab_id
# ========================================================================

def step3_add_lab_id_to_devices(engine, dry_run=False):
    """给 devices 表加 lab_id 列"""
    print("\n" + "=" * 60)
    print("Step 3: 给 devices 表加 lab_id")
    print("=" * 60)

    if dry_run:
        with engine.connect() as conn:
            if _table_exists(conn, 'devices'):
                has_col = _column_exists(conn, 'devices', 'lab_id')
                print(f"  [DRY-RUN] devices.lab_id 存在: {has_col}")
            else:
                print("  [DRY-RUN] devices 表不存在")
        return

    with engine.begin() as conn:
        if not _table_exists(conn, 'devices'):
            print("  [SKIP] devices 表不存在")
            return

        _exec_ddl(
            conn,
            "ALTER TABLE devices ADD COLUMN lab_id INTEGER",
            "新增列: devices.lab_id",
            "devices.lab_id 已存在",
        )
        _exec_ddl(
            conn,
            "CREATE INDEX IF NOT EXISTS idx_devices_lab_id ON devices(lab_id)",
            "创建索引: idx_devices_lab_id",
            "索引 idx_devices_lab_id 已存在",
        )


# ========================================================================
# Step 4: 给 playback_devices 表加 lab_id
# ========================================================================

def step4_add_lab_id_to_playback_devices(engine, dry_run=False):
    """给 playback_devices 表加 lab_id 列"""
    print("\n" + "=" * 60)
    print("Step 4: 给 playback_devices 表加 lab_id")
    print("=" * 60)

    if dry_run:
        with engine.connect() as conn:
            if _table_exists(conn, 'playback_devices'):
                has_col = _column_exists(conn, 'playback_devices', 'lab_id')
                print(f"  [DRY-RUN] playback_devices.lab_id 存在: {has_col}")
            else:
                print("  [DRY-RUN] playback_devices 表不存在")
        return

    with engine.begin() as conn:
        if not _table_exists(conn, 'playback_devices'):
            print("  [SKIP] playback_devices 表不存在")
            return

        _exec_ddl(
            conn,
            "ALTER TABLE playback_devices ADD COLUMN lab_id INTEGER",
            "新增列: playback_devices.lab_id",
            "playback_devices.lab_id 已存在",
        )
        _exec_ddl(
            conn,
            "CREATE INDEX IF NOT EXISTS idx_playback_devices_lab_id ON playback_devices(lab_id)",
            "创建索引: idx_playback_devices_lab_id",
            "索引 idx_playback_devices_lab_id 已存在",
        )


# ========================================================================
# Step 5: 给 test_results 表加 lab_id
# ========================================================================

def step5_add_lab_id_to_test_results(engine, dry_run=False):
    """给 test_results 表加 lab_id 列（标识测试结果来自哪个实验室）"""
    print("\n" + "=" * 60)
    print("Step 5: 给 test_results 表加 lab_id")
    print("=" * 60)

    if dry_run:
        with engine.connect() as conn:
            if _table_exists(conn, 'test_results'):
                has_col = _column_exists(conn, 'test_results', 'lab_id')
                print(f"  [DRY-RUN] test_results.lab_id 存在: {has_col}")
            else:
                print("  [DRY-RUN] test_results 表不存在")
        return

    with engine.begin() as conn:
        if not _table_exists(conn, 'test_results'):
            print("  [SKIP] test_results 表不存在")
            return

        _exec_ddl(
            conn,
            "ALTER TABLE test_results ADD COLUMN lab_id INTEGER",
            "新增列: test_results.lab_id",
            "test_results.lab_id 已存在",
        )
        _exec_ddl(
            conn,
            "CREATE INDEX IF NOT EXISTS idx_test_results_lab_id ON test_results(lab_id)",
            "创建索引: idx_test_results_lab_id",
            "索引 idx_test_results_lab_id 已存在",
        )


# ========================================================================
# Step 6: 给 task_case_relations 表加 lab_id
# ========================================================================

def step6_add_lab_id_to_task_case_relations(engine, dry_run=False):
    """给 task_case_relations 表加 lab_id 列（同一用例在不同实验室执行时状态需区分）"""
    print("\n" + "=" * 60)
    print("Step 6: 给 task_case_relations 表加 lab_id")
    print("=" * 60)

    if dry_run:
        with engine.connect() as conn:
            if _table_exists(conn, 'task_case_relations'):
                has_col = _column_exists(conn, 'task_case_relations', 'lab_id')
                print(f"  [DRY-RUN] task_case_relations.lab_id 存在: {has_col}")
            else:
                print("  [DRY-RUN] task_case_relations 表不存在")
        return

    with engine.begin() as conn:
        if not _table_exists(conn, 'task_case_relations'):
            print("  [SKIP] task_case_relations 表不存在")
            return

        _exec_ddl(
            conn,
            "ALTER TABLE task_case_relations ADD COLUMN lab_id INTEGER",
            "新增列: task_case_relations.lab_id",
            "task_case_relations.lab_id 已存在",
        )
        _exec_ddl(
            conn,
            "CREATE INDEX IF NOT EXISTS idx_task_case_relations_lab_id ON task_case_relations(lab_id)",
            "创建索引: idx_task_case_relations_lab_id",
            "索引 idx_task_case_relations_lab_id 已存在",
        )


# ========================================================================
# Step 7: 给 logs 表加 lab_id
# ========================================================================

def step7_add_lab_id_to_logs(engine, dry_run=False):
    """给 logs 表加 lab_id 列（标识日志来源实验室）"""
    print("\n" + "=" * 60)
    print("Step 7: 给 logs 表加 lab_id")
    print("=" * 60)

    if dry_run:
        with engine.connect() as conn:
            if _table_exists(conn, 'logs'):
                has_col = _column_exists(conn, 'logs', 'lab_id')
                print(f"  [DRY-RUN] logs.lab_id 存在: {has_col}")
            else:
                print("  [DRY-RUN] logs 表不存在")
        return

    with engine.begin() as conn:
        if not _table_exists(conn, 'logs'):
            print("  [SKIP] logs 表不存在")
            return

        _exec_ddl(
            conn,
            "ALTER TABLE logs ADD COLUMN lab_id INTEGER",
            "新增列: logs.lab_id",
            "logs.lab_id 已存在",
        )
        _exec_ddl(
            conn,
            "CREATE INDEX IF NOT EXISTS idx_logs_lab_id ON logs(lab_id)",
            "创建索引: idx_logs_lab_id",
            "索引 idx_logs_lab_id 已存在",
        )


# ========================================================================
# Step 8: 给 task_device_relations 表加 lab_id
# ========================================================================

def step8_add_lab_id_to_task_device_relations(engine, dry_run=False):
    """给 task_device_relations 表加 lab_id 列（冗余，便于按实验室查询任务设备）"""
    print("\n" + "=" * 60)
    print("Step 8: 给 task_device_relations 表加 lab_id")
    print("=" * 60)

    if dry_run:
        with engine.connect() as conn:
            if _table_exists(conn, 'task_device_relations'):
                has_col = _column_exists(conn, 'task_device_relations', 'lab_id')
                print(f"  [DRY-RUN] task_device_relations.lab_id 存在: {has_col}")
            else:
                print("  [DRY-RUN] task_device_relations 表不存在")
        return

    with engine.begin() as conn:
        if not _table_exists(conn, 'task_device_relations'):
            print("  [SKIP] task_device_relations 表不存在")
            return

        _exec_ddl(
            conn,
            "ALTER TABLE task_device_relations ADD COLUMN lab_id INTEGER",
            "新增列: task_device_relations.lab_id",
            "task_device_relations.lab_id 已存在",
        )
        _exec_ddl(
            conn,
            "CREATE INDEX IF NOT EXISTS idx_task_device_relations_lab_id ON task_device_relations(lab_id)",
            "创建索引: idx_task_device_relations_lab_id",
            "索引 idx_task_device_relations_lab_id 已存在",
        )


# ========================================================================
# 主流程
# ========================================================================

def main():
    dry_run = '--dry-run' in sys.argv
    step_only = None

    # 解析 --step N 参数
    for i, arg in enumerate(sys.argv):
        if arg == '--step' and i + 1 < len(sys.argv):
            step_only = int(sys.argv[i + 1])

    print("=" * 60)
    print(f"{'[DRY-RUN] ' if dry_run else ''}实验室扩展：新建实验室表 + 给现有表加 lab_id")
    print("=" * 60)
    safe_uri = POSTGRES_URI[:POSTGRES_URI.rindex('@')] + '@localhost/...'
    print(f"数据库: {safe_uri}")
    print()

    engine = create_engine(POSTGRES_URI)

    steps = [
        (1, step1_create_laboratories),
        (2, step2_create_task_laboratory_relations),
        (3, step3_add_lab_id_to_devices),
        (4, step4_add_lab_id_to_playback_devices),
        (5, step5_add_lab_id_to_test_results),
        (6, step6_add_lab_id_to_task_case_relations),
        (7, step7_add_lab_id_to_logs),
        (8, step8_add_lab_id_to_task_device_relations),
    ]

    for step_num, step_func in steps:
        if step_only and step_only != step_num:
            continue
        step_func(engine, dry_run=dry_run)

    print("\n" + "=" * 60)
    print(f"{'[DRY-RUN] ' if dry_run else ''}迁移完成")
    print("=" * 60)
    print("\n迁移汇总：")
    print("  Step 1: 创建 laboratories 实验室主表")
    print("  Step 2: 创建 task_laboratory_relations 任务-实验室关联表")
    print("  Step 3: devices 加 lab_id")
    print("  Step 4: playback_devices 加 lab_id")
    print("  Step 5: test_results 加 lab_id")
    print("  Step 6: task_case_relations 加 lab_id")
    print("  Step 7: logs 加 lab_id")
    print("  Step 8: task_device_relations 加 lab_id")
    print("\n不改动：")
    print("  - test_cases: lab_id 存 config JSONB（为空=通用，有值=专属）")
    print("  - spl_mappings: 不加 lab_id")
    print("  - calibration_history: 通过 mapping_id 间接关联")


if __name__ == '__main__':
    main()
