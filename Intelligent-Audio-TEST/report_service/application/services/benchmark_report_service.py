# -*- coding: utf-8 -*-
"""Benchmark 报告发布应用服务（INT-481：第五表 + 发布/查询端点）

数据流（设计文档《报告Benchmark排行功能设计文档》§4.5 + INT-481）：
  发布请求 → 聚合当前排行 ReadModel（benchmark_rankings 快照，可按
  suite/category/source 筛选）→ 复用报告 7 表结构建报告主记录
  （report_type='benchmark'）→ 排行快照落库 benchmark_reports（report_id 关联）
  → REPORT_EVENTS 域内事件 + 审计

生成链扩展边界（INT-481 范围钉死）：复用报告 7 表结构、独立 benchmark 数据
组装，不重构既有任务中心化生成链。

严格 CQRS：publish 是写侧命令（唯一写入口）；list/get 由查询侧只读。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from report_service.application.commands.benchmark_commands import (
    CreateBenchmarkReportCommand,
)
from report_service.application.services.benchmark_audit import write_benchmark_audit
from report_service.domain.entities import ReportAggregate, ReportStatus
from report_service.domain.entities.benchmark import BenchmarkCategory, RankingSource
from report_service.infrastructure.persistence.report_repository import report_repository
from shared.infrastructure.user_context import get_current_user_id
from shared.models.common_enums import AuditEvent
from shared.utils.query_utils import now_cst

logger = logging.getLogger(__name__)

_SOURCE_VALUES = {source.value for source in RankingSource}
_CATEGORY_VALUES = {category.value for category in BenchmarkCategory}


def _default_repo():
    from report_service.infrastructure.persistence.benchmark_repository import (
        BenchmarkRepositoryImpl,
    )
    return BenchmarkRepositoryImpl()


def _emit_report_event(event_name, data):
    """经 EventBus REPORT_EVENTS 发布 Benchmark 报告发布事件，由 api_gateway 订阅五通道后转发前端"""
    try:
        from shared.utils.redis_pubsub import EventBus, EventChannel, EventType
        EventBus().publish(EventChannel.REPORT_EVENTS, EventType.REPORT_GENERATED,
                           {'event': event_name, 'data': data})
    except Exception as _e:
        logger.warning('Benchmark 报告事件发布失败: %s', _e)


class BenchmarkReportService:
    """Benchmark 报告发布服务（可注入仓储替身，便于单测）。"""

    def __init__(self, repo=None, report_repo=None):
        self._repo = repo
        self._report_repo = report_repo

    @property
    def repo(self):
        if self._repo is None:
            self._repo = _default_repo()
        return self._repo

    @property
    def report_repo(self):
        if self._report_repo is None:
            return report_repository
        return self._report_repo

    # ---------- 数据组装 ----------

    @staticmethod
    def _collect_ranking_rows(repo, suite: str, category: str, source: str) -> List[Dict[str, Any]]:
        """聚合当前排行 ReadModel 快照行（读侧查询，无写副作用）。"""
        return repo.query_rankings({
            'suite': suite or '',
            'category': category or '',
            'metric_code': '',
            'source': source or '',
            'published_task_id': None,
            'subject_name': '',
        })

    @staticmethod
    def _snapshot_payload(suite, category, source, rows) -> Dict[str, Any]:
        """组装排行快照 JSON（发布时点定格，报告不随后续重算漂移）。"""
        published_task_ids = {r.get('published_task_id') for r in rows
                              if r.get('published_task_id') is not None}
        subjects = {r.get('subject_name') for r in rows if r.get('subject_name')}
        metric_codes = {r.get('metric_code') for r in rows if r.get('metric_code')}
        return {
            'filters': {
                'suite': suite or '',
                'category': category or '',
                'source': source or '',
            },
            'counts': {
                'published_task_count': len(published_task_ids),
                'subject_count': len(subjects),
                'metric_count': len(metric_codes),
                'row_count': len(rows),
            },
            'rows': rows,
        }

    @staticmethod
    def _default_name(suite: str, category: str, source: str) -> str:
        """自动生成报告名（未显式命名时）。"""
        suite_label = suite or '全量'
        category_label = category or '全量'
        source_label = source or '全量'
        return (f"Benchmark报告_{suite_label}_{category_label}_{source_label}_"
                f"{now_cst().strftime('%Y%m%d%H%M%S')}")

    # ---------- 写侧：发布 ----------

    def publish(self, command: CreateBenchmarkReportCommand) -> Dict[str, Any]:
        """发布 Benchmark 报告：聚合排行快照 → 建报告主记录 → 快照落库 + 事件 + 审计。

        失败语义：数据组装 / 报告记录创建 / 快照落库任一环节失败即整体失败，
        不产生半成品记录（报告主记录与快照先后写入，快照失败时回滚补偿删除报告主记录）。
        """
        try:
            suite = (command.suite or '').strip()
            category = (command.category or '').strip()
            source = (command.source or '').strip()
            if category and category not in _CATEGORY_VALUES:
                return {
                    'success': False,
                    'message': f'被测类别非法，仅支持: {", ".join(sorted(_CATEGORY_VALUES))}',
                    'data': None, 'code': 100,
                }
            if source and source not in _SOURCE_VALUES:
                return {
                    'success': False,
                    'message': f'数据来源非法，仅支持: {", ".join(sorted(_SOURCE_VALUES))}',
                    'data': None, 'code': 101,
                }

            rows = self._collect_ranking_rows(self.repo, suite, category, source)
            snapshot = self._snapshot_payload(suite, category, source, rows)
            counts = snapshot['counts']

            name = (command.name or '').strip() or self._default_name(suite, category, source)
            task_id = command.task_id
            try:
                task_id = int(task_id) if task_id not in (None, '') else None
            except (TypeError, ValueError):
                return {'success': False, 'message': '来源任务 ID 必须为整数', 'data': None, 'code': 102}

            # 复用报告 7 表结构：聚合根主记录（report_type='benchmark'，状态 published）
            aggregate = ReportAggregate(
                id=0,
                task_id=task_id or 0,
                name=name,
                report_type='benchmark',
                status='published',
                config={'name': name, 'description': command.description or '',
                        'benchmark': True, 'suite': suite, 'category': category,
                        'source': source},
            )
            report_id = self.report_repo.add(aggregate)

            try:
                # 摘要快照（复用报告 7 表结构；Benchmark 报告无用例统计，计数入 benchmark_reports）
                self.report_repo.add_summary(report_id, {
                    'total_cases': 0,
                    'completed_cases': 0,
                    'failed_cases': 0,
                    'pass_rate': 0,
                    'duration': 0,
                    'task_ids': [task_id] if task_id else None,
                })
                # 发布记录 + 排行快照
                version = self.repo.max_benchmark_report_version(suite, category) + 1
                record = self.repo.insert_benchmark_report({
                    'report_id': report_id,
                    'task_id': task_id,
                    'suite': suite,
                    'category': category,
                    'source': source,
                    'algorithm_set': (command.algorithm_set or '').strip(),
                    'published_task_count': counts['published_task_count'],
                    'subject_count': counts['subject_count'],
                    'metric_count': counts['metric_count'],
                    'ranking_data': snapshot,
                    'version': version,
                    # V9.7.10 兼容旧列（客户端自报仅作展示，非操作人依据）
                    'published_by': command.published_by or '',
                    # INT-844：发布操作人认证 user_id（AUTH_MODE=off → None → NULL）
                    'created_by_user_id': get_current_user_id(),
                })
            except Exception:
                # 快照落库失败：删除已建的报告主记录（含子表级联），避免半成品
                logger.exception('Benchmark 报告快照落库失败，回滚报告主记录 report_id=%s', report_id)
                try:
                    self.report_repo.hard_delete(report_id)
                except Exception:
                    logger.warning('回滚删除报告主记录失败 report_id=%s', report_id, exc_info=True)
                raise

            write_benchmark_audit(AuditEvent.BENCHMARK_REPORT_PUBLISHED, 'benchmark_report', {
                'report_id': report_id,
                'record_id': record.get('id'),
                'suite': suite,
                'category': category,
                'source': source,
                'published_task_count': counts['published_task_count'],
                'subject_count': counts['subject_count'],
                'metric_count': counts['metric_count'],
                'row_count': counts['row_count'],
                'version': record.get('version'),
                'published_by': command.published_by or '',
            })
            _emit_report_event('benchmark_report_published', {
                'reportId': report_id,
                'recordId': record.get('id'),
                'name': name,
                'suite': suite,
                'category': category,
                'source': source,
                'version': record.get('version'),
            })
            return {
                'success': True,
                'message': f'Benchmark 报告发布成功（v{record.get("version")}）',
                'data': record,
                'code': 0,
            }
        except Exception:
            logger.exception('Benchmark 报告发布失败')
            return {'success': False, 'message': '报告发布失败，请稍后重试',
                    'data': None, 'code': 301}


# 模块级默认实例（接口层使用；单测可自建实例注入替身）
benchmark_report_service = BenchmarkReportService()
