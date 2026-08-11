# -*- coding: utf-8 -*-
"""
数据库表重建脚本

通过 ``Base.metadata.create_all()`` 重建全部 53 张表。

使用方式：
    python scripts/create_all_tables.py          # 使用 .env 中的 DATABASE_URL
    python scripts/create_all_tables.py --dry-run # 仅打印将要创建的表，不执行

此脚本替代了历史迁移脚本（backend/scripts/migrations/202604~202607/），
后者为一次性运行脚本，不适用于 FastAPI 微服务架构。
"""

import argparse
import sys
import os

# 确保项目根目录在 sys.path 中
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


def _import_all_models():
    """导入所有服务的 PO 模型，确保它们注册到 Base.metadata。

    每个服务 infrastructure/persistence/models/__init__.py 导入即注册。
    """
    # task_service: 13 张表
    from task_service.infrastructure.persistence.models import (  # noqa: F401
        Task, TaskTag, TaskCase, TaskDevice, TaskAPI, TaskMergeRelation,
        TestResult, TagCategory, Tag, TestCaseGroup, TestCase, TestCaseTag,
        Log,
    )
    # evaluation_service: 3 张表
    from evaluation_service.infrastructure.persistence.models import (  # noqa: F401
        Category, Dimension, TestResultDimension,
    )
    # algorithm_service: 9 张表
    from algorithm_service.infrastructure.persistence.models import (  # noqa: F401
        AlgorithmGroup, AlgorithmDefinition, AlgorithmDeviceParam,
        AlgorithmApiParam, AlgorithmReferenceParam, EvaluationDimensionParam,
        ParamMapping, AlgorithmDimensionRelation, CaseAlgorithmParam,
    )
    # report_service: 7 张表
    from report_service.infrastructure.persistence.models import (  # noqa: F401
        Report, ReportSummary, ReportSummaryMeta, ReportRawData,
        ReportCase, ReportMetricStats, ReportComparisonMatrix,
    )
    # auth_service: 7 张表
    from auth_service.infrastructure.persistence.models import (  # noqa: F401
        Role, Permission, RolePermission, UserPermission,
        User, OAuthClient, OAuthRefreshToken,
    )
    # audio_service: 7 张表
    from audio_service.infrastructure.persistence.models import (  # noqa: F401
        Audio, AudioAnnotation, AudioTag, AudioAlgorithmRelation,
        UploadTask, UploadFile, UploadChunk,
    )
    # device_service: 5 张表
    from device_service.infrastructure.persistence.models import (  # noqa: F401
        Device, DeviceTag, PlaybackDevice, SPLMapping, CalibrationHistory,
    )
    # api_test_service: 1 张表
    from api_test_service.infrastructure.persistence.models import API  # noqa: F401


def create_all_tables(dry_run=False):
    """初始化数据库连接池并调用 ``Base.metadata.create_all()``。

    Args:
        dry_run: True 时仅打印表列表，不执行 DDL
    """
    from shared.models.database import Base, init_db, get_engine

    # 导入所有 PO 模型，注册到 Base.metadata
    _import_all_models()

    # 初始化连接池
    init_db(pool_size=5)
    engine = get_engine()

    # 获取已注册的表名
    table_names = sorted(Base.metadata.tables.keys())
    print(f"已注册 {len(table_names)} 张表:")
    for name in table_names:
        print(f"  - {name}")

    if len(table_names) != 53:
        print(f"\n⚠️ 警告: 预期 53 张表，实际注册 {len(table_names)} 张")

    if dry_run:
        print("\n--dry-run 模式，未执行 DDL")
        return

    print("\n执行 Base.metadata.create_all() ...")
    Base.metadata.create_all(engine, checkfirst=True)
    print("✅ 全部表创建完成（已存在的表跳过）")


def main():
    parser = argparse.ArgumentParser(
        description="重建全部数据库表（Base.metadata.create_all）"
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='仅打印将要创建的表名，不执行 DDL',
    )
    args = parser.parse_args()

    create_all_tables(dry_run=args.dry_run)


if __name__ == '__main__':
    main()
