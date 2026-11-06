# -*- coding: utf-8 -*-
"""INT-2293：引导链种子代际互踩 —— Step 0 只迁移旧代、代际收敛、关联复活。

背景（卡内现象）：引导链每次按 202609 → 202610 顺序全跑，而两代对同一
task_type_code 的处置互斥，导致每跑一遍 db_bootstrap 就软删并重建 18 个维度
（env_judge 3 + interruption_metrics 15），dimension id 每代都变：
  1. `202609/seed_env_sound_judge.py` Step 0 按 legacy code 一把抓，把
     `202610/seed_env_judge.py` 的 env_judge 新代三维度当旧代软删；
  2. `202609/seed_interruption_dimensions.py` Step 0 `name != '打断成功率'` 一把抓，
     软删的正是 `202610/seed_interruption_v2.py` 的现行 15 个维度；
  3. 202609 建「打断成功率」树、202610 又物理删除它（连 test_result_dimensions 行），
     两端对冲。

本文件钉死四件事（不连库，用假 conn 记录 SQL）：
1. env_judge：新代主维度存在 → Step 0 整段跳过、不动任何行；
2. env_judge：只有旧代 → 迁移；冲突软删时级联到 params / mappings / relations
   （不留「生效关联指向软删维度」的悬空行）；
3. interruption：Step 0 只按旧代 name 集合判定，绝不软删 v2 维度；且本脚本不再
   创建「打断成功率」树（引导链不再一建一删）；
4. 4 个仅按「任意行存在」判关联的种子改为 INT-2292 的 upsert 判据
   （有生效行复用 / 无则复活最新一条 / 无行才 INSERT）。
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

ENV_SOUND_JUDGE = 'scripts/migrations/202609/seed_env_sound_judge.py'
INTERRUPTION_SEED = 'scripts/migrations/202609/seed_interruption_dimensions.py'

# 卡内要求的 4 处「关联写入不过滤软删」
RELATION_SEED_FILES = [
    'scripts/migrations/202609/seed_voice_llm.py',
    'scripts/migrations/202609/seed_llm_judge_dimension.py',
    'scripts/migrations/202609/seed_noise_latency.py',
    'scripts/migrations/202609/seed_non_interactive_latency.py',
]

DIM_ID = 433


def _load(path):
    name = 'int2293_' + os.path.basename(path)[:-3]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeResult:
    def __init__(self, rows=None, row=None):
        self._rows = list(rows or [])
        self._row = row

    def fetchone(self):
        if self._row is not None:
            return self._row
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows

    def scalar(self):
        row = self.fetchone()
        return row[0] if row else None

    @property
    def rowcount(self):
        return len(self._rows)


class _FakeConn:
    """按 SQL 形态返回预设行，并记录全部 (sql, params)。"""

    def __init__(self, new_gen=(), legacy=(), conflict=None, subs=()):
        self.new_gen = list(new_gen)
        self.legacy = list(legacy)
        self.conflict = conflict
        self.subs = list(subs)
        self.active_rel = None
        self.revive_rel = None
        self.calls = []

    def execute(self, stmt, params=None):
        sql = str(stmt)
        self.calls.append((sql, dict(params or {})))
        low = sql.lower()
        if low.lstrip().startswith(('update', 'insert', 'delete')):
            return _FakeResult(row=None)
        if 'task_type_code in (' in low and 'name in (' in low:
            return _FakeResult(rows=self.new_gen)          # 新代探测
        if 'task_type_code = :oc' in low:
            return _FakeResult(rows=self.legacy)           # 旧代行
        if 'id <> :rid' in low:
            return _FakeResult(row=self.conflict)          # 与现行维度冲突
        if 'parent_dimension_id = :pid' in low:
            return _FakeResult(rows=self.subs)             # 子维度级联
        if 'deleted = false order by id desc limit 1' in low:
            return _FakeResult(row=self.active_rel)
        if 'deleted = true order by id desc limit 1' in low:
            return _FakeResult(row=self.revive_rel)
        return _FakeResult()

    # ---- 断言辅助 ----
    def statements(self, kind):
        return [c for c in self.calls if c[0].lower().lstrip().startswith(kind)]

    def touching(self, table):
        return [c for c in self.calls if table in c[0]]


class _FakeEngine:
    def __init__(self, conn):
        self._conn = conn

    def begin(self):
        conn = self._conn

        class _Ctx:
            def __enter__(self):
                return conn

            def __exit__(self, *exc):
                return False

        return _Ctx()


# ============================================================
# 1+2. env_judge Step 0：新代存在 → 跳过；只有旧代 → 迁移并级联软删
# ============================================================

def test_env_judge_step0_skips_when_new_generation_exists():
    """新代（202610 三个主维度）存在 → Step 0 一行不动。"""
    module = _load(os.path.join(PROJECT_ROOT, ENV_SOUND_JUDGE))
    conn = _FakeConn(
        new_gen=[(433, '环境理解准确率'), (434, '平均回复时延'), (435, '环境理解评分')],
        legacy=[(409, '环境理解准确率')],   # 若误按 code 一把抓，这行会被软删
    )
    handled = module._migrate_legacy_codes(conn, 'rejection_judge', ['env_judge', 'env_sound_judge'])

    assert handled == 0
    assert not conn.statements('update'), f'新代存在时不得发任何 UPDATE: {conn.calls}'
    assert not conn.statements('delete')
    # 只允许一次「新代探测」SELECT
    assert len(conn.statements('select')) == 1


def test_env_judge_step0_migrates_legacy_and_cascades_soft_delete():
    """只有旧代 → 与现行 rejection_judge 冲突时整棵树软删（含 params/mappings/relations）。"""
    module = _load(os.path.join(PROJECT_ROOT, ENV_SOUND_JUDGE))
    conn = _FakeConn(new_gen=[], legacy=[(409, '环境理解')], conflict=(133,))
    handled = module._migrate_legacy_codes(conn, 'rejection_judge', ['env_judge'])

    assert handled == 1
    env_updates = [c for c in conn.statements('update')
                   if 'from dimensions' not in c[0] and ' dimensions ' in c[0]]
    assert env_updates, '旧的 env_judge 行应被软删'
    assert any("deleted = true" in c[0].lower() for c in env_updates)
    # 级联：params / mappings / relations 同步软删（INT-2293 要求 5）
    for table in ('evaluation_dimension_params', 'param_mappings', 'algorithm_dimension_relations'):
        rows = [c for c in conn.statements('update') if table in c[0]]
        assert rows, f'{table} 未被级联软删，会留下悬空关联'
        assert 'deleted = true' in rows[0][0].lower()


def test_env_judge_step0_renames_when_no_conflict():
    """旧代存在且无冲突 → 改名 task_type_code（保留历史行的 id）。"""
    module = _load(os.path.join(PROJECT_ROOT, ENV_SOUND_JUDGE))
    conn = _FakeConn(new_gen=[], legacy=[(77, '环境理解')], conflict=None)
    handled = module._migrate_legacy_codes(conn, 'rejection_judge', ['env_judge'])

    assert handled == 1
    rename = [c for c in conn.statements('update') if 'task_type_code = :nc' in c[0]]
    assert len(rename) == 1
    assert rename[0][1]['rid'] == 77
    assert not [c for c in conn.statements('update') if 'deleted = true' in c[0].lower()]


# ============================================================
# 3. interruption Step 0：只认旧代 name 集合；且不再创建「打断成功率」树
# ============================================================

def test_interruption_step0_filters_by_legacy_name_set():
    """Step 0 必须按旧代 name 集合判定，不得出现「name != '打断成功率'」式一把抓。"""
    module = _load(os.path.join(PROJECT_ROOT, INTERRUPTION_SEED))
    conn = _FakeConn(legacy=[])
    module._cleanup_legacy_main_dims(conn)

    selects = conn.statements('select')
    assert len(selects) == 1
    sql, params = selects[0]
    low = sql.lower()
    assert 'name in (' in low, sql
    assert '!=' not in sql and '<>' not in sql, f'不得用 name != 判旧代: {sql}'
    bound = {v for k, v in params.items() if k.startswith('n')}
    assert set(module.LEGACY_MAIN_NAMES) == bound
    # v2 现行维度名一个都不能进旧代集合
    for name in ('打断成功数量', '打断时延', '打断回复内容评分'):
        assert name not in bound


def test_interruption_seed_no_longer_creates_success_rate_tree(monkeypatch):
    """引导链里本脚本只做旧代清理，不再 INSERT/UPDATE 任何维度（否则与 v2 一建一删）。"""
    module = _load(os.path.join(PROJECT_ROOT, INTERRUPTION_SEED))
    conn = _FakeConn(legacy=[])
    monkeypatch.setattr(module, 'create_engine', lambda uri: _FakeEngine(conn))

    module.seed_interruption_dimensions()

    assert not conn.statements('insert'), f'不应再插入维度: {conn.calls}'
    assert not conn.statements('update'), f'无旧代行时不应有任何 UPDATE: {conn.calls}'


# ============================================================
# 4. 4 处关联 upsert：有生效行复用 / 无则复活最新 / 无行才 INSERT
# ============================================================

def test_relation_reused_when_active_row_exists():
    for rel in RELATION_SEED_FILES:
        module = _load(os.path.join(PROJECT_ROOT, rel))
        conn = _FakeConn()
        conn.active_rel = (552,)
        conn.revive_rel = (372,)
        assert module._upsert_relation(conn, DIM_ID) == 'active', rel
        selects = conn.statements('select')
        assert len(selects) == 1, f'{rel}: 有生效行应只查一次'
        assert 'deleted = false' in selects[0][0].lower(), rel
        assert conn.calls == selects, f'{rel}: 有生效行不得发 UPDATE/INSERT'


def test_relation_revives_latest_soft_deleted_row():
    for rel in RELATION_SEED_FILES:
        module = _load(os.path.join(PROJECT_ROOT, rel))
        conn = _FakeConn()
        conn.active_rel = None
        conn.revive_rel = (551,)
        assert module._upsert_relation(conn, DIM_ID) == 'revived', rel

        selects = conn.statements('select')
        assert len(selects) == 2, f'{rel}: 应先查生效行再查软删行'
        assert 'deleted = true' in selects[1][0].lower(), rel
        assert 'order by id desc' in selects[1][0].lower(), rel

        updates = conn.statements('update')
        assert len(updates) == 2, f'{rel}: 期望「置软删同键其它行 + 复活」两条 UPDATE'
        assert 'id <> :id' in updates[0][0].lower(), rel
        assert updates[0][1].get('id') == 551, rel
        assert 'deleted = false' in updates[1][0].lower(), rel


def test_relation_inserts_when_key_absent():
    for rel in RELATION_SEED_FILES:
        module = _load(os.path.join(PROJECT_ROOT, rel))
        conn = _FakeConn()
        assert module._upsert_relation(conn, DIM_ID) == 'inserted', rel
        inserts = conn.statements('insert')
        assert len(inserts) == 1, f'{rel}: 无行时应 INSERT 一条'
        assert 'algorithm_dimension_relations' in inserts[0][0], rel
        assert inserts[0][1].get('did') == DIM_ID, rel


def test_no_seed_still_queries_relation_without_deleted_filter():
    """回归防线：4 个脚本里不许再有「不看 deleted 的关联存在性判断」。"""
    for rel in RELATION_SEED_FILES:
        with open(os.path.join(PROJECT_ROOT, rel), encoding='utf-8') as fh:
            source = fh.read()
        marker = "SELECT id FROM algorithm_dimension_relations "
        idx = 0
        while True:
            idx = source.find(marker, idx)
            if idx == -1:
                break
            snippet = source[idx:idx + 260].lower()
            assert 'deleted = false' in snippet or 'deleted = true' in snippet, (
                f'{rel}: 关联 SELECT 缺 deleted 过滤 → 软删后永不复活')
            idx += len(marker)
