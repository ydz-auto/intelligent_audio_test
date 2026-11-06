# -*- coding: utf-8 -*-
"""INT-2292：维度种子脚本 `_upsert_relation` 按唯一键全量判，禁止复活最早软删行。

背景：`uq_algorithm_dimension` 在 `algorithm_service` 模型里是
`WHERE deleted = false` 的部分唯一索引。旧实现只 `SELECT id, deleted ...` 无过滤、
无排序取 `fetchone()`（物理顺序=最早那行），同键堆积多行软删历史时会把最早软删行
改成 `deleted = FALSE`，与当前生效行撞索引，整条 db_bootstrap 引导链 exit 1。

本文件钉死三件事（不连库，用假 conn 记录 SQL）：
1. 有生效行 → 只 SELECT 一次即返回，不发任何 UPDATE（绝不复活软删行）；
2. 无生效行 → 复活 id 最新的一条，且复活前先把同键其余生效行置软删（防撞索引）；
3. 无任何行 → 直接 INSERT；
4. 前面两条策略对引导链里全部带 `_upsert_relation` 的种子脚本一致（兄弟函数同步修）。
"""
import importlib.util
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 种子脚本模块 import 期会校验/读取配置（不触网），与其它单测同口径先序兜底。
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('DATABASE_URL', 'postgresql://u:p@localhost:1/unused')
os.environ.setdefault('DATABASE_URI', 'postgresql://u:p@localhost:1/unused')

# 引导链 BOOTSTRAP_STEPS 内全部带 _upsert_relation 的种子脚本
SEED_FILES = [
    'scripts/migrations/202609/seed_env_sound_judge.py',
    'scripts/migrations/202609/seed_interruption_dimensions.py',
    'scripts/migrations/202609/seed_reject_judge.py',
    'scripts/migrations/202609/seed_xiaoyi_dimensions.py',
    'scripts/migrations/202610/seed_env_judge.py',
    'scripts/migrations/202610/seed_interruption_v2.py',
    'scripts/migrations/202610/seed_turn_eval.py',
]

DIM_ID = 72


def _load(path):
    name = 'int2292_' + os.path.basename(path)[:-3]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeConn:
    """按 SQL 形态返回预设行，并记录全部 (sql, params)。"""

    def __init__(self, active_row=None, revive_row=None):
        self.active_row = active_row
        self.revive_row = revive_row
        self.calls = []

    def execute(self, stmt, params=None):
        sql = str(stmt)
        self.calls.append((sql, dict(params or {})))
        low = sql.lower()
        if low.startswith('update') or low.startswith('insert'):
            return _FakeResult(None)
        if 'deleted = false order by id desc limit 1' in low:
            return _FakeResult(self.active_row)
        if 'deleted = true order by id desc limit 1' in low:
            return _FakeResult(self.revive_row)
        return _FakeResult(None)


def _call_upsert(module, conn, dim_id=DIM_ID):
    """兼容 2 参 / 3 参（带 dim_name）两种兄弟签名。"""
    import inspect
    sig = inspect.signature(module._upsert_relation)
    if len(sig.parameters) >= 3:
        return module._upsert_relation(conn, dim_id, '会话时延')
    return module._upsert_relation(conn, dim_id)


def _selects(conn):
    return [c for c in conn.calls if c[0].lower().lstrip().startswith('select')]


def test_active_row_is_reused_without_revive(tmp_path):
    """键上已有生效行（551/552 场景）→ 只查生效行并复用，不发 UPDATE。"""
    for rel in SEED_FILES:
        module = _load(os.path.join(PROJECT_ROOT, rel))
        conn = _FakeConn(active_row=(552,), revive_row=(372,))
        _call_upsert(module, conn)
        selects = _selects(conn)
        assert len(selects) == 1, f'{rel}: 有生效行应只查一次，实际 {len(selects)}'
        assert 'deleted = false' in selects[0][0].lower(), rel
        assert conn.calls == selects, f'{rel}: 有生效行不得发 UPDATE/INSERT'


def test_revive_latest_soft_deleted_row_and_demote_others():
    """无生效行（314 类）→ 复活最新一条，并显式把同键其它行置软删。"""
    for rel in SEED_FILES:
        module = _load(os.path.join(PROJECT_ROOT, rel))
        conn = _FakeConn(active_row=None, revive_row=(551,))
        _call_upsert(module, conn)

        selects = _selects(conn)
        assert len(selects) == 2, f'{rel}: 应先查生效行再查软删行'
        assert 'deleted = false' in selects[0][0].lower(), rel
        assert 'deleted = true' in selects[1][0].lower(), rel
        assert 'order by id desc' in selects[1][0].lower(), (
            f'{rel}: 复活选行必须按 id 倒序取最新一条')

        updates = [c for c in conn.calls if c[0].lower().lstrip().startswith('update')]
        assert len(updates) == 2, f'{rel}: 期望「置软删同键其它行 + 复活」两条 UPDATE'
        demote_sql, demote_params = updates[0]
        assert 'deleted = true' in demote_sql.lower(), rel
        assert 'id <> :id' in demote_sql.lower(), rel
        assert demote_params.get('id') == 551, rel
        revive_sql, revive_params = updates[1]
        assert 'id = :id' in revive_sql.lower(), rel
        assert 'deleted = false' in revive_sql.lower(), rel
        assert revive_params.get('id') == 551, rel


def test_insert_when_key_absent():
    """键上没有任何行 → 直接 INSERT（带 deleted = FALSE）。"""
    for rel in SEED_FILES:
        module = _load(os.path.join(PROJECT_ROOT, rel))
        conn = _FakeConn(active_row=None, revive_row=None)
        _call_upsert(module, conn)

        assert len(_selects(conn)) == 2, rel
        inserts = [c for c in conn.calls if c[0].lower().lstrip().startswith('insert')]
        assert len(inserts) == 1, f'{rel}: 无行时应 INSERT 一条'
        assert 'algorithm_dimension_relations' in inserts[0][0], rel
        assert inserts[0][1].get('did') == DIM_ID, rel
