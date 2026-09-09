# -*- coding: utf-8 -*-
"""测试用例仓储 — Tag / TagCategory Mixin（从 testcase_repository.py 拆分，P4-5）。

Tag CRUD / TagCategory CRUD / 引用计数 / 名称与分类映射。
"""
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func

from shared.models.database import get_db_session
from task_service.infrastructure.persistence.models import Tag, TagCategory
from task_service.infrastructure.persistence._testcase_repo_common import (
    _now,
    apply_keyword_like,
)


class TagRepositoryMixin:
    """Tag / TagCategory 持久化访问"""

    # ========== Tag 基础 ==========

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
        """按更新时间倒序查询所有未删除标签。"""
        session = get_db_session()
        return session.query(Tag).filter(
            Tag.deleted == False  # noqa: E712
        ).order_by(Tag.updated_at.desc()).all()

    def list_tags_paginated(self, page: int, per_page: int):
        """分页查询未删除标签（view=tag 数据源，需剔除软删除标签）。"""
        session = get_db_session()
        return session.query(Tag).filter(
            Tag.deleted == False  # noqa: E712
        ).order_by(Tag.name).paginate(
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
        session = get_db_session()
        return session.get(TagCategory, category_id)

    def get_tag_category_by_name(self, name: str) -> Optional[TagCategory]:
        """按名称查询未删除的标签分类。"""
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
            query = apply_keyword_like(query, TagCategory.name, keyword.strip())

        query = query.order_by(TagCategory.sort_order, TagCategory.id)
        return query.paginate(page=page, per_page=per_page, error_out=False)

    def list_tag_categories_ordered(self) -> List[TagCategory]:
        """按 sort_order/id 查询所有未删除分类。"""
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

    # ========== Tag 引用计数 ==========

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

    # ========== Tag 列表查询 ==========

    def list_tags_paginated_with_filter(self, page: int, per_page: int,
                                        category_id: int = None, keyword: str = None):
        """分页查询标签（支持按分类与关键字过滤，按更新时间倒序）。"""
        session = get_db_session()
        query = session.query(Tag).filter(Tag.deleted == False)  # noqa: E712

        if category_id:
            query = query.filter_by(category_id=category_id)

        if keyword and keyword.strip():
            query = apply_keyword_like(query, Tag.name, keyword.strip())

        query = query.order_by(Tag.updated_at.desc())
        return query.paginate(page=page, per_page=per_page, error_out=False)

    def list_tag_names_paginated(self, page: int, per_page: int, keyword: str = None):
        """分页查询标签名称（按名称排序）。"""
        session = get_db_session()
        query = session.query(Tag).filter(Tag.deleted == False)  # noqa: E712

        if keyword and keyword.strip():
            query = apply_keyword_like(query, Tag.name, keyword.strip())

        query = query.order_by(Tag.name)
        return query.paginate(page=page, per_page=per_page, error_out=False)

    def get_category_name_map(self, category_ids: set) -> Dict[int, str]:
        """按 ID 集合批量查询分类名称，返回 {category_id: name}。"""
        session = get_db_session()
        if not category_ids:
            return {}
        cats = session.query(TagCategory).filter(
            TagCategory.id.in_(category_ids), TagCategory.deleted == False  # noqa: E712
        ).all()
        return {c.id: c.name for c in cats}

    def get_category_name_by_id(self, category_id) -> Optional[str]:
        """按 ID 查询分类名称（未删除）。"""
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
