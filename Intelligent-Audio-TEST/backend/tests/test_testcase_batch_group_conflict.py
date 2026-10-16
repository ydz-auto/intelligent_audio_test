# -*- coding: utf-8 -*-
"""批量移动 / 复制到分组的同名处置 测试（VEGA-30）

本卡另两条**活跃**同名路径（审计 D3 补入）：

1. `TestCaseController._batch_move_to_group`：批量移动**不检查目标分组是否已有同名
   用例** → 可产生「**同组内**同名两条活跃」，恰好击穿用例创建路径
   （`audio_controller.py` 同名去重键 `(name, group_id)`）想维护的那条不变量
   → **本卡加冲突校验，一律拦**（这是缺陷，不是产品能力）。
2. `TestCaseController._batch_copy_to_group`：`name=tc.name` 逐字复制到目标分组，
   产生**跨组**同名 —— 这是**有意保留**的产品能力（前端以 `copy_to_group` 暴露），
   **不得拦死**，故本文件对它只做「仍然可用」的回归断言。

走真实接口 `POST /api/v1/testcases/batch`。
"""
import uuid
from unittest.mock import patch

import pytest

from backend.models.database import db
from backend.models.models import TestCase, TestCaseGroup

RUN_TAG = uuid.uuid4().hex[:8]
ENDPOINT = '/api/v1/testcases/batch'


class _NoCommitSession:
    """controller 视角的 session 代理：commit 降级为 flush，其余属性透传"""

    def __init__(self, real_session):
        self._real_session = real_session

    def commit(self):
        self._real_session.flush()

    def __getattr__(self, name):
        return getattr(self._real_session, name)


class _NoCommitDB:
    """controller 视角的 db 代理：只替换 session.commit，其余透传"""

    def __init__(self, real_db):
        self._real_db = real_db
        self.session = _NoCommitSession(real_db.session)

    def __getattr__(self, name):
        return getattr(self._real_db, name)


# ============================================================
# 辅助
# ============================================================

def _make_group(suffix):
    group = TestCaseGroup(
        id=str(uuid.uuid4()), name=f'批量组_{suffix}_{RUN_TAG}', algorithm_type='asr'
    )
    db.session.add(group)
    db.session.flush()
    return group


def _make_case(name, group_id, deleted=False):
    tc = TestCase(
        id=str(uuid.uuid4()), name=name, group_id=group_id, config={}, test_type='api'
    )
    tc.deleted = deleted
    db.session.add(tc)
    db.session.flush()
    return tc


def _post(client, action, ids, target_group_id):
    return client.post(
        ENDPOINT, json={'ids': ids, 'action': action, 'targetGroupId': target_group_id}
    )


def _purge(case_ids, group_ids):
    """按精确 ID 清理本测试创建的行（接口成功路径会 commit，绕过外层事务回滚）"""
    if case_ids:
        db.session.query(TestCase).filter(TestCase.id.in_(list(case_ids))).delete(
            synchronize_session=False
        )
    for group_id in group_ids:
        if not TestCase.query.filter_by(group_id=group_id).count():
            db.session.query(TestCaseGroup).filter(
                TestCaseGroup.id == group_id
            ).delete(synchronize_session=False)
    db.session.commit()


# ============================================================
# _batch_move_to_group：同组同名一律拦
# ============================================================

class TestBatchMoveToGroupConflict:
    """移动到目标分组后不得产生同组内同名活跃用例"""

    def test_move_into_group_with_same_name_is_blocked(self, client, app):
        """目标分组已有同名活跃用例 → 拦下，用例仍留在原分组"""
        source_group = _make_group('src1')
        target_group = _make_group('tgt1')
        name = f'待移动用例_{RUN_TAG}.wav'
        moved_case = _make_case(name, source_group.id)
        existing_case = _make_case(name, target_group.id)
        case_ids = [moved_case.id, existing_case.id]
        try:
            resp = _post(client, 'move_to_group', [moved_case.id], target_group.id)

            body = resp.get_json()
            assert body['success'] is False, body
            assert name in body['message']
            # 未提交移动：用例仍在原分组
            assert (
                TestCase.query.filter_by(id=moved_case.id).first().group_id
                == source_group.id
            )
        finally:
            _purge(case_ids, [source_group.id, target_group.id])

    def test_move_two_same_named_cases_together_is_blocked(self, client, app):
        """本次一起移入的两条用例互相同名 → 拦下（目标分组为空也一样）"""
        source_group = _make_group('src2')
        target_group = _make_group('tgt2')
        name = f'同名两条_{RUN_TAG}.wav'
        first = _make_case(name, source_group.id)
        second = _make_case(name, source_group.id)
        case_ids = [first.id, second.id]
        try:
            resp = _post(client, 'move_to_group', case_ids, target_group.id)

            body = resp.get_json()
            assert body['success'] is False, body
            assert name in body['message']
            for case_id in case_ids:
                assert (
                    TestCase.query.filter_by(id=case_id).first().group_id
                    == source_group.id
                )
        finally:
            _purge(case_ids, [source_group.id, target_group.id])

    def test_move_to_group_without_conflict_succeeds(self, client, app):
        """目标分组无同名活跃用例 → 正常移动（既有行为不回归）"""
        import backend.controllers.testcase_controller as testcase_controller

        source_group = _make_group('src3')
        target_group = _make_group('tgt3')
        case = _make_case(f'可移动用例_{RUN_TAG}.wav', source_group.id)
        try:
            with patch.object(testcase_controller, 'db', _NoCommitDB(db)):
                resp = _post(client, 'move_to_group', [case.id], target_group.id)

            body = resp.get_json()
            assert body['success'] is True, body
            assert TestCase.query.filter_by(id=case.id).first().group_id == target_group.id
        finally:
            _purge([case.id], [source_group.id, target_group.id])

    def test_move_to_same_group_is_idempotent(self, client, app):
        """用例本来就在目标分组、且无其它同名活跃用例 → 不视为冲突"""
        import backend.controllers.testcase_controller as testcase_controller

        target_group = _make_group('tgt4')
        case = _make_case(f'原地用例_{RUN_TAG}.wav', target_group.id)
        try:
            with patch.object(testcase_controller, 'db', _NoCommitDB(db)):
                resp = _post(client, 'move_to_group', [case.id], target_group.id)

            body = resp.get_json()
            assert body['success'] is True, body
        finally:
            _purge([case.id], [target_group.id])

    def test_soft_deleted_case_in_target_group_does_not_block(self, client, app):
        """目标分组里的**软删**同名用例不算冲突（deleted 过滤语义不变）"""
        import backend.controllers.testcase_controller as testcase_controller

        source_group = _make_group('src5')
        target_group = _make_group('tgt5')
        name = f'软删同名_{RUN_TAG}.wav'
        moved_case = _make_case(name, source_group.id)
        deleted_case = _make_case(name, target_group.id, deleted=True)
        try:
            with patch.object(testcase_controller, 'db', _NoCommitDB(db)):
                resp = _post(client, 'move_to_group', [moved_case.id], target_group.id)

            body = resp.get_json()
            assert body['success'] is True, body
            assert (
                TestCase.query.filter_by(id=moved_case.id).first().group_id
                == target_group.id
            )
        finally:
            _purge([moved_case.id, deleted_case.id], [source_group.id, target_group.id])


# ============================================================
# _batch_copy_to_group：既有跨组同名复制能力必须保留
# ============================================================

class TestBatchCopyToGroupRegression:
    """复制到分组的跨组同名是**有意保留**的产品能力，本卡不得拦死"""

    def test_cross_group_same_name_copy_still_works(self, client, app):
        """把用例复制到已有同名用例的分组：仍然成功，且复制出的行保持逐字同名"""
        import backend.controllers.testcase_controller as testcase_controller

        source_group = _make_group('csrc')
        target_group = _make_group('ctgt')
        name = f'跨组复制用例_{RUN_TAG}.wav'
        source_case = _make_case(name, source_group.id)
        target_case = _make_case(name, target_group.id)
        new_case_id = None
        try:
            with patch.object(testcase_controller, 'db', _NoCommitDB(db)):
                resp = _post(client, 'copy_to_group', [source_case.id], target_group.id)

            body = resp.get_json()
            assert body['success'] is True, body

            copied = (
                TestCase.query.filter_by(name=name, group_id=target_group.id)
                .filter(TestCase.id != target_case.id)
                .all()
            )
            assert len(copied) == 1
            new_case_id = copied[0].id
        finally:
            _purge([source_case.id, target_case.id, new_case_id], [source_group.id, target_group.id])
