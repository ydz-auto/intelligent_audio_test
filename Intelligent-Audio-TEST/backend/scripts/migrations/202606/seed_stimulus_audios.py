# -*- coding: utf-8 -*-
"""
轮次结构化音频（played_audios / background_noise / interferers）维度参数种子脚本

背景：
   用例配置承载本轮播放音频（激励音频 audios、背景噪声 background_noise、
   干扰人 algorithm_params.interferers）。评估服务通过参数映射
   source=case_config 取用这些字段，注入到评估维度 input 参数。

功能（幂等，可重复执行）：
1. 给所有启用中的主维度（dimension_type='main'，deleted=FALSE）
   - 注册/更新 input 参数 played_audios / background_noise / interferers
     （field_type='json'，required=FALSE）
   - 注册/更新参数映射 case_config → audios/background_noise/interferers
     → 对应 input 参数（挂主维度 id）
2. 将历史 stimulus_audios 参数与映射目标归一化为 played_audios
3. 不清理、不删除任何已有参数/映射（区别于维度 seed 的 _cleanup_stale_params）
4. 不做维度创建/删除，仅扩展主维度参数与映射

用途：
   - get_dimension_params 接口返回上述参数，前端维度参数下拉可选中
   - evaluation_service 在评估映射含 case_config source 时组装 case.config，
     经 _build_rounds_list / _build_evaluation_params 按轮映射为对应参数，
     音频路径运行时经 _normalize_round_eval_fields 补全并 multipart 上传、
     eval_server 落盘还原

对应实现：
   - backend/utils/algorithm/case_parameter_extractor.py  case_config 分支 + _normalize_round_eval_fields
   - backend/services/evaluation/evaluation_service.py    _build_case_config / _build_rounds_list
   - backend/services/evaluation/api_request_handler.py   _extract_nested_files
   - eval_server/app/controllers/api.py                   _restore_multipart_placeholders

使用方法：
    cd Intelligent-Audio-TEST
    python backend/scripts/migrations/202606/seed_stimulus_audios.py

注意：此脚本可重复执行（幂等）
"""

import sys
import os
from sqlalchemy import create_engine, text

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'
)

ALGORITHM_TYPE = os.environ.get('ALGO_TYPE', 'voice_llm')

# ============================================================
# 轮次结构化音频参数定义
# (param_code, param_name, label, field_type, param_direction,
#  field_path, agg_role, output_role, visible_in_report,
#  required, default_value, help_text, ui_order)
# ============================================================
AUDIO_PARAMS = (
    (
        'played_audios', '被播放音频', '被播放音频', 'json', 'input',
        None, None, None, True,
        False, None,
        '本轮被播放音频（用例配置 rounds[].audios，含 audio_id/spl/play_order，'
        'audio_path 由评估链路运行时补全上传），评估时经 case_config→audios 映射取用', 3,
    ),
    (
        'background_noise', '背景噪声', '背景噪声', 'json', 'input',
        None, None, None, True,
        False, None,
        '本轮背景噪声配置（轮次级 background_noise，缺省时取用例级全局 background_noise），'
        '评估时经 case_config→background_noise 映射取用', 4,
    ),
    (
        'interferers', '干扰人', '干扰人', 'json', 'input',
        None, None, None, True,
        False, None,
        '本轮干扰人音频列表（algorithm_params.interferers，评估前提升为轮级字段），'
        '评估时经 case_config→interferers 映射取用', 5,
    ),
)

# 参数映射 (source, source_direction, source_param, target_param, transform_type)
# source_param 与 AUDIO_PARAMS 一一对应（case_config 轮级的结构化字段名）
AUDIO_MAPPINGS = (
    ('case_config', 'output', 'audios', 'played_audios', 'none'),
    ('case_config', 'output', 'background_noise', 'background_noise', 'none'),
    ('case_config', 'output', 'interferers', 'interferers', 'none'),
)


def _find_main_dimensions(conn):
    """查询所有启用中的主维度。"""
    rows = conn.execute(text(
        "SELECT d.id, d.name, d.task_type_code "
        "FROM dimensions d "
        "WHERE d.deleted = FALSE AND d.dimension_type = 'main' "
        "  AND (parent_dimension_id IS NULL) "
        "ORDER BY d.id"
    )).fetchall()
    return rows


def _rename_legacy_fields(conn):
    """将历史 stimulus_audios 参数和映射目标归一化为 played_audios。"""
    conn.execute(text(
        "UPDATE evaluation_dimension_params "
        "SET param_code = 'played_audios', updated_at = NOW() "
        "WHERE param_code = 'stimulus_audios'"
    ))
    conn.execute(text(
        "UPDATE param_mappings "
        "SET target_param = 'played_audios', updated_at = NOW() "
        "WHERE target_param = 'stimulus_audios'"
    ))


def _upsert_param(conn, dim_id, param_def):
    """注册/更新单个 input 参数（幂等，不清其他参数）。

    param_def 顺序与 _upsert_param 解构一致（见 AUDIO_PARAMS 注释）。
    """
    (param_code, param_name, label, field_type, param_direction,
     field_path, agg_role, output_role, visible_in_report,
     required, default_value, help_text, ui_order, *rest) = param_def

    existing = conn.execute(text(
        "SELECT id FROM evaluation_dimension_params "
        "WHERE dimension_id = :did AND param_code = :pc "
        "AND param_direction = :dir"
    ), {'did': dim_id, 'pc': param_code, 'dir': param_direction}).fetchone()

    if existing:
        conn.execute(text(
            "UPDATE evaluation_dimension_params SET "
            "  param_name = :pn, label = :lb, field_type = :ft, "
            "  field_path = :fp, agg_role = :ar, output_role = :or, "
            "  visible_in_report = :vir, required = :req, "
            "  default_value = :dv, help_text = :ht, ui_order = :uo, "
            "  deleted = FALSE, updated_at = NOW() "
            "WHERE id = :id"
        ), {
            'pn': param_name, 'lb': label, 'ft': field_type,
            'fp': field_path, 'ar': agg_role, 'or': output_role,
            'vir': visible_in_report, 'req': required,
            'dv': default_value, 'ht': help_text, 'uo': ui_order,
            'id': existing[0],
        })
        print(f"    ~ param {param_code} 已更新 (id={existing[0]})")
    else:
        conn.execute(text(
            "INSERT INTO evaluation_dimension_params "
            "  (dimension_id, param_code, param_name, label, field_type, "
            "   param_direction, field_path, agg_role, output_role, "
            "   visible_in_report, required, default_value, help_text, "
            "   ui_order, deleted, created_at, updated_at) "
            "VALUES "
            "  (:did, :pc, :pn, :lb, :ft, "
            "   :dir, :fp, :ar, :or, "
            "   :vir, :req, :dv, :ht, "
            "   :uo, FALSE, NOW(), NOW())"
        ), {
            'did': dim_id, 'pc': param_code, 'pn': param_name,
            'lb': label, 'ft': field_type, 'dir': param_direction,
            'fp': field_path, 'ar': agg_role, 'or': output_role,
            'vir': visible_in_report, 'req': required,
            'dv': default_value, 'ht': help_text, 'uo': ui_order,
        })
        print(f"    + param {param_code} 已插入 (dimension_id={dim_id})")


def _upsert_mapping(conn, dim_id, mapping_def):
    """注册/更新 case_config → source_param → target_param 映射（幂等）。"""
    (source, source_direction, source_param, target_param,
     transform_type) = mapping_def
    existing = conn.execute(text(
        "SELECT id FROM param_mappings "
        "WHERE algorithm_type = :at AND source = :src "
        "AND source_param = :sp AND dimension_id = :did"
    ), {'at': ALGORITHM_TYPE, 'src': source, 'sp': source_param, 'did': dim_id}).fetchone()
    if existing:
        conn.execute(text(
            "UPDATE param_mappings SET "
            "  target_param = :tp, transform_type = :tt, "
            "  deleted = FALSE, updated_at = NOW() "
            "WHERE id = :id"
        ), {'tp': target_param, 'tt': transform_type, 'id': existing[0]})
        print(f"    ~ mapping case_config→{source_param} 已更新 (id={existing[0]})")
    else:
        conn.execute(text(
            "INSERT INTO param_mappings "
            "  (algorithm_type, source, source_direction, source_param, "
            "   dimension_id, target_param, transform_type, "
            "   deleted, created_at, updated_at) "
            "VALUES "
            "  (:at, :src, :sd, :sp, :did, :tp, :tt, "
            "   FALSE, NOW(), NOW())"
        ), {
            'at': ALGORITHM_TYPE, 'src': source, 'sd': source_direction,
            'sp': source_param, 'did': dim_id, 'tp': target_param,
            'tt': transform_type,
        })
        print(f"    + mapping case_config→{source_param} 已插入 (dimension_id={dim_id})")


def seed_audio_params():
    engine = create_engine(POSTGRES_URI)

    with engine.begin() as conn:
        _rename_legacy_fields(conn)
        dims = _find_main_dimensions(conn)
        if not dims:
            print("  未找到启用中的主维度，跳过")
            return
        print(f"  将处理 {len(dims)} 个主维度:")
        for dim_id, name, tc in dims:
            print(f"    - id={dim_id}, name={name}, task_type_code={tc}")

        for dim_id, name, tc in dims:
            print(f"\n  -- 维度 id={dim_id} ({name}) --")
            for param_def in AUDIO_PARAMS:
                _upsert_param(conn, dim_id, param_def)
            for mapping_def in AUDIO_MAPPINGS:
                _upsert_mapping(conn, dim_id, mapping_def)


if __name__ == '__main__':
    print("=" * 60)
    print("轮次结构化音频维度参数种子数据注册")
    print("  (played_audios / background_noise / interferers)")
    print("=" * 60)
    print()
    print(f"数据库: {POSTGRES_URI[:POSTGRES_URI.rindex('@')]}@localhost/...")
    print(f"算法类型: {ALGORITHM_TYPE}")
    print()
    print("此脚本将：")
    print("1. 给所有启用中的主维度注册 input 参数 played_audios / background_noise / interferers")
    print("   （field_type=json, required=False）")
    print("2. 注册参数映射 case_config → audios / background_noise / interferers")
    print("3. 将历史 stimulus_audios 参数与映射目标归一化为 played_audios")
    print("4. 不创建/删除维度，不清理其他参数/映射（幂等）")
    print()
    print("执行链路：前端映射 case_config → 用例配置 rounds[].{audios,background_noise,"
          "interferers}")
    print("→ evaluation_service 按轮组装 case.config（audio_path 运行时补全）")
    print("→ api_request_handler multipart 上传 → eval_server 占位符还原为本地文件")
    print()
    print("脚本可重复执行（幂等）")
    print()

    confirm = input("是否继续？(y/N): ").strip().lower()
    if confirm != 'y':
        print("已取消")
        sys.exit(0)

    try:
        seed_audio_params()
    except Exception as e:
        print(f"\n迁移失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)