# -*- coding: utf-8 -*-
"""报告用例配置快照 PO（INT-1994 / 档4 R1）—— 内容寻址快照表

归属：report_service；表：report_case_snapshots

背景：``report_cases`` 是报告级用例行，每份报告把用例配置**整份**再落一次库，
同一份配置在几十份报告里重复（主库实测 33,925 行 / 258MB，九字段 payload 去重后
仅 10,843 个不同值）。R1 把这九个字段按 ``sha256(规范化 JSON)`` 外置到本表，
``report_cases`` 行上只留 4 个指针列（双写期间原内容列仍在，供回滚）。

表口径（设计文档 ``doc/功能设计文档/01_测试执行/10_报告用例快照外置.md`` §3.2）：

    sha256        char(64) PRIMARY KEY   内容寻址主键，天然幂等
    payload_gz    bytea NOT NULL         九字段规范化字节的 gzip 体
                 SET STORAGE EXTERNAL    已经是压缩体，关掉 TOAST 二次压缩
    payload_bytes int                     压缩后字节数
    created_at    timestamptz             快照行写入时间（不是冻结时间）

**不建 ``deleted``、不建 ``report_id``**：纯内容寻址，引用集合以 ``report_cases``
为准（快照被多份报告共享，按报告删会打断别的报告的解引用）；回收走 anti-join
sweep，由 M1 之后的独立低频任务负责。因此本表**不是** SoftDelete 家族成员，
``ReportServiceCleaner.hard_delete_expired`` 不碰它。

规范化 / sha256 / gzip 口径 100% 复用 ``shared/utils/raw_payload.py`` 纯函数
（见 ``report_case_snapshot_store``），本模块只声明存储形态。
"""
from sqlalchemy import (
    CHAR, Column, DateTime, Integer, LargeBinary, func,
)

from shared.models.database import Base, utc8now


class ReportCaseSnapshot(Base):
    """报告用例配置快照（内容寻址，一份 payload 一行）"""
    __tablename__ = 'report_case_snapshots'
    sha256 = Column(CHAR(64), primary_key=True,
                    comment='九字段规范化 JSON 字节的 sha256（内容寻址主键）')
    payload_gz = Column(LargeBinary, nullable=False,
                        comment='九字段规范化 JSON 的 gzip 体（STORAGE EXTERNAL）')
    payload_bytes = Column(Integer, nullable=True, comment='压缩后字节数（gzip）')
    created_at = Column(DateTime, default=utc8now, server_default=func.now(),
                        nullable=False, comment='快照行写入时间（不是冻结时间）')
