# -*- coding: utf-8 -*-
"""测试用例仓储 — 持久化访问 TestCase / TestCaseGroup / Tag 等数据。

通过 shared.models.database.get_db_session() 的 scoped_session 访问数据库，
向上层（application/testcase_crud_service 等）提供领域可读的接口。

P1.7 改造：Dimension 已迁移到 evaluation_service 自有 PO，本仓储不再持有 Dimension
引用，跨域查询通过 evaluation_service gRPC 完成。
P3 改造：Audio / AudioTag / DeviceTag 已改为通过 e2e_test_service gRPC 查询，
本仓储不再直连这些 PO。
"""
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from shared.models.database import get_db_session
from task_service.infrastructure.persistence.models import Tag, TagCategory, TestCase, TestCaseGroup
from shared.utils.query_utils import now_cst
from task_service.domain.repositories.testcase_group_repository import TestCaseGroupRepositoryABC

def _now():
    return now_cst()


class TestCaseRepository(TestCaseGroupRepositoryABC):
    """测试用例仓储"""

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

    # ========== TestCaseGroup 相关 ==========

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

    def list_groups(self, algorithm_type: str = '', search: str = '') -> list:
        """查询 TestCaseGroup 列表（过滤逻辑删除，返回 dict 列表）。"""
        session = get_db_session()
        try:
            query = session.query(TestCaseGroup).filter(TestCaseGroup.deleted == False)  # noqa: E712
            if algorithm_type:
                query = query.filter(TestCaseGroup.algorithm_type == algorithm_type)
            if search:
                query = query.filter(TestCaseGroup.name.ilike(f'%{search}%'))
            rows = query.all()
            return [{
                'id': str(r.id),
                'name': r.name,
                'description': getattr(r, 'description', ''),
                'algorithm_type': getattr(r, 'algorithm_type', ''),
            } for r in rows]
        finally:
            session.close()

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
            return [{
                'id': str(r.id),
                'name': r.name,
                'description': getattr(r, 'description', ''),
                'algorithm_type': getattr(r, 'algorithm_type', ''),
            } for r in rows]
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
            return [{
                'id': str(r.id),
                'name': r.name,
                'description': getattr(r, 'description', ''),
                'algorithm_type': getattr(r, 'algorithm_type', ''),
            } for r in rows]
        finally:
            session.close()

    def get_group_by_id_as_dict(self, group_id: str) -> Optional[dict]:
        """按 ID 查询单个 TestCaseGroup（返回 dict 或 None）。"""
        session = get_db_session()
        try:
            r = session.get(TestCaseGroup, group_id)
            if r is None or getattr(r, 'deleted', False):
                return None
            return {
                'id': str(r.id),
                'name': r.name,
                'description': getattr(r, 'description', ''),
                'algorithm_type': getattr(r, 'algorithm_type', ''),
            }
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
            return {
                'id': str(r.id),
                'name': r.name,
                'description': getattr(r, 'description', ''),
                'algorithm_type': getattr(r, 'algorithm_type', ''),
            }
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
            return {
                'id': str(po.id),
                'name': po.name,
                'description': getattr(po, 'description', ''),
                'algorithm_type': getattr(po, 'algorithm_type', ''),
            }
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

            if name and name != r.name:
                existing = (
                    session.query(TestCaseGroup)
                    .filter(
                        TestCaseGroup.name == name,
                        TestCaseGroup.id != group_id,
                        TestCaseGroup.deleted == False,  # noqa: E712
                    )
                    .first()
                )
                if existing:
                    raise ValueError(f"已存在名为 '{name}' 的其他分组")
                r.name = name

            if description:
                r.description = description
            if algorithm_type:
                r.algorithm_type = algorithm_type

            r.updated_at = _now()
            session.commit()
            return {
                'id': str(r.id),
                'name': r.name,
                'description': getattr(r, 'description', ''),
                'algorithm_type': getattr(r, 'algorithm_type', ''),
            }
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

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

    def get_testcase_stats(self, algorithm_type: str = '', group_id: str = '',
                           group_by: str = '') -> dict:
        """聚合统计 TestCase — count / group_by。"""
        from sqlalchemy import func as _func
        session = get_db_session()
        try:
            query = session.query(TestCase).filter(TestCase.deleted == False)  # noqa: E712
            if algorithm_type:
                query = query.filter(TestCase.algorithm_type == algorithm_type)
            if group_id:
                query = query.filter(TestCase.group_id == group_id)

            if group_by:
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
                rows = rows.group_by(col).all()
                items = [{'key': str(k) if k is not None else '', 'count': int(c)} for k, c in rows]
                return {'items': items}

            total = query.count()
            return {'total': int(total)}
        finally:
            session.close()

    # ========== Tag 相关 ==========

    def get_tag_by_name(self, name: str) -> Optional[Tag]:
        """按名称查询标签。"""
        session = get_db_session()
        return session.query(Tag).filter_by(name=name).first()

    def get_or_create_tag(self, name: str) -> Tag:
        """查找或创建标签（含 flush，未 commit）。"""
        session = get_db_session()
        tag = session.query(Tag).filter_by(name=name).first()
        if not tag:
            tag = Tag(name=name)
            session.add(tag)
            session.flush()
        return tag

    def list_tags_ordered_by_updated_at(self) -> List[Tag]:
        """按更新时间倒序查询所有标签。"""
        session = get_db_session()
        return session.query(Tag).order_by(Tag.updated_at.desc()).all()

    def list_tags_paginated(self, page: int, per_page: int):
        """分页查询标签。"""
        session = get_db_session()
        return session.query(Tag).order_by(Tag.name).paginate(
            page=page, per_page=per_page, error_out=False
        )

    def rename_tag(self, old_name: str, new_name: str) -> Optional[Tuple[Tag, Optional[Tag]]]:
        """重命名标签前的校验：返回 (old_tag, new_tag_if_exists) 或 None（old 不存在）。

        调用方需在确认后自行 setattr(old_tag, name=new_name) 并 flush。
        """
        session = get_db_session()
        old_tag = session.query(Tag).filter_by(name=old_name).first()
        if not old_tag:
            return None
        new_tag_exists = session.query(Tag).filter_by(name=new_name).first()
        return (old_tag, new_tag_exists)

    def update_tag_name(self, tag: Tag, new_name: str) -> None:
        """更新标签名（含 flush，未 commit）。"""
        session = get_db_session()
        tag.name = new_name
        tag.updated_at = _now()
        session.flush()

    # ========== TagCategory CRUD（tag_crud_service 使用） ==========

    def create_tag_category(self, data: dict) -> TagCategory:
        """创建标签分类（含 flush，未 commit）。"""
        from task_service.infrastructure.persistence.models import TagCategory

        session = get_db_session()
        cat = TagCategory(
            name=data.get('name'),
            description=data.get('description'),
            color=data.get('color'),
            sort_order=data.get('sort_order') or 0,
        )
        session.add(cat)
        session.flush()
        return cat

    def get_tag_category_by_id(self, category_id: int) -> Optional[TagCategory]:
        """按 ID 查询单个标签分类（含已删除）。"""
        from task_service.infrastructure.persistence.models import TagCategory

        session = get_db_session()
        return session.get(TagCategory, category_id)

    def get_tag_category_by_name(self, name: str) -> Optional[TagCategory]:
        """按名称查询未删除的标签分类。"""
        from task_service.infrastructure.persistence.models import TagCategory

        session = get_db_session()
        return session.query(TagCategory).filter_by(name=name, deleted=False).first()

    def soft_delete_tag_category(self, cat: TagCategory) -> None:
        """软删除标签分类（含 flush，未 commit）。"""
        now = _now()
        cat.deleted = True
        cat.deleted_at = now
        cat.updated_at = now
        get_db_session().flush()

    def count_tags_by_category(self, category_id: int) -> int:
        """统计某分类下未删除标签数量。"""
        session = get_db_session()
        return session.query(Tag).filter_by(category_id=category_id, deleted=False).count()

    def list_tag_categories_paginated(self, page: int, per_page: int, keyword: str = None):
        """分页查询标签分类（带每分类标签计数）。"""
        from task_service.infrastructure.persistence.models import TagCategory

        session = get_db_session()
        subquery = session.query(
            Tag.category_id,
            func.count(Tag.id).label('tag_count')
        ).filter(Tag.deleted == False).group_by(Tag.category_id).subquery()  # noqa: E712

        query = session.query(
            TagCategory,
            func.coalesce(subquery.c.tag_count, 0).label('tag_count')
        ).outerjoin(
            subquery, TagCategory.id == subquery.c.category_id
        ).filter(TagCategory.deleted == False)  # noqa: E712

        if keyword:
            keyword = keyword.strip()
            if keyword:
                escaped = keyword.replace('%', '\\%').replace('_', '\\_')
                query = query.filter(TagCategory.name.like(f'%{escaped}%', escape='\\'))

        query = query.order_by(TagCategory.sort_order, TagCategory.id)
        return query.paginate(page=page, per_page=per_page, error_out=False)

    def list_tag_categories_ordered(self) -> List[TagCategory]:
        """按 sort_order/id 查询所有未删除分类。"""
        from task_service.infrastructure.persistence.models import TagCategory

        session = get_db_session()
        return session.query(TagCategory).filter(
            TagCategory.deleted == False  # noqa: E712
        ).order_by(TagCategory.sort_order, TagCategory.id).all()

    # ========== Tag CRUD（tag_crud_service 使用） ==========

    def create_tag(self, data: dict) -> Tag:
        """创建标签（含 flush，未 commit）。"""
        session = get_db_session()
        tag = Tag(
            name=data.get('name'),
            description=data.get('description'),
            color=data.get('color'),
            category_id=data.get('category_id'),
        )
        session.add(tag)
        session.flush()
        return tag

    def get_tag_by_id(self, tag_id: int) -> Optional[Tag]:
        """按 ID 查询单个标签（含已删除）。"""
        session = get_db_session()
        return session.get(Tag, tag_id)

    def get_active_tag_by_name(self, name: str) -> Optional[Tag]:
        """按名称查询未删除的标签。"""
        session = get_db_session()
        return session.query(Tag).filter_by(name=name, deleted=False).first()

    def soft_delete_tag(self, tag: Tag) -> None:
        """软删除标签（含 flush，未 commit）。"""
        now = _now()
        tag.deleted = True
        tag.deleted_at = now
        tag.updated_at = now
        get_db_session().flush()

    def batch_update_tag_category(self, tag_ids: List[int], category_id) -> int:
        """批量更新标签分类（含 flush，未 commit）。"""
        session = get_db_session()
        if not tag_ids:
            return 0
        update_data = {'category_id': category_id if category_id else None, 'updated_at': _now()}
        count = session.query(Tag).filter(
            Tag.id.in_(tag_ids), Tag.deleted == False  # noqa: E712
        ).update(update_data, synchronize_session=False)
        session.flush()
        return count

    def count_tag_usage_in_cases(self, tag_id: int) -> int:
        """统计标签在测试用例中的引用数。"""
        from task_service.infrastructure.persistence.models import TestCaseTag

        session = get_db_session()
        return session.query(TestCaseTag).filter_by(tag_id=tag_id).count()

    def count_tag_usage_in_audios(self, tag_id: int) -> int:
        """统计标签在音频中的引用数。

        P3 改造：AudioTag 是 e2e_test_service 自有 PO，通过 gRPC 查询。
        TODO: e2e_test_service 暂无按 tag_id 统计 AudioTag 引用数的专用 RPC，
        当前 GetAllAudioTags 仅返回标签名列表，无法按 tag_id 计数。
        暂返回 0，待补充统计类 proto 接口后实现。
        """
        # 暂无合适的 gRPC 接口按 tag_id 统计音频标签引用数
        return 0

    def count_tag_usage_in_devices(self, tag_id: int) -> int:
        """统计标签在设备中的引用数。

        P3 改造：DeviceTag 是 e2e_test_service 自有 PO，通过 gRPC 查询。
        TODO: e2e_test_service 暂无按 tag_id 统计 DeviceTag 引用数的专用 RPC，
        暂返回 0，待补充统计类 proto 接口后实现。
        """
        # 暂无合适的 gRPC 接口按 tag_id 统计设备标签引用数
        return 0

    def count_tag_usage_in_tasks(self, tag_id: int) -> int:
        """统计标签在任务中的引用数。"""
        from task_service.infrastructure.persistence.models import TaskTag

        session = get_db_session()
        return session.query(TaskTag).filter_by(tag_id=tag_id).count()

    def list_tags_paginated_with_filter(self, page: int, per_page: int,
                                        category_id: int = None, keyword: str = None):
        """分页查询标签（支持按分类与关键字过滤，按更新时间倒序）。"""
        session = get_db_session()
        query = session.query(Tag).filter(Tag.deleted == False)  # noqa: E712

        if category_id:
            query = query.filter_by(category_id=category_id)

        if keyword:
            keyword = keyword.strip()
            if keyword:
                escaped = keyword.replace('%', '\\%').replace('_', '\\_')
                query = query.filter(Tag.name.like(f'%{escaped}%', escape='\\'))

        query = query.order_by(Tag.updated_at.desc())
        return query.paginate(page=page, per_page=per_page, error_out=False)

    def list_tag_names_paginated(self, page: int, per_page: int, keyword: str = None):
        """分页查询标签名称（按名称排序）。"""
        session = get_db_session()
        query = session.query(Tag).filter(Tag.deleted == False)  # noqa: E712

        if keyword:
            keyword = keyword.strip()
            if keyword:
                escaped = keyword.replace('%', '\\%').replace('_', '\\_')
                query = query.filter(Tag.name.like(f'%{escaped}%', escape='\\'))

        query = query.order_by(Tag.name)
        return query.paginate(page=page, per_page=per_page, error_out=False)

    def get_category_name_map(self, category_ids: set) -> Dict[int, str]:
        """按 ID 集合批量查询分类名称，返回 {category_id: name}。"""
        from task_service.infrastructure.persistence.models import TagCategory

        session = get_db_session()
        if not category_ids:
            return {}
        cats = session.query(TagCategory).filter(
            TagCategory.id.in_(category_ids), TagCategory.deleted == False  # noqa: E712
        ).all()
        return {c.id: c.name for c in cats}

    def get_category_name_by_id(self, category_id) -> Optional[str]:
        """按 ID 查询分类名称（未删除）。"""
        from task_service.infrastructure.persistence.models import TagCategory

        session = get_db_session()
        cat = session.get(TagCategory, category_id)
        if cat and not cat.deleted:
            return cat.name
        return None

    def list_all_tags_ordered_by_name(self) -> List[Tag]:
        """按名称排序查询所有未删除标签。"""
        session = get_db_session()
        return session.query(Tag).filter(
            Tag.deleted == False  # noqa: E712
        ).order_by(Tag.name).all()

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
    ):
        """分页查询测试用例（带 group/tags 预加载）。"""
        session = get_db_session()
        query = session.query(TestCase).options(
            joinedload(TestCase.group),
            joinedload(TestCase.tags),
        ).order_by(TestCase.created_at.desc())

        if not include_deleted:
            query = query.filter(TestCase.deleted == False)  # noqa: E712

        if keyword:
            query = query.filter(
                (TestCase.name.like(f'%{keyword}%')) |
                (TestCase.description.like(f'%{keyword}%'))
            )

        if tag:
            query = query.join(TestCase.tags).filter(Tag.name == tag)

        if group_id:
            query = query.filter(TestCase.group_id == group_id)

        if algorithm_type:
            query = query.filter(TestCase.algorithm_type == algorithm_type)

        if test_type and test_type in ['api', 'e2e']:
            query = query.filter(TestCase.test_type == test_type)

        return query.paginate(page=page, per_page=per_page, error_out=False)

    def query_testcases_by_tag_ids(
        self,
        tag_ids: List[str],
        keyword: str = None,
        test_type: str = None,
        algorithm_type: str = None,
        include_deleted: bool = False,
    ) -> List[TestCase]:
        """按标签 ID 列表查询关联的测试用例（带 group/tags 预加载）。"""
        session = get_db_session()
        tc_query = session.query(TestCase).options(
            joinedload(TestCase.group),
            joinedload(TestCase.tags),
        ).join(TestCase.tags).filter(Tag.id.in_(tag_ids))

        if not include_deleted:
            tc_query = tc_query.filter(TestCase.deleted == False)  # noqa: E712
        if keyword:
            tc_query = tc_query.filter(
                (TestCase.name.like(f'%{keyword}%')) |
                (TestCase.description.like(f'%{keyword}%'))
            )
        if test_type and test_type in ['api', 'e2e']:
            tc_query = tc_query.filter(TestCase.test_type == test_type)
        if algorithm_type:
            tc_query = tc_query.filter(TestCase.algorithm_type == algorithm_type)

        return tc_query.all()

    def count_testcases(self) -> int:
        """统计未删除测试用例总数。"""
        session = get_db_session()
        return session.query(TestCase).filter_by(deleted=False).count()

    def count_testcases_by_group(self) -> List[Tuple[str, int]]:
        """按分组名统计用例数（join group）。"""
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

    # ========== 跨域查询：Audio / Dimension ==========

    def get_audio_by_id(self, audio_id) -> Optional[dict]:
        """按 ID 查询单个音频，返回 dict（含 id/name/duration 等字段）。

        P3 改造：Audio 是 e2e_test_service 自有 PO，通过
        AudioConfigService.GetAudio gRPC 查询，替代直连 DB。
        失败时返回 None（仅日志告警）。
        """
        if not audio_id:
            return None

        from task_service.infrastructure.acl.audio_acl_repository import audio_acl_repository
        return audio_acl_repository.get_audio_by_id(audio_id)

    def list_audios_by_ids(self, audio_ids: set) -> Dict[Any, dict]:
        """按 ID 集合批量查询音频，返回 {id: audio_dict} 映射。

        P3 改造：Audio 是 e2e_test_service 自有 PO，通过
        AudioConfigService.GetAudiosByIds gRPC 批量查询，替代直连 DB。
        失败时返回空 dict（仅日志告警）。
        """
        if not audio_ids:
            return {}

        from task_service.infrastructure.acl.audio_acl_repository import audio_acl_repository
        return audio_acl_repository.list_audios_by_ids(audio_ids)

    def list_dimensions_by_ids(self, dim_ids):
        """按 ID 列表批量查询评价维度基础信息。

        P1.7 改造：Dimension 是 evaluation_service 自有 PO，通过 gRPC 调
        evaluation_service.EvaluationConfigService.GetDimensionByIds 获取。

        Args:
            dim_ids: list[int]，Dimension.id 列表

        Returns:
            list[dict]: [{'id': int, 'name': str, 'type': str, 'description': str}, ...]
            调用失败时返回空列表（仅日志告警）。
        """
        if not dim_ids:
            return []

        from task_service.infrastructure.acl.evaluation_config_acl_repository import evaluation_config_acl_repository
        return evaluation_config_acl_repository.list_dimensions_by_ids(dim_ids)

    # ========== 事务控制 ==========

    def commit(self):
        """提交事务。"""
        get_db_session().commit()

    def rollback(self):
        """回滚事务。"""
        get_db_session().rollback()

    def flush(self):
        """flush session。"""
        get_db_session().flush()


# 模块级单例，供 application 层导入
testcase_repository = TestCaseRepository()

