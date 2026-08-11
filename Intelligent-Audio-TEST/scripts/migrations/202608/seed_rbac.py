# -*- coding: utf-8 -*-
"""
RBAC 种子数据初始化
===================================

向 permissions / roles / role_permissions 表插入系统内置数据：
  - 86 个权限点（permissions）
  - 5 个系统角色（roles: admin / tester / algo_engineer / device_admin / guest）
  - 超级通配权限 * → admin
  - tester / algo_engineer / device_admin / guest 各自的角色-权限映射

幂等性：脚本可重复执行，已存在的记录会跳过。

用法:
    python seed_rbac.py              # 正式执行
    python seed_rbac.py --dry-run     # 仅预览

依赖:
    pip install sqlalchemy psycopg2-binary

权限点来源: docs/RBAC权限划分.md 第三节 + 第四节角色-权限矩阵
"""
import os
import sys
import argparse

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
# 权限点定义（85 个）
# ========================================================================

PERMISSIONS = [
    # 任务 (8)
    ('task:read', '查看任务'),
    ('task:create', '创建任务'),
    ('task:update', '修改任务'),
    ('task:delete', '删除任务'),
    ('task:execute', '执行/控制任务'),
    ('task:merge', '合并任务'),
    ('task:batch', '批量任务'),
    ('task:reextract', '重新提取任务结果'),
    # 测试用例 (7)
    ('testcase:read', '查看测试用例'),
    ('testcase:create', '创建测试用例'),
    ('testcase:update', '修改测试用例'),
    ('testcase:delete', '删除测试用例'),
    ('testcase:copy', '复制测试用例'),
    ('testcase:preview', '预览测试用例'),
    ('testcase:import_export', '导入/导出测试用例'),
    # 音频 (6)
    ('audio:read', '查看音频'),
    ('audio:upload', '上传音频'),
    ('audio:update', '修改音频'),
    ('audio:delete', '删除音频'),
    ('audio:convert', '音频转码'),
    ('audio:folder', '音频文件夹管理'),
    # 被测设备 (5)
    ('device:read', '查看被测设备'),
    ('device:create', '创建被测设备'),
    ('device:update', '修改被测设备'),
    ('device:delete', '删除被测设备'),
    ('device:control', '控制被测设备'),
    # 播放设备 (5)
    ('playback:read', '查看播放设备'),
    ('playback:create', '创建播放设备'),
    ('playback:update', '修改播放设备'),
    ('playback:delete', '删除播放设备'),
    ('playback:control', '控制播放设备'),
    # 声压级 (5)
    ('spl:read', '查看 SPL 校准'),
    ('spl:create', '创建 SPL 校准'),
    ('spl:update', '修改 SPL 校准'),
    ('spl:delete', '删除 SPL 校准'),
    ('spl:test_tone', 'SPL 测试音播放'),
    # API 配置 (5)
    ('api_config:read', '查看 API 配置'),
    ('api_config:create', '创建 API 配置'),
    ('api_config:update', '修改 API 配置'),
    ('api_config:delete', '删除 API 配置'),
    ('api_config:test', '测试 API 连接'),
    # 报告 (7)
    ('report:read', '查看报告'),
    ('report:create', '创建报告'),
    ('report:update', '修改报告'),
    ('report:delete', '删除报告'),
    ('report:publish', '发布报告'),
    ('report:compare', '对比报告'),
    ('report:download_log', '下载报告日志'),
    # 评估 (5)
    ('evaluation:read', '查看评估维度'),
    ('evaluation:execute', '触发重新评估'),
    ('evaluation:dim_manage', '维度 CRUD/批量/计算'),
    ('evaluation:category_manage', '评估分类 CRUD'),
    ('evaluation:import_export', '维度导入/导出'),
    # 算法配置 (5)
    ('algorithm:read', '查看算法配置'),
    ('algorithm:definition_manage', '算法定义 CRUD'),
    ('algorithm:group_manage', '算法分组 CRUD'),
    ('algorithm:param_manage', '算法参数 CRUD'),
    ('algorithm:case_param_manage', '用例算法参数 CRUD'),
    # 用例分组 (4)
    ('group:read', '查看用例分组'),
    ('group:create', '创建分组'),
    ('group:update', '修改分组/移动用例'),
    ('group:delete', '删除分组'),
    # 标签 (4)
    ('tag:read', '查看标签/分类'),
    ('tag:create', '创建标签/分类'),
    ('tag:update', '修改标签/分类'),
    ('tag:delete', '删除标签/分类'),
    # 日志 (3)
    ('log:read', '查看日志/统计/归档'),
    ('log:manage', '标记/刷新/清空/归档日志'),
    ('log:websocket', '订阅 WebSocket 日志推送'),
    # 首页 (2)
    ('home:read', '查看首页统计'),
    ('home:refresh', '刷新首页统计'),
    # SSE (1)
    ('sse:read', '订阅 SSE 事件流'),
    # 用户/角色/权限管理 (11)
    ('user:read', '查看用户列表/详情'),
    ('user:create', '创建用户'),
    ('user:update', '修改用户信息/状态/密码'),
    ('user:delete', '禁用/删除用户'),
    ('user:assign_role', '分配用户角色'),
    ('user:grant_permission', '授予/撤销用户额外权限'),
    ('role:read', '查看角色列表/详情/权限'),
    ('role:create', '创建自定义角色'),
    ('role:update', '修改角色信息/权限分配'),
    ('role:delete', '删除自定义角色'),
    ('permission:read', '查看所有权限点'),
    # 认证 (5)
    ('auth:login', '登录'),
    ('auth:callback', 'OAuth 回调'),
    ('auth:refresh', '刷新令牌'),
    ('auth:logout', '登出'),
    ('auth:me', '获取当前用户信息'),
    # 超级通配 (1)
    ('*', '超级权限（通配所有操作）'),
]

# ========================================================================
# 角色定义 (5)
# ========================================================================

ROLES = [
    ('admin', '超级管理员', True),
    ('tester', '测试工程师（含测试主管）', True),
    ('algo_engineer', '算法工程师（含质量负责人）', True),
    ('device_admin', '设备管理员', True),
    ('guest', '游客', True),
]

# ========================================================================
# 角色-权限映射
# ========================================================================

# tester 权限（对应 RBAC 权限划分文档 4.1 矩阵 tester = ✓）
TESTER_PERMS = [
    'task:read', 'task:create', 'task:update', 'task:delete', 'task:execute',
    'task:merge', 'task:batch', 'task:reextract',
    'testcase:read', 'testcase:create', 'testcase:update', 'testcase:delete',
    'testcase:copy', 'testcase:preview', 'testcase:import_export',
    'audio:read', 'audio:upload', 'audio:update', 'audio:delete',
    'audio:convert', 'audio:folder',
    'device:read',
    'api_config:read', 'api_config:create', 'api_config:update',
    'api_config:delete', 'api_config:test',
    'report:read', 'report:create', 'report:update', 'report:delete',
    'report:compare', 'report:download_log',
    'evaluation:read', 'evaluation:execute', 'evaluation:dim_manage',
    'evaluation:category_manage', 'evaluation:import_export',
    'algorithm:read', 'algorithm:case_param_manage',
    'group:read', 'group:create', 'group:update', 'group:delete',
    'tag:read', 'tag:create', 'tag:update', 'tag:delete',
    'log:read', 'log:manage', 'log:websocket',
    'home:read', 'home:refresh',
    'sse:read',
    'auth:login', 'auth:callback', 'auth:refresh', 'auth:logout', 'auth:me',
]

# algo_engineer 权限
ALGO_ENGINEER_PERMS = [
    'task:read',
    'testcase:read',
    'audio:read',
    'api_config:read',
    'report:read', 'report:create', 'report:update', 'report:publish',
    'report:compare', 'report:download_log',
    'evaluation:read', 'evaluation:dim_manage', 'evaluation:category_manage',
    'evaluation:import_export',
    'algorithm:read', 'algorithm:definition_manage', 'algorithm:group_manage',
    'algorithm:param_manage', 'algorithm:case_param_manage',
    'group:read',
    'tag:read',
    'log:read', 'log:websocket',
    'home:read',
    'sse:read',
    'auth:login', 'auth:callback', 'auth:refresh', 'auth:logout', 'auth:me',
]

# device_admin 权限
DEVICE_ADMIN_PERMS = [
    'device:read', 'device:create', 'device:update', 'device:delete',
    'device:control',
    'playback:read', 'playback:create', 'playback:update', 'playback:delete',
    'playback:control',
    'spl:read', 'spl:create', 'spl:update', 'spl:delete', 'spl:test_tone',
    'home:read',
    'sse:read',
    'auth:login', 'auth:callback', 'auth:refresh', 'auth:logout', 'auth:me',
]

# guest 权限（只读：报告 + 首页 + SSE + 认证，不含日志）
GUEST_PERMS = [
    'report:read', 'report:compare',
    'home:read',
    'sse:read',
    'auth:login', 'auth:callback', 'auth:refresh', 'auth:logout', 'auth:me',
]


# ========================================================================
# 执行逻辑
# ========================================================================

def _get_perm_id_map(conn):
    """获取 permission name → id 映射"""
    rows = conn.execute(text(
        'SELECT id, name FROM permissions'
    )).fetchall()
    return {row[1]: row[0] for row in rows}


def _get_role_id_map(conn):
    """获取 role name → id 映射"""
    rows = conn.execute(text(
        'SELECT id, name FROM roles'
    )).fetchall()
    return {row[1]: row[0] for row in rows}


def _perm_exists(conn, name):
    """检查权限是否已存在"""
    return conn.execute(text(
        'SELECT 1 FROM permissions WHERE name = :n'
    ), {'n': name}).scalar() is not None


def _role_exists(conn, name):
    """检查角色是否已存在"""
    return conn.execute(text(
        'SELECT 1 FROM roles WHERE name = :n'
    ), {'n': name}).scalar() is not None


def _role_perm_exists(conn, role_id, perm_id):
    """检查角色-权限映射是否已存在"""
    return conn.execute(text(
        'SELECT 1 FROM role_permissions WHERE role_id = :r AND permission_id = :p'
    ), {'r': role_id, 'p': perm_id}).scalar() is not None


def seed_permissions(conn, dry_run=False):
    """Step 1: 插入权限点"""
    print('[Step 1] 插入权限点...')
    inserted = 0
    for name, desc in PERMISSIONS:
        if _perm_exists(conn, name):
            continue
        if dry_run:
            print(f'  [DRY-RUN] INSERT permission: {name}')
        else:
            conn.execute(text(
                'INSERT INTO permissions (name, description) VALUES (:n, :d)'
            ), {'n': name, 'd': desc})
        inserted += 1
    print(f'  权限点: {inserted} 新增, {len(PERMISSIONS) - inserted} 已存在')
    return inserted


def seed_roles(conn, dry_run=False):
    """Step 2: 插入系统角色"""
    print('[Step 2] 插入系统角色...')
    inserted = 0
    for name, desc, is_system in ROLES:
        if _role_exists(conn, name):
            continue
        if dry_run:
            print(f'  [DRY-RUN] INSERT role: {name}')
        else:
            conn.execute(text(
                'INSERT INTO roles (name, description, is_system) '
                'VALUES (:n, :d, :s)'
            ), {'n': name, 'd': desc, 's': is_system})
        inserted += 1
    print(f'  角色: {inserted} 新增, {len(ROLES) - inserted} 已存在')
    return inserted


def seed_role_permissions(conn, dry_run=False):
    """Step 3: 插入角色-权限映射"""
    print('[Step 3] 插入角色-权限映射...')
    perm_map = _get_perm_id_map(conn)
    role_map = _get_role_id_map(conn)

    role_perm_groups = [
        ('admin', ['*']),  # admin 持有超级通配权限
        ('tester', TESTER_PERMS),
        ('algo_engineer', ALGO_ENGINEER_PERMS),
        ('device_admin', DEVICE_ADMIN_PERMS),
        ('guest', GUEST_PERMS),
    ]

    total_inserted = 0
    for role_name, perm_names in role_perm_groups:
        role_id = role_map.get(role_name)
        if not role_id:
            print(f'  [SKIP] 角色 {role_name} 不存在，跳过')
            continue
        count = 0
        for pn in perm_names:
            perm_id = perm_map.get(pn)
            if not perm_id:
                print(f'  [WARN] 权限 {pn} 不存在，跳过')
                continue
            if _role_perm_exists(conn, role_id, perm_id):
                continue
            if dry_run:
                print(f'  [DRY-RUN] {role_name} → {pn}')
            else:
                conn.execute(text(
                    'INSERT INTO role_permissions (role_id, permission_id) '
                    'VALUES (:r, :p)'
                ), {'r': role_id, 'p': perm_id})
            count += 1
        print(f'  {role_name}: {count} 个映射新增')
        total_inserted += count

    print(f'  总计: {total_inserted} 个角色-权限映射新增')
    return total_inserted


def verify(conn):
    """验证种子数据"""
    print('\n========== 验证 ==========')
    perm_count = conn.execute(
        text('SELECT COUNT(*) FROM permissions')
    ).scalar()
    role_count = conn.execute(
        text('SELECT COUNT(*) FROM roles')
    ).scalar()
    rp_count = conn.execute(
        text('SELECT COUNT(*) FROM role_permissions')
    ).scalar()

    print(f'  permissions 表: {perm_count} 条')
    print(f'  roles 表: {role_count} 条')
    print(f'  role_permissions 表: {rp_count} 条')

    print('\n  各角色权限数:')
    for role_name in ['admin', 'tester', 'algo_engineer', 'device_admin', 'guest']:
        role_id = conn.execute(text(
            'SELECT id FROM roles WHERE name = :n'
        ), {'n': role_name}).scalar()
        if role_id:
            cnt = conn.execute(text(
                'SELECT COUNT(*) FROM role_permissions WHERE role_id = :r'
            ), {'r': role_id}).scalar()
            print(f'    {role_name}: {cnt} 个权限')


def main():
    parser = argparse.ArgumentParser(description='RBAC 种子数据初始化')
    parser.add_argument('--dry-run', action='store_true', help='仅预览，不实际执行')
    args = parser.parse_args()

    print(f'数据库: {POSTGRES_URI.split("@")[1]}')
    print(f'模式: {"DRY-RUN" if args.dry_run else "正式执行"}\n')

    engine = create_engine(POSTGRES_URI)

    with engine.begin() as conn:
        seed_permissions(conn, dry_run=args.dry_run)
        seed_roles(conn, dry_run=args.dry_run)
        seed_role_permissions(conn, dry_run=args.dry_run)

        if not args.dry_run:
            verify(conn)
            print('\n种子数据初始化完成!')
        else:
            print('\n[DRY-RUN] 未实际写入数据。')


if __name__ == '__main__':
    main()
