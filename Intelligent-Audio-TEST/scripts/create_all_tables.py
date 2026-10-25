# -*- coding: utf-8 -*-
"""
数据库表重建脚本

通过 ``Base.metadata.create_all()`` 重建全部 90 张表。

使用方式：
    python scripts/create_all_tables.py          # 使用 .env 中的 DATABASE_URL
    python scripts/create_all_tables.py --dry-run # 仅打印将要创建的表，不执行

此脚本替代了历史迁移脚本（backend/scripts/migrations/202604~202607/），
后者为一次性运行脚本，不适用于 FastAPI 微服务架构。

INT-1623：本函数是「模型全集」的唯一来源 —— 任何一个 PO 模块漏导入，都会让
``Base.metadata`` 随测试调度漂移（INT-1565 迁移守卫踩过：transfer_agent 两表
漏导，-n 8 全量随机红）。新增服务 / 新 PO 模块必须在此登记。
"""

import argparse
import sys
import os

# 模型全集应有的表数（新增表必须同时改这里）
EXPECTED_TABLE_COUNT = 92

# 确保项目根目录在 sys.path 中
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


def _import_all_models():
    """导入所有服务的 PO 模型，确保它们注册到 Base.metadata。

    每个服务 infrastructure/persistence/models/__init__.py 导入即注册。
    """
    # task_service（含人工复核留痕 INT-340 / AI 复核记录 INT-821）
    from task_service.infrastructure.persistence.models import (  # noqa: F401
        Task, TaskTag, TaskCase, TaskDevice, TaskAPI, TaskMergeRelation,
        TestResult, TagCategory, Tag, TestCaseGroup, TestCase, TestCaseTag,
        EvaluationStrategy, Log, Favorite, TestResultReview, AiReview,
        DataTransferSourceMap,
    )
    # evaluation_service: 4 张表（含 INT-1762 D4 合并批次快照）
    from evaluation_service.infrastructure.persistence.models import (  # noqa: F401
        Category, Dimension, TestResultDimension, EvaluationMergeSnapshot,
    )
    # algorithm_service: 10 张表（含 INT-589 algorithm_definition_drafts）
    from algorithm_service.infrastructure.persistence.models import (  # noqa: F401
        AlgorithmGroup, AlgorithmDefinition, AlgorithmDeviceParam,
        AlgorithmApiParam, AlgorithmReferenceParam, EvaluationDimensionParam,
        ParamMapping, AlgorithmDimensionRelation, CaseAlgorithmParam,
        AlgorithmDefinitionDraft,
    )
    # report_service: 8 张表（INT-971 新增 report_shares 分享表）
    from report_service.infrastructure.persistence.models import (  # noqa: F401
        Report, ReportSummary, ReportSummaryMeta, ReportRawData,
        ReportCase, ReportMetricStats, ReportComparisonMatrix,
        ReportFavorite, ReportShare,
    )
    # report_service: 导出历史 1 张表（INT-1555 report_export_records）
    from report_service.infrastructure.persistence.models import (  # noqa: F401
        ReportExportRecord,
    )
    # report_service: Benchmark 排行 4 张表（D1）
    from report_service.infrastructure.persistence.models import (  # noqa: F401
        BenchmarkRanking, BenchmarkMetricMapping, BenchmarkSource, BenchmarkBaseline,
    )
    # report_service: 报告替换批次快照 1 张表（INT-1762 D4）
    from report_service.infrastructure.persistence.models import (  # noqa: F401
        ReportMergeSnapshot,
    )
    # auth_service: 9 张表
    from auth_service.infrastructure.persistence.models import (  # noqa: F401
        Role, Permission, RolePermission, UserPermission,
        User, OAuthClient, UserOAuthBinding, OAuthRefreshToken,
        AccessToken,
    )
    # audio_service: 7 张表
    from audio_service.infrastructure.persistence.models import (  # noqa: F401
        Audio, AudioAnnotation, AudioTag, AudioAlgorithmRelation,
        UploadTask, UploadFile, UploadChunk,
    )
    # device_service: 10 张表（INT-80 新增 device_groups/device_group_members/
    #                 device_status_events/device_alarm_rules/device_alarms）
    from device_service.infrastructure.persistence.models import (  # noqa: F401
        Device, DeviceTag, PlaybackDevice, SPLMapping, CalibrationHistory,
        DeviceGroup, DeviceGroupMember, DeviceStatusEvent,
        DeviceAlarmRule, DeviceAlarm,
    )
    # api_test_service: 1 张表
    from api_test_service.infrastructure.persistence.models import API  # noqa: F401
    # api_gateway: 1 张表（INT-620 系统选项 KV；api_gateway 直管，无独立 config 微服务）
    from api_gateway.infrastructure.models.system_option_model import SystemOption  # noqa: F401
    # transfer_agent: 2 张表（INT-1623 补入；此前漏导，真实库靠 transfer_agent 启动时
    #                 自行 create_all 才有这两张表，全新库 / 重引导库都缺）
    from transfer_agent.infrastructure.persistence.models import (  # noqa: F401
        TransferRecord, TransferChunk,
    )


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

    if len(table_names) != EXPECTED_TABLE_COUNT:
        print(f"\n⚠️ 警告: 预期 {EXPECTED_TABLE_COUNT} 张表，"
              f"实际注册 {len(table_names)} 张")

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
