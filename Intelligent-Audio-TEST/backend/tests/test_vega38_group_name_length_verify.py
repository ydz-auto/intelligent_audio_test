# -*- coding: utf-8 -*-
"""VEGA-38 分组名长度守卫（审计 P1）——测试工程师独立验收用例

开发新增的 5 例在 ``test_audio_upload_group_name_source.py::TestGroupNameLengthBoundary``，
形状是「秒传 + groupNameType='root' + testCaseConfig.groupName」。本文件独立补三条开发
未覆盖、且直接对应审计 P1 用户可见后果的边界：

1. **真实前端文件夹导入形状**（`groupNameType=''` + `customGroupName=<目录名>`）下的超长
   目录名 —— 审计 P1 的原始场景：目录名长度不受前端约束（Windows 单级目录名上限 255），
   改动后 `effective_group_name` 才第一次可能是用户目录名；
2. **NFKC 归一后长度膨胀**（原始 ≤100、归一后 >100）—— 守卫必须作用在**归一后**的值上，
   否则落库仍是 DB 截断错；守卫若放在归一前，这条会漏（`_normalize_group_name` 只做
   NFKC + 空白折叠，NFKC 会让部分字符变长，如 U+337F 1 字符 → 「株式会社」4 字符）；
3. **归一后恰好 100、原始因空白 >100** —— 守卫不得误伤：假拒绝会把本可正常上传的文件拦掉，
   而落库值本就是归一后的 100 字符。

断言全部走真实 ``/api/v1/audios/upload/merge``，不 mock controller 内部函数。
接口内部 ``db.session.commit()`` 会穿透 conftest 外层事务回滚（conftest 已注明的已知限制），
故用 ``_NoCommitDB`` 把 commit 降级为 flush，并按精确 ID 兜底清理。
"""
import uuid
from unittest.mock import patch

from backend.models.database import db
from backend.models.models import (
    Audio,
    TestCase,
    TestCaseGroup,
    UploadFile,
    UploadTask,
)
from backend.utils.web.error_codes import ErrorCode

RUN_TAG = uuid.uuid4().hex[:8]
ENDPOINT = '/api/v1/audios/upload/merge'
ALGORITHM_TYPE = 'asr'
PATCH_REF_PARAMS = (
    'backend.utils.algorithm.reference_params_generator.ReferenceParamsGenerator.apply_to_config'
)
# 与 TestCaseGroup.name 的 String(100) 对齐（backend/models/models.py）
GROUP_NAME_MAX_LENGTH = 100
# DB 截断错裸奔时响应体里会出现的痕迹（审计 P1 的信息泄露面）
SQL_LEAK_MARKERS = (
    'psycopg2',
    'StringDataRightTruncation',
    'INSERT INTO',
    'test_case_groups',
)


class _NoCommitSession:
    """controller 视角的 session 代理：commit 降级为 flush，其余属性透传"""

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


def _padded(total_length):
    """构成长度恰为 total_length 的名字（带本次运行 tag，避免撞历史残留）"""
    prefix = f'VEGA38LENV_{RUN_TAG}_'
    assert total_length >= len(prefix), total_length
    return prefix + 'G' * (total_length - len(prefix))


def _purge(case_ids=(), audio_id=None, task_ids=()):
    """按精确 ID 清理本文件创建的行，不触碰其它测试的数据"""
    case_ids = list(case_ids)
    group_ids = set()
    if case_ids:
        group_ids = {
            gid
            for (gid,) in db.session.query(TestCase.group_id)
            .filter(TestCase.id.in_(case_ids))
            .all()
        }
        db.session.query(TestCase).filter(TestCase.id.in_(case_ids)).delete(
            synchronize_session=False
        )
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


class _UploadHarness:
    """秒传场景（total_chunks=0 + status=completed + 同 md5 音频已入库）上传建用例"""

    def __init__(self):
        self.task_ids = []
        self.case_ids = []
        self.audio_ids = []

    def upload(self, client, extra_payload):
        md5 = uuid.uuid4().hex
        audio = Audio(
            name=f'VEGA38LENV_{RUN_TAG}_{md5[:6]}.wav',
            file_path='/tmp/vega38lenv.wav',
            size=1,
            duration=1.0,
            format='wav',
            md5=md5,
        )
        db.session.add(audio)
        db.session.flush()
        self.audio_ids.append(audio.id)

        task = UploadTask(
            id=str(uuid.uuid4()), total_files=1, total_size=1, status='uploading'
        )
        db.session.add(task)
        self.task_ids.append(task.id)
        file_id = str(uuid.uuid4())
        db.session.add(
            UploadFile(
                id=file_id,
                task_id=task.id,
                filename=audio.name,
                original_filename=audio.name,
                relative_path='',
                size=1,
                md5=md5,
                status='completed',
                uploaded_size=1,
                completed_chunks=0,
                total_chunks=0,
            )
        )
        db.session.flush()

        import backend.controllers.audio_controller as audio_controller

        payload = {
            'fileId': file_id,
            'taskId': task.id,
            'createTestCase': True,
            'algorithmType': ALGORITHM_TYPE,
            **extra_payload,
        }
        with patch.object(audio_controller, 'db', _NoCommitDB(db)), patch(
            PATCH_REF_PARAMS
        ):
            resp = client.post(ENDPOINT, json=payload)
        return resp

    def track(self, data):
        if data.get('testCaseId'):
            self.case_ids.append(data['testCaseId'])
        return data

    def cleanup(self):
        _purge(case_ids=self.case_ids, task_ids=self.task_ids)
        for audio_id in self.audio_ids:
            _purge(audio_id=audio_id)


def _assert_business_rejection(resp, group_name):
    """超长分组名被拒的统一断言：400 / INVALID_PARAMS / 中文提示 / 不泄露 SQL / 未落库"""
    assert resp.status_code == 400, resp.get_json()
    body = resp.get_json()
    assert body['success'] is False, body
    assert body['code'] == ErrorCode.INVALID_PARAMS, body
    assert '分组名过长' in body['message'], body
    assert str(GROUP_NAME_MAX_LENGTH) in body['message'], body
    raw = resp.get_data(as_text=True)
    for marker in SQL_LEAK_MARKERS:
        assert marker not in raw, f'响应体泄露了 {marker!r}: {raw}'
    assert not TestCaseGroup.query.filter_by(name=group_name).first(), (
        f'被拒的分组名不应落库：{group_name!r}'
    )


class TestGroupNameLengthGuard:
    """分组名长度守卫的独立验收（审计 P1）"""

    def test_real_folder_import_shape_overlong_dirname_rejected(self, client, app):
        """真实前端文件夹导入形状：超长目录名 → 明确业务错误，不落库、不泄露 SQL

        浏览器实测的 merge 请求体（VEGA-38 复现记录）：
            groupNameType: ""            ← UploadOptions 没有「用例分组」UI，取不到值
            customGroupName: "<目录名>"   ← audioImport.ts 按文件所在根目录映射
            testCaseConfig.groupName: "<目录名>"
        """
        dirname = _padded(GROUP_NAME_MAX_LENGTH + 1)
        harness = _UploadHarness()
        try:
            resp = harness.upload(
                client,
                {
                    'groupNameType': '',
                    'customGroupName': dirname,
                    'testCaseConfig': {'groupName': dirname},
                },
            )
            _assert_business_rejection(resp, dirname)
        finally:
            harness.cleanup()

    def test_nfkc_expanded_name_over_limit_rejected(self, client, app):
        """原始 30 字符、NFKC 归一后 120 字符 → 同样必须被拒（守卫作用于归一后的值）

        U+337F「㍿」NFKC → 「株式会社」（1 → 4 字符）。守卫若放在归一**之前**，
        这条会漏到 `TestCaseGroup(name=...)` 落库，仍是 DB 截断错 + 原始 SQL 回传。
        """
        raw_name = '㍿' * 30
        normalized_name = '株式会社' * 30
        assert len(raw_name) <= GROUP_NAME_MAX_LENGTH < len(normalized_name)

        harness = _UploadHarness()
        try:
            resp = harness.upload(
                client,
                {
                    'groupNameType': 'root',
                    'customGroupName': '',
                    'testCaseConfig': {'groupName': raw_name},
                },
            )
            # 提示里的长度是**归一后**的长度，即 DB 真正要写入的值
            _assert_business_rejection(resp, normalized_name)
            assert str(len(normalized_name)) in resp.get_json()['message']
        finally:
            harness.cleanup()

    def test_name_over_limit_only_by_whitespace_is_accepted(self, client, app):
        """原始因空白 >100、归一后恰好 100 → 必须放行且落库为归一后的 100 字符

        防止守卫误伤：落库值本就是归一后的值，按原始长度拒绝会把可正常上传的文件拦掉。
        """
        normalized_name = _padded(GROUP_NAME_MAX_LENGTH)
        raw_name = normalized_name + ' ' * 20
        assert len(raw_name) > GROUP_NAME_MAX_LENGTH

        harness = _UploadHarness()
        try:
            resp = harness.upload(
                client,
                {
                    'groupNameType': 'root',
                    'customGroupName': '',
                    'testCaseConfig': {'groupName': raw_name},
                },
            )
            assert resp.status_code == 200, resp.get_json()
            data = harness.track(resp.get_json()['data'])
            assert data['instantUpload'] is True, data
            case_id = data['testCaseId']
            row = (
                db.session.query(TestCaseGroup.name)
                .join(TestCase, TestCase.group_id == TestCaseGroup.id)
                .filter(TestCase.id == case_id)
                .first()
            )
            assert row and row[0] == normalized_name, row
        finally:
            harness.cleanup()
