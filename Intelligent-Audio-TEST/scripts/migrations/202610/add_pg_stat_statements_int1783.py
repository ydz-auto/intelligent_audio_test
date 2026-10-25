# -*- coding: utf-8 -*-
"""迁移脚本：安装 pg_stat_statements 扩展（PG 观测基线·档 0，INT-1783）

背景（2026-10-24 真实库实测，主库 864 MB）：
- pg_available_extensions 里 pg_stat_statements 1.10 可安装，但 pg_extension 里没有；
  没有它，「库很卡」只能靠主观感受，档 1（索引裁决）/ 档 2（logs 收口）/ 索引二次
  评审都缺数据源。
- 该扩展的共享内存只在 **服务端启动时** 由 shared_preload_libraries 建立，运行期
  无法补载 —— 加载侧配置随本卡落在 docker/docker-compose.yml 的 postgres 服务
  （shared_preload_libraries=pg_stat_statements / pg_stat_statements.max=5000 /
  pg_stat_statements.track=all / log_min_duration_statement=500）。
- 本脚本只负责「把扩展装进目标库」这一步，且必须进 docker db_bootstrap 引导链：
  手工建完就完事的话，任何按引导链重建的库（隔离库、全新库）都不会有该扩展。

为什么不是 create_all 的活：
- 扩展不是 ORM 模型，create_all 只建表；扩展属于「存量库/新库都要自愈」的结构
  对象，与 202610 其它 additive 迁移同一口径。

步骤（幂等）：
    ① 检查 pg_available_extensions 是否提供 pg_stat_statements（缺 → 报错退出，
       说明 postgres 镜像不带 contrib，需换镜像；不能静默跳过，否则观测基线永远
       建立不起来）
    ② 已安装 → [SKIP]；否则 CREATE EXTENSION IF NOT EXISTS pg_stat_statements
    ③ 回读 pg_extension.extversion
    ④ 回读四个配置项；shared_preload_libraries 不含该库时打 [WARN]（此时视图
       不可查询，但扩展本身已装好，重启服务端后即生效）——WARN 不阻断引导链：
       配置项是 docker 侧的职责，引导链只保证库内对象存在
    ⑤ 若能查询 pg_stat_statements，回读当前已登记的语句数（证明可用）

用法:
    python scripts/migrations/202610/add_pg_stat_statements_int1783.py --apply
    python scripts/migrations/202610/add_pg_stat_statements_int1783.py --dry-run

幂等性:
    扩展已存在即 [SKIP]，重复执行不报错；不建表、不写业务数据、不改任何既有对象。
"""
import argparse
import os
import sys

import psycopg2

EXTENSION = 'pg_stat_statements'

# 与 docker/docker-compose.yml postgres 服务的 command 一一对应（只用于回读比对）
EXPECTED_SETTINGS = [
    ('shared_preload_libraries', 'pg_stat_statements'),
    ('pg_stat_statements.max', '5000'),
    ('pg_stat_statements.track', 'all'),
    ('log_min_duration_statement', '500ms'),
]

if not os.environ.get('DATABASE_URL'):
    os.environ['DATABASE_URL'] = os.environ.get(
        'DATABASE_URI',
        'postgresql://intelligent_audio_test:intelligent_audio_test666'
        '@localhost:5432/intelligent_audio_test')


def _connect():
    from urllib.parse import urlparse
    parsed = urlparse(os.environ['DATABASE_URL'])
    return psycopg2.connect(
        host=parsed.hostname, port=parsed.port or 5432,
        dbname=parsed.path.lstrip('/'), user=parsed.username,
        password=parsed.password)


def _extension_available(cur):
    cur.execute(
        "SELECT default_version FROM pg_available_extensions WHERE name = %s",
        (EXTENSION,))
    row = cur.fetchone()
    return row[0] if row else None


def _extension_version(cur):
    cur.execute(
        "SELECT extversion FROM pg_extension WHERE extname = %s", (EXTENSION,))
    row = cur.fetchone()
    return row[0] if row else None


def _setting(cur, name):
    cur.execute('SHOW ' + name)
    return cur.fetchone()[0]


def migrate(dry_run=False):
    conn = _connect()
    conn.autocommit = True
    cur = conn.cursor()

    # ① 可用性（镜像不带 contrib 时我们必须知道，而不是静默跳过）
    available = _extension_available(cur)
    if not available:
        print(f'[ERROR] {EXTENSION} 不在 pg_available_extensions：当前 postgres 镜像'
              f'不含该 contrib 扩展，无法建立观测基线')
        cur.close()
        conn.close()
        return 1
    print(f'[CHECK] {EXTENSION} 可用，最新版本 {available}')

    # ② 安装
    installed = _extension_version(cur)
    if installed:
        print(f'[SKIP] 扩展 {EXTENSION} 已安装（版本 {installed}）')
    elif dry_run:
        print(f'[DRY-RUN] CREATE EXTENSION IF NOT EXISTS {EXTENSION}')
    else:
        print(f'[EXEC] CREATE EXTENSION IF NOT EXISTS {EXTENSION}')
        cur.execute(f'CREATE EXTENSION IF NOT EXISTS {EXTENSION}')

    # ③ 回读扩展版本
    if not dry_run:
        version = _extension_version(cur)
        if not version:
            print(f'[ERROR] 执行后仍查不到 {EXTENSION}，安装失败')
            cur.close()
            conn.close()
            return 1
        print(f'[VERIFY] {EXTENSION} extversion = {version}')

    # ④ 回读配置（docker 侧配置项，缺了只 WARN 不阻断引导链）
    preloaded = ''
    for name, expected in EXPECTED_SETTINGS:
        try:
            actual = _setting(cur, name)
        except psycopg2.Error as exc:  # 参数不存在（低版本 PG）时也不阻断
            print(f'[WARN] 读取 {name} 失败: {exc}')
            continue
        print(f'[VERIFY] {name} = {actual!r}（期望 {expected!r}）')
        if name == 'shared_preload_libraries':
            preloaded = actual or ''
        if str(actual) != expected:
            print(f'[WARN] {name} 与期望不一致：库侧要重启 postgres 并按 '
                  f'docker/docker-compose.yml 的 command 加载后才会生效')

    if preloaded and EXTENSION not in [p.strip() for p in preloaded.split(',')]:
        print(f'[WARN] shared_preload_libraries 未包含 {EXTENSION}：'
              f'扩展已安装但 pg_stat_statements 视图在服务端重启加载该库前不可查询')

    # ⑤ 可用性验证（预加载缺失时该查询会报错，仅 WARN）
    if not dry_run:
        try:
            cur.execute('SELECT count(*) FROM pg_stat_statements')
            print(f'[VERIFY] pg_stat_statements 当前登记语句数 = {cur.fetchone()[0]}')
        except psycopg2.Error as exc:
            conn.rollback()
            print(f'[WARN] pg_stat_statements 暂不可查询（{str(exc).strip()}）：'
                  f'服务端未预加载，重启 postgres 后即生效')

    cur.close()
    conn.close()
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='安装 pg_stat_statements 扩展（PG 观测基线，INT-1783）')
    parser.add_argument('--apply', action='store_true',
                        help='真正执行（缺省 dry-run，只检查）')
    parser.add_argument('--dry-run', action='store_true',
                        help='只检查不执行（缺省行为，保留以对齐其它迁移脚本）')
    args = parser.parse_args()
    sys.exit(migrate(dry_run=not args.apply))
