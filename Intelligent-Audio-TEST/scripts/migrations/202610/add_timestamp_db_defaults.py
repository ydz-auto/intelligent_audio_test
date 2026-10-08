# -*- coding: utf-8 -*-
"""时间戳列 DB 级 DEFAULT 对齐迁移（INT-47）

背景：各服务 PO 的 created_at / updated_at / received_at / published_at /
computed_at 等时间戳列此前仅有 SQLAlchemy ORM 层默认值（default=utc8now），
``Base.metadata.create_all()`` 建出的表 NOT NULL 但不带 DB 级 DEFAULT，
裸 SQL INSERT（如 seed_rbac.py）在全新库上报 NotNullViolation：

    sqlalchemy.exc.IntegrityError: (psycopg2.errors.NotNullViolation)
    null value in column "created_at" of relation "permissions" ...

配套修复：
- PO 模型已统一补 ``server_default=func.now()``（新建库由 create_all 直接带出默认值）；
- 本脚本对**既有环境**以 ORM 元数据为准，逐表检查 information_schema，
  对缺失 DB 级默认值的上述列执行 ``ALTER TABLE ... SET DEFAULT now()``
  （与既有验收库 historical schema 现状一致）。全新库执行本脚本为 no-op。

幂等性：已有任意 DB 级默认值的列自动 [SKIP]，可安全重复执行。

用法:
    python scripts/migrations/202610/add_timestamp_db_defaults.py [--dry-run]

依赖:
    连接串读环境变量 DATABASE_URI（回退 DATABASE_URL）；
    需要目标库已建表（create_all_tables.py / 历史建表路径）。
"""
import argparse
import os
import sys

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
_scripts_dir = os.path.join(_project_root, 'scripts')
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from sqlalchemy import DateTime, create_engine, inspect  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

# 导入全部服务的 PO 模型，注册到 Base.metadata（与 create_all_tables.py 同源，
# 额外包含 transfer_agent 两表，保证对齐覆盖完整）
from create_all_tables import _import_all_models  # noqa: E402


def _resolve_uri():
    uri = os.environ.get('DATABASE_URI') or os.environ.get('DATABASE_URL')
    if not uri:
        print('❌ 未配置 DATABASE_URI / DATABASE_URL 环境变量')
        sys.exit(1)
    return uri


def _target_columns():
    """收集目标列：{表名: [列名, ...]}，规则 = DateTime 列且声明了 server_default。"""
    from shared.models.database import Base

    _import_all_models()
    # transfer_agent 不在 create_all_tables 的导入清单里，单独注册
    from transfer_agent.infrastructure.persistence.models import (  # noqa: F401
        TransferRecord, TransferChunk,
    )

    targets = {}
    for table_name, table in sorted(Base.metadata.tables.items()):
        cols = [
            c.name for c in table.columns
            if isinstance(c.type, DateTime) and c.server_default is not None
        ]
        if cols:
            targets[table_name] = cols
    return targets


def main():
    parser = argparse.ArgumentParser(
        description='为缺失 DB 级默认值的时间戳列补 SET DEFAULT now()（INT-47）'
    )
    parser.add_argument('--dry-run', action='store_true', help='仅列出待 ALTER 的列，不执行')
    args = parser.parse_args()

    uri = _resolve_uri()
    print(f'数据库: {make_url(uri).render_as_string(hide_password=True)}')
    print(f'模式: {"DRY-RUN" if args.dry_run else "正式执行"}\n')

    targets = _target_columns()
    total_cols = sum(len(v) for v in targets.values())
    print(f'目标：{len(targets)} 张表 / {total_cols} 个时间戳列（ORM 元数据声明 server_default）')

    engine = create_engine(uri)
    inspector = inspect(engine)

    pending, skipped, missing_tables = [], [], []
    for table_name, cols in targets.items():
        if not inspector.has_table(table_name):
            missing_tables.append(table_name)
            continue
        db_defaults = {
            row['name']: row['default']
            for row in inspector.get_columns(table_name)
        }
        for col in cols:
            if db_defaults.get(col) is not None:
                skipped.append((table_name, col, db_defaults[col]))
            else:
                pending.append((table_name, col))

    if missing_tables:
        print(f'\n[SKIP] {len(missing_tables)} 张表在库中不存在（全新库先跑 create_all_tables.py）：')
        for t in missing_tables:
            print(f'  - {t}')

    print(f'\n待补 DB 级默认：{len(pending)} 列；已有默认 [SKIP]：{len(skipped)} 列')

    if not pending:
        print('\n✅ 所有目标时间戳列均已具备 DB 级默认值，无需迁移')
        return

    print('\n待执行 ALTER：')
    for t, c in pending:
        print(f'  ALTER TABLE {t} ALTER COLUMN {c} SET DEFAULT now()')

    if args.dry_run:
        print('\n[DRY-RUN] 未实际执行。')
        return

    applied, failed = 0, 0
    print('\n执行 ALTER ...')
    for t, c in pending:
        stmt = f'ALTER TABLE {t} ALTER COLUMN {c} SET DEFAULT now()'
        try:
            with engine.begin() as conn:
                conn.exec_driver_sql(stmt)
            applied += 1
            print(f'  [OK] {t}.{c}')
        except Exception as e:  # 单列失败不影响其余列（逐列提交，重跑续传）
            failed += 1
            print(f'  [FAIL] {t}.{c}: {e}')

    print(f'\n完成：补默认 {applied} 列，失败 {failed} 列，已有默认跳过 {len(skipped)} 列')
    if failed:
        sys.exit(2)


if __name__ == '__main__':
    main()
