# -*- coding: utf-8 -*-
"""测试用例仓储 — TestCase CRUD Mixin（从 testcase_repository.py 拆分，P4-5）。

TestCase 基础 CRUD / 软删除 / 批量更新 / TestCase-Tag 关联维护。
"""
from typing import List, Optional

from sqlalchemy.orm import joinedload

from shared.models.database import get_db_session
from task_service.infrastructure.persistence.models import Tag, TestCase
from task_service.infrastructure.persistence._testcase_repo_common import _now


class TestCaseCrudMixin:
    """TestCase 基础 CRUD 与用例-标签关联维护"""

    # ========== TestCase 基础 CRUD ==========

    def create_testcase(self, data: dict) -> TestCase:
        """创建测试用例记录（含 flush，未 commit）。

        data 需含 id/name/group_id/config/algorithm_params/algorithm_type/test_type。
        """
        session = get_db_session()
        tc = TestCase(
            id=data.get('id'),
            name=data.get('name'),
            description=data.get('description'),
            group_id=data.get('group_id'),
            config=data.get('config'),
            algorithm_params=data.get('algorithm_params'),
            algorithm_type=data.get('algorithm_type'),
            test_type=data.get('test_type'),
        )
        session.add(tc)
        session.flush()
        return tc

    def get_testcase(self, tc_id: str) -> Optional[TestCase]:
        """按 ID 查询单个未删除测试用例。"""
        session = get_db_session()
        return session.query(TestCase).filter_by(id=tc_id, deleted=False).first()

    def get_testcase_by_name(self, name: str, group_id: str) -> Optional[TestCase]:
        """按名称和分组 ID 查询未删除测试用例（用于重名校验）。"""
        session = get_db_session()
        return session.query(TestCase).filter_by(
            name=name, group_id=group_id, deleted=False
        ).first()

    def add_tag_to_testcase(self, tc_id: str, tag_id: str) -> None:
        """为测试用例追加标签关联（含 flush，未 commit）。

        P5+DOMAIN: 封装 TestCase.tags.append(tag) 操作，避免 application 层
        直接操作 PO 关联集合。
        """
        session = get_db_session()
        tc = session.query(TestCase).filter_by(id=tc_id, deleted=False).first()
        if tc:
            tag = session.query(Tag).filter_by(id=tag_id).first()
            if tag and tag not in tc.tags:
                tc.tags.append(tag)
                session.flush()

    def _get_session_no_autoflush(self):
        """返回 session 的 no_autoflush 上下文管理器。

        供 application 层使用 session.no_autoflush 语义，而不直接依赖
        get_db_session()。
        """
        session = get_db_session()
        return session.no_autoflush

    def soft_delete_testcase(self, tc_id: str) -> bool:
        """软删除单个测试用例（未 commit）。"""
        session = get_db_session()
        tc = session.query(TestCase).filter_by(id=tc_id, deleted=False).first()
        if not tc:
            return False
        now = _now()
        tc.deleted = True
        tc.deleted_at = now
        tc.updated_at = now
        session.flush()
        return True

    def soft_delete_testcases_by_ids(self, ids: List[str]) -> int:
        """批量软删除测试用例（未 commit）。"""
        session = get_db_session()
        if not ids:
            return 0
        now = _now()
        count = session.query(TestCase).filter(TestCase.id.in_(ids)).update(
            {"deleted": True, "deleted_at": now, "updated_at": now},
            synchronize_session=False,
        )
        session.flush()
        return count

    def update_testcase_group_id_by_ids(self, ids: List[str], group_id: str) -> int:
        """批量更新测试用例的 group_id（未 commit）。"""
        session = get_db_session()
        if not ids:
            return 0
        count = session.query(TestCase).filter(TestCase.id.in_(ids)).update(
            {"group_id": group_id}, synchronize_session=False
        )
        session.flush()
        return count

    def list_testcases_by_ids(self, ids: List[str], include_deleted: bool = False) -> List[TestCase]:
        """按 ID 列表查询测试用例。"""
        session = get_db_session()
        if not ids:
            return []
        query = session.query(TestCase).filter(TestCase.id.in_(ids))
        if not include_deleted:
            query = query.filter(TestCase.deleted == False)  # noqa: E712
        return query.all()

    def list_testcases_by_group(self, group_id: str, include_deleted: bool = False) -> List[TestCase]:
        """按分组查询测试用例。"""
        session = get_db_session()
        query = session.query(TestCase).filter_by(group_id=group_id)
        if not include_deleted:
            query = query.filter(TestCase.deleted == False)  # noqa: E712
        return query.all()

    def list_all_testcases(self, include_deleted: bool = False) -> List[TestCase]:
        """查询所有测试用例（供跨域反查 config 中 audio_id 引用）。

        P5+DOMAIN: 封装全表扫描，避免 application 层直接 import TestCase PO。
        """
        session = get_db_session()
        query = session.query(TestCase)
        if not include_deleted:
            query = query.filter(TestCase.deleted == False)  # noqa: E712
        return query.all()

    def update_testcase_algorithm_params(self, tc_id: str, algorithm_params) -> None:
        """更新测试用例的 algorithm_params 字段（含 flush，未 commit）。

        P5+DOMAIN: 封装 tc.algorithm_params = ... 赋值，避免 application 层
        直接操作 PO 字段。
        """
        session = get_db_session()
        tc = session.query(TestCase).filter_by(id=tc_id, deleted=False).first()
        if tc:
            tc.algorithm_params = algorithm_params
            session.flush()

    # ========== TestCase-Tag 关联 ==========

    def set_testcase_tags(self, tc: TestCase, tag_names: List[str]) -> None:
        """重新设置用例的标签集合（含 flush，未 commit）。"""
        session = get_db_session()
        tc.tags = []
        for tag_name in tag_names:
            tag = self.get_or_create_tag(tag_name)
            tc.tags.append(tag)
        session.flush()

    def add_tags_to_testcases(self, ids: List[str], tag_names: List[str]) -> List[TestCase]:
        """为多个用例追加标签（仅追加不存在的标签，含 flush，未 commit）。

        返回受影响的用例列表。
        """
        session = get_db_session()
        test_cases = session.query(TestCase).filter(
            TestCase.id.in_(ids), TestCase.deleted == False  # noqa: E712
        ).all()
        for tc in test_cases:
            existing_tag_names = {tag.name for tag in tc.tags}
            for tag_name in tag_names:
                if tag_name not in existing_tag_names:
                    tag = self.get_or_create_tag(tag_name)
                    tc.tags.append(tag)
            tc.updated_at = _now()
        session.flush()
        return test_cases

    def remove_tags_from_testcases(self, ids: List[str], tag_names: List[str]) -> List[TestCase]:
        """从多个用例移除指定标签（含 flush，未 commit）。

        返回受影响的用例列表。
        """
        session = get_db_session()
        test_cases = session.query(TestCase).filter(
            TestCase.id.in_(ids), TestCase.deleted == False  # noqa: E712
        ).all()
        tags_to_remove_set = set(tag_names)
        for tc in test_cases:
            tc.tags = [tag for tag in tc.tags if tag.name not in tags_to_remove_set]
            tc.updated_at = _now()
        session.flush()
        return test_cases

    def auto_generate_names_by_tag_order(self, ids: List[str]) -> List[TestCase]:
        """按标签名排序自动生成用例名（含 flush，未 commit）。

        返回受影响的用例列表。
        """
        session = get_db_session()
        test_cases = session.query(TestCase).filter(
            TestCase.id.in_(ids), TestCase.deleted == False  # noqa: E712
        ).all()
        for tc in test_cases:
            tag_names = sorted(
                [tag.name for tag in tc.tags if len(tag.name) <= 25],
                key=lambda x: len(x),
            )
            if tag_names:
                tc.name = '-'.join(tag_names)
            tc.updated_at = _now()
        session.flush()
        return test_cases

    # ========== TestCase 预加载查询（供 Query Mixin 复用） ==========

    def _query_testcases_with_preload(self, session):
        """构建带 group/tags 预加载的 TestCase 查询（消除重复）。"""
        return session.query(TestCase).options(
            joinedload(TestCase.group),
            joinedload(TestCase.tags),
        )
