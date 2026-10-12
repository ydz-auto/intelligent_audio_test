# -*- coding: utf-8 -*-
"""INT-185 共享库 users/RBAC 历史验收残留清理
=============================================================================

背景：INT-179 验收后共享认证库残留约 21+ 条测试用户与 6 个 RBAC 测试角色
（teardown 修复前各验收测试直打共享库所致，来源逐组见 DELETE_USERS 注释）。

原则（issue 验收标准）：
  - 先快照后删除：--snapshot-out 导出全部待删行为 JSON 留档后才执行删除；
  - 内容圈选：按 username/name 精确圈选（均为仓库测试夹具名或运行标记），
    绝不按 ID 盲删；admin / dev_user（INT-156 dev 引导账号）为受保护白名单；
  - 拿不准不删：选集与快照快照态任何漂移（行缺失/多出/被外部引用）一律
    中止，不落删除；
  - 级联清理：user_permissions / user_oauth_bindings / role_permissions
    一并清除，不留孤儿；
  - 不动 custom_oauth_providers 与 user_oauth_bindings 行（INT-179 已清零，
    非零即中止——说明库态与本脚本假设不符）；不碰其他业务表。

用法：
    python cleanup_int185_test_residue.py --dry-run --snapshot-out snap.json
    python cleanup_int185_test_residue.py --snapshot-out snap.json

连接串经 DATABASE_URI / DATABASE_URL 环境变量覆盖（对齐 seed_rbac 惯例）。
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

import psycopg2

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    os.environ.get(
        'DATABASE_URL',
        'postgresql://intelligent_audio_test:intelligent_audio_test666'
        '@localhost:5432/intelligent_audio_test'))

LOCK_TIMEOUT = '10s'

# 受保护账号：真实/基线用户，永不进入删除集
PROTECTED_USERNAMES = {'admin', 'dev_user'}

# ---------------------------------------------------------------------------
# 待删用户（内容圈选，全部为仓库测试夹具名 / 运行标记，来源逐组标注）
# ---------------------------------------------------------------------------
DELETE_USERS = [
    # INT-147 验收/对齐残留（test_int147_auth_alignment.py，运行标记后缀）
    'int147_verify_1791780986',
    'int147_verify_1791781001',
    'int147_verify_1791781141',
    'int147_verify2_39b2aa1d',
    'int147_dbg_25e947',
    'int147_verify2_a3fb1407',
    'int147_rsa_c7f99f80',
    'int147_mail_c7f99f80',
    'int147_tamper_c7f99f80',
    'int147_plain_c7f99f80',
    'int147_bind_0d2032ea',
    'int147_other_0d2032ea',
    # INT-30 sqlite e2e 历史运行固定夹具名（test_auth_servicer_sqlite_e2e.py，
    # 当年直打共享库且无 teardown）
    'busy_user',
    'audit_status_user',
    'perm_user_1',
    'perm_user_3',
    'perm_user_4',
    'managed_user',
    'deleted_role_user',
    'self_registered',
    # INT-141 相关验证残留（int141_ 前缀，status=deleted 软删行）
    'int141_user_b',
    'int141_verify_b',
    'int141_rb_798071',
    'int141_rb_798198',
    'int141_rb_799379',
    # INT-84 空邮箱回归运行标记 f1de6ead（test_auth_empty_email_users.py，
    # 补 teardown 前残留）
    'no_email_a_f1de6ead',
    'no_email_b_f1de6ead',
    'ws_email_f1de6ead',
    'has_email_f1de6ead',
    # G3 HTTP e2e 运行标记 1b548fc3（test_g3_auth_http_e2e.py，INT-179
    # teardown 修复 commit 133336a7 之前残留）
    'e2e_reg_1b548fc3',
    'e2e_dup_1b548fc3',
    'e2e_wrongpw_1b548fc3',
    'zhangsan',
    'e2e_guest_1b548fc3',
    'e2e_admin_1b548fc3',
    'e2e_victim_1b548fc3',
    'takeover-idp-1b548fc3_e2e_victim_1b548fc3',
    # test_g3_oauth_provider_management.py PID=2836 历史运行残留（该测试现已
    # 带 teardown，PID 后缀为当年运行进程号）
    'self_registered_2836',
    'admin_created_2836',
    'login_user_2836',
    'wrong_pw_user_2836',
    'oauth_only_2836',
]

# 待删角色：INT-30 sqlite e2e 历史运行残留（仅删 is_system=false 的同名行）
DELETE_ROLES = [
    'busy_role', 'dup_role', 'baseline_role',
    'wildcard_role', 'assigned_role', 'doomed_role',
]


def _die(msg):
    print(f'[ABORT] {msg}')
    sys.exit(1)


def _rows(cur, sql, params=None):
    cur.execute(sql, params or ())
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def main():
    parser = argparse.ArgumentParser(description='INT-185 残留清理')
    parser.add_argument('--dry-run', action='store_true', help='仅校验与快照，不删除')
    parser.add_argument('--snapshot-out', required=True, help='快照 JSON 输出路径')
    args = parser.parse_args()

    assert not (PROTECTED_USERNAMES & set(DELETE_USERS)), \
        '受保护账号不得进入删除集'

    conn = psycopg2.connect(POSTGRES_URI)
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute(f"SET lock_timeout = '{LOCK_TIMEOUT}'")

    print(f'目标库: {POSTGRES_URI.split("@")[-1]}')
    print(f'模式: {"DRY-RUN" if args.dry_run else "正式执行"}\n')

    # ---- ① 内容圈选 + 门禁校验 ----
    users = _rows(cur, 'SELECT * FROM users WHERE username = ANY(%s) '
                       'ORDER BY id', (DELETE_USERS,))
    found_names = {u['username'] for u in users}
    if found_names != set(DELETE_USERS):
        _die(f'用户选集漂移: 库中缺失 {sorted(set(DELETE_USERS) - found_names)}, '
             f'多出 {sorted(found_names - set(DELETE_USERS))}（先人工核查再重跑）')
    protected_hit = found_names & PROTECTED_USERNAMES
    if protected_hit:
        _die(f'受保护账号被圈中: {protected_hit}')

    roles = _rows(cur, 'SELECT * FROM roles WHERE name = ANY(%s) '
                       'AND is_system = false ORDER BY id', (DELETE_ROLES,))
    if {r['name'] for r in roles} != set(DELETE_ROLES):
        _die('角色选集漂移（缺失/含系统角色），先人工核查')

    role_ids = [r['id'] for r in roles]
    user_ids = [u['id'] for u in users]

    # 待删角色被删除集之外的用户引用 → 中止（防止破坏真实用户）
    outside_refs = _rows(
        cur, 'SELECT id, username, role_id FROM users '
             'WHERE role_id = ANY(%s) AND username != ALL(%s)',
        (role_ids, DELETE_USERS))
    if outside_refs:
        _die(f'待删角色仍被删除集之外的用户引用: {outside_refs}')

    # providers/bindings 基线门禁（issue：保持 0，非零即库态不符）
    for table in ('custom_oauth_providers', 'user_oauth_bindings'):
        cur.execute(f'SELECT COUNT(*) FROM {table}')
        n = cur.fetchone()[0]
        if n != 0:
            _die(f'{table} 有 {n} 行（预期 0）——库态与本脚本假设不符，中止')

    # 删除集之外的用户若有额外权限/绑定行则与本次清理无关，不校验；
    # 删除集用户的关联行先查出来留档
    user_perm_rows = _rows(
        cur, 'SELECT * FROM user_permissions WHERE user_id = ANY(%s) ORDER BY id',
        (user_ids,))
    binding_rows = _rows(
        cur, 'SELECT * FROM user_oauth_bindings WHERE user_id = ANY(%s) ORDER BY id',
        (user_ids,))
    role_perm_rows = _rows(
        cur, 'SELECT * FROM role_permissions WHERE role_id = ANY(%s) ORDER BY id',
        (role_ids,))

    # ---- ② 快照留档（先于任何删除）----
    snapshot = {
        'issue': 'INT-185',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'database': POSTGRES_URI.split('@')[-1],
        'mode': 'dry-run' if args.dry_run else 'apply',
        'delete_users': users,
        'delete_roles': roles,
        'cascade_user_permissions': user_perm_rows,
        'cascade_user_oauth_bindings': binding_rows,
        'cascade_role_permissions': role_perm_rows,
        'protected_usernames': sorted(PROTECTED_USERNAMES),
    }
    with open(args.snapshot_out, 'w', encoding='utf-8') as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2, default=str)
    print(f'快照已写出: {args.snapshot_out}')
    print(f'  待删用户 {len(users)} 条 / 待删角色 {len(roles)} 条 / '
          f'级联 user_permissions {len(user_perm_rows)} / bindings '
          f'{len(binding_rows)} / role_permissions {len(role_perm_rows)}\n')

    if args.dry_run:
        for u in users:
            print(f"  [DRY-RUN] DEL user {u['id']:>4} {u['username']}"
                  f"  (role_id={u['role_id']}, status={u['status']}, "
                  f"created={u['created_at']})")
        for r in roles:
            print(f"  [DRY-RUN] DEL role {r['id']:>4} {r['name']}")
        print('\n[DRY-RUN] 未实际删除。')
        conn.close()
        return

    # ---- ③ 单事务删除（先关联表后主体）----
    try:
        cur.execute('DELETE FROM user_permissions WHERE user_id = ANY(%s)',
                    (user_ids,))
        n_up = cur.rowcount
        cur.execute('DELETE FROM user_oauth_bindings WHERE user_id = ANY(%s)',
                    (user_ids,))
        n_bind = cur.rowcount
        cur.execute('DELETE FROM role_permissions WHERE role_id = ANY(%s)',
                    (role_ids,))
        n_rp = cur.rowcount
        cur.execute('DELETE FROM users WHERE id = ANY(%s)', (user_ids,))
        n_u = cur.rowcount
        cur.execute('DELETE FROM roles WHERE id = ANY(%s)', (role_ids,))
        n_r = cur.rowcount
        conn.commit()
        print(f'已删除: users {n_u} / roles {n_r} / role_permissions {n_rp} / '
              f'user_permissions {n_up} / user_oauth_bindings {n_bind}')
    except Exception as e:
        conn.rollback()
        _die(f'删除事务失败已回滚: {e.__class__.__name__}: {e}')

    # ---- ④ 删除后五表快照 + 孤儿核查 ----
    print('\n== 删除后快照 ==')
    for table in ('users', 'custom_oauth_providers', 'user_oauth_bindings',
                  'roles', 'permissions', 'role_permissions',
                  'user_permissions'):
        cur.execute(f'SELECT COUNT(*) FROM {table}')
        print(f'  {table}: {cur.fetchone()[0]}')

    orphans = {
        'role_permissions→缺失角色': _rows(
            cur, 'SELECT rp.id FROM role_permissions rp LEFT JOIN roles r '
                 'ON r.id = rp.role_id WHERE r.id IS NULL'),
        'role_permissions→缺失权限': _rows(
            cur, 'SELECT rp.id FROM role_permissions rp LEFT JOIN permissions p '
                 'ON p.id = rp.permission_id WHERE p.id IS NULL'),
        'user_permissions→缺失用户': _rows(
            cur, 'SELECT up.id FROM user_permissions up LEFT JOIN users u '
                 'ON u.id = up.user_id WHERE u.id IS NULL'),
        'users.role_id→缺失角色': _rows(
            cur, 'SELECT u.id, u.username FROM users u LEFT JOIN roles r '
                 'ON r.id = u.role_id WHERE u.role_id IS NOT NULL AND r.id IS NULL'),
    }
    for name, rows in orphans.items():
        status = 'OK' if not rows else f'✗ {len(rows)} 条'
        print(f'  孤儿核查 {name}: {status}')

    marker_sql = ("SELECT id, username FROM users WHERE username ~ "
                  "'^(int147_|int141_|e2e_|takeover-idp-|no_email_|ws_email_|"
                  "has_email_|perm_user_|self_registered|admin_created_|"
                  "login_user_|wrong_pw_user_|oauth_only_)' OR username IN "
                  "('zhangsan','busy_user','audit_status_user','managed_user',"
                  "'deleted_role_user')")
    residue = _rows(cur, marker_sql)
    print(f"  用户测试标记扫描: {'OK 零残留' if not residue else residue}")
    cur.execute('SELECT id, name FROM roles WHERE name = ANY(%s)',
                (DELETE_ROLES,))
    print(f"  角色测试标记扫描: {'OK 零残留' if not cur.fetchall() else '✗ 有残留'}")

    conn.close()
    if any(orphans.values()) or residue:
        _die('存在孤儿/残留，人工核查')
    print('\n清理完成。')


if __name__ == '__main__':
    main()
