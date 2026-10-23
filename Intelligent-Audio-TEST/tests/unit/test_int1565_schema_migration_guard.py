# -*- coding: utf-8 -*-
"""INT-1565 守卫：ORM 持久化列与迁移清单一致 —— 模型加列必须带迁移且接上引导链。

背景（本卡缺陷）：INT-1469 在 test_cases 上新增持久化列 derived_test_type，
迁移脚本随同一提交落盘（scripts/migrations/202610/add_derived_test_type_int1469.py，
README ㊳），但：
  - create_all 只建缺失的表，**不给已存在的表补列**；
  - 该脚本没进 docker db_bootstrap 引导链，存量库（真实库 / 隔离库）永远不会
    自愈 → task_service 新镜像一重建，建用例 / 用例列表即 UndefinedColumn 400。

本守卫锁三件事（纯静态，不连库）：
1. 模型列覆盖：ORM 元数据里有、但不在基线快照
   tests/data/schema_baseline.json 的列，必须在 scripts/migrations/ 某个脚本里
   出现（新增列忘了写迁移 → 直接红）；
2. 本卡锚点：基线刻意不含 test_cases.derived_test_type，迁移脚本一旦被删 /
   改名，同一断言即红 —— 证明守卫对 INT-1469 同类漂移有效（红-绿锚点）；
3. 部署链路：docker/db_bootstrap_entrypoint.py 的 BOOTSTRAP_STEPS 必须包含该
   迁移的 --apply 步骤（只写脚本不接引导链 → 存量库仍永不补列，即本卡根因）。

基线维护：新增列请在写迁移脚本后更新 tests/data/schema_baseline.json（只登记
已有存量列的语义，不要靠改基线绕过迁移检查 —— 第 1 条只对「基线里没有的列」
要求迁移，改基线等于绕过守卫）。

INT-1623 补充：判定的模型集合取自「映射类的 __module__ 不在 tests/ 下」的真实
PO（见 _registered_po_tables）。原因：Base.metadata 是进程级全局，xdist 把不同
测试文件调度进同一 worker 时，别的测试 import 的模型 / 测试自建的临时 PO 都会
注册进来，守卫结论会随调度红绿不定。真实模型的漏导另有
tests/unit/test_int1623_transfer_tables_migration.py 的仓库 PO 扫描兜住。

DB：无（sqlite 元数据 + 迁移目录文本）。
"""
import importlib.util
import json
import os
import re

import pytest

# 导入全部 PO 需要 BaseConfig（OSS 凭据仅 import 期校验非空，本守卫不触网）
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
_MIGRATIONS_DIR = os.path.join(PROJECT_ROOT, 'scripts', 'migrations')
_BASELINE_PATH = os.path.join(PROJECT_ROOT, 'tests', 'data',
                              'schema_baseline.json')
_BOOTSTRAP_PATH = os.path.join(PROJECT_ROOT, 'docker',
                               'db_bootstrap_entrypoint.py')
_DERIVED_MIGRATION = os.path.join(
    _MIGRATIONS_DIR, '202610', 'add_derived_test_type_int1469.py')
_DERIVED_REL = 'scripts/migrations/202610/add_derived_test_type_int1469.py'


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _registered_po_tables():
    """真实模型的表集合（不含测试文件里临时定义的 PO）。

    守卫读的是进程级全局 ``Base.metadata``：``-n 8 --dist loadgroup`` 会把不同
    测试文件调度进同一 worker，别的测试 import 的模型都会注册进来。真实 PO 的
    注册是幂等的，但**测试自建的临时 PO**（如 tests/unit/
    test_int90_db_session_hygiene.py 的 int90_poison）也会注册 —— 守卫的结论
    就会随调度红/绿不定（INT-1623 根因②）。按映射类的 ``__module__`` 过滤后，
    判定只取决于真实模型。

    INT-1623 根因①（模型全集漏导）在 scripts/create_all_tables.py 收口，并由
    tests/unit/test_int1623_transfer_tables_migration.py 的仓库 PO 扫描兜住。
    """
    from shared.models.database import Base
    tables = {}
    for mapper in Base.registry.mappers:
        module = mapper.class_.__module__ or ''
        if module.startswith(('tests.', 'test_')):
            continue
        table = mapper.local_table
        tables[table.name] = table
    return tables


@pytest.fixture(scope='module')
def model_metadata():
    """导入全部服务的 PO（与 scripts/create_all_tables.py 同口径）取真实模型表。"""
    _load_module(
        os.path.join(PROJECT_ROOT, 'scripts', 'create_all_tables.py'),
        'int1565_create_all_tables')._import_all_models()
    return _registered_po_tables()


def _baseline():
    with open(_BASELINE_PATH, encoding='utf-8') as f:
        return json.load(f)


def _migration_text():
    parts = []
    for dirpath, _dirnames, filenames in os.walk(_MIGRATIONS_DIR):
        for filename in sorted(filenames):
            if filename.endswith('.py'):
                with open(os.path.join(dirpath, filename), encoding='utf-8') as f:
                    parts.append(f.read())
    return '\n'.join(parts)


def _mentions(text, name):
    """词边界匹配，避免 test_type 命中 derived_test_type 这类子串假阳性。"""
    return re.search(r'(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])'
                     % re.escape(name), text) is not None


class TestModelColumnsCoveredByMigrations:
    """模型新增持久化列必须有迁移脚本落盘（本卡缺陷的第一层）。"""

    def test_every_post_baseline_column_has_migration(self, model_metadata):
        baseline = _baseline()
        blob = _migration_text()
        missing = []
        for table_name, table in model_metadata.items():
            known = set(baseline.get(table_name, ()))
            for column in table.columns:
                if column.name in known:
                    continue
                if _mentions(blob, column.name):
                    continue
                missing.append(f'{table_name}.{column.name}')
        assert not missing, (
            '以下模型列的存量库补列迁移缺失：' + ', '.join(sorted(missing))
            + '\n请按 scripts/migrations/README.md 编号补幂等迁移脚本'
              '（ADD COLUMN IF NOT EXISTS + 回填 + 索引），并接上 '
              'docker/db_bootstrap_entrypoint.py 引导链。')

    def test_baseline_excludes_int1469_column_as_red_green_anchor(self,
                                                                 model_metadata):
        """红-绿锚点：基线不含 derived_test_type，迁移脚本必须提到它。

        若迁移脚本被删/改名，test_every_post_baseline_column_has_migration
        会对同一列报缺迁移；本用例把「锚点仍有效」钉死，避免有人顺手把该列
        登记进基线让守卫失去这层保护。
        """
        baseline = _baseline()
        assert 'derived_test_type' not in baseline.get('test_cases', [])
        assert _mentions(_migration_text(), 'derived_test_type')
        assert 'derived_test_type' in model_metadata['test_cases'].columns


class TestDerivedTestTypeMigrationScript:
    """迁移脚本本身的幂等要素（本卡缺陷的第二层：脚本要能安全跑在存量库上）。"""

    def test_ddl_is_idempotent_and_not_null_with_default(self):
        with open(_DERIVED_MIGRATION, encoding='utf-8') as f:
            text = f.read()
        assert 'ADD COLUMN IF NOT EXISTS' in text
        assert re.search(r'derived_test_type\s+varchar\(10\)\s+NOT NULL\s+'
                         r'DEFAULT\s+\'api\'', text), '补列口径应与 ORM 一致'
        assert 'CREATE INDEX IF NOT EXISTS' in text
        assert 'ix_test_cases_derived_test_type' in text
        # 默认 dry-run，防止误在存量库上直接改结构
        assert "add_argument('--apply'" in text


class TestDeployChainAppliesMigration:
    """本卡根因：脚本写好了但没进 docker db_bootstrap 引导链。"""

    def test_bootstrap_steps_include_derived_test_type_migration(self):
        steps = [list(step) for step in
                 _load_module(_BOOTSTRAP_PATH,
                              'int1565_db_bootstrap').BOOTSTRAP_STEPS]
        matches = [step for step in steps if _DERIVED_REL in step]
        assert matches, (
            f'BOOTSTRAP_STEPS 未包含 {_DERIVED_REL}：存量库（真实库 / 隔离库）'
            '不会补列，task_service 新镜像重建即 UndefinedColumn 400（INT-1565）')
        assert any('--apply' in step for step in matches), (
            '引导链步骤必须带 --apply（脚本默认 dry-run，不加等于没跑）')
