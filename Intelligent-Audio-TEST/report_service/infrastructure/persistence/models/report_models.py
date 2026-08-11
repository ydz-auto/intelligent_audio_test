# -*- coding: utf-8 -*-
"""report_service 报告 PO 定义

归属：report_service（报告上下文）
表：test_reports / report_summaries / report_summary_meta / report_raw_data
     / report_cases / report_metric_stats / report_comparison_matrix

P5 改造：从 shared/models/models/report_models.py 真正下沉到本服务。

关键决策：移除 Report.task 跨域 relationship（Task 归属 task_service）。
Report → ReportSummary/ReportCase 等子表的同域 relationship 全部保留。
"""
from shared.models.database import Base, utc8now
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, DateTime, Boolean, Float, JSON,
    Index, ForeignKey,
)
from sqlalchemy.orm import relationship


class Report(Base):
    """测试报告模型 (Test Report Model)
    存储任务执行完成后生成的汇总分析报告。
    """
    __tablename__ = 'test_reports'
    __table_args__ = (
        Index('idx_report_task_id', 'task_id'),
        Index('idx_report_type', 'type'),
        Index('idx_report_status', 'status'),
        Index('idx_report_created_at', 'created_at'),
        Index('idx_report_type_status', 'type', 'status'),
    )
    id = Column(Integer, primary_key=True, autoincrement=True, comment='报告唯一ID')
    name = Column(String(255), nullable=False, comment='报告名称')
    type = Column(String(30), nullable=False, comment='报告类型')
    description = Column(Text, comment='报告详细描述')
    task_id = Column(Integer, comment='关联测试任务ID')
    status = Column(String(20), nullable=False, default='draft', comment='报告状态 (draft/published)')
    analysis = Column(Text, comment='人工/自动分析结论')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')
    deleted = Column(Boolean, nullable=False, default=False, comment='逻辑删除标志')
    deleted_at = Column(DateTime, nullable=True, comment='逻辑删除时间（60天后硬删除）')

    # P5: 跨域 relationship task 移除（Task 归属 task_service），跨域查询改 gRPC
    summary_info = relationship('ReportSummary', foreign_keys='ReportSummary.report_id', backref='report', uselist=False, lazy='select', passive_deletes=True)
    summary_meta = relationship('ReportSummaryMeta', foreign_keys='ReportSummaryMeta.report_id', backref='report', uselist=False, lazy='select', passive_deletes=True)
    raw_data = relationship('ReportRawData', foreign_keys='ReportRawData.report_id', backref='report', uselist=False, lazy='select', passive_deletes=True)
    cases = relationship('ReportCase', foreign_keys='ReportCase.report_id', backref='report', lazy='dynamic', passive_deletes=True)
    metric_stats = relationship('ReportMetricStats', foreign_keys='ReportMetricStats.report_id', backref='report', uselist=False, lazy='select', passive_deletes=True)
    comparison_matrix_data = relationship('ReportComparisonMatrix', foreign_keys='ReportComparisonMatrix.report_id', backref='report', uselist=False, lazy='select', passive_deletes=True)


class ReportSummary(Base):
    """报告摘要模型 (Report Summary Model)
    存储报告的小数据量摘要信息，用于列表页快速查询。与 Report 一对一关联。
    """
    __tablename__ = 'report_summaries'
    __table_args__ = (
        Index('idx_report_summary_report_id', 'report_id'),
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='摘要唯一ID')
    report_id = Column(BigInteger, ForeignKey('test_reports.id'), nullable=False, unique=True, comment='关联报告ID')
    task_ids = Column(JSON, comment='关联任务ID列表 (对比报告使用)')
    total_cases = Column(Integer, default=0, comment='总用例数')
    completed_cases = Column(Integer, default=0, comment='完成用例数')
    failed_cases = Column(Integer, default=0, comment='失败用例数')
    pass_rate = Column(Float, default=0, comment='通过率')
    duration = Column(Float, default=0, comment='任务执行时长(秒)')
    started_at = Column(DateTime, comment='任务开始时间')
    completed_at = Column(DateTime, comment='任务完成时间')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')


class ReportSummaryMeta(Base):
    """报告摘要元数据模型 (Report Summary Meta Model)
    存储报告摘要的 JSON 元数据，按需加载。与 Report 一对一关联。
    """
    __tablename__ = 'report_summary_meta'
    __table_args__ = (
        Index('idx_report_summary_meta_report_id', 'report_id'),
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='元数据唯一ID')
    report_id = Column(BigInteger, ForeignKey('test_reports.id'), nullable=False, unique=True, comment='关联报告ID')
    dimension_values = Column(JSON, comment='维度平均分列表')
    case_categories = Column(JSON, comment='用例分组列表')
    all_case_tags = Column(JSON, comment='用例标签列表')
    devices = Column(JSON, comment='设备列表')
    apis = Column(JSON, comment='API列表')
    resources = Column(JSON, comment='资源列表')
    resource_headers = Column(JSON, comment='资源头信息')
    all_metrics = Column(JSON, comment='评估维度列表')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')


class ReportRawData(Base):
    """报告原始数据模型 (Report Raw Data Model)
    存储报告的原始维度分数数据，按需加载。与 Report 一对一关联。
    """
    __tablename__ = 'report_raw_data'
    __table_args__ = (
        Index('idx_report_raw_data_report_id', 'report_id'),
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='原始数据唯一ID')
    report_id = Column(BigInteger, ForeignKey('test_reports.id'), nullable=False, unique=True, comment='关联报告ID')
    raw_data = Column(JSON, comment='原始维度分数数据')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')


class ReportCase(Base):
    """报告用例数据模型 (Report Case Model)
    存储报告的单个用例详情，一个 case 一行记录。与 Report 多对一关联。
    """
    __tablename__ = 'report_cases'
    __table_args__ = (
        Index('idx_report_cases_report_id', 'report_id'),
        Index('idx_report_cases_test_case_id', 'test_case_id'),
        Index('idx_report_cases_category', 'category'),
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='用例数据唯一ID')
    report_id = Column(BigInteger, ForeignKey('test_reports.id'), nullable=False, comment='关联报告ID')
    test_case_id = Column(String(50), comment='关联测试用例ID')
    name = Column(String(500), comment='用例名称')
    description = Column(Text, comment='用例描述')
    category = Column(String(255), comment='用例分组')
    tags = Column(JSON, comment='用例标签列表')
    metrics = Column(JSON, comment='指标数据 {resource: {dim_name: value}}')
    results = Column(JSON, comment='执行结果列表')
    audios = Column(JSON, comment='音频列表')
    reference_params = Column(JSON, comment='参考参数')
    algorithm_results = Column(JSON, comment='算法结果')
    algorithm_type = Column(String(100), comment='算法类型')
    logs = Column(Text, comment='日志')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')


class ReportMetricStats(Base):
    """报告指标统计数据模型 (Report Metric Stats Model)
    存储报告的分组指标数据、统计数据，按需加载。与 Report 一对一关联。
    """
    __tablename__ = 'report_metric_stats'
    __table_args__ = (
        Index('idx_report_metric_stats_report_id', 'report_id'),
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='统计数据唯一ID')
    report_id = Column(BigInteger, ForeignKey('test_reports.id'), nullable=False, unique=True, comment='关联报告ID')
    metric_data = Column(JSON, comment='分组指标数据')
    tag_metric_data = Column(JSON, comment='标签指标数据')
    tag_category_metric_data = Column(JSON, comment='按标签分类的指标数据')
    case_type_stats = Column(JSON, comment='用例类型统计数据')
    device_stats = Column(JSON, comment='设备统计数据')
    api_stats = Column(JSON, comment='API统计数据')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')


class ReportComparisonMatrix(Base):
    """报告对比矩阵数据模型 (Report Comparison Matrix Model)
    存储对比报告的矩阵数据，按需加载。与 Report 一对一关联。
    """
    __tablename__ = 'report_comparison_matrix'
    __table_args__ = (
        Index('idx_report_comparison_matrix_report_id', 'report_id'),
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='对比矩阵唯一ID')
    report_id = Column(BigInteger, ForeignKey('test_reports.id'), nullable=False, unique=True, comment='关联报告ID')
    comparison_matrix = Column(JSON, comment='对比矩阵数据 (对比报告使用)')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')
