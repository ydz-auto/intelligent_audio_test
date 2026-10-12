# -*- coding: utf-8 -*-
"""
users 表旧 schema 漂移收敛 + dev 引导用户种子（INT-156）
=============================================================================

问题：
  快照恢复 / 旧库升级场景下，users 表仍为旧 schema，与代码模型
  auth_service/infrastructure/persistence/models/user_models.py 漂移：
    ① password_hash NOT NULL（代码 nullable=True，OAuth 用户可为空）；
    ② email        NOT NULL（代码 nullable=True）；
    ③ legacy 列 role NOT NULL 且无默认值（代码已无此列，ORM INSERT 不含它，
       任何 ORM 建号必然 NotNullViolation）；
  users 表为空时，dev 登录引导建号（api_gateway local_oauth →
  auth_service CreateUser）必败，一切依赖登录的链路全阻塞。

修复（四步，全部幂等，可安全重复执行）：
  ① users.password_hash 置 nullable（对齐 ORM）；
  ② users.email 置 nullable（对齐 ORM）；
  ③ legacy 列 role 处置：先把 role 字符串按 roles.name 回填 role_id
     （镜像 202608 基线的 role→role_id 迁移，兜底未跑过基线的库），
     再 DROP COLUMN role（⚠️ 破坏性：role 原值删除；代码与 202608 后
     的数据均以 role_id 为准，代码库无任何裸 SQL 引用 users.role）；
  ④ users 表为空时种子 dev 引导用户：username=DEV_DEFAULT_USERNAME
     （默认 dev_user），绑定角色 DEV_DEFAULT_ROLE（默认 admin，
     roles 表缺失该角色则跳过并提示先跑 seed_rbac.py），密码哈希
     DEV_DEFAULT_PASSWORD（默认 dev_password，bcrypt），email NULL，
     status='active'。表非空则跳过（运行时 INT-36 引导路径自会建号）。

幂等性：列已 nullable / 已删除 / 表非空 均打印 [SKIP]；种子带
ON CONFLICT DO NOTHING 兜底并发。全新库（create_all_tables 建表）
①②③ 为 no-op，④ 视 users 是否为空执行。

用法：
    python scripts/migrations/202610/fix_users_schema_drift.py           # 预览
    python scripts/migrations/202610/fix_users_schema_drift.py --apply   # 实际执行

⚠️ 先停服务再执行（README 执行须知：ALTER TABLE 需 ACCESS EXCLUSIVE 锁）。
连接串经 DATABASE_URI 环境变量覆盖；连接带 lock_timeout=10s，
被长事务阻塞时快速失败而非无限等待，稍后重试即可。

依赖：
  ③ 的回填与 ④ 的角色解析依赖 roles 表（202608 ① 建表 / ⑦ seed_rbac
  种子）；roles 缺失时对应步骤跳过并给出提示。
"""
import os
import sys

import psycopg2

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666'
    '@localhost:5432/intelligent_audio_test'
)

DEV_USERNAME = os.environ.get('DEV_DEFAULT_USERNAME', 'dev_user')
DEV_ROLE = os.environ.get('DEV_DEFAULT_ROLE', 'admin')
DEV_PASSWORD = os.environ.get('DEV_DEFAULT_PASSWORD', 'dev_password')

LOCK_TIMEOUT = '10s'


def main():
    apply = '--apply' in sys.argv

    print("=" * 60)
    print("users 表旧 schema 漂移收敛 + dev 引导用户种子（INT-156）")
    print(f"模式: {'实际执行 (--apply)' if apply else '预览 (dry-run)'}")
    print(f"目标库: {POSTGRES_URI.split('@')[-1]}")
    print(f"dev 引导用户: {DEV_USERNAME} / 角色 {DEV_ROLE}")
    print("=" * 60)

    conn = psycopg2.connect(POSTGRES_URI)
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute(f"SET lock_timeout = '{LOCK_TIMEOUT}'")

    def run(sql, tag):
        """执行单条 DDL/DML；锁超时回滚并中止，提示停服务重试。"""
        try:
            cur.execute(sql)
            conn.commit()
            print(f"  [OK] {tag}")
            return True
        except psycopg2.errors.LockNotAvailable:
            conn.rollback()
            print(f"  [FAIL] {tag}: 等待锁超时（{LOCK_TIMEOUT}）。"
                  "有长事务/空闲连接持有 users 表锁——先停服务再执行（README 执行须知）")
            sys.exit(1)
        except psycopg2.errors.UndefinedTable:
            conn.rollback()
            print(f"  [FAIL] {tag}: users/roles 表不存在——先跑 scripts/create_all_tables.py 与 202608 基线")
            sys.exit(1)

    columns = None
    with conn.cursor() as c:
        c.execute("SELECT to_regclass('public.users') IS NOT NULL")
        has_users = c.fetchone()[0]
    if not has_users:
        print("\n[FAIL] users 表不存在——先跑 scripts/create_all_tables.py")
        sys.exit(1)
    with conn.cursor() as c:
        c.execute("SELECT column_name, is_nullable, column_default "
                  "FROM information_schema.columns WHERE table_name = 'users'")
        columns = {name: (nullable == 'NO', default)
                   for name, nullable, default in c.fetchall()}

    # ---- ① password_hash 置 nullable ----
    not_null = columns.get('password_hash', (True, None))[0]
    if not_null:
        print("\n① users.password_hash: NOT NULL → nullable")
        if apply:
            run("ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL",
                "password_hash 已置 nullable")
            columns['password_hash'] = (False, columns['password_hash'][1])
    else:
        print("\n① users.password_hash: 已 nullable（幂等跳过）")

    # ---- ② email 置 nullable ----
    not_null = columns.get('email', (True, None))[0]
    if not_null:
        print("\n② users.email: NOT NULL → nullable")
        if apply:
            run("ALTER TABLE users ALTER COLUMN email DROP NOT NULL",
                "email 已置 nullable")
            columns['email'] = (False, columns['email'][1])
    else:
        print("\n② users.email: 已 nullable（幂等跳过）")

    # ---- ③ legacy 列 role：回填 role_id 后删除 ----
    has_role_col = 'role' in columns
    print(f"\n③ legacy 列 users.role: {'存在' if has_role_col else '不存在（幂等跳过）'}")
    if has_role_col:
        has_roles = False
        with conn.cursor() as c:
            c.execute("SELECT to_regclass('public.roles') IS NOT NULL")
            has_roles = c.fetchone()[0]
        if not has_roles:
            print("  [WARN] roles 表不存在，无法回填 role_id——"
                  "先跑 202608 基线 ① 与 seed_rbac ⑦，再执行本脚本")
            sys.exit(1)
        with conn.cursor() as c:
            c.execute("SELECT count(*) FROM users "
                      "WHERE role IS NOT NULL AND role_id IS NULL")
            backfill_rows = c.fetchone()[0]
        print(f"  ③-回填: role_id 为空且 role 非空的行: {backfill_rows} 条"
              f"{'（UPDATE ... 按roles.name回填）' if backfill_rows else '（无需处理）'}")
        if apply and backfill_rows:
            run("UPDATE users SET role_id = "
                "(SELECT id FROM roles WHERE roles.name = users.role) "
                "WHERE role IS NOT NULL AND role_id IS NULL",
                f"已回填 {backfill_rows} 行 role_id")
        print("  ③-删除: ⚠️ DROP COLUMN role（破坏性：原值删除，数据已由 role_id 承载）")
        if apply:
            run("ALTER TABLE users DROP COLUMN role", "legacy 列 role 已删除")

    # ---- ④ users 为空时种子 dev 引导用户 ----
    with conn.cursor() as c:
        c.execute("SELECT count(*) FROM users")
        user_count = c.fetchone()[0]
    print(f"\n④ dev 引导用户种子: users 现有 {user_count} 行")
    if user_count > 0:
        print("  [SKIP] 表非空，不种子（运行时 INT-36 引导路径自会建号）")
    else:
        has_roles = False
        with conn.cursor() as c:
            c.execute("SELECT to_regclass('public.roles') IS NOT NULL")
            has_roles = c.fetchone()[0]
        role_id = None
        if has_roles:
            with conn.cursor() as c:
                c.execute("SELECT id FROM roles WHERE name = %s", (DEV_ROLE,))
                row = c.fetchone()
                role_id = row[0] if row else None
        if role_id is None:
            print(f"  [WARN] 角色 {DEV_ROLE!r} 不存在，跳过种子——"
                  "先跑 scripts/migrations/202608/seed_rbac.py 再重跑本脚本")
        else:
            import bcrypt
            password_hash = bcrypt.hashpw(
                DEV_PASSWORD.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            sql = ("INSERT INTO users "
                   "(username, password_hash, email, role_id, status, "
                   "created_at, updated_at) "
                   "VALUES (%s, %s, NULL, %s, 'active', now(), now()) "
                   "ON CONFLICT DO NOTHING")
            print(f"  计划: INSERT {DEV_USERNAME}（role_id={role_id}，"
                  "email NULL，bcrypt 密码哈希，status=active）")
            if apply:
                try:
                    cur.execute(sql, (DEV_USERNAME, password_hash, role_id))
                    conn.commit()
                    with conn.cursor() as c:
                        c.execute("SELECT id, username, role_id, status "
                                  "FROM users WHERE username = %s", (DEV_USERNAME,))
                        row = c.fetchone()
                    if row:
                        print(f"  [OK] 已种子 dev 引导用户: id={row[0]} "
                              f"username={row[1]} role_id={row[2]} status={row[3]}")
                    else:
                        print("  [SKIP] 并发下已存在同名用户（ON CONFLICT 兜底）")
                except psycopg2.errors.LockNotAvailable:
                    conn.rollback()
                    print(f"  [FAIL] 等待锁超时（{LOCK_TIMEOUT}）——先停服务再执行")
                    sys.exit(1)

    # ---- 校验 ----
    print("\n== 迁移后 users 表校验 ==")
    with conn.cursor() as c:
        c.execute("SELECT column_name, is_nullable FROM information_schema.columns "
                  "WHERE table_name = 'users' ORDER BY ordinal_position")
        final_cols = c.fetchall()
        for name, nullable in final_cols:
            mark = ''
            if name in ('password_hash', 'email'):
                mark = '  ← 应为 YES' if nullable == 'YES' else '  ← ✗ 仍为 NO！'
            if name == 'role':
                mark = '  ← ✗ 应已删除！'
            print(f"  {name}: nullable={nullable}{mark}")
        c.execute("SELECT count(*) FROM users")
        print(f"  users 行数: {c.fetchone()[0]}")

    conn.close()
    if not apply:
        print("\n" + "=" * 60)
        print("预览完成，加上 --apply 参数执行实际迁移")
    print("\n完成！")


if __name__ == '__main__':
    main()
