# -*- coding: utf-8 -*-
"""
逐轮话轮评估（turn_eval）维度种子数据（1 主维度 + 6 子维度，INT-192 移植）

蓝本：V9.7.10 backend/scripts/migrations/202606/seed_turn_eval.py（金标对齐后）。
结构金标：运行库实查（2026-10-12，逐项比对维度行/参数/映射/关联/分类）。

层级结构：
  逐轮话轮评估 (main, task_type_code=turn_eval，只配 input + api_settings + param_mappings)
    ├── 逐轮三分类评估 (sub, turn_evaluation)
    ├── 接管率占比     (sub, turn_evaluation)
    ├── 未接管率占比   (sub, turn_evaluation)
    ├── 误接管率占比   (sub, turn_evaluation)
    ├── 接管时延平均值 (sub, turn_evaluation)
    └── 接管内容平均分 (sub, turn_evaluation)

主维度不配 output（只作容器）；子维度 output field_path 映射 turn_eval JSON 响应
（turn_classification.* / tor.tor / false_takeover.* / takeover_latency.* /
reply_quality.* / interaction_text）。param_mappings 只挂主维度，子维度共用。

执行链路：
   用例选 turn_evaluation 子维度 → 平台按 (api_url, parent_dimension_id) 分组
   → task_type 用主维度的 turn_eval，payload 注入 sub_tasks=['turn_evaluation']
   → 调一次 eval_server TurnEvalCalculator → 按 output field_path 分发提取

V9.7.31 适配（与 V9.7.10 蓝本差异）：
   1. INSERT 显式补 sort_order / api_status / estimated_exec_time / agg_denominator /
      exclude_rounds（fresh create_all 库这些 NOT NULL 列无 DB 级 server default，
      裸 SQL INSERT 缺列会 NotNullViolation）；sort_order 取运行库金标值。
   2. UPDATE 不写 status（保留运行库现状；运行库金标中「逐轮三分类评估」status=FALSE，
      幂等对齐不得翻转）。
   3. 子维度 INSERT 也写 api_url（运行库金标子维度均带端点）。
   4. 陈旧参数软删（deleted=TRUE），不物理删除。
   5. 不配 group_key（本族金标 api_settings 本就无 group_key；V9.7.31 组间合并由
      task_dispatcher._merge_dimension_groups 运行时签名合并实现）。

对应 eval_server 服务：
   - turn_eval/strategy.py 一次返回包含 turn_classification/tor/false_takeover/
     takeover_latency/reply_quality/interaction_text 的 JSON

使用方法：
    cd Intelligent-Audio-TEST
    python scripts/migrations/202610/seed_turn_eval.py

依赖：scripts/create_all_tables.py 建表 + scripts/migrations/202609/seed_voice_llm.py
（algorithm_definitions 需已有 voice_llm 行，param_mappings/关联表外键引用）。

注意：此脚本可重复执行（幂等）：已存在的维度/参数/映射/关联原地更新或 SKIP，无重复插入。
"""

import os
import json
from sqlalchemy import create_engine, text

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'
)

# eval_server 微服务地址
API_URL = os.environ.get('EVAL_SERVER_URL', 'http://100.70.20.135:8888')

# 族 → 分类（同族同分组；复用已有分类「话轮接管」）
_CATEGORY_NAME = '话轮接管'
_CATEGORY_ICON = 'fas fa-tachometer-alt'
_CATEGORY_DESC = '话轮接管类评估维度（逐轮话轮评估/三分类/接管率/时延/质量等）'
_CATEGORY_TASK_CODES = ('turn_eval', 'turn_evaluation')

# ============================================================
# 主维度定义：turn_eval（只配 input + api_settings + param_mappings，不配 output）
# ============================================================
MAIN_DIMENSION = {
    'task_type_code': 'turn_eval',
    'name': '逐轮话轮评估',
    'keywords': 'turn_eval,逐轮,三分类,误解管,接管,未接管,turn_evaluation,接管时延,回复质量',
    'description': '逐轮话轮评估主维度：调双路 ASR（user_wav + ai_wav）一次，切分轮次后逐轮三分类（误解管/接管/未接管），仅对"接管"轮计算接管时延和回复质量。主维度只配 input 和映射，不配 output。',
    'type': 'auto',
    'result_type': 0,
    'result_min': 0.0,
    'result_max': 1.0,
    'decimal_places': 2,
    'weight': 1,
    'estimated_exec_time': 60,
    'score_unit': '',
    'statistic_method': 'pass_rate',
    'agg_denominator': 'case',
    'sort_order': 22,
    'body_template': {
        'rounds': [
            {
                'user_wav': '{{user_wav}}',
                'ai_wav': '{{ai_wav}}',
                'played_audios': '{{played_audios}}',
                'query': '{{query}}',
            }
        ]
    },
    'params': [
        # ─── 输入参数（挂在主维度 id 下，子维度通过继承机制使用）───
        ('user_wav', '用户通道音频', '用户通道音频', 'audio', 'input',
         None, None, None, True,
         False, None, '用户通道 wav 路径（cap_client_process_out.wav）', 1),
        ('ai_wav', 'AI回复通道音频', 'AI回复通道音频', 'audio', 'input',
         None, None, None, True,
         False, None, 'AI 回复通道 wav 路径（cap_client_ec_out.wav）', 2),
        ('played_audios', '被播放音频', '被播放音频', 'json', 'input',
         None, None, None, True,
         False, None, '本轮被播放音频列表（用例配置 rounds[].audios），运行时补全上传', 3),
        ('query', '用户提问', '用户提问', 'text', 'input',
         None, None, None, True,
         False, None, '用户提问文本（回复质量评分参考）', 4),
        # 主维度不配 output 参数
    ],
    'param_mappings': [
        # 与库真实运行状态一致：仅 case_config 轮次音频映射（音频路径运行时按维度注入，无需 device 映射）
        ('case_config', 'output', 'audios', 'played_audios', 'none'),
        ('case_config', 'output', 'background_noise', 'background_noise', 'none'),
        ('case_config', 'output', 'interferers', 'interferers', 'none'),
    ],
}

# ============================================================
# 子维度定义：turn_evaluation（只配 output 参数）
# ============================================================
# params 元组顺序：
# (param_code, param_name, label, field_type, param_direction,
#  field_path, agg_role, output_role, visible_in_report,
#  required, default_value, help_text, ui_order, pass_threshold)
# pass_threshold 可选，pass_rate 策略时用，默认 None

SUB_DIMENSIONS = [
    {
        'task_type_code': 'turn_evaluation',  # 子维度独立类型，平台提取后注入 sub_tasks
        'name': '逐轮三分类评估',
        'keywords': 'turn_evaluation,三分类,误解管,接管,未接管,接管时延,回复质量',
        'description': '子维度：逐轮三分类（误解管/接管/未接管）+ 接管时延 + 回复质量。output field_path 映射 turn_eval JSON 响应各字段。',
        'type': 'auto',
        'result_type': 0,
        'result_min': 0.0,
        'result_max': 1.0,
        'decimal_places': 2,
        'weight': 1,
        'estimated_exec_time': 60,
        'score_unit': '',
        'statistic_method': 'pass_rate',
        'agg_denominator': 'round',
        'sort_order': 23,
        'params': [
            # ─── 主评分：误解管数（pass when 0，即无误解管时通过）───
            ('false_takeover_count', '误解管数', '误解管数', 'number', 'output',
             'turn_classification.false_takeover_count', 'pass_eq', 'main', True,
             False, None, '误解管轮次数（0=无误解管=通过）', 10, 0),
            # ─── 三分类汇总 ───
            ('tc_summary', '三分类汇总', '三分类汇总', 'text', 'output',
             'turn_classification.summary', None, 'aux', True,
             False, None, '三分类自然语言汇总（如：正常接管N，未接管M，误解管K）', 11),
            ('normal_takeover_count', '正常接管数', '正常接管数', 'number', 'output',
             'turn_classification.normal_takeover_count', None, 'aux', True,
             False, None, '正常接管轮次数', 12),
            ('no_takeover_count', '未接管数', '未接管数', 'number', 'output',
             'turn_classification.no_takeover_count', None, 'aux', True,
             False, None, '未接管轮次数', 13),
            ('total_turns', '总轮数', '总轮数', 'number', 'output',
             'turn_classification.total_turns', None, 'aux', True,
             False, None, '总轮次数', 14),
            ('tc_turns', '逐轮详情', '逐轮详情', 'json', 'output',
             'turn_classification.turns', None, 'aux', True,
             False, None, '逐轮分类详情（含分类/时延/质量/时间戳）', 15),
            # ─── 兼容旧字段（取最后一轮结果）───
            ('te_tor', '接话率(末轮)', '接话率(末轮)', 'number', 'output',
             'tor.tor', None, 'aux', True,
             False, None, '兼容字段：末轮接话率(0=没接话, 1=接话)', 20),
            ('te_false_takeover', '误接管率(末轮)', '误接管率(末轮)', 'number', 'output',
             'false_takeover.tor', None, 'aux', True,
             False, None, '兼容字段：末轮误接管率(0=未抢话, 1=抢话)', 21),
            ('te_false_takeover_reason', '误接管理由(末轮)', '误接管理由(末轮)', 'text', 'output',
             'false_takeover.reason', None, 'aux', True,
             False, None, '兼容字段：末轮误接管判定理由', 22),
            ('te_takeover_latency_ms', '接管时延(末轮)', '接管时延(末轮)', 'number', 'output',
             'takeover_latency.takeover_latency_ms', None, 'aux', True,
             False, None, '兼容字段：末轮接管时延(毫秒)，正=AI后回复，负=抢话', 23),
            ('te_reply_quality_score', '回复质量得分(末轮)', '回复质量得分(末轮)', 'number', 'output',
             'reply_quality.score', None, 'aux', True,
             False, None, '兼容字段：末轮回复质量评分(1-5分)', 24),
            # ─── 交互内容 ───
            ('te_interaction', '交互内容', '完整交互文字(带时间戳)', 'text', 'output',
             'interaction_text', None, 'aux', True,
             False, None, '用例完整交互文字，query/answer 按时间排序，含 [m:ss; m:ss] 时间戳', 30),
        ],
    },
    # ════════════════════════════════════════════════════════════
    # 接管统计子维度（报告 overview 逐行展示；numerator/denominator 不显示于报告）
    # 依赖 eval_server turn_eval 响应补充的 rate/avg 字段
    # ════════════════════════════════════════════════════════════
    {
        'task_type_code': 'turn_evaluation',
        'name': '接管率占比',
        'keywords': 'turn_evaluation,接管率,takeover_rate,正常接管占比',
        'description': '子维度：接管率占比 = Σ正常接管轮次 / Σ总轮次（ratio 加权聚合，产出 %）。',
        'type': 'auto',
        'result_type': 0,
        'result_min': 0.0,
        'result_max': 1.0,
        'decimal_places': 2,
        'weight': 1,
        'estimated_exec_time': 60,
        'score_unit': '',
        'statistic_method': 'ratio',
        'agg_denominator': 'round',
        'sort_order': 28,
        'params': [
            ('takeover_rate', '接管率占比', '接管率占比', 'number', 'output',
             'turn_classification.takeover_rate', 'main', 'main', True,
             False, None, '接管率占比(0~1)，取每用例整体结果', 1),
            ('normal_takeover_count', '正常接管数(分子)', '正常接管数', 'number', 'output',
             'turn_classification.normal_takeover_count', 'numerator', 'aux', False,
             False, None, 'ratio 分子：正常接管轮次数', 2),
            ('total_turns', '总轮数(分母)', '总轮数', 'number', 'output',
             'turn_classification.total_turns', 'denominator', 'aux', False,
             False, None, 'ratio 分母：总轮次数', 3),
        ],
    },
    {
        'task_type_code': 'turn_evaluation',
        'name': '未接管率占比',
        'keywords': 'turn_evaluation,未接管率,no_takeover_rate,未接管占比',
        'description': '子维度：未接管率占比 = Σ未接管轮次 / Σ总轮次（ratio 加权聚合，产出 %）。',
        'type': 'auto',
        'result_type': 0,
        'result_min': 0.0,
        'result_max': 1.0,
        'decimal_places': 2,
        'weight': 1,
        'estimated_exec_time': 60,
        'score_unit': '',
        'statistic_method': 'ratio',
        'agg_denominator': 'round',
        'sort_order': 29,
        'params': [
            ('no_takeover_rate', '未接管率占比', '未接管率占比', 'number', 'output',
             'turn_classification.no_takeover_rate', 'main', 'main', True,
             False, None, '未接管率占比(0~1)，取每用例整体结果', 1),
            ('no_takeover_count', '未接管数(分子)', '未接管数', 'number', 'output',
             'turn_classification.no_takeover_count', 'numerator', 'aux', False,
             False, None, 'ratio 分子：未接管轮次数', 2),
            ('total_turns', '总轮数(分母)', '总轮数', 'number', 'output',
             'turn_classification.total_turns', 'denominator', 'aux', False,
             False, None, 'ratio 分母：总轮次数', 3),
        ],
    },
    {
        'task_type_code': 'turn_evaluation',
        'name': '误接管率占比',
        'keywords': 'turn_evaluation,误接管率,false_takeover_rate,误解管占比',
        'description': '子维度：误接管率占比 = Σ误解管轮次 / Σ总轮次（ratio 加权聚合，产出 %）。',
        'type': 'auto',
        'result_type': 0,
        'result_min': 0.0,
        'result_max': 1.0,
        'decimal_places': 2,
        'weight': 1,
        'estimated_exec_time': 60,
        'score_unit': '',
        'statistic_method': 'ratio',
        'agg_denominator': 'round',
        'sort_order': 30,
        'params': [
            ('false_takeover_rate', '误接管率占比', '误接管率占比', 'number', 'output',
             'turn_classification.false_takeover_rate', 'main', 'main', True,
             False, None, '误接管率占比(0~1)，取每用例整体结果', 1),
            ('false_takeover_count', '误解管数(分子)', '误解管数', 'number', 'output',
             'turn_classification.false_takeover_count', 'numerator', 'aux', False,
             False, None, 'ratio 分子：误解管轮次数', 2),
            ('total_turns', '总轮数(分母)', '总轮数', 'number', 'output',
             'turn_classification.total_turns', 'denominator', 'aux', False,
             False, None, 'ratio 分母：总轮次数', 3),
        ],
    },
    {
        'task_type_code': 'turn_evaluation',
        'name': '接管时延平均值',
        'keywords': 'turn_evaluation,接管时延,takeover_latency,时延平均',
        'description': '子维度：接管时延平均值 = 所有"接管"轮接管时延的均值（average 聚合，单位 ms）。',
        'type': 'auto',
        'result_type': 0,
        'result_min': 0.0,
        'result_max': 100000.0,
        'decimal_places': 1,
        'weight': 1,
        'estimated_exec_time': 60,
        'score_unit': 'ms',
        'statistic_method': 'average',
        'agg_denominator': 'round',
        'sort_order': 31,
        'params': [
            ('takeover_latency_avg_ms', '接管时延平均值', '接管时延平均值', 'number', 'output',
             'takeover_latency.takeover_latency_avg_ms', 'main', 'main', True,
             False, None, '所有接管轮接管时延均值(ms)，正=AI后回复，负=抢话', 1),
        ],
    },
    {
        'task_type_code': 'turn_evaluation',
        'name': '接管内容平均分',
        'keywords': 'turn_evaluation,接管内容,回复质量,reply_quality,平均分',
        'description': '子维度：接管内容平均分 = 所有"接管"轮回复质量评分的均值（average 聚合，1-5 分）。',
        'type': 'auto',
        'result_type': 0,
        'result_min': 1.0,
        'result_max': 5.0,
        'decimal_places': 2,
        'weight': 1,
        'estimated_exec_time': 60,
        'score_unit': '分',
        'statistic_method': 'average',
        'agg_denominator': 'round',
        'sort_order': 32,
        'params': [
            ('reply_quality_avg_score', '接管内容平均分', '接管内容平均分', 'number', 'output',
             'reply_quality.reply_quality_avg_score', 'main', 'main', True,
             False, None, '所有接管轮回复质量评分均值(1-5分)', 1),
        ],
    },
]

# 子维度 body_template（金标：rounds 含轮次背景噪声/干扰人，运行时按轮注入；
# 子维度自身不发请求，api_settings 仅保持与金标一致）
_SUB_BODY_TEMPLATE = {
    'rounds': [
        {
            'user_wav': '{{user_wav}}',
            'ai_wav': '{{ai_wav}}',
            'played_audios': '{{played_audios}}',
            'background_noise': '{{background_noise}}',
            'interferers': '{{interferers}}',
        }
    ]
}


def _api_settings(dim_def):
    """构建 api_settings dict（金标形态：method/headers/body_template/timeout）。"""
    return {
        'method': 'POST',
        'headers': {},
        'body_template': dim_def.get('body_template', _SUB_BODY_TEMPLATE),
        'timeout': 30000,
    }


# ============================================================
# 数据库操作函数（与 seed_reject_judge 同一口径：软删复活 + 原地更新，无物理删除）
# ============================================================

def _upsert_dimension(conn, dim_def, dimension_type, parent_id=None):
    """注册/更新一个维度，返回 dim_id。dimension_type: 'main' or 'sub'。"""
    task_code = dim_def['task_type_code']
    name = dim_def['name']

    # 按 name 查找（子维度不限定 task_type_code，保证改名后能复用旧记录）
    existing = conn.execute(text(
        "SELECT id FROM dimensions "
        "WHERE name = :name "
        "AND dimension_type = :dtype AND deleted = FALSE"
    ), {'name': name, 'dtype': dimension_type}).fetchone()

    if existing:
        old_tc = conn.execute(text(
            "SELECT task_type_code FROM dimensions WHERE id = :did"
        ), {'did': existing[0]}).scalar()
        if old_tc and old_tc != task_code:
            print(f"  ~ 维度 '{name}' task_type_code 原地对齐: {old_tc} → {task_code} (id={existing[0]})")
            conn.execute(text(
                "UPDATE dimensions SET task_type_code = :tc, updated_at = NOW() WHERE id = :did"
            ), {'tc': task_code, 'did': existing[0]})

    api_settings = json.dumps(_api_settings(dim_def), ensure_ascii=False)
    rule = json.dumps({'rules': [], 'defaultScore': 0}, ensure_ascii=False)

    common_fields = {
        'name': name,
        'kw': dim_def['keywords'],
        'desc': dim_def['description'],
        'type': dim_def['type'],
        'rt': dim_def['result_type'],
        'rmin': dim_def['result_min'],
        'rmax': dim_def['result_max'],
        'dp': dim_def['decimal_places'],
        'w': dim_def['weight'],
        'et': dim_def['estimated_exec_time'],
        'su': dim_def['score_unit'],
        'sm': dim_def['statistic_method'],
        'ad': dim_def.get('agg_denominator', 'case'),
        'apis': api_settings,
        'rule': rule,
        'dtype': dimension_type,
        'pid': parent_id,
    }

    if existing:
        dim_id = existing[0]
        print(f"  - {dimension_type} 维度已存在 (id={dim_id}, name={name})，更新")
        if dimension_type == 'main':
            conn.execute(text(
                "UPDATE dimensions SET "
                "  name = :name, keywords = :kw, description = :desc, "
                "  type = :type, result_type = :rt, result_min = :rmin, "
                "  result_max = :rmax, decimal_places = :dp, weight = :w, "
                "  estimated_exec_time = :et, score_unit = :su, "
                "  statistic_method = :sm, agg_denominator = :ad, "
                "  api_settings = :apis, "
                "  rule = :rule, dimension_type = :dtype, "
                "  parent_dimension_id = :pid, api_url = :api_url, "
                "  deleted = FALSE, updated_at = NOW() "
                "WHERE id = :did"
            ), {**common_fields, 'api_url': API_URL, 'did': dim_id})
        else:
            conn.execute(text(
                "UPDATE dimensions SET "
                "  name = :name, keywords = :kw, description = :desc, "
                "  type = :type, result_type = :rt, result_min = :rmin, "
                "  result_max = :rmax, decimal_places = :dp, weight = :w, "
                "  estimated_exec_time = :et, score_unit = :su, "
                "  statistic_method = :sm, agg_denominator = :ad, "
                "  api_settings = :apis, "
                "  rule = :rule, dimension_type = :dtype, "
                "  parent_dimension_id = :pid, "
                "  deleted = FALSE, updated_at = NOW() "
                "WHERE id = :did"
            ), {**common_fields, 'did': dim_id})
    else:
        # 显式补 NOT NULL 无 DB 级 server default 的列（fresh create_all 库）：
        # sort_order / estimated_exec_time / api_status / agg_denominator / status / deleted
        if dimension_type == 'main':
            result = conn.execute(text(
                "INSERT INTO dimensions "
                "  (name, keywords, dimension_type, parent_dimension_id, task_type_code, description, "
                "   type, result_type, result_min, result_max, decimal_places, "
                "   weight, estimated_exec_time, rule, api_settings, status, "
                "   api_status, score_unit, statistic_method, agg_denominator, api_url, "
                "   sort_order, exclude_rounds, deleted, created_at, updated_at) "
                "VALUES "
                "  (:name, :kw, :dtype, :pid, :tc, :desc, "
                "   :type, :rt, :rmin, :rmax, :dp, "
                "   :w, :et, :rule, :apis, TRUE, "
                "   'online', :su, :sm, :ad, :api_url, "
                "   :sort, '[]', FALSE, NOW(), NOW()) "
                "RETURNING id"
            ), {**common_fields, 'tc': task_code, 'api_url': API_URL,
                'sort': dim_def.get('sort_order', 0)})
        else:
            result = conn.execute(text(
                "INSERT INTO dimensions "
                "  (name, keywords, dimension_type, parent_dimension_id, task_type_code, description, "
                "   type, result_type, result_min, result_max, decimal_places, "
                "   weight, estimated_exec_time, rule, api_settings, status, "
                "   api_status, score_unit, statistic_method, agg_denominator, api_url, "
                "   sort_order, exclude_rounds, deleted, created_at, updated_at) "
                "VALUES "
                "  (:name, :kw, :dtype, :pid, :tc, :desc, "
                "   :type, :rt, :rmin, :rmax, :dp, "
                "   :w, :et, :rule, :apis, TRUE, "
                "   'online', :su, :sm, :ad, :api_url, "
                "   :sort, '[]', FALSE, NOW(), NOW()) "
                "RETURNING id"
            ), {**common_fields, 'tc': task_code, 'api_url': API_URL,
                'sort': dim_def.get('sort_order', 0)})
        dim_id = result.fetchone()[0]
        print(f"  + {dimension_type} 维度已插入 (id={dim_id}, name={name})")
    return dim_id


def _cleanup_stale_params(conn, dim_id, dim_def):
    """软清理 DB 中当前 dim_def.params 不再出现的 param_code。"""
    current_output_codes = {p[0] for p in dim_def['params'] if p[4] == 'output'}
    current_input_codes = {p[0] for p in dim_def['params'] if p[4] == 'input'}
    for direction, current_codes in (
        ('output', current_output_codes),
        ('input', current_input_codes),
    ):
        if not current_codes:
            stale = conn.execute(text(
                "SELECT param_code FROM evaluation_dimension_params "
                "WHERE dimension_id = :did AND param_direction = :dir "
                "AND deleted = FALSE"
            ), {'did': dim_id, 'dir': direction}).fetchall()
            if stale:
                stale_codes = [r[0] for r in stale]
                print(f"  ! 清理已废弃 {direction} 参数: {stale_codes}")
                conn.execute(text(
                    "UPDATE evaluation_dimension_params SET "
                    "  deleted = TRUE, updated_at = NOW() "
                    "WHERE dimension_id = :did AND param_direction = :dir"
                ), {'did': dim_id, 'dir': direction})
            continue
        placeholders = ','.join(f':c{i}' for i in range(len(current_codes)))
        bind = {f'c{i}': code for i, code in enumerate(current_codes)}
        stale = conn.execute(text(
            "SELECT param_code FROM evaluation_dimension_params "
            "WHERE dimension_id = :did AND param_direction = :dir "
            f"AND param_code NOT IN ({placeholders}) "
            "AND deleted = FALSE"
        ), {'did': dim_id, 'dir': direction, **bind}).fetchall()
        if stale:
            stale_codes = [r[0] for r in stale]
            print(f"  ! 清理已废弃 {direction} 参数: {stale_codes}")
            stale_placeholders = ','.join(f':s{i}' for i in range(len(stale_codes)))
            stale_bind = {f's{i}': code for i, code in enumerate(stale_codes)}
            conn.execute(text(
                "UPDATE evaluation_dimension_params SET "
                "  deleted = TRUE, updated_at = NOW() "
                "WHERE dimension_id = :did AND param_direction = :dir "
                f"AND param_code IN ({stale_placeholders})"
            ), {'did': dim_id, 'dir': direction, **stale_bind})


def _upsert_params(conn, dim_id, dim_def):
    """注册/更新维度的 params。"""
    print(f"  --- 注册参数 (dimension_id={dim_id}) ---")
    _cleanup_stale_params(conn, dim_id, dim_def)

    inserted = 0
    updated = 0
    for dp in dim_def['params']:
        (param_code, param_name, label, field_type, param_direction,
         field_path, agg_role, output_role, visible_in_report,
         required, default_value, help_text, ui_order, *rest) = dp
        pass_threshold = rest[0] if rest else None

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
                "  default_value = :dv, pass_threshold = :pt, help_text = :ht, ui_order = :uo, "
                "  deleted = FALSE, updated_at = NOW() "
                "WHERE id = :id"
            ), {
                'pn': param_name, 'lb': label, 'ft': field_type,
                'fp': field_path, 'ar': agg_role, 'or': output_role,
                'vir': visible_in_report, 'req': required,
                'dv': default_value, 'pt': pass_threshold,
                'ht': help_text, 'uo': ui_order,
                'id': existing[0],
            })
            updated += 1
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
            ), {
                'did': dim_id, 'pc': param_code, 'pn': param_name,
                'lb': label, 'ft': field_type, 'dir': param_direction,
                'fp': field_path, 'ar': agg_role, 'or': output_role,
                'vir': visible_in_report, 'req': required,
                'dv': default_value, 'pt': pass_threshold,
                'ht': help_text, 'uo': ui_order,
            })
            inserted += 1
    print(f"  插入 {inserted} 条，更新 {updated} 条")


def _upsert_relation(conn, dim_id):
    """注册 voice_llm → 维度关联（幂等）。"""
    existing = conn.execute(text(
        "SELECT id, deleted FROM algorithm_dimension_relations "
        "WHERE algorithm_type = 'voice_llm' AND dimension_id = :did"
    ), {'did': dim_id}).fetchone()
    if existing:
        if existing[1]:
            conn.execute(text(
                "UPDATE algorithm_dimension_relations SET deleted = FALSE, updated_at = NOW() "
                "WHERE id = :id"
            ), {'id': existing[0]})
            print(f"  ~ 关联 voice_llm → dim {dim_id} 已软删，重新激活")
        else:
            print(f"  - 关联 voice_llm → dim {dim_id} 已存在，跳过")
    else:
        conn.execute(text(
            "INSERT INTO algorithm_dimension_relations "
            "  (algorithm_type, dimension_id, is_default, weight, "
            "   deleted, created_at, updated_at) "
            "VALUES "
            "  ('voice_llm', :did, FALSE, 1.0, FALSE, NOW(), NOW())"
        ), {'did': dim_id})
        print(f"  + 关联 voice_llm → dim {dim_id} 已插入")


def _upsert_param_mappings(conn, dim_id, dim_def):
    """注册 voice_llm → 维度的 param_mappings（幂等）。只在主维度配，子维度共用。"""
    print(f"  --- 注册 param_mappings (dimension_id={dim_id}) ---")
    inserted = 0
    updated = 0
    for m in dim_def.get('param_mappings', []):
        (source, source_direction, source_param, target_param,
         transform_type) = m
        existing = conn.execute(text(
            "SELECT id FROM param_mappings "
            "WHERE algorithm_type = 'voice_llm' AND source = :src "
            "AND source_param = :sp AND dimension_id = :did"
        ), {'src': source, 'sp': source_param, 'did': dim_id}).fetchone()
        if existing:
            conn.execute(text(
                "UPDATE param_mappings SET "
                "  target_param = :tp, transform_type = :tt, "
                "  deleted = FALSE, updated_at = NOW() "
                "WHERE id = :id"
            ), {'tp': target_param, 'tt': transform_type, 'id': existing[0]})
            updated += 1
        else:
            conn.execute(text(
                "INSERT INTO param_mappings "
                "  (algorithm_type, source, source_direction, source_param, "
                "   dimension_id, target_param, transform_type, "
                "   deleted, created_at, updated_at) "
                "VALUES "
                "  ('voice_llm', :src, :sd, :sp, :did, :tp, :tt, "
                "   FALSE, NOW(), NOW())"
            ), {
                'src': source, 'sd': source_direction, 'sp': source_param,
                'did': dim_id, 'tp': target_param, 'tt': transform_type,
            })
            inserted += 1
    print(f"  插入 {inserted} 条，更新 {updated} 条")


def _assign_dimension_category(conn):
    """幂等：确保族分类存在（复用已有「话轮接管」），并把族内所有维度 category_id 回填。"""
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

    placeholders = ','.join(f':tc{i}' for i in range(len(_CATEGORY_TASK_CODES)))
    bind = {f'tc{i}': tc for i, tc in enumerate(_CATEGORY_TASK_CODES)}
    dims = conn.execute(text(
        "SELECT id, name FROM dimensions "
        f"WHERE task_type_code IN ({placeholders}) AND deleted = FALSE ORDER BY id"
    ), bind).fetchall()
    for dim_id, dim_name in dims:
        conn.execute(text(
            "UPDATE dimensions SET category_id = :cid, updated_at = NOW() WHERE id = :did"
        ), {'cid': cat_id, 'did': dim_id})
    print(f"  ~ 已回填 {len(dims)} 个维度 → category_id={cat_id}（{_CATEGORY_NAME}）")


def seed_turn_eval():
    engine = create_engine(POSTGRES_URI)

    with engine.begin() as conn:
        # ============================================================
        # Step 1: 注册/更新 turn_eval 主维度
        # ============================================================
        print(f"\n{'=' * 60}")
        print("  Step 1: 注册 turn_eval 主维度")
        print(f"{'=' * 60}")
        main_id = _upsert_dimension(conn, MAIN_DIMENSION, dimension_type='main', parent_id=None)
        print(f"  主维度 id = {main_id}")
        _upsert_params(conn, main_id, MAIN_DIMENSION)
        _upsert_relation(conn, main_id)
        _upsert_param_mappings(conn, main_id, MAIN_DIMENSION)

        # ============================================================
        # Step 2: 注册子维度 turn_evaluation
        # ============================================================
        print(f"\n{'=' * 60}")
        print(f"  Step 2: 注册子维度（parent_dimension_id={main_id}）")
        print(f"{'=' * 60}")
        for sub_def in SUB_DIMENSIONS:
            print(f"\n  -- 子维度: {sub_def['name']} --")
            sub_id = _upsert_dimension(conn, sub_def, dimension_type='sub', parent_id=main_id)
            print(f"  子维度 id = {sub_id}")
            _upsert_params(conn, sub_id, sub_def)
            _upsert_relation(conn, sub_id)
            # 子维度不配 param_mappings，共用主维度的 mappings

        # ============================================================
        # Step 3: 分类分配（同族同分组）
        # ============================================================
        print(f"\n{'=' * 60}")
        print(f"  Step 3: 分类分配（{_CATEGORY_NAME}）")
        print(f"{'=' * 60}")
        _assign_dimension_category(conn)

        # ============================================================
        # Step 4: 验证结果
        # ============================================================
        print(f"\n{'=' * 60}")
        print("  Step 4: 验证结果")
        print(f"{'=' * 60}")
        placeholders = ','.join(f':tc{i}' for i in range(len(_CATEGORY_TASK_CODES)))
        bind = {f'tc{i}': tc for i, tc in enumerate(_CATEGORY_TASK_CODES)}
        result = conn.execute(text(
            "SELECT id, name, dimension_type, parent_dimension_id, status "
            "FROM dimensions "
            f"WHERE task_type_code IN ({placeholders}) AND deleted = FALSE "
            "ORDER BY sort_order, id"
        ), bind).fetchall()

        print(f"\n  逐轮话轮评估维度结构（共 {len(result)} 个活跃维度）:")
        for r in result:
            dim_id, name, dtype, parent_id, status = r
            parent_name = ""
            if parent_id:
                p = conn.execute(text(
                    "SELECT name FROM dimensions WHERE id = :pid"
                ), {'pid': parent_id}).fetchone()
                parent_name = f" → parent: {p[0]}" if p else f" → parent_id: {parent_id}"
            print(f"    [{dtype:4s}] id={dim_id:4d}  status={status}  {name}{parent_name}")

        print(f"\n{'=' * 60}")
        print("  逐轮话轮评估（turn_eval）维度种子数据注册完成")
        print(f"{'=' * 60}")


if __name__ == '__main__':
    print("=" * 60)
    print("逐轮话轮评估（turn_eval）维度种子数据注册 — INT-192 移植")
    print("=" * 60)
    print()
    print(f"数据库: {POSTGRES_URI[:POSTGRES_URI.rindex('@')]}@localhost/...")
    print()
    print("此脚本将：")
    print("1. 注册/更新 turn_eval 主维度（dimension_type=main，无 output）")
    print("   配置 input params + api_settings + param_mappings")
    print("2. 注册/更新 turn_evaluation 子维度（dimension_type=sub）6 个：")
    print("   - 逐轮三分类评估 / 接管率占比 / 未接管率占比 / 误接管率占比")
    print("   - 接管时延平均值 / 接管内容平均分")
    print("3. 注册 voice_llm → 主维度 + 子维度的关联")
    print("4. 分类分配：全族 category_id → 话轮接管")
    print()
    print("脚本可重复执行（幂等）：运行库执行为原地更新/SKIP，无重复插入；")
    print("UPDATE 不写 status（保留运行库现状）。")
    print()
    seed_turn_eval()
    print()
    print("完成！")
