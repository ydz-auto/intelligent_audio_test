# -*- coding: utf-8 -*-
"""
音频多轮上传相关 schema 与逻辑的单元测试。

覆盖：
- MergeChunksRequest 接收 rounds 配置
- 标注 annotation.scope / roundNumber 字段
- _build_rounds_from_files 构建多轮配置
- _create_test_case_from_audio 接收 rounds 并生成参考参数

契约口径（蛇形 key 统一后）：
- API 边界：TestCaseUploadConfig.rounds 为 List[RoundConfigItem]（pydantic 模型，
  AliasChoices 兼容驼峰入参），属性访问用蛇形（round_number）
- controller 内部：rounds 一律为蛇形 key 的 dict 列表（round_number/audio_id/play_order）
- algorithm_params / reference_params 不在 config.rounds[] 中，剥离到 test_cases 独立列
  （按轮分组 [{round_number, params}]）
"""
import pytest
from unittest.mock import MagicMock, patch


# ============================================================
# Schema 测试
# ============================================================

class TestMergeChunksRequestRounds:
    """MergeChunksRequest 对多轮配置的支持"""

    def test_merge_request_accepts_rounds_config(self):
        """merge 请求可以携带 rounds 配置"""
        from backend.schemas.audio import MergeChunksRequest

        payload = {
            "fileId": "f1",
            "taskId": "t1",
            "createTestCase": True,
            "testCaseConfig": {
                "rounds": [
                    {
                        "roundNumber": 1,
                        "audios": [{"audioId": 1, "playOrder": 0}],
                        "algorithmParams": [{"fieldCode": "model", "fieldValue": "whisper"}],
                    },
                    {
                        "roundNumber": 2,
                        "audios": [{"audioId": 2, "playOrder": 0}],
                    },
                ],
                "dimensions": [{"id": 1, "name": "wer"}],
                "groupName": "自定义分组",
                "inheritTags": True,
            },
        }

        req = MergeChunksRequest.model_validate(payload)
        assert req.create_test_case is True
        tc = req.test_case_config
        assert tc is not None
        assert len(tc.rounds) == 2
        # schema 演进后 rounds 由 List[Dict] 归一为 List[RoundConfigItem]（pydantic 模型），
        # 断言改用蛇形属性访问；驼峰入参（roundNumber/audioId/playOrder）经 AliasChoices 归一
        assert tc.rounds[0].round_number == 1
        assert tc.rounds[1].round_number == 2
        assert tc.rounds[0].audios[0].audio_id == 1
        assert tc.rounds[0].audios[0].play_order == 0
        assert tc.group_name == "自定义分组"
        assert tc.inherit_tags is True

    def test_merge_request_rounds_default_none(self):
        """不传 testCaseConfig 时默认为 None，向后兼容"""
        from backend.schemas.audio import MergeChunksRequest

        req = MergeChunksRequest.model_validate({"fileId": "f1", "taskId": "t1"})
        assert req.test_case_config is None

    def test_annotation_accepts_scope_and_round_number(self):
        """标注条目支持 scope 和 roundNumber 字段"""
        from backend.schemas.audio import MergeChunksRequest

        payload = {
            "fileId": "f1",
            "taskId": "t1",
            "annotations": [
                {
                    "format": "json",
                    "code": "multi_round",
                    "data": {"segments": []},
                    "scope": "round",
                    "roundNumber": 1,
                },
                {
                    "format": "text",
                    "code": "asr",
                    "data": {"text": "hello"},
                    # 默认 scope = audio
                },
            ],
        }

        req = MergeChunksRequest.model_validate(payload)
        anns = req.annotations
        assert anns[0]["scope"] == "round"
        assert anns[0]["roundNumber"] == 1
        # 不传 scope 时不报错，保留原结构
        assert "scope" not in anns[1] or anns[1].get("scope") is None


# ============================================================
# _build_rounds_from_files 逻辑测试
# ============================================================

class TestBuildRoundsFromFiles:
    """从文件列表构建 rounds 配置"""

    def test_single_audio_per_round_mode(self):
        """模式 A：每个音频 = 一轮"""
        from backend.controllers.audio_controller import AudioController

        files = [
            {"file_id": "f1", "audio_id": 1, "filename": "01.wav"},
            {"file_id": "f2", "audio_id": 2, "filename": "02.wav"},
            {"file_id": "f3", "audio_id": 3, "filename": "03.wav"},
        ]

        rounds = AudioController._build_rounds_from_files(
            files, mode="multi_round"
        )

        # 后端统一蛇形 key：round_number（不再是 roundNumber）
        assert len(rounds) == 3
        assert rounds[0]["round_number"] == 1
        assert rounds[0]["audios"][0]["audio_id"] == 1
        assert rounds[0]["audios"][0]["play_order"] == 0
        assert rounds[1]["round_number"] == 2
        assert rounds[2]["round_number"] == 3

    def test_single_round_multi_audio_mode(self):
        """模式 B：一个文件夹 = 一轮，多音频同轮"""
        from backend.controllers.audio_controller import AudioController

        files = [
            {"file_id": "f1", "audio_id": 1, "filename": "dry.wav"},
            {"file_id": "f2", "audio_id": 2, "filename": "noise1.wav"},
            {"file_id": "f3", "audio_id": 3, "filename": "noise2.wav"},
        ]

        rounds = AudioController._build_rounds_from_files(
            files, mode="single_round_multi_audio"
        )

        assert len(rounds) == 1
        assert rounds[0]["round_number"] == 1
        assert len(rounds[0]["audios"]) == 3
        assert rounds[0]["audios"][0]["play_order"] == 0
        assert rounds[0]["audios"][1]["play_order"] == 1
        assert rounds[0]["audios"][2]["play_order"] == 2

    def test_empty_files_returns_empty_rounds(self):
        from backend.controllers.audio_controller import AudioController

        rounds = AudioController._build_rounds_from_files([], mode="multi_round")
        assert rounds == []

    def test_single_file_multi_round_mode(self):
        """单个文件走 multi_round 模式 = 单轮单音频"""
        from backend.controllers.audio_controller import AudioController

        files = [{"file_id": "f1", "audio_id": 1, "filename": "01.wav"}]

        rounds = AudioController._build_rounds_from_files(
            files, mode="multi_round"
        )

        assert len(rounds) == 1
        assert rounds[0]["round_number"] == 1
        assert len(rounds[0]["audios"]) == 1


# ============================================================
# _create_test_case_from_audio rounds 支持 测试
# ============================================================

class TestCreateTestCaseWithRounds:
    """_create_test_case_from_audio 接收 rounds 配置"""

    def test_create_test_case_with_explicit_rounds(self):
        """传入完整 rounds 时，TestCase.config 应包含 rounds"""
        from backend.controllers.audio_controller import AudioController
        from backend.models.models import TestCase

        mock_audio = MagicMock()
        mock_audio.id = 1
        mock_audio.name = "test.wav"

        # PlaybackDevice 需在源模块 patch：_create_test_case_from_audio 内部
        # `from backend.models.models import PlaybackDevice` 做设备名→ID 预查询，
        # 未 patch 时会触发真实查询（Working outside of application context）
        with patch("backend.controllers.audio_controller.db") as mock_db, \
             patch("backend.controllers.audio_controller.Audio") as mock_audio_cls, \
             patch("backend.controllers.audio_controller.TestCaseGroup") as mock_group_cls, \
             patch("backend.controllers.audio_controller.TestCase") as mock_tc_cls, \
             patch("backend.controllers.audio_controller.Tag") as mock_tag_cls, \
             patch("backend.models.models.PlaybackDevice") as mock_dev_cls, \
             patch("backend.utils.algorithm.reference_params_generator.ReferenceParamsGenerator") as mock_gen:

            mock_db.session.no_autoflush = MagicMock(return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock()))
            mock_db.session.add = MagicMock()
            mock_db.session.flush = MagicMock()
            mock_db.session.get = MagicMock(return_value=mock_audio)

            mock_audio_cls.query.filter_by.return_value.first.return_value = None
            mock_group_cls.query.filter_by.return_value.first.return_value = None
            mock_group_cls.return_value = MagicMock(id="g1")

            mock_tc = MagicMock()
            mock_tc.id = "tc1"
            mock_tc.config = {}
            mock_tc.algorithm_type = "asr"
            # 测试中参考参数生成器为 MagicMock 不会回填独立列，
            # 显式置 None，避免 controller 调试日志对 MagicMock 做 JSON 序列化报错
            mock_tc.algorithm_params = None
            mock_tc.reference_params = None
            mock_tc_cls.return_value = mock_tc

            # 执行
            # 边界（mergeChunks）经 RoundConfigItem.model_dump(by_alias=False) 归一后
            # 传给 controller 的是蛇形 key 的 dict 列表
            rounds_config = [
                {
                    "round_number": 1,
                    "audios": [{"audio_id": 1, "play_order": 0}],
                    "algorithm_params": [{"field_code": "model", "field_value": "whisper"}],
                }
            ]

            result = AudioController._create_test_case_from_audio(
                audio_id=1,
                test_types=["api"],
                audio_tags=["tag1"],
                rounds_config=rounds_config,
                algorithm_type="asr",
            )

            # 验证 TestCase 被创建，config 包含 rounds
            assert mock_tc_cls.called
            _, kwargs = mock_tc_cls.call_args
            config = kwargs.get("config", {})
            assert "rounds" in config
            assert len(config["rounds"]) == 1
            assert config["rounds"][0]["round_number"] == 1
            # schema 演进：algorithm_params 从 config.rounds[] 剥离到独立列（按轮分组）
            assert "algorithm_params" not in config["rounds"][0]
            assert kwargs.get("algorithm_params") == [
                {"round_number": 1, "params": [{"field_code": "model", "field_value": "whisper"}]}
            ]

            # 验证参考参数生成器被调用（同步生成）
            mock_gen.apply_to_config.assert_called_once_with(mock_tc)

    def test_create_test_case_falls_back_to_minimal_rounds_when_no_rounds(self):
        """不传 rounds_config 时，自动构建最小 rounds（统一 rounds 架构）"""
        from backend.controllers.audio_controller import AudioController

        with patch("backend.controllers.audio_controller.db") as mock_db, \
             patch("backend.controllers.audio_controller.Audio") as mock_audio_cls, \
             patch("backend.controllers.audio_controller.TestCaseGroup") as mock_group_cls, \
             patch("backend.controllers.audio_controller.TestCase") as mock_tc_cls, \
             patch("backend.controllers.audio_controller.Tag") as mock_tag_cls, \
             patch("backend.models.models.PlaybackDevice") as mock_dev_cls, \
             patch("backend.utils.algorithm.reference_params_generator.ReferenceParamsGenerator") as mock_gen:

            mock_audio = MagicMock()
            mock_audio.id = 1
            mock_audio.name = "test.wav"
            mock_db.session.get.return_value = mock_audio
            mock_db.session.no_autoflush = MagicMock(return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock()))

            mock_group_cls.query.filter_by.return_value.first.return_value = MagicMock(id="g1")
            mock_tc = MagicMock()
            mock_tc.id = "tc1"
            mock_tc.config = {}
            mock_tc.algorithm_type = "asr"
            # 测试中参考参数生成器为 MagicMock 不会回填独立列，
            # 显式置 None，避免 controller 调试日志对 MagicMock 做 JSON 序列化报错
            mock_tc.algorithm_params = None
            mock_tc.reference_params = None
            mock_tc_cls.return_value = mock_tc

            AudioController._create_test_case_from_audio(
                audio_id=1,
                test_types=["api"],
                audio_tags=[],
                rounds_config=None,  # 不传 rounds
                algorithm_type="asr",
                spl=65.0,
            )

            # 验证 config 统一走 rounds 架构（无平面模式 audios 字段）
            _, kwargs = mock_tc_cls.call_args
            config = kwargs.get("config", {})
            assert "rounds" in config
            assert "audios" not in config  # 不再有顶层 audios
            rounds = config["rounds"]
            assert len(rounds) == 1
            assert rounds[0]["round_number"] == 1
            # audio_id / spl 应该已填入
            assert rounds[0]["audios"][0]["audio_id"] == 1
            assert rounds[0]["audios"][0]["spl"] == 65.0
            # 算法参数不再写入 rounds（存独立列），inputAudio 也不再自动填入
            assert "algorithmParams" not in rounds[0]
            assert "algorithm_params" not in rounds[0]
            assert kwargs.get("algorithm_params") is None

    def test_create_test_case_resolves_audio_name_to_id(self):
        """前端用 audio_name 占位，后端 rounds 模式应替换为真实 audio_id"""
        from backend.controllers.audio_controller import AudioController

        with patch("backend.controllers.audio_controller.db") as mock_db, \
             patch("backend.controllers.audio_controller.Audio") as mock_audio_cls, \
             patch("backend.controllers.audio_controller.TestCaseGroup") as mock_group_cls, \
             patch("backend.controllers.audio_controller.TestCase") as mock_tc_cls, \
             patch("backend.controllers.audio_controller.Tag") as mock_tag_cls, \
             patch("backend.models.models.PlaybackDevice") as mock_dev_cls, \
             patch("backend.utils.algorithm.reference_params_generator.ReferenceParamsGenerator") as mock_gen:

            mock_audio = MagicMock()
            mock_audio.id = 42
            mock_audio.name = "test.wav"
            mock_db.session.get.return_value = mock_audio
            mock_db.session.no_autoflush = MagicMock(return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock()))

            mock_group_cls.query.filter_by.return_value.first.return_value = MagicMock(id="g1")
            mock_tc = MagicMock()
            mock_tc.id = "tc1"
            mock_tc.config = {}
            mock_tc.algorithm_type = "voice_llm"
            # 测试中参考参数生成器为 MagicMock 不会回填独立列，
            # 显式置 None，避免 controller 调试日志对 MagicMock 做 JSON 序列化报错
            mock_tc.algorithm_params = None
            mock_tc.reference_params = None
            mock_tc_cls.return_value = mock_tc

            # 前端构建的 rounds 用 audio_name 占位，无 audio_id（边界归一后为蛇形 key）
            rounds_config = [
                {
                    "round_number": 1,
                    "audios": [{"audio_name": "test.wav", "play_order": 0}],
                    "algorithm_params": [],
                }
            ]

            AudioController._create_test_case_from_audio(
                audio_id=42,
                test_types=["api"],
                audio_tags=[],
                rounds_config=rounds_config,
                algorithm_type="voice_llm",
            )

            _, kwargs = mock_tc_cls.call_args
            config = kwargs.get("config", {})
            rounds = config["rounds"]
            # audio_name 应被替换为 audio_id
            assert rounds[0]["audios"][0]["audio_id"] == 42
            # 算法参数不再写入 rounds（存独立列），inputAudio 也不再自动填入
            assert "algorithmParams" not in rounds[0]
            assert "algorithm_params" not in rounds[0]

    def test_inherit_tags_false_skips_tag_inheritance(self):
        """inherit_tags=False 时不继承标签"""
        from backend.controllers.audio_controller import AudioController

        with patch("backend.controllers.audio_controller.db") as mock_db, \
             patch("backend.controllers.audio_controller.Audio") as mock_audio_cls, \
             patch("backend.controllers.audio_controller.TestCaseGroup") as mock_group_cls, \
             patch("backend.controllers.audio_controller.TestCase") as mock_tc_cls, \
             patch("backend.controllers.audio_controller.Tag") as mock_tag_cls, \
             patch("backend.models.models.PlaybackDevice") as mock_dev_cls, \
             patch("backend.utils.algorithm.reference_params_generator.ReferenceParamsGenerator") as mock_gen:

            mock_audio = MagicMock()
            mock_audio.id = 1
            mock_audio.name = "test.wav"
            mock_db.session.get.return_value = mock_audio
            mock_db.session.no_autoflush = MagicMock(return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock()))

            mock_group_cls.query.filter_by.return_value.first.return_value = MagicMock(id="g1")
            mock_tc = MagicMock()
            mock_tc.id = "tc1"
            mock_tc.config = {}
            mock_tc.algorithm_type = "asr"
            mock_tc.tags = MagicMock()  # MagicMock list-like
            # 测试中参考参数生成器为 MagicMock 不会回填独立列，
            # 显式置 None，避免 controller 调试日志对 MagicMock 做 JSON 序列化报错
            mock_tc.algorithm_params = None
            mock_tc.reference_params = None
            mock_tc_cls.return_value = mock_tc

            AudioController._create_test_case_from_audio(
                audio_id=1,
                test_types=["api"],
                audio_tags=["tag1", "tag2"],
                rounds_config=None,
                algorithm_type="asr",
                inherit_tags=False,
            )

            # inherit_tags=False 时，不调用 tag 查找
            mock_tag_cls.query.filter_by.assert_not_called()
