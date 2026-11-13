# -*- coding: utf-8 -*-
"""驱动提案的材料口径与校验（INT-2467，方案 §6.5 / §6.5.1）。

``driver_propose`` 产出**代码提案**（设备驱动 ``AppDriver`` / 厂商 API 适配器
``ApiVendorAdapter``），不执行、不注册、不发布。本模块只放**共享事实**与纯校验，
不做代码生成、不碰沙箱：

- 目标 / 产物枚举：``TARGET_KINDS``（``DEVICE_DRIVER`` / ``API_ADAPTER`` /
  ``PAIR``）、``ARTIFACT_KINDS``；
- 能力画像 ``capabilities.json`` 的字段词表（激励 / 采集 / 时序点 / 结果字段 /
  可计算指标）与**可计算性校验**：声明的指标必须有对应采集模式与时序点支撑，
  否则拒绝（「接入包至少产出一个可计算指标」）；
- UI 探索轨迹 ``ui_trace.json`` 的结构校验：元素定位优先 ``resource_id`` / ``key``，
  退化到 ``text`` 时必须写明 ``fallback_reason``（否则拒绝）；
- 结果字段沿用现有驱动契约（``RESULT_FIELDS``），不另造 schema；
- 指标由 algorithm_service / evaluation_service 计算，驱动只采集文本 / 音频 /
  时序，**不在驱动里算 WER / MOS**（``METRIC_OWNERS`` 仅用于提案说明）。

代码生成与 T2 验证在 ``agent_service/application/driver_proposal_service.py``：
生成结果受本模块校验，校验失败即不产生可发布产物。
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------- 枚举

TARGET_DEVICE_DRIVER = 'DEVICE_DRIVER'
TARGET_API_ADAPTER = 'API_ADAPTER'
TARGET_PAIR = 'PAIR'
TARGET_KINDS: Tuple[str, ...] = (
    TARGET_DEVICE_DRIVER, TARGET_API_ADAPTER, TARGET_PAIR)

#: 每个代码产物带 ``artifact_kind``（§6.5 拍板增补 2）
ARTIFACT_KINDS: Tuple[str, ...] = (TARGET_DEVICE_DRIVER, TARGET_API_ADAPTER)

#: 激励方式（怎么喂）
STIMULUS_MODES: Tuple[str, ...] = (
    'ACOUSTIC_PLAYBACK', 'VIRTUAL_MIC', 'FILE_UPLOAD', 'TEXT_INPUT')

#: 采集方式（怎么收）
CAPTURE_MODES: Tuple[str, ...] = (
    'UI_TEXT', 'SCREEN_RECORD', 'PCM_CAPTURE', 'APP_EXPORT', 'API_RESPONSE')

#: 时序点（怎么对齐）
TIMING_POINTS: Tuple[str, ...] = (
    'PLAYBACK_START', 'PLAYBACK_END', 'FIRST_FRAME', 'FIRST_PARTIAL',
    'FINAL_TEXT', 'FIRST_AUDIO_PACKET', 'REPLY_END')

#: 结果字段：沿用现有驱动契约（§6.5.1），不另造 schema
RESULT_FIELDS: Tuple[str, ...] = (
    'success', 'message', 'asr', 'text', 'question', 'answer', 'wav_path',
    'user_wav', 'ai_wav', 'record_path', 'start_ms', 'end_ms',
    'first_frame_ms', 'latency_ms')

#: 可计算指标（由 algorithm / evaluation 服务计算，驱动不算）
SUPPORTED_METRICS: Tuple[str, ...] = (
    'WER', 'CER', 'SENTENCE_ACC', 'FIRST_TOKEN_LATENCY', 'REPLY_LATENCY',
    'TTS_QUALITY', 'BARGE_IN')

#: 指标归属：驱动只采集，计算在算法 / 评估服务（写进提案的说明）
METRIC_OWNERS: Dict[str, str] = {
    'WER': 'algorithm_service',
    'CER': 'algorithm_service',
    'SENTENCE_ACC': 'algorithm_service',
    'FIRST_TOKEN_LATENCY': 'evaluation_service',
    'REPLY_LATENCY': 'evaluation_service',
    'TTS_QUALITY': 'algorithm_service',
    'BARGE_IN': 'evaluation_service',
}

#: 指标需要的采集方式（任选其一即视为可计算）
METRIC_CAPTURE_REQUIREMENTS: Dict[str, Tuple[str, ...]] = {
    'WER': ('UI_TEXT', 'APP_EXPORT', 'API_RESPONSE', 'SCREEN_RECORD'),
    'CER': ('UI_TEXT', 'APP_EXPORT', 'API_RESPONSE', 'SCREEN_RECORD'),
    'SENTENCE_ACC': ('UI_TEXT', 'APP_EXPORT', 'API_RESPONSE', 'SCREEN_RECORD'),
    'FIRST_TOKEN_LATENCY': ('UI_TEXT', 'APP_EXPORT', 'API_RESPONSE',
                            'PCM_CAPTURE'),
    'REPLY_LATENCY': ('UI_TEXT', 'APP_EXPORT', 'API_RESPONSE', 'PCM_CAPTURE',
                      'SCREEN_RECORD'),
    'TTS_QUALITY': ('SCREEN_RECORD', 'PCM_CAPTURE', 'API_RESPONSE'),
    'BARGE_IN': ('PCM_CAPTURE', 'API_RESPONSE'),
}

#: 指标需要的时序点（任选其一）；没有时序无法出延迟 / 打断类指标
METRIC_TIMING_REQUIREMENTS: Dict[str, Tuple[str, ...]] = {
    'FIRST_TOKEN_LATENCY': ('FIRST_PARTIAL', 'FIRST_AUDIO_PACKET',
                            'FINAL_TEXT'),
    'REPLY_LATENCY': ('REPLY_END', 'FINAL_TEXT'),
    'BARGE_IN': ('PLAYBACK_START', 'PLAYBACK_END'),
}

#: 页面树字段名（两种写法都接受：``pages`` 列表 / ``page_tree`` 对象）
PAGE_TREE_KEYS: Tuple[str, ...] = ('pages', 'page_tree')

#: 元素定位键：稳定标识在前，退化到文本必须写原因
LOCATOR_STABLE_KEYS: Tuple[str, ...] = ('resource_id', 'key')
LOCATOR_TEXT_KEYS: Tuple[str, ...] = ('text', 'label')
LOCATOR_FALLBACK_REASON_KEY = 'fallback_reason'

#: 每个 target_kind 必需的输入材料（缺失即拒绝生成，不当成空值补全）
REQUIRED_INPUTS: Dict[str, Tuple[str, ...]] = {
    TARGET_DEVICE_DRIVER: ('app_type', 'version', 'platform', 'capabilities',
                           'ui_trace'),
    TARGET_API_ADAPTER: ('api_id', 'vendor', 'protocol', 'capabilities',
                         'contract'),
    TARGET_PAIR: ('app_type', 'version', 'platform', 'capabilities',
                  'ui_trace', 'api_id', 'vendor', 'protocol', 'contract'),
}

#: 设备驱动支持的平台（``DevicePlatform`` 的成员名，见 driver_types.py）
DEVICE_PLATFORMS: Tuple[str, ...] = ('ANDROID', 'HARMONYOS', 'IOS')

#: 平台成员名 → 生成的驱动代码里使用的枚举成员（与 DevicePlatform 同名）
PLATFORM_MEMBERS: Dict[str, str] = {name: name for name in DEVICE_PLATFORMS}

#: 适配器协议 → ``APIProtocol`` 传输枚举成员（Realtime 走 WebSocket 传输）
ADAPTER_SUPPORTED_TRANSPORTS: Dict[str, Tuple[str, ...]] = {
    'http': ('HTTP',),
    'websocket': ('WEBSOCKET',),
    'realtime': ('WEBSOCKET',),
    'grpc': ('GRPC',),
}

#: API 适配器协议 / 品牌（``AdapterProtocol`` / ``AdapterVendor`` 的接口取值）
API_ADAPTER_PROTOCOLS: Tuple[str, ...] = (
    'http', 'websocket', 'realtime', 'grpc')
API_ADAPTER_VENDORS: Tuple[str, ...] = ('api_driver', 'mock', 'openai')

CAPABILITY_REQUIRED_KEYS: Tuple[str, ...] = (
    'stimulus_modes', 'capture_modes', 'timing_points', 'result_fields',
    'supported_metrics', 'limitations')


def _string_list(value: Any) -> Optional[List[str]]:
    if value is None:
        return []
    if not isinstance(value, list) or any(
            not isinstance(item, str) for item in value):
        return None
    return [item.strip() for item in value if item.strip()]


def _unknown(values: Sequence[str], allowed: Sequence[str]) -> List[str]:
    return sorted({value for value in values if value not in allowed})


def validate_capabilities(capabilities: Any) -> Optional[str]:
    """校验能力画像；返回错误文本或 ``None``。

    规则（全部确定性，不做语义猜测）：

    1. 必填键齐全，取值都是字符串数组；
    2. 枚举字段的取值在词表内；
    3. 至少一个采集方式；``result_fields`` 必须含 ``success``；
    4. 至少一个可计算指标；每个指标的采集要求与时序要求都满足
       （不满足即拒绝，而不是「声明了却算不出来」）；
    5. ``limitations`` 必须是字符串数组（可为空，但键必须存在）。
    """
    if not isinstance(capabilities, dict):
        return '参数 capabilities 必须是对象（capabilities.json 内容）'
    missing = [key for key in CAPABILITY_REQUIRED_KEYS
               if key not in capabilities]
    if missing:
        return f'capabilities 缺少必填字段：{"、".join(missing)}'

    normalized: Dict[str, List[str]] = {}
    for key in CAPABILITY_REQUIRED_KEYS:
        values = _string_list(capabilities.get(key))
        if values is None:
            return f'capabilities.{key} 必须是字符串数组'
        normalized[key] = values

    for key, allowed in (
            ('stimulus_modes', STIMULUS_MODES),
            ('capture_modes', CAPTURE_MODES),
            ('timing_points', TIMING_POINTS),
            ('result_fields', RESULT_FIELDS),
            ('supported_metrics', SUPPORTED_METRICS)):
        unknown = _unknown(normalized[key], allowed)
        if unknown:
            return f'capabilities.{key} 含未知取值：{"、".join(unknown)}'

    if not normalized['stimulus_modes']:
        return 'capabilities.stimulus_modes 不能为空（至少要说明怎么喂）'
    if not normalized['capture_modes']:
        return 'capabilities.capture_modes 不能为空（至少要说明怎么收）'
    if 'success' not in normalized['result_fields']:
        return 'capabilities.result_fields 必须包含 success'
    if not normalized['supported_metrics']:
        return ('capabilities.supported_metrics 不能为空：'
                '接入包至少产出一个可计算指标（ASR 文本或 TTS 音频 + 时序）')

    captures = set(normalized['capture_modes'])
    timings = set(normalized['timing_points'])
    for metric in normalized['supported_metrics']:
        needs = METRIC_CAPTURE_REQUIREMENTS.get(metric, ())
        if needs and not captures.intersection(needs):
            return (f'指标 {metric} 需要采集方式 {" / ".join(needs)} 之一，'
                    f'当前 capture_modes={sorted(captures)}；'
                    '请改声明或从 supported_metrics 移除该指标')
        timing_needs = METRIC_TIMING_REQUIREMENTS.get(metric, ())
        if timing_needs and not timings.intersection(timing_needs):
            return (f'指标 {metric} 需要时序点 {" / ".join(timing_needs)} 之一，'
                    f'当前 timing_points={sorted(timings)}')
    return None


def normalize_capabilities(capabilities: Dict[str, Any]) -> Dict[str, Any]:
    """把能力画像规整成固定键序（``validate_capabilities`` 通过后调用）。"""
    return {key: list(capabilities.get(key) or ())
            for key in CAPABILITY_REQUIRED_KEYS}


def validate_ui_trace(ui_trace: Any, *, required: bool) -> Optional[str]:
    """校验 UI 探索轨迹（动作序列 + 页面树 + 截图引用）；返回错误文本或 ``None``。

    元素定位优先稳定标识（``resource_id`` / ``key``）；退化到文本定位
    （``text`` / ``label``）时必须记录 ``fallback_reason``，否则拒绝——
    「退化要能解释」是后续驱动可维护性的前提（§6.5 拍板增补 1）。
    """
    if ui_trace is None:
        return ('缺少必填参数：ui_trace（动作序列 + 页面树 + 截图引用）'
                if required else None)
    if not isinstance(ui_trace, dict):
        return '参数 ui_trace 必须是对象（ui_trace.json 内容）'
    actions = ui_trace.get('actions')
    if required or actions is not None:
        if not isinstance(actions, list) or not actions:
            return 'ui_trace.actions 必须是非空数组（动作序列）'
    if required and not any(key in ui_trace for key in PAGE_TREE_KEYS):
        return (f'ui_trace 缺少页面树（{" 或 ".join(PAGE_TREE_KEYS)}）；'
                '设备驱动提案必须带页面结构')
    screenshots = ui_trace.get('screenshots')
    if screenshots is not None and not isinstance(screenshots, list):
        return 'ui_trace.screenshots 必须是数组（截图引用列表）'
    for index, item in enumerate(actions or ()):
        if not isinstance(item, dict):
            return f'ui_trace.actions[{index}] 必须是对象'
        if not str(item.get('action') or item.get('type') or '').strip():
            return f'ui_trace.actions[{index}].action 不能为空'
        locator = item.get('locator')
        if locator is None:
            continue
        if not isinstance(locator, dict):
            return f'ui_trace.actions[{index}].locator 必须是对象'
        stable = [key for key in LOCATOR_STABLE_KEYS if locator.get(key)]
        text_keys = [key for key in LOCATOR_TEXT_KEYS if locator.get(key)]
        if not stable and not text_keys:
            return (f'ui_trace.actions[{index}].locator 必须包含 '
                    f'{" / ".join(LOCATOR_STABLE_KEYS + LOCATOR_TEXT_KEYS)} 之一')
        if not stable and text_keys and not locator.get(
                LOCATOR_FALLBACK_REASON_KEY):
            return (f'ui_trace.actions[{index}].locator 使用文本定位但缺少 '
                    f'{LOCATOR_FALLBACK_REASON_KEY}：请说明为何找不到 '
                    'resource_id / key')
    return None


def locator_report(ui_trace: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """UI 轨迹的定位质量摘要（写进提案，供人工评审判断可维护性）。"""
    actions = (ui_trace or {}).get('actions') or []
    stable = text = none = 0
    fallbacks: List[Dict[str, Any]] = []
    for index, item in enumerate(actions):
        locator = item.get('locator') if isinstance(item, dict) else None
        if not isinstance(locator, dict):
            none += 1
            continue
        if any(locator.get(key) for key in LOCATOR_STABLE_KEYS):
            stable += 1
        elif any(locator.get(key) for key in LOCATOR_TEXT_KEYS):
            text += 1
            fallbacks.append({
                'index': index,
                'reason': locator.get(LOCATOR_FALLBACK_REASON_KEY),
                'locator': {key: locator[key] for key in LOCATOR_TEXT_KEYS
                            if locator.get(key)},
            })
        else:
            none += 1
    return {
        'actions': len(actions),
        'stable_locators': stable,
        'text_locators': text,
        'no_locator': none,
        'text_fallbacks': fallbacks,
    }


def trace_summary(ui_trace: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """UI 轨迹摘要：动作数 / 页面数 / 截图数 / 定位质量 / 内容 hash。"""
    trace = ui_trace or {}
    pages = trace.get('pages')
    page_count = len(pages) if isinstance(pages, list) else (
        1 if isinstance(trace.get('page_tree'), dict) else 0)
    screenshots = trace.get('screenshots')
    canonical = json.dumps(trace, ensure_ascii=False, sort_keys=True,
                           separators=(',', ':'), default=str)
    return {
        'sha256': hashlib.sha256(canonical.encode('utf-8')).hexdigest(),
        'actions': len(trace.get('actions') or ()),
        'pages': page_count,
        'screenshots': len(screenshots) if isinstance(screenshots, list) else 0,
        'locators': locator_report(trace),
    }


def validate_target_inputs(target_kind: str,
                           arguments: Dict[str, Any]) -> Optional[str]:
    """按 ``target_kind`` 检查材料是否齐全（缺失当面说，不用假设值补全）。"""
    if target_kind not in TARGET_KINDS:
        return f'参数 target_kind 取值必须是 {"/".join(TARGET_KINDS)} 之一'
    missing = [name for name in REQUIRED_INPUTS[target_kind]
               if arguments.get(name) in (None, '')]
    if missing:
        return (f'target_kind={target_kind} 缺少材料：{"、".join(missing)}'
                '；缺材料时请先补齐，不要用假设值生成提案')
    return None


def check_platform(platform: Any) -> Optional[str]:
    value = str(platform or '').upper()
    if value not in DEVICE_PLATFORMS:
        return (f'参数 platform 取值必须是 {"/".join(DEVICE_PLATFORMS)} 之一'
                f'（收到 {platform!r}）')
    return None


def check_adapter_dimensions(protocol: Any, vendor: Any) -> Optional[str]:
    protocol_value = str(protocol or '').lower()
    if protocol_value not in API_ADAPTER_PROTOCOLS:
        return (f'参数 protocol 取值必须是 {"/".join(API_ADAPTER_PROTOCOLS)} 之一'
                f'（收到 {protocol!r}）')
    vendor_value = str(vendor or '').lower()
    if vendor_value not in API_ADAPTER_VENDORS:
        return (f'参数 vendor 取值必须是 {"/".join(API_ADAPTER_VENDORS)} 之一'
                f'（收到 {vendor!r}）')
    return None


__all__ = [
    'API_ADAPTER_PROTOCOLS', 'API_ADAPTER_VENDORS', 'ARTIFACT_KINDS',
    'CAPABILITY_REQUIRED_KEYS', 'CAPTURE_MODES', 'DEVICE_PLATFORMS',
    'LOCATOR_FALLBACK_REASON_KEY', 'LOCATOR_STABLE_KEYS', 'LOCATOR_TEXT_KEYS',
    'METRIC_CAPTURE_REQUIREMENTS', 'METRIC_OWNERS', 'METRIC_TIMING_REQUIREMENTS',
    'ADAPTER_SUPPORTED_TRANSPORTS', 'PAGE_TREE_KEYS', 'PLATFORM_MEMBERS',
    'REQUIRED_INPUTS', 'RESULT_FIELDS', 'STIMULUS_MODES',
    'SUPPORTED_METRICS', 'TARGET_API_ADAPTER', 'TARGET_DEVICE_DRIVER',
    'TARGET_KINDS', 'TARGET_PAIR', 'TIMING_POINTS', 'check_adapter_dimensions',
    'check_platform', 'locator_report', 'normalize_capabilities',
    'trace_summary', 'validate_capabilities', 'validate_target_inputs',
    'validate_ui_trace',
]
