# -*- coding: utf-8 -*-
"""报告导出历史应用服务（INT-1555）

职责：
- record：每次报告中心导出（POST/GET /reports/export）结束后落一条历史，
  成功 done、失败 failed（带 error）；记录失败不影响导出本身（只记日志）。
- list_history：导出历史分页读（按导出时间倒序），供「导出历史」页签消费。

可见性：已认证普通用户只看本人导出（created_by），admin / 未认证
（AUTH_MODE=off，user_id 为空）看全部——历史里的 scope 含报告名，不能
把别人的私有报告名透给普通用户。
"""
from __future__ import annotations

import logging
from typing import List, Optional

from shared.infrastructure.user_context import (
    get_current_user_id,
    get_current_user_is_admin,
)
from report_service.infrastructure.persistence.report_export_record_repository import (
    report_export_record_repository,
)

logger = logging.getLogger(__name__)

# 导出状态取值（同步导出：只有完成 / 失败两态）
STATUS_DONE = 'done'
STATUS_FAILED = 'failed'

# 分页上限（避免一次拉全表）
MAX_PER_PAGE = 100
DEFAULT_PER_PAGE = 20

# 批量导出的范围描述（不拼多份报告名）
_MULTI_SCOPE_FMT = '已选择 {count} 个报告'
# 单报告查不到名称时的兜底
_SINGLE_SCOPE_FMT = '报告 {report_id}'


def _record_to_dict(record) -> dict:
    """导出记录 PO → 对外契约 dict（GET /reports/export/history items 项）。"""
    return {
        'id': int(record.id),
        'scope': record.scope or '',
        'format': record.format or '',
        'created_at': record.created_at.isoformat() if record.created_at else None,
        'status': record.status or '',
        'error': record.error,
        'report_ids': list(record.report_ids or []),
    }


class ReportExportHistoryService:
    """报告导出历史应用服务（INT-1555）。"""

    def __init__(self, repository=report_export_record_repository):
        self.repository = repository

    # ------------------------------------------------------------------
    # 写侧：导出结束后登记历史
    # ------------------------------------------------------------------

    def _build_scope(self, report_ids: List[int]) -> str:
        """导出范围描述：单报告 = 报告名；批量 = 「已选择 N 个报告」。"""
        if not report_ids:
            return ''
        if len(report_ids) > 1:
            return _MULTI_SCOPE_FMT.format(count=len(report_ids))
        report_id = report_ids[0]
        names = self.repository.report_names([report_id])
        return names.get(report_id) or _SINGLE_SCOPE_FMT.format(report_id=report_id)

    def record(
        self,
        report_ids: List[int],
        format_type: str,
        result: Optional[dict] = None,
    ) -> Optional[int]:
        """登记一条导出历史，返回主键 ID（失败/异常返回 None）。

        判定依据是导出的实际产物：result 含 content_base64 才算成功，
        其余（success=False / 空产物 / 异常调用方传入的 message）记 failed。

        Args:
            report_ids: 本次导出的报告 ID 列表
            format_type: 请求的导出格式
            result: 导出处理结果 dict（handler 返回值）
        """
        result = result or {}
        try:
            ids = [int(rid) for rid in (report_ids or [])]
            filename = result.get('filename')
            content_base64 = result.get('content_base64')
            succeeded = bool(content_base64) and result.get('success') is not False
            return self.repository.create(
                report_ids=ids,
                scope=self._build_scope(ids),
                format_type=result.get('format') or format_type or 'csv',
                status=STATUS_DONE if succeeded else STATUS_FAILED,
                error=None if succeeded else (result.get('message') or '导出失败'),
                filename=filename,
                created_by=get_current_user_id(),
            )
        except Exception:
            logger.exception('登记报告导出历史失败（不影响导出结果）')
            return None

    # ------------------------------------------------------------------
    # 读侧：导出历史分页
    # ------------------------------------------------------------------

    def list_history(self, params: Optional[dict] = None) -> dict:
        """分页查询导出历史（导出时间倒序）。

        Args:
            params: {page, per_page}（均可选，page 默认 1、per_page 默认 20）

        Returns:
            {items: [{id, scope, format, created_at, status, error, report_ids}],
             total, page, per_page}
        """
        params = params or {}
        page = max(int(params.get('page') or 1), 1)
        per_page = min(max(int(params.get('per_page') or DEFAULT_PER_PAGE), 1),
                       MAX_PER_PAGE)

        user_id = get_current_user_id()
        created_by = None if (user_id is None or get_current_user_is_admin()) \
            else int(user_id)

        records, total = self.repository.list_page(
            page, per_page, created_by=created_by)
        return {
            'items': [_record_to_dict(record) for record in records],
            'total': total,
            'page': page,
            'per_page': per_page,
        }


# 模块级单例
report_export_history_service = ReportExportHistoryService()
