# -*- coding: utf-8 -*-
"""VEGA-38 独立验收：`merge_chunks` 缺省分组分支（测试工程师补充）

背景：开发交付评论把「缺省落 `音频上传生成`」这一级说成由 VEGA-30 的
`test_audio_case_name_dedup.py::test_missing_group_name_logs_warning` 覆盖
（理由「同一函数路径」）。核对后该说法**不成立**——那条用例直接调
`AudioController._create_test_case_from_audio(...)`，覆盖的是该函数内部的缺省分组
分支；而本卡改动所在的 `merge_chunks` 里 `effective_group_name` 的缺省分支
（`else: effective_group_name = DEFAULT_UPLOAD_GROUP_NAME`）**没有任何用例覆盖**。

本文件补上这条断言：当分组级配置 / 目录名 / 顶层字段 / 算法类型**全空**时，
分组名必须落到缺省「音频上传生成」，且与改动前一致。

运行：
    python -m pytest backend/tests/test_vega38_default_group_branch_verify.py -v
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

RUN_TAG = uuid.uuid4().hex[:8]
DEFAULT_GROUP = '音频上传生成'
PATCH_REF_PARAMS = (
    'backend.utils.algorithm.reference_params_generator.ReferenceParamsGenerator.apply_to_config'
)


class _NoCommitSession:
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


def _purge(case_ids=(), audio_id=None, task_ids=()):
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


def _upload(client, extra_payload):
    """秒传分支上传建用例；返回 (响应 data, 清理句柄)"""
    md5 = uuid.uuid4().hex
    audio = Audio(
        name=f'VEGA38DEF_{RUN_TAG}_{md5[:6]}.wav',
        file_path='/tmp/vega38def.wav',
        size=1,
        duration=1.0,
        format='wav',
        md5=md5,
    )
    db.session.add(audio)
    db.session.flush()

    task = UploadTask(
        id=str(uuid.uuid4()), total_files=1, total_size=1, status='uploading'
    )
    db.session.add(task)
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
        **extra_payload,
    }
    with patch.object(audio_controller, 'db', _NoCommitDB(db)), patch(PATCH_REF_PARAMS):
        resp = client.post('/api/v1/audios/upload/merge', json=payload)

    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()['data']
    assert data['instantUpload'] is True, data

    def cleanup():
        _purge(case_ids=[data['testCaseId']] if data.get('testCaseId') else [],
               audio_id=audio.id, task_ids=[task.id])

    return data, cleanup


def _group_name_of_case(case_id):
    row = (
        db.session.query(TestCaseGroup.name)
        .join(TestCase, TestCase.group_id == TestCaseGroup.id)
        .filter(TestCase.id == case_id)
        .first()
    )
    return row[0] if row else None


def test_all_group_sources_empty_lands_in_default_group(client, app):
    """四个分组名来源全空 → 落缺省「音频上传生成」（改动前口径）"""
    data, cleanup = _upload(
        client,
        {
            'groupNameType': 'root',      # custom 闸门关闭
            'customGroupName': '',        # 目录名/自定义名空
            'testCaseGroupName': '',      # 顶层字段空
            'algorithmType': '',          # 算法类型空
            'testCaseConfig': {'inheritTags': True},  # 分组级配置无 group_name
        },
    )
    try:
        assert data.get('testCaseId'), data
        assert _group_name_of_case(data['testCaseId']) == DEFAULT_GROUP
    finally:
        cleanup()


def test_tc_config_empty_group_name_does_not_override_default(client, app):
    """分组级配置存在但 group_name 为 None/空串 → 不得被当成一个分组名"""
    data, cleanup = _upload(
        client,
        {
            'groupNameType': 'root',
            'customGroupName': '',
            'testCaseGroupName': '',
            'algorithmType': '',
            'testCaseConfig': {'groupName': None, 'inheritTags': True},
        },
    )
    try:
        assert data.get('testCaseId'), data
        assert _group_name_of_case(data['testCaseId']) == DEFAULT_GROUP
    finally:
        cleanup()


def test_tc_config_whitespace_only_group_name_falls_through(client, app):
    """分组级分组名只有空白 → 归一后为空，必须继续走兜底链而不是建一个空白分组"""
    data, cleanup = _upload(
        client,
        {
            'groupNameType': 'root',
            'customGroupName': '',
            'testCaseGroupName': '',
            'algorithmType': 'asr',
            'testCaseConfig': {'groupName': '   ', 'inheritTags': True},
        },
    )
    try:
        assert data.get('testCaseId'), data
        assert _group_name_of_case(data['testCaseId']) == 'asr'
    finally:
        cleanup()
