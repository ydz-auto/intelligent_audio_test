# -*- coding: utf-8 -*-
"""INT-423 数据可见性基座实方言验收：迁移脚本 + seed_rbac 在真实 PostgreSQL 上复核。

tests/unit/test_int423_visibility_base.py 已验证 shared 层语义（Visibility 枚举 /
visibility_filter 三助手 / AuditEvent）；本文件按 INT-337/INT-364 验收同款方式
（真实 Postgres 临时库，用后即删）复核数据面落地：

- add_visibility_columns_int423.py 对既有库（10 表已建、无 visibility 列）首次
  执行全量 DDL、二次执行全 [SKIP]（幂等，重跑不报错）；
- 10 表 visibility 列 NOT NULL DEFAULT 'shared'，存量行自动回填 shared（零回归）；
  published_tasks 补 created_by_user_id（存量置 NULL，不回填）；
  各表 visibility 单列索引 + 高频 5 表 (created_by_user_id, visibility) 复合索引齐备；
- seed_rbac.py 幂等重跑授予 7 个 share 权限点：tester 全给、
  algo_engineer 给 report:share/evaluation:share、admin 通配 '*' 自动覆盖。

DB：本文件模块级夹具整库创建 → 真实 PO 建表 → 用后即删（测试数据不落库外）。
"""
import os
import subprocess
import sys
import uuid

import psycopg2
import pytest
from sqlalchemy import create_engine

from tests.integration.test_task_execute_real_chain import (
    _pg_reachable,
    storage_env,  # noqa: F401  pg_db 依赖（单独运行本文件时需显式注册）
)

PG_HOST = os.environ.get('INT35_PG_HOST', '127.0.0.1')
PG_PORT = int(os.environ.get('INT35_PG_PORT', '5432'))
PG_USER = os.environ.get('INT35_PG_USER', 'intelligent_audio_test')
PG_PASSWORD = os.environ.get('INT35_PG_PASSWORD', 'intelligent_audio_test666')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
_MIGRATION = os.path.join(
    PROJECT_ROOT, 'scripts', 'migrations', '202610',
    'add_visibility_columns_int423.py')
_SEED_RBAC = os.path.join(
    PROJECT_ROOT, 'scripts', 'migrations', '202608', 'seed_rbac.py')

VISIBILITY_TABLES = (
    'test_tasks', 'test_cases', 'test_case_groups', 'tags', 'tag_categories',
    'published_tasks', 'audios', 'test_reports', 'dimensions', 'categories',
)
SHARE_CODES = [
    'task:share', 'testcase:share', 'group:share', 'tag:share',
    'audio:share', 'report:share', 'evaluation:share',
]


@pytest.fixture(scope='module')
def int423_pg_db(storage_env):
    """真实 Postgres 临时库：整库创建 → 全模型建表 → 用后即删。"""
    if not _pg_reachable():
        pytest.skip(f'本机 Postgres {PG_HOST}:{PG_PORT} 不可用，INT-423 实方言验收跳过')

    dbname = f'int423_{uuid.uuid4().hex[:10]}'
    admin = psycopg2.connect(
        host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASSWORD,
        dbname='postgres', connect_timeout=5)
    admin.autocommit = True
    cur = admin.cursor()
    cur.execute(f'CREATE DATABASE {dbname} ENCODING utf8')
    cur.close()

    # 注册全部 PO：10 张资源表 + auth 三表（permissions/roles/role_permissions）
    import shared.models.database as database
    import task_service.infrastructure.persistence.models  # noqa: F401
    import evaluation_service.infrastructure.persistence.models  # noqa: F401
    import audio_service.infrastructure.persistence.models  # noqa: F401
    import report_service.infrastructure.persistence.models  # noqa: F401
    import auth_service.infrastructure.persistence.models  # noqa: F401

    uri = f'postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{dbname}'
    engine = create_engine(uri, pool_pre_ping=True)
    database.Base.metadata.create_all(engine)
    engine.dispose()

    yield uri

    admin = psycopg2.connect(
        host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASSWORD,
        dbname='postgres', connect_timeout=5)
    admin.autocommit = True
    cur = admin.cursor()
    cur.execute(f'DROP DATABASE IF EXISTS {dbname} WITH (FORCE)')
    cur.close()
    admin.close()


def _run_script(script, env_extra):
    """以真实 CLI 方式运行迁移/种子脚本（独立进程，环境变量注入连接串）。"""
    env = dict(os.environ)
    env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, script], env=env, cwd=PROJECT_ROOT,
        capture_output=True, text=True)
    return proc


def _run_migration(uri):
    return _run_script(_MIGRATION, {'DATABASE_URL': uri})


def _run_seed_rbac(uri):
    return _run_script(_SEED_RBAC, {'DATABASE_URI': uri})


class TestVisibilityMigrationRealPG:
    """验收③：迁移脚本对已有库首次执行全量 DDL、二次执行幂等；列/索引落地正确。

    方法定义顺序即执行顺序：先验存量行回填（本用例完成首次迁移），
    再验二次幂等（无任何 [EXEC]，全 [SKIP]）。
    """

    def test_backfill_existing_rows_and_first_migration(self, int423_pg_db):
        uri = int423_pg_db

        # 迁移前：test_tasks 尚无 visibility 列，插入存量行（不涉及 visibility）
        conn = psycopg2.connect(uri)
        cur = conn.cursor()
        try:
            # NOT NULL 列（completed_cases/failed_cases/deleted/reevaluation_count
            # 仅 ORM 侧默认，无 server_default）需显式给出
            cur.execute(
                "INSERT INTO test_tasks (name, status, total_cases, completed_cases, "
                "failed_cases, deleted, reevaluation_count) "
                "VALUES ('INT423_MIG', 'completed', 1, 0, 0, FALSE, 0)")
            conn.commit()
        finally:
            cur.close()
            conn.close()

        # 首次执行迁移
        proc = _run_migration(uri)
        assert proc.returncode == 0, proc.stdout + proc.stderr

        conn = psycopg2.connect(uri)
        cur = conn.cursor()
        try:
            # 存量行自动回填 shared（NOT NULL DEFAULT 'shared' 语义）
            cur.execute("SELECT visibility FROM test_tasks WHERE name = 'INT423_MIG'")
            assert cur.fetchone()[0] == 'shared'

            # 10 表 visibility 列存在，NOT NULL，默认 shared
            for t in VISIBILITY_TABLES:
                cur.execute(
                    "SELECT is_nullable, column_default FROM information_schema.columns "
                    "WHERE table_name = %s AND column_name = 'visibility'", (t,))
                row = cur.fetchone()
                assert row is not None, f'{t}.visibility 列缺失'
                is_nullable, col_default = row
                assert is_nullable == 'NO'
                assert col_default is not None and 'shared' in col_default, \
                    f'{t}.visibility 默认值应为 shared，实际 {col_default!r}'

            # published_tasks 补 created_by_user_id（BIGINT NULL，存量不回填）
            cur.execute(
                "SELECT data_type, is_nullable FROM information_schema.columns "
                "WHERE table_name = 'published_tasks' AND column_name = 'created_by_user_id'")
            row = cur.fetchone()
            assert row is not None, 'published_tasks.created_by_user_id 列缺失'
            assert row[0] == 'bigint' and row[1] == 'YES'

            # 各表 visibility 单列索引（10 个，排除复合索引）
            cur.execute(
                "SELECT count(*) FROM pg_indexes "
                "WHERE indexname LIKE 'idx\\_%\\_visibility' ESCAPE '\\' "
                "AND indexname NOT LIKE 'idx\\_%\\_created\\_visibility' ESCAPE '\\'")
            assert cur.fetchone()[0] == 10, 'visibility 单列索引应为 10 个'

            # 高频 5 表复合索引 (created_by_user_id, visibility)
            cur.execute(
                "SELECT count(*) FROM pg_indexes "
                "WHERE indexname LIKE 'idx\\_%\\_created\\_visibility' ESCAPE '\\'")
            assert cur.fetchone()[0] == 5, '(created_by_user_id, visibility) 复合索引应为 5 个'
        finally:
            cur.close()
            conn.close()

    def test_second_migration_idempotent(self, int423_pg_db):
        """二次执行全 [SKIP]，不执行任何 DDL，不报错。"""
        uri = int423_pg_db
        proc = _run_migration(uri)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert '[EXEC]' not in proc.stdout, '二次执行不应再执行任何 DDL:\n' + proc.stdout


class TestSeedRbacSharePermissionsRealPG:
    """验收④：seed_rbac 幂等重跑授予 7 新权限点，role→权限映射正确。"""

    def test_seed_rbac_idempotent_and_share_mappings(self, int423_pg_db):
        uri = int423_pg_db

        # 首次 + 二次（幂等重跑不报错）
        for _ in range(2):
            proc = _run_seed_rbac(uri)
            assert proc.returncode == 0, proc.stdout + proc.stderr

        conn = psycopg2.connect(uri)
        cur = conn.cursor()
        try:
            # 7 个 share 权限点存在
            for code in SHARE_CODES:
                cur.execute('SELECT 1 FROM permissions WHERE name = %s', (code,))
                assert cur.fetchone() is not None, f'权限点 {code} 缺失'

            # tester 全给 7 个（集合比较：SQL 按名排序，语义集合一致即可）
            cur.execute(
                "SELECT p.name FROM role_permissions rp "
                "JOIN roles r ON r.id = rp.role_id "
                "JOIN permissions p ON p.id = rp.permission_id "
                "WHERE r.name = 'tester' AND p.name LIKE '%:share'")
            assert {r[0] for r in cur.fetchall()} == set(SHARE_CODES)

            # algo_engineer 给 report:share / evaluation:share
            cur.execute(
                "SELECT p.name FROM role_permissions rp "
                "JOIN roles r ON r.id = rp.role_id "
                "JOIN permissions p ON p.id = rp.permission_id "
                "WHERE r.name = 'algo_engineer' AND p.name LIKE '%:share' ORDER BY p.name")
            assert [r[0] for r in cur.fetchall()] == ['evaluation:share', 'report:share']

            # admin 通配 '*' 自动覆盖
            cur.execute(
                "SELECT 1 FROM role_permissions rp "
                "JOIN roles r ON r.id = rp.role_id "
                "JOIN permissions p ON p.id = rp.permission_id "
                "WHERE r.name = 'admin' AND p.name = '*'")
            assert cur.fetchone() is not None

            # device_admin / guest 不应持有任何 share 权限点
            cur.execute(
                "SELECT count(*) FROM role_permissions rp "
                "JOIN roles r ON r.id = rp.role_id "
                "JOIN permissions p ON p.id = rp.permission_id "
                "WHERE r.name IN ('device_admin', 'guest') AND p.name LIKE '%:share'")
            assert cur.fetchone()[0] == 0
        finally:
            cur.close()
            conn.close()
