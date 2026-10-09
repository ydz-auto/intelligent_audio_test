# -*- coding: utf-8 -*-
"""自定义 OAuth 提供方种子数据（INT-51 登录体系改造）

向 custom_oauth_providers 表插入预置提供方：
  - huawei（华为云）：配置取自 HW_OAUTH_* 环境变量（与旧硬编码
    HuaweiOAuthProvider 行为等效）；未配置环境变量时跳过。

幂等性：slug 已存在时跳过（不覆盖管理端已修改的配置）。
表结构由 auth_service PO 在建库时创建（custom_oauth_providers）。

用法:
    python seed_custom_oauth_providers.py             # 正式执行
    python seed_custom_oauth_providers.py --dry-run   # 仅预览
"""
import os
import argparse

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666'
    '@localhost:5432/intelligent_audio_test'
)


def _display_uri(uri):
    """控制台展示用连接串：隐藏密码，解析失败不崩溃。"""
    try:
        return make_url(uri).render_as_string(hide_password=True)
    except ArgumentError:
        return '<无法解析的连接串>'


def _huawei_preset():
    """环境变量构造华为云预置提供方（未配置 client_id → None 跳过）。"""
    client_id = os.environ.get('HW_OAUTH_CLIENT_ID', '')
    if not client_id:
        return None
    return {
        'name': '华为云',
        'slug': 'huawei',
        'icon': '',
        'enabled': True,
        'client_id': client_id,
        'client_secret': os.environ.get('HW_OAUTH_CLIENT_SECRET', ''),
        'authorize_url': os.environ.get(
            'HW_OAUTH_AUTHORIZE_URL',
            'https://oauth.huaweicloud.com/oauth2/authorize'),
        'token_url': os.environ.get(
            'HW_OAUTH_TOKEN_URL',
            'https://oauth.huaweicloud.com/oauth2/token'),
        'userinfo_url': os.environ.get(
            'HW_OAUTH_USERINFO_URL',
            'https://oauth.huaweicloud.com/oauth2/userinfo'),
        'scopes': '',
        'user_id_field': 'sub',
        'username_field': 'preferred_username',
        'display_name_field': 'name',
        'email_field': 'email',
    }


def _slug_exists(conn, slug):
    return conn.execute(text(
        'SELECT 1 FROM custom_oauth_providers WHERE slug = :s'
    ), {'s': slug}).scalar() is not None


def seed_providers(conn, dry_run=False):
    print('[Step 1] 插入预置 OAuth 提供方...')
    preset = _huawei_preset()
    if preset is None:
        print('  [SKIP] 未配置 HW_OAUTH_CLIENT_ID，跳过华为云预置提供方')
        return
    if _slug_exists(conn, preset['slug']):
        print(f"  [SKIP] slug 已存在: {preset['slug']}（不覆盖管理端配置）")
        return
    if dry_run:
        print(f"  [DRY-RUN] INSERT provider: {preset['slug']}")
        return
    conn.execute(text(
        'INSERT INTO custom_oauth_providers '
        '(name, slug, icon, enabled, client_id, client_secret, '
        ' authorize_url, token_url, userinfo_url, scopes, '
        ' user_id_field, username_field, display_name_field, email_field) '
        'VALUES (:name, :slug, :icon, :enabled, :client_id, :client_secret, '
        ' :authorize_url, :token_url, :userinfo_url, :scopes, '
        ' :user_id_field, :username_field, :display_name_field, :email_field)'
    ), preset)
    print(f"  [OK] INSERT provider: {preset['slug']}")


def verify(conn):
    rows = conn.execute(text(
        'SELECT id, name, slug, enabled FROM custom_oauth_providers '
        'ORDER BY id'
    )).fetchall()
    print(f'\n验证: custom_oauth_providers 共 {len(rows)} 行')
    for r in rows:
        print(f'  id={r[0]} name={r[1]} slug={r[2]} enabled={r[3]}')


def main():
    parser = argparse.ArgumentParser(description='自定义 OAuth 提供方种子数据')
    parser.add_argument('--dry-run', action='store_true', help='仅预览，不实际执行')
    args = parser.parse_args()

    print(f'数据库: {_display_uri(POSTGRES_URI)}')
    print(f'模式: {"DRY-RUN" if args.dry_run else "正式执行"}\n')

    engine = create_engine(POSTGRES_URI)
    with engine.begin() as conn:
        seed_providers(conn, dry_run=args.dry_run)
        if not args.dry_run:
            verify(conn)
            print('\n种子数据初始化完成!')
        else:
            print('\n[DRY-RUN] 未实际写入数据。')


if __name__ == '__main__':
    main()
