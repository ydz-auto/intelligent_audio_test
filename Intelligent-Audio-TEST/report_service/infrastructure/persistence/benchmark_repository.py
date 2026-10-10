# -*- coding: utf-8 -*-
"""Benchmark 排行仓储 — SQLAlchemy 实现

实现 report_service/domain/repositories/benchmark_repository_abc.py。
benchmark_rankings 为 ReadModel：写侧整体刷新（同事务删旧插新），读侧只读。
benchmark_baselines 为不可变快照：行只插不改，版本翻转用 is_current 布尔位。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import func

from shared.models.database import get_db_session
from report_service.domain.entities.benchmark import MetricMapping, RankingDirection
from report_service.domain.repositories.benchmark_repository_abc import (
    BenchmarkRepository,
)
from report_service.infrastructure.persistence.models import (
    BenchmarkBaseline,
    BenchmarkMetricMapping,
    BenchmarkRanking,
    BenchmarkSource,
)

logger = logging.getLogger(__name__)


def _mapping_to_entity(po: BenchmarkMetricMapping) -> MetricMapping:
    return MetricMapping(
        id=po.id,
        dimension_name=po.dimension_name,
        metric_code=po.metric_code,
        metric_name=po.metric_name or po.dimension_name,
        unit=po.unit or '',
        direction=RankingDirection(po.direction),
        scenario_tags=list(po.scenario_tags or []),
        active=bool(po.active),
    )


def _row_dict(po) -> Dict[str, Any]:
    return {
        'id': po.id,
        'source': po.source,
        'published_task_id': po.published_task_id,
        'published_task_version': po.published_task_version,
        'report_id': po.report_id,
        'baseline_id': po.baseline_id,
        'subject_name': po.subject_name,
        'subject_type': po.subject_type,
        'device_type': po.device_type,
        'benchmark_suite': po.benchmark_suite,
        'category': po.category,
        'metric_code': po.metric_code,
        'metric_name': po.metric_name,
        'metric_value': po.metric_value,
        'unit': po.unit,
        'direction': po.direction,
        'rank': po.rank,
        'total': po.total,
        'percentile': po.percentile,
        'score100': po.score100,
        'gap_best': po.gap_best,
        'gap_median': po.gap_median,
        'delta_external': po.delta_external,
        'scenario_key': po.scenario_key,
        'computed_at': po.computed_at.isoformat() if po.computed_at else None,
    }


def _baseline_row_dict(po: BenchmarkBaseline) -> Dict[str, Any]:
    return {
        'id': po.id,
        'source_id': po.source_id,
        'category': po.category,
        'model_name': po.model_name,
        'vendor': po.vendor,
        'metric_code': po.metric_code,
        'metric_name': po.metric_name,
        'value': po.value,
        'unit': po.unit,
        'direction': po.direction,
        'scenario_tags': list(po.scenario_tags or []),
        'sample_size': po.sample_size,
        'metric_date': po.metric_date,
        'version': po.version,
        'is_current': bool(po.is_current),
        'created_at': po.created_at.isoformat() if po.created_at else None,
    }


class BenchmarkRepositoryImpl(BenchmarkRepository):
    """Benchmark 排行仓储实现。"""

    # ---------- 排行 ReadModel（写侧） ----------

    def replace_ranking_rows(self, group_keys: List[Dict[str, Any]], rows: List[Dict[str, Any]]) -> int:
        session = get_db_session()
        try:
            for key in group_keys:
                session.query(BenchmarkRanking).filter(
                    BenchmarkRanking.category == key['category'],
                    BenchmarkRanking.metric_code == key['metric_code'],
                    BenchmarkRanking.scenario_key == key['scenario_key'],
                    BenchmarkRanking.source == key['source'],
                ).delete(synchronize_session=False)
            for row in rows:
                session.add(BenchmarkRanking(**row))
            session.commit()
            return len(rows)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ---------- 排行 ReadModel（读侧） ----------

    def query_rankings(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        session = get_db_session()
        try:
            query = session.query(BenchmarkRanking)
            if filters.get('suite'):
                query = query.filter(BenchmarkRanking.benchmark_suite == filters['suite'])
            if filters.get('category'):
                query = query.filter(BenchmarkRanking.category == filters['category'])
            if filters.get('metric_code'):
                query = query.filter(BenchmarkRanking.metric_code == filters['metric_code'])
            if filters.get('source'):
                query = query.filter(BenchmarkRanking.source == filters['source'])
            if filters.get('published_task_id') is not None:
                query = query.filter(
                    BenchmarkRanking.published_task_id == int(filters['published_task_id']))
            if filters.get('subject_name'):
                query = query.filter(BenchmarkRanking.subject_name == filters['subject_name'])
            query = query.order_by(
                BenchmarkRanking.benchmark_suite, BenchmarkRanking.category,
                BenchmarkRanking.metric_code, BenchmarkRanking.rank,
            )
            return [_row_dict(po) for po in query.all()]
        finally:
            session.close()

    def list_ranking_subjects(self, suite: Optional[str] = None) -> List[str]:
        session = get_db_session()
        try:
            query = session.query(BenchmarkRanking.subject_name).distinct()
            if suite:
                query = query.filter(BenchmarkRanking.benchmark_suite == suite)
            return [row[0] for row in query.order_by(BenchmarkRanking.subject_name).all()]
        finally:
            session.close()

    # ---------- 指标映射 ----------

    def list_metric_mappings(self, active_only: bool = False) -> List[MetricMapping]:
        session = get_db_session()
        try:
            query = session.query(BenchmarkMetricMapping)
            if active_only:
                query = query.filter(BenchmarkMetricMapping.active.is_(True))
            return [_mapping_to_entity(po) for po in query.order_by(BenchmarkMetricMapping.id).all()]
        finally:
            session.close()

    def get_metric_mapping(self, mapping_id: int) -> Optional[MetricMapping]:
        session = get_db_session()
        try:
            po = session.query(BenchmarkMetricMapping).filter(
                BenchmarkMetricMapping.id == int(mapping_id)).first()
            return _mapping_to_entity(po) if po else None
        finally:
            session.close()

    def create_metric_mapping(self, data: Dict[str, Any]) -> MetricMapping:
        session = get_db_session()
        try:
            po = BenchmarkMetricMapping(
                dimension_name=data['dimension_name'],
                metric_code=data['metric_code'],
                metric_name=data.get('metric_name') or data['dimension_name'],
                unit=data.get('unit') or '',
                direction=data['direction'],
                scenario_tags=data.get('scenario_tags') or [],
                active=bool(data.get('active', True)),
            )
            session.add(po)
            session.commit()
            session.refresh(po)
            return _mapping_to_entity(po)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def update_metric_mapping(self, mapping_id: int, updates: Dict[str, Any]) -> Optional[MetricMapping]:
        session = get_db_session()
        try:
            po = session.query(BenchmarkMetricMapping).filter(
                BenchmarkMetricMapping.id == int(mapping_id)).first()
            if po is None:
                return None
            allowed = ('metric_name', 'unit', 'direction', 'scenario_tags', 'active')
            for field_name in allowed:
                if field_name in updates and updates[field_name] is not None:
                    setattr(po, field_name, updates[field_name])
            session.commit()
            session.refresh(po)
            return _mapping_to_entity(po)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ---------- 外部基线数据源 ----------

    def create_source(self, data: Dict[str, Any]) -> Dict[str, Any]:
        session = get_db_session()
        try:
            po = BenchmarkSource(
                name=data['name'],
                provider=data.get('provider'),
                source_type=data.get('source_type') or 'manual',
                url=data.get('url'),
                version=data.get('version'),
                description=data.get('description'),
                created_by=data.get('created_by'),
            )
            session.add(po)
            session.commit()
            session.refresh(po)
            return {
                'id': po.id,
                'name': po.name,
                'provider': po.provider,
                'source_type': po.source_type,
                'url': po.url,
                'version': po.version,
                'description': po.description,
                'created_by': po.created_by,
                'created_at': po.created_at.isoformat() if po.created_at else None,
            }
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_source(self, source_id: int) -> Optional[Dict[str, Any]]:
        session = get_db_session()
        try:
            po = session.query(BenchmarkSource).filter(
                BenchmarkSource.id == int(source_id)).first()
            if po is None:
                return None
            return {
                'id': po.id,
                'name': po.name,
                'provider': po.provider,
                'source_type': po.source_type,
                'url': po.url,
                'version': po.version,
                'description': po.description,
                'created_by': po.created_by,
                'created_at': po.created_at.isoformat() if po.created_at else None,
            }
        finally:
            session.close()

    def list_sources(self, page: int, per_page: int, source_type: str = '') -> Dict[str, Any]:
        session = get_db_session()
        try:
            query = session.query(BenchmarkSource)
            if source_type:
                query = query.filter(BenchmarkSource.source_type == source_type)
            total = query.count()
            rows = (
                query.order_by(BenchmarkSource.id.desc())
                .offset((page - 1) * per_page)
                .limit(per_page)
                .all()
            )
            items = [
                {
                    'id': po.id,
                    'name': po.name,
                    'provider': po.provider,
                    'source_type': po.source_type,
                    'url': po.url,
                    'version': po.version,
                    'description': po.description,
                    'created_by': po.created_by,
                    'created_at': po.created_at.isoformat() if po.created_at else None,
                }
                for po in rows
            ]
            return {
                'items': items,
                'total': total,
                'page': page,
                'per_page': per_page,
                'pages': (total + per_page - 1) // per_page if total else 0,
            }
        finally:
            session.close()

    # ---------- 外部基线条目（不可变快照版本） ----------

    def list_baseline_versions(self, source_id: int, category: str) -> List[Dict[str, Any]]:
        session = get_db_session()
        try:
            rows = (
                session.query(
                    BenchmarkBaseline.version,
                    func.max(BenchmarkBaseline.is_current).label('is_current'),
                    func.count(BenchmarkBaseline.id).label('entry_count'),
                    func.min(BenchmarkBaseline.created_at).label('created_at'),
                )
                .filter(
                    BenchmarkBaseline.source_id == int(source_id),
                    BenchmarkBaseline.category == category,
                )
                .group_by(BenchmarkBaseline.version)
                .order_by(BenchmarkBaseline.version.desc())
                .all()
            )
            return [
                {
                    'version': row.version,
                    'is_current': bool(row.is_current),
                    'entry_count': int(row.entry_count),
                    'created_at': row.created_at.isoformat() if row.created_at else None,
                }
                for row in rows
            ]
        finally:
            session.close()

    def get_baseline_rows(self, source_id: int, category: str, version: int) -> List[Dict[str, Any]]:
        session = get_db_session()
        try:
            rows = session.query(BenchmarkBaseline).filter(
                BenchmarkBaseline.source_id == int(source_id),
                BenchmarkBaseline.category == category,
                BenchmarkBaseline.version == int(version),
            ).all()
            return [_baseline_row_dict(po) for po in rows]
        finally:
            session.close()

    def insert_baseline_version(
        self, rows: List[Dict[str, Any]], demote_source_id: int, demote_category: str,
    ) -> Dict[str, Any]:
        session = get_db_session()
        try:
            # 数据源行锁串行化同源同类并发导入：版本号在锁内分配，
            # 杜绝并发重复 version 号 / 双 is_current
            session.query(BenchmarkSource).filter(
                BenchmarkSource.id == int(demote_source_id),
            ).with_for_update().one()
            # 同事务：同源同类旧当前版本翻转 False → 新行 is_current=True（快照切换）
            session.query(BenchmarkBaseline).filter(
                BenchmarkBaseline.source_id == int(demote_source_id),
                BenchmarkBaseline.category == demote_category,
                BenchmarkBaseline.is_current.is_(True),
            ).update({'is_current': False}, synchronize_session=False)
            next_version = (
                session.query(func.max(BenchmarkBaseline.version)).filter(
                    BenchmarkBaseline.source_id == int(demote_source_id),
                    BenchmarkBaseline.category == demote_category,
                ).scalar() or 0
            ) + 1
            pos = [
                BenchmarkBaseline(
                    version=next_version, is_current=True,
                    **{k: v for k, v in row.items()
                       if k not in ('version', 'is_current')},
                )
                for row in rows
            ]
            session.add_all(pos)
            session.commit()
            return {'version': next_version, 'ids': [po.id for po in pos]}
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def list_current_baselines(
        self, category: str = '', metric_code: str = '', source_id: Optional[int] = None,
        page: int = 1, per_page: int = 20,
    ) -> Dict[str, Any]:
        session = get_db_session()
        try:
            query = session.query(BenchmarkBaseline).filter(
                BenchmarkBaseline.is_current.is_(True))
            if category:
                query = query.filter(BenchmarkBaseline.category == category)
            if metric_code:
                query = query.filter(BenchmarkBaseline.metric_code == metric_code)
            if source_id is not None:
                query = query.filter(BenchmarkBaseline.source_id == int(source_id))
            total = query.count()
            rows = (
                query.order_by(BenchmarkBaseline.category, BenchmarkBaseline.metric_code,
                               BenchmarkBaseline.model_name)
                .offset((page - 1) * per_page)
                .limit(per_page)
                .all()
            )
            return {
                'items': [_baseline_row_dict(po) for po in rows],
                'total': total,
                'page': page,
                'per_page': per_page,
                'pages': (total + per_page - 1) // per_page if total else 0,
            }
        finally:
            session.close()

    def list_all_current_baselines(
        self, category: str = '', metric_code: str = '', source_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        session = get_db_session()
        try:
            query = session.query(BenchmarkBaseline).filter(
                BenchmarkBaseline.is_current.is_(True))
            if category:
                query = query.filter(BenchmarkBaseline.category == category)
            if metric_code:
                query = query.filter(BenchmarkBaseline.metric_code == metric_code)
            if source_id is not None:
                query = query.filter(BenchmarkBaseline.source_id == int(source_id))
            rows = query.order_by(
                BenchmarkBaseline.category, BenchmarkBaseline.metric_code,
                BenchmarkBaseline.model_name,
            ).all()
            return [_baseline_row_dict(po) for po in rows]
        finally:
            session.close()
