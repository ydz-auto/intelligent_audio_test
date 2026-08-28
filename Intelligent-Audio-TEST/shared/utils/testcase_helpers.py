"""测试用例共享辅助函数（纯工具，无 DB/ORM 依赖）。

这些函数原为 TestCaseController 的静态方法，后下沉到 task_service。
为消除 api_gateway 对 task_service 的跨服务 Python 直导，现迁至 shared/utils，
供所有服务（api_gateway/task_service 等）共享引用。
"""
import logging

from shared.utils.log_handler import log_not_emit

logger = logging.getLogger(__name__)

# 预览停止标志：跨服务共享（原 TestCaseController 模块级全局变量）
preview_stop_flags = {}


def log(level, content, task_id=None, test_case_id=None, api_id=None, category='execution', module='TestCase', **kwargs):
    """统一日志记录方法"""
    log_not_emit(
        level=level,
        module=module,
        content=content,
        category=category,
        source='backend',
        task_id=task_id,
        api_id=api_id,
        test_case_id=test_case_id,
        **kwargs
    )


def normalize_optional_int(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(text)
        except Exception:
            try:
                f = float(text)
                return int(f) if f.is_integer() else None
            except Exception:
                return None
    try:
        return int(value)
    except Exception:
        return None


def has_overlap_param_changed(old_params: list, new_params: list) -> bool:
    overlap_fields = {'overlap_rate', 'overlap_time', 'overlapRate', 'overlapTime'}

    def get_overlap_values(params: list) -> dict:
        result = {}
        for p in params:
            if not isinstance(p, dict):
                continue
            field_code = p.get('field_code') or p.get('fieldCode')
            if field_code in overlap_fields:
                result[field_code] = p.get('field_value', p.get('fieldValue'))
        return result

    old_overlap = get_overlap_values(old_params)
    new_overlap = get_overlap_values(new_params)

    return old_overlap != new_overlap


def get_algo_params_list_from_config(config: dict) -> list:
    """从 config 中提取 algorithm_params 列表格式（兼容旧数据）

    新数据：config.rounds[] 不含 algorithmParams，应从独立列读取（见 _get_algo_params_list_from_columns）
    旧数据：config.rounds[0].algorithmParams 为 dict，转换为 [{field_code, field_value}] 列表
    """
    if not config:
        return []
    rounds = config.get('rounds', [])
    if rounds:
        first_round = rounds[0] if rounds else {}
        if isinstance(first_round, dict):
            ap_dict = first_round.get('algorithmParams', {})
            if isinstance(ap_dict, dict):
                return [{'field_code': k, 'field_value': v} for k, v in ap_dict.items()]
    return []


def get_algo_params_list_from_columns(algorithm_params_col, round_number=1):
    """从 algorithm_params 独立列按轮获取 [{field_code, field_value}] 列表"""
    if not algorithm_params_col:
        return []
    for item in algorithm_params_col:
        if isinstance(item, dict) and item.get('round_number') == round_number:
            return item.get('params', [])
    return []


def get_algorithm_params_dict_for_columns(algorithm_params_col, round_number=1):
    """从 algorithm_params 独立列按轮获取 dict"""
    params_list = get_algo_params_list_from_columns(algorithm_params_col, round_number)
    result = {}
    for p in params_list:
        if not isinstance(p, dict):
            continue
        fc = p.get('field_code')
        if fc:
            result[fc] = p.get('field_value')
    return result


def has_rounds(config: dict) -> bool:
    """判断 config 是否为 rounds-as-top-level 格式"""
    return bool(config and isinstance(config.get('rounds'), list) and len(config['rounds']) > 0)


def convert_flat_config_to_rounds(config: dict) -> dict:
    """将平面格式 config 转换为 rounds-as-top-level 格式

    只构建结构性字段（roundNumber/audios/backgroundNoise/evaluation），
    不再写入 algorithmParams 和 referenceParamsPath。
    algorithm_params 由调用方从 schema 获取并赋值给独立列。
    """
    if has_rounds(config):
        return config

    result = dict(config)
    audios = result.pop('audios', [])
    bg_noise = result.pop('background_noise', None) or result.pop('backgroundNoise', None)
    dimensions = result.pop('dimensions', [])

    # 剥离非结构性字段（algorithm_params 由独立列存储）
    result.pop('algorithm_params', None)
    for key in ('reference_params', 'referenceParamsPath'):
        result.pop(key, None)

    round_data = {
        'roundNumber': 1,
        'audios': audios or [],
        'backgroundNoise': bg_noise,
        'evaluation': {'dimensions': dimensions or []},
    }

    result['rounds'] = [round_data]
    return result


def collect_audios(config: dict) -> list:
    """从 config 中提取所有音频配置项（从 rounds[].audios 收集）"""
    if not config:
        return []
    all_audios = []
    for round_item in config.get('rounds', []):
        if isinstance(round_item, dict):
            round_audios = round_item.get('audios', [])
            if isinstance(round_audios, list):
                all_audios.extend(round_audios)
    return all_audios


def collect_dimensions(config: dict) -> list:
    """从 config 中提取评测维度
    合并 rounds[].evaluation.dimensions（单轮维度）和 config.dimensions（多轮维度）
    """
    if not config:
        return []
    result = []
    seen_ids = set()
    rounds = config.get('rounds', [])
    if rounds:
        for round_item in rounds:
            if isinstance(round_item, dict):
                evaluation = round_item.get('evaluation', {})
                if isinstance(evaluation, dict):
                    for d in evaluation.get('dimensions', []):
                        dim_id = d.get('id') if isinstance(d, dict) else d
                        if dim_id and dim_id not in seen_ids:
                            seen_ids.add(dim_id)
                            result.append(d)
    # 合并顶层 config.dimensions（多轮聚合维度）
    for d in config.get('dimensions', []):
        dim_id = d.get('id') if isinstance(d, dict) else d
        if dim_id and dim_id not in seen_ids:
            seen_ids.add(dim_id)
            result.append(d)
    return result


def validate_multi_round_audio_dimensions(config: dict):
    """校验整体评估(config.dimensions)不能配置需要音频文件的维度

    整体评估在所有轮次执行完成后触发，无法传递音频文件。
    只检查 config.dimensions（整体评估维度），不检查 rounds[].evaluation.dimensions（单轮维度）。
    多轮时，rounds[].evaluation.dimensions（单轮评估）允许配置音频维度。
    """
    if not config:
        return None
    rounds = config.get('rounds', [])
    if not isinstance(rounds, list) or len(rounds) <= 1:
        return None  # 单轮不限制

    # 只收集 config.dimensions（整体评估维度），不收集 rounds[].evaluation.dimensions
    overall_dims = config.get('dimensions', [])
    dim_ids = set()
    for d in overall_dims:
        dim_id = d.get('id') if isinstance(d, dict) else d
        if dim_id:
            dim_ids.add(dim_id)
    if not dim_ids:
        return None

    # 查询这些维度是否有 field_type='audio' 的输入参数
    # algorithm_service proto 已接入：通过 gRPC 调用
    # get_algorithm_definition_service_stub().GetDimensionParams 按维度逐个查询，
    # 再本地过滤 audio/input 字段；gRPC 不可用时回退直连 EvaluationDimensionParam PO。
    audio_dims = []
    try:
        from shared.clients.grpc_clients import get_algorithm_definition_service_stub
        from shared.proto import algorithm_service_pb2 as _algo_pb
        from shared.utils.grpc_json import loads as _grpc_loads
        stub = get_algorithm_definition_service_stub()
        for dim_id in dim_ids:
            req = _algo_pb.GetDimensionParamsRequest(dimension_id=int(dim_id))
            resp = stub.GetDimensionParams(req)
            if not resp.success:
                continue
            params = (_grpc_loads(resp.data, {}) or {}).get('params', []) or []
            for p in params:
                if (p.get('field_type') == 'audio'
                        and p.get('param_direction') == 'input'):
                    audio_dims.append((p.get('dimension_id', dim_id), p.get('param_code')))
    except Exception:
        # gRPC 不可用时返回空（不再跨服务直连 PO）
        pass

    if audio_dims:
        # 通过 gRPC 查维度名（evaluation_service）
        import json as _json
        from shared.clients.grpc_clients import get_evaluation_config_service_stub
        from shared.proto import evaluation_service_pb2 as eval_pb
        from shared.utils.grpc_json import loads as _eval_loads
        dim_map = {}
        audio_dim_ids = [ad[0] for ad in audio_dims]
        try:
            stub = get_evaluation_config_service_stub()
            resp = stub.GetDimensionByIds(eval_pb.GetDimensionByIdsRequest(
                dim_ids=_json.dumps([int(d) for d in audio_dim_ids if d is not None],
                                    ensure_ascii=False, default=str),
            ))
            if resp.success and resp.data:
                items = _eval_loads(resp.data, {}) or {}
                if isinstance(items, dict):
                    raw_items = items.get('items', items)
                else:
                    raw_items = items
                if isinstance(raw_items, list):
                    dim_map = {str(d.get('id')): d for d in raw_items
                               if isinstance(d, dict) and d.get('id') is not None}
                elif isinstance(raw_items, dict):
                    dim_map = raw_items
        except Exception:
            logger.debug("查询评估维度列表失败，回退到 ID 占位", exc_info=True)
        dim_names = [dim_map.get(str(ad[0]), {}).get('name', f"ID:{ad[0]}") for ad in audio_dims]
        param_codes = [ad[1] for ad in audio_dims]
        return (f"整体评估维度不支持需要传递音频文件的维度。"
                f"维度 {', '.join(dim_names)} 包含音频参数({', '.join(param_codes)})，"
                f"请在单轮评估中配置该维度，或从整体评估中移除。")
    return None


def audios_changed(old_config: dict, new_config: dict) -> bool:
    """比较两个 config 中的音频配置是否发生变化"""
    old_audios = collect_audios(old_config)
    new_audios = collect_audios(new_config)
    old_ids = sorted([str(a.get('audio_id')) for a in old_audios if isinstance(a, dict) and a.get('audio_id')])
    new_ids = sorted([str(a.get('audio_id')) for a in new_audios if isinstance(a, dict) and a.get('audio_id')])
    return old_ids != new_ids


def get_algorithm_params_dict_for_executor(config: dict) -> dict:
    """从 rounds[0].algorithmParams 读取（兼容旧数据）

    新数据：config.rounds[] 不含 algorithmParams，返回空 dict。
    调用方应从独立列读取（见 _get_algorithm_params_dict_for_columns）。
    """
    if not config:
        return {}
    rounds = config.get('rounds', [])
    if rounds:
        first_round = rounds[0] if rounds else {}
        if isinstance(first_round, dict):
            return first_round.get('algorithmParams', {}) or {}
    return {}
