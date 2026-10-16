# -*- coding: utf-8 -*-
"""秒传兜底强填致用例名与音频互相矛盾 —— 修复回归（VEGA-31）

缺陷（VEGA-27 只读排查 + 独立复核确认）：
`audio_controller.merge_chunks` 的秒传分支里，按 name/original_filename/md5 都匹配不上时，
旧实现「只有一个未匹配项就直接填 existing_audio.id」——秒传命中已有音频靠的是 **md5**，
与文件名无关，于是建出「用例名取自前端 audio_name（JS135）/ description 与
config.rounds[].audios[].audio_id 指向另一条音频（JS121）」的矛盾用例，且全程无提示。

本卡口径（代码侧修复，不处置存量错配行）：
1. 秒传建用例前，按名称一个都对不上 → **拒绝建用例**并给出可操作提示（不再强填）。
   选「拒绝」而非「按真实文件名另建 audios 行」：后者会绕过 md5 去重留下同 md5 两行，
   后续 `Audio.query.filter_by(md5=...).first()` 命中哪条不确定。
   判定是**逐项**的：按名匹配完仍没有 audio_id 的项一律拒绝，不看「全 rounds 一个都
   没匹配上」这个全局计数（后者在错配项不是唯一未匹配项时会漏，见 TestPerItemJudgment）。
2. 前端已回填的 audio_id 也要与该项 audio_name 一致（多文件分组里前一个秒传文件会把
   md5 命中的 audio_id 回填进 rounds）→ 不一致同样拒绝，不静默错配。
3. 回归：md5 已存在且名称匹配（含「音频在库里改过名、原始文件名仍对得上」）的秒传
   路径必须照常建用例，且用例名 / description / audio_id 三者指向同一条音频。

测试用独立测试库 intelligent_audio_test_test，由 conftest 的外层事务回滚隔离；
接口内部 `db.session.commit()` 会穿透该回滚（conftest 已注明的已知限制），
故用 `_NoCommitDB` 把 controller 的 commit 降级为 flush，并按精确 ID 兜底清理。
"""
import uuid
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
# 存量音频（md5 命中的那一条，模拟 JS121）
EXISTING_NAME = f'JS121_{RUN_TAG}_response_2.wav'
# 本次上传的文件名（模拟 JS135），md5 与存量音频相同但名字不同
UPLOADED_NAME = f'JS135_{RUN_TAG}.wav'
# 另一条无关音频（模拟链式错配里被误指的音频）
OTHER_NAME = f'JS110_{RUN_TAG}_response_1.wav'
GROUP_NAME = f'秒传错配回归_{RUN_TAG}'
CONTROLLER = 'backend.controllers.audio_controller'
ENDPOINT = '/api/v1/audios/upload/merge'
PATCH_REF_PARAMS = (
    'backend.utils.algorithm.reference_params_generator.ReferenceParamsGenerator.apply_to_config'
)


def _md5(seed):
    """32 位十六进制 md5 占位（唯一，避免与测试库历史行撞车）"""
    return (seed * 32)[:32]


MD5_EXISTING = _md5(f'a{RUN_TAG}')
MD5_OTHER = _md5(f'b{RUN_TAG}')


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

def _make_audio(name, md5, original_filename=None):
    audio = Audio(
        name=name,
        original_filename=original_filename if original_filename is not None else name,
        file_path=f'/tmp/vega31_{uuid.uuid4().hex}.wav',
        size=1608734,
        duration=1.0,
        format='wav',
        md5=md5,
    )
    db.session.add(audio)
    db.session.flush()
    return audio


def _make_upload_file(md5, filename=UPLOADED_NAME):
    """秒传文件记录：total_chunks=0 + status=completed（register 阶段按 md5 命中即秒传）"""
    task = UploadTask(id=str(uuid.uuid4()), total_files=1, total_size=1, status='uploading')
    db.session.add(task)
    file_id = str(uuid.uuid4())
    db.session.add(
        UploadFile(
            id=file_id,
            task_id=task.id,
            filename=filename,
            original_filename=filename,
            relative_path='',
            size=1608734,
            md5=md5,
            status='completed',
            uploaded_size=1608734,
            completed_chunks=0,
            total_chunks=0,
        )
    )
    db.session.flush()
    return task.id, file_id


def _purge(case_ids=(), audio_ids=(), task_ids=()):
    """兜底清理本测试创建的行（按精确 ID / 本次运行唯一分组名，绝不触碰其它测试数据）

    修复前跑本文件时，被断言「不该建」的用例其实会被建出来（这正是缺陷本身），
    因此除显式 case_ids 外，还要清掉本次运行唯一分组（GROUP_NAME 带 RUN_TAG）下的
    全部用例——否则残留行会指向已被删掉的 audio_id，而 ID 序列复用后会让后续测试
    误判为「该音频已在其它分组有用例」。
    """
    case_ids = {cid for cid in case_ids if cid}
    group = TestCaseGroup.query.filter_by(name=GROUP_NAME).first()
    if group:
        case_ids |= {
            cid for (cid,) in db.session.query(TestCase.id).filter(TestCase.group_id == group.id).all()
        }
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
    if audio_ids:
        db.session.query(Audio).filter(Audio.id.in_(list(audio_ids))).delete(
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


def _merge_payload(file_id, task_id, rounds, create_test_case=True):
    return {
        'fileId': file_id,
        'taskId': task_id,
        'createTestCase': create_test_case,
        'algorithmType': 'asr',
        'testTypes': ['api'],
        'groupNameType': 'custom',
        'customGroupName': GROUP_NAME,
        'testCaseConfig': {'rounds': rounds},
    }


def _cases_in_group():
    group = TestCaseGroup.query.filter_by(name=GROUP_NAME, deleted=False).first()
    if not group:
        return []
    return TestCase.query.filter_by(group_id=group.id, deleted=False).all()


# ============================================================
# 1. 秒传 + 名称不匹配 → 拒绝建用例（本卡核心验收）
# ============================================================

class TestInstantUploadNameMismatch:
    """md5 命中已有音频但文件名对不上：不得建出名称与音频互相矛盾的用例"""

    def test_mismatched_name_is_rejected_without_case(self, client, app):
        """JS135↔JS121 复现链：拒绝建用例 + 可操作提示 + 库里不留矛盾行"""
        import backend.controllers.audio_controller as audio_controller

        existing = _make_audio(EXISTING_NAME, MD5_EXISTING)
        task_id, file_id = _make_upload_file(MD5_EXISTING, filename=UPLOADED_NAME)
        before_count = TestCase.query.count()
        case_ids = []
        try:
            with patch.object(audio_controller, 'db', _NoCommitDB(db)), patch(PATCH_REF_PARAMS):
                resp = client.post(
                    ENDPOINT,
                    json=_merge_payload(
                        file_id,
                        task_id,
                        [{'roundNumber': 1, 'audios': [{'audioName': UPLOADED_NAME, 'playOrder': 0}]}],
                    ),
                )

            # 拒绝 = 明确报错（前端把 message 显示在该文件的失败原因上）
            assert resp.status_code == 400, resp.get_json()
            body = resp.get_json()
            assert body['code'] != 0
            message = body['message']
            # 提示必须同时点名「上传的文件」与「命中的已有音频」，并给出可操作指引
            assert UPLOADED_NAME in message
            assert EXISTING_NAME in message
            assert '重命名' in message

            # 不再生成任何用例（旧实现会建出 测试用例_JS135… 且 audio_id 指向 JS121）
            assert TestCase.query.count() == before_count
            assert _cases_in_group() == []
        finally:
            _purge(case_ids=case_ids, audio_ids=[existing.id], task_ids=[task_id])

    def test_mismatched_name_logs_warning(self, client, app):
        """拒绝不得静默：留 warning 日志，点名上传文件名与命中的已有音频"""
        import backend.controllers.audio_controller as audio_controller

        existing = _make_audio(EXISTING_NAME, MD5_EXISTING)
        task_id, file_id = _make_upload_file(MD5_EXISTING, filename=UPLOADED_NAME)
        try:
            with patch.object(audio_controller, 'db', _NoCommitDB(db)), \
                 patch(PATCH_REF_PARAMS), \
                 patch(f'{CONTROLLER}.logger') as mock_logger:
                client.post(
                    ENDPOINT,
                    json=_merge_payload(
                        file_id,
                        task_id,
                        [{'roundNumber': 1, 'audios': [{'audioName': UPLOADED_NAME, 'playOrder': 0}]}],
                    ),
                )

            warnings = [str(call.args[0]) for call in mock_logger.warning.call_args_list]
            assert any(UPLOADED_NAME in msg and EXISTING_NAME in msg for msg in warnings), warnings
        finally:
            _purge(audio_ids=[existing.id], task_ids=[task_id])

    def test_prefilled_audio_id_with_wrong_name_is_rejected(self, client, app):
        """前端已回填的 audio_id 与该项 audio_name 对不上 → 同样拒绝（链式错配）"""
        import backend.controllers.audio_controller as audio_controller

        # 存量音频 A：本次上传文件 md5 命中它
        existing = _make_audio(EXISTING_NAME, MD5_EXISTING)
        # 另一条无关音频 B：被前端错填给了「JS135」那一项
        other = _make_audio(OTHER_NAME, MD5_OTHER)
        task_id, file_id = _make_upload_file(MD5_EXISTING, filename=EXISTING_NAME)
        before_count = TestCase.query.count()
        try:
            with patch.object(audio_controller, 'db', _NoCommitDB(db)), patch(PATCH_REF_PARAMS):
                resp = client.post(
                    ENDPOINT,
                    json=_merge_payload(
                        file_id,
                        task_id,
                        [
                            {
                                'roundNumber': 1,
                                'audios': [
                                    # 前一个秒传文件回填进来的错配项：名字是 JS135，id 指向 B
                                    {'audioName': UPLOADED_NAME, 'audioId': other.id, 'playOrder': 0},
                                    # 本次上传文件自己的项：名字与命中音频一致
                                    {'audioName': EXISTING_NAME, 'playOrder': 1},
                                ],
                            }
                        ],
                    ),
                )

            assert resp.status_code == 400, resp.get_json()
            message = resp.get_json()['message']
            assert UPLOADED_NAME in message
            assert OTHER_NAME in message
            assert TestCase.query.count() == before_count
            assert _cases_in_group() == []
        finally:
            _purge(audio_ids=[existing.id, other.id], task_ids=[task_id])


# ============================================================
# 2. 回归：名称匹配的秒传路径照常建用例（不得把正常路径一起堵死）
# ============================================================

class TestInstantUploadNameMatchRegression:
    """md5 已存在且名称匹配：秒传建用例照常，且用例名 / description / audio_id 三者一致"""

    def test_matching_name_creates_consistent_case(self, client, app):
        """文件名与已有音频一致（同一文件重传）→ 正常建用例，三者指向同一条音频"""
        import backend.controllers.audio_controller as audio_controller

        existing = _make_audio(EXISTING_NAME, MD5_EXISTING)
        task_id, file_id = _make_upload_file(MD5_EXISTING, filename=EXISTING_NAME)
        case_ids = []
        try:
            with patch.object(audio_controller, 'db', _NoCommitDB(db)), patch(PATCH_REF_PARAMS):
                resp = client.post(
                    ENDPOINT,
                    json=_merge_payload(
                        file_id,
                        task_id,
                        [{'roundNumber': 1, 'audios': [{'audioName': EXISTING_NAME, 'playOrder': 0}]}],
                    ),
                )

            assert resp.status_code == 200, resp.get_json()
            data = resp.get_json()['data']
            assert data['instantUpload'] is True
            assert data['audioId'] == existing.id
            assert data['testCaseId'], data
            case_ids = [data['testCaseId']]

            case = TestCase.query.filter_by(id=data['testCaseId']).first()
            assert case is not None
            # 用例名取自前端 audio_name（= 文件名），与音频一致
            assert case.name == f'测试用例_{EXISTING_NAME}'
            # description 与 config 里的 audio_id 也指向同一条音频 → 三者一致
            assert EXISTING_NAME in (case.description or '')
            assert case.config['rounds'][0]['audios'][0]['audio_id'] == existing.id
        finally:
            _purge(case_ids=case_ids, audio_ids=[existing.id], task_ids=[task_id])

    def test_renamed_audio_matches_by_original_filename(self, client, app):
        """音频在库里改过名，但原始文件名与上传文件名一致 → 仍按秒传正常建用例

        这是既有匹配能力（name / original_filename / md5 三键），收紧兜底不得把它一起堵死。
        """
        import backend.controllers.audio_controller as audio_controller

        renamed = f'JS121_{RUN_TAG}_renamed.wav'
        existing = _make_audio(renamed, MD5_EXISTING, original_filename=UPLOADED_NAME)
        task_id, file_id = _make_upload_file(MD5_EXISTING, filename=UPLOADED_NAME)
        case_ids = []
        try:
            with patch.object(audio_controller, 'db', _NoCommitDB(db)), patch(PATCH_REF_PARAMS):
                resp = client.post(
                    ENDPOINT,
                    json=_merge_payload(
                        file_id,
                        task_id,
                        [{'roundNumber': 1, 'audios': [{'audioName': UPLOADED_NAME, 'playOrder': 0}]}],
                    ),
                )

            assert resp.status_code == 200, resp.get_json()
            data = resp.get_json()['data']
            assert data['instantUpload'] is True
            assert data['audioId'] == existing.id
            assert data['testCaseId'], data
            case_ids = [data['testCaseId']]

            case = TestCase.query.filter_by(id=data['testCaseId']).first()
            assert case.name == f'测试用例_{UPLOADED_NAME}'
            assert case.config['rounds'][0]['audios'][0]['audio_id'] == existing.id
        finally:
            _purge(case_ids=case_ids, audio_ids=[existing.id], task_ids=[task_id])

    def test_no_case_when_flag_off(self, client, app):
        """createTestCase=False 的秒传（分组内非最后一个文件）不受影响：只回音频信息"""
        import backend.controllers.audio_controller as audio_controller

        existing = _make_audio(EXISTING_NAME, MD5_EXISTING)
        task_id, file_id = _make_upload_file(MD5_EXISTING, filename=UPLOADED_NAME)
        before_count = TestCase.query.count()
        try:
            with patch.object(audio_controller, 'db', _NoCommitDB(db)), patch(PATCH_REF_PARAMS):
                resp = client.post(
                    ENDPOINT,
                    json=_merge_payload(
                        file_id,
                        task_id,
                        [{'roundNumber': 1, 'audios': [{'audioName': UPLOADED_NAME, 'playOrder': 0}]}],
                        create_test_case=False,
                    ),
                )

            assert resp.status_code == 200, resp.get_json()
            assert resp.get_json()['data']['instantUpload'] is True
            assert TestCase.query.count() == before_count
        finally:
            _purge(audio_ids=[existing.id], task_ids=[task_id])


# ============================================================
# 3. 一致性自检helper（单测）
# ============================================================

class TestFindRoundAudioNameMismatch:
    """`_find_round_audio_name_mismatch`：audio_name 与所指向音频对不上的自检"""

    def test_returns_none_when_consistent(self, app):
        from backend.controllers.audio_controller import AudioController

        audio = _make_audio(EXISTING_NAME, MD5_EXISTING)
        rounds = [{'round_number': 1, 'audios': [{'audio_name': EXISTING_NAME, 'audio_id': audio.id}]}]
        assert AudioController._find_round_audio_name_mismatch(rounds) is None

    def test_accepts_original_filename_and_md5_keys(self, app):
        from backend.controllers.audio_controller import AudioController

        audio = _make_audio(EXISTING_NAME, MD5_EXISTING, original_filename=UPLOADED_NAME)
        rounds = [
            {'round_number': 1, 'audios': [{'audio_name': UPLOADED_NAME, 'audio_id': audio.id}]},
            {'round_number': 2, 'audios': [{'audio_name': MD5_EXISTING, 'audio_id': audio.id}]},
        ]
        assert AudioController._find_round_audio_name_mismatch(rounds) is None

    def test_reports_first_mismatch(self, app):
        from backend.controllers.audio_controller import AudioController

        audio = _make_audio(EXISTING_NAME, MD5_EXISTING)
        rounds = [
            {'round_number': 1, 'audios': [{'audio_name': EXISTING_NAME, 'audio_id': audio.id}]},
            {'round_number': 2, 'audios': [{'audio_name': UPLOADED_NAME, 'audio_id': audio.id}]},
        ]
        assert AudioController._find_round_audio_name_mismatch(rounds) == (
            UPLOADED_NAME,
            audio.id,
            EXISTING_NAME,
        )

    def test_ignores_items_without_id_or_name(self, app):
        from backend.controllers.audio_controller import AudioController

        audio = _make_audio(EXISTING_NAME, MD5_EXISTING)
        rounds = [
            {'round_number': 1, 'audios': [
                {'audio_name': UPLOADED_NAME},          # 未定 id：交由既有流程解析
                {'audio_id': audio.id},                 # 无 name：不判矛盾
                {'audio_name': UPLOADED_NAME, 'audio_id': 'not-a-number'},
            ]},
        ]
        assert AudioController._find_round_audio_name_mismatch(rounds) is None

    def test_ignores_missing_audio_row(self, app):
        """指向不存在的音频不算「名称矛盾」（不在本卡拦截面内）"""
        from backend.controllers.audio_controller import AudioController

        rounds = [{'round_number': 1, 'audios': [{'audio_name': UPLOADED_NAME, 'audio_id': 99999999}]}]
        assert AudioController._find_round_audio_name_mismatch(rounds) is None

    @pytest.mark.parametrize('rounds', [None, [], 'not-a-list', [None], [{'audios': None}]])
    def test_tolerates_malformed_config(self, app, rounds):
        from backend.controllers.audio_controller import AudioController

        assert AudioController._find_round_audio_name_mismatch(rounds) is None


# ============================================================
# 4. 逐项判定：错配项不在「唯一未匹配位置」时同样必须拒绝（第 2 轮补充）
# ============================================================

# 独立命名：本文件其它测试都不用它做 audio.name / original_filename / md5，
# 因此「按名匹配」不可能被别处残留行命中，判定结果与测试执行顺序无关。
MISMATCH_NAME = f'JS135_{RUN_TAG}_second.wav'


class TestPerItemJudgment:
    """自检必须是**逐项**的：不能只看「全 rounds 一个都没匹配上」这个全局计数

    原判定 `matched_count == 0 and unmatched_items`（全局）会漏掉这类构造：同分组别的项
    名字恰好对得上命中音频（或没带 audio_name 被「空名」规则填上）时 matched_count ≥ 1，
    错配项不再被拦，随后被 `_create_test_case_from_audio` 的兜底强填成命中音频，
    建出与缺陷「现象」逐字相同的用例（用例名 JS135 / description 与 audio_id 都是 JS121）。
    """

    @pytest.mark.parametrize(
        'label,rounds',
        [
            (
                'A-错配项在第二轮',
                [
                    {'roundNumber': 1, 'audios': [{'audioName': EXISTING_NAME, 'playOrder': 0}]},
                    {'roundNumber': 2, 'audios': [{'audioName': MISMATCH_NAME, 'playOrder': 0}]},
                ],
            ),
            (
                'C-首项无audio_name',
                [
                    {'roundNumber': 1, 'audios': [{'playOrder': 0}]},
                    {'roundNumber': 2, 'audios': [{'audioName': MISMATCH_NAME, 'playOrder': 0}]},
                ],
            ),
            (
                'D-同轮第二项错配',
                [
                    {
                        'roundNumber': 1,
                        'audios': [
                            {'audioName': EXISTING_NAME, 'playOrder': 0},
                            {'audioName': MISMATCH_NAME, 'playOrder': 1},
                        ],
                    }
                ],
            ),
        ],
    )
    def test_mismatch_item_not_in_first_position_is_rejected(self, client, app, label, rounds):
        """本次秒传文件名为 MISMATCH_NAME（md5 命中 EXISTING_NAME 那条音频）→ 拒绝建用例"""
        import backend.controllers.audio_controller as audio_controller

        existing = _make_audio(EXISTING_NAME, MD5_EXISTING)
        task_id, file_id = _make_upload_file(MD5_EXISTING, filename=MISMATCH_NAME)
        before_count = TestCase.query.count()
        try:
            with patch.object(audio_controller, 'db', _NoCommitDB(db)), patch(PATCH_REF_PARAMS):
                resp = client.post(
                    ENDPOINT,
                    json=_merge_payload(file_id, task_id, rounds),
                )

            body = resp.get_json()
            assert resp.status_code == 400, f'[{label}] 期望拒绝建用例，实际 {resp.status_code} {body}'
            assert body['code'] != 0, body
            # 提示点名对不上的项与命中的已有音频，且给出可操作指引
            assert MISMATCH_NAME in body['message'], body
            assert EXISTING_NAME in body['message'], body
            assert '重命名' in body['message'], body

            # 不建用例、不留矛盾行（无部分写入）
            assert TestCase.query.count() == before_count, _cases_in_group()
            assert _cases_in_group() == []
        finally:
            _purge(audio_ids=[existing.id], task_ids=[task_id])

    def test_sole_unmatched_item_still_rejected(self, client, app):
        """对照：唯一未匹配项（单文件场景）与逐项判定结果一致，仍拒绝"""
        import backend.controllers.audio_controller as audio_controller

        existing = _make_audio(EXISTING_NAME, MD5_EXISTING)
        task_id, file_id = _make_upload_file(MD5_EXISTING, filename=MISMATCH_NAME)
        before_count = TestCase.query.count()
        try:
            with patch.object(audio_controller, 'db', _NoCommitDB(db)), patch(PATCH_REF_PARAMS):
                resp = client.post(
                    ENDPOINT,
                    json=_merge_payload(
                        file_id,
                        task_id,
                        [{'roundNumber': 1, 'audios': [{'audioName': MISMATCH_NAME, 'playOrder': 0}]}],
                    ),
                )

            assert resp.status_code == 400, resp.get_json()
            assert TestCase.query.count() == before_count
            assert _cases_in_group() == []
        finally:
            _purge(audio_ids=[existing.id], task_ids=[task_id])

