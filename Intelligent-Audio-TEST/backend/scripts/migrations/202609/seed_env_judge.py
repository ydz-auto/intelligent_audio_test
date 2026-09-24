# -*- coding: utf-8 -*-
"""
环境理解（env_judge）维度种子脚本

背景：
   环境理解族评估"模型对环境音内容的理解"：模型回复音频(ai_wav) + 用户通道音频(user_wav)
   + 被播放音频(played_audios) + 参考答案(correctAnswer)/脚本类型(task_type)，
   由 LLM 判定理解正确性 / 本地时序计算回复时延。评估经 eval_server 的
   env_judge 计算器执行，输出 understand_correct_pass / response_latency_ms / score 等。

功能（幂等，可重复执行）：
1. 注册/更新 env_judge 主维度（133 环境理解准确率 / 134 平均回复时延 / 135 环境理解评分）
2. 注册共享输入参数（ai_wav/user_wav/played_audios/correctAnswer/task_type/model/max_tokens/temperature）
   与各维度输出参数（main + aux）
3. 注册 case_config → audios/background_noise/interferers 映射（轮次结构化音频，与运行时一致）
4. 注册 voice_llm → 维度关联
5. 不做维度创建/删除，仅 upsert（与库真实运行状态对齐）

对应实现：
   - eval_server/app/services/calculators/xiaoyi_metrics/env_judge/  env_judge 计算器
   - evaluation_service 经 case_config 组装轮次音频、device/case 注入 played_audios 等

使用方法：
    cd Intelligent-Audio-TEST
    python backend/scripts/migrations/202609/seed_env_judge.py
"""

import sys
import os
import json
from sqlalchemy import create_engine, text

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'
)

ALGORITHM_TYPE = os.environ.get('ALGO_TYPE', 'voice_llm')
API_URL = os.environ.get('EVAL_SERVER_URL', 'http://100.70.20.135:8888')
TASK_TYPE = 'env_judge'
GROUP_KEY = 'env_judge_v2'

# 族 → 分类（同族同分组）
_CATEGORY_NAME = '环境理解'
_CATEGORY_ICON = 'fas fa-headphones'
_CATEGORY_DESC = '环境理解类评估维度（环境音理解准确率/回复时延/评分）'

# ============================================================
# 共享输入参数（所有主维度一致）
# ============================================================
_INPUT_PARAMS = [
    ('ai_wav', '模型回复音频', '模型回复音频路径(被判定对象)', 'audio', 'input',
     None, None, None, True,
     False, None, '模型回复音频路径，裁判 LLM 直接听回复音频 + ASR 提取回复内容/首字时间戳', 5),
    ('user_wav', '用户通道音频', '用户通道音频路径', 'audio', 'input',
     None, None, None, True,
     False, None, '用户通道音频(含环境声+用户询问)，ASR 词级时间戳用于定位用户询问结束时间', 6),
    ('played_audios', '被播放音频', '被播放音频', 'json', 'input',
     None, None, None, True,
     False, None, '本轮被播放音频（用例配置 rounds[].audios，含 audio_id/spl/audio_path），'
                  '评估时经 case_config→audios 映射取用，env_judge 计算器按轮取首位作为原始环境声做对齐', 7),
    ('background_noise', '背景噪声', '背景噪声', 'json', 'input',
     None, None, None, True,
     False, None, '本轮背景噪声配置（轮次级 background_noise），'
                  '评估时经 case_config→background_noise 映射取用', 21),
    ('interferers', '干扰人', '干扰人', 'json', 'input',
     None, None, None, True,
     False, None, '本轮干扰人音频列表（algorithm_params.interferers），'
                  '评估时经 case_config→interferers 映射取用', 22),
    ('correctAnswer', '正确答案', '环境音参考内容文本', 'text', 'input',
     None, None, None, True,
     False, None, '环境音参考内容文本（正确答案），作为 LLM 判定模型理解是否正确的参考标准', 8),
    ('task_type', '脚本类型', '脚本类型', 'number', 'input',
     None, None, None, True,
     False, '0', '脚本类型: 0=无语义(non_semantic, 环境声为噪声判断声音类型), 1=有语义(semantic, 判断内容理解)', 9),
    ('model', 'LLM模型', 'LLM 模型名(覆盖默认)', 'text', 'input',
     None, None, None, False,
     False, None, '覆盖 config.LLM_JUDGE.default_model，留空用默认(注意:默认gpt-4o-mini不支持音频)', 10),
    ('max_tokens', '最大token', '最大输出 token 数', 'number', 'input',
     None, None, None, False,
     False, '4096', 'LLM 最大输出 token 数', 15),
    ('temperature', '采样温度', '采样温度', 'number', 'input',
     None, None, None, False,
     False, '0.1', '采样温度，评判场景建议低温 0.1', 20),
]

# 轮次结构化音频映射（case_config）：与库一致，三个 input 参数（played_audios/
# background_noise/interferers）均有对应映射，映射 target 均落在 input 参数上
_AUDIO_MAPPINGS = [
    ('case_config', 'output', 'audios', 'played_audios', 'none'),
    ('case_config', 'output', 'background_noise', 'background_noise', 'none'),
    ('case_config', 'output', 'interferers', 'interferers', 'none'),
]

# body_template（与库 api_settings 一致）
_BODY_TEMPLATE = {
    'model': '{{model}}',
    'rounds': [
        {
            'ai_wav': '{{ai_wav}}',
            'user_wav': '{{user_wav}}',
            'played_audios': '{{played_audios}}',
            'correctAnswer': '{{correctAnswer}}',
        }
    ],
    'task_type': '{{task_type}}',
    'max_tokens': '{{max_tokens}}',
    'temperature': '{{temperature}}',
}

# ============================================================
# 主维度定义（3 个 main，无子维度）
# ============================================================
_MAIN_DIMENSIONS_DEF = [
    {
        'name': '环境理解准确率',
        'keywords': 'env_judge,understand_correct_pass,环境理解准确率,环境音理解',
        'description': '环境理解裁判主维度：模型对环境音内容理解正确的比例。由 LLM 判定 understand_correct（评分4分及以上为正确），'
                       'understand_correct_pass=1 为达标。LLM 判定失败(understand_correct 为空)的轮次不参与统计。'
                       '报告按 pass_rate 聚合（按轮次）：达标轮次数 / 有值轮次数 × 100，产出准确率(%)。',
        'result_type': 0, 'result_min': 0.0, 'result_max': 100.0, 'decimal_places': 2,
        'weight': 1, 'estimated_exec_time': 120, 'score_unit': '%',
        'statistic_method': 'pass_rate', 'agg_denominator': 'round',
        'output_params': [
            ('score', '环境理解评分', '环境理解评分', 'number', 'output',
             'score', 'value', 'main', True,
             False, None, 'LLM 1-5 评分（有语义场景参考主指标）', 60),
            ('understand_correct_pass', '环境理解准确率', '环境理解准确率', 'number', 'output',
             'understand_correct_pass', 'pass_eq', 'main', True,
             False, '0', '达标轮次数/有值轮次数×100；达标=understand_correct_pass=1', 60, 1.0),
            ('understand_correct', '理解正确标记', '理解正确标记', 'boolean', 'output',
             'understand_correct', None, 'aux', True,
             False, None, 'LLM 判定的理解正确标记(True/False)', 61),
            ('reason', '判定理由', '判定理由', 'text', 'output',
             'reason', None, 'aux', True,
             False, None, 'LLM 判定理由', 62),
            ('ai_answer', '模型回答ASR', '模型回答ASR', 'text', 'output',
             'ai_answer', None, 'aux', True,
             False, None, '模型回复的 ASR 文本', 63),
            ('script_type', '脚本类型', '脚本类型', 'text', 'output',
             'script_type', None, 'aux', True,
             False, None, 'non_semantic(无语义)/semantic(有语义)', 64),
            ('tokens_used', '裁判Token消耗', '裁判Token消耗', 'number', 'output',
             'tokens_used', None, 'aux', True,
             False, None, '本次 LLM 调用 token 数', 65),
            ('message', '计算说明', '计算说明', 'text', 'output',
             'message', None, 'aux', True,
             False, None, 'OK 或错误原因', 66),
        ],
    },
    {
        'name': '平均回复时延',
        'keywords': 'env_judge,response_latency_ms,平均回复时延,环境音回复时延',
        'description': '环境理解裁判主维度：用户询问结束到模型首字开始的平均时延(毫秒)。本地时序计算'
                       '（FFT 互相关定位环境声 + ASR 词级时间戳），非 LLM 判定。计算失败(response_latency_ms 为空)的轮次不参与统计。'
                       '报告按 average 聚合：Σ(response_latency_ms) / 有值用例数，产出毫秒均值。',
        'result_type': 1, 'result_min': 0.0, 'result_max': None, 'decimal_places': 0,
        'weight': 1, 'estimated_exec_time': 120, 'score_unit': 'ms',
        'statistic_method': 'average', 'agg_denominator': 'case',
        'output_params': [
            ('response_latency_ms', '平均回复时延', '平均回复时延', 'number', 'output',
             'response_latency_ms', 'value', 'main', True,
             False, None, '用户询问结束→模型首字的时延(毫秒)', 60),
            ('env_sound_start_ms', '环境声起始', '环境声起始', 'number', 'output',
             'env_sound_start_ms', None, 'aux', True,
             False, None, '环境声在 user_wav 中的起始时间(毫秒)', 61),
            ('env_sound_end_ms', '环境声结束', '环境声结束', 'number', 'output',
             'env_sound_end_ms', None, 'aux', True,
             False, None, '环境声在 user_wav 中的结束时间(毫秒)', 62),
            ('user_question_end_ms', '用户询问结束', '用户询问结束', 'number', 'output',
             'user_question_end_ms', None, 'aux', True,
             False, None, '用户询问结束时间(毫秒)', 63),
            ('model_first_word_start_ms', '模型首字开始', '模型首字开始', 'number', 'output',
             'model_first_word_start_ms', None, 'aux', True,
             False, None, '模型首字开始时间(毫秒)', 64),
            ('ncc', '对齐NCC', '对齐NCC', 'number', 'output',
             'ncc', None, 'aux', True,
             False, None, 'FFT 互相关对齐的归一化互相关值', 65),
        ],
    },
    {
        'name': '环境理解评分',
        'keywords': 'env_judge,score,环境理解评分,环境音理解评分,语义理解评分',
        'description': '环境理解裁判主维度（有语义场景）：LLM 对环境音内容理解程度的 1-5 评分均值。'
                       'LLM 判定失败(score 为空)的轮次不参与统计。'
                       '报告按 average 聚合：Σ(score) / 有值用例数，产出平均分(分)。',
        'result_type': 0, 'result_min': 1.0, 'result_max': 5.0, 'decimal_places': 2,
        'weight': 1, 'estimated_exec_time': 120, 'score_unit': '分',
        'statistic_method': 'average', 'agg_denominator': 'case',
        'output_params': [
            ('score', '环境理解评分', '环境理解评分', 'number', 'output',
             'score', 'value', 'main', True,
             False, None, 'LLM 1-5 评分均值（有语义场景主指标）', 60),
            ('understand_correct', '理解正确标记', '理解正确标记', 'boolean', 'output',
             'understand_correct', None, 'aux', True,
             False, None, 'LLM 判定的理解正确标记(True/False)', 61),
            ('reason', '判定理由', '判定理由', 'text', 'output',
             'reason', None, 'aux', True,
             False, None, 'LLM 判定理由', 62),
            ('ai_answer', '模型回答ASR', '模型回答ASR', 'text', 'output',
             'ai_answer', None, 'aux', True,
             False, None, '模型回复的 ASR 文本', 63),
            ('script_type', '脚本类型', '脚本类型', 'text', 'output',
             'script_type', None, 'aux', True,
             False, None, 'non_semantic(无语义)/semantic(有语义)', 64),
            ('tokens_used', '裁判Token消耗', '裁判Token消耗', 'number', 'output',
             'tokens_used', None, 'aux', True,
             False, None, '本次 LLM 调用 token 数', 65),
            ('message', '计算说明', '计算说明', 'text', 'output',
             'message', None, 'aux', True,
             False, None, 'OK 或错误原因', 66),
        ],
    },
]


def _upsert_dimension(conn, dim_def):
    """按 name 匹配主维度（env_judge 三个主维度 task_type_code 相同，必须按 name 唯一匹配），
    避免定义错位；不存在则新建。"""
    name = dim_def['name']
    api_settings = json.dumps({
        'method': 'POST',
        'headers': {},
        'body_template': _BODY_TEMPLATE,
        'timeout': 30000,
        'group_key': GROUP_KEY,
    }, ensure_ascii=False)
    rule = json.dumps({'rules': [], 'defaultScore': 0}, ensure_ascii=False)

    existing = conn.execute(text(
        "SELECT id FROM dimensions "
        "WHERE name = :name AND dimension_type = 'main' "
        "AND parent_dimension_id IS NULL AND deleted = FALSE"
    ), {'name': name}).fetchone()

    fields = {
        'name': name,
        'kw': dim_def['keywords'],
        'desc': dim_def['description'],
        'rt': dim_def['result_type'],
        'rmin': dim_def['result_min'],
        'rmax': dim_def['result_max'],
        'dp': dim_def['decimal_places'],
        'w': dim_def['weight'],
        'et': dim_def['estimated_exec_time'],
        'su': dim_def['score_unit'],
        'sm': dim_def['statistic_method'],
        'ad': dim_def['agg_denominator'],
        'apis': api_settings,
        'rule': rule,
    }

    if existing:
        dim_id = existing[0]
        print(f"  - main 维度已存在 (id={dim_id}, name={name})，更新")
        conn.execute(text(
            "UPDATE dimensions SET "
            "  name = :name, keywords = :kw, description = :desc, "
            "  result_type = :rt, result_min = :rmin, result_max = :rmax, "
            "  decimal_places = :dp, weight = :w, estimated_exec_time = :et, "
            "  score_unit = :su, statistic_method = :sm, agg_denominator = :ad, "
            "  api_settings = :apis, rule = :rule, api_url = :api_url, "
            "  task_type_code = :tc, "
            "  deleted = FALSE, updated_at = NOW() "
            "WHERE id = :did"
        ), {**fields, 'api_url': API_URL, 'tc': TASK_TYPE, 'did': dim_id})
    else:
        result = conn.execute(text(
            "INSERT INTO dimensions "
            "  (name, keywords, dimension_type, parent_dimension_id, task_type_code, description, "
            "   type, result_type, result_min, result_max, decimal_places, "
            "   weight, estimated_exec_time, rule, api_settings, status, "
            "   api_status, score_unit, statistic_method, agg_denominator, api_url, "
            "   deleted, created_at, updated_at) "
            "VALUES "
            "  (:name, :kw, 'main', NULL, :tc, :desc, "
            "   'auto', :rt, :rmin, :rmax, :dp, "
            "   :w, :et, :rule, :apis, TRUE, "
            "   'online', :su, :sm, :ad, :api_url, "
            "   FALSE, NOW(), NOW()) "
            "RETURNING id"
        ), {**fields, 'tc': TASK_TYPE, 'api_url': API_URL})
        dim_id = result.fetchone()[0]
        print(f"  + main 维度已插入 (id={dim_id}, name={name})")
    return dim_id


def _upsert_params(conn, dim_id, dim_def):
    """注册/更新维度参数（共享输入 + 各维度输出），软删行复活；并清理该维度上
    不在定义内的陈旧参数（软删，保证与运行时状态精确一致）。"""
    params = list(_INPUT_PARAMS) + list(dim_def['output_params'])
    for p in params:
        (param_code, param_name, label, field_type, param_direction,
         field_path, agg_role, output_role, visible_in_report,
         required, default_value, help_text, ui_order, *rest) = p
        pass_threshold = rest[0] if rest else None

        existing = conn.execute(text(
            "SELECT id FROM evaluation_dimension_params "
            "WHERE dimension_id = :did AND param_code = :pc AND param_direction = :dir"
        ), {'did': dim_id, 'pc': param_code, 'dir': param_direction}).fetchone()

        if existing:
            conn.execute(text(
                "UPDATE evaluation_dimension_params SET "
                "  param_name = :pn, label = :lb, field_type = :ft, "
                "  field_path = :fp, agg_role = :ar, output_role = :or, "
                "  visible_in_report = :vir, required = :req, "
                "  default_value = :dv, pass_threshold = :pt, help_text = :ht, ui_order = :uo, "
                "  deleted = FALSE, updated_at = NOW() "
                "WHERE id = :id"
            ), {'pn': param_name, 'lb': label, 'ft': field_type,
                'fp': field_path, 'ar': agg_role, 'or': output_role,
                'vir': visible_in_report, 'req': required,
                'dv': default_value, 'pt': pass_threshold,
                'ht': help_text, 'uo': ui_order, 'id': existing[0]})
        else:
            conn.execute(text(
                "INSERT INTO evaluation_dimension_params "
                "  (dimension_id, param_code, param_name, label, field_type, "
                "   param_direction, field_path, agg_role, output_role, "
                "   visible_in_report, required, default_value, pass_threshold, help_text, "
                "   ui_order, deleted, created_at, updated_at) "
                "VALUES "
                "  (:did, :pc, :pn, :lb, :ft, "
                "   :dir, :fp, :ar, :or, "
                "   :vir, :req, :dv, :pt, :ht, "
                "   :uo, FALSE, NOW(), NOW())"
            ), {'did': dim_id, 'pc': param_code, 'pn': param_name,
                'lb': label, 'ft': field_type, 'dir': param_direction,
                'fp': field_path, 'ar': agg_role, 'or': output_role,
                'vir': visible_in_report, 'req': required,
                'dv': default_value, 'pt': pass_threshold,
                'ht': help_text, 'uo': ui_order})
    print(f"    params {len(params)} 条已注册 (dimension_id={dim_id})")

    # 清理陈旧参数（软删定义外的残留，如历史上误配/历史版本遗留）
    expected = {(p[0], p[4]) for p in params}
    stale = conn.execute(text(
        "SELECT id, param_code FROM evaluation_dimension_params "
        "WHERE dimension_id = :did AND deleted = FALSE"
    ), {'did': dim_id}).fetchall()
    cleaned = 0
    for pid, pcode in stale:
        if (pcode, 'input') not in expected and (pcode, 'output') not in expected:
            conn.execute(text(
                "UPDATE evaluation_dimension_params SET deleted = TRUE, updated_at = NOW() "
                "WHERE id = :id"
            ), {'id': pid})
            print(f"    ~ 清理陈旧参数 {pcode} (id={pid})")
            cleaned += 1
    if cleaned:
        print(f"    * 软删陈旧参数 {cleaned} 条 (dimension_id={dim_id})")


def _upsert_mappings(conn, dim_id):
    """注册 case_config → audios/background_noise/interferers 映射（与运行时一致）。"""
    for (source, source_direction, source_param, target_param, transform_type) in _AUDIO_MAPPINGS:
        existing = conn.execute(text(
            "SELECT id FROM param_mappings "
            "WHERE algorithm_type = :at AND source = :src "
            "AND source_param = :sp AND dimension_id = :did"
        ), {'at': ALGORITHM_TYPE, 'src': source, 'sp': source_param, 'did': dim_id}).fetchone()
        if existing:
            conn.execute(text(
                "UPDATE param_mappings SET target_param = :tp, transform_type = :tt, "
                "  source_direction = :sd, deleted = FALSE, updated_at = NOW() "
                "WHERE id = :id"
            ), {'tp': target_param, 'tt': transform_type, 'sd': source_direction, 'id': existing[0]})
        else:
            conn.execute(text(
                "INSERT INTO param_mappings "
                "  (algorithm_type, source, source_direction, source_param, "
                "   dimension_id, target_param, transform_type, "
                "   deleted, created_at, updated_at) "
                "VALUES "
                "  (:at, :src, :sd, :sp, :did, :tp, :tt, FALSE, NOW(), NOW())"
            ), {'at': ALGORITHM_TYPE, 'src': source, 'sd': source_direction,
                'sp': source_param, 'did': dim_id, 'tp': target_param, 'tt': transform_type})


def _upsert_relation(conn, dim_id, dim_name):
    """注册 voice_llm → 维度关联（幂等，软删复活）。"""
    existing = conn.execute(text(
        "SELECT id, deleted FROM algorithm_dimension_relations "
        "WHERE algorithm_type = :at AND dimension_id = :did"
    ), {'at': ALGORITHM_TYPE, 'did': dim_id}).fetchone()
    if existing:
        if existing[1]:
            conn.execute(text(
                "UPDATE algorithm_dimension_relations SET deleted = FALSE, updated_at = NOW() "
                "WHERE id = :id"
            ), {'id': existing[0]})
            print(f"  ~ 关联 '{dim_name}' (id={dim_id}) 已软删，重新激活")
        else:
            print(f"  - 关联 '{dim_name}' (id={dim_id}) 已存在")
    else:
        conn.execute(text(
            "INSERT INTO algorithm_dimension_relations "
            "  (algorithm_type, dimension_id, is_default, weight, deleted, created_at, updated_at) "
            "VALUES "
            "  (:at, :did, FALSE, 1.0, FALSE, NOW(), NOW())"
        ), {'at': ALGORITHM_TYPE, 'did': dim_id})
        print(f"  + 关联 '{dim_name}' (id={dim_id}) 已插入")


def _assign_dimension_category(conn):
    """幂等：确保族分类存在，并把族内所有维度 category_id 回填为该分类。"""
    row = conn.execute(text(
        "SELECT id, deleted FROM categories WHERE name = :name"
    ), {'name': _CATEGORY_NAME}).fetchone()
    if row:
        cat_id = row[0]
        conn.execute(text(
            "UPDATE categories SET description = :desc, icon = :icon, "
            "deleted = FALSE, deleted_at = NULL, updated_at = NOW() WHERE id = :cid"
        ), {'desc': _CATEGORY_DESC, 'icon': _CATEGORY_ICON, 'cid': cat_id})
        print(f"  ~ 分类已存在并更新: id={cat_id}, name={_CATEGORY_NAME}")
    else:
        res = conn.execute(text(
            "INSERT INTO categories (name, description, icon, created_at, updated_at, deleted) "
            "VALUES (:name, :desc, :icon, NOW(), NOW(), FALSE) RETURNING id"
        ), {'name': _CATEGORY_NAME, 'desc': _CATEGORY_DESC, 'icon': _CATEGORY_ICON})
        cat_id = res.fetchone()[0]
        print(f"  + 分类已插入: id={cat_id}, name={_CATEGORY_NAME}")

    dims = conn.execute(text(
        "SELECT id, name FROM dimensions "
        "WHERE task_type_code = :tc AND deleted = FALSE ORDER BY id"
    ), {'tc': TASK_TYPE}).fetchall()
    for dim_id, dim_name in dims:
        conn.execute(text(
            "UPDATE dimensions SET category_id = :cid, updated_at = NOW() WHERE id = :did"
        ), {'cid': cat_id, 'did': dim_id})
    print(f"  ~ 已回填 {len(dims)} 个维度 → category_id={cat_id}（{_CATEGORY_NAME}）")


def seed_env_judge():
    engine = create_engine(POSTGRES_URI)
    with engine.begin() as conn:
        for dim_def in _MAIN_DIMENSIONS_DEF:
            print(f"\n-- 维度: {dim_def['name']} --")
            dim_id = _upsert_dimension(conn, dim_def)
            _upsert_params(conn, dim_id, dim_def)
            _upsert_mappings(conn, dim_id)
            _upsert_relation(conn, dim_id, dim_def['name'])
        print("\n-- 分类分配（环境理解）--")
        _assign_dimension_category(conn)
        print("\nenv_judge 维度种子数据注册完成")


if __name__ == '__main__':
    print("=" * 60)
    print("环境理解（env_judge）维度种子数据注册")
    print("=" * 60)
    print()
    print(f"数据库: {POSTGRES_URI[:POSTGRES_URI.rindex('@')]}@localhost/...")
    print(f"算法类型: {ALGORITHM_TYPE}")
    print(f"eval_server: {API_URL}")
    print()
    print("此脚本将：")
    print("1. 注册/更新 env_judge 主维度（133 环境理解准确率 / 134 平均回复时延 / 135 环境理解评分）")
    print("2. 注册共享输入参数 + 各维度输出参数（main/aux）")
    print("3. 注册 case_config 轮次音频映射")
    print("4. 注册 voice_llm 算法-维度关联")
    print()
    print("脚本可重复执行（幂等）")
    print()

    confirm = input("是否继续？(y/N): ").strip().lower()
    if confirm != 'y':
        print("已取消")
        sys.exit(0)

    try:
        seed_env_judge()
    except Exception as e:
        print(f"\n迁移失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
