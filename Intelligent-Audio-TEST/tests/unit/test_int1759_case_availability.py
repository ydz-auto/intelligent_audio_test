# -*- coding: utf-8 -*-
"""INT-1759 验收补充：用例可用性三分（D0 裁定 A10-4）的真实 ORM 口径。

实施者单测用 monkeypatch 替换了 `fetch_case_availability`，软删 / 私有非 owner
的判定本身没有被任何测试执行到（`check_visible` 真身）。本文件补这一层：

- missing：目标库不存在 / 已软删
- invisible：存在且未软删，但私有用例且非 owner、非 admin
- available：其余
- `fetch_existing_case_ids` 必须等于 available 子集（预检 warning 与硬校验同源）
- `_case_consistency` 的 missingCaseIds 必须是 missing ∪ invisible（不可用即缺失）
"""
import os
import tempfile

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int1759_') + '/case.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from sqlalchemy import create_engine

import shared.models.database as database
from task_service.infrastructure.persistence.models import TestCase
from task_service.infrastructure.persistence.transfer_repository import transfer_repository

OWNER = 9101759
OTHER = 9201759

SHARED_ID = 'int1759_case_shared'
DELETED_ID = 'int1759_case_deleted'
PRIVATE_OWNER_ID = 'int1759_case_private_owner'
PRIVATE_OTHER_ID = 'int1759_case_private_other'
GHOST_ID = 'int1759_case_not_exist'

ALL_IDS = [SHARED_ID, DELETED_ID, PRIVATE_OWNER_ID, PRIVATE_OTHER_ID, GHOST_ID]


@pytest.fixture()
def cases():
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    engine = create_engine(f'sqlite:///{path}', connect_args={'check_same_thread': False})
    database._engine = engine
    database._SessionFactory.configure(bind=engine)
    database.Base.metadata.create_all(engine)

    session = database.get_db_session()
    try:
        session.add_all([
            TestCase(id=SHARED_ID, name='接线测试_共享用例', config={},
                     visibility='shared', deleted=False),
            TestCase(id=DELETED_ID, name='接线测试_软删用例', config={},
                     visibility='shared', deleted=True),
            TestCase(id=PRIVATE_OWNER_ID, name='接线测试_私有owner', config={},
                     visibility='private', created_by_user_id=OWNER, deleted=False),
            TestCase(id=PRIVATE_OTHER_ID, name='接线测试_私有他人', config={},
                     visibility='private', created_by_user_id=OTHER, deleted=False),
        ])
        session.commit()
    finally:
        session.close()
    yield ALL_IDS
    database.remove_db_session()
    engine.dispose()
    os.remove(path)


def test_missing_and_deleted_are_unavailable(cases):
    """软删用例必须算 missing（A10-4 第一条）；不存在的 id 同样 missing。"""
    got = transfer_repository.fetch_case_availability(
        ALL_IDS, user_id=OWNER, is_admin=False)
    assert got['missing'] == {DELETED_ID, GHOST_ID}
    assert got['invisible'] == {PRIVATE_OTHER_ID}
    assert got['available'] == {SHARED_ID, PRIVATE_OWNER_ID}


def test_private_visible_to_owner_only(cases):
    """私有用例：owner 可用，非 owner 归入 invisible（不是 missing，也不算存在）。"""
    as_other = transfer_repository.fetch_case_availability(
        ALL_IDS, user_id=OTHER, is_admin=False)
    assert PRIVATE_OWNER_ID in as_other['invisible']
    assert PRIVATE_OWNER_ID not in as_other['available']
    assert as_other['missing'] == {DELETED_ID, GHOST_ID}

    as_owner = transfer_repository.fetch_case_availability(
        ALL_IDS, user_id=OWNER, is_admin=False)
    assert PRIVATE_OWNER_ID in as_owner['available']
    assert PRIVATE_OWNER_ID not in as_owner['invisible']


def test_admin_sees_all_alive_cases(cases):
    got = transfer_repository.fetch_case_availability(ALL_IDS, is_admin=True)
    assert got['available'] == {SHARED_ID, PRIVATE_OWNER_ID, PRIVATE_OTHER_ID}
    assert got['invisible'] == set()
    assert got['missing'] == {DELETED_ID, GHOST_ID}


def test_anonymous_only_sees_shared(cases):
    got = transfer_repository.fetch_case_availability(ALL_IDS, user_id=None, is_admin=False)
    assert got['available'] == {SHARED_ID}
    assert got['invisible'] == {PRIVATE_OWNER_ID, PRIVATE_OTHER_ID}


def test_existing_case_ids_is_available_subset(cases):
    legacy = transfer_repository.fetch_existing_case_ids(ALL_IDS, user_id=OWNER, is_admin=False)
    assert legacy == {SHARED_ID, PRIVATE_OWNER_ID}


def test_case_consistency_payload_counts_invisible_as_missing(cases):
    """执行侧回执：missingCaseIds = missing ∪ invisible，invisible 另列。"""
    from shared.infrastructure.user_context import (
        set_current_user_id,
        set_current_user_is_admin,
    )
    from task_service.application.task.data_transfer_import_service import (
        data_transfer_import_service,
    )

    rows_by_table = {
        'task_case_relations': [
            {'task_id': 1, 'test_case_id': SHARED_ID},
            {'task_id': 1, 'test_case_id': DELETED_ID},
            {'task_id': 1, 'test_case_id': PRIVATE_OTHER_ID},
            {'task_id': 1, 'test_case_id': GHOST_ID},
        ],
    }
    set_current_user_id(OWNER)
    set_current_user_is_admin(False)
    try:
        result = data_transfer_import_service._case_consistency(rows_by_table, required=True)
    finally:
        set_current_user_id(None)
        set_current_user_is_admin(False)

    assert result['required'] is True
    assert result['complete'] is False
    assert result['missingCaseIds'] == sorted([DELETED_ID, GHOST_ID, PRIVATE_OTHER_ID])
    assert result['invisibleCaseIds'] == [PRIVATE_OTHER_ID]
    assert result['missingCount'] == 3
    assert result['truncated'] is False
