# -*- coding: utf-8 -*-
"""report_service Benchmark 排行 PO 定义（D1 双轨排行）

归属：report_service（报告上下文）
表：benchmark_rankings / benchmark_metric_mappings / benchmark_sources / benchmark_baselines

设计文档：《报告Benchmark排行功能设计文档》§6.3-§6.6。
- benchmark_rankings 是排行 ReadModel 缓存：仅由排行计算（写侧命令）整体刷新，
  查询侧只读，不产生写副作用（严格 CQRS）。
- benchmark_baselines 导入即不可变快照：版本行只插不改，重复导入幂等。
"""
from shared.models.database import Base, utc8now
from sqlalchemy import (
    func, Column, Integer, BigInteger, String, Text, DateTime, Boolean, Float, JSON,
    Index, UniqueConstraint,
)


class BenchmarkRanking(Base):
    """Benchmark 排行结果（ReadModel）。"""
    __tablename__ = 'benchmark_rankings'
    __table_args__ = (
        # 排行行唯一性兜底（并发重算防重复行）：组内每来源每主体至多一行
        UniqueConstraint('category', 'metric_code', 'scenario_key', 'source',
                         'subject_name', name='uq_benchmark_ranking_row'),
        Index('idx_benchmark_ranking_group', 'benchmark_suite', 'category', 'metric_code', 'source'),
        Index('idx_benchmark_ranking_subject', 'subject_name'),
        Index('idx_benchmark_ranking_pt', 'published_task_id'),
        Index('idx_benchmark_ranking_baseline', 'baseline_id'),
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='排行 ID')
    source = Column(String(30), nullable=False, comment="数据来源：platform_test / external_import")
    published_task_id = Column(BigInteger, comment='外键 → published_tasks.id（source=platform_test 时有值）')
    published_task_version = Column(Integer, comment='引用的已发布任务版本号（source=platform_test 时有值）')
    report_id = Column(BigInteger, comment='来源报告 ID（source=platform_test 时有值）')
    baseline_id = Column(BigInteger, comment='外键 → benchmark_baselines.id（source=external_import 时有值）')
    subject_name = Column(String(255), nullable=False, comment='被测对象名（模型/APP/API 名称）')
    subject_type = Column(String(30), comment='open_source / closed_source / app')
    device_type = Column(String(30), comment='physical / http_api / websocket_api')
    benchmark_suite = Column(String(120), comment='测试集标识（排行分组键）')
    category = Column(String(30), comment='asr / voice_llm / tts / translation')
    metric_code = Column(String(60), nullable=False, comment='排行指标代码')
    metric_name = Column(String(120), comment='指标显示名')
    metric_value = Column(Float, nullable=False, comment='被测指标值')
    unit = Column(String(20), comment='单位')
    direction = Column(String(20), nullable=False, comment='lower_is_better / higher_is_better')
    rank = Column(Integer, comment='名次（并列共享）')
    total = Column(Integer, comment='参与对比的模型数')
    percentile = Column(Float, comment='百分位（越低越靠前）')
    score100 = Column(Float, comment='归一化分 0-100，可空（单主体不归一化）')
    gap_best = Column(Float, comment='与排行最佳差距')
    gap_median = Column(Float, comment='与排行中位数差距')
    delta_external = Column(Float, comment='实测值与外部基线值的差异（双轨并存时有值）')
    scenario_key = Column(String(120), comment='排行所用场景')
    computed_at = Column(DateTime, default=utc8now, server_default=func.now(), nullable=False, comment='计算时间')


class BenchmarkMetricMapping(Base):
    """Benchmark 指标映射配置（单一事实源：系统维度 ↔ 排行指标）。"""
    __tablename__ = 'benchmark_metric_mappings'
    __table_args__ = (
        Index('idx_benchmark_mapping_dimension', 'dimension_name'),
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='映射 ID')
    dimension_name = Column(String(120), nullable=False, comment='系统维度名（如 WER、takeover_latency）')
    metric_code = Column(String(60), nullable=False, comment='排行指标代码')
    metric_name = Column(String(120), comment='指标显示名')
    unit = Column(String(20), comment='单位')
    direction = Column(String(20), nullable=False, comment='lower_is_better / higher_is_better')
    scenario_tags = Column(JSON, comment='默认场景标签')
    active = Column(Boolean, nullable=False, default=True, comment='是否启用')
    updated_at = Column(DateTime, default=utc8now, server_default=func.now(), onupdate=utc8now, nullable=False, comment='更新时间')


class BenchmarkSource(Base):
    """外部基线数据源（业界公开 Benchmark 榜单）。"""
    __tablename__ = 'benchmark_sources'
    __table_args__ = (
        Index('idx_benchmark_source_type', 'source_type'),
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='数据源 ID')
    name = Column(String(255), nullable=False, comment='数据源名称（如 Pipecat STT Benchmark）')
    provider = Column(String(255), comment='发布方')
    source_type = Column(String(30), nullable=False, default='manual',
                         comment='official / third_party / self_test / manual')
    url = Column(String(1024), comment='原始链接')
    version = Column(String(60), comment='数据源版本')
    description = Column(Text, comment='说明')
    created_by = Column(String(120), comment='创建人')
    created_at = Column(DateTime, default=utc8now, server_default=func.now(), nullable=False, comment='创建时间')


class BenchmarkBaseline(Base):
    """外部基线条目（导入即不可变快照，version 从 1 递增，is_current 标记当前版本）。"""
    __tablename__ = 'benchmark_baselines'
    __table_args__ = (
        Index('idx_benchmark_baseline_current', 'source_id', 'category', 'is_current'),
        Index('idx_benchmark_baseline_metric', 'category', 'metric_code'),
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='基线 ID')
    source_id = Column(BigInteger, nullable=False, comment='外键 → benchmark_sources.id')
    category = Column(String(30), nullable=False, comment='asr / voice_llm / tts / translation')
    model_name = Column(String(255), nullable=False, comment='模型名（如 Deepgram Nova-4）')
    vendor = Column(String(255), comment='厂商（如 Deepgram）')
    metric_code = Column(String(60), nullable=False, comment='排行指标代码（如 WER、TTLW）')
    metric_name = Column(String(120), comment='指标显示名')
    value = Column(Float, nullable=False, comment='指标值')
    unit = Column(String(20), comment='单位（% / ms / 分）')
    direction = Column(String(20), nullable=False, comment='lower_is_better / higher_is_better')
    scenario_tags = Column(JSON, comment='场景标签（普通话通用 / 噪声 / 多轮 / 打断 / 翻译 / TTS）')
    sample_size = Column(Integer, comment='采样规模（可空）')
    metric_date = Column(String(20), comment='数据产生日期（YYYY-MM-DD）')
    version = Column(Integer, nullable=False, default=1, comment='基线版本号，从 1 开始')
    is_current = Column(Boolean, nullable=False, default=True, comment='是否当前版本')
    created_at = Column(DateTime, default=utc8now, server_default=func.now(), nullable=False, comment='创建时间')
