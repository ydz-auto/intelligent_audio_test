# -*- coding: utf-8 -*-
"""API 输出字段提取（C0 裁定 §9.2 / §9.3，INT-1747 / C2）。

裁定要点：
- 输出字段声明唯一来源是 ``algorithm_api_params(direction=output)``：
  ``field_path`` 非空按路径从厂商原始响应取值，为空按 ``param_code`` 取
  顶层键（存量行为，零改动）；
- ``apis.meta.result_parser`` / ``asr_mapping`` / ``trans_mapping`` 只在
  该算法类型**一条输出声明都没有**时逐键兜底，不与声明表按字段混用；
- 路径提取统一走 ``shared.utils.path_extractor.extract_by_path``（本卡扩展
  ``a.b[0].c`` 写法），不另建提取器。

单轮（api_task_runner）、多轮（api_session_executor）、Realtime
（realtime_session_executor）三条 API 执行链共用本入口；C1（INT-1746）
在同一入口上完成 ``param_mappings`` 的 ``target_param`` 映射。
"""
from shared.utils.path_extractor import extract_by_path

# 提取来源：声明表 / 零声明时的 meta 解析器兜底 / 两者都没有
SOURCE_DECLARED = 'declared'
SOURCE_META_FALLBACK = 'meta_fallback'
SOURCE_NONE = 'none'

# meta 解析器（result_parser / asr_mapping / trans_mapping）产出的键
META_FALLBACK_KEYS = ('asr', 'trans', 'output')


def get_api_output_field_defs(field_mappings) -> dict:
    """取 ``original.api.output``（param_code → 字段定义）。

    ``field_mappings`` 为 GetFieldMappings 返回的 dict（``original`` /
    ``mapped`` 两段）；结构缺失时返回空 dict（= 该算法类型零输出声明）。
    """
    if not isinstance(field_mappings, dict):
        return {}
    original = field_mappings.get('original') or {}
    if not isinstance(original, dict):
        return {}
    api = original.get('api') or {}
    if not isinstance(api, dict):
        return {}
    output = api.get('output') or {}
    return output if isinstance(output, dict) else {}


def extract_declared_output_fields(api_output_defs: dict, raw_response,
                                   flat_source=None) -> dict:
    """按声明提取，返回 ``{param_code: value}``（字段全集，缺失值为 None）。

    - ``field_path`` 非空：在 ``raw_response``（厂商原始响应）上按路径取值；
    - ``field_path`` 为空：在 ``flat_source`` 上按 ``param_code`` 取顶层键。
      单轮协议把业务数据包在 ``json.data`` 里，调用方传 ``flat_source=data``
      保持存量语义；多轮 / Realtime 的响应无该包装，``flat_source`` 留空即
      用 ``raw_response`` 本身。
    """
    source = flat_source if isinstance(flat_source, dict) else raw_response
    if not isinstance(source, dict):
        source = {}
    values = {}
    for code, definition in (api_output_defs or {}).items():
        field_path = definition.get('field_path') if isinstance(definition, dict) else None
        if field_path:
            values[code] = extract_by_path(raw_response, field_path)
        else:
            values[code] = source.get(code)
    return values


def extract_api_output_fields(field_mappings, raw_response, *,
                              flat_source=None, fallback_values=None):
    """声明驱动提取；零声明时逐键兜底。

    返回 ``(values, source)``，``source`` ∈
    ``SOURCE_DECLARED`` / ``SOURCE_META_FALLBACK`` / ``SOURCE_NONE``。
    走兜底时调用方必须打 WARNING 并列出兜底键（C0 §9.3 优先级 3）。
    """
    defs = get_api_output_field_defs(field_mappings)
    if defs:
        return (extract_declared_output_fields(defs, raw_response, flat_source),
                SOURCE_DECLARED)
    values = {
        key: value for key, value in (fallback_values or {}).items()
        if key in META_FALLBACK_KEYS and value not in (None, '')
    }
    return values, (SOURCE_META_FALLBACK if values else SOURCE_NONE)
