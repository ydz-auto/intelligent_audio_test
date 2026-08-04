"""测试用例共享私有辅助函数。

这些函数从 TestCaseController 中抽取，供多个 service 共用。
原为 TestCaseController 的静态方法，现改为模块级函数以简化跨 service 引用。
"""
from shared.models.models import Dimension
from shared.models.database import db
from shared.utils.log_handler import log_not_emit

# 预览停止标志：跨 service 共享（原 TestCaseController 模块级全局变量）
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
    from shared.models.algorithm_models import EvaluationDimensionParam
    audio_dims = db.session.query(
        EvaluationDimensionParam.dimension_id,
        EvaluationDimensionParam.param_code
    ).filter(
        EvaluationDimensionParam.dimension_id.in_(dim_ids),
        EvaluationDimensionParam.field_type == 'audio',
        EvaluationDimensionParam.param_direction == 'input',
        EvaluationDimensionParam.deleted == False
    ).all()

    if audio_dims:
        # 查维度名
        dim_map = {d.id: d.name for d in Dimension.query.filter(Dimension.id.in_([ad[0] for ad in audio_dims])).all()}
        dim_names = [dim_map.get(ad[0], f"ID:{ad[0]}") for ad in audio_dims]
        param_codes = [ad[1] for ad in audio_dims]
        return (f"整体评估维度不支持需要传递音频文件的维度。"
                f"维度 {', '.join(dim_names)} 包含音频参数({', '.join(param_codes)})，"
                f"请在单轮评估中配置该维度，或从整体评估中移除。")
    return None


def audios_changed(old_config: dict, new_config: dict) -> bool:
    """比较两个 config 中的音频配置是否发生变化"""
    old_audios = collect_audios(old_config)
    new_audios = collect_audios(new_config)
    old_ids = sorted([a.get('audio_id') for a in old_audios if isinstance(a, dict) and a.get('audio_id')])
    new_ids = sorted([a.get('audio_id') for a in new_audios if isinstance(a, dict) and a.get('audio_id')])
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
