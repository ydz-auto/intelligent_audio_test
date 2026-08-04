# -*- coding: utf-8 -*-
"""
移除外键约束 + 启用软删除 + RBAC/OAuth 扩展
===================================

目标：
1. 删除数据库中所有外键约束（DROP CONSTRAINT），改由应用层代码自行管理引用完整性
2. 给 test_case_groups / test_cases 表补充软删除字段（deleted / deleted_at）
3. 删除 test_case_groups.name 上的唯一约束（软删除后允许同名重建）
4. 给所有带 deleted 但缺 deleted_at 的表补 deleted_at 列
5. 给业务表补 created_by_user_id / updated_by_user_id 列
6. 创建 RBAC 新表（roles / role_permissions），修改 users 表（加 oauth 字段、role_id），迁移历史角色数据
7. 创建 OAuth 新表（oauth_clients / oauth_refresh_tokens）
8. 删除相关表的 unique 约束（tags.name, tag_categories.name, categories.name）
9. 添加索引：软删除清理（部分索引）+ 外键替代索引（原 FK 列查询索引）

幂等性：脚本可重复执行，已完成的操作会被跳过。

用法:
    python remove_foreign_keys_and_soft_delete.py              # 正式执行
    python remove_foreign_keys_and_soft_delete.py --dry-run    # 仅预览
    python remove_foreign_keys_and_soft_delete.py --step 2     # 仅执行第 2 步

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
# Step 1: 删除所有外键约束
# ========================================================================

def step1_drop_all_foreign_keys(engine, dry_run=False):
    """删除当前数据库中所有外键约束"""
    print("\n" + "=" * 60)
    print("Step 1: 删除所有外键约束")
    print("=" * 60)

    with engine.connect() as conn:
        rows = conn.execute(text(
            """
            SELECT nsp.nspname AS table_schema,
                   cls.relname AS table_name,
                   con.conname AS constraint_name
            FROM pg_constraint con
            JOIN pg_class cls ON cls.oid = con.conrelid
            JOIN pg_namespace nsp ON nsp.oid = cls.relnamespace
            WHERE con.contype = 'f'
            ORDER BY nsp.nspname, cls.relname, con.conname
            """
        )).fetchall()

    total = len(rows)
    print(f"  发现 {total} 个外键约束\n")

    if dry_run:
        for schema, table, constraint in rows:
            print(f"  [DRY-RUN] DROP CONSTRAINT {constraint} on {schema}.{table}")
        return

    dropped = 0
    for schema, table, constraint in rows:
        fqn = f'"{schema}"."{table}"' if schema != 'public' else f'"{table}"'
        with engine.begin() as conn:
            conn.execute(text(
                f'ALTER TABLE {fqn} DROP CONSTRAINT IF EXISTS "{constraint}"'
            ))
        dropped += 1
        print(f"  [OK] DROP CONSTRAINT {constraint} on {schema}.{table}")

    print(f"\n  删除外键约束: {dropped} 个")


# ========================================================================
# Step 2: 给 test_case_groups 补充软删除字段
# ========================================================================

def step2_add_soft_delete_to_groups(engine, dry_run=False):
    """给 test_case_groups 表补充 deleted / deleted_at 列"""
    print("\n" + "=" * 60)
    print("Step 2: 给 test_case_groups 补充软删除字段")
    print("=" * 60)

    if dry_run:
        with engine.connect() as conn:
            exists_t = _table_exists(conn, 'test_case_groups')
            print(f"  [DRY-RUN] test_case_groups 表存在: {exists_t}")
            if exists_t:
                print(f"  [DRY-RUN] deleted 列存在: {_column_exists(conn, 'test_case_groups', 'deleted')}")
                print(f"  [DRY-RUN] deleted_at 列存在: {_column_exists(conn, 'test_case_groups', 'deleted_at')}")
        return

    with engine.begin() as conn:
        if not _table_exists(conn, 'test_case_groups'):
            print("  [SKIP] test_case_groups 表不存在")
            return

        _exec_ddl(
            conn,
            "ALTER TABLE test_case_groups ADD COLUMN deleted BOOLEAN NOT NULL DEFAULT FALSE",
            "新增列: test_case_groups.deleted",
            "deleted 列已存在",
        )
        _exec_ddl(
            conn,
            "ALTER TABLE test_case_groups ADD COLUMN deleted_at TIMESTAMP NULL",
            "新增列: test_case_groups.deleted_at",
            "deleted_at 列已存在",
        )


# ========================================================================
# Step 3: 给 test_cases 补充 deleted_at 列
# ========================================================================

def step3_add_deleted_at_to_cases(engine, dry_run=False):
    """给 test_cases 表补充 deleted_at 列，并补全存量已删数据的时间戳"""
    print("\n" + "=" * 60)
    print("Step 3: 给 test_cases 补充 deleted_at 列")
    print("=" * 60)

    if dry_run:
        with engine.connect() as conn:
            exists_t = _table_exists(conn, 'test_cases')
            print(f"  [DRY-RUN] test_cases 表存在: {exists_t}")
            if exists_t:
                has_col = _column_exists(conn, 'test_cases', 'deleted_at')
                print(f"  [DRY-RUN] deleted_at 列存在: {has_col}")
                if has_col:
                    cnt = conn.execute(text(
                        "SELECT count(*) FROM test_cases WHERE deleted = TRUE AND deleted_at IS NULL"
                    )).scalar()
                    print(f"  [DRY-RUN] 待补全 deleted_at 的已删用例: {cnt} 条")
        return

    with engine.begin() as conn:
        if not _table_exists(conn, 'test_cases'):
            print("  [SKIP] test_cases 表不存在")
            return

        if not _column_exists(conn, 'test_cases', 'deleted_at'):
            conn.execute(text(
                "ALTER TABLE test_cases ADD COLUMN deleted_at TIMESTAMP NULL"
            ))
            print("  [OK] 新增列: test_cases.deleted_at")
        else:
            print("  [SKIP] deleted_at 列已存在")

        # 为已软删除但未设置 deleted_at 的用例补上时间戳（用 updated_at 兜底）
        result = conn.execute(text(
            "UPDATE test_cases SET deleted_at = updated_at "
            "WHERE deleted = TRUE AND deleted_at IS NULL"
        ))
        if result.rowcount > 0:
            print(f"  [OK] 为 {result.rowcount} 条已删用例补全 deleted_at")
        else:
            print("  [SKIP] 无需补全 deleted_at")


# ========================================================================
# Step 4: 同步空分组的软删除标记
# ========================================================================

def step4_mark_empty_groups_deleted(engine, dry_run=False):
    """将不存在活跃用例、且曾被软删除用例引用的分组标记为已删除"""
    print("\n" + "=" * 60)
    print("Step 4: 同步空分组的软删除标记")
    print("=" * 60)

    if dry_run:
        with engine.connect() as conn:
            if not _table_exists(conn, 'test_case_groups'):
                print("  [DRY-RUN] test_case_groups 表不存在，跳过")
                return
            if not _column_exists(conn, 'test_case_groups', 'deleted'):
                print("  [DRY-RUN] test_case_groups.deleted 列不存在，需先执行 Step 2")
                return
            cnt = conn.execute(text(
                """
                SELECT count(*) FROM test_case_groups g
                WHERE g.deleted = FALSE
                  AND NOT EXISTS (
                      SELECT 1 FROM test_cases tc
                      WHERE tc.group_id = g.id AND tc.deleted = FALSE
                  )
                  AND EXISTS (
                      SELECT 1 FROM test_cases tc
                      WHERE tc.group_id = g.id AND tc.deleted = TRUE
                  )
                """
            )).scalar()
            print(f"  [DRY-RUN] 待标记软删除的空分组: {cnt} 个")
        return

    with engine.begin() as conn:
        if not _table_exists(conn, 'test_case_groups'):
            print("  [SKIP] test_case_groups 表不存在")
            return

        result = conn.execute(text(
            """
            UPDATE test_case_groups g
            SET deleted = TRUE, deleted_at = NOW()
            WHERE g.deleted = FALSE
              AND NOT EXISTS (
                  SELECT 1 FROM test_cases tc
                  WHERE tc.group_id = g.id AND tc.deleted = FALSE
              )
              AND EXISTS (
                  SELECT 1 FROM test_cases tc
                  WHERE tc.group_id = g.id AND tc.deleted = TRUE
              )
            """
        ))
        if result.rowcount > 0:
            print(f"  [OK] 标记 {result.rowcount} 个空分组为软删除")
        else:
            print("  [SKIP] 无空分组需标记")


# ========================================================================
# Step 5: 删除 test_case_groups.name 上的唯一约束
# ========================================================================

def step5_drop_unique_on_group_name(engine, dry_run=False):
    """删除 test_case_groups.name 上的唯一约束（软删除后允许同名重建）"""
    print("\n" + "=" * 60)
    print("Step 5: 删除 test_case_groups.name 上的唯一约束")
    print("=" * 60)

    with engine.connect() as conn:
        if not _table_exists(conn, 'test_case_groups'):
            print("  [SKIP] test_case_groups 表不存在")
            return

        rows = conn.execute(text(
            """
            SELECT con.conname
            FROM pg_constraint con
            JOIN pg_class cls ON cls.oid = con.conrelid
            JOIN pg_namespace nsp ON nsp.oid = cls.relnamespace
            JOIN pg_attribute att ON att.attrelid = con.conrelid
            WHERE con.contype = 'u'
              AND cls.relname = 'test_case_groups'
              AND att.attname = 'name'
              AND array_length(con.conkey, 1) = 1
              AND att.attnum = con.conkey[1]
            """
        )).fetchall()

    uq_names = [r[0] for r in rows]
    if not uq_names:
        print("  [SKIP] test_case_groups.name 上无唯一约束")
        return

    if dry_run:
        for name in uq_names:
            print(f"  [DRY-RUN] DROP CONSTRAINT {name}")
        return

    with engine.begin() as conn:
        for name in uq_names:
            conn.execute(text(
                f'ALTER TABLE test_case_groups DROP CONSTRAINT IF EXISTS "{name}"'
            ))
            print(f"  [OK] DROP CONSTRAINT {name}")


# ========================================================================
# Step 6: 补 deleted_at 列（所有带 deleted 但缺 deleted_at 的表）
# ========================================================================

# 已有 deleted 列但可能缺 deleted_at 的表
DELETED_AT_TABLES = [
    'test_cases',
    'test_case_groups',
    'devices',
    'audios',
    'audio_annotations',
    'audio_algorithm_relations',
    'apis',
    'test_tasks',
    'dimensions',
    'test_reports',
    'spl_mappings',
    'tags',
    'tag_categories',
    'categories',
]


def step6_add_deleted_at_to_all_tables(engine, dry_run=False):
    """给所有带 deleted 但缺 deleted_at 的表补 deleted_at 列"""
    print("\n" + "=" * 60)
    print("Step 6: 补 deleted_at 列（所有软删除表）")
    print("=" * 60)

    if dry_run:
        with engine.connect() as conn:
            for table in DELETED_AT_TABLES:
                if not _table_exists(conn, table):
                    print(f"  [DRY-RUN] {table}: 表不存在")
                    continue
                has_deleted = _column_exists(conn, table, 'deleted')
                has_deleted_at = _column_exists(conn, table, 'deleted_at')
                print(f"  [DRY-RUN] {table}: deleted={has_deleted}, deleted_at={has_deleted_at}")
        return

    added = 0
    skipped = 0
    with engine.begin() as conn:
        for table in DELETED_AT_TABLES:
            if not _table_exists(conn, table):
                print(f"  [SKIP] 表 {table} 不存在")
                skipped += 1
                continue
            if not _column_exists(conn, table, 'deleted'):
                print(f"  [SKIP] {table} 无 deleted 列，跳过 deleted_at")
                skipped += 1
                continue
            if _column_exists(conn, table, 'deleted_at'):
                print(f"  [SKIP] {table}.deleted_at 已存在")
                skipped += 1
                continue
            conn.execute(text(
                f"ALTER TABLE {table} ADD COLUMN deleted_at TIMESTAMP NULL"
            ))
            print(f"  [OK] 新增列: {table}.deleted_at")
            added += 1
        print(f"\n  新增 deleted_at: {added}, 跳过: {skipped}")


# ========================================================================
# Step 7: 给业务表补 created_by_user_id / updated_by_user_id 列
# ========================================================================

# 需要补 user_id 字段的业务表
USER_ID_TABLES = [
    'test_case_groups',
    'test_cases',
    'devices',
    'playback_devices',
    'audios',
    'audio_annotations',
    'audio_algorithm_relations',
    'apis',
    'test_tasks',
    'test_results',
    'test_result_dimensions',
    'test_reports',
    'report_summaries',
    'report_summary_meta',
    'report_raw_data',
    'report_cases',
    'report_metric_stats',
    'report_comparison_matrix',
    'categories',
    'dimensions',
    'logs',
    'spl_mappings',
    'calibration_history',
    'upload_tasks',
    'upload_files',
    'upload_chunks',
    'stats_cache',
]


def step7_add_user_id_columns(engine, dry_run=False):
    """给业务表补 created_by_user_id / updated_by_user_id 列"""
    print("\n" + "=" * 60)
    print("Step 7: 给业务表补 created_by_user_id / updated_by_user_id 列")
    print("=" * 60)

    if dry_run:
        with engine.connect() as conn:
            for table in USER_ID_TABLES:
                if not _table_exists(conn, table):
                    print(f"  [DRY-RUN] {table}: 表不存在")
                    continue
                has_created = _column_exists(conn, table, 'created_by_user_id')
                has_updated = _column_exists(conn, table, 'updated_by_user_id')
                print(f"  [DRY-RUN] {table}: created_by_user_id={has_created}, updated_by_user_id={has_updated}")
        return

    added = 0
    skipped = 0
    with engine.begin() as conn:
        for table in USER_ID_TABLES:
            if not _table_exists(conn, table):
                print(f"  [SKIP] 表 {table} 不存在")
                skipped += 1
                continue

            if not _column_exists(conn, table, 'created_by_user_id'):
                conn.execute(text(
                    f"ALTER TABLE {table} ADD COLUMN created_by_user_id BIGINT NULL"
                ))
                print(f"  [OK] 新增列: {table}.created_by_user_id")
                added += 1
            else:
                print(f"  [SKIP] {table}.created_by_user_id 已存在")

            if not _column_exists(conn, table, 'updated_by_user_id'):
                conn.execute(text(
                    f"ALTER TABLE {table} ADD COLUMN updated_by_user_id BIGINT NULL"
                ))
                print(f"  [OK] 新增列: {table}.updated_by_user_id")
                added += 1
            else:
                print(f"  [SKIP] {table}.updated_by_user_id 已存在")
        print(f"\n  新增 user_id 列: {added}, 跳过: {skipped}")


# ========================================================================
# Step 8: 创建 RBAC 表 + 修改 users 表
# ========================================================================

def step8_create_rbac_tables(engine, dry_run=False):
    """创建 RBAC 新表（roles / role_permissions），修改 users 表（加 oauth 字段、role_id），迁移历史角色数据"""
    print("\n" + "=" * 60)
    print("Step 8: 创建 RBAC 表 + 修改 users 表")
    print("=" * 60)

    if dry_run:
        with engine.connect() as conn:
            print(f"  [DRY-RUN] roles 表存在: {_table_exists(conn, 'roles')}")
            print(f"  [DRY-RUN] role_permissions 表存在: {_table_exists(conn, 'role_permissions')}")
            print(f"  [DRY-RUN] users 表存在: {_table_exists(conn, 'users')}")
            if _table_exists(conn, 'users'):
                for col in ['role_id', 'oauth_provider', 'oauth_id', 'oauth_unionid',
                            'oauth_nickname', 'oauth_avatar_url', 'last_login_at', 'last_login_ip']:
                    print(f"  [DRY-RUN] users.{col}: {_column_exists(conn, 'users', col)}")
            print(f"  [DRY-RUN] user_permissions 表存在: {_table_exists(conn, 'user_permissions')}")
            if _table_exists(conn, 'user_permissions'):
                print(f"  [DRY-RUN] user_permissions.granted: {_column_exists(conn, 'user_permissions', 'granted')}")
        return

    with engine.begin() as conn:
        # --- 创建 roles 表 ---
        _exec_ddl(
            conn,
            """
            CREATE TABLE IF NOT EXISTS roles (
                id SERIAL PRIMARY KEY,
                name VARCHAR(50) UNIQUE NOT NULL,
                description TEXT,
                is_system BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """,
            "创建表: roles",
            "roles 表已存在",
        )

        # --- 创建 role_permissions 关联表 ---
        _exec_ddl(
            conn,
            """
            CREATE TABLE IF NOT EXISTS role_permissions (
                id BIGSERIAL PRIMARY KEY,
                role_id INTEGER NOT NULL,
                permission_id INTEGER NOT NULL
            )
            """,
            "创建表: role_permissions",
            "role_permissions 表已存在",
        )
        _exec_ddl(
            conn,
            "CREATE INDEX IF NOT EXISTS idx_role_permissions_role_id ON role_permissions(role_id)",
            "创建索引: idx_role_permissions_role_id",
            "索引 idx_role_permissions_role_id 已存在",
        )
        _exec_ddl(
            conn,
            "CREATE INDEX IF NOT EXISTS idx_role_permissions_permission_id ON role_permissions(permission_id)",
            "创建索引: idx_role_permissions_permission_id",
            "索引 idx_role_permissions_permission_id 已存在",
        )

        # --- 修改 users 表（加列）---
        if _table_exists(conn, 'users'):
            _exec_ddl(
                conn,
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS role_id INTEGER",
                "新增列: users.role_id",
                "users.role_id 已存在",
            )
            _exec_ddl(
                conn,
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS oauth_provider VARCHAR(50)",
                "新增列: users.oauth_provider",
                "users.oauth_provider 已存在",
            )
            _exec_ddl(
                conn,
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS oauth_id VARCHAR(255)",
                "新增列: users.oauth_id",
                "users.oauth_id 已存在",
            )
            _exec_ddl(
                conn,
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS oauth_unionid VARCHAR(255)",
                "新增列: users.oauth_unionid",
                "users.oauth_unionid 已存在",
            )
            _exec_ddl(
                conn,
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS oauth_nickname VARCHAR(100)",
                "新增列: users.oauth_nickname",
                "users.oauth_nickname 已存在",
            )
            _exec_ddl(
                conn,
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS oauth_avatar_url VARCHAR(500)",
                "新增列: users.oauth_avatar_url",
                "users.oauth_avatar_url 已存在",
            )
            _exec_ddl(
                conn,
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMP",
                "新增列: users.last_login_at",
                "users.last_login_at 已存在",
            )
            _exec_ddl(
                conn,
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_ip VARCHAR(50)",
                "新增列: users.last_login_ip",
                "users.last_login_ip 已存在",
            )

            # 索引
            _exec_ddl(
                conn,
                "CREATE INDEX IF NOT EXISTS idx_users_role_id ON users(role_id)",
                "创建索引: idx_users_role_id",
                "索引 idx_users_role_id 已存在",
            )
            _exec_ddl(
                conn,
                "CREATE INDEX IF NOT EXISTS idx_users_oauth_id ON users(oauth_id)",
                "创建索引: idx_users_oauth_id",
                "索引 idx_users_oauth_id 已存在",
            )
        else:
            print("  [SKIP] users 表不存在，跳过列添加")

        # --- user_permissions 表加 granted 列 ---
        if _table_exists(conn, 'user_permissions'):
            _exec_ddl(
                conn,
                "ALTER TABLE user_permissions ADD COLUMN IF NOT EXISTS granted BOOLEAN NOT NULL DEFAULT TRUE",
                "新增列: user_permissions.granted",
                "user_permissions.granted 已存在",
            )
        else:
            print("  [SKIP] user_permissions 表不存在，跳过 granted 列")

        # --- 数据迁移：把 users.role (字符串) 迁移到 roles 表 + users.role_id ---
        # 注意：users.role 列保留（向后兼容），新代码用 role_id
        if _table_exists(conn, 'users') and _column_exists(conn, 'users', 'role'):
            print("  [INFO] 开始迁移 users.role -> roles 表 + users.role_id")

            # 1. 插入 distinct role 值到 roles 表（ON CONFLICT 保证幂等）
            inserted = conn.execute(text(
                """
                INSERT INTO roles (name, description, is_system)
                SELECT DISTINCT role, '历史角色 (自动迁移)', FALSE
                FROM users
                WHERE role IS NOT NULL AND role <> ''
                ON CONFLICT (name) DO NOTHING
                """
            ))
            print(f"  [OK] 插入/跳过 {inserted.rowcount} 个角色到 roles 表")

            # 2. 更新 users.role_id
            updated = conn.execute(text(
                """
                UPDATE users
                SET role_id = (SELECT id FROM roles WHERE roles.name = users.role)
                WHERE role IS NOT NULL AND role <> '' AND role_id IS NULL
                """
            ))
            print(f"  [OK] 更新 {updated.rowcount} 个用户的 role_id")
        else:
            print("  [SKIP] users.role 列不存在，无需数据迁移")


# ========================================================================
# Step 9: 创建 OAuth 表
# ========================================================================

def step9_create_oauth_tables(engine, dry_run=False):
    """创建 OAuth 新表（oauth_clients / oauth_refresh_tokens）"""
    print("\n" + "=" * 60)
    print("Step 9: 创建 OAuth 表")
    print("=" * 60)

    if dry_run:
        with engine.connect() as conn:
            print(f"  [DRY-RUN] oauth_clients 表存在: {_table_exists(conn, 'oauth_clients')}")
            print(f"  [DRY-RUN] oauth_refresh_tokens 表存在: {_table_exists(conn, 'oauth_refresh_tokens')}")
        return

    with engine.begin() as conn:
        # --- 创建 oauth_clients 表 ---
        _exec_ddl(
            conn,
            """
            CREATE TABLE IF NOT EXISTS oauth_clients (
                id SERIAL PRIMARY KEY,
                client_id VARCHAR(64) UNIQUE NOT NULL,
                client_secret VARCHAR(255) NOT NULL,
                name VARCHAR(100) NOT NULL,
                description TEXT,
                redirect_uris JSON NOT NULL DEFAULT '[]',
                grant_types JSON NOT NULL DEFAULT '[]',
                scopes JSON NOT NULL DEFAULT '[]',
                is_confidential BOOLEAN NOT NULL DEFAULT TRUE,
                status VARCHAR(20) NOT NULL DEFAULT 'active',
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """,
            "创建表: oauth_clients",
            "oauth_clients 表已存在",
        )

        # --- 创建 oauth_refresh_tokens 表 ---
        _exec_ddl(
            conn,
            """
            CREATE TABLE IF NOT EXISTS oauth_refresh_tokens (
                id BIGSERIAL PRIMARY KEY,
                token VARCHAR(512) UNIQUE NOT NULL,
                client_id VARCHAR(64) NOT NULL,
                user_id BIGINT,
                scope TEXT,
                expires_at TIMESTAMP NOT NULL,
                revoked BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """,
            "创建表: oauth_refresh_tokens",
            "oauth_refresh_tokens 表已存在",
        )
        _exec_ddl(
            conn,
            "CREATE INDEX IF NOT EXISTS idx_oauth_refresh_tokens_token ON oauth_refresh_tokens(token)",
            "创建索引: idx_oauth_refresh_tokens_token",
            "索引 idx_oauth_refresh_tokens_token 已存在",
        )
        _exec_ddl(
            conn,
            "CREATE INDEX IF NOT EXISTS idx_oauth_refresh_tokens_client_id ON oauth_refresh_tokens(client_id)",
            "创建索引: idx_oauth_refresh_tokens_client_id",
            "索引 idx_oauth_refresh_tokens_client_id 已存在",
        )
        _exec_ddl(
            conn,
            "CREATE INDEX IF NOT EXISTS idx_oauth_refresh_tokens_user_id ON oauth_refresh_tokens(user_id)",
            "创建索引: idx_oauth_refresh_tokens_user_id",
            "索引 idx_oauth_refresh_tokens_user_id 已存在",
        )


# ========================================================================
# Step 10: 删除相关表的 unique 约束（tags/tag_categories/categories.name）
# ========================================================================

# 需要删除 name 唯一约束的表
UNIQUE_NAME_TABLES = ['tags', 'tag_categories', 'categories']


def step10_drop_unique_on_names(engine, dry_run=False):
    """删除 tags.name / tag_categories.name / categories.name 上的唯一约束"""
    print("\n" + "=" * 60)
    print("Step 10: 删除 tags/tag_categories/categories.name 上的唯一约束")
    print("=" * 60)

    if dry_run:
        with engine.connect() as conn:
            for table in UNIQUE_NAME_TABLES:
                if not _table_exists(conn, table):
                    print(f"  [DRY-RUN] {table}: 表不存在")
                    continue
                rows = conn.execute(text(
                    """
                    SELECT con.conname
                    FROM pg_constraint con
                    JOIN pg_class cls ON cls.oid = con.conrelid
                    JOIN pg_attribute att ON att.attrelid = con.conrelid
                    WHERE con.contype = 'u'
                      AND cls.relname = :table
                      AND att.attname = 'name'
                      AND array_length(con.conkey, 1) = 1
                      AND att.attnum = con.conkey[1]
                    """
                ), {"table": table}).fetchall()
                names = [r[0] for r in rows]
                if names:
                    print(f"  [DRY-RUN] {table}: 发现唯一约束 {names}")
                else:
                    print(f"  [DRY-RUN] {table}: 无 name 唯一约束")
        return

    with engine.begin() as conn:
        for table in UNIQUE_NAME_TABLES:
            if not _table_exists(conn, table):
                print(f"  [SKIP] 表 {table} 不存在")
                continue

            # 查询 name 列上的单列唯一约束
            rows = conn.execute(text(
                """
                SELECT con.conname
                FROM pg_constraint con
                JOIN pg_class cls ON cls.oid = con.conrelid
                JOIN pg_attribute att ON att.attrelid = con.conrelid
                WHERE con.contype = 'u'
                  AND cls.relname = :table
                  AND att.attname = 'name'
                  AND array_length(con.conkey, 1) = 1
                  AND att.attnum = con.conkey[1]
                """
            ), {"table": table}).fetchall()

            constraint_names = [r[0] for r in rows]
            if not constraint_names:
                print(f"  [SKIP] {table}.name 上无唯一约束")
                continue

            for cname in constraint_names:
                conn.execute(text(
                    f'ALTER TABLE {table} DROP CONSTRAINT IF EXISTS "{cname}"'
                ))
                print(f"  [OK] DROP CONSTRAINT {cname} on {table}")

            # 同时尝试删除 PostgreSQL 自动生成的默认约束名 <table>_name_key
            _exec_ddl(
                conn,
                f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {table}_name_key",
                f"DROP CONSTRAINT {table}_name_key",
                f"{table}_name_key 约束不存在",
            )


# ========================================================================
# Step 11: 添加索引（软删除 + 外键替代）
# ========================================================================

# 索引定义：(索引名, 表名, 列SQL, 是否部分索引, WHERE子句)
# 移除外键后，原 FK 列上的隐式索引消失，需显式建索引以维持 JOIN/WHERE 性能。
INDEX_DEFINITIONS = [
    # ── 软删除清理索引（部分索引）──
    ('idx_tc_groups_deleted_at', 'test_case_groups', 'deleted_at', True, "WHERE deleted = TRUE"),
    ('idx_test_cases_deleted_at', 'test_cases', 'deleted_at', True, "WHERE deleted = TRUE"),

    # ── test_case_groups ──
    ('idx_tc_groups_algorithm_type', 'test_case_groups', 'algorithm_type', False, None),

    # ── test_cases ──
    ('idx_test_cases_group_id', 'test_cases', 'group_id', False, None),
    ('idx_test_cases_algorithm_type', 'test_cases', 'algorithm_type', False, None),
    ('idx_test_cases_deleted', 'test_cases', 'deleted', False, None),

    # ── test_case_tags ──
    ('idx_test_case_tags_test_case_id', 'test_case_tags', 'test_case_id', False, None),
    ('idx_test_case_tags_tag_id', 'test_case_tags', 'tag_id', False, None),

    # ── tags ──
    ('idx_tags_category_id', 'tags', 'category_id', False, None),

    # ── dimensions ──
    ('idx_dimensions_category_id', 'dimensions', 'category_id', False, None),
    ('idx_dimensions_parent_dimension_id', 'dimensions', 'parent_dimension_id', False, None),

    # ── audio_annotations ──
    ('idx_audio_annotations_audio_id', 'audio_annotations', 'audio_id', False, None),

    # ── audio_tags ──
    ('idx_audio_tags_audio_id', 'audio_tags', 'audio_id', False, None),
    ('idx_audio_tags_tag_id', 'audio_tags', 'tag_id', False, None),

    # ── audio_algorithm_relations ──
    ('idx_audio_algo_rel_audio_id', 'audio_algorithm_relations', 'audio_id', False, None),
    ('idx_audio_algo_rel_algorithm_type', 'audio_algorithm_relations', 'algorithm_type', False, None),

    # ── device_tags ──
    ('idx_device_tags_device_id', 'device_tags', 'device_id', False, None),
    ('idx_device_tags_tag_id', 'device_tags', 'tag_id', False, None),

    # ── playback_devices ──
    ('idx_playback_devices_current_spl_mapping_id', 'playback_devices', 'current_spl_mapping_id', False, None),

    # ── spl_mappings ──
    ('idx_spl_mappings_device_id', 'spl_mappings', 'device_id', False, None),

    # ── calibration_history ──
    ('idx_calibration_history_mapping_id', 'calibration_history', 'mapping_id', False, None),

    # ── task_tags ──
    ('idx_task_tags_task_id', 'task_tags', 'task_id', False, None),
    ('idx_task_tags_tag_id', 'task_tags', 'tag_id', False, None),

    # ── task_case_relations ──
    ('idx_task_case_relations_task_id', 'task_case_relations', 'task_id', False, None),
    ('idx_task_case_relations_test_case_id', 'task_case_relations', 'test_case_id', False, None),

    # ── task_device_relations ──
    ('idx_task_device_relations_task_id', 'task_device_relations', 'task_id', False, None),
    ('idx_task_device_relations_device_id', 'task_device_relations', 'device_id', False, None),

    # ── task_api_relations ──
    ('idx_task_api_relations_task_id', 'task_api_relations', 'task_id', False, None),
    ('idx_task_api_relations_api_id', 'task_api_relations', 'api_id', False, None),

    # ── task_merge_relations ──
    ('idx_task_merge_relations_merged_task_id', 'task_merge_relations', 'merged_task_id', False, None),
    ('idx_task_merge_relations_source_task_id', 'task_merge_relations', 'source_task_id', False, None),

    # ── test_results ──
    ('idx_test_results_task_id', 'test_results', 'task_id', False, None),
    ('idx_test_results_test_case_id', 'test_results', 'test_case_id', False, None),
    ('idx_test_results_device_id', 'test_results', 'device_id', False, None),
    ('idx_test_results_api_id', 'test_results', 'api_id', False, None),
    ('idx_test_results_algorithm_type', 'test_results', 'algorithm_type', False, None),

    # ── test_result_dimensions ──
    ('idx_test_result_dimensions_test_result_id', 'test_result_dimensions', 'test_result_id', False, None),
    ('idx_test_result_dimensions_dimension_id', 'test_result_dimensions', 'dimension_id', False, None),

    # ── test_reports ──
    ('idx_test_reports_task_id', 'test_reports', 'task_id', False, None),

    # ── report_cases ──
    ('idx_report_cases_report_id', 'report_cases', 'report_id', False, None),
    ('idx_report_cases_test_case_id', 'report_cases', 'test_case_id', False, None),

    # ── logs ──
    ('idx_logs_task_id', 'logs', 'task_id', False, None),
    ('idx_logs_test_case_id', 'logs', 'test_case_id', False, None),
    ('idx_logs_device_id', 'logs', 'device_id', False, None),
    ('idx_logs_api_id', 'logs', 'api_id', False, None),

    # ── user_permissions ──
    ('idx_user_permissions_user_id', 'user_permissions', 'user_id', False, None),
    ('idx_user_permissions_permission_id', 'user_permissions', 'permission_id', False, None),

    # ── upload_files / upload_chunks ──
    ('idx_upload_files_task_id', 'upload_files', 'task_id', False, None),
    ('idx_upload_chunks_file_id', 'upload_chunks', 'file_id', False, None),

    # ── case_algorithm_params ──
    ('idx_case_algorithm_params_algorithm_type', 'case_algorithm_params', 'algorithm_type', False, None),

    # ── algorithm_models 相关（algorithm_definitions 等）──
    ('idx_algorithm_definitions_group_id', 'algorithm_definitions', 'group_id', False, None),
    ('idx_algorithm_device_params_algorithm_type', 'algorithm_device_params', 'algorithm_type', False, None),
    ('idx_algorithm_api_params_algorithm_type', 'algorithm_api_params', 'algorithm_type', False, None),
    ('idx_algorithm_reference_params_algorithm_type', 'algorithm_reference_params', 'algorithm_type', False, None),
    ('idx_evaluation_dimension_params_dimension_id', 'evaluation_dimension_params', 'dimension_id', False, None),
    ('idx_param_mappings_algorithm_type', 'param_mappings', 'algorithm_type', False, None),
    ('idx_param_mappings_dimension_id', 'param_mappings', 'dimension_id', False, None),
    ('idx_algorithm_dimension_relations_algorithm_type', 'algorithm_dimension_relations', 'algorithm_type', False, None),
    ('idx_algorithm_dimension_relations_dimension_id', 'algorithm_dimension_relations', 'dimension_id', False, None),
]


def step11_add_soft_delete_indexes(engine, dry_run=False):
    """添加索引：软删除清理 + 外键替代（原 FK 列的查询索引）"""
    print("\n" + "=" * 60)
    print("Step 11: 添加索引（软删除 + 外键替代）")
    print("=" * 60)

    if dry_run:
        with engine.connect() as conn:
            existing_tables = set()
            for idx_name, table, cols, is_partial, where in INDEX_DEFINITIONS:
                if table not in existing_tables:
                    exists = _table_exists(conn, table)
                    existing_tables.add(table)
                idx_exists = _index_exists(conn, idx_name)
                status = '已存在' if idx_exists else ('表缺失' if not exists else '待创建')
                print(f"  [DRY-RUN] {idx_name} on {table}({cols}): {status}")
        return

    with engine.begin() as conn:
        created = 0
        skipped = 0
        for idx_name, table, cols, is_partial, where in INDEX_DEFINITIONS:
            if not _table_exists(conn, table):
                print(f"  [SKIP] 表 {table} 不存在，跳过 {idx_name}")
                skipped += 1
                continue
            if _index_exists(conn, idx_name):
                print(f"  [SKIP] 索引 {idx_name} 已存在")
                skipped += 1
                continue
            sql = f"CREATE INDEX {idx_name} ON {table} ({cols})"
            if is_partial and where:
                sql += f" {where}"
            conn.execute(text(sql))
            print(f"  [OK] 创建索引: {idx_name}")
            created += 1
        print(f"\n  创建: {created}, 跳过: {skipped}")


# ========================================================================
# Step 12: 给所有 deleted_at 列建部分索引（WHERE deleted = TRUE）
# ========================================================================

def step12_add_deleted_at_partial_indexes(engine, dry_run=False):
    """给所有 deleted_at 列建部分索引（WHERE deleted = TRUE），加速 60 天清理任务"""
    print("\n" + "=" * 60)
    print("Step 12: 给所有 deleted_at 列建部分索引")
    print("=" * 60)

    if dry_run:
        with engine.connect() as conn:
            for table in DELETED_AT_TABLES:
                if not _table_exists(conn, table):
                    print(f"  [DRY-RUN] {table}: 表不存在")
                    continue
                if not _column_exists(conn, table, 'deleted_at'):
                    print(f"  [DRY-RUN] {table}: deleted_at 列不存在")
                    continue
                idx_name = f"idx_{table}_deleted_at"
                idx_exists = _index_exists(conn, idx_name)
                print(f"  [DRY-RUN] {idx_name}: {'已存在' if idx_exists else '待创建'}")
        return

    created = 0
    skipped = 0
    with engine.begin() as conn:
        for table in DELETED_AT_TABLES:
            if not _table_exists(conn, table):
                print(f"  [SKIP] 表 {table} 不存在")
                skipped += 1
                continue
            if not _column_exists(conn, table, 'deleted_at'):
                print(f"  [SKIP] {table} 无 deleted_at 列")
                skipped += 1
                continue
            idx_name = f"idx_{table}_deleted_at"
            if _index_exists(conn, idx_name):
                print(f"  [SKIP] 索引 {idx_name} 已存在")
                skipped += 1
                continue
            # 部分索引：仅对已软删除的行建索引，加速 60 天清理任务
            # 注意：test_case_groups 已有 idx_tc_groups_deleted_at（旧索引名），此处跳过重复创建
            if table == 'test_case_groups' and _index_exists(conn, 'idx_tc_groups_deleted_at'):
                print(f"  [SKIP] {table} 已有 idx_tc_groups_deleted_at 索引")
                skipped += 1
                continue
            if table == 'test_cases' and _index_exists(conn, 'idx_test_cases_deleted_at'):
                print(f"  [SKIP] {table} 已有 idx_test_cases_deleted_at 索引")
                skipped += 1
                continue
            sql = f"CREATE INDEX {idx_name} ON {table} (deleted_at) WHERE deleted = TRUE"
            conn.execute(text(sql))
            print(f"  [OK] 创建索引: {idx_name}")
            created += 1
        print(f"\n  创建: {created}, 跳过: {skipped}")


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
    print(f"{'[DRY-RUN] ' if dry_run else ''}移除外键约束 + 启用软删除 + RBAC/OAuth 扩展")
    print("=" * 60)
    safe_uri = POSTGRES_URI[:POSTGRES_URI.rindex('@')] + '@localhost/...'
    print(f"数据库: {safe_uri}")
    print()

    engine = create_engine(POSTGRES_URI)

    steps = [
        (1, step1_drop_all_foreign_keys),
        (2, step2_add_soft_delete_to_groups),
        (3, step3_add_deleted_at_to_cases),
        (4, step4_mark_empty_groups_deleted),
        (5, step5_drop_unique_on_group_name),
        (6, step6_add_deleted_at_to_all_tables),
        (7, step7_add_user_id_columns),
        (8, step8_create_rbac_tables),
        (9, step9_create_oauth_tables),
        (10, step10_drop_unique_on_names),
        (11, step11_add_soft_delete_indexes),
        (12, step12_add_deleted_at_partial_indexes),
    ]

    for step_num, step_func in steps:
        if step_only and step_only != step_num:
            continue
        step_func(engine, dry_run=dry_run)

    print("\n" + "=" * 60)
    print(f"{'[DRY-RUN] ' if dry_run else ''}迁移完成")
    print("=" * 60)
    print("\n迁移汇总：")
    print("  Step 1:  删除所有外键约束")
    print("  Step 2:  test_case_groups 补 deleted/deleted_at")
    print("  Step 3:  test_cases 补 deleted_at + 补全存量数据")
    print("  Step 4:  同步空分组的软删除标记")
    print("  Step 5:  删除 test_case_groups.name 唯一约束")
    print("  Step 6:  补 deleted_at 列（所有软删除表）")
    print("  Step 7:  补 created_by_user_id / updated_by_user_id 列")
    print("  Step 8:  创建 RBAC 表 + 修改 users 表 + 迁移角色数据")
    print("  Step 9:  创建 OAuth 表")
    print("  Step 10: 删除 tags/tag_categories/categories.name 唯一约束")
    print("  Step 11: 添加索引（软删除 + 外键替代）")
    print("  Step 12: 给所有 deleted_at 列建部分索引")


if __name__ == '__main__':
    main()
