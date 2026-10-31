# -*- coding: utf-8 -*-
"""测试用例仓储 — TestCaseGroup Mixin（从 testcase_repository.py 拆分，P4-5）。

TestCaseGroup 查询 / 创建 / 更新 / 软删除（含级联）/ 多维筛选列表。
"""
from typing import Any, Dict, List, Optional

from shared.infrastructure.user_context import get_current_user_id
from shared.models.database import get_db_session
from shared.infrastructure.visibility_filter import visible_condition
from task_service.infrastructure.visibility_context import visibility_identity
from task_service.infrastructure.persistence.models import TestCase, TestCaseGroup
from task_service.infrastructure.persistence._testcase_repo_common import (
    _now,
    build_dim_id_filter,
)


class TestCaseGroupMixin:
    """TestCaseGroup 持久化访问（实现 TestCaseGroupRepositoryABC 契约）"""

    def get_group_by_name(self, name: str) -> Optional[TestCaseGroup]:
        """按名称查询分组。"""
        session = get_db_session()
        return session.query(TestCaseGroup).filter_by(name=name).first()

    def get_group_by_id(self, group_id: str) -> Optional[TestCaseGroup]:
        """按 ID 查询分组。"""
        session = get_db_session()
        return session.query(TestCaseGroup).filter_by(id=group_id).first()

    def create_group(self, group_id: str, name: str, description: str = None,
                     visibility: str = None) -> TestCaseGroup:
        """创建分组（含 flush，未 commit）。

        INT-423：created_by_user_id 从 x-user-id 上下文取操作人。
        INT-566：透传可见性落库（默认 shared，与迁移一致）。
        """
        from shared.infrastructure.user_context import get_current_user_id
        session = get_db_session()
        group = TestCaseGroup(
            id=group_id,
            name=name,
            description=description,
            visibility=visibility or 'shared',
            created_by_user_id=get_current_user_id(),
        )
        session.add(group)
        session.flush()
        return group

    def list_groups(self, algorithm_type: str = '', search: str = '',
                    dimension_id: int = None,
                    keyword: str = None) -> list:
        """查询 TestCaseGroup 列表（旧口径：不分页，返回全量 dict 列表）。"""
        return self.list_groups_page(
            algorithm_type=algorithm_type, search=search,
            dimension_id=dimension_id, keyword=keyword)['items']

    def list_groups_page(self, algorithm_type: str = '', search: str = '',
                         dimension_id: int = None, keyword: str = None,
                         page: int = 0, per_page: int = 0) -> Dict[str, Any]:
        """查询 TestCaseGroup 列表 + 过滤后总数（INT-1470 分页下推）。

        page > 0 且 per_page > 0 时在 SQL 侧分页（offset/limit），分组计数也只
        对当前页分组聚合；page / per_page 缺省或为 0 = 不分页（旧调用方行为不
        变，total == len(items)）。

        多维筛选：algorithm_type / dimension_id / keyword
        其中 dimension_id / keyword 按用例级条件统计各分组下匹配的用例数，
        只返回含匹配用例的分组。
        INT-423：私有分组对非 owner 不可见（共享 + 自己创建的私有行）。
        """
        page = int(page or 0)
        per_page = int(per_page or 0)
        paginate = page > 0 and per_page > 0
        session = get_db_session()
        try:
            _vis_uid, _vis_admin = visibility_identity()
            query = session.query(TestCaseGroup).filter(
                TestCaseGroup.deleted == False,  # noqa: E712
                visible_condition(
                    TestCaseGroup.created_by_user_id, TestCaseGroup.visibility,
                    _vis_uid, _vis_admin),
            )
            if algorithm_type:
                query = query.filter(TestCaseGroup.algorithm_type == algorithm_type)

            # 多维筛选：按用例级条件过滤分组（该口径需先物化匹配分组集合，不下推分页）
            matched_counts = None
            if dimension_id or keyword:
                matched_counts = self._count_group_matched_cases(
                    session, dimension_id, keyword)
                query = query.filter(TestCaseGroup.id.in_(list(matched_counts.keys())))

            total = query.count() if paginate else None
            # 跨页去重/不丢行需要确定性排序（无 ORDER BY 时 offset/limit 的
            # 结果集顺序不保证稳定）
            query = query.order_by(
                TestCaseGroup.created_at.asc(), TestCaseGroup.id.asc())
            if paginate:
                query = query.offset((page - 1) * per_page).limit(per_page)
            rows = query.all()
            if total is None:
                total = len(rows)

            page_ids = [str(r.id) for r in rows]
            if matched_counts is not None:
                case_counts = matched_counts
            else:
                # INT-1470：计数聚合收敛到当前页分组（未删除 + 私有可见性，
                # algorithm_type 口径与列表一致，与 GetTestCaseStats 同口径）
                case_counts = self._count_group_matched_cases(
                    session, None, None, algorithm_type=algorithm_type,
                    group_ids=page_ids)

            return {'total': total, 'items': [{
                'id': str(r.id),
                'name': r.name,
                'description': getattr(r, 'description', ''),
                'algorithm_type': getattr(r, 'algorithm_type', ''),
                'test_case_count': case_counts.get(str(r.id), 0),
            } for r in rows]}
        finally:
            session.close()

    def _count_group_matched_cases(self, session, dimension_id, keyword,
                                   algorithm_type: str = '',
                                   group_ids: List[str] = None) -> Dict[str, int]:
        """按用例级筛选条件统计各分组下匹配用例数 {group_id: count}。

        group_ids 非 None 时只聚合这些分组（INT-1470：计数只算当前页）；
        algorithm_type 非空时与列表口径一致，只计该算法类型的用例。
        INT-423：私有用例对非 owner 不计数（与 query_testcases 同口径）。
        """
        from task_service.infrastructure.visibility_context import visibility_identity
        if group_ids is not None and not group_ids:
            # 空页无需聚合（in_([]) 恒空，省一次全表扫描）
            return {}
        _vis_uid, _vis_admin = visibility_identity()
        case_filters = [
            TestCase.deleted == False,  # noqa: E712
            visible_condition(
                TestCase.created_by_user_id, TestCase.visibility, _vis_uid, _vis_admin),
        ]
        if algorithm_type:
            case_filters.append(TestCase.algorithm_type == algorithm_type)
        if group_ids is not None:
            case_filters.append(TestCase.group_id.in_(group_ids))
        if dimension_id:
            case_filters.append(build_dim_id_filter(str(dimension_id)))
        if keyword:
            case_filters.append(
                (TestCase.id.like(f'%{keyword}%')) |
                (TestCase.name.like(f'%{keyword}%')) |
                (TestCase.description.like(f'%{keyword}%'))
            )
        # 按筛选条件统计各分组下匹配的用例数
        from sqlalchemy import func
        counts_query = session.query(
            TestCase.group_id,
            func.count(TestCase.id)
        ).filter(*case_filters).group_by(TestCase.group_id).all()
        return {str(gid): count for gid, count in counts_query}

    def get_groups_by_ids(self, group_ids: list) -> list:
        """按 ID 列表批量查询 TestCaseGroup（返回 dict 列表）。

        INT-423：私有分组对非 owner 不可见（共享 + 自己创建的私有行）。
        """
        session = get_db_session()
        try:
            ids = [gid for gid in group_ids if gid]
            if not ids:
                return []
            _vis_uid, _vis_admin = visibility_identity()
            rows = (
                session.query(TestCaseGroup)
                .filter(
                    TestCaseGroup.id.in_(ids),
                    TestCaseGroup.deleted == False,  # noqa: E712
                    visible_condition(
                        TestCaseGroup.created_by_user_id, TestCaseGroup.visibility,
                        _vis_uid, _vis_admin),
                )
                .all()
            )
            return [self._group_to_dict(r) for r in rows]
        finally:
            session.close()

    def get_groups_by_names(self, names: list) -> list:
        """按名称列表批量查询 TestCaseGroup（返回 dict 列表）。

        INT-423：私有分组对非 owner 不可见。
        """
        session = get_db_session()
        try:
            valid_names = [n for n in names if n]
            if not valid_names:
                return []
            _vis_uid, _vis_admin = visibility_identity()
            rows = (
                session.query(TestCaseGroup)
                .filter(
                    TestCaseGroup.name.in_(valid_names),
                    TestCaseGroup.deleted == False,  # noqa: E712
                    visible_condition(
                        TestCaseGroup.created_by_user_id, TestCaseGroup.visibility,
                        _vis_uid, _vis_admin),
                )
                .all()
            )
            return [self._group_to_dict(r) for r in rows]
        finally:
            session.close()

    @staticmethod
    def _group_to_dict(r: TestCaseGroup) -> Dict[str, Any]:
        """TestCaseGroup PO → dict（统一序列化，消除重复）。"""
        return {
            'id': str(r.id),
            'name': r.name,
            'description': getattr(r, 'description', ''),
            'algorithm_type': getattr(r, 'algorithm_type', ''),
            # INT-423/466：资源可见性与归属人（网关路由层 owner 校验 / 前端徽标）
            'visibility': getattr(r, 'visibility', 'shared'),
            'created_by_user_id': getattr(r, 'created_by_user_id', None),
        }

    def get_group_by_id_as_dict(self, group_id: str) -> Optional[dict]:
        """按 ID 查询单个 TestCaseGroup（返回 dict 或 None）。

        INT-423：私有分组对非 owner 视为不存在（返回 None → 404）。
        """
        from task_service.infrastructure.visibility_context import is_visible
        session = get_db_session()
        try:
            r = session.get(TestCaseGroup, group_id)
            if r is None or getattr(r, 'deleted', False):
                return None
            if not is_visible(r.created_by_user_id, r.visibility):
                return None
            return self._group_to_dict(r)
        finally:
            session.close()

    def get_group_by_name_as_dict(self, group_name: str) -> Optional[dict]:
        """按名称查询单个 TestCaseGroup（返回 dict 或 None）。

        INT-423：私有分组对非 owner 视为不存在（返回 None → 404）。
        """
        from task_service.infrastructure.visibility_context import is_visible
        session = get_db_session()
        try:
            r = (
                session.query(TestCaseGroup)
                .filter(TestCaseGroup.name == group_name, TestCaseGroup.deleted == False)  # noqa: E712
                .first()
            )
            if r is None:
                return None
            if not is_visible(r.created_by_user_id, r.visibility):
                return None
            return self._group_to_dict(r)
        finally:
            session.close()

    def create_group_and_commit(self, group_id: str, name: str, description: str = '',
                                algorithm_type: str = '', visibility: str = None) -> dict:
        """创建 TestCaseGroup 并 commit（返回 dict）。

        INT-423：created_by_user_id 从 x-user-id 上下文取操作人。
        INT-566：透传可见性落库（默认 shared，与迁移一致）。
        """
        from shared.infrastructure.user_context import get_current_user_id
        session = get_db_session()
        try:
            po = TestCaseGroup(
                id=group_id,
                name=name,
                description=description or '',
                algorithm_type=algorithm_type or '',
                visibility=visibility or 'shared',
                created_by_user_id=get_current_user_id(),
            )
            session.add(po)
            session.commit()
            return self._group_to_dict(po)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def update_group_and_commit(self, group_id: str, name: str = '',
                                description: str = '',
                                algorithm_type: str = '',
                                visibility: str = None) -> dict:
        """更新 TestCaseGroup 并 commit（返回 dict）。

        若 name 非空且与当前不同，会先检查名称冲突。
        raise ValueError 当分组不存在或名称冲突时。
        INT-423：私有分组非 owner 更新抛 VisibilityDenied（写操作 403 语义）。
        visibility（INT-466）：None 不更新；非 None 时校验二值后落库。
        """
        from shared.infrastructure.visibility_filter import check_visible
        from task_service.infrastructure.visibility_context import visibility_identity
        session = get_db_session()
        try:
            r = session.get(TestCaseGroup, group_id)
            if r is None or getattr(r, 'deleted', False):
                raise ValueError('未找到分组')
            uid, is_admin = visibility_identity()
            check_visible(r.created_by_user_id, r.visibility, uid, is_admin)

            self._check_group_name_conflict(session, r, name)

            if description:
                r.description = description
            if algorithm_type:
                r.algorithm_type = algorithm_type
            if visibility is not None:
                from shared.models.common_enums import Visibility
                if visibility not in (Visibility.SHARED.value, Visibility.PRIVATE.value):
                    raise ValueError('visibility 仅支持 shared/private')
                r.visibility = visibility

            r.updated_by_user_id = get_current_user_id()
            r.updated_at = _now()
            session.commit()
            return self._group_to_dict(r)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _check_group_name_conflict(session, group: TestCaseGroup, name: str) -> None:
        """更新时校验分组名冲突（raise ValueError）。"""
        if not (name and name != group.name):
            return
        existing = (
            session.query(TestCaseGroup)
            .filter(
                TestCaseGroup.name == name,
                TestCaseGroup.id != group.id,
                TestCaseGroup.deleted == False,  # noqa: E712
            )
            .first()
        )
        if existing:
            raise ValueError(f"已存在名为 '{name}' 的其他分组")
        group.name = name

    def delete_group_and_commit(self, group_id: str, cascade: bool = False) -> dict:
        """软删除 TestCaseGroup 并 commit（cascade=True 时同时软删分组下可见 TestCase）。

        INT-423：私有分组非 owner 删除抛 VisibilityDenied（写操作 403 语义）。
        INT-2243：级联删除逐行校验用例可见性——共享分组下他人创建的 private
        用例不得被连带软删（与 `_visible_testcase_ids` 同口径）；回执返回
        实删条数 deleted_case_count 与跳过条数 skipped_case_count。
        """
        from shared.infrastructure.visibility_filter import (
            check_visible,
            filter_visible_owners,
        )
        from task_service.infrastructure.visibility_context import visibility_identity
        session = get_db_session()
        try:
            r = session.get(TestCaseGroup, group_id)
            if r is None or getattr(r, 'deleted', False):
                raise ValueError('未找到分组')
            uid, is_admin = visibility_identity()
            check_visible(r.created_by_user_id, r.visibility, uid, is_admin)

            now = _now()
            operator_id = get_current_user_id()
            r.deleted = True
            r.deleted_at = now
            r.deleted_by_user_id = operator_id
            r.updated_at = now

            deleted_case_count = 0
            skipped_case_count = 0
            if cascade:
                # INT-2243：先逐行取可见性再删，禁止无条件整批软删（共享分组下
                # 可能存在他人创建的 private 用例）。与 _visible_testcase_ids 同口径。
                rows = session.query(
                    TestCase.id, TestCase.created_by_user_id, TestCase.visibility
                ).filter(
                    TestCase.group_id == group_id,
                    TestCase.deleted == False,  # noqa: E712
                ).all()
                visible_ids = filter_visible_owners(
                    [(r[0], r[1], r[2]) for r in rows], uid, is_admin
                )
                skipped_case_count = len(rows) - len(visible_ids)
                if visible_ids:
                    deleted_case_count = session.query(TestCase).filter(
                        TestCase.id.in_(visible_ids),
                        TestCase.deleted == False,  # noqa: E712
                    ).update({
                        'deleted': True,
                        'deleted_at': now,
                        'deleted_by_user_id': operator_id,
                        'updated_at': now,
                    }, synchronize_session=False)

            session.commit()
            return {
                'id': str(group_id),
                'cascade': cascade,
                'deleted_case_count': deleted_case_count,
                'skipped_case_count': skipped_case_count,
            }
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ========== ABC 接口适配（委托到 _and_commit 版本） ==========

    def update_group(self, group_id: str, name: str = '', description: str = '',
                     algorithm_type: str = '') -> Dict[str, Any]:
        """ABC 接口 — 委托到 update_group_and_commit。"""
        return self.update_group_and_commit(
            group_id, name=name, description=description,
            algorithm_type=algorithm_type,
        )

    def delete_group(self, group_id: str, cascade: bool = False) -> Dict[str, Any]:
        """ABC 接口 — 委托到 delete_group_and_commit。"""
        return self.delete_group_and_commit(group_id, cascade=cascade)
