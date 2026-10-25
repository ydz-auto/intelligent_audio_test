# -*- coding: utf-8 -*-
"""API 响应解析预览（INT-1772）—— 纯函数实现。

前端「响应解析」页签要「贴一段样例响应 → 看按 meta 解析器能提取出什么」。
本模块不读库、不发任何外部请求、不写文件、不落缓存，可在路由/单测里直接调。

口径与执行期同一份实现（``api_test_service/infrastructure/adapters/
api_driver_adapter.py``），路径提取一律走
``shared.utils.path_extractor.extract_by_path``，不另写解析：

- ``result_parser``（voice_llm，与 ``_parse_voice_llm_response`` 同形：
  ``asr_text_path`` / ``trans_text_path`` / ``session_id_path``）在**完整**
  响应上取值；
- ``asr_mapping`` / ``trans_mapping`` / ``sentence_end_mapping`` /
  ``session_end_mapping`` 与 ``_parse_response`` 同口径：在
  ``resp.get('data', resp)`` 上取值（标准信封 ``{"code": 0, "data": {...}}``
  会先解包，不以 ``data.`` 开头写路径）；
- ``error_code_mapping`` / ``error_msg_mapping`` 同 ``_parse_response``：
  在**完整**响应上取值。

``extracted`` 的键就是请求里的配置字段名（``result_parser`` 取其内部键），
前端可把每项值贴回对应输入项旁；取到的值为 ``None``（路径不存在 / 下标
越界 / 中间层类型不符）即进 ``unresolved``，不静默丢。
"""
import json

from shared.utils.path_extractor import extract_by_path, is_valid_path

RESULT_PARSER = 'result_parser'

# 执行期在 ``resp.get('data', resp)`` 上取值的映射（文本 / 结束标志）
TEXT_MAPPING_FIELDS = (
    'asr_mapping',
    'trans_mapping',
    'sentence_end_mapping',
    'session_end_mapping',
)

# 执行期在完整响应上取值的映射（业务错误码 / 错误信息）
ERROR_MAPPING_FIELDS = (
    'error_code_mapping',
    'error_msg_mapping',
)

MAPPING_FIELDS = TEXT_MAPPING_FIELDS + ERROR_MAPPING_FIELDS


class ParsePreviewError(ValueError):
    """请求不可用于预览；路由层按 400 返回，message 直接展示给前端。"""


def _decode_sample(value):
    """样例响应归一。

    - 对象 / 数组：直接作为提取数据；
    - 字符串：按 JSON 试解析，解析成对象/数组则用解析结果，否则按厂商原始
      文本处理（执行期 ``resp_info['json']`` 为空才走文本兜底，这里没有可
      提取的路径，由所有路径进 ``unresolved`` 表达，不报错）；
    - 其余（数字 / 布尔 / null）：既不是 JSON 对象也不是字符串 → 400。
    """
    if value is None:
        raise ParsePreviewError('缺少 sample_response（样例响应）')
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return value
        return parsed if isinstance(parsed, (dict, list)) else value
    raise ParsePreviewError('sample_response 必须是 JSON 对象/数组或原始字符串')


def _check_path(path, field):
    """路径必须是合法写法的字符串（非法写法 → 400，不与「没命中」混淆）。"""
    if not isinstance(path, str):
        raise ParsePreviewError(
            f'{field} 必须是路径字符串（如 data.events[0].text）')
    if not is_valid_path(path):
        raise ParsePreviewError(
            f'{field} 路径写法非法: {path!r}'
            '（只支持点号 + 数字下标，数字下标可写 a.b.0.c 或 a.b[0].c）')


def _record(key, path, value, extracted, unresolved):
    """命中写入 ``extracted``；未命中把路径记进 ``unresolved``（去重保序）。"""
    if value is None:
        if path not in unresolved:
            unresolved.append(path)
        return
    extracted[key] = value


def build_preview(payload):
    """把请求体算成 ``{'extracted': {...}, 'unresolved': [...]}``。

    ``payload`` 为已解析的 JSON 请求体；不合法时抛 :class:`ParsePreviewError`
    （路由层转 400）。空字符串路径 = 未配置，跳过；``None`` 同样跳过。
    """
    if not isinstance(payload, dict):
        raise ParsePreviewError('请求体不能为空或不是合法 JSON 对象')

    if 'sample_response' not in payload:
        raise ParsePreviewError('缺少 sample_response（样例响应）')
    sample = _decode_sample(payload['sample_response'])

    # 执行期口径：文本 / 结束标志映射在解包后的业务数据上取值
    unwrapped = sample.get('data', sample) if isinstance(sample, dict) else sample

    extracted = {}
    unresolved = []

    parser = payload.get(RESULT_PARSER)
    if parser is not None:
        if not isinstance(parser, dict):
            raise ParsePreviewError(
                'result_parser 必须是对象（与 meta.result_parser 同形，'
                '如 {"asr_text_path": "data.text"}）')
        for key, path in parser.items():
            if path is None or path == '':
                continue
            field = f'{RESULT_PARSER}.{key}'
            _check_path(path, field)
            _record(key, path, extract_by_path(sample, path),
                    extracted, unresolved)

    for field in MAPPING_FIELDS:
        path = payload.get(field)
        if path is None or path == '':
            continue
        _check_path(path, field)
        scope = unwrapped if field in TEXT_MAPPING_FIELDS else sample
        _record(field, path, extract_by_path(scope, path),
                extracted, unresolved)

    return {'extracted': extracted, 'unresolved': unresolved}
