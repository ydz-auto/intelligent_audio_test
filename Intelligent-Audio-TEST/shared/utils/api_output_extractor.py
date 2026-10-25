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
在同一入口上完成 ``param_mappings`` 的 ``target_param`` 映射
（``build_eval_output``），三条链的 ``rounds[i].output`` 因此同构。
"""
from shared.utils.path_extractor import extract_by_path

# 提取来源：声明表 / 零声明时的 meta 解析器兜底 / 两者都没有
SOURCE_DECLARED = 'declared'
SOURCE_META_FALLBACK = 'meta_fallback'
SOURCE_NONE = 'none'

# meta 解析器（result_parser / asr_mapping / trans_mapping）产出的键
META_FALLBACK_KEYS = ('asr', 'trans', 'output')

# 文本型参数类型（声明表 param_type 取值）
TEXT_PARAM_TYPES = ('text', 'string')

# 评估侧从轮次输出取值的参数来源类型（其余由评估侧自行加载）
ROUND_OUTPUT_SOURCES = ('api', 'device')


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


def _is_text_param(definition) -> bool:
    """声明表字段是否为文本型（缺失 param_type 时按文本处理，见调用点）。"""
    if not isinstance(definition, dict):
        return True
    param_type = definition.get('param_type') or definition.get('type')
    return param_type is None or str(param_type).lower() in TEXT_PARAM_TYPES


def extract_declared_output_fields(api_output_defs: dict, raw_response,
                                   flat_source=None, text_output=None,
                                   text_fallback_codes=None) -> dict:
    """按声明提取，返回 ``{param_code: value}``（字段全集，缺失值为 None）。

    - ``field_path`` 非空：在 ``raw_response``（厂商原始响应）上按路径取值；
    - ``field_path`` 为空：在 ``flat_source`` 上按 ``param_code`` 取顶层键。
      单轮协议把业务数据包在 ``json.data`` 里，调用方传 ``flat_source=data``
      保持存量语义；多轮 / Realtime 的响应无该包装，``flat_source`` 留空即
      用 ``raw_response`` 本身。

    ``text_output``（INT-1746）：轮次的规范文本输出（各链自行解析出的回复
    文本）。voice_llm 的回复文本在三条链上的原生键名各不相同（HTTP 为
    ``output`` / WS 为 ``text``），声明表无法用一个 ``field_path`` 同时命中，
    由调用方把规范文本传进来即可同一份声明跨链生效。

    ``text_fallback_codes``：允许取规范文本兜底的 ``param_code`` 集合，只由
    「评估映射实际消费的文本型声明」构成（见 ``_text_fallback_codes``）。
    其他文本声明是会话级展示字段（``session_id`` / ``context_mode`` /
    ``error`` …），给它们兜底会把回复文本写进展示字段，因此不在集合内一律
    不兜底。为空集时不启用兜底。
    """
    source = flat_source if isinstance(flat_source, dict) else raw_response
    if not isinstance(source, dict):
        source = {}
    fallback_codes = set(text_fallback_codes or ())
    values = {}
    for code, definition in (api_output_defs or {}).items():
        field_path = definition.get('field_path') if isinstance(definition, dict) else None
        if field_path:
            values[code] = extract_by_path(raw_response, field_path)
            continue
        value = source.get(code)
        if (value in (None, '') and text_output not in (None, '')
                and code in fallback_codes and _is_text_param(definition)):
            value = text_output
        values[code] = value
    return values


def extract_api_output_fields(field_mappings, raw_response, *,
                              flat_source=None, fallback_values=None,
                              text_output=None):
    """声明驱动提取；零声明时逐键兜底。

    返回 ``(values, source)``，``source`` ∈
    ``SOURCE_DECLARED`` / ``SOURCE_META_FALLBACK`` / ``SOURCE_NONE``。
    走兜底时调用方必须打 WARNING 并列出兜底键（C0 §9.3 优先级 3）。
    """
    defs = get_api_output_field_defs(field_mappings)
    if defs:
        return (extract_declared_output_fields(
                    defs, raw_response, flat_source,
                    text_output=text_output,
                    text_fallback_codes=_text_fallback_codes(field_mappings, defs)),
                SOURCE_DECLARED)
    values = {
        key: value for key, value in (fallback_values or {}).items()
        if key in META_FALLBACK_KEYS and value not in (None, '')
    }
    return values, (SOURCE_META_FALLBACK if values else SOURCE_NONE)


def get_eval_output_mappings(field_mappings) -> dict:
    """取 ``original.evaluation.output``（target_param → 映射条目）。"""
    if not isinstance(field_mappings, dict):
        return {}
    original = field_mappings.get('original') or {}
    if not isinstance(original, dict):
        return {}
    evaluation = original.get('evaluation') or {}
    if not isinstance(evaluation, dict):
        return {}
    output = evaluation.get('output') or {}
    return output if isinstance(output, dict) else {}


def _text_fallback_codes(field_mappings, api_output_defs) -> set:
    """允许用轮次规范文本兜底的 ``param_code`` 集合。

    只覆盖评估映射（``source ∈ api/device``）实际消费、且声明为文本型、
    ``field_path`` 为空的字段。voice_llm 除了回复文本还有一批会话级展示
    声明（``session_id`` / ``context_mode`` / ``error`` …，C3/INT-1748 的
    展示清单），它们不在评估入参里，给它们兜底会把回复文本写成会话字段值。
    """
    codes = set()
    for entry in get_eval_output_mappings(field_mappings).values():
        if not isinstance(entry, dict):
            continue
        if entry.get('source', 'api') not in ROUND_OUTPUT_SOURCES:
            continue
        source_param = entry.get('source_param')
        definition = (api_output_defs or {}).get(source_param)
        if definition is None:
            continue
        field_path = definition.get('field_path') if isinstance(definition, dict) else None
        if field_path or not _is_text_param(definition):
            continue
        codes.add(source_param)
    return codes


def get_output_transform_types(field_mappings) -> dict:
    """取执行侧要应用的 ``{target_param: transform_type}``（INT-1749 / C4）。

    ``transform_type`` 配在 ``param_mappings`` 上，由映射条目带回；只有执行侧
    负责的 source（``api`` / ``device``）才在写 ``rounds[i].output`` 前变换一次，
    ``case`` / ``reference`` 由评估侧按轮自行加载、不在此列（C0 裁定 1）。
    ``none`` / 空值不返回（原值直传），保持改前行为。
    """
    types = {}
    for target, entry in get_eval_output_mappings(field_mappings).items():
        if not isinstance(entry, dict):
            continue
        if entry.get('source', 'api') not in ROUND_OUTPUT_SOURCES:
            continue
        transform_type = entry.get('transform_type')
        if transform_type and str(transform_type).lower() != 'none':
            types[target] = transform_type
    return types


def build_eval_output(field_mappings, api_values, *, log=None):
    """把已提取的 API 输出值按 ``param_mappings`` 映射成 ``{target_param: value}``。

    C0 裁定 1（映射责任在执行侧）：评估侧只按 ``output.get(target_param)``
    取值，因此执行侧产出轮次时就必须换成 ``target_param`` 键。只有
    ``source`` 为 api/device 的映射由执行侧负责（case/reference 由评估侧
    按轮自行加载），其余来源一律跳过。

    键口径（C0 裁定 2 / 卡面结构断言「output 内只有 target_param」）：

    - 配了 api/device 映射的 ``source_param`` **只以 target_param 出现**，
      源键不残留；
    - 没配映射的输出字段（如 voice_llm 的 ``response_audio``）按自身参数名
      输出——``FieldMappingQueryHandler.mapped`` 对无映射字段的 target 就是
      它自己，评估侧 ``output_field_keys`` 与报告展开都按这个键读，丢掉会
      让这些字段在报告里消失。

    零 api/device 映射的老算法（target 6）：全等兜底（source_param 即
    target_param），``log`` 非空时打一条日志，绝不报错。

    ``None`` 值一律不写进输出；映射分支额外丢弃空串（评估侧用 ``None``
    区分「没取到」与「取到空值」，空串会覆盖维度级默认值），全等兜底分支
    保留键与空串——单轮扁平结果「缺声明字段填 ``''``」的存量口径不回归。
    """
    values = {
        key: value for key, value in (api_values or {}).items()
        if value is not None
    }
    mappings = get_eval_output_mappings(field_mappings)
    round_output_entries = {
        target: entry for target, entry in mappings.items()
        if isinstance(entry, dict)
        and entry.get('source', 'api') in ROUND_OUTPUT_SOURCES
    }

    if not round_output_entries:
        # 未配 source='api' 映射：全等兜底（source_param 即 target_param）
        if log is not None:
            log('INFO', '评估映射未配置 source=api/device 条目，'
                        f'按参数名全等映射输出字段: {sorted(values.keys())}')
        return values

    # 被映射走的源键 → 目标键（源键不再以原名出现）
    renamed_sources = {
        entry.get('source_param'): target
        for target, entry in round_output_entries.items()
        if entry.get('source_param')
    }
    output = {
        key: value for key, value in values.items()
        if key not in renamed_sources and value != ''
    }
    for target_param, entry in round_output_entries.items():
        source_param = entry.get('source_param') or target_param
        value = values.get(source_param)
        if value not in (None, ''):
            output[target_param] = value
    return output
