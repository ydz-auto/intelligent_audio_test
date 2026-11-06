# -*- coding: utf-8 -*-
"""INT-2410 设备结果字段名口径修正：stm_res/rttm_res → stm_hyp/rttm_hyp。

对齐 V9.7.10 `59b5a003c`：设备驱动 `extract_results_from_archive` 输出的两个
结果 key 改用评估侧规范名 `*_hyp`（eval_server der_calculator / wer strategies
均以 hyp 为必填入参），不保留 `*_res` 旧名、不写兼容层。

覆盖：
1. 驱动输出：`PlaudDriver.extract_results_from_archive` 返回 dict 含
   `stm_hyp` / `rttm_hyp`，不含 `stm_res` / `rttm_res`，且其余内容字段保留。
2. `AlgorithmQueryACLRepository.convert_device_output` 在映射配置
   `source_param='stm_hyp'` 时能取到值（不连真实 gRPC 服务）。
3. 报告侧 `param_type` 关键字推断：`stm_hyp` → `stm`、`rttm_hyp` → `rttm`。
4. `RttmStmUtils` 两条取值策略（配置 code 命中 / `*_content` 后缀兜底）在改名后都不断链。
"""
import os
from unittest.mock import MagicMock, patch

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from device_service.infrastructure.acl.algorithm_query_acl_repository import (
    AlgorithmQueryACLRepository,
)
from device_service.infrastructure.drivers import android_plaud
from device_service.infrastructure.drivers.android_plaud import PlaudDriver
from device_service.domain.services.rttm_stm_utils import RttmStmUtils
from report_service.application.services.report_helpers import ReportHelpers

# 最小 SRT：两个说话人、两段，足以让 _parse_srt_to_stm_rttm 生成 stm/rttm/asr
_MIN_SRT = """1
00:00:01,000 --> 00:00:02,500
Speaker 1:你好世界

2
00:00:03,000 --> 00:00:04,200
Speaker 2:测试完成
"""


def _make_driver():
    """绕过 __init__ 的配置/设备依赖，只挂一个 _log 替身。"""
    driver = PlaudDriver.__new__(PlaudDriver)
    driver._log = MagicMock()
    return driver


class TestExtractResultsFromArchiveKeys:
    def test_returns_hyp_keys_without_legacy_res_keys(self):
        def _fake_load_file(path, local_path=None, allow_fallback=True):
            with open(local_path, 'w', encoding='utf-8') as f:
                f.write(_MIN_SRT)
            return local_path

        driver = _make_driver()
        with patch.object(android_plaud.storage, 'load_file', side_effect=_fake_load_file), \
                patch.object(android_plaud.storage, 'save_file', return_value='oss://case_result/x'):
            results = driver.extract_results_from_archive(
                task_id=101, test_case_id=202, device_sn='SN-INT-2410')

        assert isinstance(results, list) and len(results) == 1
        result = results[0]

        assert result['success'] is True
        # 新口径 key
        assert result['stm_hyp'] == result['recording_stm_content']
        assert result['rttm_hyp'] == result['recording_rttm_content']
        assert result['stm_hyp'], 'STM 内容不应为空'
        assert result['rttm_hyp'], 'RTTM 内容不应为空'
        # 旧口径 key 不得保留
        assert 'stm_res' not in result
        assert 'rttm_res' not in result
        # 其余内容字段保留
        for key in ('recording_stm_content', 'recording_rttm_content',
                    'recording_asr_content', 'asr_result'):
            assert key in result
            assert result[key]
        assert '你好世界' in result['stm_hyp']
        assert 'SPEAKER' in result['rttm_hyp']


class TestConvertDeviceOutputSourceParam:
    def _repo_with_mapping(self, source_param, target_param):
        repo = AlgorithmQueryACLRepository()
        mapping = {
            'original': {
                'device': {
                    'output': {
                        source_param: {'code': source_param},
                    }
                }
            },
            'mapped': {
                'device': {
                    target_param: {
                        'code': target_param,
                        'source_param': source_param,
                        'component_type': 'device',
                    }
                }
            },
        }
        repo.get_field_mappings = MagicMock(return_value=mapping)
        return repo

    def test_stm_hyp_source_param_maps_into_target(self):
        repo = self._repo_with_mapping('stm_hyp', 'stm_hyp')
        device_result = {
            'success': True,
            'stm_hyp': '正一 1 1 speaker1 0.000 1.000 你好世界',
        }

        mapped = repo.convert_device_output('plaud_asr', device_result)

        assert mapped.get('stm_hyp') == device_result['stm_hyp']

    def test_rttm_hyp_source_param_maps_into_target(self):
        repo = self._repo_with_mapping('rttm_hyp', 'rttm_hyp')
        device_result = {
            'success': True,
            'rttm_hyp': 'SPEAKER 正一 1 1.000 0.500 <NA> <NA> speaker1 <NA>',
        }

        mapped = repo.convert_device_output('plaud_asr', device_result)

        assert mapped.get('rttm_hyp') == device_result['rttm_hyp']


class TestReportParamTypeInference:
    @pytest.mark.parametrize('param_code,expected', [
        ('stm_hyp', 'stm'),
        ('rttm_hyp', 'rttm'),
    ])
    def test_hyp_keys_infer_expected_param_type(self, param_code, expected):
        assert ReportHelpers._infer_param_type(param_code) == expected


class TestRttmStmUtilsConsumesRenamedKeys:
    """rttm_stm_utils 两条取值策略在改名后都不断链。"""

    def test_strategy1_config_code_hits_hyp_key(self):
        field_query = MagicMock()
        field_query.get_device_output_field_codes_by_type.side_effect = (
            lambda algorithm_type, param_type, device_id=None: [f'{param_type}_hyp'])
        utils = RttmStmUtils(field_query_service=field_query)

        stm, rttm = utils._get_stm_rttm_content_from_result(
            {'stm_hyp': 'STM-NEW', 'rttm_hyp': 'RTTM-NEW'},
            algorithm_type='plaud_asr')

        assert (stm, rttm) == ('STM-NEW', 'RTTM-NEW')

    def test_strategy2_content_suffix_fallback_still_hits(self):
        # 配置仍指向旧 code 时策略 1 落空，策略 2 按 *_stm_content / *_rttm_content
        # 后缀兜底——这两个字段本次改名未动。
        field_query = MagicMock()
        field_query.get_device_output_field_codes_by_type.return_value = []
        utils = RttmStmUtils(field_query_service=field_query)

        stm, rttm = utils._get_stm_rttm_content_from_result(
            {'stm_hyp': 'STM-NEW', 'rttm_hyp': 'RTTM-NEW',
             'recording_stm_content': 'STM-CONTENT',
             'recording_rttm_content': 'RTTM-CONTENT'},
            algorithm_type='plaud_asr')

        assert (stm, rttm) == ('STM-CONTENT', 'RTTM-CONTENT')

