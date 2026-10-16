# -*- coding: utf-8 -*-
"""上传分组名来源与优先级测试（VEGA-38）

缺陷：前端「从文件夹导入」按分组下发的分组名（`testCaseConfig.groupName`）在
`merge_chunks` 里读得太晚——读到它时 `effective_group_name` 已经算完，只剩一个
没人再看的赋值（旧 `audio_controller.py:1186-1192`），于是前端下发的分组名被静默
丢弃，用例落到「算法类型」分组（实测落 `voice_llm`）。

本卡口径（见首条评论）：
- 分组名派生链的优先级（高→低）：
  **分组级配置 tc_config.group_name > 目录名/自定义名 custom_group_name（限
  groupNameType ∈ {custom, folder}）> 顶层 test_case_group_name > 算法类型 > 缺省
  分组「音频上传生成」**。
- `tc_config.group_name` 的读取必须发生在算 `effective_group_name` **之前**，
  旧代码里「读晚了」的死赋值一并删除。
- 无 `tc_config.group_name` 时，其余各级的优先级**与改动前完全一致**（回归护栏）。

本文件覆盖：
1. 真实前端请求形状（`groupNameType=""` + `customGroupName=目录名` +
   `testCaseConfig.group_name=目录名`）→ 落目录名分组（改动前落算法类型分组）
2. `tc_config.group_name` 独占时的提权；分组名归一（全半角/空白）
3. 两个分组各带自己的分组名 → 分别落两个不同分组（不得串组）
4. 无 `tc_config.group_name` 时的兜底链回归（custom / 顶层 / 算法类型 / 缺省）

测试用本进程专属测试库（VEGA-49：intelligent_audio_test_test_p<pid>）。接口内部
`db.session.commit()` 会穿透 conftest 的外层事务回滚（conftest 已注明的已知限制），
故用 `_NoCommitDB` 把 controller 的 commit 降级为 flush，并按精确 ID 兜底清理，
不在库里留残留。
用例名/分组名带本次运行的随机 tag，避免历史残留行干扰断言。
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

# 本次运行的唯一 tag：测试库中可能有历史提交残留，避免同名判重断言被污染
RUN_TAG = uuid.uuid4().hex[:8]
AUDIO_NAME = f'VEGA38_{RUN_TAG}_silence.wav'
ALGORITHM_TYPE = 'asr'
DEFAULT_GROUP = '音频上传生成'
CONTROLLER = 'backend.controllers.audio_controller'
PATCH_REF_PARAMS = (
    'backend.utils.algorithm.reference_params_generator.ReferenceParamsGenerator.apply_to_config'
)

# 目录名（FolderImportModal 的 folderGroupMappings 的**值**）
GROUP_FOLDER_A = f'VEGA38目录甲_{RUN_TAG}'
GROUP_FOLDER_B = f'VEGA38目录乙_{RUN_TAG}'
# 分组级配置下发的分组名
GROUP_TC_CONFIG = f'VEGA38分组级_{RUN_TAG}'
# 顶层字段下发的分组名（前端从不发，仅用于回归）
GROUP_TOPLEVEL = f'VEGA38顶层_{RUN_TAG}'


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

def _make_audio(name=AUDIO_NAME, md5=None):
    audio = Audio(
        name=name, file_path='/tmp/vega38.wav', size=1, duration=1.0, format='wav', md5=md5
    )
    db.session.add(audio)
    db.session.flush()
    return audio


def _purge(case_ids=(), audio_id=None, task_ids=()):
    """兜底清理本测试创建的行（按精确 ID，绝不触碰其它测试的数据）"""
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


def _group_name_of_case(case_id):
    """用例实际落库的分组名（test_case_groups.name）"""
    row = (
        db.session.query(TestCaseGroup.name)
        .join(TestCase, TestCase.group_id == TestCaseGroup.id)
        .filter(TestCase.id == case_id)
        .first()
    )
    return row[0] if row else None


class _UploadHarness:
    """秒传分支上传建用例：走真实 /api/v1/audios/upload/merge"""

    ENDPOINT = '/api/v1/audios/upload/merge'

    def __init__(self):
        self.task_ids = []
        self.case_ids = []
        self.audio_ids = []

    def upload(self, client, extra_payload, md5=None, expect_success=True):
        """构造秒传场景（total_chunks=0 + status=completed + 同 md5 音频已入库）

        :param expect_success: False 时不做 200 断言，原样返回响应对象（边界用例用）
        """
        md5 = md5 or uuid.uuid4().hex
        audio = _make_audio(name=f'{RUN_TAG}_{md5[:6]}.wav', md5=md5)
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
        with patch.object(audio_controller, 'db', _NoCommitDB(db)), patch(PATCH_REF_PARAMS):
            resp = client.post(self.ENDPOINT, json=payload)

        if not expect_success:
            return resp
        assert resp.status_code == 200, resp.get_json()
        data = resp.get_json()['data']
        assert data['instantUpload'] is True, data
        if data.get('testCaseId'):
            self.case_ids.append(data['testCaseId'])
        return data

    def cleanup(self):
        _purge(case_ids=self.case_ids, task_ids=self.task_ids)
        for audio_id in self.audio_ids:
            _purge(audio_id=audio_id)

    def group_of(self, data):
        """上传响应里那条用例落库的分组名"""
        assert data.get('testCaseId'), data
        return _group_name_of_case(data['testCaseId'])


# ============================================================
# 分组级配置 tc_config.group_name：提权与归一
# ============================================================

class TestTestCaseConfigGroupName:
    """前端按分组下发的分组名必须生效，且优先级最高"""

    def test_real_folder_import_payload_lands_in_folder_group(self, client, app):
        """真实前端请求形状 → 落目录名分组

        浏览器实测的 merge 请求体（VEGA-38 复现记录）：
            groupNameType: ""            ← UploadOptions 没有「用例分组」UI，取不到值
            customGroupName: "<目录名>"   ← audioImport.ts 按文件所在根目录映射
            testCaseConfig.group_name: "<目录名>"
        旧实现里 custom_group_name 被 `group_name_type in ('custom','folder')` 挡掉，
        testCaseConfig.group_name 又读晚了 → 落算法类型分组（voice_llm）。
        """
        harness = _UploadHarness()
        try:
            data = harness.upload(
                client,
                {
                    'groupNameType': '',
                    'customGroupName': GROUP_FOLDER_A,
                    'testCaseConfig': {'groupName': GROUP_FOLDER_A},
                },
            )
            assert harness.group_of(data) == GROUP_FOLDER_A
        finally:
            harness.cleanup()

    def test_tc_config_group_name_alone_wins(self, client, app):
        """只有 tc_config.group_name（其余分组名来源全空）→ 该分组名生效"""
        harness = _UploadHarness()
        try:
            data = harness.upload(
                client,
                {
                    'groupNameType': 'root',
                    'customGroupName': '',
                    'testCaseConfig': {'groupName': GROUP_TC_CONFIG},
                },
            )
            assert harness.group_of(data) == GROUP_TC_CONFIG
        finally:
            harness.cleanup()

    def test_tc_config_group_name_beats_custom_group_name(self, client, app):
        """优先级判定：分组级配置 > 目录名/自定义名（custom 闸门打开时同样如此）"""
        harness = _UploadHarness()
        try:
            data = harness.upload(
                client,
                {
                    'groupNameType': 'custom',
                    'customGroupName': GROUP_FOLDER_A,
                    'testCaseConfig': {'groupName': GROUP_TC_CONFIG},
                },
            )
            assert harness.group_of(data) == GROUP_TC_CONFIG
        finally:
            harness.cleanup()

    def test_tc_config_group_name_is_normalized(self, client, app):
        """分组级分组名同样走 strip + 全半角归一，不另建一个「　X　」分组"""
        harness = _UploadHarness()
        try:
            data = harness.upload(
                client,
                {
                    'groupNameType': 'root',
                    'customGroupName': '',
                    'testCaseConfig': {'groupName': f'　{GROUP_TC_CONFIG}　'},
                },
            )
            assert harness.group_of(data) == GROUP_TC_CONFIG
        finally:
            harness.cleanup()

    def test_snake_case_and_camel_case_are_equivalent(self, client, app):
        """tc_config 的分组名两种写法等价（真实浏览器发的是 snake_case group_name）"""
        harness = _UploadHarness()
        try:
            snake = harness.upload(
                client,
                {
                    'groupNameType': 'root',
                    'customGroupName': '',
                    'test_case_config': {'group_name': GROUP_TC_CONFIG},
                },
            )
            camel = harness.upload(
                client,
                {
                    'groupNameType': 'root',
                    'customGroupName': '',
                    'testCaseConfig': {'groupName': GROUP_TC_CONFIG},
                },
            )
            assert harness.group_of(snake) == GROUP_TC_CONFIG
            assert harness.group_of(camel) == GROUP_TC_CONFIG
        finally:
            harness.cleanup()

    def test_two_groups_land_separately(self, client, app):
        """两个分组各带自己的分组名 → 各自落对应分组，不串组

        前端 audioImport.ts:1298-1314 每个分组各构造一份 testCaseConfig；
        旧代码对**所有**分组都取 `Object.values(folderGroupMappings)[0]`（第一个
        根目录的分组名），配合后端提权后必须保证「分组名跟着分组走」。
        """
        harness = _UploadHarness()
        try:
            first = harness.upload(
                client,
                {
                    'groupNameType': '',
                    'customGroupName': GROUP_FOLDER_A,
                    'testCaseConfig': {'groupName': GROUP_FOLDER_A},
                },
                md5='1' * 32,
            )
            second = harness.upload(
                client,
                {
                    'groupNameType': '',
                    'customGroupName': GROUP_FOLDER_B,
                    'testCaseConfig': {'groupName': GROUP_FOLDER_B},
                },
                md5='2' * 32,
            )
            first_group = harness.group_of(first)
            second_group = harness.group_of(second)
            assert first_group == GROUP_FOLDER_A
            assert second_group == GROUP_FOLDER_B
            assert first_group != second_group
        finally:
            harness.cleanup()


# ============================================================
# 回归：无 tc_config.group_name 时的兜底链与改动前一致
# ============================================================

class TestGroupNameFallbackChain:
    """tc_config.group_name 缺位时，custom / 顶层 / 算法类型 / 缺省 的优先级不变"""

    def test_custom_group_name_with_custom_type(self, client, app):
        """groupNameType=custom + customGroupName → 自定义分组名（原有行为）"""
        harness = _UploadHarness()
        try:
            data = harness.upload(
                client,
                {'groupNameType': 'custom', 'customGroupName': GROUP_FOLDER_A},
            )
            assert harness.group_of(data) == GROUP_FOLDER_A
        finally:
            harness.cleanup()

    def test_folder_group_name_with_folder_type(self, client, app):
        """groupNameType=folder + customGroupName → 目录名分组（原有行为）"""
        harness = _UploadHarness()
        try:
            data = harness.upload(
                client,
                {'groupNameType': 'folder', 'customGroupName': GROUP_FOLDER_B},
            )
            assert harness.group_of(data) == GROUP_FOLDER_B
        finally:
            harness.cleanup()

    def test_custom_group_name_ignored_for_root_type(self, client, app):
        """groupNameType=root → custom_group_name 不参与，落算法类型分组（闸门不变）"""
        harness = _UploadHarness()
        try:
            data = harness.upload(
                client,
                {'groupNameType': 'root', 'customGroupName': GROUP_FOLDER_A},
            )
            assert harness.group_of(data) == ALGORITHM_TYPE
        finally:
            harness.cleanup()

    def test_toplevel_test_case_group_name(self, client, app):
        """顶层 testCaseGroupName 独占 → 该分组名生效（原有行为）"""
        harness = _UploadHarness()
        try:
            data = harness.upload(
                client,
                {
                    'groupNameType': 'root',
                    'customGroupName': '',
                    'testCaseGroupName': GROUP_TOPLEVEL,
                },
            )
            assert harness.group_of(data) == GROUP_TOPLEVEL
        finally:
            harness.cleanup()

    def test_tc_config_without_group_name_falls_back(self, client, app):
        """tc_config 存在但 group_name 为空 → 兜底链照常（顶层 > 算法类型）"""
        harness = _UploadHarness()
        try:
            data = harness.upload(
                client,
                {
                    'groupNameType': 'root',
                    'customGroupName': '',
                    'testCaseGroupName': GROUP_TOPLEVEL,
                    'testCaseConfig': {'groupName': None, 'inheritTags': True},
                },
            )
            assert harness.group_of(data) == GROUP_TOPLEVEL
        finally:
            harness.cleanup()

    def test_algorithm_type_when_nothing_else(self, client, app):
        """全部为空 → 算法类型分组（原有行为）"""
        harness = _UploadHarness()
        try:
            data = harness.upload(
                client,
                {'groupNameType': 'root', 'customGroupName': ''},
            )
            assert harness.group_of(data) == ALGORITHM_TYPE
        finally:
            harness.cleanup()


# ============================================================
# 边界：分组名长度（审计 P1）
# ============================================================

# 与 TestCaseGroup.name 的 String(100) 对齐
GROUP_NAME_MAX_LENGTH = 100
# 超长分组名对应的请求体片段：DB 截断报错里会带上原始 SQL 与参数
SQL_LEAK_MARKERS = (
    'psycopg2',
    'StringDataRightTruncation',
    'INSERT INTO',
    'UPDATE ',
    'test_case_groups',
)


def _padded_name(total_length):
    """构成长度恰为 total_length 的分组名（带本次运行 tag，避免撞历史残留）"""
    prefix = f'VEGA38LEN_{RUN_TAG}_'
    assert total_length >= len(prefix)
    return prefix + 'G' * (total_length - len(prefix))


class TestGroupNameLengthBoundary:
    """分组名超出列长上限时必须给明确业务错误，而不是 DB 截断错裸奔

    审计 P1：修复后 `effective_group_name` 可能是**用户目录名**
    （前端 `folderGroupMappings` 默认取目录名本身，长度不受前端约束），
    101 字符时原实现直接走到 `TestCaseGroup(name=...)` 抛
    `StringDataRightTruncation`，被 `merge_chunks` 的兜底 except 转成 400 并把
    原始 SQL 与参数（含分组名）回传客户端。

    修法是**在派生处拒绝**（不截断——截断会让落库分组名与用户目录名不一致，
    正是 VEGA-38 要修的那类问题，且两个长目录名可能被截成同名而并组）。
    """

    def test_group_name_at_limit_is_accepted(self, client, app):
        """恰好 100 字符（列长上限）必须放行并落库"""
        name = _padded_name(GROUP_NAME_MAX_LENGTH)
        assert len(name) == GROUP_NAME_MAX_LENGTH
        harness = _UploadHarness()
        try:
            data = harness.upload(
                client,
                {
                    'groupNameType': 'root',
                    'customGroupName': '',
                    'testCaseConfig': {'groupName': name},
                },
            )
            assert harness.group_of(data) == name
        finally:
            harness.cleanup()

    def test_group_name_over_limit_rejected_with_business_error(self, client, app):
        """101 字符（超 1）→ 明确业务错误，且不产生任何落库分组"""
        name = _padded_name(GROUP_NAME_MAX_LENGTH + 1)
        harness = _UploadHarness()
        try:
            resp = harness.upload(
                client,
                {
                    'groupNameType': 'root',
                    'customGroupName': '',
                    'testCaseConfig': {'groupName': name},
                },
                expect_success=False,
            )
            assert resp.status_code == 400, resp.get_json()
            body = resp.get_json()
            assert body['code'] == 100, body          # ErrorCode.INVALID_PARAMS
            assert body['success'] is False, body
            assert '分组名过长' in body['message'], body
            assert str(GROUP_NAME_MAX_LENGTH) in body['message'], body
            # 被拦在建组之前：该分组名没有落库
            assert not TestCaseGroup.query.filter_by(name=name).first()
        finally:
            harness.cleanup()

    def test_overlong_group_name_does_not_leak_sql(self, client, app):
        """超长被拦时响应体不得带原始 SQL / 驱动报错（审计 P1 的信息泄露面）"""
        name = _padded_name(GROUP_NAME_MAX_LENGTH + 50)
        harness = _UploadHarness()
        try:
            resp = harness.upload(
                client,
                {
                    'groupNameType': 'root',
                    'customGroupName': '',
                    'testCaseConfig': {'groupName': name},
                },
                expect_success=False,
            )
            assert resp.status_code == 400, resp.get_json()
            raw = resp.get_data(as_text=True)
            for marker in SQL_LEAK_MARKERS:
                assert marker not in raw, f'响应体泄露了 {marker!r}: {raw}'
        finally:
            harness.cleanup()

    def test_overlong_custom_group_name_also_rejected(self, client, app):
        """超长守卫覆盖全部来源：custom/folder 闸门打开的 customGroupName 同样被拦

        （与分组级配置无关的独立来源；只守 tc_config 一条会留同一个洞）
        """
        name = _padded_name(GROUP_NAME_MAX_LENGTH + 1)
        harness = _UploadHarness()
        try:
            resp = harness.upload(
                client,
                {'groupNameType': 'custom', 'customGroupName': name},
                expect_success=False,
            )
            assert resp.status_code == 400, resp.get_json()
            assert '分组名过长' in resp.get_json()['message']
            assert not TestCaseGroup.query.filter_by(name=name).first()
        finally:
            harness.cleanup()

    def test_overlong_group_name_without_create_test_case_still_uploads(self, client, app):
        """不建用例时分组名用不上 → 超长目录名不得把音频上传本身也拦掉"""
        name = _padded_name(GROUP_NAME_MAX_LENGTH + 1)
        harness = _UploadHarness()
        try:
            resp = harness.upload(
                client,
                {
                    'groupNameType': 'root',
                    'customGroupName': '',
                    'testCaseConfig': {'groupName': name},
                    'createTestCase': False,
                },
                expect_success=False,
            )
            # createTestCase 在 extra_payload 之后展开，覆盖掉 upload() 里的默认 True
            assert resp.status_code == 200, resp.get_json()
            assert not resp.get_json()['data'].get('testCaseId')
        finally:
            harness.cleanup()
