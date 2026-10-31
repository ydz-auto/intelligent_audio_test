# -*- coding: utf-8 -*-
"""INT-2235 守卫：评估轮次音频路径补全改经 gRPC + ACL，不再裸 SQL 直连 audios 表。

原缺陷（P1）：``round_data_builder._fill_round_audio_paths`` 直接对
audio_service 自有表 ``audios`` 发裸 SQL（``SELECT file_path FROM audios ...``），
绕过 gRPC + ACL，违反「跨服务一律 gRPC + ACL，不绕网关直连」架构红线；
同时循环内逐条查询（N+1）且 session 未 close。

守卫（纯单测，不触真实 DB/gRPC）：
1. 评估侧源码不再出现 ``FROM audios`` 裸 SQL；
2. ACL 实现：入参归一去重后一次批量调用，返回 {audio_id: AudioDTO}，
   已软删/不存在记录不在返回 map 中（deleted 语义由 audio_service 侧保证）；
3. 轮次补全：一轮内多个 audio_id 合并为一次 ACL 调用并正确填充 audio_path；
4. 已填 audio_path 的项跳过、无 audio_id 的项跳过（零调用）；
5. 未找到音频（软删/无路径）→ WARNING 且不填；ACL 异常 → ERROR 且不崩。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from unittest.mock import MagicMock, patch

import pytest

import evaluation_service.infrastructure.acl as _acl_pkg
from evaluation_service.domain.dto import AudioDTO
from evaluation_service.domain.services.evaluation_service.round_data_builder import (
    RoundDataBuilderMixin,
)
from evaluation_service.infrastructure.acl.audio_acl_repository import (
    AudioAclRepository,
)

_ACL_CALL = 'evaluation_service.infrastructure.acl.audio_acl_repository.get_audios_by_ids'
_BUILDER_SRC = (
    'evaluation_service/domain/services/evaluation_service/round_data_builder.py'
)


class _Host(RoundDataBuilderMixin):
    def __init__(self):
        self.logs = []

    def _log(self, level, content, **kw):
        self.logs.append((level, content))


class TestNoRawSql:
    def test_no_raw_sql_against_audios_table(self):
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            *_BUILDER_SRC.split('/'),
        )
        with open(path, encoding='utf-8') as f:
            src = f.read()
        assert 'FROM audios' not in src
        assert 'from shared.models.database import get_db_session' not in src


class TestAudioAclRepository:
    def test_normalizes_dedupes_and_batches_once(self):
        repo = AudioAclRepository()
        payload = {
            11: {'id': 11, 'name': 'a.wav', 'file_path': 'audios/a.wav'},
            12: {'id': 12, 'name': 'b.wav', 'file_path': 'audios/b.wav'},
        }
        with patch(_ACL_CALL, return_value=payload) as call:
            result = repo.get_audios_by_ids(['11', 11, 12, None, 'abc'])
        call.assert_called_once_with([11, 12])
        assert set(result) == {11, 12}
        assert isinstance(result[11], AudioDTO)
        assert result[11].file_path == 'audios/a.wav'
        assert result[12].name == 'b.wav'

    def test_deleted_audio_absent_from_result(self):
        # audio_service 侧只返回 deleted == False 的记录：软删/不存在的 id 不在 map 中
        repo = AudioAclRepository()
        with patch(_ACL_CALL, return_value={11: {'id': 11, 'file_path': 'a.wav'}}):
            result = repo.get_audios_by_ids([11, 99])
        assert 11 in result
        assert 99 not in result

    def test_empty_input_skips_remote_call(self):
        repo = AudioAclRepository()
        with patch(_ACL_CALL, return_value={}) as call:
            assert repo.get_audios_by_ids([None, 'abc']) == {}
        call.assert_not_called()


class TestFillRoundAudioPaths:
    def test_batches_all_targets_into_one_acl_call(self):
        host = _Host()
        round_cfg = {
            'audios': [{'audio_id': 11}, {'audio_id': '12'}],
            'background_noise': {'audio_id': 13},
            'interferers': [{'audio_id': 12}],
        }
        acl = MagicMock()
        acl.get_audios_by_ids.return_value = {
            11: AudioDTO(id=11, file_path='audios/a.wav'),
            12: AudioDTO(id=12, file_path='audios/b.wav'),
        }
        with patch.object(_acl_pkg, 'audio_acl_repository', acl):
            host._fill_round_audio_paths(round_cfg, task_id=1, test_case_id='tc-1')

        acl.get_audios_by_ids.assert_called_once()
        passed_ids = acl.get_audios_by_ids.call_args.args[0]
        assert {int(x) for x in passed_ids} == {11, 12, 13}
        assert round_cfg['audios'][0]['audio_path'] == 'audios/a.wav'
        assert round_cfg['audios'][1]['audio_path'] == 'audios/b.wav'
        assert round_cfg['interferers'][0]['audio_path'] == 'audios/b.wav'
        assert 'audio_path' not in round_cfg['background_noise']
        warnings = [c for lvl, c in host.logs if lvl == 'WARNING']
        assert len(warnings) == 1 and 'audio_id=13' in warnings[0]

    def test_already_filled_items_skip_remote_call(self):
        host = _Host()
        round_cfg = {'audios': [{'audio_id': 11, 'audio_path': 'keep.wav'}]}
        acl = MagicMock()
        with patch.object(_acl_pkg, 'audio_acl_repository', acl):
            host._fill_round_audio_paths(round_cfg, task_id=1, test_case_id='tc-1')
        acl.get_audios_by_ids.assert_not_called()
        assert round_cfg['audios'][0]['audio_path'] == 'keep.wav'

    def test_missing_file_path_warns_without_filling(self):
        host = _Host()
        round_cfg = {'audios': [{'audio_id': 11}]}
        acl = MagicMock()
        acl.get_audios_by_ids.return_value = {11: AudioDTO(id=11, file_path=None)}
        with patch.object(_acl_pkg, 'audio_acl_repository', acl):
            host._fill_round_audio_paths(round_cfg, task_id=1, test_case_id='tc-1')
        assert 'audio_path' not in round_cfg['audios'][0]
        assert any(lvl == 'WARNING' and 'audio_id=11' in c for lvl, c in host.logs)

    def test_acl_failure_logs_error_and_does_not_raise(self):
        host = _Host()
        round_cfg = {'audios': [{'audio_id': 11}]}
        acl = MagicMock()
        acl.get_audios_by_ids.side_effect = RuntimeError('grpc unavailable')
        with patch.object(_acl_pkg, 'audio_acl_repository', acl):
            host._fill_round_audio_paths(round_cfg, task_id=1, test_case_id='tc-1')
        assert 'audio_path' not in round_cfg['audios'][0]
        assert any(lvl == 'ERROR' and 'grpc unavailable' in c for lvl, c in host.logs)
