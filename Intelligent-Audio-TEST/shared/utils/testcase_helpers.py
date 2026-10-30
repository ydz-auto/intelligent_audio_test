"""测试用例共享辅助函数（纯工具，无 DB/ORM 依赖）。

这些函数原为 TestCaseController 的静态方法，后下沉到 task_service。
为消除 api_gateway 对 task_service 的跨服务 Python 直导，现迁至 shared/utils，
供所有服务（api_gateway/task_service 等）共享引用。
"""
from shared.utils.log_handler import log_not_emit

# 预览停止标志：跨服务共享（原 TestCaseController 模块级全局变量）
preview_stop_flags = {}

# 用例音频关联播放设备的两种配置形态：
# - playback_device_id：老用例直接指定某实验室的物理音箱；
# - playback_speaker_group_id：新用例关联逻辑音箱（执行时按实验室换绑）。
PLAYBACK_DEVICE_ID_KEY = 'playback_device_id'
PLAYBACK_SPEAKER_GROUP_ID_KEY = 'playback_speaker_group_id'


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


def parse_config_lab_id(config: dict):
    """从用例 config JSONB 解析 lab_id（INT-539）。

    顶层 `lab_id` 键：空/缺失 = 通用用例（返回 None）；有值须为数值。
    兼容 JSON 序列化后字符串形态（"3" / 3.0）与嵌套读取失败均回退 None。
    """
    if not config or not isinstance(config, dict):
        return None
    return normalize_optional_int(config.get('lab_id'))


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


def iter_dict_rounds(config: dict) -> list:
    """按轮次遍历 config.rounds，只保留 dict 轮次项。

    rounds 由外部 JSON 载入：历史/脏数据可能把 rounds 写成轮数（int）
    等非列表形态，此时等同「无轮次配置」，返回空列表而不是迭代 int 抛
    TypeError: 'int' object is not iterable。
    """
    if not isinstance(config, dict):
        return []
    rounds = config.get('rounds')
    if not isinstance(rounds, list):
        return []
    return [r for r in rounds if isinstance(r, dict)]


def get_algo_params_list_from_config(config: dict) -> list:
    """从 config 中提取 algorithm_params 列表格式（兼容旧数据）

    新数据：config.rounds[] 不含 algorithmParams，应从独立列读取（见 _get_algo_params_list_from_columns）
    旧数据：config.rounds[0].algorithmParams 为 dict，转换为 [{field_code, field_value}] 列表
    """
    if not config:
        return []
    rounds = iter_dict_rounds(config)
    if rounds:
        first_round = rounds[0]
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
    for round_item in iter_dict_rounds(config):
        round_audios = round_item.get('audios', [])
        if isinstance(round_audios, list):
            all_audios.extend(round_audios)
    return all_audios


def _has_playback_ref(audio_item: dict) -> bool:
    """音频项是否关联了播放设备（老用例直接指定设备 / 新用例关联逻辑音箱）"""
    return bool(audio_item.get('playback_device_id')
                or audio_item.get(PLAYBACK_SPEAKER_GROUP_ID_KEY))


def has_playback_audio(config: dict) -> bool:
    """用例配置中是否存在携带播放设备/逻辑音箱的音频（E2E 形态标记）"""
    for audio_item in collect_audios(config):
        if isinstance(audio_item, dict) and _has_playback_ref(audio_item):
            return True
    # 兼容未轮次化的平面 audios 配置
    flat_audios = (config or {}).get('audios') if isinstance(config, dict) else None
    for audio_item in flat_audios if isinstance(flat_audios, list) else []:
        if isinstance(audio_item, dict) and _has_playback_ref(audio_item):
            return True
    return False


def collect_dimensions(config: dict) -> list:
    """从 config 中提取评测维度
    合并 rounds[].evaluation.dimensions（单轮维度）和 config.dimensions（多轮维度）
    """
    if not config:
        return []
    result = []
    seen_ids = set()
    for round_item in iter_dict_rounds(config):
        evaluation = round_item.get('evaluation', {})
        if isinstance(evaluation, dict):
            for d in evaluation.get('dimensions', []):
                dim_id = d.get('id') if isinstance(d, dict) else d
                if dim_id and dim_id not in seen_ids:
                    seen_ids.add(dim_id)
                    result.append(d)
    # 合并顶层 config.dimensions（多轮聚合维度）
    top_dimensions = config.get('dimensions')
    for d in top_dimensions if isinstance(top_dimensions, list) else []:
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
    rounds = iter_dict_rounds(config)
    if rounds:
        return rounds[0].get('algorithmParams', {}) or {}
    return {}
