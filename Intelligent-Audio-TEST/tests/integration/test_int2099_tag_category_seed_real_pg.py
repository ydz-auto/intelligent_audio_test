# -*- coding: utf-8 -*-
"""INT-2099 标签分类补齐种子：真实 PostgreSQL 临时库验收（阶段 1）。

卡面阶段 1 验收口径：
1. 隔离库执行两次：活跃分类恰 6 条且无重复；归类标签 61、未分类 27
   （按 2026-10-30 真实库 88 条活跃标签口径）；无标签被改除 category_id 外的字段。
2. 现有标签 CRUD（创建 / 编辑 / 删除）不受影响，回读一致。
3. 幂等：重跑 0 变更。

做法（沿用 tests/integration/test_int423_visibility_migration_real_pg.py 的
临时库范式）：本机 Postgres 建一次性库 → 全模型 create_all → 造出与真实库
同形的存量数据（105 条全软删分类、88 条活跃标签、外加若干软删标签/同名软删
分类）→ 以**独立进程**跑种子脚本（dry-run / --apply / 再 --apply）→ 逐行
快照对拍 → 再以独立进程跑标签 CRUD 回读探针（int2099_tag_crud_probe.py）。

为什么 CRUD 走子进程：网关标签接口经 gRPC 调 task_service（真实库），而
task_service 的连接由 BaseConfig 在导入时固化；同进程改绑定会污染同一
pytest 会话的其它用例（INT-90 踩过），故探针独立进程只连隔离库。
真实栈的 HTTP 层验收属本卡阶段 2（负责人确认口径后对 docker 主库执行）。
"""
import json
import os
import subprocess
import sys
import uuid

import psycopg2
import pytest
from sqlalchemy import create_engine

from tests.unit.test_int2099_tag_category_seed import (
    ACTIVE_TAG_NAMES_20261030,
    EXPECTED_COUNTS,
    EXPECTED_UNCATEGORIZED,
)

PG_HOST = os.environ.get('INT35_PG_HOST', '127.0.0.1')
PG_PORT = int(os.environ.get('INT35_PG_PORT', '5432'))
PG_USER = os.environ.get('INT35_PG_USER', 'intelligent_audio_test')
PG_PASSWORD = os.environ.get('INT35_PG_PASSWORD', 'intelligent_audio_test666')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
_SEED = os.path.join(PROJECT_ROOT, 'scripts', 'migrations', '202610',
                     'seed_tag_categories_int2099.py')
_PROBE = os.path.join(PROJECT_ROOT, 'tests', 'integration',
                      'int2099_tag_crud_probe.py')

# 造存量：105 条软删分类（含一个与目标同名的「打断」，钉住「软删行不复活」）
_SOFT_DELETED_FILLER_CATEGORIES = 99
_SOFT_DELETED_SAME_NAME = '打断'
# 造存量：软删标签（命中规则也不得被改）
_SOFT_DELETED_TAGS = ['被打断的软删标签', '软删拒识标签', '软删接管标签', '软删环境理解标签']


def _pg_params(dbname):
    return dict(host=PG_HOST, port=PG_PORT, user=PG_USER,
                password=PG_PASSWORD, dbname=dbname, connect_timeout=5)


def _pg_reachable():
    try:
        conn = psycopg2.connect(**_pg_params('postgres'))
        conn.close()
        return True
    except Exception:
        return False


@pytest.fixture(scope='module')
def int2099_pg_db():
    """真实 Postgres 临时库：整库创建 → 全模型建表 → 用后即删。"""
    if not _pg_reachable():
        pytest.skip(f'本机 Postgres {PG_HOST}:{PG_PORT} 不可用，INT-2099 隔离库验收跳过')

    dbname = f'int2099_{uuid.uuid4().hex[:10]}'
    admin = psycopg2.connect(**_pg_params('postgres'))
    admin.autocommit = True
    cur = admin.cursor()
    cur.execute(f'CREATE DATABASE {dbname} ENCODING utf8')
    cur.close()

    import shared.models.database as database
    from scripts.create_all_tables import _import_all_models
    _import_all_models()  # 注册全模型（与引导链建库口径一致，93 张表）

    uri = f'postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{dbname}'
    engine = create_engine(uri, pool_pre_ping=True)
    database.Base.metadata.create_all(engine)
    engine.dispose()

    yield uri

    admin = psycopg2.connect(**_pg_params('postgres'))
    admin.autocommit = True
    cur = admin.cursor()
    cur.execute(f'DROP DATABASE IF EXISTS {dbname} WITH (FORCE)')
    cur.close()
    admin.close()


def _run_subprocess(script, uri, *args):
    env = dict(os.environ)
    env.update({
        'DATABASE_URL': uri,
        'PYTHONIOENCODING': 'utf-8',
        'OSS_ACCESS_KEY': env.get('OSS_ACCESS_KEY', 'test'),
        'OSS_SECRET_KEY': env.get('OSS_SECRET_KEY', 'test'),
    })
    return subprocess.run(
        [sys.executable, script, *args], env=env, cwd=PROJECT_ROOT,
        capture_output=True, text=True, encoding='utf-8', errors='replace')


def _insert_existing_state(uri):
    """造出与真实库同形的存量：活跃分类 0、活跃标签 88、若干软删行。"""
    conn = psycopg2.connect(uri)
    try:
        cur = conn.cursor()
        # 105 条软删分类：含一个与目标同名的「打断」，其余为走查/测试残留形态
        names = [f'接线测试_走查分类{i:03d}' for i in range(_SOFT_DELETED_FILLER_CATEGORIES)]
        names.append(_SOFT_DELETED_SAME_NAME)
        assert len(names) == 100
        # 补齐到 105 条（真实库 105 行）
        names.extend(f'历史分类_{i:03d}' for i in range(5))
        assert len(names) == 105
        for name in names:
            cur.execute(
                "INSERT INTO tag_categories "
                "  (name, description, sort_order, visibility, deleted, created_at, updated_at) "
                "VALUES (%s, NULL, 0, 'shared', true, NOW(), NOW())", (name,))

        # 88 条活跃标签（2026-10-30 真实库快照），category_id 全 NULL
        for index, name in enumerate(ACTIVE_TAG_NAMES_20261030):
            cur.execute(
                "INSERT INTO tags "
                "  (name, description, color, category_id, visibility, deleted, created_at, updated_at) "
                "VALUES (%s, %s, NULL, NULL, 'shared', false, NOW(), NOW())",
                (name, f'snapshot#{index}'))

        # 4 条软删标签（名称命中规则也不得被改）
        for name in _SOFT_DELETED_TAGS:
            cur.execute(
                "INSERT INTO tags "
                "  (name, description, color, category_id, visibility, deleted, "
                "   deleted_at, created_at, updated_at) "
                "VALUES (%s, 'soft-deleted', NULL, NULL, 'shared', true, NOW(), NOW(), NOW())",
                (name,))
        conn.commit()
        cur.close()
    finally:
        conn.close()


def _fetch_rows(uri, sql):
    conn = psycopg2.connect(uri)
    try:
        cur = conn.cursor()
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        cur.close()
        return rows
    finally:
        conn.close()


def _snapshot(uri):
    """相关表逐行快照（按 id 排序，含软删行）。"""
    return {
        'tags': _fetch_rows(uri, 'SELECT * FROM tags ORDER BY id'),
        'categories': _fetch_rows(uri, 'SELECT * FROM tag_categories ORDER BY id'),
    }


def _assert_seed_result(uri):
    """卡面阶段 1 验收 1：6 个活跃分类、61 归类 / 27 未分类。"""
    active_categories = _fetch_rows(
        uri,
        'SELECT id, name, sort_order, description, color, visibility, '
        'created_by_user_id, deleted FROM tag_categories WHERE deleted = false '
        'ORDER BY sort_order, id')
    assert [c['name'] for c in active_categories] == [
        '人工录制', '打断', '拒识', '接管', '恢复前文', '环境理解']
    assert len({c['name'] for c in active_categories}) == 6, '活跃分类出现重复'
    assert [c['sort_order'] for c in active_categories] == [10, 20, 30, 40, 50, 60]
    # 系统回填：不冒充操作人、不私开可见性
    assert all(c['created_by_user_id'] is None for c in active_categories)
    assert all(c['visibility'] == 'shared' for c in active_categories)
    assert all(c['description'] is None and c['color'] is None
               for c in active_categories)

    grouped = _fetch_rows(
        uri,
        "SELECT c.name AS name, count(*) AS n FROM tags t "
        "JOIN tag_categories c ON c.id = t.category_id "
        "WHERE t.deleted = false AND c.deleted = false GROUP BY c.name, c.sort_order "
        "ORDER BY c.sort_order")
    assert {row['name']: row['n'] for row in grouped} == EXPECTED_COUNTS

    unclassified = _fetch_rows(
        uri, 'SELECT count(*) AS n FROM tags WHERE deleted = false AND category_id IS NULL')
    assert unclassified[0]['n'] == EXPECTED_UNCATEGORIZED
    assert sum(EXPECTED_COUNTS.values()) + EXPECTED_UNCATEGORIZED == 88

    # 不把活跃标签挂到软删分类上
    dangling = _fetch_rows(
        uri,
        'SELECT count(*) AS n FROM tags t JOIN tag_categories c ON c.id = t.category_id '
        'WHERE t.deleted = false AND c.deleted = true')
    assert dangling[0]['n'] == 0

    total_categories = _fetch_rows(uri, 'SELECT count(*) AS n FROM tag_categories')
    assert total_categories[0]['n'] == 105 + 6, '不得复活/改写软删分类行'


def test_seed_and_crud_on_isolated_pg(int2099_pg_db):
    uri = int2099_pg_db
    _insert_existing_state(uri)
    before = _snapshot(uri)

    active_before = [c for c in before['categories'] if not c['deleted']]
    assert active_before == [], '存量前置：活跃分类应为 0'
    assert len([t for t in before['tags'] if not t['deleted']]) == 88

    # ── 1) dry-run：只打印计划，不落库 ─────────────────────────────
    dry = _run_subprocess(_SEED, uri)
    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert '[DRY] 未写入' in dry.stdout
    assert '新建 6 个、复用 0 个' in dry.stdout
    assert '本次将写入 tags.category_id 共 61 行' in dry.stdout
    assert _snapshot(uri) == before, 'dry-run 不得写库'

    # ── 2) 首次 --apply ─────────────────────────────────────────
    first = _run_subprocess(_SEED, uri, '--apply')
    assert first.returncode == 0, first.stdout + first.stderr
    assert '新建分类 6 个、更新标签 61 行' in first.stdout
    after_first = _snapshot(uri)
    _assert_seed_result(uri)

    # 只改 category_id：其它列（含 updated_at / deleted / deleted_at）逐行不变
    before_tags = {t['id']: t for t in before['tags']}
    for tag in after_first['tags']:
        original = before_tags[tag['id']]
        changed = {k for k in tag if tag[k] != original[k]}
        assert changed <= {'category_id'}, \
            f"标签 {tag['id']}（{tag['name']}）被改了非 category_id 字段: {changed}"

    # 软删分类行逐行不变（含与目标同名的「打断」软删行，未复活未改写）
    soft_deleted_before = [c for c in before['categories'] if c['deleted']]
    soft_deleted_after = [c for c in after_first['categories'] if c['deleted']]
    assert soft_deleted_after == soft_deleted_before
    same_name = [c for c in soft_deleted_after if c['name'] == _SOFT_DELETED_SAME_NAME]
    assert len(same_name) == 1

    # 软删标签逐行不变
    soft_tags_before = [t for t in before['tags'] if t['deleted']]
    soft_tags_after = [t for t in after_first['tags'] if t['deleted']]
    assert soft_tags_after == soft_tags_before

    # ── 3) 重跑 --apply：0 变更、快照完全一致（幂等） ─────────────
    second = _run_subprocess(_SEED, uri, '--apply')
    assert second.returncode == 0, second.stdout + second.stderr
    assert '新建分类 0 个、更新标签 0 行' in second.stdout
    assert _snapshot(uri) == after_first, '重跑不得产生任何变更'
    _assert_seed_result(uri)

    # ── 4) 标签 CRUD 回读（独立进程连隔离库） ────────────────────
    probe = _run_subprocess(_PROBE, uri)
    assert probe.returncode == 0, probe.stdout + probe.stderr
    summary = json.loads(probe.stdout.strip().splitlines()[-1])
    assert summary['ok'] is True
    assert summary['by_category_before'] == {
        '人工录制': 1, '打断': 12, '拒识': 32, '接管': 9,
        '恢复前文': 4, '环境理解': 3, '未分类': 27}
