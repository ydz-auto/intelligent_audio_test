# -*- coding: utf-8 -*-
"""测试用例仓储 — TestCase 查询与统计 Mixin（从 _testcase_crud_query_mixin.py 拆分）。

分页查询 / 按标签查询 / 全量 ID 抓取 / 计数统计。
"""
from typing import List

from shared.models.database import get_db_session
from shared.models.common_enums import TestType
from task_service.infrastructure.persistence.models import Tag, TestCase, TestCaseGroup
from task_service.infrastructure.persistence._testcase_repo_common import (
    build_dim_id_filter,
)

# test_type 合法值（用于过滤分支判断）
_VALID_TEST_TYPES = [TestType.API.value, TestType.E2E.value]


class TestCaseQueryMixin:
    """TestCase 查询与统计"""

    @staticmethod
    def _build_dim_id_filter(dim_str: str):
        """按维度 ID 过滤（委托公共工具，保持类方法向后兼容）。"""
        return build_dim_id_filter(dim_str)

    # ========== 查询：列表与统计 ==========

    def query_testcases(
        self,
        page: int = 1,
        per_page: int = 10,
        keyword: str = None,
        tag: str = None,
        group_id: str = None,
        test_type: str = None,
        algorithm_type: str = None,
        include_deleted: bool = False,
        dimension_id: int = None,
    ):
        """分页查询测试用例（带 group/tags 预加载）。"""
        session = get_db_session()
        query = self._query_testcases_with_preload(session) \
            .order_by(TestCase.created_at.desc())

        if not include_deleted:
            query = query.filter(TestCase.deleted == False)  # noqa: E712

        if keyword:
            # 关键字搜索：除名称/描述外，也按用例 ID 模糊匹配
            query = query.filter(
                (TestCase.id.like(f'%{keyword}%')) |
                (TestCase.name.like(f'%{keyword}%')) |
                (TestCase.description.like(f'%{keyword}%'))
            )

        if tag:
            query = query.join(TestCase.tags).filter(Tag.name == tag)

        if group_id:
            query = query.filter(TestCase.group_id == group_id)

        if algorithm_type:
            query = query.filter(TestCase.algorithm_type == algorithm_type)

        if test_type and test_type in _VALID_TEST_TYPES:
            query = query.filter(TestCase.test_type == test_type)

        # 按评估维度过滤：搜索 config JSON 中包含该 dimension_id 的用例
        if dimension_id:
            query = query.filter(build_dim_id_filter(str(dimension_id)))

        return query.paginate(page=page, per_page=per_page, error_out=False)

    def query_testcases_by_tag_ids(
        self,
        tag_ids: List[str],
        keyword: str = None,
        test_type: str = None,
        algorithm_type: str = None,
        include_deleted: bool = False,
        dimension_id: int = None,
    ) -> List[TestCase]:
        """按标签 ID 列表查询关联的测试用例（带 group/tags 预加载）。"""
        session = get_db_session()
        tc_query = self._query_testcases_with_preload(session) \
            .join(TestCase.tags).filter(Tag.id.in_(tag_ids))

        if not include_deleted:
            tc_query = tc_query.filter(TestCase.deleted == False)  # noqa: E712
        if keyword:
            # 关键字搜索：除名称/描述外，也按用例 ID 模糊匹配
            tc_query = tc_query.filter(
                (TestCase.id.like(f'%{keyword}%')) |
                (TestCase.name.like(f'%{keyword}%')) |
                (TestCase.description.like(f'%{keyword}%'))
            )
        if test_type and test_type in _VALID_TEST_TYPES:
            tc_query = tc_query.filter(TestCase.test_type == test_type)
        if algorithm_type:
            tc_query = tc_query.filter(TestCase.algorithm_type == algorithm_type)

        # 按评估维度过滤
        if dimension_id:
            tc_query = tc_query.filter(build_dim_id_filter(str(dimension_id)))

        return tc_query.all()

    def fetch_case_ids(self, group=None, test_type=None, search=None, tag=None,
                       include_deleted: bool = False, algorithm_type: str = None,
                       dimension_id: int = None) -> List[str]:
        """按筛选条件查询全量用例ID（不分页）。

        Args:
            group: 分组名（通过 group_name 查 group_id）
            test_type: 用例类型（api/e2e）
            search: 名称/ID 模糊搜索
            tag: 标签名
            algorithm_type: 算法类型
            dimension_id: 评估维度ID（按 config JSON 模糊匹配）
        Returns:
            用例 ID 列表
        """
        session = get_db_session()
        query = session.query(TestCase.id).filter(TestCase.deleted == False)  # noqa: E712

        if group:
            group_obj = session.query(TestCaseGroup).filter_by(name=group).first()
            if group_obj:
                query = query.filter(TestCase.group_id == group_obj.id)
            else:
                # 未找到分组则返回空
                return []

        if test_type:
            query = query.filter(TestCase.test_type == test_type)

        if algorithm_type:
            query = query.filter(TestCase.algorithm_type == algorithm_type)

        if dimension_id:
            query = query.filter(build_dim_id_filter(str(dimension_id)))

        if search:
            keyword = f"%{search}%"
            # 搜索：除名称外，也按用例 ID 和描述模糊匹配
            query = query.filter(
                (TestCase.id.like(keyword)) |
                (TestCase.name.like(keyword)) |
                (TestCase.description.like(keyword))
            )

        if tag:
            # 按标签筛选
            query = query.join(TestCase.tags).filter(Tag.name == tag)

        return [row[0] for row in query.all()]

    def count_testcases(self) -> int:
        """统计未删除测试用例总数。"""
        session = get_db_session()
        return session.query(TestCase).filter_by(deleted=False).count()

    def count_testcases_by_group(self):
        """按分组名统计用例数（join group）。"""
        from sqlalchemy import func

        session = get_db_session()
        return session.query(
            TestCaseGroup.name, func.count(TestCase.id)
        ).join(TestCase, TestCase.group_id == TestCaseGroup.id) \
         .filter(TestCase.deleted == False) \
         .group_by(TestCaseGroup.name).all()

    def list_recent_updated_testcases(self, limit: int = 5) -> List[TestCase]:
        """查询最近更新的测试用例（未删除）。"""
        session = get_db_session()
        return session.query(TestCase).filter_by(deleted=False) \
            .order_by(TestCase.updated_at.desc()) \
            .limit(limit).all()

    def get_testcase_stats(self, algorithm_type: str = '', group_id: str = '',
                           group_by: str = '', test_type: str = None,
                           dimension_id: int = None) -> dict:
        """聚合统计 TestCase — count / group_by。

        多维筛选：algorithm_type / test_type / dimension_id / group_id
        """
        from sqlalchemy import func as _func

        session = get_db_session()
        try:
            return self._get_testcase_stats_impl(
                session, _func, algorithm_type, group_id, group_by, test_type, dimension_id)
        finally:
            session.close()

    def _get_testcase_stats_impl(self, session, _func, algorithm_type, group_id,
                                 group_by, test_type, dimension_id) -> dict:
        """get_testcase_stats 的实现（拆分大函数）。"""
        query = session.query(TestCase).filter(TestCase.deleted == False)  # noqa: E712
        if algorithm_type:
            query = query.filter(TestCase.algorithm_type == algorithm_type)
        if group_id:
            query = query.filter(TestCase.group_id == group_id)
        if test_type and test_type in _VALID_TEST_TYPES:
            query = query.filter(TestCase.test_type == test_type)
        if dimension_id:
            query = query.filter(build_dim_id_filter(str(dimension_id)))

        if group_by:
            return self._get_testcase_stats_grouped(
                session, _func, algorithm_type, group_id, group_by, test_type, dimension_id)

        total = query.count()
        return {'total': int(total)}

    def _get_testcase_stats_grouped(self, session, _func, algorithm_type, group_id,
                                    group_by, test_type, dimension_id) -> dict:
        """按字段分组统计分支。"""
        allowed = {'algorithm_type': TestCase.algorithm_type,
                   'group_id': TestCase.group_id}
        col = allowed.get(group_by)
        if col is None:
            return {'error': f'unsupported group_by field: {group_by}'}
        rows = session.query(col, _func.count(TestCase.id)).filter(
            TestCase.deleted == False  # noqa: E712
        )
        if algorithm_type:
            rows = rows.filter(TestCase.algorithm_type == algorithm_type)
        if group_id:
            rows = rows.filter(TestCase.group_id == group_id)
        if test_type and test_type in _VALID_TEST_TYPES:
            rows = rows.filter(TestCase.test_type == test_type)
        if dimension_id:
            rows = rows.filter(build_dim_id_filter(str(dimension_id)))
        rows = rows.group_by(col).all()
        items = [{'key': str(k) if k is not None else '', 'count': int(c)} for k, c in rows]
        return {'items': items}
