# -*- coding: utf-8 -*-
"""INT-1623：transfer_agent 两表建表迁移（㊵）+ 模型全集收口 静态守卫。

背景（本卡缺陷，两件事叠加）：
1. `scripts/create_all_tables.py::_import_all_models()` 漏导 transfer_agent 的
   PO（TransferRecord / TransferChunk）—— 它声称注册 87 张表，实际只注册 86 张；
   `tests/data/schema_baseline.json` 也按这份不完整的元数据采集（86 张）。
   真实库有这两张表，是 transfer_agent 启动时自己 create_all 的次生路径。
2. INT-1565 守卫读进程级全局 `Base.metadata`：任一测试 import 了 transfer_agent
   应用层，两表就注册进来，`-n 8 --dist loadgroup` 下守卫随调度红/绿不定。

本文件把修复钉死（纯静态，不连库）：
1. 模型全集收口：`_import_all_models()` 单独就能注册 transfer 两表，且仓库里
   所有 `__tablename__` 定义的 PO 表都必须在注册集合内 —— 从此元数据不再随
   测试调度漂移（新增服务 / 新 PO 漏登记直接红）；
2. 建表迁移 DDL 的列集合 / 类型 / 可空性 / server_default、索引名与唯一性、
   唯一约束名必须与 ORM 元数据逐项对齐（避免形成第二份真相）；
3. DDL 幂等（CREATE TABLE/INDEX IF NOT EXISTS + 约束存在即 SKIP），引导链
   每次部署都会跑；
4. docker/db_bootstrap_entrypoint.py 的 BOOTSTRAP_STEPS 必须包含该步；
5. 两表已登记进基线快照（快照漏收的存量表，不是本批新增列 —— 登记不算绕过）。

DB：无（模型元数据 + 迁移文本 + 引导链常量）。
"""
import importlib.util
import json
import os
import re

import pytest
from sqlalchemy import Column, Integer, String

# 导入 PO 需要 BaseConfig（OSS 凭据 / DATABASE_URL 仅 import 期校验非空，本守卫不连库）
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('DATABASE_URL', 'postgresql://u:p@localhost:1/unused')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
_MIGRATION_REL = ('scripts/migrations/202610/'
                  'add_transfer_agent_tables_int1623.py')
_MIGRATION = os.path.join(PROJECT_ROOT, *_MIGRATION_REL.split('/'))
_BOOTSTRAP_PATH = os.path.join(PROJECT_ROOT, 'docker',
                               'db_bootstrap_entrypoint.py')
_BASELINE_PATH = os.path.join(PROJECT_ROOT, 'tests', 'data',
                              'schema_baseline.json')
_CREATE_ALL_PATH = os.path.join(PROJECT_ROOT, 'scripts', 'create_all_tables.py')
_TABLES = ('transfer_records', 'transfer_chunks')

# 扫描 PO 定义时跳过的目录（测试自身、虚拟环境、运行时产物）
_SKIP_DIRS = {'.git', 'node_modules', '__pycache__', '.claude', '.multica',
              'tests', '.idea', '.pytest_cache'}

# SQLAlchemy 泛型类型 → DDL 类型别名
_TYPE_ALIASES = {'DATETIME': 'TIMESTAMP', 'SERIAL': 'INTEGER'}


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def create_all():
    return _load_module(_CREATE_ALL_PATH, 'int1623_create_all_tables')


@pytest.fixture(scope='module')
def metadata(create_all):
    create_all._import_all_models()
    from shared.models.database import Base
    return Base.metadata


@pytest.fixture(scope='module')
def migration():
    assert os.path.isfile(_MIGRATION), f'建表迁移缺失：{_MIGRATION_REL}'
    return _load_module(_MIGRATION, 'int1623_transfer_migration')


@pytest.fixture(scope='module')
def orm_tables(metadata):
    return {name: metadata.tables[name] for name in _TABLES}


def _ddl_columns(sql):
    """从 CREATE TABLE 文本取 {列名: 列定义尾部}（四空格缩进单行列）。"""
    body = sql[sql.index('(') + 1:sql.rindex(')')]
    columns = {}
    for raw in body.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.upper().startswith(
                ('CONSTRAINT', 'PRIMARY KEY', 'UNIQUE')):
            continue
        match = re.match(r'^([a-z_][a-z0-9_]*)\s+(.+?),?$', stripped)
        assert match, f'无法解析的 DDL 行：{raw!r}'
        columns[match.group(1)] = match.group(2).rstrip(',')
    return columns


def _ddl_type(ddl):
    return re.match(r'^([A-Za-z]+(?:\(\d+\))?)', ddl).group(1)


def _norm_type(type_name):
    base = type_name.upper()
    return _TYPE_ALIASES.get(base, base)


def _repo_tablenames():
    """静态扫描仓库内所有 PO 的 `__tablename__ = '...'` 定义。"""
    names = set()
    for dirpath, dirnames, filenames in os.walk(PROJECT_ROOT):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for filename in filenames:
            if not filename.endswith('.py'):
                continue
            path = os.path.join(dirpath, filename)
            with open(path, encoding='utf-8', errors='replace') as f:
                text = f.read()
            names.update(re.findall(
                r'__tablename__\s*=\s*[\'"]([A-Za-z_][A-Za-z0-9_]*)[\'"]',
                text))
    return names


class TestModelRegistryIsComplete:
    """根因 1：模型全集必须唯一确定，不随测试导入顺序 / 调度漂移。"""

    def test_create_all_registers_transfer_tables(self, create_all, metadata):
        assert set(_TABLES) <= set(metadata.tables), (
            'create_all_tables._import_all_models() 未注册 transfer_agent 两表：'
            '模型全集随测试调度漂移，INT-1565 守卫 -n 8 随机红（INT-1623）')

    def test_registered_table_count_matches_expected(self, create_all):
        po_tables = _repo_tablenames()
        assert len(po_tables) == create_all.EXPECTED_TABLE_COUNT, (
            f'仓库 PO 表 {len(po_tables)} 张与 EXPECTED_TABLE_COUNT='
            f'{create_all.EXPECTED_TABLE_COUNT} 不一致：新增表须同步登记导入清单')

    def test_every_po_table_in_repo_is_registered(self, metadata):
        orphans = sorted(_repo_tablenames() - set(metadata.tables))
        assert not orphans, (
            f'以下 PO 表未在 create_all_tables._import_all_models() 注册：'
            f'{orphans} —— 漏导即模型全集不唯一（INT-1623 根因），请补导入')

    def test_test_local_po_pollution_does_not_affect_guard(self):
        """根因②锚点：测试自建 PO 注册进全局 metadata 后，守卫判定不受影响。"""
        from shared.models.database import Base
        from tests.unit.test_int1565_schema_migration_guard import (
            _registered_po_tables,
        )

        class _PollutionProbe(Base):
            __tablename__ = 'int1623_pollution_probe'
            id = Column(Integer, primary_key=True)
            probe_only_column = Column(String(12))

        try:
            assert 'int1623_pollution_probe' in Base.metadata.tables
            assert 'int1623_pollution_probe' not in _registered_po_tables(), (
                '测试自建 PO 进入了守卫的判定集合：-n 8 调度到同一 worker 时守卫'
                '会对 probe_only_column 报缺迁移（INT-1623 根因②）')
        finally:
            Base.metadata.remove(_PollutionProbe.__table__)


class TestTransferTablesMigrationDDL:
    """根因 2：存量库补建表迁移，DDL 必须与 ORM 逐项对齐。"""

    def test_ddl_tables_match_constant(self, migration):
        assert [table for table, _sql in migration.CREATE_TABLES] == list(_TABLES)

    def test_ddl_columns_match_orm(self, migration, orm_tables):
        for table, sql in migration.CREATE_TABLES:
            orm_table = orm_tables[table]
            columns = _ddl_columns(sql)
            assert set(columns) == {c.name for c in orm_table.columns}, (
                f'{table} 建表迁移列集合与 ORM 不一致')
            for column in orm_table.columns:
                ddl = columns[column.name]
                ddl_type = _norm_type(_ddl_type(ddl))
                orm_type = _norm_type(str(column.type))
                assert ddl_type == orm_type, (
                    f'{table}.{column.name} 类型不一致：DDL={ddl_type} '
                    f'ORM={orm_type}')
                ddl_not_null = 'NOT NULL' in ddl or 'PRIMARY KEY' in ddl
                assert ddl_not_null == (not column.nullable), (
                    f'{table}.{column.name} 可空性与 ORM 不一致：DDL={ddl!r} '
                    f'ORM nullable={column.nullable}')
                ddl_has_default = 'DEFAULT' in ddl
                assert ddl_has_default == (column.server_default is not None), (
                    f'{table}.{column.name} server_default 与 ORM 不一致：'
                    f'DDL={ddl!r}')

    def test_ddl_indexes_match_orm(self, migration, orm_tables):
        for table, orm_table in orm_tables.items():
            orm_indexes = {(i.name, i.unique) for i in orm_table.indexes}
            ddl_indexes = {(name, unique) for name, ddl_table, _col, unique
                           in migration.INDEXES if ddl_table == table}
            assert ddl_indexes == orm_indexes, (
                f'{table} 建表迁移索引名 / 唯一性与 ORM 不一致：'
                f'DDL={ddl_indexes} ORM={orm_indexes}')

    def test_unique_constraints_match_orm(self, migration, orm_tables):
        from sqlalchemy import UniqueConstraint

        for table, orm_table in orm_tables.items():
            orm_uq = {(c.name, tuple(col.name for col in c.columns))
                      for c in orm_table.constraints
                      if isinstance(c, UniqueConstraint)}
            ddl_uq = {(name, tuple(col.strip() for col in cols.split(',')))
                      for name, ddl_table, cols in migration.UNIQUE_CONSTRAINTS
                      if ddl_table == table}
            assert ddl_uq == orm_uq, (
                f'{table} 唯一约束与 ORM 不一致：DDL={ddl_uq} ORM={orm_uq}')

    def test_ddl_is_idempotent(self, migration):
        for table, sql in migration.CREATE_TABLES:
            assert f'CREATE TABLE IF NOT EXISTS {table}' in sql
        for index_name, table, col_name, unique in migration.INDEXES:
            idx_sql = migration._index_sql(index_name, table, col_name, unique)
            assert 'IF NOT EXISTS' in idx_sql, idx_sql
            assert ('UNIQUE INDEX' in idx_sql) == unique, idx_sql
        with open(_MIGRATION, encoding='utf-8') as f:
            text = f.read()
        # 约束兜底须先查存在性，存量表（transfer_agent 自建）重复部署不报错
        assert '_constraint_exists' in text
        # 引导链不带 --dry-run 执行，脚本必须默认执行且幂等
        assert "add_argument('--dry-run'" in text


class TestDeployChainAndBaseline:
    def test_bootstrap_steps_include_transfer_tables_migration(self):
        steps = [list(step) for step in
                 _load_module(_BOOTSTRAP_PATH,
                              'int1623_db_bootstrap').BOOTSTRAP_STEPS]
        assert any(_MIGRATION_REL in step for step in steps), (
            f'BOOTSTRAP_STEPS 未包含 {_MIGRATION_REL}：建库早于 transfer_agent '
            '模块的存量库不会建这两张表（INT-1623）')

    def test_baseline_registers_transfer_tables(self, orm_tables):
        """两表早于基线快照（快照按不完整元数据采集而漏收），登记后快照才完整。

        基线是存量库快照而非「当前 ORM」镜像：只要求快照列都在 ORM 里（不会
        记进不存在的列），后续新增列照旧由守卫要求迁移、不得回填基线。
        """
        with open(_BASELINE_PATH, encoding='utf-8') as f:
            baseline = json.load(f)
        for table in _TABLES:
            assert table in baseline, f'基线快照漏登记 {table}（INT-1623）'
            registered = set(baseline[table])
            assert registered <= {c.name for c in orm_tables[table].columns}, (
                f'基线里 {table} 出现 ORM 不存在的列：'
                f'{sorted(registered - {c.name for c in orm_tables[table].columns})}')
        # 本卡缺陷报出的列必须都已进快照（否则守卫对它们继续报缺迁移）
        assert {'checksum', 'chunk_index', 'size', 'transfer_id'} <= set(
            baseline['transfer_chunks'])
        assert {'chunk_size', 'dst_zone', 'ephemeral', 'file_hash',
                'file_size', 'final_path', 'meta', 'pkg_type', 'signature',
                'src_zone', 'transfer_id', 'ttl_seconds'} <= set(
            baseline['transfer_records'])

    def test_migration_covers_all_previously_missing_columns(self, migration):
        """回归锚点：本卡缺陷报出的 16 个列名必须都在建表 DDL 里出现。"""
        blob = '\n'.join(sql for _table, sql in migration.CREATE_TABLES)
        reported = [
            'transfer_chunks.checksum', 'transfer_chunks.chunk_index',
            'transfer_chunks.size', 'transfer_chunks.transfer_id',
            'transfer_records.chunk_size', 'transfer_records.dst_zone',
            'transfer_records.ephemeral', 'transfer_records.file_hash',
            'transfer_records.file_size', 'transfer_records.final_path',
            'transfer_records.meta', 'transfer_records.pkg_type',
            'transfer_records.signature', 'transfer_records.src_zone',
            'transfer_records.transfer_id', 'transfer_records.ttl_seconds',
        ]
        for qualified in reported:
            column = qualified.split('.', 1)[1]
            assert re.search(r'(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])'
                             % re.escape(column), blob), (
                f'{qualified} 未在建表迁移 DDL 出现')
