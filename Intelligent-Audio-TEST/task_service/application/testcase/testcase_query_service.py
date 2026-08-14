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
                       group_id=None, test_type=None, algorithm_type=None,
                       view=None, include_deleted=False) -> dict:
        """查询测试用例列表。"""
        from shared.utils import testcase_helpers as common

        try:
            # 标签视图
            if view == 'tag':
                return self._get_tag_view(page, per_page, keyword,
                                          test_type, algorithm_type, include_deleted, common)

            pagination = self.repo.query_testcases(
                page=page, per_page=per_page, keyword=keyword, tag=tag,
                group_id=group_id, test_type=test_type,
                algorithm_type=algorithm_type, include_deleted=include_deleted,
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

            data = []
            for tc in test_cases:
                config = tc.config or {}
                tc_test_type = tc.test_type or 'api'
                total_duration = 0.0
                for audio_item in common.collect_audios(config):
                    audio_id = audio_item.get('audio_id')
                    if audio_id:
                        audio = audio_map.get(audio_id)
                        if audio and audio.get('duration'):
                            total_duration += float(audio.get('duration'))

                data.append({
                    'id': tc.id,
                    'name': tc.name,
                    'description': tc.description,
                    'group_id': tc.group_id,
                    'group_name': tc.group.name if tc.group else None,
                    'type': tc_test_type,
                    'tags': [t.name for t in tc.tags],
                    'config': tc.config.copy() if tc.config else {},
                    'algorithm_params': tc.algorithm_params,
                    'reference_params': tc.reference_params,
                    'algorithm_type': tc.algorithm_type,
                    'created_at': tc.created_at.isoformat() if tc.created_at else None,
                    'updated_at': tc.updated_at.isoformat() if tc.updated_at else None,
                    'total_duration': round(total_duration, 2) if total_duration > 0 else None,
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

    def _get_tag_view(self, page, per_page, keyword, test_type,
                      algorithm_type, include_deleted, common):
        """标签视图：按标签聚合用例。"""
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
            tag_ids, keyword=keyword, test_type=test_type,
            algorithm_type=algorithm_type, include_deleted=include_deleted,
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
                case_list.append({
                    "id": tc.id,
                    "name": tc.name,
                    "description": tc.description,
                    "groupId": tc.group_id,
                    "groupName": tc.group.name if tc.group else None,
                    "type": tc.test_type or 'api',
                    "tags": [t.name for t in tc.tags],
                    "config": tc.config.copy() if tc.config else {},
                    "algorithmParams": tc.algorithm_params,
                    "referenceParams": tc.reference_params,
                    "algorithmType": tc.algorithm_type,
                    "createdAt": tc.created_at.isoformat() if tc.created_at else None,
                    "updatedAt": tc.updated_at.isoformat() if tc.updated_at else None,
                    "totalDuration": round(total_duration, 2) if total_duration > 0 else None,
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
        """获取单个测试用例详情。"""
        from shared.utils import testcase_helpers as common

        try:
            tc = self.repo.get_testcase(tc_id)
            if not tc:
                return {'success': False, 'message': '未找到测试用例', 'data': None, 'code': 404}

            config = tc.config or {}
            tc_test_type = tc.test_type or 'api'

            audios = []
            for i, audio_item in enumerate(common.collect_audios(config)):
                # 跨域查询：Audio（后续 gRPC 改造）
                audio = self.repo.get_audio_by_id(audio_item.get('audio_id'))
                audios.append({
                    'id': i,
                    'audio_id': audio_item.get('audio_id'),
                    'audio_name': audio.get('name') if audio else None,
                    'test_type': tc_test_type,
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
                'type': tc_test_type,
                'config': config,
                'algorithm_params': getattr(tc, 'algorithm_params', None),
                'reference_params': getattr(tc, 'reference_params', None),
                'algorithm_type': tc.algorithm_type,
                'tags': [tag.name for tag in tc.tags],
                'audios': audios,
                'dimensions': dimensions,
                'created_at': tc.created_at.isoformat() if tc.created_at else None,
                'updated_at': tc.updated_at.isoformat() if tc.updated_at else None,
                'total_duration': round(total_duration, 2) if total_duration > 0 else None,
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
            return {'success': True, 'message': '', 'data': {'items': tag_names}}
        except Exception as e:
            logger.error(f"获取标签列表失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def get_testcase_ref_params(self, tc_id: str, round_number: int) -> dict:
        """获取指定用例指定轮的参考参数文件内容。"""
        from task_service.infrastructure.acl.algorithm_acl_repository import AlgorithmRepository
        _algo_repo = AlgorithmRepository()

        try:
            tc = self.repo.get_testcase(tc_id)
            if not tc:
                return {'success': False, 'message': '未找到测试用例', 'data': None, 'code': 404}

            config = tc.config or {}
            rounds = config.get('rounds', [])

            target_round = None
            for r in rounds:
                if isinstance(r, dict) and r.get('roundNumber') == round_number:
                    target_round = r
                    break

            if not target_round:
                return {'success': False, 'message': f"未找到第 {round_number} 轮", 'data': None, 'code': 404}

            ref_path = target_round.get('referenceParamsPath')
            if not ref_path:
                return {'success': False, 'message': f"第 {round_number} 轮未配置参考参数路径", 'data': None, 'code': 404}

            ref_data = _algo_repo.algo_load_reference_params_file(ref_path)
            if ref_data is None:
                return {'success': False, 'message': f"参考参数文件不存在或读取失败: {ref_path}", 'data': None, 'code': 404}

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
