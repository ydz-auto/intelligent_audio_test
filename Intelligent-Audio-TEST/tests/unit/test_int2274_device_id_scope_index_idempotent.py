# -*- coding: utf-8 -*-
"""INT-2274：add_device_id_scope 迁移幂等（唯一索引按「名称 + 定义」判定）。

背景（INT-2224 参数配置域走查 P1-7 / P2）：
1. `param_mappings` 的两条旧唯一索引与新索引**同名**，迁移却把它们列进
   `old_indexes` 且无条件 append CREATE，导致迁移完成后的每次部署都
   DROP + CREATE 唯一索引（ACCESS EXCLUSIVE 锁），`if not statements` 的空转
   分支永不触发；
2. 迁移里的索引带 `NULLS NOT DISTINCT`，而 ORM 模型没声明，全新库
   （create_all_tables 先建）按模型建出的同名索引弱于存量库，`_index_exists`
   命中即 SKIP。

本文件（不连库）钉死：
- 迁移后状态再跑 `_forward_statements` 返回空 → `_run` 打 `[SKIP]`，无 DROP/CREATE；
- 旧两级定义 / 缺 NULLS NOT DISTINCT / 列序或谓词不符 → 才 DROP 后重建；
- ORM 五条唯一索引都声明 `postgresql_nulls_not_distinct=True`（全新库口径一致）；
- 引导链仍以 `--apply` 排在 ANALYZE 之前。
"""
import importlib.util
import os
import sys

os.environ.setdefault('DATABASE_URL', 'postgresql://u:p@localhost:1/unused')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
_MIGRATION = os.path.join(
    PROJECT_ROOT, 'scripts', 'migrations', '202611', 'add_device_id_scope.py')
_BOOTSTRAP_PATH = os.path.join(PROJECT_ROOT, 'docker',
                               'db_bootstrap_entrypoint.py')


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_migration = _load(_MIGRATION, 'int2274_add_device_id_scope')

DEVICE_TABLE = 'algorithm_device_params'
MAPPING_TABLE = 'param_mappings'
SIMPLE_INDEXES = ('idx_algorithm_device_params_device_id',
                  'idx_param_mappings_device_id')
OLD_DEVICE_UNIQUE = 'uq_algorithm_device_param_direction'


def _spec(name):
    return next(item for item in _migration.UNIQUE_INDEX_SPECS
                if item['name'] == name)


def _definition(table, spec, columns, predicate, nulls_not_distinct=True):
    return ('CREATE UNIQUE INDEX %s ON public.%s USING btree (%s) %sWHERE %s'
            % (spec['name'], table, ', '.join(columns),
               'NULLS NOT DISTINCT ' if nulls_not_distinct else '', predicate))


def _state(table, spec, columns=None, predicate=None,
           nulls_not_distinct=True, unique=True):
    """造一条 pg_index 现状：默认与目标定义一致。"""
    cols = list(columns or spec['columns'])
    pred = predicate if predicate is not None else spec['where']
    return {
        'unique': unique,
        'nulls_not_distinct': nulls_not_distinct,
        'columns': cols,
        'predicate': pred,
        # 仅用于 [INFO] 打印，不参与匹配
        'definition': _definition(table, spec, cols, pred, nulls_not_distinct),
    }


def _migrated_indexes():
    """迁移完成后的索引现状：五条唯一索引都已是目标定义。"""
    return {spec['name']: _state(spec['table'], spec)
            for spec in _migration.UNIQUE_INDEX_SPECS}


class _FakeCursor:
    """按 SQL 形态应答 _forward_statements 的只读查询。"""

    def __init__(self, indexes, columns=None):
        self.indexes = indexes
        self.columns = set(columns or (
            ('algorithm_device_params', 'device_id'),
            ('param_mappings', 'device_id'),
            ('param_profiles', 'config_snapshot'),
        ))
        self._row = None

    def execute(self, sql, params=None):
        low = ' '.join(sql.split()).lower()
        params = params or ()
        self._row = None
        if 'information_schema.columns' in low:
            self._row = (('boolean', 'YES')
                         if tuple(params) in self.columns else None)
            return
        if 'from pg_indexes' in low:
            self._row = (1,) if params[0] in self.indexes or (
                params[0] in SIMPLE_INDEXES) else None
            return
        if 'from pg_index' in low:
            state = self.indexes.get(params[0])
            if state is not None:
                self._row = (state['unique'], state['nulls_not_distinct'],
                             state['predicate'], state['definition'],
                             state['columns'])
            return
        raise AssertionError('未预期的 SQL: %s' % sql)

    def fetchone(self):
        return self._row


def _sqls(indexes, columns=None):
    return _migration._forward_statements(_FakeCursor(indexes, columns))


# ---------------------------------------------------------------- 幂等

def test_migrated_schema_produces_no_statements():
    """验收 1：迁移完成后再跑不发任何 DROP/CREATE（_run 走 [SKIP]）。"""
    assert _sqls(_migrated_indexes()) == []


def test_old_two_level_mapping_indexes_rebuilt_then_noop():
    """旧两份同名索引（无 device_id 条件）只重建一次，第二遍为空转。"""
    indexes = _migrated_indexes()
    # api_id 迁移留下的旧定义：谓词没有 device_id，且 api 级仍按旧口径
    indexes['uq_param_mapping_algo_level'] = _state(
        MAPPING_TABLE, _spec('uq_param_mapping_algo_level'),
        predicate='(deleted = false) AND (api_id IS NULL)')
    indexes['uq_param_mapping_api_level'] = _state(
        MAPPING_TABLE, _spec('uq_param_mapping_api_level'),
        predicate='(deleted = false) AND (api_id IS NOT NULL)')
    indexes.pop('uq_param_mapping_device_level')
    indexes[OLD_DEVICE_UNIQUE] = _state(
        DEVICE_TABLE, _spec('uq_algorithm_device_param_algo_level'),
        columns=['algorithm_type', 'param_code', 'direction'],
        predicate='deleted = false', nulls_not_distinct=False)

    stmts = _sqls(indexes)
    # 设备参数旧唯一索引先下线
    assert 'DROP INDEX IF EXISTS %s' % OLD_DEVICE_UNIQUE in stmts
    # 两条同名映射索引：DROP 在前、CREATE 紧随
    for name in ('uq_param_mapping_algo_level', 'uq_param_mapping_api_level'):
        drop = stmts.index('DROP INDEX IF EXISTS %s' % name)
        assert stmts[drop + 1].startswith(
            'CREATE UNIQUE INDEX IF NOT EXISTS %s ' % name)
    # 缺失的设备级索引直接创建（不 DROP）
    assert any(s.startswith(
        'CREATE UNIQUE INDEX IF NOT EXISTS uq_param_mapping_device_level ')
        for s in stmts)
    assert 'DROP INDEX IF EXISTS uq_param_mapping_device_level' not in stmts
    # 其余两条设备参数索引已一致，不重建
    assert not any('DROP INDEX IF EXISTS uq_algorithm_device_param_algo_level'
                   in s for s in stmts)

    # 执行后（状态替换为目标定义）第二遍必须空转
    assert _sqls(_migrated_indexes()) == []


def test_index_missing_nulls_not_distinct_is_rebuilt():
    """验收 2：同名同列同谓词但缺 NULLS NOT DISTINCT（全新库按旧模型建的）也重建。"""
    indexes = _migrated_indexes()
    for spec in _migration.UNIQUE_INDEX_SPECS:
        indexes[spec['name']] = _state(
            spec['table'], spec, nulls_not_distinct=False)

    stmts = _sqls(indexes)
    drops = [s for s in stmts if s.startswith('DROP INDEX IF EXISTS')]
    creates = [s for s in stmts if s.startswith('CREATE UNIQUE INDEX')]
    assert len(drops) == len(_migration.UNIQUE_INDEX_SPECS)
    assert len(creates) == len(_migration.UNIQUE_INDEX_SPECS)
    assert all('NULLS NOT DISTINCT' in s for s in creates)


def test_wrong_column_order_is_rebuilt():
    """列序/列集不符同样重建（防「同名但定义漂移」被误判为已迁移）。"""
    indexes = _migrated_indexes()
    spec = _spec('uq_param_mapping_device_level')
    indexes[spec['name']] = _state(
        MAPPING_TABLE, spec,
        columns=['device_id', 'algorithm_type', 'source', 'source_param',
                 'dimension_id'])
    stmts = _sqls(indexes)
    assert 'DROP INDEX IF EXISTS %s' % spec['name'] in stmts
    assert any(s.startswith('CREATE UNIQUE INDEX IF NOT EXISTS %s ' % spec['name'])
               for s in stmts)


# ------------------------------------------------------- ORM（全新库口径）

def test_orm_unique_indexes_declare_nulls_not_distinct():
    """P2：ORM 五条唯一索引必须与迁移同口径，否则全新库弱于存量库。"""
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateIndex

    from algorithm_service.infrastructure.persistence.models import (
        algorithm_models,
    )

    tables = {
        DEVICE_TABLE: algorithm_models.AlgorithmDeviceParam.__table__,
        MAPPING_TABLE: algorithm_models.ParamMapping.__table__,
    }
    compiled = {}
    for table in tables.values():
        for index in table.indexes:
            compiled[index.name] = str(
                CreateIndex(index).compile(dialect=postgresql.dialect()))

    for spec in _migration.UNIQUE_INDEX_SPECS:
        ddl = compiled[spec['name']]
        assert 'NULLS NOT DISTINCT' in ddl, ddl
        # 谓词与迁移目标一致（归一化后逐字相等）
        where = ddl.split(' WHERE ', 1)[1]
        assert _migration._normalize_sql(where) == \
            _migration._normalize_sql(spec['where']), ddl


def test_bootstrap_runs_migration_with_apply_before_analyze():
    """引导链仍按 ㊾ 注册且带 --apply（幂等判定在链里才生效）。"""
    with open(_BOOTSTRAP_PATH, encoding='utf-8') as fh:
        source = fh.read()
    entry = ("('python', 'scripts/migrations/202611/add_device_id_scope.py', "
             "'--apply')")
    assert entry in source
    assert source.index(entry) < source.index('analyze_stale_statistics_int1741')
