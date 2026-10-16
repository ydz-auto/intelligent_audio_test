# -*- coding: utf-8 -*-
"""VEGA-30 独立验收测试（测试工程师自建，不复用开发者用例）

按卡描述「验收标准」1-4 条逐条独立构造，全部走**真实 HTTP 接口**或真实 controller
入口，不依赖测试库中的历史残留状态（用例名/分组名带本次运行 tag；接口路径的
`db.session.commit()` 用代理降级为 flush，避免污染共享测试库）。

覆盖：
1. 同一音频分别以「空 / 带目录」两种上传形态上传 → 不再新增跨组同名活跃用例
   （含**对照组**：把跨组判重关掉后确实会建出两条逐字同名的活跃用例，证明是本卡
   新增的拦截在起作用，而不是环境偶然）
2. 同秒两次同名上传 → 两行名字不同（`_HHMMSS` / `_HHMMSS_2`）
3. `_batch_move_to_group` 移入已有同名活跃用例的分组 → 拦下 + 点名冲突用例名
4. 回归：`_batch_copy_to_group` 跨组同名复制**仍然可用**；无冲突的移动仍然可用；
   单条上传仍能正常建用例（拦截不得过度触发）
"""
import uuid
from datetime import datetime
from unittest.mock import patch

import pytest

from backend.models.database import db
from backend.models.models import (
    Audio,
    TestCase,
    TestCaseGroup,
    UploadFile,
    UploadTask,
)

RUN_TAG = uuid.uuid4().hex[:8]
AUDIO_FILE = f'JG0103_跑步配速计算_{RUN_TAG}_silence.wav'
CASE_BASE_NAME = f'测试用例_{AUDIO_FILE}'
DIR_GROUP = f'验收目录_{RUN_TAG}'
SAME_SECOND_GROUP = f'验收同秒_{RUN_TAG}'
MERGE_ENDPOINT = '/api/v1/audios/upload/merge'
BATCH_ENDPOINT = '/api/v1/testcases/batch'
AC = 'backend.controllers.audio_controller'
TC = 'backend.controllers.testcase_controller'
PATCH_REF_PARAMS = (
    'backend.utils.algorithm.reference_params_generator.ReferenceParamsGenerator.apply_to_config'
)
FROZEN_NOW = datetime(2026, 10, 16, 15, 0, 0)


class _NoCommitSession:
    """commit 降级为 flush：让 conftest 外层事务回滚仍然有效（不污染共享测试库）"""

    def __init__(self, real_session):
        self._real_session = real_session

    def commit(self):
        self._real_session.flush()

    def __getattr__(self, name):
        return getattr(self._real_session, name)


class _NoCommitDB:
    def __init__(self, real_db):
        self._real_db = real_db
        self.session = _NoCommitSession(real_db.session)

    def __getattr__(self, name):
        return getattr(self._real_db, name)


# ============================================================
# 数据构造 / 断言辅助
# ============================================================

def _make_group(name):
    group = TestCaseGroup(id=str(uuid.uuid4()), name=name, algorithm_type='asr')
    db.session.add(group)
    db.session.flush()
    return group


def _make_audio(md5, name=AUDIO_FILE):
    audio = Audio(name=name, file_path='/tmp/vega30_acc.wav', size=1, duration=1.0,
                  format='wav', md5=md5)
    db.session.add(audio)
    db.session.flush()
    return audio


def _make_case(name, group_id):
    tc = TestCase(id=str(uuid.uuid4()), name=name, group_id=group_id, config={},
                  test_type='api')
    db.session.add(tc)
    db.session.flush()
    return tc


def _active_case_names_in_group(group_id):
    return [
        n for (n,) in db.session.query(TestCase.name).filter(
            TestCase.group_id == group_id, TestCase.deleted == False  # noqa: E712
        ).all()
    ]


def _duplicated_active_names(name):
    """同名活跃用例（跨分组），返回 [(name, 分组名集合)]"""
    rows = db.session.query(TestCase.name, TestCase.group_id).filter(
        TestCase.name == name, TestCase.deleted == False  # noqa: E712
    ).all()
    if len(rows) < 2:
        return []
    return [(name, {g for _, g in rows})]


def _instant_upload(client, md5, file_name, relative_path, extra):
    """构造秒传场景并 POST /api/v1/audios/upload/merge（返回 resp, task_id, file_id）"""
    task = UploadTask(id=str(uuid.uuid4()), total_files=1, total_size=1,
                      status='uploading')
    db.session.add(task)
    file_id = str(uuid.uuid4())
    db.session.add(UploadFile(
        id=file_id, task_id=task.id, filename=file_name, original_filename=file_name,
        relative_path=relative_path, size=1, md5=md5, status='completed',
        uploaded_size=1, completed_chunks=0, total_chunks=0,
    ))
    db.session.flush()
    resp = client.post(MERGE_ENDPOINT, json={
        'fileId': file_id,
        'taskId': task.id,
        'createTestCase': True,
        'algorithmType': 'asr',
        **extra,
    })
    return resp, task.id, file_id


def _purge(case_ids=(), group_ids=(), audio_id=None, task_ids=()):
    """按精确 ID 清理本测试写入的行（接口成功路径可能已 flush/commit 出外层事务）"""
    if case_ids:
        db.session.query(TestCase).filter(
            TestCase.id.in_(list(case_ids))
        ).delete(synchronize_session=False)
    for group_id in group_ids:
        if not TestCase.query.filter_by(group_id=group_id).count():
            db.session.query(TestCaseGroup).filter(
                TestCaseGroup.id == group_id
            ).delete(synchronize_session=False)
    if audio_id is not None:
        db.session.query(Audio).filter(Audio.id == audio_id).delete(
            synchronize_session=False
        )
    for task_id in task_ids:
        db.session.query(UploadFile).filter(UploadFile.task_id == task_id).delete(
            synchronize_session=False
        )
        db.session.query(UploadTask).filter(UploadTask.id == task_id).delete(
            synchronize_session=False
        )
    db.session.commit()


def _case_ids_by_name(name):
    return [i for (i,) in db.session.query(TestCase.id).filter(TestCase.name == name).all()]


def _group_ids_by_name(name):
    return [i for (i,) in db.session.query(TestCaseGroup.id).filter(
        TestCaseGroup.name == name).all()]


# ============================================================
# 验收标准 1：同一音频「空 / 带目录」两种上传形态，不新增跨组同名活跃用例
# ============================================================

class TestCriterion1CrossGroupUpload:
    """同一音频，不带目录（root）与带目录（folder）各上传一次"""

    def _two_uploads(self, client, md5):
        """返回 (root_resp, folder_resp, task_ids)"""
        task_ids = []
        root_resp, t1, _ = _instant_upload(
            client, md5, AUDIO_FILE, '',
            {'groupNameType': 'root', 'customGroupName': ''},
        )
        task_ids.append(t1)
        folder_resp, t2, _ = _instant_upload(
            client, md5, AUDIO_FILE, f'{DIR_GROUP}/{AUDIO_FILE}',
            {'groupNameType': 'folder', 'customGroupName': DIR_GROUP},
        )
        task_ids.append(t2)
        return root_resp, folder_resp, task_ids

    def test_second_upload_does_not_create_cross_group_duplicate(self, client, app):
        import backend.controllers.audio_controller as audio_controller

        audio = _make_audio(md5='c' * 32)
        task_ids = []
        try:
            with patch.object(audio_controller, 'db', _NoCommitDB(db)), \
                    patch(PATCH_REF_PARAMS):
                root_resp, folder_resp, task_ids = self._two_uploads(client, audio.md5)

            assert root_resp.status_code == 200, root_resp.get_json()
            assert folder_resp.status_code == 200, folder_resp.get_json()
            root_data = root_resp.get_json()['data']
            folder_data = folder_resp.get_json()['data']

            # 第一次建出用例；第二次（另一个分组）被拦，不建用例
            assert root_data.get('testCaseId'), root_data
            assert folder_data.get('testCaseId') is None, folder_data
            # 拦截不静默：响应体给出可见原因，并点名冲突所在分组
            reason = folder_data.get('testCaseSkippedReason')
            assert reason, folder_data
            first_case = TestCase.query.filter_by(id=root_data['testCaseId']).first()
            first_group = TestCaseGroup.query.filter_by(id=first_case.group_id).first()
            assert first_group.name in reason, (first_group.name, reason)
            # 目标分组不得被凭空建出（被拦就不留空分组）
            assert TestCaseGroup.query.filter_by(name=DIR_GROUP).first() is None
            # 核心断言：不存在跨组同名的活跃用例
            assert _duplicated_active_names(CASE_BASE_NAME) == []
        finally:
            case_ids = _case_ids_by_name(CASE_BASE_NAME)
            _purge(case_ids=case_ids,
                   group_ids=_group_ids_by_name(DIR_GROUP),
                   audio_id=audio.id, task_ids=task_ids)

    def test_control_without_guard_reproduces_the_defect(self, client, app):
        """对照组：把跨组判重关掉（等价于本卡之前的代码路径），同一场景确实建出
        两条**逐字同名**、分属不同分组的活跃用例 —— 证明上一条断言测的是本卡的拦截"""
        import backend.controllers.audio_controller as audio_controller

        audio = _make_audio(md5='d' * 32, name=f'对照_{AUDIO_FILE}')
        control_base = f'测试用例_对照_{AUDIO_FILE}'
        task_ids = []
        try:
            with patch.object(audio_controller, 'db', _NoCommitDB(db)), \
                    patch.object(audio_controller.AudioController,
                                 '_find_active_case_in_other_group',
                                 staticmethod(lambda *a, **k: None)), \
                    patch(PATCH_REF_PARAMS):
                root_resp, folder_resp, task_ids = self._two_uploads(client, audio.md5)

            root_data = root_resp.get_json()['data']
            folder_data = folder_resp.get_json()['data']
            # 关掉判重后，两次都建了用例，且名字逐字相同、分组不同
            assert root_data.get('testCaseId'), root_data
            assert folder_data.get('testCaseId'), folder_data
            rows = TestCase.query.filter_by(name=control_base, deleted=False).all()
            assert len(rows) == 2, [(r.name, r.group_id) for r in rows]
            assert len({r.group_id for r in rows}) == 2
        finally:
            case_ids = _case_ids_by_name(control_base)
            _purge(case_ids=case_ids,
                   group_ids=_group_ids_by_name(DIR_GROUP),
                   audio_id=audio.id, task_ids=task_ids)

    def test_single_upload_still_creates_case(self, client, app):
        """回归：普通单次上传仍能建用例（拦截不得过度触发）"""
        import backend.controllers.audio_controller as audio_controller

        audio = _make_audio(md5='e' * 32, name=f'单次_{AUDIO_FILE}')
        task_ids = []
        try:
            with patch.object(audio_controller, 'db', _NoCommitDB(db)), \
                    patch(PATCH_REF_PARAMS):
                resp, t1, _ = _instant_upload(
                    client, audio.md5, f'单次_{AUDIO_FILE}', '',
                    {'groupNameType': 'root', 'customGroupName': ''},
                )
            task_ids.append(t1)
            assert resp.status_code == 200, resp.get_json()
            data = resp.get_json()['data']
            assert data.get('testCaseId'), data
            assert data.get('testCaseSkippedReason') is None, data
        finally:
            _purge(case_ids=_case_ids_by_name(f'测试用例_单次_{AUDIO_FILE}'),
                   audio_id=audio.id, task_ids=task_ids)


# ============================================================
# 验收标准 2：同秒两次同名上传，两行名字不同
# ============================================================

class TestCriterion2SameSecondNaming:

    @staticmethod
    def _create(audio_id, group_name):
        from backend.controllers.audio_controller import AudioController

        with patch(PATCH_REF_PARAMS):
            return AudioController._create_test_case_from_audio(
                audio_id, ['api'], [], group_name=group_name, algorithm_type='asr'
            )

    def test_same_second_three_uploads_get_distinct_names(self, app):
        """同一秒内连续三次同名上传（同分组）：三个名字互不相同

        旧实现「单次查询 + 只加一次秒级后缀」会让第 2、3 次都得到 `_HHMMSS` 而撞名。
        """
        audio = _make_audio(md5='f' * 32, name=f'同秒_{AUDIO_FILE}')
        with patch(f'{AC}.now_cst', return_value=FROZEN_NOW):
            ids = []
            for _ in range(3):
                ids += self._create(audio.id, SAME_SECOND_GROUP)
        assert len(ids) == 3, ids
        names = [TestCase.query.filter_by(id=i).first().name for i in ids]
        assert len(set(names)) == 3, names
        base = f'测试用例_同秒_{AUDIO_FILE}'
        assert names[0] == base, names
        assert names[1] == f'{base}_150000', names
        assert names[2] == f'{base}_150000_2', names

    def test_resolve_unique_case_name_is_looped(self, app):
        """`_resolve_unique_case_name` 在目标分组内循环取到不冲突的名字"""
        from backend.controllers.audio_controller import AudioController

        group = _make_group(SAME_SECOND_GROUP)
        base = f'循环_{RUN_TAG}.wav'
        with patch(f'{AC}.now_cst', return_value=FROZEN_NOW):
            resolved = []
            for _ in range(3):
                name = AudioController._resolve_unique_case_name(base, group.id)
                resolved.append(name)
                _make_case(name, group.id)  # 落库后再取下一个
        assert resolved == [base, f'{base}_150000', f'{base}_150000_2'], resolved


# ============================================================
# 验收标准 3 / 4：批量移动拦同组同名；批量复制保持可用
# ============================================================

class TestCriterion3MoveAndCriterion4Copy:

    @staticmethod
    def _post(client, action, ids, target_group_id):
        return client.post(BATCH_ENDPOINT, json={
            'ids': ids, 'action': action, 'targetGroupId': target_group_id,
        })

    def test_move_into_group_with_same_name_is_blocked(self, client, app):
        import backend.controllers.testcase_controller as tc_controller

        src = _make_group(f'源_{RUN_TAG}')
        dst = _make_group(f'目标_{RUN_TAG}')
        name = f'移动同名_{RUN_TAG}.wav'
        moved = _make_case(name, src.id)
        existing = _make_case(name, dst.id)
        try:
            with patch.object(tc_controller, 'db', _NoCommitDB(db)):
                resp = self._post(client, 'move_to_group', [moved.id], dst.id)

            body = resp.get_json()
            assert body.get('success') is False, body
            assert name in body.get('message', ''), body
            # 移动未生效：用例仍在原分组；目标分组仍是 1 条同名
            assert TestCase.query.filter_by(id=moved.id).first().group_id == src.id
            assert _active_case_names_in_group(dst.id).count(name) == 1
        finally:
            _purge(case_ids=[moved.id, existing.id], group_ids=[src.id, dst.id])

    def test_move_without_conflict_still_works(self, client, app):
        import backend.controllers.testcase_controller as tc_controller

        src = _make_group(f'源2_{RUN_TAG}')
        dst = _make_group(f'目标2_{RUN_TAG}')
        moved = _make_case(f'正常移动_{RUN_TAG}.wav', src.id)
        try:
            with patch.object(tc_controller, 'db', _NoCommitDB(db)):
                resp = self._post(client, 'move_to_group', [moved.id], dst.id)

            body = resp.get_json()
            assert body.get('success') is True, body
            assert TestCase.query.filter_by(id=moved.id).first().group_id == dst.id
        finally:
            _purge(case_ids=[moved.id], group_ids=[src.id, dst.id])

    def test_move_two_same_named_cases_together_is_blocked(self, client, app):
        """一起移入的两条同名用例也不得造成目标分组内同名"""
        import backend.controllers.testcase_controller as tc_controller

        src_a = _make_group(f'源A_{RUN_TAG}')
        src_b = _make_group(f'源B_{RUN_TAG}')
        dst = _make_group(f'目标3_{RUN_TAG}')
        name = f'两条同名_{RUN_TAG}.wav'
        a = _make_case(name, src_a.id)
        b = _make_case(name, src_b.id)
        try:
            with patch.object(tc_controller, 'db', _NoCommitDB(db)):
                resp = self._post(client, 'move_to_group', [a.id, b.id], dst.id)

            body = resp.get_json()
            assert body.get('success') is False, body
            assert name in body.get('message', ''), body
            assert _active_case_names_in_group(dst.id) == []
        finally:
            _purge(case_ids=[a.id, b.id], group_ids=[src_a.id, src_b.id, dst.id])

    def test_copy_to_group_same_name_still_allowed(self, client, app):
        """验收标准 4：跨组同名复制是有意保留的能力，不得被本卡拦死"""
        import backend.controllers.testcase_controller as tc_controller

        src = _make_group(f'源C_{RUN_TAG}')
        dst = _make_group(f'目标C_{RUN_TAG}')
        name = f'复制同名_{RUN_TAG}.wav'
        src_case = _make_case(name, src.id)
        try:
            with patch.object(tc_controller, 'db', _NoCommitDB(db)):
                resp = self._post(client, 'copy_to_group', [src_case.id], dst.id)

            body = resp.get_json()
            assert body.get('success') is True, body
            copied = _active_case_names_in_group(dst.id)
            assert copied == [name], copied
            assert len(_case_ids_by_name(name)) == 2
        finally:
            _purge(case_ids=_case_ids_by_name(name), group_ids=[src.id, dst.id])
