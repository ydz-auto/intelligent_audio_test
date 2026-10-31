"""测试用例共享辅助函数（纯工具，无 DB/ORM 依赖）。

这些函数原为 TestCaseController 的静态方法，后下沉到 task_service。
为消除 api_gateway 对 task_service 的跨服务 Python 直导，现迁至 shared/utils，
供所有服务（api_gateway/task_service 等）共享引用。
"""
import re

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


# 用例配置里的轮次键：snake_case 为库/新接口口径，camelCase 为历史 config 口径
ROUND_NUMBER_KEYS = ('round_number', 'roundNumber')

# 轮次号白名单：只允许十进制数字（不带符号/空白/小数点/路径分隔符）
_ROUND_NUMBER_PATTERN = re.compile(r'^\d+$')

# 参考参数文件名白名单：单段文件名，不得含路径分隔符或 `..`
_FILENAME_PATTERN = re.compile(r'^[A-Za-z0-9._-]+$')


def parse_round_number(value):
    """轮次号归一：只接受正整数（int / 整值 float / 纯数字字符串），其余返回 None。

    `config` 在网关是自由 dict（无类型校验），`round_number` 会直接拼进
    参考参数存储 key。`'../../../../tmp/x'` 这类非数字值必须在这里拦掉，
    不能进入 key 拼接（INT-2246）。
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float):
        return int(value) if value.is_integer() and value > 0 else None
    if isinstance(value, str):
        text = value.strip()
        if not _ROUND_NUMBER_PATTERN.match(text):
            return None
        number = int(text)
        return number if number > 0 else None
    return None


def resolve_round_number(round_item, default=None):
    """从轮次配置项取正整数轮次号。

    键缺失 / 空值 → 返回 default（历史口径缺省为第 1 轮）；键有值但非法
    → 返回 None，由调用方跳过该轮并告警，不写存储。
    """
    if not isinstance(round_item, dict):
        return None
    for key in ROUND_NUMBER_KEYS:
        if key not in round_item:
            continue
        raw = round_item.get(key)
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            continue
        return parse_round_number(raw)
    return default


def build_ref_params_key(case_id, round_number, filename=None):
    """构建参考参数存储 key：`{case_id}/round_{n}.json`（或 `{case_id}/{filename}`）。

    轮次号与文件名都按白名单校验，非法值直接抛 ValueError，避免拼出可穿越
    存储根目录的 key（INT-2246）。
    """
    if filename is not None:
        if not isinstance(filename, str) or not _FILENAME_PATTERN.match(filename) \
                or filename in ('.', '..'):
            raise ValueError(f"非法参考参数文件名，拒绝构建存储 key: {filename!r}")
        return f"{case_id}/{filename}"
    number = parse_round_number(round_number)
    if number is None:
        raise ValueError(f"非法轮次号，拒绝构建存储 key: {round_number!r}")
    return f"{case_id}/round_{number}.json"


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


# ==================== 用例音频引用收集（单点口径，INT-2214） ====================
# 用例对音频的真实引用不止「播放音频」：
# - direct：rounds[].audios[].audio_id、rounds[].audios[].interferers[].audio_id、
#   顶层 audios[].audio_id（未轮次化的平面形态兜底）；
# - noise：顶层 / 轮次级 / segment 级 background_noise|backgroundNoise.audio_id
#   （task_service 的 _apply_noise_to_round / _apply_noise_to_case_bn 写入）。
# 导出、导入校验、任务数据导出共用本模块的实现，不允许各写一份。

BACKGROUND_NOISE_KEYS = ('background_noise', 'backgroundNoise')


def iter_background_noise(config: dict):
    """遍历 config 中各级背景噪音配置（dict），供统一判定 noise 引用。

    层级：顶层 config → rounds[] → rounds[].audios[]（segment 级）。
    非 dict 的噪音值归一为空 dict（与 task_service 的 _iter_background_noise 一致）。
    """
    if not isinstance(config, dict):
        return

    def _noise_of(obj):
        for key in BACKGROUND_NOISE_KEYS:
            noise = obj.get(key)
            if noise is not None:
                yield noise if isinstance(noise, dict) else {}

    for noise in _noise_of(config):
        yield noise
    for round_item in iter_dict_rounds(config):
        for noise in _noise_of(round_item):
            yield noise
        for audio_item in round_item.get('audios') or []:
            if isinstance(audio_item, dict):
                for noise in _noise_of(audio_item):
                    yield noise


def _collect_audio_item_ids(audio_item, target: list) -> None:
    """把单个音频项（含 interferers 干扰人）的 audio_id 追加进 target。"""
    if not isinstance(audio_item, dict):
        return
    for value in [audio_item.get('audio_id')] + [
        inf.get('audio_id') for inf in (audio_item.get('interferers') or [])
        if isinstance(inf, dict)
    ]:
        audio_id = normalize_optional_int(value)
        if audio_id is not None and audio_id not in target:
            target.append(audio_id)


def collect_case_audio_references(config: dict) -> tuple:
    """收集用例 config 的音频引用，返回 (direct_ids, noise_ids)。

    两个列表均为 int、去重保序；空值 / 非数值跳过。
    direct 覆盖 rounds[].audios[]（含 interferers[]）与顶层 audios[]；
    noise 覆盖顶层 / 轮次级 / segment 级背景噪音。
    """
    direct, noise = [], []
    if not isinstance(config, dict):
        return direct, noise
    for audio_item in collect_audios(config):
        _collect_audio_item_ids(audio_item, direct)
    for audio_item in config.get('audios') or []:
        _collect_audio_item_ids(audio_item, direct)
    for noise_cfg in iter_background_noise(config):
        audio_id = normalize_optional_int(noise_cfg.get('audio_id'))
        if audio_id is not None and audio_id not in noise:
            noise.append(audio_id)
    return direct, noise


def collect_case_audio_ids(config: dict) -> list:
    """用例引用音频的全口径 id 列表（direct + noise，去重保序）。"""
    direct, noise = collect_case_audio_references(config)
    result = list(direct)
    for audio_id in noise:
        if audio_id not in result:
            result.append(audio_id)
    return result


# ==================== 用例音频 id 位置级重写（INT-2215） ====================
# `collect_*` 只回 id 列表，没有「写回哪里」的信息；导入回导音频需要把全部
# 引用位置按映射改写成目标库 id。下面与 collect_case_audio_references 共用同一
# 遍历口径（同一顺序、同一层级），不另起一套。

def _iter_audio_item_id_positions(audio_item):
    """产出单个音频项（含 interferers 干扰人）里承载 audio_id 的 dict。"""
    if not isinstance(audio_item, dict):
        return
    yield audio_item
    interferers = audio_item.get('interferers') or []
    if isinstance(interferers, list):
        for inf in interferers:
            if isinstance(inf, dict):
                yield inf


def iter_case_audio_id_positions(config: dict):
    """遍历用例 config 中全部 `audio_id` 写入位置，产出承载它的 dict。

    覆盖 direct（rounds[].audios[]/interferers[]、顶层 audios[]）与 noise
    （顶层 / 轮次 / segment 级 background_noise|backgroundNoise），顺序与
    `collect_case_audio_references` 一致，保证「收集到的 id 都重写得到」。
    """
    if not isinstance(config, dict):
        return
    for audio_item in collect_audios(config):
        for holder in _iter_audio_item_id_positions(audio_item):
            yield holder
    flat_audios = config.get('audios')
    if isinstance(flat_audios, list):
        for audio_item in flat_audios:
            for holder in _iter_audio_item_id_positions(audio_item):
                yield holder
    for noise_cfg in iter_background_noise(config):
        yield noise_cfg


def iter_case_data_audio_id_positions(case_data: dict):
    """遍历 config 之外的两处扁平音频列：`audios[].audio_id` 与 `noise_audio_id`。

    CSV/Excel 解析列（也是 ZIP 导出行携带的扁平字段，见导出 `_build_case_row`），
    不重写会让行级校验按源 id 查库、把整包误判成「音频 X 不存在」。
    """
    if not isinstance(case_data, dict):
        return
    flat_audios = case_data.get('audios')
    if isinstance(flat_audios, list):
        for audio_item in flat_audios:
            if isinstance(audio_item, dict):
                yield audio_item, 'audio_id'
    if case_data.get('noise_audio_id') is not None:
        yield case_data, 'noise_audio_id'


def remap_audio_ids(positions, id_map: dict) -> int:
    """按 id_map（源 id → 目标 id）就地重写 positions 里的 audio_id，返回改写数。

    positions 产出 `(holder, key)` 或直接产出 `holder`（键固定 `audio_id`）；
    不在 id_map 内、非数值、目标为空的保持原样（调用方据此报行级错误）。
    """
    if not isinstance(id_map, dict) or not id_map:
        return 0
    normalized = {}
    for source_id, target_id in id_map.items():
        source = normalize_optional_int(source_id)
        target = normalize_optional_int(target_id)
        if source is not None and target is not None:
            normalized[source] = target
    if not normalized:
        return 0

    changed = 0
    for position in positions:
        if isinstance(position, tuple):
            holder, key = position
        else:
            holder, key = position, 'audio_id'
        if not isinstance(holder, dict):
            continue
        current = normalize_optional_int(holder.get(key))
        if current is None or current not in normalized:
            continue
        holder[key] = normalized[current]
        changed += 1
    return changed


def remap_case_audio_ids(case_data: dict, id_map: dict) -> int:
    """用例级全口径音频 id 重写：config 全部位置 + 扁平 audios[] / noise_audio_id。

    返回改写位置数；id_map 为 {源 audio_id: 目标 audio_id}。
    """
    if not isinstance(case_data, dict):
        return 0
    changed = remap_audio_ids(iter_case_audio_id_positions(case_data.get('config') or {}), id_map)
    changed += remap_audio_ids(iter_case_data_audio_id_positions(case_data), id_map)
    return changed
