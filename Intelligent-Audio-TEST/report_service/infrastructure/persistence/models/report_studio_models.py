# -*- coding: utf-8 -*-
"""report_service Report Studio 业务资产 PO 定义（INT-673）

归属：report_service（报告上下文）
表：report_studio_documents / report_studio_document_versions
    / report_studio_chart_specs / report_studio_export_jobs

设计文档：《对话式报告工作台功能设计文档》§15.4。
- report_studio_documents 是文档真相源（当前 Markdown + 乐观锁 current_version）；
- report_studio_document_versions 是不可变快照（每次写操作同一数据库事务落新版本）；
- report_studio_chart_specs 是图表定义源（服务端读取后重新校验权限/指标/报表归属，
  用户输入不得生成任意 JS/SQL/URL）；
- report_studio_export_jobs 是导出异步作业（状态持久化，进程生命周期不影响作业记录）。
"""
from shared.models.database import Base, utc8now
from sqlalchemy import (
    func, Column, Integer, BigInteger, String, Text, DateTime, Boolean, JSON,
    Index, UniqueConstraint,
)


class ReportStudioDocument(Base):
    """Report Studio 文档聚合根（当前版 + 乐观锁基准）。"""
    __tablename__ = 'report_studio_documents'
    __table_args__ = (
        Index('idx_rs_doc_report_id', 'report_id'),
        Index('idx_rs_doc_created_by', 'created_by'),
    )
    doc_id = Column(String(36), primary_key=True, comment='文档 ID（UUID）')
    report_id = Column(BigInteger, nullable=False, comment='外键 → test_reports.id')
    agent_session_id = Column(String(64), nullable=True, comment='绑定 DSH agent 会话（可空，Agent 后端立项前可不绑）')
    title = Column(String(255), nullable=False, comment='文档标题')
    markdown_content = Column(Text, nullable=False, default='', comment='当前版 Markdown')
    chart_refs = Column(JSON, nullable=False, default=list, comment='受控图表引用 [chart:{chartId}]')
    style_prefs = Column(JSON, nullable=False, default=dict, comment='样式偏好')
    current_version = Column(Integer, nullable=False, default=1, comment='当前版本号（乐观锁基准）')
    etag_hash = Column(String(64), nullable=False, default='', comment='ETag（内容指纹）')
    created_by = Column(BigInteger, nullable=True, comment='创建者用户 ID')
    created_at = Column(DateTime, default=utc8now, server_default=func.now(), nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, server_default=func.now(), onupdate=utc8now, nullable=False, comment='更新时间')


class ReportStudioDocumentVersion(Base):
    """Report Studio 文档不可变版本快照。"""
    __tablename__ = 'report_studio_document_versions'
    __table_args__ = (
        UniqueConstraint('doc_id', 'version', name='uq_rs_doc_version'),
        Index('idx_rs_version_doc', 'doc_id'),
    )
    id = Column(Integer, primary_key=True, autoincrement=True, comment='版本行 ID')
    doc_id = Column(String(36), nullable=False, comment='外键 → report_studio_documents.doc_id')
    version = Column(Integer, nullable=False, comment='版本号（同 doc 内递增）')
    markdown_content = Column(Text, nullable=False, default='', comment='不可变 Markdown 快照')
    chart_specs = Column(JSON, nullable=False, default=dict, comment='该版本图表定义快照')
    parent_version = Column(Integer, nullable=True, comment='父版本号（0/None = 初始版）')
    snapshot_reason = Column(String(20), nullable=False, default='manual_edit',
                             comment='ai_edit / manual_edit / restore')
    created_by = Column(BigInteger, nullable=True, comment='创建者用户 ID')
    created_at = Column(DateTime, default=utc8now, server_default=func.now(), nullable=False, comment='创建时间')


class ReportStudioChartSpec(Base):
    """Report Studio 图表定义源（受控引用）。"""
    __tablename__ = 'report_studio_chart_specs'
    __table_args__ = (
        Index('idx_rs_chart_doc', 'doc_id'),
        Index('idx_rs_chart_report', 'report_id'),
    )
    chart_id = Column(String(36), primary_key=True, comment='图表 ID（UUID）')
    doc_id = Column(String(36), nullable=False, comment='外键 → report_studio_documents.doc_id')
    report_id = Column(BigInteger, nullable=False, comment='来源报告 ID（归属校验）')
    metric_params = Column(JSON, nullable=False, default=dict, comment='指标/分组/时间范围参数')
    style = Column(JSON, nullable=False, default=dict, comment='样式定义')
    version = Column(Integer, nullable=False, default=1, comment='ChartSpec 版本')
    created_by = Column(BigInteger, nullable=True, comment='创建者用户 ID')
    created_at = Column(DateTime, default=utc8now, server_default=func.now(), nullable=False, comment='创建时间')


class ReportStudioExportJob(Base):
    """Report Studio 导出异步作业。"""
    __tablename__ = 'report_studio_export_jobs'
    __table_args__ = (
        Index('idx_rs_export_doc', 'doc_id'),
        Index('idx_rs_export_created_by', 'created_by'),
    )
    export_id = Column(String(36), primary_key=True, comment='导出作业 ID（UUID）')
    doc_id = Column(String(36), nullable=False, comment='外键 → report_studio_documents.doc_id')
    version = Column(Integer, nullable=False, comment='锁定的文档版本')
    format = Column(String(10), nullable=False, comment='html / md / pptx / pdf')
    theme = Column(String(60), nullable=True, comment='导出主题')
    status = Column(String(10), nullable=False, default='pending', comment='pending / running / done / failed')
    file_path = Column(String(512), nullable=True, comment='产物文件路径')
    error = Column(Text, nullable=True, comment='失败原因')
    progress = Column(Integer, nullable=False, default=0, comment='进度 0-100')
    created_by = Column(BigInteger, nullable=True, comment='创建者用户 ID')
    created_at = Column(DateTime, default=utc8now, server_default=func.now(), nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, server_default=func.now(), onupdate=utc8now, nullable=False, comment='更新时间')
