# -*- coding: utf-8 -*-
"""上传建用例的同名处置 / 分组名归一 测试（VEGA-30）

缺陷：`_create_test_case_from_audio` 的同名去重键含 group_id，同一音频以「带目录 /
不带目录」两种方式上传时会落到不同分组（带目录 → 目录名分组，不带目录 → 默认分组 /
算法类型分组），旧实现跨组判不出来，两行用例名**逐字相同**（实测 JG0103 / JG0078 /
JG0045 / JS135），按编号/名字匹配会命中配置不同的行（`playback_device_id` 8 vs 5，
评估比对基准也不同）。

本卡口径（见首条评论）：
- **同组内去重键保持现状** `(name, group_id, deleted=False)` —— 不改成"分组无关"，
  因为跨组同名是**有意保留的产品能力**（`_batch_copy_to_group` 逐字复制到目标分组）。
- **上传路径（隐式建用例）按 `audio_id` 拦截**：同一音频已在其它分组有活跃用例时，
  不再重复建用例，并留下 warning 日志 + 响应体可见原因。
- 同秒两次上传靠**循环取不冲突名字**（`_HHMMSS` / `_HHMMSS_2` / ...）。
- 分组名 strip + 全半角归一；缺省落默认分组不静默。

本文件覆盖：
1. `_resolve_unique_case_name`：判重范围**限定目标分组** + 同秒后缀循环
2. `_normalize_group_name`：strip + 全半角归一
3. `_extract_audio_ids_from_config` / `_find_active_case_in_other_group`：跨组音频身份判重
4. `_create_test_case_from_audio`：跨组重复被拦、同组重复改名、分组名归一、缺省分组告警
5. 上传接口（`/api/v1/audios/upload/merge` 秒传分支）既有行为不被破坏

测试用独立测试库 intelligent_audio_test_test，由 conftest 的外层事务回滚隔离。
用例名/分组名带本次运行的随机 tag，避免测试库中历史残留行干扰断言。
"""
import uuid
from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy import func

from backend.models.database import db
from backend.models.models import (
    Audio,
    TestCase,
    TestCaseGroup,
    UploadFile,
    UploadTask,
)

# 本次运行的唯一 tag：测试库中可能有历史提交残留，避免同名判重断言被污染
RUN_TAG = uuid.uuid4().hex[:8]
AUDIO_NAME = f'JG0103_跑步配速计算_{RUN_TAG}_silence.wav'
BASE_CASE_NAME = f'测试用例_{AUDIO_NAME}'
# 分组名同样带 tag：test_case_groups 有 (name, algorithm_type) 部分唯一索引
GROUP_TAKEOVER = f'话轮接管_{RUN_TAG}'
GROUP_REJECT = f'拒识_{RUN_TAG}'
DEFAULT_GROUP = '音频上传生成'
FIXED_NOW = datetime(2026, 10, 16, 14, 30, 52)
CONTROLLER = 'backend.controllers.audio_controller'
PATCH_REF_PARAMS = (
    'backend.utils.algorithm.reference_params_generator.ReferenceParamsGenerator.apply_to_config'
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
    """controller 视角的 db 代理：只替换 session.commit，其余（db.func 等）透传"""

    def __init__(self, real_db):
        self._real_db = real_db
        self.session = _NoCommitSession(real_db.session)

    def __getattr__(self, name):
        return getattr(self._real_db, name)


# ============================================================
# 测试数据构造 / 断言辅助
# ============================================================

def _make_group(name, algorithm_type='asr'):
    group = TestCaseGroup(id=str(uuid.uuid4()), name=name, algorithm_type=algorithm_type)
    db.session.add(group)
    db.session.flush()
    return group


def _make_case(name, group_id, deleted=False, audio_id=None):
    config = {}
    if audio_id is not None:
        config = {'rounds': [{'round_number': 1, 'audios': [{'audio_id': audio_id, 'spl': 65.0}]}]}
    tc = TestCase(
        id=str(uuid.uuid4()), name=name, group_id=group_id, config=config, test_type='api'
    )
    tc.deleted = deleted
    db.session.add(tc)
    db.session.flush()
    return tc


def _make_audio(name=AUDIO_NAME, md5=None):
    audio = Audio(
        name=name, file_path='/tmp/vega30.wav', size=1, duration=1.0, format='wav', md5=md5
    )
    db.session.add(audio)
    db.session.flush()
    return audio


def _duplicate_active_names(prefix):
    """返回 prefix 命名空间内、未删除用例中重名的用例名（空列表 = 无同名活跃用例）"""
    rows = (
        db.session.query(TestCase.name, func.count(TestCase.id))
        .filter(TestCase.deleted == False, TestCase.name.startswith(prefix, autoescape=True))  # noqa: E712
        .group_by(TestCase.name)
        .having(func.count(TestCase.id) > 1)
        .all()
    )
    return [name for name, _ in rows]


def _purge(case_ids=(), audio_id=None, task_ids=()):
    """兜底清理本测试创建的行。

    接口路径内部的 `db.session.commit()` 可能绕过 conftest 的外层事务回滚（conftest
    已注明的已知限制），故按**精确 ID** 清理，绝不触碰其它测试的数据。
    """
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


# ============================================================
# _resolve_unique_case_name：判重范围 + 同秒后缀循环
# ============================================================

class TestResolveUniqueCaseName:
    """用例名取唯一：判重限定目标分组（不改成分组无关），同秒冲突靠后缀递增"""

    def test_returns_base_name_when_no_conflict(self, app):
        """无同组同名活跃用例时原样返回基础名"""
        from backend.controllers.audio_controller import AudioController

        group = _make_group(GROUP_TAKEOVER)
        assert (
            AudioController._resolve_unique_case_name(BASE_CASE_NAME, group.id)
            == BASE_CASE_NAME
        )

    def test_same_group_conflict_gets_suffix(self, app):
        """同组同名：加后缀（原有行为不回归）"""
        from backend.controllers.audio_controller import AudioController

        group = _make_group(GROUP_TAKEOVER)
        _make_case(BASE_CASE_NAME, group.id)

        resolved = AudioController._resolve_unique_case_name(BASE_CASE_NAME, group.id)
        assert resolved != BASE_CASE_NAME
        assert resolved.startswith(f'{BASE_CASE_NAME}_')

    def test_cross_group_same_name_is_not_a_name_conflict(self, app):
        """跨组同名**不算**命名冲突：判重键保持 (name, group_id)，未实现"全局同名唯一"

        这是本卡口径的护栏测试——跨组同名是有意保留的产品能力
        （`_batch_copy_to_group` 逐字复制到目标分组），不得靠改去重键来消灭。
        """
        from backend.controllers.audio_controller import AudioController

        other_group = _make_group(GROUP_TAKEOVER)
        target_group = _make_group(GROUP_REJECT)
        _make_case(BASE_CASE_NAME, other_group.id)

        # 另一个分组里已有同名活跃用例，但目标分组内没有 → 不需要加后缀
        assert (
            AudioController._resolve_unique_case_name(BASE_CASE_NAME, target_group.id)
            == BASE_CASE_NAME
        )

    def test_two_uploads_in_same_second_get_distinct_names(self, app):
        """同一秒内两次同名上传：后缀递增，两行名字不同（旧实现只查一次会撞名）"""
        from backend.controllers.audio_controller import AudioController

        group = _make_group(GROUP_REJECT)
        # 已有一条同组同名活跃用例（更早的上传），两次上传落在同一秒
        _make_case(BASE_CASE_NAME, group.id)
        with patch(f'{CONTROLLER}.now_cst', return_value=FIXED_NOW):
            first = AudioController._resolve_unique_case_name(BASE_CASE_NAME, group.id)
            _make_case(first, group.id)
            second = AudioController._resolve_unique_case_name(BASE_CASE_NAME, group.id)
            _make_case(second, group.id)

        # 第一次仍沿用「_HHMMSS」后缀（与旧实现兼容），第二次递增序号
        assert first == f'{BASE_CASE_NAME}_143052'
        assert second == f'{BASE_CASE_NAME}_143052_2'
        assert first != second

    def test_soft_deleted_case_does_not_block_name(self, app):
        """软删行不参与判重：deleted=False 过滤语义保持不变"""
        from backend.controllers.audio_controller import AudioController

        group = _make_group(GROUP_TAKEOVER)
        _make_case(BASE_CASE_NAME, group.id, deleted=True)

        assert (
            AudioController._resolve_unique_case_name(BASE_CASE_NAME, group.id)
            == BASE_CASE_NAME
        )


# ============================================================
# _normalize_group_name：strip + 全半角归一
# ============================================================

class TestNormalizeGroupName:
    """分组名归一：避免「拒识」与「拒识 」建出两个分组"""

    @pytest.mark.parametrize(
        'raw, expected',
        [
            ('话轮接管', '话轮接管'),
            ('  话轮接管  ', '话轮接管'),
            ('　话轮接管　', '话轮接管'),  # 全角空格 U+3000
            ('拒识　', '拒识'),
            ('ＡＢＣ１２３', 'ABC123'),  # 全角字母数字
            ('话轮\t接管', '话轮 接管'),  # 制表符压成单空格
            ('', ''),
            (None, ''),
        ],
    )
    def test_normalize(self, app, raw, expected):
        from backend.controllers.audio_controller import AudioController

        assert AudioController._normalize_group_name(raw) == expected


# ============================================================
# 跨组音频身份判重
# ============================================================

class TestExtractAudioIdsFromConfig:
    """从 config.rounds[].audios[].audio_id 提取音频 ID"""

    def test_extracts_from_rounds(self, app):
        from backend.controllers.audio_controller import AudioController

        config = {
            'rounds': [
                {'round_number': 1, 'audios': [{'audio_id': 7}, {'audio_id': '8'}]},
                {'round_number': 2, 'audios': [{'audio_id': 9}]},
            ]
        }
        assert AudioController._extract_audio_ids_from_config(config) == {'7', '8', '9'}

    @pytest.mark.parametrize('config', [None, {}, {'rounds': []}, 'not-a-dict', {'rounds': [None]}])
    def test_tolerates_malformed_config(self, app, config):
        from backend.controllers.audio_controller import AudioController

        assert AudioController._extract_audio_ids_from_config(config) == set()


class TestFindActiveCaseInOtherGroup:
    """同一 audio_id 在其它分组的活跃用例查找"""

    def test_finds_case_in_other_group(self, app):
        from backend.controllers.audio_controller import AudioController

        audio = _make_audio()
        other_group = _make_group(GROUP_TAKEOVER)
        target_group = _make_group(GROUP_REJECT)
        case = _make_case(BASE_CASE_NAME, other_group.id, audio_id=audio.id)

        conflict = AudioController._find_active_case_in_other_group(audio.id, target_group.id)
        assert conflict == (GROUP_TAKEOVER, BASE_CASE_NAME, case.id)

    def test_ignores_case_in_target_group(self, app):
        """目标分组内的同名用例不算跨组冲突（同组去重另有后缀逻辑）"""
        from backend.controllers.audio_controller import AudioController

        audio = _make_audio()
        target_group = _make_group(GROUP_REJECT)
        _make_case(BASE_CASE_NAME, target_group.id, audio_id=audio.id)

        assert (
            AudioController._find_active_case_in_other_group(audio.id, target_group.id) is None
        )

    def test_ignores_soft_deleted_case(self, app):
        from backend.controllers.audio_controller import AudioController

        audio = _make_audio()
        other_group = _make_group(GROUP_TAKEOVER)
        target_group = _make_group(GROUP_REJECT)
        _make_case(BASE_CASE_NAME, other_group.id, deleted=True, audio_id=audio.id)

        assert (
            AudioController._find_active_case_in_other_group(audio.id, target_group.id) is None
        )

    def test_returns_none_for_unrelated_audio(self, app):
        """其它用例引用的是别的音频 → 不冲突"""
        from backend.controllers.audio_controller import AudioController

        audio = _make_audio()
        other_audio = _make_audio(name=f'other_{RUN_TAG}.wav')
        other_group = _make_group(GROUP_TAKEOVER)
        target_group = _make_group(GROUP_REJECT)
        _make_case(BASE_CASE_NAME, other_group.id, audio_id=other_audio.id)

        assert (
            AudioController._find_active_case_in_other_group(audio.id, target_group.id) is None
        )

    def test_none_group_id_excludes_nothing(self, app):
        """目标分组尚未创建（group_id=None）时不排除任何分组，仍能查出冲突"""
        from backend.controllers.audio_controller import AudioController

        audio = _make_audio()
        other_group = _make_group(GROUP_TAKEOVER)
        case = _make_case(BASE_CASE_NAME, other_group.id, audio_id=audio.id)

        conflict = AudioController._find_active_case_in_other_group(audio.id, None)
        assert conflict == (GROUP_TAKEOVER, BASE_CASE_NAME, case.id)


# ============================================================
# _create_test_case_from_audio：两种上传方式下的处置
# ============================================================

class TestCreateTestCaseFromAudioNaming:
    """同一音频在「带目录 / 不带目录」两种上传方式下的用例创建"""

    @staticmethod
    def _create(audio_id, group_name):
        """调 _create_test_case_from_audio（参考参数生成打桩，聚焦命名/去重逻辑）"""
        from backend.controllers.audio_controller import AudioController

        with patch(PATCH_REF_PARAMS):
            return AudioController._create_test_case_from_audio(
                audio_id, ['api'], [], group_name=group_name, algorithm_type='asr'
            )

    def test_cross_group_upload_modes_do_not_create_duplicate_name(self, app):
        """不带目录与带目录两种方式上传同一音频：第二次被拦，不新增跨组同名活跃用例

        本卡口径 = 隐式上传路径**拦截**（不新增跨组同名活跃用例）。
        """
        audio = _make_audio()
        # 不带目录：group_name=None → 默认分组「音频上传生成」
        first_ids = self._create(audio.id, None)
        # 带目录：group_name=目录名 → 目录名分组；同一音频已在别的分组有活跃用例 → 拦
        second_ids = self._create(audio.id, GROUP_TAKEOVER)
        db.session.flush()

        assert len(first_ids) == 1
        assert second_ids == []

        rows = TestCase.query.filter(TestCase.id.in_(first_ids)).all()
        assert len(rows) == 1
        assert _duplicate_active_names(BASE_CASE_NAME) == []
        # 被拦时不会凭空建出目标分组
        assert TestCaseGroup.query.filter_by(name=GROUP_TAKEOVER).first() is None

    def test_cross_group_block_logs_warning(self, app):
        """拦截不得静默：留 warning 日志，且点名冲突所在分组与用例"""
        audio = _make_audio(name=f'warn_{RUN_TAG}.wav')
        self._create(audio.id, GROUP_TAKEOVER)

        with patch(f'{CONTROLLER}.logger') as mock_logger:
            blocked = self._create(audio.id, None)

        assert blocked == []
        warnings = [str(call.args[0]) for call in mock_logger.warning.call_args_list]
        assert any(GROUP_TAKEOVER in msg for msg in warnings)

    def test_same_group_upload_twice_does_not_share_name(self, app):
        """同组重复上传（两次都落默认分组）：两行不同名"""
        audio = _make_audio()
        tc_ids = self._create(audio.id, None) + self._create(audio.id, None)
        db.session.flush()

        rows = TestCase.query.filter(TestCase.id.in_(tc_ids)).all()
        assert len(rows) == 2
        assert len({r.group_id for r in rows}) == 1
        assert len({r.name for r in rows}) == 2
        assert _duplicate_active_names(BASE_CASE_NAME) == []

    def test_group_name_is_normalized(self, app):
        """「话轮接管」与「　话轮接管　」归一到同一个分组"""
        first_audio = _make_audio(name=f'a1_{RUN_TAG}.wav')
        second_audio = _make_audio(name=f'a2_{RUN_TAG}.wav')
        tc_ids = self._create(first_audio.id, GROUP_TAKEOVER) + self._create(
            second_audio.id, f'　{GROUP_TAKEOVER}　'
        )
        db.session.flush()

        rows = TestCase.query.filter(TestCase.id.in_(tc_ids)).all()
        assert len(rows) == 2
        assert len({r.group_id for r in rows}) == 1

    def test_missing_group_name_logs_warning(self, app):
        """缺省落默认分组不得静默：至少留一条 warning 日志"""
        audio = _make_audio(name=f'a3_{RUN_TAG}.wav')

        with patch(f'{CONTROLLER}.logger') as mock_logger:
            self._create(audio.id, None)

        warnings = [str(call.args[0]) for call in mock_logger.warning.call_args_list]
        assert any(DEFAULT_GROUP in msg for msg in warnings)


# ============================================================
# 上传接口回归：秒传分支走真实 /api/v1/audios/upload/merge
# ============================================================

class TestUploadMergeEndpointRegression:
    """秒传建用例走真实接口：既有上传行为不被破坏，跨组重复给可见原因

    注：接口内部 `db.session.commit()` 会真正提交（穿透 conftest 的外层事务回滚，
    conftest 已注明的已知限制），把数据写进测试库。本类只验证命名/分组口径与接口
    返回，故用 `_NoCommitDB` 把 controller 的 commit 降级为 flush，使测试可重复
    运行、不污染共享测试库。
    """

    ENDPOINT = '/api/v1/audios/upload/merge'

    @staticmethod
    def _instant_upload(client, audio_md5, extra_payload, task_ids):
        """构造秒传场景（total_chunks=0 + status=completed + 同 md5 音频已入库）"""
        task = UploadTask(
            id=str(uuid.uuid4()), total_files=1, total_size=1, status='uploading'
        )
        db.session.add(task)
        task_ids.append(task.id)
        file_id = str(uuid.uuid4())
        db.session.add(
            UploadFile(
                id=file_id,
                task_id=task.id,
                filename=AUDIO_NAME,
                original_filename=AUDIO_NAME,
                relative_path='',
                size=1,
                md5=audio_md5,
                status='completed',
                uploaded_size=1,
                completed_chunks=0,
                total_chunks=0,
            )
        )
        db.session.flush()
        return client.post(
            TestUploadMergeEndpointRegression.ENDPOINT,
            json={
                'fileId': file_id,
                'taskId': task.id,
                'createTestCase': True,
                'algorithmType': 'asr',
                **extra_payload,
            },
        )

    def test_two_group_scopes_do_not_create_duplicate_name(self, client, app):
        """不带目录（root）与带目录（folder）两次上传：第二次不重复建用例并给出原因"""
        import backend.controllers.audio_controller as audio_controller

        audio = _make_audio(md5='a' * 32)
        task_ids = []
        tc_ids = []
        try:
            with patch.object(audio_controller, 'db', _NoCommitDB(db)), patch(PATCH_REF_PARAMS):
                root_resp = self._instant_upload(
                    client,
                    audio.md5,
                    {'groupNameType': 'root', 'customGroupName': ''},
                    task_ids,
                )
                folder_resp = self._instant_upload(
                    client,
                    audio.md5,
                    {'groupNameType': 'folder', 'customGroupName': GROUP_TAKEOVER},
                    task_ids,
                )

            assert root_resp.status_code == 200, root_resp.get_json()
            assert folder_resp.status_code == 200, folder_resp.get_json()
            root_data = root_resp.get_json()['data']
            folder_data = folder_resp.get_json()['data']
            assert root_data['instantUpload'] is True
            assert folder_data['instantUpload'] is True

            # 第一次建了用例；第二次因同一音频已在其它分组有活跃用例而跳过
            tc_ids = [root_data['testCaseId']] if root_data.get('testCaseId') else []
            assert tc_ids
            assert folder_data.get('testCaseId') is None
            reason = folder_data.get('testCaseSkippedReason')
            assert reason, folder_data
            # 可见原因要点名冲突所在分组（第一次那条用例落的分组）
            first_case = TestCase.query.filter_by(id=tc_ids[0]).first()
            conflict_group = TestCaseGroup.query.filter_by(id=first_case.group_id).first()
            assert conflict_group.name in reason
            assert _duplicate_active_names(BASE_CASE_NAME) == []
        finally:
            _purge(case_ids=tc_ids, audio_id=audio.id, task_ids=task_ids)

    def test_no_test_case_when_flag_off(self, client, app):
        """createTestCase=False 时不建用例（上传接口既有行为回归）"""
        import backend.controllers.audio_controller as audio_controller

        audio = _make_audio(name=f'no_tc_{RUN_TAG}.wav', md5='b' * 32)
        task_ids = []
        before = TestCase.query.count()
        try:
            with patch.object(audio_controller, 'db', _NoCommitDB(db)):
                resp = self._instant_upload(
                    client,
                    audio.md5,
                    {'createTestCase': False, 'groupNameType': 'root'},
                    task_ids,
                )

            assert resp.status_code == 200, resp.get_json()
            assert resp.get_json()['data']['instantUpload'] is True
            assert TestCase.query.count() == before
        finally:
            _purge(audio_id=audio.id, task_ids=task_ids)
