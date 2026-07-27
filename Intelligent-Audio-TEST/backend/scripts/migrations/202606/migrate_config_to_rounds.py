"""
迁移脚本: config 轮次化 + reference_params 存文件 + algorithm_params 移入独立列
===========================================================================

将 TestCase 从旧结构迁移到"轮次为顶层"新结构：

1. config 从 {audios, dimensions, backgroundNoise, ...} 转为 {rounds: [...]}
   config 只含结构性字段（rounds/dimensions/background_noise 等）
2. reference_params 列 → 写入 JSON 文件，reference_params 独立列存路径
   格式: [{round_number, reference_params_path}]
3. algorithm_params 列 → 保留在独立列，格式改为按轮分组
   格式: [{round_number, params:[{field_code, field_value}]}]
4. config.rounds[] 中不再包含 algorithmParams / referenceParamsPath

可重复执行（幂等），支持 --dry-run 预览。

用法:
    python migrate_config_to_rounds.py              # 正式执行
    python migrate_config_to_rounds.py --dry-run    # 仅预览，不修改数据库
"""

import json
import os
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

from sqlalchemy import create_engine, text

# ========================================================================
# 配置
# ========================================================================

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666'
    '@localhost:5432/intelligent_audio_test'
)

# reference_params 文件存储目录: 使用项目统一 static 目录 (相对路径)
REF_PARAMS_DIR = os.path.join('static', 'ref_params')

UTC8 = timezone(timedelta(hours=8))

# ========================================================================
# 辅助函数
# ========================================================================

def ensure_ref_dir():
    """确保参考文件目录存在"""
    Path(REF_PARAMS_DIR).mkdir(parents=True, exist_ok=True)


def write_ref_file(case_id: str, round_number: int, content) -> str:
    """将 reference_params 写入文件，返回文件路径"""
    filename = f"{case_id}_round_{round_number}.json"
    filepath = os.path.join(REF_PARAMS_DIR, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(content, f, ensure_ascii=False, indent=2)
    return filepath


def build_round_from_old_config(config: dict, test_type: str) -> dict:
    """
    从旧 config 结构构建单个 RoundConfigItem。
    
    旧 config 顶层字段:
      audios, dimensions, backgroundNoise/background_noise,
      voiceprintRegistration, interferers, roundEvaluation,
      railDistance, volumeLevel, promptAudioId, interruption,
      rounds (旧的多轮配置)
    """
    round_item = {
        'round_number': 1,
        'input_type': 'text' if test_type == 'api' else 'audio',
    }

    # --- 音频配置 ---
    audios = config.get('audios', [])
    if audios:
        round_item['audios'] = audios
        # E2E: 取第一个音频作为干声
        if test_type == 'e2e' and audios:
            first_audio = audios[0]
            round_item['audio_id'] = first_audio.get('audio_id') or first_audio.get('audioId', '')

    # --- 背景噪声 ---
    bg_noise = config.get('backgroundNoise') or config.get('background_noise')
    if bg_noise:
        round_item['background_noise'] = bg_noise

    # --- 等待时间 ---
    round_item['wait_time'] = 5

    # --- 评估维度（从旧 config.dimensions 移入 evaluation） ---
    dimensions = config.get('dimensions', [])
    if dimensions:
        # 兼容: dimensions 可能是扁平数组或 {api:[], e2e:[]} 格式
        if isinstance(dimensions, dict):
            dims = dimensions.get(test_type, [])
        elif isinstance(dimensions, list):
            dims = dimensions
        else:
            dims = []
        if dims:
            round_item['evaluation'] = {
                'enabled': True,
                'dimensions': dims
            }

    # --- 旧的 rounds 配置（如果存在多轮，合并输入信息） ---
    old_rounds = config.get('rounds', [])
    if old_rounds and isinstance(old_rounds, list) and len(old_rounds) > 0:
        # 如果旧结构有多轮，这里只取第一轮的输入信息
        first_old = old_rounds[0]
        round_item['input_type'] = first_old.get('input_type', first_old.get('inputType', round_item.get('input_type', 'text')))
        if first_old.get('input_text') or first_old.get('inputText'):
            round_item['input_text'] = first_old.get('input_text') or first_old.get('inputText')
        if first_old.get('input_audio_id') or first_old.get('inputAudioId'):
            round_item['input_audio_id'] = first_old.get('input_audio_id') or first_old.get('inputAudioId')
        if first_old.get('audio_id') or first_old.get('audioId'):
            round_item['audio_id'] = first_old.get('audio_id') or first_old.get('audioId')
        if first_old.get('wait_time') or first_old.get('waitTime'):
            round_item['wait_time'] = first_old.get('wait_time', first_old.get('waitTime', 5))

    return round_item


def build_rounds_from_old_rounds(old_rounds: list, config: dict, test_type: str) -> list:
    """
    如果旧 config 已有多轮 rounds 配置，逐轮构建。
    将顶层的设备环境/声纹/干扰人等字段复制到每轮（旧设计是用例级）。
    """
    new_rounds = []
    for i, old_round in enumerate(old_rounds):
        if not isinstance(old_round, dict):
            continue

        round_item = {
            'round_number': old_round.get('round_number', old_round.get('roundNumber', old_round.get('order', i + 1))),
            'input_type': old_round.get('input_type', old_round.get('inputType', 'text' if test_type == 'api' else 'audio')),
            'wait_time': old_round.get('wait_time', old_round.get('waitTime', 5)),
        }

        # 输入
        if old_round.get('input_text') or old_round.get('inputText'):
            round_item['input_text'] = old_round.get('input_text') or old_round.get('inputText')
        if old_round.get('input_audio_id') or old_round.get('inputAudioId'):
            round_item['input_audio_id'] = old_round.get('input_audio_id') or old_round.get('inputAudioId')
        if old_round.get('audio_id') or old_round.get('audioId'):
            round_item['audio_id'] = old_round.get('audio_id') or old_round.get('audioId')

        # 从顶层复制结构字段（旧设计中这些是用例级的）
        audios = config.get('audios', [])
        if audios:
            round_item['audios'] = audios

        bg_noise = config.get('backgroundNoise') or config.get('background_noise')
        if bg_noise:
            round_item['background_noise'] = bg_noise

        # 评估
        dimensions = config.get('dimensions', [])
        if isinstance(dimensions, dict):
            dims = dimensions.get(test_type, [])
        elif isinstance(dimensions, list):
            dims = dimensions
        else:
            dims = []
        if dims:
            round_item['evaluation'] = {'enabled': True, 'dimensions': dims}

        new_rounds.append(round_item)

    return new_rounds


def algorithm_params_to_list(algo_params) -> list:
    """
    将 algorithm_params 列的 [{field_code, field_value}, ...] 格式
    或 {field_code: field_value, ...} 格式
    统一转为 [{field_code, field_value}, ...] 列表格式。
    """
    if not algo_params:
        return []
    if isinstance(algo_params, list):
        result = []
        for item in algo_params:
            if isinstance(item, dict):
                code = item.get('field_code') or item.get('fieldCode', '')
                value = item.get('field_value') if 'field_value' in item else item.get('fieldValue')
                if code:
                    result.append({'field_code': code, 'field_value': value})
        return result
    elif isinstance(algo_params, dict):
        result = []
        for code, value in algo_params.items():
            if code:
                result.append({'field_code': code, 'field_value': value})
        return result
    return []


# 旧 config 顶层字段 → algorithm_params field_code 的映射
# key: 旧 config 中的字段名, value: 新 algorithm_params 中的 field_code
_LEGACY_FIELD_TO_ALGO_PARAM = {
    'rail_distance': 'rail_distance',
    'volume_level': 'volume_level',
    'prompt_audio_id': 'prompt_audio_id',
}


def _migrate_legacy_fields_to_algo_params(config: dict) -> list:
    """
    将旧 config 顶层的设备/能力字段转为 algorithm_params 列表项。

    仅处理 case_algorithm_params 表中已定义的字段。
    voiceprint_registration 复合对象拆分为 voiceprint_enabled + voiceprint_audio_id。
    """
    params = []

    for old_field, field_code in _LEGACY_FIELD_TO_ALGO_PARAM.items():
        if old_field in config and config[old_field] is not None:
            params.append({'field_code': field_code, 'field_value': config[old_field]})

    # voiceprint_registration 复合对象拆分
    vp = config.get('voiceprint_registration') or config.get('voiceprintRegistration')
    if vp:
        if isinstance(vp, dict):
            params.append({'field_code': 'voiceprint_enabled', 'field_value': True})
            if vp.get('audio_id') or vp.get('audioId'):
                params.append({'field_code': 'voiceprint_audio_id', 'field_value': vp.get('audio_id') or vp.get('audioId')})
            if vp.get('playback_device_id') or vp.get('playbackDeviceId'):
                params.append({'field_code': 'voiceprint_playback_device_id', 'field_value': vp.get('playback_device_id') or vp.get('playbackDeviceId')})
            if vp.get('spl'):
                params.append({'field_code': 'voiceprint_spl', 'field_value': vp.get('spl')})
        else:
            # 简单布尔值场景
            params.append({'field_code': 'voiceprint_enabled', 'field_value': vp})

    # interferers 干扰人列表
    interferers = config.get('interferers', [])
    if interferers:
        params.append({'field_code': 'interferers', 'field_value': interferers})

    return params


def _merge_algo_params(base_params: list, extra_params: list) -> list:
    """合并两组 algorithmParams 列表，extra 覆盖 base 中同 field_code 的项"""
    merged = {p['field_code']: p['field_value'] for p in base_params}
    for p in extra_params:
        merged[p['field_code']] = p['field_value']
    return [{'field_code': k, 'field_value': v} for k, v in merged.items()]


# ========================================================================
# 主迁移逻辑
# ========================================================================

def migrate(dry_run=False):
    engine = create_engine(POSTGRES_URI)

    ensure_ref_dir()

    with engine.connect() as conn:
        # 查询所有未删除的用例
        rows = conn.execute(text(
            "SELECT id, test_type, config, reference_params, algorithm_params "
            "FROM test_cases WHERE deleted = false"
        )).fetchall()

    total = len(rows)
    migrated = 0
    skipped = 0
    errors = 0

    print(f"\n{'[DRY-RUN] ' if dry_run else ''}共 {total} 条用例待迁移\n")

    for row in rows:
        case_id = row[0]
        test_type = row[1] or 'api'
        config = row[2] or {}
        ref_params_raw = row[3]  # reference_params 列
        algo_params_raw = row[4]  # algorithm_params 列

        # ---- 幂等检查: 如果 config 已经是 rounds-only 格式则跳过 ----
        if 'rounds' in config and not config.get('audios') and not config.get('dimensions'):
            skipped += 1
            continue

        try:
            # ==== Step 1: 构建 rounds ====
            old_rounds = config.get('rounds', [])
            if old_rounds and isinstance(old_rounds, list) and len(old_rounds) > 1:
                # 旧 config 已有多轮 → 逐轮构建
                new_rounds = build_rounds_from_old_rounds(old_rounds, config, test_type)
            else:
                # 单轮 → 将所有顶层打包为一轮
                new_rounds = [build_round_from_old_config(config, test_type)]

            # ==== Step 2: algorithm_params 保留在独立列，按轮分组 ====
            db_algo_params = algorithm_params_to_list(algo_params_raw)
            legacy_algo_params = _migrate_legacy_fields_to_algo_params(config)
            merged_algo_params = _merge_algo_params(db_algo_params, legacy_algo_params)
            # 按轮分组格式: [{round_number, params:[{field_code, field_value}]}]
            algo_params_col = []
            for rd in new_rounds:
                rn = rd.get('round_number', 1)
                algo_params_col.append({
                    'round_number': rn,
                    'params': [p.copy() for p in merged_algo_params]
                })

            # ==== Step 3: reference_params 写入文件，路径存独立列 ====
            ref_params_col = []
            if ref_params_raw:
                # ref_params_raw 可能是 list 或 JSON string
                ref_content = ref_params_raw
                if isinstance(ref_content, str):
                    try:
                        ref_content = json.loads(ref_content)
                    except (json.JSONDecodeError, TypeError):
                        ref_content = None

                if ref_content and isinstance(ref_content, list) and len(ref_content) > 0:
                    for rd in new_rounds:
                        rn = rd.get('round_number', 1)
                        if not dry_run:
                            filepath = write_ref_file(case_id, rn, ref_content)
                            ref_params_col.append({
                                'round_number': rn,
                                'reference_params_path': filepath
                            })
                        else:
                            ref_params_col.append({
                                'round_number': rn,
                                'reference_params_path': f"[DRY-RUN] {REF_PARAMS_DIR}/{case_id}_round_{rn}.json"
                            })

            # ==== Step 4: 组装新 config（rounds + dimensions 顶层，不含 algorithmParams/referenceParamsPath） ====
            new_config = {'rounds': new_rounds}
            # dimensions 提升到 config 顶层（从旧 config.dimensions 或从轮次 evaluation 中提取）
            old_dimensions = config.get('dimensions', [])
            if old_dimensions:
                if isinstance(old_dimensions, dict):
                    new_config['dimensions'] = old_dimensions
                elif isinstance(old_dimensions, list):
                    new_config['dimensions'] = old_dimensions

            # ==== Step 5: 写入数据库（config + 独立列） ====
            if not dry_run:
                with engine.begin() as conn:
                    conn.execute(text(
                        "UPDATE test_cases SET "
                        "  config = :config, "
                        "  algorithm_params = :algo_params, "
                        "  reference_params = :ref_params, "
                        "  updated_at = :now "
                        "WHERE id = :id"
                    ), {
                        'config': json.dumps(new_config, ensure_ascii=False),
                        'algo_params': json.dumps(algo_params_col, ensure_ascii=False) if algo_params_col else None,
                        'ref_params': json.dumps(ref_params_col, ensure_ascii=False) if ref_params_col else None,
                        'now': datetime.now(UTC8),
                        'id': case_id,
                    })

            migrated += 1
            if dry_run or migrated <= 5:
                print(f"  {'[DRY-RUN] ' if dry_run else ''}[OK] {case_id} ({test_type}): "
                      f"{len(new_rounds)} rounds, "
                      f"ref={'yes' if ref_params_raw else 'no'}, "
                      f"algo={'yes' if merged_algo_params else 'no'}")

        except Exception as e:
            errors += 1
            print(f"  [FAIL] {case_id} ({test_type}): {e}")
            import traceback
            traceback.print_exc()

    # ==== 汇总 ====
    print(f"\n{'='*60}")
    print(f"{'[DRY-RUN] ' if dry_run else ''}迁移完成:")
    print(f"  总计: {total}")
    print(f"  已迁移: {migrated}")
    print(f"  跳过(已是新格式): {skipped}")
    print(f"  失败: {errors}")
    if not dry_run:
        print(f"  参考文件目录: {os.path.abspath(REF_PARAMS_DIR)}")


def verify():
    """验证迁移结果"""
    engine = create_engine(POSTGRES_URI)

    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT id, test_type, config, reference_params, algorithm_params "
            "FROM test_cases WHERE deleted = false"
        )).fetchall()

    total = len(rows)
    new_format = 0
    old_format = 0
    has_ref_col = 0
    has_algo_col = 0

    for row in rows:
        config = row[2] or {}
        ref_params = row[3]
        algo_params = row[4]

        # 检查新格式
        if 'rounds' in config and not config.get('audios') and not config.get('dimensions'):
            new_format += 1
        else:
            old_format += 1

        # 检查旧列
        if ref_params:
            has_ref_col += 1
        if algo_params:
            has_algo_col += 1

    print(f"\n验证结果:")
    print(f"  总用例: {total}")
    print(f"  新格式 (rounds-only): {new_format}")
    print(f"  旧格式 (待迁移): {old_format}")
    print(f"  reference_params 列非空: {has_ref_col}")
    print(f"  algorithm_params 列非空: {has_algo_col}")

    # 检查参考文件
    if os.path.exists(REF_PARAMS_DIR):
        ref_files = os.listdir(REF_PARAMS_DIR)
        print(f"  参考文件数: {len(ref_files)}")
        total_size = sum(os.path.getsize(os.path.join(REF_PARAMS_DIR, f)) for f in ref_files if os.path.isfile(os.path.join(REF_PARAMS_DIR, f)))
        print(f"  参考文件总大小: {total_size / 1024:.1f} KB")
    else:
        print(f"  参考文件目录不存在: {REF_PARAMS_DIR}")


# ========================================================================
# 入口
# ========================================================================

if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv

    if dry_run:
        print("=" * 60)
        print("  DRY-RUN 模式 — 不修改数据库")
        print("=" * 60)

    migrate(dry_run=dry_run)

    if not dry_run:
        verify()
