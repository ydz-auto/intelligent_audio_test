# -*- coding: utf-8 -*-
"""Benchmark 排行计算应用服务（D1 双轨排行写侧编排）

数据流（设计文档《报告Benchmark排行功能设计文档》§4.3）：
  数据源 A（platform_test）：task_service gRPC 拉取 benchmark=true 且 published
    的已发布任务 → 冻结报告快照 summary.dimensionValues 平台实测得分
  数据源 B（external_import）：benchmark_baselines 当前生效版本（is_current=true）
  合并 A + B → 指标映射解析（单一事实源 benchmark_metric_mappings）→
  按 (category, metric_code, scenario_key) 分组 → 6 算法计算 →
  benchmark_rankings ReadModel 整体刷新（同事务删旧插新）+ 审计

分组口径决策：suite 仅作行级展示元数据（外部基线无测试集概念），
排行分组键为 被测类别 + 指标 + 场景，保证双轨数据可合并排行（口径一致）。
双轨并存规则：同模型同指标既有实测又有导入时，排名以实测值参与排序，
无实测值时以导入值参与排序；delta = 实测值 - 导入值，两行同值承载。

严格 CQRS：本服务是排行 ReadModel 的唯一写入口；查询侧只读，无写副作用。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from report_service.application.commands.benchmark_commands import (
    ComputeBenchmarkRankingCommand,
)
from report_service.application.services.benchmark_audit import write_benchmark_audit
from report_service.config.config import Config
from report_service.domain.entities.benchmark import (
    MetricMapping,
    RankingDirection,
    RankingEntry,
    RankingSource,
)
from report_service.domain.services.benchmark_metric_mapper import (
    resolve_external_metric,
    resolve_platform_dimension,
)
from report_service.domain.services.benchmark_ranking_calculator import (
    calculate_ranking_metrics,
)
from shared.models.common_enums import AuditEvent

logger = logging.getLogger(__name__)

_SOURCE_VALUES = {source.value for source in RankingSource}


def _default_repo():
    from report_service.infrastructure.persistence.benchmark_repository import (
        BenchmarkRepositoryImpl,
    )
    return BenchmarkRepositoryImpl()


def _default_pt_acl():
    from report_service.infrastructure.acl.published_task_acl_repository import (
        PublishedTaskAclRepositoryImpl,
    )
    return PublishedTaskAclRepositoryImpl()


def _resolve_subject(summary: Dict[str, Any], fallback_name: str) -> Tuple[str, str, str]:
    """从报告快照 summary 解析被测主体（名称 / device_type / subject_type）。

    API 被测（http_api/websocket_api）优先，其次物理设备（APP，physical），
    均缺失时回退已发布任务名。
    """
    apis = [a for a in (summary.get('apis') or []) if isinstance(a, dict)]
    devices = [d for d in (summary.get('devices') or []) if isinstance(d, dict)]
    if apis:
        api = apis[0]
        raw_type = (api.get('type') or api.get('protocol') or 'http').lower()
        device_type = 'websocket_api' if 'websocket' in raw_type else 'http_api'
        return (api.get('name') or fallback_name, device_type, 'closed_source')
    if devices:
        device = devices[0]
        name = device.get('app_name') or device.get('name') or fallback_name
        return (name, 'physical', 'app')
    return (fallback_name, '', 'closed_source')


def _scenario_of(tags: Optional[List[str]]) -> str:
    """场景键：条目/映射提供场景标签时取第一个，否则回退默认场景。"""
    for tag in (tags or []):
        if tag and str(tag).strip():
            return str(tag).strip()
    return Config.BENCHMARK_DEFAULT_SCENARIO


class BenchmarkRankingService:
    """排行计算服务（可注入仓储与 ACL 替身，便于单测）。"""

    def __init__(self, repo=None, pt_acl=None):
        self._repo = repo
        self._pt_acl = pt_acl

    @property
    def repo(self):
        if self._repo is None:
            self._repo = _default_repo()
        return self._repo

    @property
    def pt_acl(self):
        if self._pt_acl is None:
            self._pt_acl = _default_pt_acl()
        return self._pt_acl

    # ---------- 双轨数据采集 ----------

    def _collect_platform_entries(
        self, command: ComputeBenchmarkRankingCommand,
        mappings_by_dimension: Dict[str, MetricMapping],
    ) -> Tuple[List[RankingEntry], List[Dict[str, Any]]]:
        """实测轨：已发布任务冻结报告快照 → RankingEntry 列表。

        无报告的已发布任务跳过并标记 no_report；维度无映射配置的指标
        跳过并标记 no_mapping（设计文档 §10）。
        """
        entries: List[RankingEntry] = []
        skipped: List[Dict[str, Any]] = []
        for pt in self.pt_acl.list_benchmark_published_tasks():
            if command.published_task_id and pt.get('id') != command.published_task_id:
                continue
            detail = self.pt_acl.get_published_task_detail(pt.get('id')) or {}
            snapshot = detail.get('report_snapshot') or {}
            summary = snapshot.get('summary') or {}
            dim_values = summary.get('dimensionValues') or []
            snapshot_config = detail.get('snapshot_config') or pt.get('snapshot_config') or {}
            suite = (snapshot_config.get('benchmarkSuite')
                     or Config.BENCHMARK_DEFAULT_SUITE)
            category = (snapshot_config.get('benchmarkCategory')
                        or Config.BENCHMARK_DEFAULT_CATEGORY)
            fallback_name = pt.get('name') or f"published-task-{pt.get('id')}"
            subject_name, device_type, subject_type = _resolve_subject(summary, fallback_name)
            if not dim_values:
                skipped.append({'subject': subject_name, 'reason': 'no_report',
                                'published_task_id': pt.get('id')})
                continue
            report_id = snapshot.get('reportId')
            for dim in dim_values:
                if not isinstance(dim, dict) or dim.get('average_value') is None:
                    continue
                mapping = resolve_platform_dimension(mappings_by_dimension, dim.get('name'))
                if mapping is None:
                    skipped.append({'subject': subject_name,
                                    'metric': dim.get('name'), 'reason': 'no_mapping'})
                    continue
                entries.append(RankingEntry(
                    source=RankingSource.PLATFORM_TEST,
                    subject_name=subject_name,
                    metric_code=mapping.metric_code,
                    metric_name=mapping.metric_name,
                    metric_value=float(dim['average_value']),
                    unit=mapping.unit,
                    direction=mapping.direction,
                    suite=suite,
                    category=category,
                    scenario_key=_scenario_of(mapping.scenario_tags),
                    subject_type=subject_type,
                    device_type=device_type,
                    published_task_id=pt.get('id'),
                    published_task_version=pt.get('version'),
                    report_id=report_id,
                ))
        return entries, skipped

    def _collect_external_entries(
        self, command: ComputeBenchmarkRankingCommand,
        mappings_by_code: Dict[str, MetricMapping],
    ) -> Tuple[List[RankingEntry], List[Dict[str, Any]]]:
        """基线轨：当前生效基线条目 → RankingEntry 列表。

        外部基线缺失映射的指标跳过并标记 no_mapping（验收边界）。
        """
        entries: List[RankingEntry] = []
        skipped: List[Dict[str, Any]] = []
        rows = self.repo.list_all_current_baselines(
            category=command.category or '', source_id=None)
        for row in rows:
            mapping = resolve_external_metric(mappings_by_code, row.get('metric_code'))
            if mapping is None:
                skipped.append({'subject': row.get('model_name'),
                                'metric': row.get('metric_code'), 'reason': 'no_mapping'})
                continue
            if row.get('value') is None:
                continue
            entries.append(RankingEntry(
                source=RankingSource.EXTERNAL_IMPORT,
                subject_name=row.get('model_name') or '',
                metric_code=mapping.metric_code,
                metric_name=mapping.metric_name,
                metric_value=float(row['value']),
                unit=mapping.unit or row.get('unit') or '',
                direction=mapping.direction,
                suite=Config.BENCHMARK_DEFAULT_SUITE,
                category=row.get('category') or '',
                scenario_key=_scenario_of(
                    row.get('scenario_tags') or mapping.scenario_tags),
                subject_type='closed_source',
                device_type='',
                baseline_id=row.get('id'),
            ))
        return entries, skipped

    # ---------- 分组与计算 ----------

    @staticmethod
    def _keep_latest_platform(entries: List[RankingEntry]) -> List[RankingEntry]:
        """同组同主体多条实测记录取最新版本参与排行（旧版本保留历史）。"""
        best: Dict[str, RankingEntry] = {}
        for entry in entries:
            key = entry.subject_name
            current = best.get(key)
            rank_key = (entry.published_task_version or 0, entry.published_task_id or 0)
            if current is None:
                best[key] = entry
                continue
            current_key = (current.published_task_version or 0, current.published_task_id or 0)
            if rank_key > current_key:
                best[key] = entry
        return list(best.values())

    def _build_group_rows(self, key: Tuple[str, str, str], entries: List[RankingEntry]) -> List[Dict[str, Any]]:
        """对同组条目做双轨合并与 6 算法计算，产出 ReadModel 行。"""
        category, metric_code, scenario_key = key
        direction = entries[0].direction
        platform_entries = [e for e in entries if e.source == RankingSource.PLATFORM_TEST]
        external_entries = [e for e in entries if e.source == RankingSource.EXTERNAL_IMPORT]

        subjects: Dict[str, Dict[str, RankingEntry]] = {}
        if platform_entries:
            for entry in self._keep_latest_platform(platform_entries):
                subjects.setdefault(entry.subject_name, {})['platform'] = entry
        if external_entries:
            for entry in external_entries:
                # 同主体同指标多国基线并存时取首条（当前版本内不重复约束）
                subjects.setdefault(entry.subject_name, {}).setdefault('external', entry)

        # 参与排序的值：实测优先，无实测时以导入值参与排序
        names = list(subjects.keys())
        values = []
        external_map: Dict[int, float] = {}
        for i, name in enumerate(names):
            pair = subjects[name]
            primary = pair.get('platform') or pair.get('external')
            values.append(primary.metric_value)
            if 'platform' in pair and 'external' in pair:
                external_map[i] = pair['external'].metric_value

        metrics = calculate_ranking_metrics(values, direction, external_map or None)

        rows: List[Dict[str, Any]] = []
        now = datetime.now()
        for i, name in enumerate(names):
            m = metrics[i]
            pair = subjects[name]
            for source_key in ('platform', 'external'):
                entry = pair.get(source_key)
                if entry is None:
                    continue
                rows.append({
                    'source': entry.source.value,
                    'published_task_id': entry.published_task_id,
                    'published_task_version': entry.published_task_version,
                    'report_id': entry.report_id,
                    'baseline_id': entry.baseline_id,
                    'subject_name': entry.subject_name,
                    'subject_type': entry.subject_type,
                    'device_type': entry.device_type,
                    'benchmark_suite': entry.suite,
                    'category': entry.category,
                    'metric_code': entry.metric_code,
                    'metric_name': entry.metric_name,
                    'metric_value': entry.metric_value,
                    'unit': entry.unit,
                    'direction': entry.direction.value,
                    'rank': m.rank,
                    'total': m.total,
                    'percentile': m.percentile,
                    'score100': m.score100,
                    'gap_best': m.gap_best,
                    'gap_median': m.gap_median,
                    'delta_external': m.delta_external,
                    'scenario_key': entry.scenario_key,
                    'computed_at': now,
                })
        return rows

    # ---------- 入口 ----------

    def compute_ranking(self, command: ComputeBenchmarkRankingCommand) -> Dict[str, Any]:
        """排行计算：合并双轨 → 映射 → 分组 → 6 算法 → ReadModel 刷新 + 审计。"""
        try:
            if command.source and command.source not in _SOURCE_VALUES:
                return {'success': False, 'message': f'非法数据来源: {command.source}',
                        'data': None, 'code': 100}

            mappings = self.repo.list_metric_mappings(active_only=True)
            mappings_by_dimension = {m.dimension_name: m for m in mappings}
            mappings_by_code = {m.metric_code: m for m in mappings}

            entries: List[RankingEntry] = []
            skipped: List[Dict[str, Any]] = []
            if not command.source or command.source == RankingSource.PLATFORM_TEST.value:
                platform_entries, platform_skipped = self._collect_platform_entries(
                    command, mappings_by_dimension)
                entries.extend(platform_entries)
                skipped.extend(platform_skipped)
            if not command.source or command.source == RankingSource.EXTERNAL_IMPORT.value:
                external_entries, external_skipped = self._collect_external_entries(
                    command, mappings_by_code)
                entries.extend(external_entries)
                skipped.extend(external_skipped)

            if command.category:
                entries = [e for e in entries if e.category == command.category]
            if command.suite:
                entries = [e for e in entries if e.suite == command.suite]

            groups: Dict[Tuple[str, str, str], List[RankingEntry]] = {}
            for entry in entries:
                groups.setdefault(
                    (entry.category, entry.metric_code, entry.scenario_key), [],
                ).append(entry)

            rows: List[Dict[str, Any]] = []
            group_summaries: List[Dict[str, Any]] = []
            refresh_keys: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
            for key, group_entries in groups.items():
                category, metric_code, scenario_key = key
                group_rows = self._build_group_rows(key, group_entries)
                if not group_rows:
                    continue
                rows.extend(group_rows)
                # 混合来源组按 source 拆分刷新键
                for source_value in {row['source'] for row in group_rows}:
                    refresh_keys[(category, metric_code, scenario_key, source_value)] = {
                        'category': category,
                        'metric_code': metric_code,
                        'scenario_key': scenario_key,
                        'source': source_value,
                    }
                group_summaries.append({
                    'category': category,
                    'metric_code': metric_code,
                    'scenario_key': scenario_key,
                    'subjects': len({row['subject_name'] for row in group_rows}),
                    'rows': len(group_rows),
                })

            unique_keys = list(refresh_keys.values())

            written = self.repo.replace_ranking_rows(unique_keys, rows)
            computed_at = datetime.now().isoformat()
            write_benchmark_audit(AuditEvent.BENCHMARK_RANKING_COMPUTED, 'benchmark_ranking', {
                'rows_written': written,
                'group_count': len(unique_keys),
                'suite': command.suite or '',
                'category': command.category or '',
                'published_task_id': command.published_task_id or '',
                'source': command.source or '',
            })
            return {
                'success': True,
                'message': f'排行计算完成：{len(unique_keys)} 组 / {written} 行',
                'data': {
                    'rows_written': written,
                    'group_count': len(unique_keys),
                    'groups': group_summaries,
                    'skipped': skipped,
                    'computed_at': computed_at,
                },
                'code': 0,
            }
        except Exception as e:
            logger.exception('Benchmark 排行计算失败')
            return {'success': False, 'message': f'排行计算失败: {e}', 'data': None, 'code': 301}


# 模块级默认实例（接口层使用；单测可自建实例注入替身）
benchmark_ranking_service = BenchmarkRankingService()
