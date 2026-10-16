# -*- coding: utf-8 -*-
"""测试用例仓储 — TestCase 查询与统计 Mixin（从 _testcase_crud_query_mixin.py 拆分）。

分页查询 / 按标签查询 / 全量 ID 抓取 / 计数统计。
"""
from typing import List

from shared.models.database import get_db_session
from shared.models.common_enums import TestType
from shared.infrastructure.visibility_filter import visible_condition
from task_service.infrastructure.visibility_context import visibility_identity
from task_service.infrastructure.persistence.models import Tag, TestCase, TestCaseGroup
from task_service.infrastructure.persistence._testcase_repo_common import (
    build_dim_id_filter,
    build_lab_id_filter,
)


class _DerivedTypePagination:
    """test_type 派生口径过滤后的内存分页结果（接口与 _Pagination 对齐）。"""

    def __init__(self, items, total, page, per_page):
        self.items = items
        self.total = total
        self.page = page
        self.per_page = per_page

    @property
    def pages(self):
        if self.per_page == 0:
            return 0
        return (self.total + self.per_page - 1) // self.per_page

    @property
    def has_prev(self):
        return self.page > 1

    @property
    def has_next(self):
        return self.page < self.pages

    @property
    def prev_num(self):
        return self.page - 1 if self.has_prev else None

    @property
    def next_num(self):
        return self.page + 1 if self.has_next else None


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
        algorithm_type: str = None,
        test_type: str = None,
        include_deleted: bool = False,
        dimension_id: int = None,
        favorite: bool = False,
        only_deleted: bool = False,
        user_id: int = None,
        lab_ids: List[int] = None,
    ):
        """分页查询测试用例（带 group/tags 预加载）。

        favorite（INT-141）：仅当前用户收藏；only_deleted（INT-141）：仅回收站。
        test_type（INT-193）：执行口径 api/e2e，配置形态派生过滤（Python 侧）。
        lab_ids（INT-539）：按实验室过滤（含通用用例；None/空 = 不过滤）。
        """
        session = get_db_session()
        # INT-228：同事务批量创建的用例 created_at 全同（Postgres now() 为事务级
        # 时间戳），仅按 created_at 排序平局序不确定，跨页边界会重复/漏行，
        # 追加 id 次级键强定序
        query = self._query_testcases_with_preload(session) \
            .order_by(TestCase.created_at.desc(), TestCase.id.asc())

        # INT-423：行级可见性过滤（共享 + 自己创建的私有行；admin 全量）。
        # user_id 显式传参（收藏/回收站入口）优先，否则取用户上下文。
        _vis_uid, _vis_admin = visibility_identity(user_id)
        query = query.filter(visible_condition(
            TestCase.created_by_user_id, TestCase.visibility, _vis_uid, _vis_admin))

        # INT-141：回收站模式查软删除项，否则按 include_deleted 语义
        if only_deleted:
            query = query.filter(TestCase.deleted == True)  # noqa: E712
        elif not include_deleted:
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

        # 按评估维度过滤：搜索 config JSON 中包含该 dimension_id 的用例
        if dimension_id:
            query = query.filter(build_dim_id_filter(str(dimension_id)))

        # INT-539：按实验室过滤（含通用用例；config JSONB 顶层 lab_id）
        if lab_ids:
            query = query.filter(build_lab_id_filter(lab_ids))

        # INT-141：仅当前用户收藏（user_id 来自 x-user-id metadata）
        if favorite:
            from shared.models.common_enums import EntityType
            from task_service.infrastructure.persistence.models import Favorite
            if not user_id:
                return query.filter(TestCase.id.is_(None)).paginate(
                    page=page, per_page=per_page, error_out=False)
            from sqlalchemy import select as sa_select
            query = query.filter(sa_select(Favorite.id)
                                 .where(Favorite.user_id == user_id,
                                        Favorite.entity_type == EntityType.TESTCASE.value,
                                        Favorite.entity_id == TestCase.id)
                                 .correlate(TestCase)
                                 .exists())

        # INT-193：test_type 执行口径过滤（api/e2e）。差异#2 收尾后用例不存储类型，
        # 双变体两形态 config 相同（INT-129），SQL 无法区分——物化候选行后
        # Python 侧按 derive_case_test_type（config+用例名）过滤再分页，
        # 与 fetch_case_ids / get_testcase_stats 派生口径一致
        if test_type in (TestType.API.value, TestType.E2E.value):
            return self._paginate_derived_test_type(
                session, query, page, per_page, test_type)

        return query.paginate(page=page, per_page=per_page, error_out=False)

    def _paginate_derived_test_type(self, session, query, page, per_page, test_type):
        """test_type 派生口径分页：物化候选行 → Python 过滤 → 内存分页。

        过滤必须发生在分页之前，否则页内条目数与 total 口径不一致。
        """
        from shared.utils.testcase_helpers import derive_case_test_type

        rows = query.with_entities(
            TestCase.id, TestCase.name, TestCase.config,
        ).order_by(TestCase.created_at.desc(), TestCase.id.asc()).all()
        matched_ids = [rid for rid, name, config in rows
                       if derive_case_test_type(config, name) == test_type]

        total = len(matched_ids)
        start = (page - 1) * per_page
        page_ids = matched_ids[start:start + per_page]

        items_map = {}
        if page_ids:
            items_map = {
                tc.id: tc for tc in self._query_testcases_with_preload(session)
                .filter(TestCase.id.in_(page_ids)).all()
            }
        ordered_items = [items_map[rid] for rid in page_ids if rid in items_map]
        return _DerivedTypePagination(ordered_items, total, page, per_page)

    def query_testcases_by_tag_ids(
        self,
        tag_ids: List[str],
        keyword: str = None,
        algorithm_type: str = None,
        test_type: str = None,
        include_deleted: bool = False,
        dimension_id: int = None,
        favorite: bool = False,
        only_deleted: bool = False,
        user_id: int = None,
        lab_ids: List[int] = None,
    ) -> List[TestCase]:
        """按标签 ID 列表查询关联的测试用例（带 group/tags 预加载）。

        favorite/only_deleted（INT-215）：标签视图回收站/收藏过滤，
        口径与 query_testcases 一致（user_id 来自 x-user-id metadata）。
        test_type（INT-193）：执行口径 api/e2e，Python 侧派生过滤（无分页诉求，
        标签视图分页在标签维度）。
        lab_ids（INT-539）：按实验室过滤（含通用用例；None/空 = 不过滤）。
        """
        session = get_db_session()
        tc_query = self._query_testcases_with_preload(session) \
            .join(TestCase.tags).filter(Tag.id.in_(tag_ids))

        # INT-423：行级可见性过滤（与 query_testcases 同口径）
        _vis_uid, _vis_admin = visibility_identity(user_id)
        tc_query = tc_query.filter(visible_condition(
            TestCase.created_by_user_id, TestCase.visibility, _vis_uid, _vis_admin))

        # INT-215：回收站模式查软删除项，否则按 include_deleted 语义
        if only_deleted:
            tc_query = tc_query.filter(TestCase.deleted == True)  # noqa: E712
        elif not include_deleted:
            tc_query = tc_query.filter(TestCase.deleted == False)  # noqa: E712
        if keyword:
            # 关键字搜索：除名称/描述外，也按用例 ID 模糊匹配
            tc_query = tc_query.filter(
                (TestCase.id.like(f'%{keyword}%')) |
                (TestCase.name.like(f'%{keyword}%')) |
                (TestCase.description.like(f'%{keyword}%'))
            )
        if algorithm_type:
            tc_query = tc_query.filter(TestCase.algorithm_type == algorithm_type)

        # 按评估维度过滤
        if dimension_id:
            tc_query = tc_query.filter(build_dim_id_filter(str(dimension_id)))

        # INT-539：按实验室过滤（含通用用例；config JSONB 顶层 lab_id）
        if lab_ids:
            tc_query = tc_query.filter(build_lab_id_filter(lab_ids))

        # INT-215：仅当前用户收藏（与 query_testcases 同口径）
        if favorite:
            from shared.models.common_enums import EntityType
            from task_service.infrastructure.persistence.models import Favorite
            if not user_id:
                return []
            from sqlalchemy import select as sa_select
            tc_query = tc_query.filter(sa_select(Favorite.id)
                                       .where(Favorite.user_id == user_id,
                                              Favorite.entity_type == EntityType.TESTCASE.value,
                                              Favorite.entity_id == TestCase.id)
                                       .correlate(TestCase)
                                       .exists())

        items = tc_query.all()

        # INT-193：test_type 派生口径过滤（与 query_testcases 同口径，
        # 传用例名使双变体 _api/_e2e 后缀生效）
        if test_type in (TestType.API.value, TestType.E2E.value):
            from shared.utils.testcase_helpers import derive_case_test_type
            items = [tc for tc in items
                     if derive_case_test_type(tc.config, tc.name) == test_type]

        return items

    def fetch_case_ids(self, group=None, test_type=None, search=None, tag=None,
                       include_deleted: bool = False, algorithm_type: str = None,
                       dimension_id: int = None, only_deleted: bool = False) -> List[str]:
        """按筛选条件查询全量用例ID（不分页）。

        Args:
            group: 分组名（通过 group_name 查 group_id）
            test_type: 执行口径（api/e2e）——差异#2 收尾后用例不存储类型，
                按配置形态派生过滤（E2E 起跑流程圈定含播放设备音频的可物理执行用例）
            search: 名称/ID 模糊搜索
            tag: 标签名
            algorithm_type: 算法类型
            dimension_id: 评估维度ID（按 config JSON 模糊匹配）
            only_deleted: 仅回收站软删除项（INT-215：回收站全部恢复按已删集合圈定）
        Returns:
            用例 ID 列表
        """
        session = get_db_session()
        # INT-215：回收站口径查软删除项，否则仅活跃用例
        if only_deleted:
            query = session.query(TestCase.id, TestCase.config).filter(TestCase.deleted == True)  # noqa: E712
        else:
            query = session.query(TestCase.id, TestCase.config).filter(TestCase.deleted == False)  # noqa: E712
        # INT-423：行级可见性过滤（取用户上下文）
        _vis_uid, _vis_admin = visibility_identity()
        query = query.filter(visible_condition(
            TestCase.created_by_user_id, TestCase.visibility, _vis_uid, _vis_admin))

        if group:
            group_obj = session.query(TestCaseGroup).filter_by(name=group).first()
            if group_obj:
                query = query.filter(TestCase.group_id == group_obj.id)
            else:
                # 未找到分组则返回空
                return []

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

        rows = query.all()
        if test_type in (TestType.API.value, TestType.E2E.value):
            from shared.utils.testcase_helpers import derive_case_test_type
            return [cid for cid, config in rows
                    if derive_case_test_type(config) == test_type]
        return [cid for cid, _config in rows]

    def count_testcases(self) -> int:
        """统计未删除测试用例总数（INT-423：私有用例对非 owner 不计数）。"""
        from task_service.infrastructure.visibility_context import visibility_identity
        session = get_db_session()
        _vis_uid, _vis_admin = visibility_identity()
        return session.query(TestCase).filter(
            TestCase.deleted == False,  # noqa: E712
            visible_condition(
                TestCase.created_by_user_id, TestCase.visibility, _vis_uid, _vis_admin),
        ).count()

    def count_testcases_by_group(self):
        """按分组名统计用例数（join group，INT-423 私有用例不计数）。"""
        from sqlalchemy import func

        from task_service.infrastructure.visibility_context import visibility_identity
        session = get_db_session()
        _vis_uid, _vis_admin = visibility_identity()
        return session.query(
            TestCaseGroup.name, func.count(TestCase.id)
        ).join(TestCase, TestCase.group_id == TestCaseGroup.id) \
         .filter(
             TestCase.deleted == False,  # noqa: E712
             visible_condition(
                 TestCase.created_by_user_id, TestCase.visibility, _vis_uid, _vis_admin),
         ) \
         .group_by(TestCaseGroup.name).all()

    def list_recent_updated_testcases(self, limit: int = 5) -> List[TestCase]:
        """查询最近更新的测试用例（未删除，INT-423 私有用例对非 owner 不可见）。"""
        from task_service.infrastructure.visibility_context import visibility_identity
        session = get_db_session()
        _vis_uid, _vis_admin = visibility_identity()
        return session.query(TestCase).filter(
            TestCase.deleted == False,  # noqa: E712
            visible_condition(
                TestCase.created_by_user_id, TestCase.visibility, _vis_uid, _vis_admin),
        ) \
            .order_by(TestCase.updated_at.desc()) \
            .limit(limit).all()

    def get_testcase_stats(self, algorithm_type: str = '', group_id: str = '',
                           group_by: str = '', dimension_id: int = None,
                           keyword: str = '', test_type: str = '',
                           favorite: bool = False, deleted: bool = False,
                           user_id: int = None) -> dict:
        """聚合统计 TestCase — count / group_by。

        多维筛选：algorithm_type / dimension_id / group_id / keyword /
        test_type（执行口径，test_type 列已废弃后按配置形态派生）；
        favorite（INT-528）：仅当前用户收藏（user_id 来自 x-user-id metadata，
        与 query_testcases 同口径）；deleted（INT-528）：True 统计回收站
        （软删除）用例，默认统计未删除用例（镜像 get_task_stats 的 deleted）。
        """
        from sqlalchemy import func as _func

        session = get_db_session()
        try:
            return self._get_testcase_stats_impl(
                session, _func, algorithm_type, group_id, group_by,
                dimension_id, keyword, test_type, favorite, deleted, user_id)
        finally:
            session.close()

    def _get_testcase_stats_impl(self, session, _func, algorithm_type, group_id,
                                 group_by, dimension_id, keyword, test_type,
                                 favorite=False, deleted=False, user_id=None) -> dict:
        """get_testcase_stats 的实现（拆分大函数，INT-423 私有用例不计数）。"""
        from task_service.infrastructure.visibility_context import visibility_identity
        _vis_uid, _vis_admin = visibility_identity()
        query = session.query(TestCase)
        # INT-528：回收站口径可统计软删除用例；默认与既有行为一致仅统计未删除
        if deleted:
            query = query.filter(TestCase.deleted == True)  # noqa: E712
        else:
            query = query.filter(TestCase.deleted == False)  # noqa: E712
        # INT-423：私有非 owner 用例不计数（未删除/回收站统计都叠加可见性过滤）
        query = query.filter(visible_condition(
            TestCase.created_by_user_id, TestCase.visibility, _vis_uid, _vis_admin))
        if algorithm_type:
            query = query.filter(TestCase.algorithm_type == algorithm_type)
        if group_id:
            query = query.filter(TestCase.group_id == group_id)
        if dimension_id:
            query = query.filter(build_dim_id_filter(str(dimension_id)))
        if keyword:
            # 关键字搜索口径与 query_testcases 一致：用例 ID / 名称 / 描述模糊匹配
            query = query.filter(
                (TestCase.id.like(f'%{keyword}%')) |
                (TestCase.name.like(f'%{keyword}%')) |
                (TestCase.description.like(f'%{keyword}%'))
            )

        # INT-528：仅当前用户收藏（与 query_testcases 同口径，user_id 缺失恒空）
        if favorite:
            from shared.models.common_enums import EntityType
            from task_service.infrastructure.persistence.models import Favorite
            if not user_id:
                return {'items': [], 'total': 0} if group_by else {'total': 0}
            from sqlalchemy import select as sa_select
            query = query.filter(sa_select(Favorite.id)
                                 .where(Favorite.user_id == user_id,
                                        Favorite.entity_type == EntityType.TESTCASE.value,
                                        Favorite.entity_id == TestCase.id)
                                 .correlate(TestCase)
                                 .exists())

        # test_type 执行口径由 config 形态（+上传双变体名后缀）派生，
        # SQL 无法过滤，命中时逐行取 config 后 Python 侧过滤
        if test_type in (TestType.API.value, TestType.E2E.value):
            return self._get_testcase_stats_derived_type(query, group_by, test_type)

        if group_by:
            return self._get_testcase_stats_grouped(query, _func, group_by)

        total = query.count()
        return {'total': int(total)}

    def _get_testcase_stats_derived_type(self, query, group_by, test_type) -> dict:
        """test_type 派生口径统计：物化候选行后按派生类型过滤再计数/分组。"""
        from shared.utils.testcase_helpers import derive_case_test_type

        rows = query.with_entities(
            TestCase.name, TestCase.config,
            TestCase.algorithm_type, TestCase.group_id,
        ).all()
        matched = [
            (algo_type, gid)
            for name, config, algo_type, gid in rows
            if derive_case_test_type(config, name) == test_type
        ]
        if group_by:
            counts: dict = {}
            for algo_type, gid in matched:
                key = algo_type if group_by == 'algorithm_type' else gid
                key_str = str(key) if key is not None else ''
                counts[key_str] = counts.get(key_str, 0) + 1
            return {'items': [{'key': k, 'count': c} for k, c in counts.items()]}
        return {'total': len(matched)}

    def _get_testcase_stats_grouped(self, query, _func, group_by) -> dict:
        """按字段分组统计分支（复用已应用过滤的 query）。"""
        allowed = {'algorithm_type': TestCase.algorithm_type,
                   'group_id': TestCase.group_id}
        col = allowed.get(group_by)
        if col is None:
            return {'error': f'unsupported group_by field: {group_by}'}
        rows = query.with_entities(col, _func.count(TestCase.id)).group_by(col).all()
        items = [{'key': str(k) if k is not None else '', 'count': int(c)} for k, c in rows]
        return {'items': items}
