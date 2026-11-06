# -*- coding: utf-8 -*-
"""INT-423 数据可见性基座单测：Visibility 枚举 + visibility_filter 三助手。

覆盖（不依赖真库，visible_condition 以内存 SQLite 验证 SQL 语义）：
- Visibility 枚举仅二值（shared / private）
- visible_condition：admin 恒真 / 未认证仅 shared / 认证用户 shared+owner
- check_visible：owner / 共享 / admin 三视角放行，越权抛 VisibilityDenied
- filter_visible_owners：批量逐行过滤（admin 全量 / 未认证仅 shared /
  认证用户 shared+owner），保持入参顺序
- AuditEvent 含 PRIVATE_RESOURCE_ACCESS

验收口径对齐原卡：1. 枚举存在且仅二值；2. 三助手单测通过（owner/共享/
admin 三视角）；5. AuditEvent 含 PRIVATE_RESOURCE_ACCESS。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from sqlalchemy import (
    Column, Integer, MetaData, String, Table, create_engine, select,
)

from shared.infrastructure.visibility_filter import (
    VisibilityDenied,
    check_visible,
    filter_visible_owners,
    visible_condition,
)
from shared.models.common_enums import AuditEvent, Visibility


class TestVisibilityEnum:
    """验收①：Visibility 枚举存在且仅二值。"""

    def test_only_two_members(self):
        assert {m.name: m.value for m in Visibility} == {
            'SHARED': 'shared',
            'PRIVATE': 'private',
        }

    def test_values_match_spec(self):
        assert Visibility.SHARED.value == 'shared'
        assert Visibility.PRIVATE.value == 'private'


class TestVisibleCondition:
    """可见性条件构造：admin 恒真 / 未认证仅 shared / 认证 shared+owner。"""

    @pytest.fixture()
    def engine(self):
        eng = create_engine('sqlite://')
        meta = MetaData()
        t = Table(
            't', meta,
            Column('id', Integer, primary_key=True),
            Column('created_by_user_id', Integer),
            Column('visibility', String(20)),
        )
        meta.create_all(eng)
        with eng.begin() as conn:
            conn.execute(t.insert(), [
                {'id': 1, 'created_by_user_id': 1, 'visibility': 'private'},   # user1 的私有
                {'id': 2, 'created_by_user_id': 2, 'visibility': 'private'},   # 他人的私有
                {'id': 3, 'created_by_user_id': 2, 'visibility': 'shared'},    # 他人创建的共享
                {'id': 4, 'created_by_user_id': None, 'visibility': 'shared'},  # 无 owner 的共享
            ])
        return eng, t

    def _visible_ids(self, engine, table, user_id, is_admin):
        cond = visible_condition(
            table.c.created_by_user_id, table.c.visibility, user_id, is_admin)
        with engine.connect() as conn:
            return conn.execute(select(table.c.id).where(cond)).scalars().all()

    def test_admin_sees_all(self, engine):
        eng, t = engine
        assert self._visible_ids(eng, t, 1, True) == [1, 2, 3, 4]
        assert self._visible_ids(eng, t, None, True) == [1, 2, 3, 4]

    def test_authenticated_owner_plus_shared(self, engine):
        """owner / 共享 两视角：user1 可见自己的私有 + 全部共享。"""
        eng, t = engine
        assert self._visible_ids(eng, t, 1, False) == [1, 3, 4]

    def test_authenticated_other_private_hidden(self, engine):
        """user2 可见自己的私有 + 共享；user1 的私有不可见。"""
        eng, t = engine
        assert self._visible_ids(eng, t, 2, False) == [2, 3, 4]

    def test_anonymous_only_shared(self, engine):
        """未认证（user_id=None）仅共享行可见。"""
        eng, t = engine
        assert self._visible_ids(eng, t, None, False) == [3, 4]


class TestCheckVisible:
    """单行可见性校验：不通过抛 VisibilityDenied（网关映射 403/404）。"""

    def test_admin_always_visible(self):
        # admin 访问任何 owner 的私有行均放行
        check_visible(owner=2, vis='private', user_id=1, is_admin=True)

    def test_shared_visible_to_anyone(self):
        check_visible(owner=2, vis='shared', user_id=1, is_admin=False)
        check_visible(owner=2, vis='shared', user_id=None, is_admin=False)

    def test_owner_visible(self):
        check_visible(owner=1, vis='private', user_id=1, is_admin=False)

    def test_private_non_owner_denied(self):
        with pytest.raises(VisibilityDenied):
            check_visible(owner=2, vis='private', user_id=1, is_admin=False)

    def test_private_anonymous_denied(self):
        with pytest.raises(VisibilityDenied):
            check_visible(owner=2, vis='private', user_id=None, is_admin=False)


class TestFilterVisibleOwners:
    """批量逐行过滤（镜像 filter_purgeable_owners 的逐行口径）。"""

    ROWS = [
        (1, 1, 'private'),   # user1 的私有
        (2, 2, 'private'),   # 他人的私有
        (3, 2, 'shared'),    # 共享
        (4, None, 'shared'),  # 无 owner 的共享
    ]

    def test_admin_returns_all_in_order(self):
        assert filter_visible_owners(self.ROWS, 1, True) == [1, 2, 3, 4]

    def test_owner_plus_shared(self):
        assert filter_visible_owners(self.ROWS, 1, False) == [1, 3, 4]

    def test_other_user_private_hidden(self):
        assert filter_visible_owners(self.ROWS, 2, False) == [2, 3, 4]

    def test_anonymous_only_shared(self):
        assert filter_visible_owners(self.ROWS, None, False) == [3, 4]

    def test_empty_rows(self):
        assert filter_visible_owners([], 1, False) == []
        assert filter_visible_owners([], 1, True) == []


class TestAuditEvent:
    """验收⑤：AuditEvent 含 PRIVATE_RESOURCE_ACCESS。"""

    def test_private_resource_access_present(self):
        assert AuditEvent.PRIVATE_RESOURCE_ACCESS.value == 'PRIVATE_RESOURCE_ACCESS'
        assert 'PRIVATE_RESOURCE_ACCESS' in {e.value for e in AuditEvent}
