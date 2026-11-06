# -*- coding: utf-8 -*-
"""INT-2269 设备结果转换的设备级作用域单测。

背景：``DeviceResultCollector.convert_results`` / ``build_case_result_log``
早先按 ``res.get('_device_id')`` 取设备作用域，但采集行（``collect_raw_results``
/ ``collect_round_results`` 构造的 ``{'device_id': ...}``）以及 e2e
``CollectedResultDTO.device_id`` 用的键都是 ``device_id``，``_device_id``
只写在 ``raw_results`` 内层（轮次标记），外层结果行永远取不到值 ——
设备级输出映射与设备级 query_fields 在真机链路从未生效。

本测试锁定：
1. 采集行携带 ``device_id`` 时，映射查询按该设备作用域取值；
2. 未携带 ``device_id`` 时回落算法级（device_id=None）；
3. ``collect_round_results`` → ``convert_results`` 的轮次链路同样生效；
4. ``build_case_result_log`` 的字段键与 query_fields 也按设备作用域。
"""
import os
from types import SimpleNamespace

# shared.infrastructure.config 在导入期强校验；单测不连 OSS，给占位值
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from device_service.domain.services.device_result_collector import DeviceResultCollector  # noqa: E402

ALGO = 'asha_llm'
DEVICE_WITH_OVERRIDE = 501
DEVICE_WITHOUT_OVERRIDE = 502


class _FakeFieldQuery:
    """字段查询桩：设备 501 配置了设备级输出映射，其余走算法级默认。"""

    def __init__(self):
        self.mapped_calls = []
        self.convert_calls = []
        self.keys_calls = []
        self.extra_calls = []

    @staticmethod
    def _target(device_id):
        return 'device_asha_text' if device_id == DEVICE_WITH_OVERRIDE else 'algo_asha_text'

    def get_mapped_device_output_fields(self, algorithm_type, device_id=None):
        self.mapped_calls.append((algorithm_type, device_id))
        return [SimpleNamespace(
            code=self._target(device_id), source_param='asha_text', dimension_id=None)]

    def convert_device_output(self, algorithm_type, device_result, device_id=None):
        self.convert_calls.append((algorithm_type, device_id))
        value = (device_result or {}).get('asha_text')
        if value is None:
            return {}
        return {self._target(device_id): value}

    def get_mapped_device_output_field_keys(self, algorithm_type, device_id=None):
        self.keys_calls.append((algorithm_type, device_id))
        return [self._target(device_id)]

    def get_algorithm_extra_config(self, algorithm_type, device_id=None):
        self.extra_calls.append((algorithm_type, device_id))
        if device_id == DEVICE_WITH_OVERRIDE:
            return {'query_fields': {'device_query_field': {}}}
        return {'query_fields': {}}


class _FakeDriver:
    """设备驱动桩：返回单条带 asha_text 的结果。"""

    def __init__(self, text):
        self.text = text

    def get_results(self, device_sn, task_id=None, test_case_id=None):
        return [{'success': True, 'asha_text': self.text}]


def _row(device_id, text):
    row = {
        'device_name': f'设备{device_id}',
        'device_sn': f'SN-{device_id}',
        'raw_results': {'success': True, 'asha_text': text},
    }
    if device_id is not None:
        row['device_id'] = device_id
    return row


def test_convert_results_uses_device_level_mapping_when_configured():
    """设备级输出映射覆盖算法级：设备 501 命中设备级 target。"""
    fake = _FakeFieldQuery()
    collector = DeviceResultCollector(field_query_service=fake)

    converted = collector.convert_results(
        [_row(DEVICE_WITH_OVERRIDE, '设备级文本'),
         _row(DEVICE_WITHOUT_OVERRIDE, '算法级文本')],
        ALGO,
    )

    assert fake.mapped_calls == [(ALGO, DEVICE_WITH_OVERRIDE), (ALGO, DEVICE_WITHOUT_OVERRIDE)]
    assert fake.convert_calls == [(ALGO, DEVICE_WITH_OVERRIDE), (ALGO, DEVICE_WITHOUT_OVERRIDE)]

    assert converted[0]['device_asha_text'] == '设备级文本'
    assert 'algo_asha_text' not in converted[0]
    assert converted[0]['success'] is True

    assert converted[1]['algo_asha_text'] == '算法级文本'
    assert 'device_asha_text' not in converted[1]


def test_convert_results_falls_back_to_algorithm_scope_without_device_id():
    """结果行未携带设备键时回落算法级（device_id=None），不按设备解析。"""
    fake = _FakeFieldQuery()
    collector = DeviceResultCollector(field_query_service=fake)

    converted = collector.convert_results([_row(None, '无设备文本')], ALGO)

    assert fake.mapped_calls == [(ALGO, None)]
    assert fake.convert_calls == [(ALGO, None)]
    assert converted[0]['algo_asha_text'] == '无设备文本'


def test_round_results_keep_device_scope_through_conversion():
    """collect_round_results → convert_results 的轮次链路保留设备作用域。"""
    fake = _FakeFieldQuery()
    collector = DeviceResultCollector(field_query_service=fake)
    device_info_list = [{
        'device_id': DEVICE_WITH_OVERRIDE,
        'device_name': '设备501',
        'device_sn': 'SN-ROUND',
        'driver': _FakeDriver('轮次设备文本'),
    }]

    rows = collector.collect_round_results(
        'task-1', 1, device_info_list, round_idx=0,
        round_config={}, round_start_time=0.0,
    )
    assert rows[0]['device_id'] == DEVICE_WITH_OVERRIDE

    converted = collector.convert_results(rows, ALGO)

    assert fake.mapped_calls == [(ALGO, DEVICE_WITH_OVERRIDE)]
    assert fake.convert_calls == [(ALGO, DEVICE_WITH_OVERRIDE)]
    assert converted[0]['device_asha_text'] == '轮次设备文本'
    assert converted[0]['success'] is True


def test_build_case_result_log_uses_device_scope():
    """结果日志的字段键与 query_fields 按设备作用域取值。"""
    fake = _FakeFieldQuery()
    collector = DeviceResultCollector(field_query_service=fake)

    res = {
        'device_id': DEVICE_WITH_OVERRIDE,
        'device_name': '设备501',
        'success': True,
        'device_asha_text': '日志设备值',
    }
    log_content = collector.build_case_result_log(
        ALGO, res, {'参考文本': 'hello'}, device_query_field='额外值')

    assert fake.keys_calls == [(ALGO, DEVICE_WITH_OVERRIDE)]
    assert fake.extra_calls == [(ALGO, DEVICE_WITH_OVERRIDE)]
    assert 'device_asha_text: 日志设备值' in log_content
    assert 'device_query_field: 额外值' in log_content


def test_build_case_result_log_falls_back_to_algorithm_scope():
    """无设备键时日志按算法级字段取键，不出现设备级 query_fields。"""
    fake = _FakeFieldQuery()
    collector = DeviceResultCollector(field_query_service=fake)

    log_content = collector.build_case_result_log(
        ALGO, {'device_name': '未知设备', 'algo_asha_text': '算法级日志'})

    assert fake.keys_calls == [(ALGO, None)]
    assert fake.extra_calls == [(ALGO, None)]
    assert 'algo_asha_text: 算法级日志' in log_content
    assert 'device_query_field' not in log_content
