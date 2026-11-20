# -*- coding: utf-8 -*-
"""INT-2467 写意图工具注册与解析（音频 / 设备 / SPL / 驱动提案）。

验证锚点：
- 5 个 M2 写工具已登记且启用，风险等级与 §6.1 一致；
- 动作 → 目标 REST 的映射 / 参数白名单 / 动作级权限与网关真实路由一致；
- 写工具不映射 REST 的（driver_propose）走本地实现；
- 参数不合法在提案前就被拒绝（不会生成注定 422 的提案）。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.agent_tools import audio_tools, device_tools, driver_tools, intent_tools
from shared.agent_tools import mcp_registry


def _tool(name):
    return intent_tools.INTENT_TOOL_BY_NAME[name]


# ---------------------------------------------------------------- 注册与风险

def test_m2_write_tools_registered_and_enabled():
    expected = {
        'audio_import': 'WRITE',
        'audio_annotate': 'WRITE',
        'device_control': 'DESTRUCTIVE',
        'spl_calibrate': 'WRITE',
        'driver_propose': 'WRITE',
    }
    for name, risk in expected.items():
        tool = _tool(name)
        assert tool.enabled is True, name
        assert tool.risk == risk, name
        assert name in intent_tools.ENABLED_TOOLS
        assert name in intent_tools.TOOL_INDEX_BY_NAME, name


def test_write_action_tools_are_the_four_rest_tools():
    assert intent_tools.WRITE_ACTION_TOOL_NAMES == {
        'audio_import', 'audio_annotate', 'device_control', 'spl_calibrate'}
    # driver_propose 是本地工具（代码生成 + T2），不映射 REST
    assert 'driver_propose' in intent_tools.LOCAL_INTENT_TOOL_NAMES
    tool, merged, error = intent_tools.resolve_rest_call(
        'driver_propose', {'target_kind': 'DEVICE_DRIVER'})
    assert tool is None and merged is None and '本地实现' in error


# ---------------------------------------------------------------- 音频

def test_audio_import_resolves_to_mcp_write_tools():
    tool, merged, error = intent_tools.resolve_write_call(
        'audio_import', {'action': 'url_import', 'url': ' http://a/b.wav ',
                         'audio_type': 'dry'})
    assert error is None
    assert tool['name'] == mcp_registry.get_tool('audio_url_import')['name']
    assert tool['method'] == 'POST'
    assert tool['path'] == '/api/v1/audios/url-import'
    assert merged == {'body': {'url': 'http://a/b.wav', 'audio_type': 'dry'}}

    tool, merged, error = intent_tools.resolve_write_call(
        'audio_import', {'action': 'upload_init'})
    assert error is None and merged == {}
    assert tool['path'] == '/api/v1/audios/upload/init'


def test_audio_import_merge_requires_body_keys():
    _t, _m, error = intent_tools.resolve_write_call(
        'audio_import', {'action': 'upload_merge', 'body': {'file_id': 'f1'}})
    assert error and 'task_id' in error


def test_audio_annotate_update_meta_uses_path_param():
    tool, merged, error = intent_tools.resolve_write_call(
        'audio_annotate', {'action': 'update_meta', 'audio_id': 9,
                           'metadata': {'name': 'n', 'tags': 'a,b'}})
    assert error is None
    assert tool['path'] == '/api/v1/audios/{audio_id}/metadata'
    assert merged == {'audio_id': 9, 'body': {'name': 'n', 'tags': 'a,b'}}


def test_audio_annotate_rejects_unknown_metadata_and_bad_items():
    _t, _m, error = intent_tools.resolve_write_call(
        'audio_annotate', {'action': 'update_meta', 'audio_id': 9,
                           'metadata': {'unknown_field': 1}})
    assert error and '不支持字段' in error

    _t, _m, error = intent_tools.resolve_write_call(
        'audio_annotate', {'action': 'update_meta', 'audio_id': 9,
                           'metadata': {'tags': ['a']}})
    assert error and 'tags 必须是字符串' in error

    _t, _m, error = intent_tools.resolve_write_call(
        'audio_annotate', {'action': 'batch_annotate',
                           'items': [{'audio_id': 0}]})
    assert error and 'audio_id 必须是正整数' in error


def test_audio_annotate_set_algorithms_validates_items():
    _t, merged, error = intent_tools.resolve_write_call(
        'audio_annotate', {'action': 'set_algorithms', 'audio_id': 3,
                           'algorithms': [{'algorithm_type': 'asr'}]})
    assert error is None
    assert merged['body'] == {'algorithms': [{'algorithm_type': 'asr'}]}

    _t, _m, error = intent_tools.resolve_write_call(
        'audio_annotate', {'action': 'set_algorithms', 'audio_id': 3,
                           'algorithms': [{'is_primary': True}]})
    assert error and 'algorithm_type 不能为空' in error


def test_audio_write_permissions():
    assert intent_tools.permissions_for(
        'audio_import', {'action': 'url_import'}) == ('audio:upload',)
    assert intent_tools.permissions_for(
        'audio_annotate', {'action': 'batch_annotate'}) == ('audio:update',)


# ---------------------------------------------------------------- 设备

def test_device_control_maps_every_action():
    assert set(device_tools.DEVICE_CONTROL_ACTIONS) == {
        'connect', 'disconnect', 'reboot', 'shutdown', 'install',
        'uninstall', 'scan', 'batch'}
    for action, mcp_name in device_tools.DEVICE_CONTROL_ACTIONS.items():
        assert mcp_registry.get_tool(mcp_name) is not None, (action, mcp_name)


def test_device_control_batch_renames_operation_to_action():
    tool, merged, error = intent_tools.resolve_write_call(
        'device_control', {'action': 'batch', 'operation': 'reboot',
                           'device_ids': [1, 2], 'idempotency_key': 'k1'})
    assert error is None
    assert tool['path'] == '/api/v1/test-devices/batch'
    assert merged == {'body': {'action': 'reboot', 'device_ids': [1, 2],
                               'idempotency_key': 'k1'}}


def test_device_control_install_requires_file_path():
    _t, _m, error = intent_tools.resolve_write_call(
        'device_control', {'action': 'install', 'device_id': 1, 'params': {}})
    assert error and 'file_path' in error

    _t, merged, error = intent_tools.resolve_write_call(
        'device_control', {'action': 'install', 'device_id': 1,
                           'params': {'file_path': '/tmp/a.apk'}})
    assert error is None
    assert merged == {'device_id': 1, 'params': {'file_path': '/tmp/a.apk'}}


def test_device_control_scan_takes_no_params():
    _t, merged, error = intent_tools.resolve_write_call(
        'device_control', {'action': 'scan'})
    assert error is None and merged == {}
    _t, _m, error = intent_tools.resolve_write_call(
        'device_control', {'action': 'scan', 'device_id': 3})
    assert error and '不支持参数' in error


def test_device_control_unknown_action_and_bad_batch_operation():
    _t, _m, error = intent_tools.resolve_write_call(
        'device_control', {'action': 'destroy'})
    assert error and 'action 取值必须是' in error
    _t, _m, error = intent_tools.resolve_write_call(
        'device_control', {'action': 'batch', 'operation': 'format',
                           'device_ids': [1]})
    assert error and 'operation 取值必须是' in error


def test_device_control_permissions_are_control():
    assert intent_tools.permissions_for(
        'device_control', {'action': 'reboot'}) == ('device:control',)


# ---------------------------------------------------------------- SPL

def test_spl_calibrate_resolves_all_targets():
    for action, target in device_tools.SPL_CALIBRATE_TARGETS.items():
        assert target['method'] in ('POST', 'PUT', 'DELETE'), action
        assert target['path'].startswith('/api/v1/spl') or \
            target['path'].startswith('/api/v1/digital-spl'), action


def test_spl_calibrate_mapping_create_requires_device():
    _t, _m, error = intent_tools.resolve_write_call(
        'spl_calibrate', {'action': 'mapping_create', 'name': 'm1'})
    assert error and 'device_id' in error

    tool, merged, error = intent_tools.resolve_write_call(
        'spl_calibrate', {'action': 'mapping_create', 'name': 'm1',
                          'device_id': 4, 'distance': 1.5})
    assert error is None
    assert tool['path'] == '/api/v1/spl'
    assert merged == {'name': 'm1', 'device_id': 4, 'distance': 1.5}


def test_spl_calibrate_calibrate_uses_path_param():
    tool, merged, error = intent_tools.resolve_write_call(
        'spl_calibrate', {'action': 'calibrate', 'mapping_id': 7})
    assert error is None
    assert tool['path'] == '/api/v1/spl/{mapping_id}/calibrate'
    assert merged == {'mapping_id': 7}


def test_spl_calibrate_permissions_narrow_by_action():
    assert intent_tools.permissions_for(
        'spl_calibrate', {'action': 'mapping_delete'}) == ('spl:delete',)
    assert intent_tools.permissions_for(
        'spl_calibrate', {'action': 'test_tone'}) == ('spl:test_tone',)
    assert intent_tools.permissions_for(
        'spl_calibrate', {'action': 'digital_calibrate'}) == \
        ('digital_spl:create',)


# ---------------------------------------------------------------- 统一校验

@pytest.mark.parametrize('name,arguments', [
    ('audio_import', {'action': 'url_import'}),
    ('device_control', {'action': 'reboot'}),
    ('spl_calibrate', {'action': 'calibrate'}),
])
def test_validate_write_arguments_reports_missing(name, arguments):
    error = intent_tools.validate_write_arguments(name, arguments)
    assert error and '缺少必填参数' in error


def test_validate_write_arguments_ignores_non_write_tools():
    assert intent_tools.validate_write_arguments(
        'audio_query', {'action': 'list'}) is None


def test_driver_capability_metrics_must_be_computable():
    base = {
        'stimulus_modes': ['ACOUSTIC_PLAYBACK'],
        'capture_modes': ['UI_TEXT'],
        'timing_points': ['PLAYBACK_START', 'FINAL_TEXT'],
        'result_fields': ['success', 'asr', 'text'],
        'supported_metrics': ['WER'],
        'limitations': [],
    }
    assert driver_tools.validate_capabilities(base) is None
    # 只有 UI 文本却声明 TTS 音质 → 拒绝（只能取文本时不能评 TTS 音质）
    tts = dict(base, supported_metrics=['TTS_QUALITY'])
    assert 'TTS_QUALITY' in driver_tools.validate_capabilities(tts)
    # 延迟指标需要时序点
    latency = dict(base, supported_metrics=['FIRST_TOKEN_LATENCY'],
                   timing_points=[])
    assert 'FIRST_TOKEN_LATENCY' in driver_tools.validate_capabilities(latency)
    # 没有可计算指标 → 拒绝
    none_metric = dict(base, supported_metrics=[])
    assert '至少产出一个可计算指标' in driver_tools.validate_capabilities(
        none_metric)


def test_ui_trace_text_locator_requires_reason():
    trace = {'actions': [{'action': 'tap', 'locator': {'text': '发送'}}],
             'pages': [{'name': 'chat'}]}
    assert 'fallback_reason' in driver_tools.validate_ui_trace(
        trace, required=True)
    trace['actions'][0]['locator']['fallback_reason'] = '控件无 resource_id'
    assert driver_tools.validate_ui_trace(trace, required=True) is None
    stable = {'actions': [{'action': 'tap',
                           'locator': {'resource_id': 'com.x:id/btn'}}],
              'pages': []}
    assert driver_tools.validate_ui_trace(stable, required=True) is None
