"""测试用例共享辅助函数（纯工具，无 DB/ORM 依赖）。

这些函数原为 TestCaseController 的静态方法，后下沉到 task_service。
为消除 api_gateway 对 task_service 的跨服务 Python 直导，现迁至 shared/utils，
供所有服务（api_gateway/task_service 等）共享引用。
"""
import re

from shared.utils.log_handler import log_not_emit

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


def has_playback_audio(config: dict) -> bool:
    """用例配置中是否存在携带播放设备的音频（E2E 形态标记）"""
    for audio_item in collect_audios(config):
        if isinstance(audio_item, dict) and audio_item.get('playback_device_id'):
            return True
    # 兼容未轮次化的平面 audios 配置
    for audio_item in (config or {}).get('audios', []) or []:
        if isinstance(audio_item, dict) and audio_item.get('playback_device_id'):
            return True
    return False


# 上传双变体用例名后缀（INT-129）：audio_service 建用例名 f"{base_name}_{tt}"
# （tt∈{api,e2e}），重名冲突追加 _%H%M%S，故后缀形如 _api / _api_HHMMSS
_DUAL_VARIANT_NAME_RE = re.compile(r'_(api|e2e)(?:_\d{6})?$')


def derive_case_test_type(config: dict, case_name: str = None) -> str:
    """由用例配置形态推导 e2e/api 口径（用例纯数据化过渡）。

    test_type 列已废弃（差异#2 收尾）：用例不再存储类型，执行方式由
    任务侧 task_case_relations.device_type 决定。评估/报告/算法服务的
    参考值口径契约仍需 'e2e'/'api' 取值，此处由配置形态派生：
    任一音频携带 playback_device_id 即 E2E 口径（物理执行），否则 API 口径。

    INT-129：上传双变体两变体配置形态相同（rounds[].audios 均带
    playback_device_id——API 变体逐轮 SPL 渲染也依赖播放设备），配置形态
    无法区分变体，唯一可靠标记是用例名 _api/_e2e 后缀。仅当用例为上传
    生成（config.auto_generated）且名称带变体后缀时以后缀为准，避免 API
    变体建任务被误路由到 E2E 执行器；未传名称或非上传生成的用例一律
    回落配置形态口径，手工用例不受影响。
    """
    if case_name:
        match = _DUAL_VARIANT_NAME_RE.search(case_name.strip())
        if match and (config or {}).get('auto_generated'):
            return match.group(1)
    return 'e2e' if has_playback_audio(config) else 'api'


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
