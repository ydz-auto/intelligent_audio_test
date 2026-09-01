# -*- coding: utf-8 -*-
"""测试用例仓储 — TestCaseGroup Mixin（从 testcase_repository.py 拆分，P4-5）。

TestCaseGroup 查询 / 创建 / 更新 / 软删除（含级联）/ 多维筛选列表。
"""
from typing import Any, Dict, List, Optional

from shared.models.database import get_db_session
from shared.models.common_enums import TestType
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

    def create_group(self, group_id: str, name: str, description: str = None) -> TestCaseGroup:
        """创建分组（含 flush，未 commit）。"""
        session = get_db_session()
        group = TestCaseGroup(
            id=group_id,
            name=name,
            description=description,
        )
        session.add(group)
        session.flush()
        return group

    def list_groups(self, algorithm_type: str = '', search: str = '',
                    test_type: str = None, dimension_id: int = None,
                    keyword: str = None) -> list:
        """查询 TestCaseGroup 列表（过滤逻辑删除，返回 dict 列表）。

        多维筛选：algorithm_type / test_type / dimension_id / keyword
        其中 test_type / dimension_id / keyword 按用例级条件统计各分组下匹配的用例数，
        只返回含匹配用例的分组。
        """
        session = get_db_session()
        try:
            query = session.query(TestCaseGroup).filter(TestCaseGroup.deleted == False)  # noqa: E712
            if algorithm_type:
                query = query.filter(TestCaseGroup.algorithm_type == algorithm_type)

            # 多维筛选：按用例级条件过滤分组
            if test_type or dimension_id or keyword:
                case_counts = self._count_group_matched_cases(
                    session, test_type, dimension_id, keyword)
                query = query.filter(TestCaseGroup.id.in_(list(case_counts.keys())))
            else:
                case_counts = {}

            rows = query.all()
            return [{
                'id': str(r.id),
                'name': r.name,
                'description': getattr(r, 'description', ''),
                'algorithm_type': getattr(r, 'algorithm_type', ''),
                'test_case_count': case_counts.get(str(r.id), 0),
            } for r in rows]
        finally:
            session.close()

    def _count_group_matched_cases(self, session, test_type, dimension_id, keyword) -> Dict[str, int]:
        """按用例级筛选条件统计各分组下匹配用例数 {group_id: count}。"""
        case_filters = [TestCase.deleted == False]  # noqa: E712
        if test_type and test_type in [TestType.API.value, TestType.E2E.value]:
            case_filters.append(TestCase.test_type == test_type)
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
        """按 ID 列表批量查询 TestCaseGroup（返回 dict 列表）。"""
        session = get_db_session()
        try:
            ids = [gid for gid in group_ids if gid]
            if not ids:
                return []
            rows = (
                session.query(TestCaseGroup)
                .filter(TestCaseGroup.id.in_(ids), TestCaseGroup.deleted == False)  # noqa: E712
                .all()
            )
            return [self._group_to_dict(r) for r in rows]
        finally:
            session.close()

    def get_groups_by_names(self, names: list) -> list:
        """按名称列表批量查询 TestCaseGroup（返回 dict 列表）。"""
        session = get_db_session()
        try:
            valid_names = [n for n in names if n]
            if not valid_names:
                return []
            rows = (
                session.query(TestCaseGroup)
                .filter(TestCaseGroup.name.in_(valid_names), TestCaseGroup.deleted == False)  # noqa: E712
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
        }

    def get_group_by_id_as_dict(self, group_id: str) -> Optional[dict]:
        """按 ID 查询单个 TestCaseGroup（返回 dict 或 None）。"""
        session = get_db_session()
        try:
            r = session.get(TestCaseGroup, group_id)
            if r is None or getattr(r, 'deleted', False):
                return None
            return self._group_to_dict(r)
        finally:
            session.close()

    def get_group_by_name_as_dict(self, group_name: str) -> Optional[dict]:
        """按名称查询单个 TestCaseGroup（返回 dict 或 None）。"""
        session = get_db_session()
        try:
            r = (
                session.query(TestCaseGroup)
                .filter(TestCaseGroup.name == group_name, TestCaseGroup.deleted == False)  # noqa: E712
                .first()
            )
            if r is None:
                return None
            return self._group_to_dict(r)
        finally:
            session.close()

    def create_group_and_commit(self, group_id: str, name: str, description: str = '',
                                algorithm_type: str = '') -> dict:
        """创建 TestCaseGroup 并 commit（返回 dict）。"""
        session = get_db_session()
        try:
            po = TestCaseGroup(
                id=group_id,
                name=name,
                description=description or '',
                algorithm_type=algorithm_type or '',
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
                                algorithm_type: str = '') -> dict:
        """更新 TestCaseGroup 并 commit（返回 dict）。

        若 name 非空且与当前不同，会先检查名称冲突。
        raise ValueError 当分组不存在或名称冲突时。
        """
        session = get_db_session()
        try:
            r = session.get(TestCaseGroup, group_id)
            if r is None or getattr(r, 'deleted', False):
                raise ValueError('未找到分组')

            self._check_group_name_conflict(session, r, name)

            if description:
                r.description = description
            if algorithm_type:
                r.algorithm_type = algorithm_type

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
        """软删除 TestCaseGroup 并 commit（cascade=True 时同时软删分组下所有 TestCase）。"""
        session = get_db_session()
        try:
            r = session.get(TestCaseGroup, group_id)
            if r is None or getattr(r, 'deleted', False):
                raise ValueError('未找到分组')

            now = _now()
            r.deleted = True
            r.deleted_at = now
            r.updated_at = now

            if cascade:
                session.query(TestCase).filter(
                    TestCase.group_id == group_id,
                    TestCase.deleted == False,  # noqa: E712
                ).update({
                    'deleted': True,
                    'deleted_at': now,
                    'updated_at': now,
                }, synchronize=False)

            session.commit()
            return {'id': str(group_id), 'cascade': cascade}
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
