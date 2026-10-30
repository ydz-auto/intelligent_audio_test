# -*- coding: utf-8 -*-
"""参数策略仓储（ACL：只暴露 dict，不把 ORM 漏给上层）。

- ``ParamProfileRepository``：供 ``config_cache`` 全量重载（只读）；
- ``ParamProfileCommandRepository``：策略保存/克隆/删除/绑定/实例覆盖（写）。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from shared.models.database import get_db_session

from algorithm_service.infrastructure.persistence.models import (
    ApiParamBinding,
    ParamProfile,
    ParamProfileMapping,
    ParamProfileParam,
)
from algorithm_service.infrastructure.persistence._param_converters import _po_to_dict


class ParamProfileRepository:
    """策略只读仓储（重载用）。"""

    def load_active(self) -> Tuple[List[Dict[str, Any]], Dict[int, List[Dict[str, Any]]],
                                    Dict[int, List[Dict[str, Any]]]]:
        """返回 (策略列表, profile_id→字段声明, profile_id→映射)。"""
        session = get_db_session()
        profiles = [
            _po_to_dict(po)
            for po in session.query(ParamProfile).filter_by(deleted=False).all()
        ]
        params: Dict[int, List[Dict[str, Any]]] = {}
        for po in session.query(ParamProfileParam).filter_by(deleted=False).all():
            params.setdefault(po.profile_id, []).append(_po_to_dict(po))
        mappings: Dict[int, List[Dict[str, Any]]] = {}
        for po in session.query(ParamProfileMapping).filter_by(deleted=False).all():
            mappings.setdefault(po.profile_id, []).append(_po_to_dict(po))
        return profiles, params, mappings

    def load_profiles_by_types(self, algorithm_types: List[str]) -> List[Dict[str, Any]]:
        """按算法类型批量读取策略（切片重载用；空列表不发 IN 查询）。"""
        types = [t for t in algorithm_types or [] if t]
        if not types:
            return []
        session = get_db_session()
        rows = session.query(ParamProfile).filter(
            ParamProfile.deleted.is_(False),
            ParamProfile.algorithm_type.in_(types),
        ).all()
        return [_po_to_dict(po) for po in rows]

    def load_bindings(self) -> Dict[int, int]:
        """返回 api_id → profile_id（仅未删除绑定）。"""
        session = get_db_session()
        rows = session.query(ApiParamBinding).filter_by(deleted=False).all()
        return {po.api_id: po.profile_id for po in rows}

    def list_bindings(self, profile_ids: List[int]) -> List[Dict[str, Any]]:
        """按策略 id 批量读取绑定（仅未删除）；空列表不发 IN 查询。"""
        if not profile_ids:
            return []
        session = get_db_session()
        rows = session.query(ApiParamBinding).filter(
            ApiParamBinding.deleted.is_(False),
            ApiParamBinding.profile_id.in_([int(pid) for pid in profile_ids]),
        ).all()
        return [{'api_id': po.api_id, 'profile_id': po.profile_id} for po in rows]


class ParamProfileCommandRepository:
    """策略写仓储（保存 / 克隆 / 删除 / 绑定 / 实例覆盖）。

    所有方法自行 commit，异常回滚；只操作本服务拥有的四张表。
    """

    # ---- 读 ----

    def list(self, algorithm_type: Optional[str] = None,
             scope: Optional[str] = None) -> List[Dict[str, Any]]:
        session = get_db_session()
        query = session.query(ParamProfile).filter_by(deleted=False)
        if algorithm_type:
            query = query.filter_by(algorithm_type=algorithm_type)
        if scope:
            query = query.filter_by(scope=scope)
        return [_po_to_dict(po) for po in query.order_by(ParamProfile.id).all()]

    def get(self, profile_id: int) -> Optional[Dict[str, Any]]:
        session = get_db_session()
        po = session.query(ParamProfile).filter_by(
            id=int(profile_id), deleted=False).first()
        if po is None:
            return None
        params = [
            _po_to_dict(p) for p in session.query(ParamProfileParam).filter_by(
                profile_id=po.id, deleted=False).order_by(ParamProfileParam.ui_order).all()
        ]
        mappings = [
            _po_to_dict(m) for m in session.query(ParamProfileMapping).filter_by(
                profile_id=po.id, deleted=False).order_by(ParamProfileMapping.id).all()
        ]
        detail = _po_to_dict(po)
        detail['params'] = params
        detail['mappings'] = mappings
        return detail

    def get_binding(self, api_id: int) -> Optional[int]:
        session = get_db_session()
        po = session.query(ApiParamBinding).filter_by(
            api_id=int(api_id), deleted=False).first()
        return po.profile_id if po is not None else None

    # ---- 写 ----

    def save(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """整份保存策略（基础字段 + 字段声明 + 映射）。返回详情。"""
        session = get_db_session()
        try:
            profile_id = data.get('id')
            if profile_id:
                po = session.query(ParamProfile).filter_by(
                    id=int(profile_id), deleted=False).first()
                if po is None:
                    raise ValueError('策略不存在或已删除')
                if data.get('name') is not None:
                    po.name = data['name']
                if data.get('description') is not None:
                    po.description = data['description']
                if data.get('status') is not None:
                    po.status = data['status']
            else:
                po = ParamProfile(
                    scope=data.get('scope') or 'api',
                    algorithm_type=data.get('algorithm_type') or '',
                    name=data.get('name') or '',
                    description=data.get('description'),
                    status=data.get('status') or 'online',
                    cloned_from=data.get('cloned_from'),
                )
                if not po.algorithm_type or not po.name:
                    raise ValueError('策略的 algorithm_type / name 必填')
                session.add(po)
                session.flush()
            profile_id = po.id

            self._sync_params(session, profile_id, data.get('params') or [])
            self._sync_mappings(session, profile_id, data.get('mappings') or [])
            session.commit()
            return self.get(profile_id)
        except Exception:
            session.rollback()
            raise

    def clone(self, source_profile_id: int, name: str,
              description: Optional[str] = None) -> Dict[str, Any]:
        source = self.get(source_profile_id)
        if source is None:
            raise ValueError('源策略不存在或已删除')
        if not name:
            raise ValueError('新策略名称必填')
        return self.save({
            'scope': source.get('scope'),
            'algorithm_type': source.get('algorithm_type'),
            'name': name,
            'description': description if description is not None else source.get('description'),
            'status': source.get('status'),
            'cloned_from': source.get('id'),
            'params': source.get('params') or [],
            'mappings': source.get('mappings') or [],
        })

    def delete(self, profile_id: int) -> bool:
        session = get_db_session()
        try:
            po = session.query(ParamProfile).filter_by(
                id=int(profile_id), deleted=False).first()
            if po is None:
                return False
            po.deleted = True
            session.query(ParamProfileParam).filter_by(
                profile_id=po.id, deleted=False).update({'deleted': True})
            session.query(ParamProfileMapping).filter_by(
                profile_id=po.id, deleted=False).update({'deleted': True})
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise

    def bind_api(self, api_id: int, profile_id: Optional[int]) -> Dict[str, Any]:
        """API 实例绑定策略；profile_id 为空/0 表示解绑。"""
        session = get_db_session()
        try:
            binding = session.query(ApiParamBinding).filter_by(
                api_id=int(api_id), deleted=False).first()
            if not profile_id:
                if binding is not None:
                    binding.deleted = True
                session.commit()
                return {'api_id': int(api_id), 'profile_id': None}

            profile = session.query(ParamProfile).filter_by(
                id=int(profile_id), deleted=False).first()
            if profile is None:
                raise ValueError('策略不存在或已删除')
            if profile.scope != 'api':
                raise ValueError(f"策略 scope={profile.scope}，不能绑定到 API 实例")
            if binding is None:
                binding = ApiParamBinding(
                    api_id=int(api_id), profile_id=int(profile_id))
                session.add(binding)
            else:
                binding.profile_id = int(profile_id)
            session.commit()
            return {'api_id': int(api_id), 'profile_id': int(profile_id)}
        except Exception:
            session.rollback()
            raise

    def save_api_overrides(self, api_id: int, algorithm_type: str,
                           api_params: List[Dict[str, Any]],
                           mappings: List[Dict[str, Any]]) -> Dict[str, int]:
        """原子保存某个 API 的实例覆盖行（只动 api_id 作用域，不碰策略行）。"""
        from algorithm_service.infrastructure.persistence.models import (
            AlgorithmApiParam as AlgorithmApiParamPO,
            ParamMapping as ParamMappingPO,
        )
        from algorithm_service.infrastructure.persistence._algorithm_full_save import (
            _pick_target, _split_rows, _text_or_json,
        )

        session = get_db_session()
        try:
            counts = self._sync_override_params(
                session, AlgorithmApiParamPO, api_id, algorithm_type,
                api_params, _pick_target, _split_rows, _text_or_json)
            counts.update(self._sync_override_mappings(
                session, ParamMappingPO, api_id, algorithm_type, mappings,
                _pick_target, _split_rows))
            session.commit()
            return counts
        except Exception:
            session.rollback()
            raise

    # ---- 内部同步 ----

    @staticmethod
    def _sync_params(session, profile_id: int, items: List[Dict[str, Any]]) -> None:
        from algorithm_service.infrastructure.persistence._algorithm_full_save import (
            _text_or_json,
        )
        active = {
            (p.param_code, p.direction): p
            for p in session.query(ParamProfileParam).filter_by(
                profile_id=profile_id, deleted=False).all()
        }
        soft_deleted = {
            (p.param_code, p.direction): p
            for p in session.query(ParamProfileParam).filter_by(
                profile_id=profile_id, deleted=True).all()
        }
        submitted = set()
        for item in items or []:
            code = str(item.get('param_code') or item.get('code') or '').strip()
            direction = str(item.get('direction') or 'input').strip() or 'input'
            if not code:
                raise ValueError('策略字段缺少 param_code')
            key = (code, direction)
            submitted.add(key)
            row = active.get(key) or soft_deleted.get(key)
            if row is None:
                row = ParamProfileParam(profile_id=profile_id, param_code=code)
                session.add(row)
            row.deleted = False
            row.direction = direction
            row.param_name = item.get('param_name')
            row.label = item.get('label')
            row.param_type = item.get('param_type') or 'text'
            row.required = bool(item.get('required'))
            row.default_value = _text_or_json(item.get('default_value'))
            row.validation_rules = _text_or_json(
                item.get('validation_rules') or item.get('validation'))
            row.help_text = item.get('help_text')
            row.ui_order = item.get('ui_order') or 0
            row.hidden = bool(item.get('hidden'))
            row.field_path = item.get('field_path')
        for key, row in active.items():
            if key not in submitted:
                row.deleted = True

    @staticmethod
    def _sync_mappings(session, profile_id: int, items: List[Dict[str, Any]]) -> None:
        active = {
            (m.source, m.source_param, m.dimension_id): m
            for m in session.query(ParamProfileMapping).filter_by(
                profile_id=profile_id, deleted=False).all()
        }
        soft_deleted = {
            (m.source, m.source_param, m.dimension_id): m
            for m in session.query(ParamProfileMapping).filter_by(
                profile_id=profile_id, deleted=True).all()
        }
        submitted = set()
        for item in items or []:
            source = str(item.get('source') or item.get('source_type') or 'api')
            source_param = str(item.get('source_param') or '').strip()
            if not source_param:
                raise ValueError('策略映射缺少 source_param')
            target_param = item.get('target_param')
            if not target_param:
                raise ValueError('策略映射缺少 target_param')
            dimension_id = item.get('dimension_id')
            if dimension_id is not None:
                try:
                    dimension_id = int(dimension_id)
                except (TypeError, ValueError):
                    dimension_id = None
            key = (source, source_param, dimension_id)
            submitted.add(key)
            row = active.get(key) or soft_deleted.get(key)
            if row is None:
                row = ParamProfileMapping(
                    profile_id=profile_id, source=source,
                    source_param=source_param, dimension_id=dimension_id)
                session.add(row)
            row.deleted = False
            row.source_direction = item.get('source_direction') or 'output'
            row.target_param = target_param
            row.transform_type = item.get('transform_type') or 'none'
        for key, row in active.items():
            if key not in submitted:
                row.deleted = True

    @staticmethod
    def _sync_override_params(session, po_cls, api_id, algorithm_type, items,
                              pick_target, split_rows, text_or_json) -> Dict[str, int]:
        rows = session.query(po_cls).filter_by(
            algorithm_type=algorithm_type, api_id=api_id).all()
        active, deleted = split_rows(rows, lambda r: (r.param_code, r.direction))
        submitted = set()
        created = updated = 0
        for item in items or []:
            code = str(item.get('param_code') or item.get('code') or '').strip()
            direction = str(item.get('direction') or 'input').strip() or 'input'
            if not code:
                raise ValueError('API 参数缺少 param_code')
            key = (code, direction)
            submitted.add(key)
            row, revive = pick_target(active, deleted, key)
            if row is None:
                row = po_cls(algorithm_type=algorithm_type, api_id=api_id,
                             param_code=code)
                session.add(row)
                created += 1
            else:
                updated += 1
            row.deleted = False
            row.direction = direction
            row.param_name = item.get('param_name')
            row.label = item.get('label')
            row.param_type = item.get('param_type') or 'text'
            row.required = bool(item.get('required'))
            row.default_value = text_or_json(item.get('default_value'))
            row.validation_rules = text_or_json(
                item.get('validation_rules') or item.get('validation'))
            row.help_text = item.get('help_text')
            row.ui_order = item.get('ui_order') or 0
            row.hidden = bool(item.get('hidden'))
            row.field_path = item.get('field_path')
            if revive:
                row.updated_at = datetime.now()
        dropped = 0
        for key, row in active.items():
            if key not in submitted:
                row.deleted = True
                dropped += 1
        return {'params_created': created, 'params_updated': updated,
                'params_deleted': dropped}

    @staticmethod
    def _sync_override_mappings(session, po_cls, api_id, algorithm_type, items,
                                pick_target, split_rows) -> Dict[str, int]:
        rows = session.query(po_cls).filter_by(
            algorithm_type=algorithm_type, api_id=api_id).all()
        active, deleted = split_rows(
            rows, lambda r: (r.source, r.source_param, r.dimension_id))
        submitted = set()
        created = updated = 0
        for item in items or []:
            source = str(item.get('source') or item.get('source_type') or 'api')
            source_param = str(item.get('source_param') or '').strip()
            if not source_param:
                raise ValueError('参数映射缺少 source_param')
            target_param = item.get('target_param')
            if not target_param:
                raise ValueError('参数映射缺少 target_param')
            dimension_id = item.get('dimension_id')
            if dimension_id is not None:
                try:
                    dimension_id = int(dimension_id)
                except (TypeError, ValueError):
                    dimension_id = None
            key = (source, source_param, dimension_id)
            submitted.add(key)
            row, revive = pick_target(active, deleted, key)
            if row is None:
                row = po_cls(algorithm_type=algorithm_type, api_id=api_id,
                             source=source, source_param=source_param,
                             dimension_id=dimension_id)
                session.add(row)
                created += 1
            else:
                updated += 1
            row.deleted = False
            row.source_direction = item.get('source_direction') or 'output'
            row.target_param = target_param
            row.transform_type = item.get('transform_type') or 'none'
            if revive:
                row.updated_at = datetime.now()
        dropped = 0
        for key, row in active.items():
            if key not in submitted:
                row.deleted = True
                dropped += 1
        return {'mappings_created': created, 'mappings_updated': updated,
                'mappings_deleted': dropped}


param_profile_repository = ParamProfileRepository()
param_profile_command_repository = ParamProfileCommandRepository()
