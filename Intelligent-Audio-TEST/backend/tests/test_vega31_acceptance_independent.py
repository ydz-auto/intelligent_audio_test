# -*- coding: utf-8 -*-
"""VEGA-31 独立验收（测试工程师）——秒传兜底强填致用例名与音频互相矛盾

与开发自测（test_audio_instant_upload_name_mismatch.py）**刻意保持独立**：

1. 断言不依赖开发新增的 `_find_round_audio_name_mismatch` helper，改判**领域不变量**：
   「用例名里的编号」==「config 里 audio_id 所指音频名里的编号」==「description 里的编号」。
   缺陷的原始现象（JS135 用例名 / description 与 audio_id 指向 JS121）正是该不变量被打破。
2. 额外覆盖开发自测未覆盖的边界：无 rounds_config、audio_name 为空、拒绝路径无部分写入、
   存量音频已软删时不误拦。
3. 反证：本文件在修复前代码（5671ab04^）上同样应大面积失败——证明断言确实在测新逻辑。

隔离方式与开发自测一致：conftest 的独立测试库 + 外层事务回滚；controller 内部
`db.session.commit()` 会穿透回滚，故用 `_NoCommitDB` 把 commit 降级为 flush。
"""
import re
import uuid
from unittest.mock import patch

import pytest

from backend.models.database import db
from backend.models.models import (
    Audio,
    AudioAlgorithmRelation,
    AudioAnnotation,
    TestCase,
    TestCaseGroup,
    UploadFile,
    UploadTask,
)

TAG = uuid.uuid4().hex[:8]

# 存量音频（md5 命中的那一条，模拟 JS121 的 …_response_2.wav）
AUDIO_NAME = f'JS121_{TAG}_response_2.wav'
# 本次秒传上传的文件名（模拟 JS135），md5 与存量音频相同、名字不同
UPLOAD_NAME = f'JS135_{TAG}.wav'
# 另一条无关音频（链式错配里被前端错填给 JS135 那一项）
OTHER_AUDIO_NAME = f'JS110_{TAG}_response_1.wav'
# 库里改过名的存量音频（模拟用户重命名音频后重传原始文件）
RENAMED_AUDIO_NAME = f'JS121_{TAG}_renamed.wav'
GROUP_NAME = f'VEGA31独立验收_{TAG}'
ENDPOINT = '/api/v1/audios/upload/merge'
PATCH_REF_PARAMS = (
    'backend.utils.algorithm.reference_params_generator.ReferenceParamsGenerator.apply_to_config'
)

MD5_AUDIO = (f'c{TAG}' * 32)[:32]
MD5_OTHER = (f'd{TAG}' * 32)[:32]


def _js_no(text):
    """取名字里的 JS 编号（JS121 / JS135 …），无则 None"""
    m = re.search(r'JS\d+', text or '')
    return m.group(0) if m else None


class _NoCommitSession:
    """commit 降级为 flush，其余透传"""

    def __init__(self, real_session):
        self._real = real_session

    def commit(self):
        self._real.flush()

    def __getattr__(self, name):
        return getattr(self._real, name)


class _NoCommitDB:
    def __init__(self, real_db):
        self._real = real_db
        self.session = _NoCommitSession(real_db.session)

    def __getattr__(self, name):
        return getattr(self._real, name)


# ------------------------------------------------------------------
# 构造 / 清理 / 断言辅助
# ------------------------------------------------------------------

def _make_audio(name, md5, original_filename=None, deleted=False):
    audio = Audio(
        name=name,
        original_filename=name if original_filename is None else original_filename,
        file_path=f'/tmp/vega31_acc_{uuid.uuid4().hex}.wav',
        size=1608734,
        duration=1.0,
        format='wav',
        md5=md5,
        deleted=deleted,
    )
    db.session.add(audio)
    db.session.flush()
    return audio


def _make_instant_upload_file(md5, filename):
    """秒传文件：total_chunks=0 + status=completed"""
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


def _payload(file_id, task_id, rounds=None, create_test_case=True):
    cfg = {}
    if rounds is not None:
        cfg['rounds'] = rounds
    return {
        'fileId': file_id,
        'taskId': task_id,
        'createTestCase': create_test_case,
        'algorithmType': 'asr',
        'testTypes': ['api'],
        'groupNameType': 'custom',
        'customGroupName': GROUP_NAME,
        'testCaseConfig': cfg,
    }


def _purge(audio_ids=(), task_ids=()):
    """按本次运行唯一分组名 + 精确 ID 清理（绝不触碰其它测试数据）

    只 flush 不 commit：本文件的每个请求都包在 `_NoCommitDB` 里，controller 不会真正提交，
    因此 flush 就足以让清理在本测试事务内生效，而**不**把 conftest 的外层事务提交掉
    （一旦 commit，conftest 的算法表清理与隔离回滚都会失效，后续测试会 FK 报错）。
    """
    group = TestCaseGroup.query.filter_by(name=GROUP_NAME).first()
    if group:
        case_ids = [
            cid for (cid,) in db.session.query(TestCase.id).filter(TestCase.group_id == group.id).all()
        ]
        if case_ids:
            db.session.query(TestCase).filter(TestCase.id.in_(case_ids)).delete(
                synchronize_session=False
            )
        db.session.query(TestCaseGroup).filter(TestCaseGroup.id == group.id).delete(
            synchronize_session=False
        )
    if audio_ids:
        audio_ids = list(audio_ids)
        # 音频↔算法关联行先删，避免残留行指向被删音频
        db.session.query(AudioAlgorithmRelation).filter(
            AudioAlgorithmRelation.audio_id.in_(audio_ids)
        ).delete(synchronize_session=False)
        db.session.query(Audio).filter(Audio.id.in_(audio_ids)).delete(
            synchronize_session=False
        )
    for task_id in task_ids:
        db.session.query(UploadFile).filter(UploadFile.task_id == task_id).delete(
            synchronize_session=False
        )
        db.session.query(UploadTask).filter(UploadTask.id == task_id).delete(
            synchronize_session=False
        )
    db.session.flush()


def _cases_in_group():
    group = TestCaseGroup.query.filter_by(name=GROUP_NAME, deleted=False).first()
    if not group:
        return []
    return TestCase.query.filter_by(group_id=group.id, deleted=False).all()


def _referenced_audios(case):
    """用例 config 里所有已定 audio_id 的音频项（含 audio_name 与音频行）"""
    out = []
    for r in (case.config or {}).get('rounds') or []:
        for a in (r or {}).get('audios') or []:
            if not isinstance(a, dict) or not a.get('audio_id'):
                continue
            audio = db.session.get(Audio, int(a['audio_id']))
            out.append((a, audio))
    return out


def _assert_three_way_consistent(case):
    """领域不变量：用例名编号 / description 编号 / 主音频(audio_id) 编号 三者一致

    - 主音频 = config.rounds[0].audios[0]（用例名与 description 都取自它）；
    - 逐项校验：只要该项带了 audio_name，就必须与其 audio_id 所指音频同一编号；
    - 多轮用例可含**多条不同音频**（用例名只可能对应其中一条、description 取本次上传那条），
      故仅在「全部引用同一条音频」时校验 description 与用例名同编号。
    """
    refs = _referenced_audios(case)
    assert refs, f'用例「{case.name}」config 里没有已定 audio_id 的音频项'
    for item, audio in refs:
        assert audio is not None, f'用例「{case.name}」指向不存在的 audio_id={item["audio_id"]}'
        if item.get('audio_name'):
            assert _js_no(item['audio_name']) == _js_no(audio.name), (
                f'项 audio_name={item["audio_name"]!r} 与所指音频 name={audio.name!r} 编号不一致'
            )
    primary_audio = refs[0][1]
    assert _js_no(case.name) == _js_no(primary_audio.name), (
        f'用例名「{case.name}」与主音频「{primary_audio.name}」编号不一致'
    )
    if len({a.id for _, a in refs}) == 1:
        assert _js_no(case.description or '') == _js_no(primary_audio.name), (
            f'用例 description={case.description!r} 与主音频「{primary_audio.name}」编号不一致'
        )


def _dump_cases():
    """把本分组用例渲染成可读文本，用于失败信息（含每项 audio_name → 实际音频名）"""
    out = []
    for case in _cases_in_group():
        items = []
        for r in (case.config or {}).get('rounds') or []:
            for a in (r or {}).get('audios') or []:
                audio = db.session.get(Audio, int(a['audio_id'])) if a.get('audio_id') else None
                items.append(f'{a.get("audio_name")!r}→{audio.name if audio else None}')
        out.append(f'name={case.name!r} desc={case.description!r} items=[{", ".join(items)}]')
    return out or ['(无)']


def _assert_no_contradictory_case():
    """核心不变量：库里不存在「用例名编号 ≠ 主音频编号」的用例"""
    bad = []
    for case in _cases_in_group():
        refs = _referenced_audios(case)
        if not refs:
            bad.append((case.name, '(无 audio_id)', case.description))
            continue
        item, audio = refs[0]
        if audio is None or _js_no(case.name) != _js_no(audio.name):
            bad.append((case.name, audio.name if audio else item.get('audio_id'), case.description))
    assert not bad, f'存在用例名与音频互相矛盾的用例：{bad}'


# ------------------------------------------------------------------
# 1. 核心：JS135↔JS121 复现链 —— 拒绝建用例
# ------------------------------------------------------------------

class TestCoreRejection:
    def test_js135_js121_shape_is_rejected(self, client, app):
        """md5 命中 JS121 的音频、文件名是 JS135 → 拒绝 + 提示 + 无矛盾用例落库"""
        import backend.controllers.audio_controller as audio_controller

        existing = _make_audio(AUDIO_NAME, MD5_AUDIO)
        task_id, file_id = _make_instant_upload_file(MD5_AUDIO, UPLOAD_NAME)
        cases_before = TestCase.query.count()
        audio_before = Audio.query.count()
        ann_before = AudioAnnotation.query.count()
        try:
            with patch.object(audio_controller, 'db', _NoCommitDB(db)), patch(PATCH_REF_PARAMS):
                resp = client.post(
                    ENDPOINT,
                    json=_payload(
                        file_id,
                        task_id,
                        [{'roundNumber': 1, 'audios': [{'audioName': UPLOAD_NAME, 'playOrder': 0}]}],
                    ),
                )

            body = resp.get_json()
            # 明确报错（前端 fetch 路径 response.ok=false → throw new Error(data.message)）
            assert resp.status_code == 400, body
            assert body['code'] != 0, body
            msg = body['message']
            # 提示必须同时点名两个名字，且给出可操作指引
            assert UPLOAD_NAME in msg and AUDIO_NAME in msg, msg
            assert '重命名' in msg, msg

            # 不建用例、不留矛盾行
            assert TestCase.query.count() == cases_before
            assert _cases_in_group() == []
            _assert_no_contradictory_case()
            # 拒绝路径无部分写入：不建分组、不建音频、不写标注
            assert TestCaseGroup.query.filter_by(name=GROUP_NAME).first() is None
            assert Audio.query.count() == audio_before
            assert AudioAnnotation.query.count() == ann_before
        finally:
            _purge(audio_ids=[existing.id], task_ids=[task_id])

    def test_rejection_is_not_silent(self, client, app):
        """拒绝必须留 warning 日志（不得静默错配）"""
        import backend.controllers.audio_controller as audio_controller

        existing = _make_audio(AUDIO_NAME, MD5_AUDIO)
        task_id, file_id = _make_instant_upload_file(MD5_AUDIO, UPLOAD_NAME)
        try:
            with patch.object(audio_controller, 'db', _NoCommitDB(db)), \
                 patch(PATCH_REF_PARAMS), \
                 patch('backend.controllers.audio_controller.logger') as mock_logger:
                client.post(
                    ENDPOINT,
                    json=_payload(
                        file_id,
                        task_id,
                        [{'roundNumber': 1, 'audios': [{'audioName': UPLOAD_NAME, 'playOrder': 0}]}],
                    ),
                )
            msgs = [str(c.args[0]) for c in mock_logger.warning.call_args_list]
            assert any(UPLOAD_NAME in m and AUDIO_NAME in m for m in msgs), msgs
        finally:
            _purge(audio_ids=[existing.id], task_ids=[task_id])


# ------------------------------------------------------------------
# 2. 链式错配（前端已回填的 audio_id 与该项名称不符）
# ------------------------------------------------------------------

class TestChainedMismatch:
    def test_prefilled_wrong_audio_id_rejected(self, client, app):
        """rounds 里前置项 audio_id 指向另一条音频、名字对不上 → 拒绝（自检 B）"""
        import backend.controllers.audio_controller as audio_controller

        existing = _make_audio(AUDIO_NAME, MD5_AUDIO)
        other = _make_audio(OTHER_AUDIO_NAME, MD5_OTHER)
        # 本次上传的文件名与命中音频一致（自检 A 不会拦），错配来自前置项
        task_id, file_id = _make_instant_upload_file(MD5_AUDIO, AUDIO_NAME)
        cases_before = TestCase.query.count()
        try:
            with patch.object(audio_controller, 'db', _NoCommitDB(db)), patch(PATCH_REF_PARAMS):
                resp = client.post(
                    ENDPOINT,
                    json=_payload(
                        file_id,
                        task_id,
                        [
                            {
                                'roundNumber': 1,
                                'audios': [
                                    {'audioName': UPLOAD_NAME, 'audioId': other.id, 'playOrder': 0},
                                    {'audioName': AUDIO_NAME, 'playOrder': 1},
                                ],
                            }
                        ],
                    ),
                )

            body = resp.get_json()
            assert resp.status_code == 400, body
            assert UPLOAD_NAME in body['message'] and OTHER_AUDIO_NAME in body['message'], body
            assert TestCase.query.count() == cases_before
            _assert_no_contradictory_case()
        finally:
            _purge(audio_ids=[existing.id, other.id], task_ids=[task_id])


# ------------------------------------------------------------------
# 3. 回归：正常秒传路径不得被一起堵死，且三者一致
# ------------------------------------------------------------------

class TestRegression:
    def test_same_name_instant_upload_still_creates_consistent_case(self, client, app):
        """同一文件重传（名字一致）→ 照常建用例，且用例名/description/audio_id 三者一致"""
        import backend.controllers.audio_controller as audio_controller

        existing = _make_audio(AUDIO_NAME, MD5_AUDIO)
        task_id, file_id = _make_instant_upload_file(MD5_AUDIO, AUDIO_NAME)
        try:
            with patch.object(audio_controller, 'db', _NoCommitDB(db)), patch(PATCH_REF_PARAMS):
                resp = client.post(
                    ENDPOINT,
                    json=_payload(
                        file_id,
                        task_id,
                        [{'roundNumber': 1, 'audios': [{'audioName': AUDIO_NAME, 'playOrder': 0}]}],
                    ),
                )

            body = resp.get_json()
            assert resp.status_code == 200, body
            assert body['code'] == 0, body
            data = body['data']
            assert data['instantUpload'] is True
            assert data['audioId'] == existing.id
            assert data['testCaseId'], body

            case = TestCase.query.filter_by(id=data['testCaseId']).first()
            assert case is not None
            assert case.name == f'测试用例_{AUDIO_NAME}'
            _assert_three_way_consistent(case)
        finally:
            _purge(audio_ids=[existing.id], task_ids=[task_id])

    def test_renamed_in_library_still_matches_by_original_filename(self, client, app):
        """音频在库里改过名、原始文件名与上传名一致 → 仍正常秒传建用例且三者一致"""
        import backend.controllers.audio_controller as audio_controller

        existing = _make_audio(RENAMED_AUDIO_NAME, MD5_AUDIO, original_filename=UPLOAD_NAME)
        task_id, file_id = _make_instant_upload_file(MD5_AUDIO, UPLOAD_NAME)
        try:
            with patch.object(audio_controller, 'db', _NoCommitDB(db)), patch(PATCH_REF_PARAMS):
                resp = client.post(
                    ENDPOINT,
                    json=_payload(
                        file_id,
                        task_id,
                        [{'roundNumber': 1, 'audios': [{'audioName': UPLOAD_NAME, 'playOrder': 0}]}],
                    ),
                )

            body = resp.get_json()
            assert resp.status_code == 200, body
            data = body['data']
            assert data['instantUpload'] is True and data['audioId'] == existing.id
            case = TestCase.query.filter_by(id=data['testCaseId']).first()
            assert case.name == f'测试用例_{UPLOAD_NAME}'
            assert case.config['rounds'][0]['audios'][0]['audio_id'] == existing.id
        finally:
            _purge(audio_ids=[existing.id], task_ids=[task_id])

    def test_create_test_case_false_unaffected(self, client, app):
        """createTestCase=false 的秒传（分组内非最后一个文件）不受影响：200 + 不建用例"""
        import backend.controllers.audio_controller as audio_controller

        existing = _make_audio(AUDIO_NAME, MD5_AUDIO)
        task_id, file_id = _make_instant_upload_file(MD5_AUDIO, UPLOAD_NAME)
        cases_before = TestCase.query.count()
        try:
            with patch.object(audio_controller, 'db', _NoCommitDB(db)), patch(PATCH_REF_PARAMS):
                resp = client.post(
                    ENDPOINT,
                    json=_payload(
                        file_id,
                        task_id,
                        [{'roundNumber': 1, 'audios': [{'audioName': UPLOAD_NAME, 'playOrder': 0}]}],
                        create_test_case=False,
                    ),
                )

            body = resp.get_json()
            assert resp.status_code == 200, body
            assert body['data']['instantUpload'] is True
            assert TestCase.query.count() == cases_before
        finally:
            _purge(audio_ids=[existing.id], task_ids=[task_id])

    def test_multi_file_group_last_file_matching_still_creates_case(self, client, app):
        """多文件分组收尾：前置项已回填正确 audio_id + 本次项名字匹配 → 正常建用例且三者一致

        这是「收紧兜底」最需要保护的正常路径：分组内前几个秒传文件已回填 audio_id，
        最后一个文件建用例时 matched_count 可能为 0（本次项已回填）——不得误拦。
        """
        import backend.controllers.audio_controller as audio_controller

        first = _make_audio(AUDIO_NAME, MD5_AUDIO)
        second = _make_audio(f'JS136_{TAG}_response_1.wav', MD5_OTHER)
        task_id, file_id = _make_instant_upload_file(MD5_OTHER, f'JS136_{TAG}_response_1.wav')
        try:
            with patch.object(audio_controller, 'db', _NoCommitDB(db)), patch(PATCH_REF_PARAMS):
                resp = client.post(
                    ENDPOINT,
                    json=_payload(
                        file_id,
                        task_id,
                        [
                            {
                                'roundNumber': 1,
                                'audios': [
                                    # 前置文件（已由前端回填 audio_id，名字与音频一致）
                                    {'audioName': AUDIO_NAME, 'audioId': first.id, 'playOrder': 0},
                                    # 本次上传项（名字与命中音频一致）
                                    {'audioName': f'JS136_{TAG}_response_1.wav', 'playOrder': 1},
                                ],
                            }
                        ],
                    ),
                )

            body = resp.get_json()
            assert resp.status_code == 200, body
            case = TestCase.query.filter_by(id=body['data']['testCaseId']).first()
            assert case is not None
            _assert_three_way_consistent(case)
        finally:
            _purge(audio_ids=[first.id, second.id], task_ids=[task_id])


# ------------------------------------------------------------------
# 4. 边界：开发自测未覆盖的口径边界（记录实际行为，非缺陷）
# ------------------------------------------------------------------

class TestBoundaries:
    def test_empty_audio_name_not_blocked_and_case_named_after_audio(self, client, app):
        """rounds 项未带 audio_name（前端未填）→ 不拦；用例名回退到音频名，三者仍一致"""
        import backend.controllers.audio_controller as audio_controller

        existing = _make_audio(AUDIO_NAME, MD5_AUDIO)
        task_id, file_id = _make_instant_upload_file(MD5_AUDIO, UPLOAD_NAME)
        try:
            with patch.object(audio_controller, 'db', _NoCommitDB(db)), patch(PATCH_REF_PARAMS):
                resp = client.post(
                    ENDPOINT,
                    json=_payload(
                        file_id,
                        task_id,
                        [{'roundNumber': 1, 'audios': [{'playOrder': 0}]}],
                    ),
                )

            body = resp.get_json()
            assert resp.status_code == 200, body
            case = TestCase.query.filter_by(id=body['data']['testCaseId']).first()
            assert case.name == f'测试用例_{AUDIO_NAME}'
            _assert_three_way_consistent(case)
        finally:
            _purge(audio_ids=[existing.id], task_ids=[task_id])

    def test_no_rounds_config_behavior(self, client, app):
        """前端未下发 rounds（分组无多轮配置）时的实际行为：用例名取自音频名，三者一致

        记录性断言：此路径下 backend 无 audio_name 可比对，用例名/description/audio_id
        均取自命中音频本身 → 不构成本卡定义的「名称与音频互相矛盾」，故不在拦截面内。
        """
        import backend.controllers.audio_controller as audio_controller

        existing = _make_audio(AUDIO_NAME, MD5_AUDIO)
        task_id, file_id = _make_instant_upload_file(MD5_AUDIO, UPLOAD_NAME)
        try:
            with patch.object(audio_controller, 'db', _NoCommitDB(db)), patch(PATCH_REF_PARAMS):
                resp = client.post(ENDPOINT, json=_payload(file_id, task_id, rounds=None))

            body = resp.get_json()
            assert resp.status_code == 200, body
            case = TestCase.query.filter_by(id=body['data']['testCaseId']).first()
            assert case is not None
            _assert_three_way_consistent(case)
        finally:
            _purge(audio_ids=[existing.id], task_ids=[task_id])

    def test_soft_deleted_audio_not_flagged_by_helper(self, app):
        """helper 不把「指向已软删音频」判为名称矛盾（不扩大拦截面）"""
        from backend.controllers.audio_controller import AudioController

        deleted = _make_audio(AUDIO_NAME, MD5_AUDIO, deleted=True)
        rounds = [{'round_number': 1, 'audios': [{'audio_name': UPLOAD_NAME, 'audio_id': deleted.id}]}]
        assert AudioController._find_round_audio_name_mismatch(rounds) is None

    def test_md5_as_audio_name_accepted(self, app):
        """audio_name 直接给 md5（既有三键匹配约定）→ 不算矛盾（不拦）"""
        from backend.controllers.audio_controller import AudioController

        audio = _make_audio(AUDIO_NAME, MD5_AUDIO)
        rounds = [{'round_number': 1, 'audios': [{'audio_name': MD5_AUDIO, 'audio_id': audio.id}]}]
        assert AudioController._find_round_audio_name_mismatch(rounds) is None

    @pytest.mark.parametrize('rounds', [None, [], 'x', [None], [{'audios': None}], [{'audios': [None]}]])
    def test_helper_tolerates_malformed(self, app, rounds):
        from backend.controllers.audio_controller import AudioController

        assert AudioController._find_round_audio_name_mismatch(rounds) is None


class TestResidualEscape:
    """残留逃逸（阻断项）：自检 A 是「全局计数」口径，矛盾项不在唯一未匹配位置时漏过"""

    @pytest.mark.parametrize(
        'label,rounds',
        [
            # A：矛盾项在 rounds[1]，rounds[0] 的项靠名字匹配（无 audio_id）
            (
                'A-错配项在第二轮',
                [
                    {'roundNumber': 1, 'audios': [{'audioName': AUDIO_NAME, 'playOrder': 0}]},
                    {'roundNumber': 2, 'audios': [{'audioName': UPLOAD_NAME, 'playOrder': 0}]},
                ],
            ),
            # C：rounds[0] 的项没带 audio_name（既有匹配把「空名」当命中，同样让 matched_count≥1）
            (
                'C-首项无audio_name',
                [
                    {'roundNumber': 1, 'audios': [{'playOrder': 0}]},
                    {'roundNumber': 2, 'audios': [{'audioName': UPLOAD_NAME, 'playOrder': 0}]},
                ],
            ),
            # D：矛盾项与匹配项同在一轮（用例名/description 一致，但该轮音频项 audio_name↔audio_id 矛盾）
            (
                'D-同轮第二项错配',
                [
                    {
                        'roundNumber': 1,
                        'audios': [
                            {'audioName': AUDIO_NAME, 'playOrder': 0},
                            {'audioName': UPLOAD_NAME, 'playOrder': 1},
                        ],
                    }
                ],
            ),
        ],
    )
    def test_mismatch_item_not_in_first_position_must_be_rejected_BLOCKING(self, client, app, label, rounds):
        """【阻断项】矛盾项不在「无 audio_id 项里的唯一一个」时，秒传仍会建出名称与音频矛盾的用例

        构造（满足验收标准 1 的前提「md5 已存在 + 名称不匹配」）：
        - 存量音频 name=JS121…（md5=M）；
        - 本次秒传上传的文件名 JS135…，md5=M（= 名称不匹配的秒传）；
        - rounds 里另有一项名字与存量音频一致（同分组前一个文件的项），且该项没有 audio_id。

        期望：拒绝（400）或至少不建出「名称与音频互相矛盾」的用例。
        实际（5671ab04 / HEAD）：200 + code=0，建出矛盾用例，例如 A：
          name = 测试用例_JS135…                 ← 取自 rounds[1].audios[0].audio_name
          description = 自动从音频 'JS121…' 创建的测试用例
          config.rounds[1].audios[0] = {audio_name: JS135…, audio_id: <JS121 那条音频>}
        即本卡「现象」原文（用例名 JS135 / description 与 audio_id 都是 JS121）原样复现。

        成因：两道自检都跑在 `_create_test_case_from_audio` **之前**，而
        ① 自检 A 用「全 rounds 一个都没匹配上」（matched_count == 0）判定——只要另有一项
           按 name/original_filename/md5/空名匹配上，本次上传这一项就不再被拦；
        ② 自检 B 只查「已定 audio_id 且与 audio_name 不符」的项，此时本次上传项还没有 audio_id → 漏过；
        ③ 之后 `_create_test_case_from_audio` 的兜底强填（audio_controller.py:2171-2173）把命中音频 id
           填进该项；用例名又取「第一个与命中音频名不同的 audio_name」→ 矛盾在自检之后生成。
        """
        import backend.controllers.audio_controller as audio_controller

        existing = _make_audio(AUDIO_NAME, MD5_AUDIO)
        task_id, file_id = _make_instant_upload_file(MD5_AUDIO, UPLOAD_NAME)
        cases_before = TestCase.query.count()
        try:
            with patch.object(audio_controller, 'db', _NoCommitDB(db)), patch(PATCH_REF_PARAMS):
                resp = client.post(ENDPOINT, json=_payload(file_id, task_id, rounds))

            body = resp.get_json()
            assert resp.status_code == 400, (
                f'[{label}] 期望拒绝建用例，实际 {resp.status_code} {body}\n'
                f'库内用例：{_dump_cases()}'
            )
            assert TestCase.query.count() == cases_before
            _assert_no_contradictory_case()
        finally:
            _purge(audio_ids=[existing.id], task_ids=[task_id])

    def test_backfilled_first_item_is_rejected(self, client, app):
        """对照（已通过）：rounds[0] 项已由前端回填正确 audio_id 时，同一构造会被正确拒绝

        与上面 BLOCKING 用例的唯一差别是首项带了 audio_id（= 前端正常回填后的状态），
        此时本次上传项成为唯一未匹配项，自检 A 生效 → 400。说明缺陷出在
        「matched_count 是全局计数」这一判定口径上，而不是整条秒传路径都失效。
        """
        import backend.controllers.audio_controller as audio_controller

        existing = _make_audio(AUDIO_NAME, MD5_AUDIO)
        task_id, file_id = _make_instant_upload_file(MD5_AUDIO, UPLOAD_NAME)
        cases_before = TestCase.query.count()
        try:
            with patch.object(audio_controller, 'db', _NoCommitDB(db)), patch(PATCH_REF_PARAMS):
                resp = client.post(
                    ENDPOINT,
                    json=_payload(
                        file_id,
                        task_id,
                        [
                            {
                                'roundNumber': 1,
                                'audios': [
                                    {'audioName': AUDIO_NAME, 'audioId': existing.id, 'playOrder': 0}
                                ],
                            },
                            {'roundNumber': 2, 'audios': [{'audioName': UPLOAD_NAME, 'playOrder': 0}]},
                        ],
                    ),
                )

            body = resp.get_json()
            assert resp.status_code == 400, body
            assert TestCase.query.count() == cases_before
            _assert_no_contradictory_case()
        finally:
            _purge(audio_ids=[existing.id], task_ids=[task_id])
