# -*- coding: utf-8 -*-
"""report_service 报告导出记录 PO（INT-1555 导出历史）

归属：report_service（报告上下文）。
表：report_export_records —— 报告中心「导出历史」页签的数据源。

- 每次 POST/GET /reports/export 无论成功失败都落一条记录（失败带 error），
  导出为同步链路（content_base64 直接回文件），故 status 只取 done / failed；
- report_ids 保留导出范围原始 ID 列表，scope 是给前端展示的范围描述
  （单报告 = 报告名，批量 = 「已选择 N 个报告」），不把多份报告名拼进一列；
- created_by 为导出人（x-user-id；AUTH_MODE=off 时为空，历史对所有人可见）。
"""
from shared.models.database import Base, utc8now
from sqlalchemy import (
    func, Column, Integer, BigInteger, String, Text, DateTime, JSON, Index,
)

# 自增主键：SQLite（测试库）仅 INTEGER PRIMARY KEY 自增，PG 用 BIGINT
_PK_BIGINT = BigInteger().with_variant(Integer, 'sqlite')


class ReportExportRecord(Base):
    """报告导出记录（INT-1555）"""
    __tablename__ = 'report_export_records'
    __table_args__ = (
        Index('idx_report_export_created_at', 'created_at'),
        Index('idx_report_export_created_by', 'created_by'),
    )
    id = Column(_PK_BIGINT, primary_key=True, autoincrement=True, comment='主键ID')
    report_ids = Column(JSON, nullable=False, default=list, comment='导出报告 ID 列表')
    scope = Column(String(255), nullable=False, default='',
                   comment='导出范围描述（单报告名 / 已选择 N 个报告）')
    format = Column(String(10), nullable=False, default='csv',
                    comment='导出格式 csv / excel / pdf / html')
    status = Column(String(20), nullable=False, default='done',
                    comment='导出状态 done / failed')
    error = Column(Text, nullable=True, comment='失败原因（status=failed 时非空）')
    filename = Column(String(255), nullable=True, comment='产物文件名')
    created_by = Column(BigInteger, nullable=True, comment='导出人（x-user-id）')
    created_at = Column(DateTime, default=utc8now, server_default=func.now(),
                        nullable=False, comment='导出时间')
