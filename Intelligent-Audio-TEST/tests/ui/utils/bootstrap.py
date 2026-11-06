# -*- coding: utf-8 -*-
"""隔离库引导（INT-260）：RBAC 种子 + 首个 admin 账号自举。

隔离库口径（负责人指定 intelligent_audio_test_test）下，UI 用例需要：
1. permissions/roles/role_permissions 有 RBAC 种子（否则注册用户无任何权限，
   路由守卫把所有页面弹回首页）——种子由 scripts/migrations/202608/seed_rbac.py
   以 DATABASE_URI 指向隔离库重播（幂等，已存在则跳过）；
2. 存在可登录的 admin 账号（空库首个注册用户自动获 admin 角色，见
   auth_service handle_create_user 的 _FIRST_USER_ROLE_NAME 逻辑）。

安全红线：本模块仅在 conftest 隔离库守卫（/health database == 隔离库名）
通过后被调用；对共享业务库零写路径。
"""
import os
import subprocess
import sys

import psycopg2

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SEED_RBAC = os.path.join(PROJECT_ROOT, 'scripts', 'migrations', '202608', 'seed_rbac.py')


def isolated_db_url() -> str:
    """从仓库 .env 的 DATABASE_URL 推导隔离库连接串（与 run_all --test-db 同口径）。"""
    from urllib.parse import urlsplit, urlunsplit

    from shared.constants.database import ISOLATED_TEST_DB_NAME

    env_path = os.path.join(PROJECT_ROOT, '.env')
    url = ''
    if os.path.isfile(env_path):
        with open(env_path, 'r', encoding='utf-8', errors='replace') as fh:
            for line in fh:
                line = line.strip()
                if line.startswith('DATABASE_URL='):
                    url = line.split('=', 1)[1].strip().strip('"').strip("'")
                    break
    if not url:
        url = os.environ.get('DATABASE_URL', '')
    parts = urlsplit(url)
    if not parts.scheme.startswith('postgres'):
        raise RuntimeError(f'.env DATABASE_URL 非 Postgres，无法推导隔离库连接串: {url!r}')
    return urlunsplit((parts.scheme, parts.netloc, '/' + ISOLATED_TEST_DB_NAME, '', ''))


def roles_seeded(url: str) -> bool:
    conn = psycopg2.connect(url, connect_timeout=5)
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT count(*) FROM roles')
            return (cur.fetchone()[0] or 0) > 0
    finally:
        conn.close()


def seed_rbac(url: str) -> None:
    env = dict(os.environ)
    env['DATABASE_URI'] = url
    env.pop('DATABASE_URL', None)  # 脚本只读 DATABASE_URI，防止串库歧义
    proc = subprocess.run(
        [sys.executable, SEED_RBAC],
        cwd=PROJECT_ROOT, env=env, capture_output=True, text=True, timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f'seed_rbac.py 失败（exit {proc.returncode}）:\n{proc.stdout[-800:]}\n{proc.stderr[-800:]}')
