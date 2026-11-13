# -*- coding: utf-8 -*-
"""用例域只读工具与草案推导（INT-2460，M1）。

本模块补两块 ``mcp_registry`` 没有覆盖的用例只读能力，并承载
``testcase_generate`` 的**纯函数**推导（不落库、不碰数据库）：

1. ``TESTCASE_READ_TOOLS``：网关已有、但外部 MCP 表未登记的用例只读路由
   （用例统计、轮次参考参数、导出作业状态、参考参数刷新状态）。工具项形状
   与 ``mcp_registry`` 完全一致，复用同一 ``build_path`` / ``build_body``
   构造器，不复制第二套参数口径。**不并入** ``mcp_registry.TOOLS``：外部
   MCP ``tools/list`` 的 205 条是 INT-2453 钉住的对外契约，本卡不外扩。
2. ``build_case_drafts``：音频标注 → 用例草案。口径对齐既有「音频上传生成
   用例」链路（``audio_service/application/services/_creation_annotation_mixin``
   与 ``_creation_round_config_mixin``）：
   - 轮次号取标注 ``data.round_number``（缺失按第 1 轮），不凭空造轮次；
   - ``spl`` / ``playback_device_id`` / ``playback_device_name`` **入参显式给定
     即覆盖**标注 ``segments[]``（与创建服务「入参优先、标注只填空」一致），
     都没有才按创建服务的缺省（spl 65.0）；
   - 用例参数按 ``algorithm/case-params`` 的 ``annotation_code`` +
     ``field_path``（``segments[].<field>``）抽取，作用域按
     ``common`` / 目标 ``device_type`` 过滤；
   - 评估维度按 ``round_scope``（``multi`` 进顶层 ``config.dimensions``，
     其余逐轮）与 ``(id, round_scope)`` 去重，作用域按 ``device_type`` 过滤。

草案**只做推导**：没有真实用例 ID、不写库、不调用任何非 GET 接口；名字 /
设备名 → ID 的名解析属写侧创建流程，草案里原样保留名字并写明未解析。
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from shared.agent_tools.mcp_registry import tool_entry
from shared.models.common_enums import CaseParamScope, DeviceType

# ---------------------------------------------------------------- 参数辅助


def _str(desc: str, required: bool = False,
         enum: Optional[Sequence[str]] = None) -> dict:
    """字符串参数（与 mcp_registry 的 _str 同形）。"""
    prop: Dict[str, Any] = {'type': 'string', 'description': desc,
                            'required': required}
    if enum:
        prop['enum'] = list(enum)
    return prop


def _int(desc: str, required: bool = False) -> dict:
    """整数参数（与 mcp_registry 的 _int 同形）。"""
    return {'type': 'integer', 'description': desc, 'required': required}


# ---------------------------------------------------------------- 只读路由

# 与 mcp_registry 同形（name / description / inputSchema / permissions /
# method / path / path_params / query_params），复用共享构造器。
TESTCASE_READ_TOOLS: List[dict] = [
    tool_entry('testcase_stats', '获取用例统计（总数 / 按分组 / 最近更新）',
               {}, ['testcase:read'], 'GET', '/api/v1/testcases/stats'),
    tool_entry(
        'testcase_round_ref_params', '读取用例指定轮次的参考参数文件内容',
        {'tc_id': _str('用例 ID', True),
         'round_number': _int('轮次号（从 1 开始）', True)},
        ['testcase:read'], 'GET',
        '/api/v1/testcases/{tc_id}/rounds/{round_number}/ref-params',
        path_params=['tc_id', 'round_number']),
    tool_entry('testcase_export_job_status',
               '查询用例导出作业状态（进度与导出产物）',
               {'task_id': _str('导出作业 ID', True)},
               ['testcase:import_export'], 'GET',
               '/api/v1/testcases/export/jobs/{task_id}',
               path_params=['task_id']),
    tool_entry('testcase_refresh_status', '查询参考参数刷新任务状态与进度',
               {'task_id': _str('刷新任务 ID', True)},
               ['testcase:read'], 'GET',
               '/api/v1/testcases/refresh_task/{task_id}',
               path_params=['task_id']),
]

TESTCASE_READ_TOOL_BY_NAME: Dict[str, dict] = {
    tool['name']: tool for tool in TESTCASE_READ_TOOLS}

# 草案推导的存在性校验回源：播放设备详情（``playback:read``）。
# **不进**对外工具表（T1 只读动作表 / MCP tools/list），仅供 ToolGateway 在
# ``testcase_generate`` 里校验 ``playback_device_id``（INT-2530：收 ID 必验存在）。
PLAYBACK_DEVICE_GET_TOOL: dict = tool_entry(
    'playback_device_get', '读取播放设备详情（草案播放设备存在性校验）',
    {'device_id': _int('播放设备 ID', True)},
    ['playback:read'], 'GET', '/api/v1/playback-devices/{device_id}',
    path_params=['device_id'])


def get_tool(name: str) -> Optional[dict]:
    """按工具名取用例域只读工具（不含 mcp_registry 的工具）。"""
    return TESTCASE_READ_TOOL_BY_NAME.get(name)


# ---------------------------------------------------------------- 口径常量

# 用例参数 / 维度 / 标注的固定口径（对齐创建服务，不散落魔法值）
ANNOTATION_SEGMENTS_KEY = 'segments'
ANNOTATION_ROUND_KEY = 'round_number'
ANNOTATION_CODE_KEY = 'code'
SEGMENT_SPL_KEY = 'spl'
SEGMENT_PLAYBACK_DEVICE_ID_KEY = 'playback_device_id'
SEGMENT_PLAYBACK_DEVICE_NAME_KEY = 'playback_device_name'

DEFAULT_ROUND_NUMBER = 1
DEFAULT_SPL = 65.0
DRAFT_NAME_PREFIX = '测试用例_'
DRAFT_DESCRIPTION = '由音频标注推导的用例草案（未落库，确认后再创建）'

# 维度口径：多轮整体评估（与读侧 case_loader.OVERALL_ROUND_SCOPE 一致）
OVERALL_ROUND_SCOPE = 'multi'
ROUND_SCOPES: Tuple[str, ...] = ('single', 'per_round', OVERALL_ROUND_SCOPE)

# 单次生成上限：草案逐音频回源取详情，避免一次调用打爆工具预算
MAX_GENERATE_AUDIOS = 20

# 标注 field_path 的数组前缀（``segments[].xxx``）
_SEGMENTS_PATH_PREFIX = 'segments[]'


# ---------------------------------------------------------------- 标注解析


def normalize_device_type(value: Optional[str]) -> Optional[str]:
    """设备类型归一：缺省按创建服务口径取 http_api；非法值返回 None。"""
    if value is None or str(value).strip() == '':
        return DeviceType.HTTP_API.value
    try:
        return DeviceType(str(value).strip()).value
    except ValueError:
        return None


def normalize_round_number(value: Any) -> Optional[int]:
    """轮次号归一：只认正整数（int / 整值 float / 纯数字串），否则 None。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float):
        return int(value) if value.is_integer() and value > 0 else None
    text = str(value).strip()
    if text.isdigit() and int(text) > 0:
        return int(text)
    return None


def is_positive_int(value: Any) -> bool:
    """严格正整数（排除 bool / 浮点 / 字符串）。"""
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def validate_dimension_ids(raw: Any) -> Optional[str]:
    """逐项校验 ``dimension_ids`` 入参，返回错误文本或 ``None``。

    INT-2529 / INT-2531：数组元素也必须校验——非法元素显式失败，不能像
    旧实现那样 ``continue`` 静默丢弃（模型会把「全丢了」当成「没挂维度」）。
    合法项只有两种：正整数 ID，或带正整数 ``id`` 的对象（可选
    ``round_scope`` ∈ :data:`ROUND_SCOPES`、``device_type`` ∈ DeviceType）。
    """
    if raw is None:
        return None
    if not isinstance(raw, list):
        return 'dimension_ids 必须是数组'
    for item in raw:
        if is_positive_int(item):
            continue
        if isinstance(item, dict):
            if not is_positive_int(item.get('id')):
                return f'dimension_ids 对象项必须带正整数 id：{item}'
            round_scope = item.get('round_scope')
            if round_scope is not None and round_scope not in ROUND_SCOPES:
                return (f'dimension_ids 的 round_scope 取值必须是 '
                        f'{"/".join(ROUND_SCOPES)} 之一：{item}')
            device_type = item.get('device_type')
            if device_type is not None and normalize_device_type(device_type) is None:
                return f'dimension_ids 的 device_type 取值非法：{item}'
            continue
        return f'dimension_ids 每项必须是正整数或带 id 的对象：{item}'
    return None


def _as_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _segment_field(segment: dict, key: str) -> Any:
    """从标注 segment 取字段：精确 key 优先，其次驼峰 → 蛇形兜底。"""
    if segment.get(key) is not None:
        return segment.get(key)
    snake = re.sub(r'([A-Z])', r'_\1', key).lower()
    return segment.get(snake)


def extract_annotation_value(data: Any, field_path: Optional[str]) -> Any:
    """按 ``field_path``（``segments[].xxx`` 口径）从标注 data 取首个有效值。

    与既有创建服务 ``_extract_field_value_from_annotation_data`` 同口径：
    空数组 / 空字符串不算有效值；多个有效值原样返回列表。
    """
    if not isinstance(data, dict) or not field_path:
        return None
    effective = str(field_path)
    if _SEGMENTS_PATH_PREFIX not in effective:
        effective = f'{_SEGMENTS_PATH_PREFIX}.{effective}'
    array_key, _, field_key = effective.partition('[].')
    rows = data.get(array_key)
    if not isinstance(rows, list) or not field_key:
        return None
    collected = [
        _segment_field(row, field_key) for row in rows
        if isinstance(row, dict) and _segment_field(row, field_key) is not None
    ]
    collected = [item for item in collected
                 if not (isinstance(item, (list, str, dict)) and len(item) == 0)]
    if not collected:
        return None
    return collected[0] if len(collected) == 1 else collected


def _annotation_round(annotation: dict) -> int:
    """标注所属轮次：``data.round_number`` 合法即用，缺失/非法按第 1 轮。"""
    data = annotation.get('data')
    raw = data.get(ANNOTATION_ROUND_KEY) if isinstance(data, dict) else None
    return normalize_round_number(raw) or DEFAULT_ROUND_NUMBER


def _annotation_segments(annotation: dict) -> List[dict]:
    data = annotation.get('data')
    rows = data.get(ANNOTATION_SEGMENTS_KEY) if isinstance(data, dict) else None
    return [row for row in rows or [] if isinstance(row, dict)]


def _select_annotations(annotations: Sequence[dict],
                        annotation_code: Optional[str]) -> List[dict]:
    """按标注 code 选：匹配不到就用全部（与创建服务回退口径一致）。"""
    if not annotation_code:
        return list(annotations)
    matched = [a for a in annotations if a.get(ANNOTATION_CODE_KEY) == annotation_code]
    return matched or list(annotations)


def _first_segment_value(segments: Iterable[dict], key: str) -> Any:
    for segment in segments:
        value = _segment_field(segment, key)
        if value is not None:
            return value
    return None


# ---------------------------------------------------------------- 维度解析


def _normalize_dimension(item: Any) -> dict:
    """维度项归一；非法项**抛 ValueError**（不静默丢弃，INT-2529/2531）。"""
    if isinstance(item, dict):
        dim_id = item.get('id')
        if not is_positive_int(dim_id):
            raise ValueError(f'维度项必须带正整数 id：{item}')
        normalized = {'id': dim_id}
        if item.get('round_scope'):
            normalized['round_scope'] = item['round_scope']
        if item.get('device_type'):
            normalized['device_type'] = item['device_type']
        return normalized
    if is_positive_int(item):
        return {'id': item}
    raise ValueError(f'维度项必须是正整数或带 id 的对象：{item}')


def partition_dimensions(raw: Sequence[Any], device_type: str,
                         default_round_scope: str = 'single'
                         ) -> Tuple[List[dict], List[dict]]:
    """维度归一 → 设备作用域过滤 → ``(逐轮, 整体)`` 两桶（去重保序）。

    ``default_round_scope`` 用于只给维度 ID 的入参（``multi`` 表示多轮整体）。
    非法项抛 ``ValueError``——网关在回源前已用
    :func:`validate_dimension_ids` 拦一遍，这里再守一层，杜绝静默丢弃。
    """
    normalized: List[dict] = []
    for item in raw or []:
        dim = _normalize_dimension(item)
        dim.setdefault('round_scope', default_round_scope)
        if dim.get('device_type') and dim['device_type'] != device_type:
            continue
        normalized.append(dim)

    seen = set()
    per_round: List[dict] = []
    overall: List[dict] = []
    for dim in normalized:
        key = (dim['id'], dim.get('round_scope', 'single'))
        if key in seen:
            continue
        seen.add(key)
        if dim.get('round_scope') == OVERALL_ROUND_SCOPE:
            overall.append(dim)
        else:
            per_round.append(dim)
    return per_round, overall


# ---------------------------------------------------------------- 草案推导


def _scoped_case_params(case_params: Sequence[dict], device_type: str) -> List[dict]:
    """用例参数按作用域过滤：``common`` 通用 + 目标设备类型专属。"""
    scoped = []
    for param in case_params or []:
        if not isinstance(param, dict):
            continue
        scope = param.get('scope')
        if scope == CaseParamScope.COMMON.value or scope == device_type:
            scoped.append(param)
    return scoped


def _round_params(annotations: Sequence[dict], scoped_params: Sequence[dict],
                  algorithm_type: Optional[str]) -> List[dict]:
    """从一个轮次的标注里抽用例参数（``field_code`` / ``field_value``）。"""
    params: List[dict] = []
    for param in scoped_params:
        field_code = param.get('param_code')
        if not field_code:
            continue
        field_path = param.get('field_path') or field_code
        annotation_code = param.get('annotation_code') or algorithm_type
        value = None
        for annotation in _select_annotations(annotations, annotation_code):
            value = extract_annotation_value(annotation.get('data'), field_path)
            if value is not None:
                break
        if value is not None:
            params.append({'field_code': field_code, 'field_value': value})
    return params


def build_case_drafts(*, audios: Sequence[dict],
                      case_params: Sequence[dict] = (),
                      algorithm_type: Optional[str] = None,
                      device_type: Optional[str] = None,
                      dimensions: Sequence[Any] = (),
                      dimension_round_scope: str = 'single',
                      group_id: Optional[str] = None,
                      spl: Optional[float] = None,
                      playback_device_id: Optional[int] = None,
                      inherit_tags: bool = True) -> Dict[str, Any]:
    """把音频标注推导成用例草案（纯函数，不写库）。

    返回 ``{'drafts': [...], 'notes': [...], 'device_type': ...}``；
    每个草案含 ``name`` / ``config`` / ``algorithm_params`` /
    ``derived_from`` / ``notes``，且**没有**用例 ID（未落库）。

    ``spl`` / ``playback_device_id`` 是**覆盖**语义：显式给定即压过标注，
    标注只补缺（与创建服务一致，见 ``_creation_annotation_mixin``）。
    """
    effective_device_type = (normalize_device_type(device_type)
                             or DeviceType.HTTP_API.value)
    # 用例参数抽取依赖 algorithm_type（创建服务同口径：无算法类型就不抽参数，
    # 否则会把任意标注字段当成某算法的参数）
    scoped_params = (_scoped_case_params(case_params, effective_device_type)
                     if algorithm_type else [])
    per_round_dims, overall_dims = partition_dimensions(
        dimensions, effective_device_type, dimension_round_scope)

    notes: List[str] = []
    drafts: List[dict] = []

    for audio in audios:
        audio_id = audio.get('id')
        audio_name = audio.get('name') or audio.get('original_filename') or ''
        annotations = [a for a in audio.get('annotations') or []
                       if isinstance(a, dict)]
        matched = _select_annotations(annotations, algorithm_type)

        # 轮次口径来自标注本身：没有标注就是第 1 轮（不凭空造轮次）
        rounds_map: Dict[int, List[dict]] = {}
        for annotation in matched:
            rounds_map.setdefault(_annotation_round(annotation), []).extend(
                _annotation_segments(annotation))
        if not rounds_map:
            rounds_map[DEFAULT_ROUND_NUMBER] = []

        rounds: List[dict] = []
        algorithm_params: List[dict] = []
        draft_notes: List[str] = []
        for round_number in sorted(rounds_map):
            segments = rounds_map[round_number]
            segment_spl = _as_float(
                _first_segment_value(segments, SEGMENT_SPL_KEY))
            segment_device_id = _first_segment_value(
                segments, SEGMENT_PLAYBACK_DEVICE_ID_KEY)
            segment_device_name = _first_segment_value(
                segments, SEGMENT_PLAYBACK_DEVICE_NAME_KEY)
            audio_entry: Dict[str, Any] = {
                'audio_id': audio_id,
                'audio_name': audio_name,
                # 入参显式 spl 优先，标注只填空，最后是创建服务缺省
                'spl': (spl if spl is not None
                        else (segment_spl if segment_spl is not None
                              else DEFAULT_SPL)),
                'play_order': 0,
            }
            resolved_device_id = (playback_device_id if playback_device_id is not None
                                  else segment_device_id)
            if resolved_device_id is not None:
                audio_entry['playback_device_id'] = resolved_device_id
            if segment_device_name:
                # 名 → ID 解析属写侧创建流程；草案原样保留名字并注明未解析
                audio_entry['playback_device_name'] = segment_device_name
                if resolved_device_id is None:
                    draft_notes.append(
                        f'第 {round_number} 轮的播放设备名「{segment_device_name}」'
                        '未解析为 ID（草案不落库，创建时按名解析）')

            rounds.append({
                'round_number': round_number,
                'audios': [audio_entry],
                'evaluation': {'dimensions': [dict(d) for d in per_round_dims]},
            })

            round_annotations = [
                a for a in matched if _annotation_round(a) == round_number]
            params = _round_params(
                round_annotations, scoped_params, algorithm_type)
            if params:
                algorithm_params.append({
                    'round_number': round_number, 'params': params})

        config: Dict[str, Any] = {
            'source_audio': audio_name,
            'auto_generated': True,
            'rounds': rounds,
        }
        if overall_dims:
            config['dimensions'] = [dict(d) for d in overall_dims]

        drafts.append({
            'name': f'{DRAFT_NAME_PREFIX}{audio_name}',
            'description': DRAFT_DESCRIPTION,
            'group_id': group_id,
            'algorithm_type': algorithm_type,
            'device_type': effective_device_type,
            'tags': list(audio.get('tags') or []) if inherit_tags else [],
            'config': config,
            'algorithm_params': algorithm_params or None,
            'derived_from': {
                'audio_id': audio_id,
                'audio_name': audio_name,
                'audio_type': audio.get('audio_type'),
                'asr_text': audio.get('asr_text'),
                'annotation_codes': [a.get(ANNOTATION_CODE_KEY) for a in matched
                                     if a.get(ANNOTATION_CODE_KEY)],
                'rounds': sorted(rounds_map),
            },
            'notes': draft_notes,
        })

    if len(audios) > MAX_GENERATE_AUDIOS:
        notes.append(f'单次最多推导 {MAX_GENERATE_AUDIOS} 条音频，超出部分未处理')
    if algorithm_type and not scoped_params:
        notes.append(
            f'算法类型 {algorithm_type} 未配置用例参数（case-params 为空），'
            'algorithm_params 为空')
    return {'drafts': drafts, 'notes': notes,
            'device_type': effective_device_type}


__all__ = [
    'ANNOTATION_SEGMENTS_KEY', 'DEFAULT_ROUND_NUMBER', 'DEFAULT_SPL',
    'DRAFT_DESCRIPTION', 'DRAFT_NAME_PREFIX', 'MAX_GENERATE_AUDIOS',
    'OVERALL_ROUND_SCOPE', 'PLAYBACK_DEVICE_GET_TOOL', 'ROUND_SCOPES',
    'TESTCASE_READ_TOOLS', 'TESTCASE_READ_TOOL_BY_NAME', 'build_case_drafts',
    'extract_annotation_value', 'get_tool', 'is_positive_int',
    'normalize_device_type', 'normalize_round_number', 'partition_dimensions',
    'validate_dimension_ids',
]
