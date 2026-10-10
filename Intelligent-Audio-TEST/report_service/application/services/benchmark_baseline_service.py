# -*- coding: utf-8 -*-
"""Benchmark 外部基线应用服务（D1 轨 2 写侧编排）

导入即不可变快照（设计文档 §4.2 + INT-27 验收标准 3）：
- 逐行校验（模型名 / 指标代码 / 数值 / 方向；映射存在时单位方向必须与映射一致）
- 合法行作为新版本一次性入库（version = 当前最大版本 + 1，is_current=True，
  同源同类别旧当前版本翻转 False），版本行只插不改
- 内容重复的重复导入幂等：与既有任一版本内容完全一致时直接返回该版本，
  不产生新版本、不翻转 is_current
- 校验失败按行返回错误明细 {row, field, message}，不阻断合法行
"""
from __future__ import annotations

import logging
import math
import threading
from typing import Any, Dict, List, Optional, Tuple

from report_service.application.commands.benchmark_commands import (
    CreateBenchmarkMetricMappingCommand,
    CreateBenchmarkSourceCommand,
    ImportBenchmarkBaselinesCommand,
    UpdateBenchmarkMetricMappingCommand,
)
from report_service.application.services.benchmark_audit import write_benchmark_audit
from report_service.domain.entities.benchmark import (
    BaselineDraftEntry,
    BenchmarkCategory,
    BenchmarkSourceType,
)
from report_service.domain.services.benchmark_metric_mapper import normalize_direction
from shared.models.common_enums import AuditEvent

logger = logging.getLogger(__name__)

# 导入串行化（进程内）：版本分配已由仓储行锁保证，此处避免同源多批次
# 并发导入在幂等检查与建版本之间交错
_IMPORT_LOCK = threading.Lock()


def _default_repo():
    from report_service.infrastructure.persistence.benchmark_repository import (
        BenchmarkRepositoryImpl,
    )
    return BenchmarkRepositoryImpl()


def _baseline_identity(row: Dict[str, Any]) -> Tuple:
    """基线行内容指纹（幂等比对用；metric_name 为展示元数据不参与）。"""
    return (
        (row.get('model_name') or '').strip(),
        (row.get('vendor') or '').strip(),
        (row.get('metric_code') or '').strip(),
        float(row.get('value')),
        (row.get('unit') or '').strip(),
        (row.get('direction') or '').strip(),
        tuple(sorted(row.get('scenario_tags') or [])),
        row.get('sample_size'),
        (row.get('metric_date') or '').strip(),
    )


class BenchmarkBaselineService:
    """外部基线导入 / 数据源 / 指标映射写侧服务（可注入仓储替身）。"""

    def __init__(self, repo=None):
        self._repo = repo

    @property
    def repo(self):
        if self._repo is None:
            self._repo = _default_repo()
        return self._repo

    # ---------- 数据源 ----------

    def create_source(self, command: CreateBenchmarkSourceCommand) -> Dict[str, Any]:
        name = (command.name or '').strip()
        if not name:
            return {'success': False, 'message': '数据源名称不能为空', 'data': None, 'code': 100}
        source_type = (command.source_type or BenchmarkSourceType.MANUAL.value).strip().lower()
        valid_types = {t.value for t in BenchmarkSourceType}
        if source_type not in valid_types:
            return {'success': False,
                    'message': f'source_type 非法，仅支持: {", ".join(sorted(valid_types))}',
                    'data': None, 'code': 101}
        try:
            source = self.repo.create_source({
                'name': name,
                'provider': (command.provider or '').strip(),
                'source_type': source_type,
                'url': (command.url or '').strip(),
                'version': (command.version or '').strip(),
                'description': command.description or '',
                'created_by': command.created_by or '',
            })
            return {'success': True, 'message': '数据源创建成功', 'data': source, 'code': 201}
        except Exception:
            logger.exception('创建外部基线数据源失败')
            return {'success': False, 'message': '创建数据源失败，请稍后重试',
                    'data': None, 'code': 301}

    # ---------- 基线导入（不可变版本快照 + 幂等） ----------

    def _validate_entry(
        self, index: int, entry: BaselineDraftEntry, mappings_by_code: Dict[str, Any],
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """逐行校验。返回 (入库行, 错误)；合法行返回 (row, None)，非法行 (None, error)。"""
        row_index = index + 1
        model_name = (entry.model_name or '').strip()
        if not model_name:
            return None, {'row': row_index, 'field': 'model_name', 'message': '模型名不能为空'}
        metric_code = (entry.metric_code or '').strip()
        if not metric_code:
            return None, {'row': row_index, 'field': 'metric_code', 'message': '指标代码不能为空'}
        if entry.value is None:
            return None, {'row': row_index, 'field': 'value', 'message': '指标值不能为空'}
        try:
            value = float(entry.value)
        except (TypeError, ValueError):
            return None, {'row': row_index, 'field': 'value', 'message': '指标值必须为数值'}
        if not math.isfinite(value):
            return None, {'row': row_index, 'field': 'value',
                          'message': '指标值必须为有限数值（不允许 NaN/Infinity）'}
        direction = normalize_direction(entry.direction or '')
        if direction is None:
            return None, {
                'row': row_index, 'field': 'direction',
                'message': '方向非法，仅支持 lower_is_better / higher_is_better',
            }
        unit = (entry.unit or '').strip()
        scenario_tags = [str(t).strip() for t in (entry.scenario_tags or []) if str(t).strip()]
        sample_size = entry.sample_size
        if sample_size is not None:
            try:
                sample_size = int(sample_size)
            except (TypeError, ValueError):
                return None, {'row': row_index, 'field': 'sample_size',
                              'message': '采样规模必须为整数'}
        metric_date = (entry.metric_date or '').strip()

        mapping = mappings_by_code.get(metric_code)
        if mapping is not None:
            # 单位/方向不一致：映射配置校验拦截，不允许入库（设计文档 §10）
            if direction.value != mapping.direction.value:
                return None, {
                    'row': row_index, 'field': 'direction',
                    'message': f'方向与映射配置不一致（映射: {mapping.direction.value}）',
                }
            if unit and mapping.unit and unit != mapping.unit:
                return None, {
                    'row': row_index, 'field': 'unit',
                    'message': f'单位与映射配置不一致（映射: {mapping.unit}）',
                }
            unit = unit or mapping.unit
            metric_name = (entry.metric_name or '').strip() or mapping.metric_name
            scenario_tags = scenario_tags or list(mapping.scenario_tags)
        else:
            metric_name = (entry.metric_name or '').strip() or metric_code

        return {
            'model_name': model_name,
            'vendor': (entry.vendor or '').strip(),
            'metric_code': metric_code,
            'metric_name': metric_name,
            'value': value,
            'unit': unit,
            'direction': direction.value,
            'scenario_tags': scenario_tags,
            'sample_size': sample_size,
            'metric_date': metric_date,
        }, None

    def import_baselines(self, command: ImportBenchmarkBaselinesCommand) -> Dict[str, Any]:
        try:
            with _IMPORT_LOCK:
                return self._import_baselines_locked(command)
        except Exception:
            logger.exception('外部基线导入失败')
            return {'success': False, 'message': '基线导入失败，请稍后重试',
                    'data': None, 'code': 301}

    def _import_baselines_locked(self, command: ImportBenchmarkBaselinesCommand) -> Dict[str, Any]:
        source = self.repo.get_source(command.source_id)
        if source is None:
            return {'success': False, 'message': '数据源不存在', 'data': None, 'code': 201}
        category = (command.category or '').strip().lower()
        valid_categories = {c.value for c in BenchmarkCategory}
        if category not in valid_categories:
            return {'success': False,
                    'message': f'被测类别非法，仅支持: {", ".join(sorted(valid_categories))}',
                    'data': None, 'code': 102}
        if not command.entries:
            return {'success': False, 'message': '导入条目为空', 'data': None, 'code': 103}

        mappings_by_code = {
            m.metric_code: m for m in self.repo.list_metric_mappings(active_only=True)
        }

        errors: List[Dict[str, Any]] = []
        rows: List[Dict[str, Any]] = []
        for index, entry in enumerate(command.entries):
            row, error = self._validate_entry(index, entry, mappings_by_code)
            if error:
                errors.append(error)
            else:
                row['source_id'] = command.source_id
                row['category'] = category
                rows.append(row)

        if not rows:
            return {
                'success': False,
                'message': '全部条目校验失败，未入库',
                'data': {'errors': errors, 'imported': 0},
                'code': 104,
            }

        # 幂等：合法行内容与既有任一版本完全一致 → 返回该版本，不新建
        existing_versions = self.repo.list_baseline_versions(command.source_id, category)
        new_identity = {_baseline_identity(row) for row in rows}
        for version_info in existing_versions:
            existing_rows = self.repo.get_baseline_rows(
                command.source_id, category, version_info['version'])
            if {_baseline_identity(r) for r in existing_rows} == new_identity:
                return {
                    'success': True,
                    'message': f'重复导入，幂等返回已有版本 v{version_info["version"]}',
                    'data': {
                        'source_id': command.source_id,
                        'category': category,
                        'version': version_info['version'],
                        'is_new_version': False,
                        'entry_count': len(rows),
                        'errors': errors,
                        'imported': 0,
                    },
                    'code': 0,
                }

        # 版本号由仓储在行锁事务内分配（并发导入防重复版本号 / 双 is_current）
        inserted = self.repo.insert_baseline_version(
            rows, demote_source_id=command.source_id, demote_category=category)
        next_version = inserted['version']
        inserted_ids = inserted['ids']

        write_benchmark_audit(AuditEvent.BENCHMARK_BASELINE_IMPORTED, 'benchmark_baseline', {
            'source_id': command.source_id,
            'source_name': source.get('name'),
            'category': category,
            'version': next_version,
            'entry_count': len(inserted_ids),
            'error_count': len(errors),
            'published_by': command.published_by or '',
        })
        return {
            'success': True,
            'message': f'基线导入成功：v{next_version}（{len(inserted_ids)} 条，{len(errors)} 行校验失败）',
            'data': {
                'source_id': command.source_id,
                'category': category,
                'version': next_version,
                'is_new_version': True,
                'entry_count': len(inserted_ids),
                'errors': errors,
                'imported': len(inserted_ids),
            },
            'code': 201,
        }

    # ---------- 指标映射 ----------

    def create_metric_mapping(self, command: CreateBenchmarkMetricMappingCommand) -> Dict[str, Any]:
        try:
            dimension_name = (command.dimension_name or '').strip()
            if not dimension_name:
                return {'success': False, 'message': '系统维度名不能为空', 'data': None, 'code': 100}
            metric_code = (command.metric_code or '').strip()
            if not metric_code:
                return {'success': False, 'message': '排行指标代码不能为空', 'data': None, 'code': 100}
            direction = normalize_direction(command.direction or '')
            if direction is None:
                return {'success': False,
                        'message': '方向非法，仅支持 lower_is_better / higher_is_better',
                        'data': None, 'code': 100}
            existing = self.repo.list_metric_mappings(active_only=False)
            if any(m.dimension_name == dimension_name for m in existing):
                return {'success': False,
                        'message': f'系统维度 {dimension_name} 已存在映射配置（同一维度仅一条映射）',
                        'data': None, 'code': 409}
            mapping = self.repo.create_metric_mapping({
                'dimension_name': dimension_name,
                'metric_code': metric_code,
                'metric_name': (command.metric_name or '').strip(),
                'unit': (command.unit or '').strip(),
                'direction': direction.value,
                'scenario_tags': [str(t).strip() for t in (command.scenario_tags or []) if str(t).strip()],
                'active': bool(command.active),
            })
            write_benchmark_audit(AuditEvent.BENCHMARK_MAPPING_CREATED, 'benchmark_mapping', {
                'mapping_id': mapping.id,
                'dimension_name': mapping.dimension_name,
                'metric_code': mapping.metric_code,
                'direction': mapping.direction.value,
                'unit': mapping.unit,
            })
            return {'success': True, 'message': '指标映射已创建',
                    'data': {'id': mapping.id, 'dimension_name': mapping.dimension_name,
                             'metric_code': mapping.metric_code, 'metric_name': mapping.metric_name,
                             'direction': mapping.direction.value, 'unit': mapping.unit,
                             'scenario_tags': mapping.scenario_tags, 'active': mapping.active},
                    'code': 201}
        except Exception:
            logger.exception('创建指标映射失败')
            return {'success': False, 'message': '创建指标映射失败，请稍后重试',
                    'data': None, 'code': 301}

    def update_metric_mapping(self, command: UpdateBenchmarkMetricMappingCommand) -> Dict[str, Any]:
        try:
            updates: Dict[str, Any] = {}
            if command.metric_name is not None:
                updates['metric_name'] = command.metric_name.strip()
            if command.unit is not None:
                updates['unit'] = command.unit.strip()
            if command.direction is not None:
                direction = normalize_direction(command.direction)
                if direction is None:
                    return {'success': False,
                            'message': '方向非法，仅支持 lower_is_better / higher_is_better',
                            'data': None, 'code': 100}
                updates['direction'] = direction.value
            if command.scenario_tags is not None:
                updates['scenario_tags'] = [
                    str(t).strip() for t in command.scenario_tags if str(t).strip()]
            if command.active is not None:
                updates['active'] = bool(command.active)
            if not updates:
                return {'success': False, 'message': '无可更新的字段', 'data': None, 'code': 101}
            mapping = self.repo.update_metric_mapping(command.mapping_id, updates)
            if mapping is None:
                return {'success': False, 'message': '指标映射不存在', 'data': None, 'code': 201}
            write_benchmark_audit(AuditEvent.BENCHMARK_MAPPING_UPDATED, 'benchmark_mapping', {
                'mapping_id': mapping.id,
                'dimension_name': mapping.dimension_name,
                'metric_code': mapping.metric_code,
                'updates': updates,
            })
            return {'success': True, 'message': '指标映射已更新',
                    'data': {'id': mapping.id, 'dimension_name': mapping.dimension_name,
                             'metric_code': mapping.metric_code, 'direction': mapping.direction.value,
                             'unit': mapping.unit, 'scenario_tags': mapping.scenario_tags,
                             'active': mapping.active}, 'code': 0}
        except Exception:
            logger.exception('更新指标映射失败')
            return {'success': False, 'message': '更新指标映射失败，请稍后重试',
                    'data': None, 'code': 301}


# 模块级默认实例（接口层使用；单测可自建实例注入替身）
benchmark_baseline_service = BenchmarkBaselineService()
