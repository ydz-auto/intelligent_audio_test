# -*- coding: utf-8 -*-
"""TestCaseQueryService — 测试用例查询应用服务。

从 testcase_crud_service 拆分，承担所有读操作（列表/标签视图/详情/
统计/标签列表/参考参数读取）。

约定：
- 所有方法返回 dict: {success, message, data, code?}
- 通过 self.repo 调用 Repository，不直连 DB
- 跨域查询（Audio / Dimension）通过 repo 访问并加注释标记后续 gRPC 改造
"""
from __future__ import annotations

import logging

from task_service.domain.repositories.testcase_group_repository import TestCaseGroupRepositoryABC
from task_service.infrastructure.persistence.testcase_repository import testcase_repository

logger = logging.getLogger(__name__)


class TestCaseQueryService:
    """测试用例查询应用服务。"""

    def __init__(self, repo: TestCaseGroupRepositoryABC = None):
        self.repo = repo or testcase_repository

    # ==================== 读操作 ====================

    def list_testcases(self, page=1, per_page=10, keyword=None, tag=None,
                       group_id=None, algorithm_type=None,
                       view=None, include_deleted=False, dimension_id=None,
                       favorite=False, only_deleted=False, user_id=None,
                       lab_ids=None, visibility=None) -> dict:
        """查询测试用例列表。

        favorite（INT-141）：仅当前用户收藏；only_deleted（INT-141）：仅回收站。
        lab_ids（INT-539）：按实验室过滤（含通用用例；None/空 = 不过滤），
        列表项透出 lab_id/lab_name（config JSONB 解析 + laboratories join）。
        visibility（INT-466）：可见性筛选（shared/private；None=全部）。
        """
        from shared.utils import testcase_helpers as common

        try:
            # 标签视图（INT-215：收藏/回收站过滤贯通标签聚合视图）
            if view == 'tag':
                return self._get_tag_view(page, per_page, keyword,
                                          algorithm_type, include_deleted, common,
                                          dimension_id=dimension_id,
                                          favorite=favorite, only_deleted=only_deleted,
                                          user_id=user_id, lab_ids=lab_ids,
                                          visibility=visibility)

            pagination = self.repo.query_testcases(
                page=page, per_page=per_page, keyword=keyword, tag=tag,
                group_id=group_id,
                algorithm_type=algorithm_type,
                include_deleted=include_deleted,
                dimension_id=dimension_id,
                favorite=favorite, only_deleted=only_deleted, user_id=user_id,
                lab_ids=lab_ids,
                visibility=visibility,
            )
            test_cases = pagination.items

            audio_ids = set()
            for tc in test_cases:
                config = tc.config or {}
                for audio_item in common.collect_audios(config):
                    aid = audio_item.get('audio_id')
                    if aid is not None:
                        audio_ids.add(aid)

            # 跨域查询：Audio（后续 gRPC 改造）
            audio_map = self.repo.list_audios_by_ids(audio_ids) if audio_ids else {}

            # INT-539：lab_id → lab_name（laboratories 表 join，同共享库）
            lab_map = self._load_lab_map(test_cases)

            # INT-141：当前用户对本页用例的收藏集合（is_favorite 标记）
            favorite_ids = set()
            if user_id and test_cases:
                from shared.models.common_enums import EntityType
                from task_service.infrastructure.persistence.models import Favorite
                from shared.models.database import get_db_session
                fav_session = get_db_session()
                try:
                    fav_rows = (fav_session.query(Favorite.entity_id)
                                .filter(Favorite.user_id == user_id,
                                        Favorite.entity_type == EntityType.TESTCASE.value,
                                        Favorite.entity_id.in_([tc.id for tc in test_cases]))
                                .all())
                    favorite_ids = {r[0] for r in fav_rows}
                finally:
                    fav_session.close()

            data = []
            for tc in test_cases:
                config = tc.config or {}
                total_duration = 0.0
                for audio_item in common.collect_audios(config):
                    audio_id = audio_item.get('audio_id')
                    if audio_id:
                        audio = audio_map.get(audio_id)
                        if audio and audio.get('duration'):
                            total_duration += float(audio.get('duration'))

                lab_id = common.parse_config_lab_id(config)

                data.append({
                    'id': tc.id,
                    'name': tc.name,
                    'description': tc.description,
                    'group_id': tc.group_id,
                    'group_name': tc.group.name if tc.group else None,
                    'tags': [t.name for t in tc.tags],
                    'config': tc.config.copy() if tc.config else {},
                    'algorithm_params': tc.algorithm_params,
                    'reference_params': tc.reference_params,
                    'algorithm_type': tc.algorithm_type,
                    # INT-590：评估策略引用（列表页展示引用策略名/覆盖标记）
                    'strategy_id': getattr(tc, 'strategy_id', None),
                    'strategy_overrides': getattr(tc, 'strategy_overrides', None),
                    'created_at': tc.created_at.isoformat() if tc.created_at else None,
                    'updated_at': tc.updated_at.isoformat() if tc.updated_at else None,
                    'is_favorite': tc.id in favorite_ids,
                    'deleted': bool(getattr(tc, 'deleted', False)),
                    'deleted_at': tc.deleted_at.isoformat() if getattr(tc, 'deleted_at', None) else None,
                    'deleted_by_user_id': getattr(tc, 'deleted_by_user_id', None),
                    'total_duration': round(total_duration, 2) if total_duration > 0 else None,
                    # INT-423/466：资源可见性与归属人（网关路由层 owner 校验 / 前端徽标）
                    'visibility': getattr(tc, 'visibility', 'shared'),
                    'created_by_user_id': getattr(tc, 'created_by_user_id', None),
                    # INT-539：lab 归属透出（config JSONB 解析；通用用例 lab_id=null）
                    'lab_id': lab_id,
                    'lab_name': lab_map.get(lab_id) if lab_id else None,
                })

            return {
                'success': True,
                'message': '',
                'data': {
                    'items': data,
                    'total': pagination.total,
                    'page': pagination.page,
                    'per_page': pagination.per_page,
                    'pages': pagination.pages,
                }
            }
        except Exception as e:
            logger.error(f"查询测试用例列表失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def _load_lab_map(self, test_cases) -> dict:
        """从用例集合收集 lab_id 并批量查询实验室名称（INT-539）。

        软删/缺失实验室不参与映射（lab_name 返回 None）。
        """
        lab_ids = set()
        from shared.utils import testcase_helpers as common
        for tc in test_cases:
            lab_id = common.parse_config_lab_id(tc.config or {})
            if lab_id:
                lab_ids.add(lab_id)
        if not lab_ids:
            return {}
        return self.repo.list_laboratories_by_ids(lab_ids)

    def _get_tag_view(self, page, per_page, keyword,
                      algorithm_type, include_deleted, common,
                      dimension_id=None,
                      favorite=False, only_deleted=False, user_id=None,
                      lab_ids=None, visibility=None):
        """标签视图：按标签聚合用例。lab_ids（INT-539）：按实验室过滤（含通用用例）。"""
        tag_pagination = self.repo.list_tags_paginated(page=page, per_page=per_page)
        page_tags = tag_pagination.items

        items = []
        if not page_tags:
            return {
                'success': True,
                'message': '',
                'data': {
                    "items": [],
                    "total": tag_pagination.total,
                    "page": tag_pagination.page,
                    "per_page": tag_pagination.per_page,
                    "pages": tag_pagination.pages,
                }
            }

        tag_ids = [t.id for t in page_tags]
        test_cases = self.repo.query_testcases_by_tag_ids(
            tag_ids, keyword=keyword,
            algorithm_type=algorithm_type,
            include_deleted=include_deleted,
            dimension_id=dimension_id,
            favorite=favorite, only_deleted=only_deleted, user_id=user_id,
            lab_ids=lab_ids,
            visibility=visibility,
        )

        audio_ids = set()
        for tc in test_cases:
            config = tc.config or {}
            for audio_item in common.collect_audios(config):
                aid = audio_item.get('audio_id')
                if aid is not None:
                    audio_ids.add(aid)

        # 跨域查询：Audio（后续 gRPC 改造）
        audio_map = self.repo.list_audios_by_ids(audio_ids) if audio_ids else {}

        # INT-539：lab_id → lab_name（laboratories 表 join，同共享库）
        lab_map = self._load_lab_map(test_cases)

        # INT-215：当前用户对本批用例的收藏集合（isFavorite 标记）
        favorite_ids = set()
        if user_id and test_cases:
            from shared.models.common_enums import EntityType
            from task_service.infrastructure.persistence.models import Favorite
            from shared.models.database import get_db_session
            fav_session = get_db_session()
            try:
                fav_rows = (fav_session.query(Favorite.entity_id)
                            .filter(Favorite.user_id == user_id,
                                    Favorite.entity_type == EntityType.TESTCASE.value,
                                    Favorite.entity_id.in_([tc.id for tc in test_cases]))
                            .all())
                favorite_ids = {r[0] for r in fav_rows}
            finally:
                fav_session.close()

        cases_by_tag = {t.id: [] for t in page_tags}
        for tc in test_cases:
            for t in tc.tags:
                if t.id in cases_by_tag:
                    cases_by_tag[t.id].append(tc)

        for tag in page_tags:
            case_list = []
            for tc in cases_by_tag.get(tag.id, []):
                config = tc.config or {}
                total_duration = 0.0
                for audio_item in common.collect_audios(config):
                    audio_id = audio_item.get('audio_id')
                    if audio_id:
                        audio = audio_map.get(audio_id)
                        if audio and audio.get('duration'):
                            total_duration += float(audio.get('duration'))
                lab_id = common.parse_config_lab_id(config)
                case_list.append({
                    "id": tc.id,
                    "name": tc.name,
                    "description": tc.description,
                    "groupId": tc.group_id,
                    "groupName": tc.group.name if tc.group else None,
                    "tags": [t.name for t in tc.tags],
                    "config": tc.config.copy() if tc.config else {},
                    "algorithmParams": tc.algorithm_params,
                    "referenceParams": tc.reference_params,
                    "algorithmType": tc.algorithm_type,
                    # INT-590：评估策略引用（标签视图对齐普通列表口径）
                    "strategyId": getattr(tc, 'strategy_id', None),
                    "strategyOverrides": getattr(tc, 'strategy_overrides', None),
                    "createdAt": tc.created_at.isoformat() if tc.created_at else None,
                    "updatedAt": tc.updated_at.isoformat() if tc.updated_at else None,
                    # INT-215：收藏标记 / 回收站字段（与普通列表对齐）
                    "isFavorite": tc.id in favorite_ids,
                    "deleted": bool(getattr(tc, 'deleted', False)),
                    "deletedAt": tc.deleted_at.isoformat() if getattr(tc, 'deleted_at', None) else None,
                    "deletedByUserId": getattr(tc, 'deleted_by_user_id', None),
                    "totalDuration": round(total_duration, 2) if total_duration > 0 else None,
                    # INT-423/466：资源可见性与归属人（前端徽标，标签视图 camelCase 输出）
                    "visibility": getattr(tc, 'visibility', 'shared'),
                    "createdByUserId": getattr(tc, 'created_by_user_id', None),
                    # INT-539：lab 归属透出（config JSONB 解析；通用用例 lab_id=null）
                    "labId": lab_id,
                    "labName": lab_map.get(lab_id) if lab_id else None,
                })

            items.append({
                "tag": tag.name,
                "testCases": case_list,
            })

        return {
            'success': True,
            'message': '',
            'data': {
                "items": items,
                "total": tag_pagination.total,
                "page": tag_pagination.page,
                "per_page": tag_pagination.per_page,
                "pages": tag_pagination.pages,
            }
        }

    def get_testcase_detail(self, tc_id: str) -> dict:
        """获取单个测试用例详情。

        INT-423：私有用例对非 owner 视为不存在（404）。
        """
        from shared.utils import testcase_helpers as common
        from shared.infrastructure.visibility_filter import VisibilityDenied
        from task_service.infrastructure.visibility_context import (
            check_object_visible, visibility_identity,
        )

        try:
            tc = self.repo.get_testcase(tc_id)
            if not tc:
                return {'success': False, 'message': '未找到测试用例', 'data': None, 'code': 404}
            _uid, _is_admin = visibility_identity()
            try:
                check_object_visible(tc, _uid, _is_admin)
            except VisibilityDenied:
                return {'success': False, 'message': '未找到测试用例', 'data': None, 'code': 404}

            config = tc.config or {}

            audios = []
            for i, audio_item in enumerate(common.collect_audios(config)):
                # 跨域查询：Audio（后续 gRPC 改造）
                audio = self.repo.get_audio_by_id(audio_item.get('audio_id'))
                audios.append({
                    'id': i,
                    'audio_id': audio_item.get('audio_id'),
                    'audio_name': audio.get('name') if audio else None,
                    'spl': audio_item.get('spl'),
                    'playback_device_id': common.normalize_optional_int(audio_item.get('playback_device_id')),
                    'play_order': audio_item.get('play_order'),
                })

            dimensions = []
            dim_config = common.collect_dimensions(config)
            dimension_ids = []
            for item in dim_config:
                if isinstance(item, dict):
                    dim_id = item.get('id')
                    if dim_id:
                        dimension_ids.append(dim_id)
                else:
                    dimension_ids.append(item)

            unique_dimension_ids = list(set(dimension_ids))
            # P1.7: Dimension 跨域查询改 gRPC（evaluation_service 自有 PO）
            dim_list = self.repo.list_dimensions_by_ids(unique_dimension_ids)
            for dim in dim_list:
                dimensions.append({'id': dim.get('id'), 'name': dim.get('name'), 'type': dim.get('type')})

            total_duration = 0.0
            for audio_item in common.collect_audios(config):
                audio_id = audio_item.get('audio_id')
                if audio_id:
                    # 跨域查询：Audio（后续 gRPC 改造）
                    audio = self.repo.get_audio_by_id(audio_id)
                    if audio and audio.get('duration'):
                        total_duration += float(audio.get('duration'))

            detail_data = {
                'id': tc.id,
                'name': tc.name,
                'description': tc.description,
                'group_id': tc.group_id,
                'group_name': tc.group.name if tc.group else None,
                'group': {"id": tc.group.id, "name": tc.group.name} if tc.group else None,
                'config': config,
                'algorithm_params': getattr(tc, 'algorithm_params', None),
                'reference_params': getattr(tc, 'reference_params', None),
                'algorithm_type': tc.algorithm_type,
                # INT-590：评估策略引用（详情回显引用策略 + 覆盖源，前端可编辑覆盖）
                'strategy_id': getattr(tc, 'strategy_id', None),
                'strategy_overrides': getattr(tc, 'strategy_overrides', None),
                'tags': [tag.name for tag in tc.tags],
                'audios': audios,
                'dimensions': dimensions,
                'created_at': tc.created_at.isoformat() if tc.created_at else None,
                'updated_at': tc.updated_at.isoformat() if tc.updated_at else None,
                'total_duration': round(total_duration, 2) if total_duration > 0 else None,
                # INT-423/466：资源可见性与归属人（网关路由层 owner 校验 / 前端徽标）
                'visibility': getattr(tc, 'visibility', 'shared'),
                'created_by_user_id': getattr(tc, 'created_by_user_id', None),
            }

            return {'success': True, 'message': '', 'data': detail_data}
        except Exception as e:
            logger.error(f"获取测试用例详情失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def get_testcase_stats(self) -> dict:
        """获取测试用例统计信息。"""
        try:
            total_count = self.repo.count_testcases()
            group_stats = self.repo.count_testcases_by_group()
            recent_updates = self.repo.list_recent_updated_testcases(limit=5)

            return {
                'success': True,
                'message': '',
                'data': {
                    'total_count': total_count,
                    'by_group': {name: count for name, count in group_stats},
                    'recent_updates': [
                        {"id": tc.id, "name": tc.name, "updated_at": tc.updated_at.isoformat()}
                        for tc in recent_updates
                    ],
                }
            }
        except Exception as e:
            logger.error(f"获取测试用例统计失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def get_testcase_tags(self) -> dict:
        """获取所有标签名列表。"""
        try:
            tags = self.repo.list_tags_ordered_by_updated_at()
            tag_names = [tag.name for tag in tags]
            # INT-297：列表信封统一（无分页语义：单页全量）
            return {'success': True, 'message': '', 'data': {
                'items': tag_names,
                'total': len(tag_names),
                'page': 1,
                'per_page': len(tag_names) or 1,
                'pages': 1,
            }}
        except Exception as e:
            logger.error(f"获取标签列表失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def fetch_case_ids(self, data: dict) -> dict:
        """按筛选条件返回全量用例ID（不分页）。

        Args:
            data: {group, search, tag, algorithm_type, dimension_id, only_deleted}
        Returns:
            {success, message, data: {'ids': [...]}}
        """
        try:
            group = data.get('group')
            search = data.get('search')
            tag = data.get('tag')
            # INT-215：回收站全部恢复按已删集合圈定（snake_case 由前端 QUERY_PARAM_MAP 转换）
            only_deleted = bool(data.get('only_deleted'))
            # INT-215/P2-R1：算法/维度过滤透传——原被本层丢弃（仓储已支持），
            # 回收站「全部恢复」在算法/维度筛选下恢复超集、确认数与可见列表不符
            algorithm_type = data.get('algorithm_type')
            dimension_id = data.get('dimension_id')

            ids = self.repo.fetch_case_ids(
                group=group, search=search, tag=tag,
                only_deleted=only_deleted,
                algorithm_type=algorithm_type, dimension_id=dimension_id,
            )
            return {'success': True, 'message': '', 'data': {'ids': ids}}
        except Exception as e:
            logger.error(f"查询用例ID失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def get_testcase_ref_params(self, tc_id: str, round_number: int) -> dict:
        """获取指定用例指定轮的参考参数文件内容。

        INT-1645：轮次键 snake/camel 都认、路径以 reference_params 独立列为准
        （config.rounds[] 兜底）并归一化，读取直连存储抽象；读取失败必须
        显式 404 带路径，不再退化成「200 + 空列表」。
        """
        from task_service.infrastructure.oss.ref_params_store import (
            RefParamsReadError, normalize_ref_params_path, read_ref_params,
            resolve_round_ref_path, to_round_number,
        )

        try:
            tc = self.repo.get_testcase(tc_id)
            if not tc:
                return {'success': False, 'message': '未找到测试用例', 'data': None, 'code': 404}

            # INT-423：私有用例对非 owner 视为不存在（404）
            from shared.infrastructure.visibility_filter import VisibilityDenied
            from task_service.infrastructure.visibility_context import (
                check_object_visible, visibility_identity,
            )
            _uid, _is_admin = visibility_identity()
            try:
                check_object_visible(tc, _uid, _is_admin)
            except VisibilityDenied:
                return {'success': False, 'message': '未找到测试用例', 'data': None, 'code': 404}

            round_number = to_round_number(round_number)
            round_exists, raw_path = resolve_round_ref_path(tc, round_number)
            if not round_exists:
                return {'success': False, 'message': f"未找到第 {round_number} 轮", 'data': None, 'code': 404}

            if not raw_path:
                return {'success': False, 'message': f"第 {round_number} 轮未生成参考参数", 'data': None, 'code': 404}

            ref_path = normalize_ref_params_path(raw_path)
            try:
                ref_data = read_ref_params(ref_path)
            except RefParamsReadError as e:
                logger.warning(f"[ref_params] 读取失败 case={tc_id} round={round_number}: {e}")
                detail = raw_path if raw_path == ref_path else f'{raw_path}（归一化: {ref_path}）'
                return {
                    'success': False,
                    'message': f"参考参数文件读取失败: {detail}",
                    'data': None,
                    'code': 404,
                }

            return {
                'success': True,
                'message': '',
                'data': {
                    'roundNumber': round_number,
                    'referenceParamsPath': ref_path,
                    'referenceParams': ref_data
                }
            }
        except Exception as e:
            logger.error(f"获取参考参数失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}
