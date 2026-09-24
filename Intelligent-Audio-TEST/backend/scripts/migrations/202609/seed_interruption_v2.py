# -*- coding: utf-8 -*-
"""
打断指标 v2 维度种子（11 主维度 + 「打断时延」容器 1 主 3 子，全族合并一次请求）

背景（重构规划见 Obsidian 04-工作安排/打断指标重构.md）：
   - 「打断成功率」(主+4子，纯本地时序) 与「打断场景裁判」(主+11子，独立 LLM 维度)
     合并为统一的 interruption_metrics v2：eval_server 本地时序 + 进程内直调
     逐轮 LLM 五分类（回复/恢复/无关/静默/询问），整例一次 LLM 调用。
   - 旧「打断成功率」维度取消，spec 指标除时延归一个容器维度外全部为主维度。

功能（幂等，可重复执行）：
1. Step 0 物理删除旧树（先删后建，避免子维度按 name 匹配复活旧行）：
   - interruption_metrics 旧主维度（打断成功率/打断指标，排除本 seed 新族名字）+ 其子树
   - interruption_judge（打断场景裁判）+ 其子树
   - 引用旧维度的历史 TestResultDimension 行级联物理删除（软删数据直接移除）
2. Step 1 注册 11 个主维度（task_type_code 全部 = interruption_metrics）：
   成功/失败/询问数量、回复/恢复/无关/静默/询问行为数量、
   回复内容评分、停止指令遵循、恢复首轮内容评分
   数量类主维度（成功/失败/询问/5 个行为数量）statistic_method='ratio'、
   score_unit='%'、agg_denominator='round'（按轮次）：报告按
   Σ数量 / Σ该维度有值轮次数 × 100 聚合为占比比例。
3. Step 2 注册「打断时延」容器主维度（仿 turn_taking：只配 input+映射，无自身 output）
   + 3 个子维度：响应时延 / 回复时延 / 恢复首轮内容时延
4. 全族 api_settings 写入 group_key='interruption_v2' + 同一份 body_template：
   evaluation_service 按 (endpoint_url, group_key) 合并为一组，
   任选维度组合都只发一次 eval_server 请求、只做一次 LLM 判定
5. 每个主维度都配全量 input params + param_mappings
   （映射按选中维度 id 过滤，任一维度单独被选/作组代表都可用）
6. 注册 voice_llm → 全部维度关联（algorithm_dimension_relations）

使用方法：
    cd Intelligent-Audio-TEST
    python backend/scripts/migrations/202609/seed_interruption_v2.py

    # 另一个库（两个库都要跑）：
    DATABASE_URI=postgresql://user:pwd@host:5432/db EVAL_SERVER_URL=http://... \
        python backend/scripts/migrations/202609/seed_interruption_v2.py
"""

import sys
import os
import json
from sqlalchemy import create_engine, text

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'
)

# eval_server 微服务地址（本机 5002 / 线上 100.70.20.135:8888）
API_URL = os.environ.get('EVAL_SERVER_URL', 'http://100.70.20.135:8888')

TASK_TYPE = 'interruption_metrics'
GROUP_KEY = 'interruption_v2'

# 族 → 分类（同族同分组）
_CATEGORY_NAME = '打断'
_CATEGORY_ICON = 'fas fa-hand-paper'
_CATEGORY_DESC = '打断类评估维度（打断成功/失败/时延/停止指令遵循/恢复内容等）'

# ============================================================
# 全族同一份 body_template（组代表任取安全）
# 顶层字段兼容单轮/平台切片路径；rounds 承载多轮音频/ASR/轮次标记
# ============================================================
BODY_TEMPLATE = {
    'user_wav': '{{user_wav}}',
    'ai_wav': '{{ai_wav}}',
    'case_wav': '{{case_wav}}',
    'user_asr': '{{user_asr}}',
    'model_asr': '{{model_asr}}',
    'user_seg_merge_gap_s': '{{user_seg_merge_gap_s}}',
    'model_seg_merge_gap_s': '{{model_seg_merge_gap_s}}',
    'round_number': '{{round_number}}',
    'stop_intent': '{{stop_intent}}',
    'is_actual_interruption': '{{is_actual_interruption}}',
    'interruption_rounds': '{{interruption_rounds}}',
    'dangling_interruption_rounds': '{{dangling_interruption_rounds}}',
    'rounds': [
        {
            'user_wav': '{{user_wav}}',
            'ai_wav': '{{ai_wav}}',
            'case_wav': '{{case_wav}}',
            'user_asr': '{{user_asr}}',
            'model_asr': '{{model_asr}}',
            'query': '{{query}}',
            'is_return_to_topic': '{{is_return_to_topic}}',
            'is_interruption': '{{is_interruption}}',
            'is_actual_interruption': '{{is_actual_interruption}}',
            'stop_intent': '{{stop_intent}}',
            'played_audios': '{{played_audios}}',
            'background_noise': '{{background_noise}}',
            'interferers': '{{interferers}}',
        }
    ],
}

API_SETTINGS = json.dumps({
    'method': 'POST',
    'headers': {},
    'body_template': BODY_TEMPLATE,
    'timeout': 30000,
    # 跨主维度合并分组：evaluation_service 按 (endpoint_url, group_key) 一组一请求
    'group_key': GROUP_KEY,
}, ensure_ascii=False)

RULE = json.dumps({'rules': [], 'defaultScore': 0}, ensure_ascii=False)

# ============================================================
# 族公共 input 参数（挂每个主维度；子维度经继承机制使用容器主维度的）
# params 元组顺序:
# (param_code, param_name, label, field_type, param_direction,
#  field_path, agg_role, output_role, visible_in_report,
#  required, default_value, help_text, ui_order[, pass_threshold])
# ============================================================
_COMMON_INPUT_PARAMS = [
    ('played_audios', '被播放音频', '被播放音频', 'json', 'input',
     None, None, None, True,
     False, None, '本轮被播放音频（用例配置 rounds[].audios）；FFT 互相关精修打断轮定位窗口用', 3),
    ('background_noise', '背景噪声', '背景噪声', 'json', 'input',
     None, None, None, True,
     False, None, '本轮背景噪声配置（轮次级 background_noise，缺省取用例级全局）', 4),
    ('user_wav', '用户打断音频', '用户打断语音 wav', 'audio', 'input',
     None, None, None, True,
     False, None, '用户打断语音 wav 路径；eval_server 内部调 asr_server 转 ASR 词级时间戳', 5),
    ('ai_wav', '模型恢复音频', '模型恢复语音 wav', 'audio', 'input',
     None, None, None, True,
     False, None, '模型恢复语音 wav 路径；与 user_wav 各调一次 ASR 后对齐算打断', 6),
    ('user_asr', '用户词级ASR', '用户词级ASR时间戳列表', 'json', 'input',
     None, None, None, False,
     False, None, '已有用户词级 ASR 时可直接传入，格式由 eval_server interruption_metrics 兼容解析。', 7),
    ('model_asr', '模型词级ASR', '模型词级ASR时间戳列表', 'json', 'input',
     None, None, None, False,
     False, None, '已有模型词级 ASR 时可直接传入，格式由 eval_server interruption_metrics 兼容解析。', 8),
    ('case_wav', '用例干净音源', '用例干净音源', 'audio', 'input',
     None, None, None, False,
     False, None, '兼容旧字段：干净打断音源 wav；v2 优先读 played_audios，本字段仅回退用', 9),
    ('user_seg_merge_gap_s', '用户侧合并间隙', '用户侧词合并为段的间隙阈值(秒)', 'number', 'input',
     None, None, None, False,
     False, '1.5', '用户侧相邻词时间戳间隙小于该值则合并为同一段(秒)，默认1.5', 11),
    ('model_seg_merge_gap_s', '模型侧合并间隙', '模型侧词合并为段的间隙阈值(秒)', 'number', 'input',
     None, None, None, False,
     False, '0.7', '模型侧合并间隙(秒)，默认0.7，更敏感以识别打断后短停顿+恢复', 12),
    ('rounds', '多轮轮次', '多轮对话音频/ASR及打断控制元数据', 'json', 'input',
     None, None, None, False,
     False, None,
     '多轮轮次列表；每轮可包含 user_wav/ai_wav、user_asr/model_asr、played_audios、'
     'is_interruption、is_actual_interruption、stop_intent、is_return_to_topic 及 query/answer 等字段。'
     'is_interruption 表示当前轮不等待模型完成，实际打断轮是下一轮；末轮未闭合标记由 dangling_interruption_rounds 记录。', 13),
    ('round_number', '当前轮次', '当前评估的轮索引', 'number', 'input',
     None, None, None, False,
     False, None, '逐轮评估时由平台传入；单轮切片路径用。', 14),
    ('is_actual_interruption', '实际打断模式', '是否按实际打断轮计算', 'boolean', 'input',
     None, None, None, False,
     False, None, '显式传入时按有效实际打断轮聚合；未传入时保持兼容模式。', 17),
    ('interruption_rounds', '实际打断轮次', '有效实际打断轮索引列表', 'json', 'input',
     None, None, None, False,
     False, None, '由平台轮次元数据生成的有效实际打断轮索引；数量类指标的分母。', 18),
    ('dangling_interruption_rounds', '未闭合打断轮次', '末轮未闭合打断标记列表', 'json', 'input',
     None, None, None, False,
     False, None, '末轮 is_interruption=true 且没有下一轮可承接时记录，不参与数量/时延统计。', 19),
    ('stop_intent', '停止指令意图', '是否为停止指令实际轮', 'boolean', 'input',
     None, None, None, False,
     False, None, '显式停止指令标记；不从 is_interruption 推断。停止指令遵循仅停止类用例计算，由族内 LLM 判定。', 20),
    ('interferers', '干扰人', '干扰人', 'json', 'input',
     None, None, None, True,
     False, None, '本轮干扰人音频列表（algorithm_params.interferers，评估前提升为轮级字段）', 21),
    ('query', '用户提问', '用户提问', 'text', 'input',
     None, None, None, False,
     False, None, '用户提问文本（reference.query 映射取用，打断内容评分/回复质量参考）', 22),
    ('is_return_to_topic', '是否回到原话题', '是否回到原话题', 'boolean', 'input',
     None, None, None, False,
     False, None, '该轮是否回到原话题（case.is_return_to_topic 用例参数映射取用，打断行为统计参考）', 23),
]

# 每个主维度全量挂载（映射提取按选中维度 id 过滤，见 case_parameter_extractor）
_PARAM_MAPPINGS = [
    ('device', 'output', 'user_wav', 'user_wav', 'none'),
    ('device', 'output', 'ai_wav', 'ai_wav', 'none'),
    ('device', 'output', 'case_wav', 'case_wav', 'none'),
    ('reference', 'output', 'query', 'query', 'none'),
    ('case', 'output', 'is_return_to_topic', 'is_return_to_topic', 'none'),
    ('case_config', 'output', 'audios', 'played_audios', 'none'),
    ('case_config', 'output', 'background_noise', 'background_noise', 'none'),
    ('case_config', 'output', 'interferers', 'interferers', 'none'),
]


def _out(code, name, path, help_text, ui_order, role='main', agg='value',
         field_type='number', pass_threshold=None):
    """构造 output 参数元组（main 或 aux）。"""
    p = (code, name, name, field_type, 'output', path, agg, role, True,
         False, None, help_text, ui_order)
    return p + ((pass_threshold,) if pass_threshold is not None else ())


def _count_dim(name, code, behavior_help, ui_order, extra_out=()):
    """数量类主维度：ratio/%（Σ数量/Σ分母，分母口径=按轮次），main=对应 count 字段，
    extra_out 追加 aux。分母来自该维度有值的轮次数（interruption.round_details 每轮判定）。"""
    return {
        'task_type_code': TASK_TYPE,
        'name': name,
        'keywords': f'interruption,{code},{name},barge-in',
        'description': f'打断指标 v2 主维度：{name}。{behavior_help}'
                       '由族内同一次 LLM 逐轮五分类判定派生（回复=成功；恢复/无关/静默=失败；询问=询问）；'
                       'LLM 降级时为空（不当作 0）。'
                       f'报告按 ratio 聚合（按轮次）：Σ{name} / Σ有值轮次数 × 100，产出占比(%)。',
        'type': 'auto',
        'result_type': 0, 'result_min': 0.0, 'result_max': None,
        'decimal_places': 0, 'weight': 1, 'estimated_exec_time': 120,
        'score_unit': '%', 'statistic_method': 'ratio', 'agg_denominator': 'round',
        'params': _COMMON_INPUT_PARAMS + [
            _out(code, name, f'interruption.{code}', behavior_help, ui_order),
            *extra_out,
        ],
        'param_mappings': _PARAM_MAPPINGS,
    }


# ============================================================
# 11 个主维度（spec 19 项指标中除时延外全部为主维度）
# ============================================================
MAIN_DIMENSIONS = [
    # ── 成功数量：额外承载 case_type/message/round_details 等 aux 诊断 ──
    _count_dim(
        '打断成功数量', 'success_count',
        '行为「回复」（正常响应打断内容）的轮数，与「打断回复行为数量」同值。', 10,
        extra_out=[
            _out('case_type', '用例类型', 'interruption.case_type',
                 '7 类之一：single/single_stop/multi/stop_resume_single/stop_resume_multi/'
                 'topic_resume_single/topic_resume_multi；由轮次标记推导，无有效实际轮为空。',
                 11, role='aux', agg=None, field_type='text'),
            _out('case_type_label', '用例类型标签', 'interruption.case_type_label',
                 '用例类型中文名。', 12, role='aux', agg=None, field_type='text'),
            _out('interruption_message', '打断指标说明', 'interruption.message',
                 '计算说明；含 LLM 行为判定/时序锚定降级标注。', 13,
                 role='aux', agg=None, field_type='text'),
            _out('round_details', '逐轮明细', 'interruption.round_details',
                 '每个实际打断轮/恢复轮的时序锚定(anchor_method/定位窗口/时延)+行为分类+三维评分明细表。',
                 14, role='aux', agg=None, field_type='json'),
        ],
    ),
    _count_dim('打断失败数量', 'failure_count',
               '行为「恢复+无关+静默」的轮数合计。', 20),
    _count_dim('打断询问数量', 'inquiry_count',
               '行为「询问」的轮数，与「打断询问行为数量」同值。', 21),
    _count_dim('打断回复行为数量', 'reply_behavior_count',
               '行为「回复」：正常响应打断内容的轮数。', 22),
    _count_dim('打断恢复行为数量', 'recover_behavior_count',
               '行为「恢复」：说穿不停、或停后续说原内容的轮数。', 23),
    _count_dim('打断无关行为数量', 'irrelevant_behavior_count',
               '行为「无关」：与打断内容及前文均无关的轮数。', 24),
    _count_dim('打断静默行为数量', 'silence_behavior_count',
               '行为「静默」：打断后不再产生任何有意义回复的轮数。', 25),
    _count_dim('打断询问行为数量', 'ask_behavior_count',
               '行为「询问」：反问/确认打断意图的轮数。', 26),
    # ── 回复内容评分：LLM 逐轮 overall 均值 + LLM 诊断 aux ──
    {
        'task_type_code': TASK_TYPE,
        'name': '打断回复内容评分',
        'keywords': 'interruption,reply_content_score,打断回复内容评分,内容评分',
        'description': '打断指标 v2 主维度：各实际打断轮 LLM 内容综合评分(0-5)的均值。'
                       '逐轮三维评分（连贯性/相关性/适应性）明细见「打断成功数量」的逐轮明细 aux。'
                       'LLM 降级时为空。',
        'type': 'auto',
        'result_type': 0, 'result_min': 0.0, 'result_max': 5.0,
        'decimal_places': 2, 'weight': 1, 'estimated_exec_time': 120,
        'score_unit': '分', 'statistic_method': 'average',
        'params': _COMMON_INPUT_PARAMS + [
            _out('reply_content_score', '打断回复内容评分', 'interruption.reply_content_score',
                 '各实际打断轮 LLM 内容综合评分(0-5)的均值；无可判定轮为空。', 30),
            _out('interaction_text', '交互内容', 'interruption.interaction_text',
                 '用例完整交互文字（带时间戳），LLM 判定的输入时间线。', 31,
                 role='aux', agg=None, field_type='text'),
            _out('llm_round_evaluations', 'LLM逐轮判定', 'interruption.llm_round_evaluations',
                 'LLM 逐轮输出：行为分类+理由+三维评分+停止遵从。', 32,
                 role='aux', agg=None, field_type='json'),
            _out('llm_judge_model', '裁判模型', 'interruption.llm_judge_model',
                 '本次行为判定使用的 LLM 模型名。', 33,
                 role='aux', agg=None, field_type='text'),
            _out('tokens_used', '裁判Token消耗', 'interruption.tokens_used',
                 '本次行为判定 LLM 调用 token 数。', 34, role='aux', agg=None),
        ],
        'param_mappings': _PARAM_MAPPINGS,
    },
    # ── 停止指令遵循：仅停止类用例计算，pass_rate(pass_eq=1) 聚合为百分比 ──
    {
        'task_type_code': TASK_TYPE,
        'name': '停止指令遵循',
        'keywords': 'interruption,stop_compliance,停止指令遵循,停止遵从',
        'description': '打断指标 v2 主维度：显式停止指令轮中模型遵从停止的比例（LLM 逐停止轮判定）。'
                       '仅停止类用例（single_stop/stop_resume_*）计算；非停止类用例为空。'
                       '报告按 pass_rate 聚合：全部停止轮遵从的用例占比(%)。',
        'type': 'auto',
        'result_type': 0, 'result_min': 0.0, 'result_max': 1.0,
        'decimal_places': 2, 'weight': 1, 'estimated_exec_time': 120,
        'score_unit': '%', 'statistic_method': 'pass_rate', 'agg_denominator': 'case',
        'params': _COMMON_INPUT_PARAMS + [
            _out('stop_compliance_rate', '停止指令遵循', 'interruption.stop_compliance_rate',
                 '遵从停止的轮占比(0-1)；模型停止原内容输出即遵从，只回复确认语同样算遵从。'
                 '非停止类用例或 LLM 降级为空。', 40,
                 agg='pass_eq', pass_threshold=1),
        ],
        'param_mappings': _PARAM_MAPPINGS,
    },
    # ── 恢复首轮内容评分（spec 未列，保留现成维度）──
    {
        'task_type_code': TASK_TYPE,
        'name': '恢复首轮内容评分',
        'keywords': 'interruption,resume_content_score,恢复首轮内容评分',
        'description': '打断指标 v2 主维度：打断后模型恢复首轮回复的内容综合评分(0-5)，LLM 判定。'
                       '无恢复轮或 LLM 降级时为空。',
        'type': 'auto',
        'result_type': 0, 'result_min': 0.0, 'result_max': 5.0,
        'decimal_places': 2, 'weight': 1, 'estimated_exec_time': 120,
        'score_unit': '分', 'statistic_method': 'average',
        'params': _COMMON_INPUT_PARAMS + [
            _out('resume_content_score', '恢复首轮内容评分', 'interruption.resume_content_score',
                 '恢复首轮回复的内容综合评分(0-5)；无恢复轮为空。', 50),
        ],
        'param_mappings': _PARAM_MAPPINGS,
    },
]

# ============================================================
# 「打断时延」容器主维度（仿 turn_taking：只配 input + 映射，无自身 output）
# + 3 个子维度（output field_path 各自提取）
# ============================================================
LATENCY_CONTAINER = {
    'task_type_code': TASK_TYPE,
    'name': '打断时延',
    'keywords': 'interruption,latency,打断时延,响应时延,回复时延,恢复时延',
    'description': '打断指标 v2 时延容器主维度：承载族公共 input/api_settings/group_key，'
                   '自身不配 output；时延指标见子维度（响应时延/回复时延/恢复首轮内容时延）。'
                   '时延由本地时序计算（ASR 词级时间戳 + FFT 精修），失败轮记 -1，avg/min/max 排除 -1。',
    'type': 'auto',
    'result_type': 0, 'result_min': 0.0, 'result_max': 1.0,
    'decimal_places': 0, 'weight': 1, 'estimated_exec_time': 120,
    'score_unit': '', 'statistic_method': 'average',
    'params': list(_COMMON_INPUT_PARAMS),
    'param_mappings': _PARAM_MAPPINGS,
}


def _latency_sub(name, code_prefix, main_code, main_help, list_code, ui_base, description):
    """时延子维度：main=avg，aux=min/max/逐轮 list。"""
    params = [
        _out(main_code, name, f'interruption.{main_code}', main_help, ui_base),
        _out(f'{code_prefix}_latency_min_ms', '最小值', f'interruption.{code_prefix}_latency_min_ms',
             f'{name}最小值(毫秒，排除 -1)；全部失败为空。', ui_base + 1,
             role='aux', agg=None),
        _out(f'{code_prefix}_latency_max_ms', '最大值', f'interruption.{code_prefix}_latency_max_ms',
             f'{name}最大值(毫秒，排除 -1)；全部失败为空。', ui_base + 2,
             role='aux', agg=None),
        _out(list_code, '逐轮列表', f'interruption.{list_code}',
             f'每实际打断轮的{name}列表(毫秒)；失败轮记 -1。', ui_base + 3,
             role='aux', agg=None, field_type='json'),
    ]
    return {
        'task_type_code': TASK_TYPE,
        'name': name,
        'keywords': f'interruption,{main_code},{name}',
        'description': description,
        'type': 'auto',
        'result_type': 1, 'result_min': 0.0, 'result_max': None,
        'decimal_places': 0, 'weight': 1, 'estimated_exec_time': 120,
        'score_unit': 'ms', 'statistic_method': 'average',
        'params': params,
    }


LATENCY_SUBS = [
    _latency_sub(
        '响应时延', 'response', 'response_latency_avg_ms',
        '平均响应时延(毫秒，排除 -1)；全部失败为空。', 'round_response_latencies', 60,
        '子维度：用户开始打断 → 模型停口的时延(毫秒)。本地时序计算，'
        'LLM 判定失败/静默的轮记 -1 不入均值；询问轮照记。',
    ),
    _latency_sub(
        '回复时延', 'reply', 'reply_latency_avg_ms',
        '平均回复时延(毫秒，排除 -1)；全部失败为空。', 'round_reply_latencies', 70,
        '子维度：用户说完打断内容 → 模型重新开口的时延(毫秒)。本地时序计算，'
        'LLM 判定失败/静默的轮记 -1 不入均值；询问轮照记。',
    ),
    {
        'task_type_code': TASK_TYPE,
        'name': '恢复首轮内容时延',
        'keywords': 'interruption,resume_first_reply_latency_ms,恢复首轮内容时延',
        'description': '子维度：打断后模型恢复首轮内容的回复时延(毫秒)'
                       '＝最后一轮模型的回复时延（前面轮次回复被后续打断截断，不计时延）。'
                       '无恢复轮为空。',
        'type': 'auto',
        'result_type': 1, 'result_min': 0.0, 'result_max': None,
        'decimal_places': 0, 'weight': 1, 'estimated_exec_time': 120,
        'score_unit': 'ms', 'statistic_method': 'average',
        'params': [
            _out('resume_first_reply_latency_ms', '恢复首轮内容时延',
                 'interruption.resume_first_reply_latency_ms',
                 '恢复首轮回复时延(毫秒)＝最后一轮模型的回复时延；无恢复轮为空。', 80),
        ],
    },
]


# ============================================================
# upsert helpers（沿用 202606 seed 脚本通用模式；软删逻辑已改为物理删除）
# 差异：主维度按 name 匹配（全族 12 个主维度共用 task_type_code，不能按 tc fetchone）
# ============================================================
def _upsert_dimension(conn, dim_def, dimension_type, parent_id=None):
    """注册/更新一个维度，返回 dim_id。dimension_type: 'main' or 'sub'。"""
    task_code = dim_def['task_type_code']
    name = dim_def['name']

    if dimension_type == 'sub':
        # 子维度按 name 匹配（旧树已先软删，同名旧行 deleted=TRUE 不会被复活）
        existing = conn.execute(text(
            "SELECT id FROM dimensions "
            "WHERE name = :name AND dimension_type = 'sub' AND deleted = FALSE"
        ), {'name': name}).fetchone()
        if existing:
            old_tc = conn.execute(text(
                "SELECT task_type_code FROM dimensions WHERE id = :did"
            ), {'did': existing[0]}).scalar()
            if old_tc and old_tc != task_code:
                print(f"  ! 检测到子维度 '{name}' task_type_code 变更: {old_tc} → {task_code}，原地更新 id={existing[0]}")
                conn.execute(text(
                    "UPDATE dimensions SET task_type_code = :tc, updated_at = NOW() WHERE id = :did"
                ), {'tc': task_code, 'did': existing[0]})
    else:
        # 主维度按 name 匹配：全族 task_type_code 相同，按 tc 匹配会串维度
        existing = conn.execute(text(
            "SELECT id FROM dimensions "
            "WHERE name = :name AND dimension_type = 'main' "
            "AND parent_dimension_id IS NULL AND deleted = FALSE"
        ), {'name': name}).fetchone()

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
        'apis': API_SETTINGS,
        'rule': RULE,
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
            # 子维度不写 api_url：保持 NULL 走父维度继承（api_settings 已全族一致）
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
        if dimension_type == 'main':
            result = conn.execute(text(
                "INSERT INTO dimensions "
                "  (name, keywords, dimension_type, parent_dimension_id, task_type_code, description, "
                "   type, result_type, result_min, result_max, decimal_places, "
                "   weight, estimated_exec_time, rule, api_settings, status, "
                "   api_status, score_unit, statistic_method, agg_denominator, api_url, "
                "   deleted, created_at, updated_at) "
                "VALUES "
                "  (:name, :kw, :dtype, :pid, :tc, :desc, "
                "   :type, :rt, :rmin, :rmax, :dp, "
                "   :w, :et, :rule, :apis, TRUE, "
                "   'online', :su, :sm, :ad, :api_url, "
                "   FALSE, NOW(), NOW()) "
                "RETURNING id"
            ), {**common_fields, 'tc': task_code, 'api_url': API_URL})
        else:
            result = conn.execute(text(
                "INSERT INTO dimensions "
                "  (name, keywords, dimension_type, parent_dimension_id, task_type_code, description, "
                "   type, result_type, result_min, result_max, decimal_places, "
                "   weight, estimated_exec_time, rule, api_settings, status, "
                "   api_status, score_unit, statistic_method, agg_denominator, "
                "   deleted, created_at, updated_at) "
                "VALUES "
                "  (:name, :kw, :dtype, :pid, :tc, :desc, "
                "   :type, :rt, :rmin, :rmax, :dp, "
                "   :w, :et, :rule, :apis, TRUE, "
                "   'online', :su, :sm, :ad, "
                "   FALSE, NOW(), NOW()) "
                "RETURNING id"
            ), {**common_fields, 'tc': task_code})
        dim_id = result.fetchone()[0]
        print(f"  + {dimension_type} 维度已插入 (id={dim_id}, name={name})")
    return dim_id


def _cleanup_stale_params(conn, dim_id, dim_def):
    """物理清理 DB 中当前 dim_def.params 不再出现的 param_code（按 direction 分组）。

    历史软删（deleted=TRUE）的遗留参数一并物理删除，不留软删垃圾数据。
    """
    current_output_codes = {p[0] for p in dim_def['params'] if p[4] == 'output'}
    current_input_codes = {p[0] for p in dim_def['params'] if p[4] == 'input'}
    for direction, current_codes in (
        ('output', current_output_codes),
        ('input', current_input_codes),
    ):
        if not current_codes:
            stale = conn.execute(text(
                "SELECT param_code FROM evaluation_dimension_params "
                "WHERE dimension_id = :did AND param_direction = :dir"
            ), {'did': dim_id, 'dir': direction}).fetchall()
            if stale:
                stale_codes = [r[0] for r in stale]
                print(f"  ! 物理清理已废弃 {direction} 参数: {stale_codes}")
                conn.execute(text(
                    "DELETE FROM evaluation_dimension_params "
                    "WHERE dimension_id = :did AND param_direction = :dir"
                ), {'did': dim_id, 'dir': direction})
            continue
        placeholders = ','.join(f':c{i}' for i in range(len(current_codes)))
        bind = {f'c{i}': code for i, code in enumerate(current_codes)}
        stale = conn.execute(text(
            "SELECT param_code FROM evaluation_dimension_params "
            "WHERE dimension_id = :did AND param_direction = :dir "
            f"AND param_code NOT IN ({placeholders})"
        ), {'did': dim_id, 'dir': direction, **bind}).fetchall()
        if stale:
            stale_codes = [r[0] for r in stale]
            print(f"  ! 物理清理已废弃 {direction} 参数: {stale_codes}")
            # 用 stale_codes(要删的) 建 IN 列表，勿用 current_codes(要留的)——否则删错+被upsert复活
            stale_placeholders = ','.join(f':s{i}' for i in range(len(stale_codes)))
            stale_bind = {f's{i}': code for i, code in enumerate(stale_codes)}
            conn.execute(text(
                "DELETE FROM evaluation_dimension_params "
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
    """注册 voice_llm → 维度关联（幂等；历史软删行直接物理删除后重建，不留软删垃圾）。"""
    existing = conn.execute(text(
        "SELECT id, deleted FROM algorithm_dimension_relations "
        "WHERE algorithm_type = 'voice_llm' AND dimension_id = :did"
    ), {'did': dim_id}).fetchone()
    if existing:
        if existing[1]:
            print(f"  ! 删除历史软删关联 voice_llm → dim {dim_id} 并重建")
            conn.execute(text(
                "DELETE FROM algorithm_dimension_relations WHERE id = :id"
            ), {'id': existing[0]})
            conn.execute(text(
                "INSERT INTO algorithm_dimension_relations "
                "  (algorithm_type, dimension_id, is_default, weight, "
                "   deleted, created_at, updated_at) "
                "VALUES "
                "  ('voice_llm', :did, FALSE, 1.0, FALSE, NOW(), NOW())"
            ), {'did': dim_id})
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


def _hard_delete_dimension_tree(conn, dim_id, reason):
    """物理删除一个维度及其 params / mappings / relations / 子维度 / 历史结果行。

    库中该维度已是金标口径下的废弃数据（含历史软删遗留），直接移除，
    不再保留软删（deleted=TRUE）记录。
    """
    subs = conn.execute(text(
        "SELECT id, name FROM dimensions WHERE parent_dimension_id = :pid"
    ), {'pid': dim_id}).fetchall()
    for sub_id, sub_name in subs:
        _hard_delete_dimension_tree(conn, sub_id, f"父维度 {dim_id} 被物理删除")

    n_results = conn.execute(text(
        "DELETE FROM test_result_dimensions WHERE dimension_id = :did"
    ), {'did': dim_id}).rowcount
    if n_results:
        print(f"  ! 级联删除 test_result_dimensions {n_results} 行 (dimension_id={dim_id})")
    conn.execute(text(
        "DELETE FROM evaluation_dimension_params WHERE dimension_id = :did"
    ), {'did': dim_id})
    conn.execute(text(
        "DELETE FROM param_mappings WHERE dimension_id = :did"
    ), {'did': dim_id})
    conn.execute(text(
        "DELETE FROM algorithm_dimension_relations WHERE dimension_id = :did"
    ), {'did': dim_id})
    conn.execute(text(
        "DELETE FROM dimensions WHERE id = :did"
    ), {'did': dim_id})
    print(f"  ! 物理删除维度 id={dim_id}（{reason}）：dimensions/params/mappings/relations/结果行已移除")


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


def _verify(conn):
    """出口核对：每个输出维度 main param 唯一；容器无 output；旧树已物理删除。"""
    ok = True
    rows = conn.execute(text(
        "SELECT d.id, d.name, d.dimension_type, "
        "  COUNT(p.id) FILTER (WHERE p.output_role = 'main' AND p.deleted = FALSE) AS n_main "
        "FROM dimensions d "
        "LEFT JOIN evaluation_dimension_params p ON p.dimension_id = d.id "
        "WHERE d.deleted = FALSE AND d.task_type_code = :tc "
        "GROUP BY d.id, d.name, d.dimension_type ORDER BY d.id"
    ), {'tc': TASK_TYPE}).fetchall()
    print(f"\n  核对：interruption_metrics 族 {len(rows)} 个维度")
    for dim_id, name, dtype, n_main in rows:
        expect = 0 if name == LATENCY_CONTAINER['name'] else 1
        flag = 'OK' if n_main == expect else '!!'
        if n_main != expect:
            ok = False
        print(f"    [{flag}] id={dim_id} {dtype:4s} {name}: main output param = {n_main} (期望 {expect})")
    stale = conn.execute(text(
        "SELECT id, name FROM dimensions "
        "WHERE deleted = FALSE AND dimension_type = 'main' AND parent_dimension_id IS NULL "
        "AND task_type_code IN ('interruption_judge')"
    )).fetchall()
    if stale:
        ok = False
        print(f"    [!!] 旧打断场景裁判主维度未物理删除: {stale}")
    legacy = conn.execute(text(
        "SELECT id, name FROM dimensions "
        "WHERE deleted = FALSE AND dimension_type = 'main' AND parent_dimension_id IS NULL "
        "AND task_type_code = 'interruption_metrics' AND name = '打断成功率'"
    )).fetchall()
    if legacy:
        ok = False
        print(f"    [!!] 旧打断成功率主维度未物理删除: {legacy}")
    print(f"  核对结果: {'通过' if ok else '未通过'}")
    return ok


def seed_interruption_v2():
    engine = create_engine(POSTGRES_URI)

    with engine.begin() as conn:
        # ============================================================
        # Step 0: 物理删除旧树（必须先于新建：子维度按 name 匹配 deleted=FALSE，
        #         「恢复首轮内容时延」新旧同名，先删旧行避免复活旧 parent/field_path）
        # ============================================================
        print(f"\n{'=' * 60}")
        print("  Step 0: 物理删除旧维度树（打断成功率主+4子 / 打断场景裁判主+11子）")
        print(f"{'=' * 60}")
        new_main_names = [d['name'] for d in MAIN_DIMENSIONS] + [LATENCY_CONTAINER['name']]
        placeholders = ','.join(f':n{i}' for i in range(len(new_main_names)))
        bind = {f'n{i}': n for i, n in enumerate(new_main_names)}
        legacy = conn.execute(text(
            "SELECT id, name, task_type_code FROM dimensions "
            "WHERE task_type_code = 'interruption_metrics' "
            "AND dimension_type = 'main' AND parent_dimension_id IS NULL "
            f"AND name NOT IN ({placeholders}) AND deleted = FALSE"
        ), bind).fetchall()
        judge = conn.execute(text(
            "SELECT id, name, task_type_code FROM dimensions "
            "WHERE task_type_code = 'interruption_judge' "
            "AND dimension_type = 'main' AND parent_dimension_id IS NULL "
            "AND deleted = FALSE"
        )).fetchall()
        if not legacy and not judge:
            print("  无旧树需清理")
        for dim_id, name, tc in legacy:
            print(f"  物理删除旧主维度: id={dim_id}, name={name}, task_type_code={tc}")
            _hard_delete_dimension_tree(conn, dim_id, "被打断指标 v2 维度树替代")
        for dim_id, name, tc in judge:
            print(f"  物理删除旧主维度: id={dim_id}, name={name}, task_type_code={tc}")
            _hard_delete_dimension_tree(conn, dim_id, "LLM 裁判已并入打断指标 v2 族（进程内直调，不再独立维度）")

        # ============================================================
        # Step 1: 11 个主维度
        # ============================================================
        print(f"\n{'=' * 60}")
        print(f"  Step 1: 注册 {len(MAIN_DIMENSIONS)} 个主维度")
        print(f"{'=' * 60}")
        for dim_def in MAIN_DIMENSIONS:
            print(f"\n  -- 主维度: {dim_def['name']} --")
            dim_id = _upsert_dimension(conn, dim_def, dimension_type='main', parent_id=None)
            _upsert_params(conn, dim_id, dim_def)
            _upsert_relation(conn, dim_id)
            _upsert_param_mappings(conn, dim_id, dim_def)

        # ============================================================
        # Step 2: 打断时延容器 + 3 个子维度
        # ============================================================
        print(f"\n{'=' * 60}")
        print("  Step 2: 注册「打断时延」容器主维度 + 3 个子维度")
        print(f"{'=' * 60}")
        container_id = _upsert_dimension(conn, LATENCY_CONTAINER, dimension_type='main', parent_id=None)
        _upsert_params(conn, container_id, LATENCY_CONTAINER)
        _upsert_relation(conn, container_id)
        _upsert_param_mappings(conn, container_id, LATENCY_CONTAINER)
        for sub_def in LATENCY_SUBS:
            print(f"\n  -- 子维度: {sub_def['name']} (parent={container_id}) --")
            sub_id = _upsert_dimension(conn, sub_def, dimension_type='sub', parent_id=container_id)
            _upsert_params(conn, sub_id, sub_def)
            _upsert_relation(conn, sub_id)
            # 子维度不配 input params / param_mappings：继承容器主维度

        # ============================================================
        # Step 3: 分类分配 + 出口核对
        # ============================================================
        print(f"\n{'=' * 60}")
        print("  Step 3: 分类分配 + 出口核对")
        print(f"{'=' * 60}")
        _assign_dimension_category(conn)
        if not _verify(conn):
            raise RuntimeError("出口核对未通过，请检查上方 [!!] 项（事务将回滚）")

        print(f"\n{'=' * 60}")
        print("  打断指标 v2 维度种子注册完成")
        print(f"  主维度 {len(MAIN_DIMENSIONS)} 个 + 「打断时延」容器(id={container_id}) + 3 个子维度")
        print(f"  全族 task_type_code={TASK_TYPE}, api_settings.group_key={GROUP_KEY}")
        print(f"  任选维度组合 → 平台合并一组 → 一次 eval_server 请求 → 一次 LLM 判定")
        print(f"{'=' * 60}")


if __name__ == '__main__':
    print("=" * 60)
    print("打断指标 v2 维度种子数据注册")
    print("=" * 60)
    print()
    print(f"数据库: {POSTGRES_URI[:POSTGRES_URI.rindex('@')]}@...")
    print(f"eval_server: {API_URL}")
    print()
    print("此脚本将：")
    print("1. 物理删除旧树：「打断成功率」(主+4子) 与「打断场景裁判」(主+11子)")
    print("   及其引用结果行（软删数据直接移除，不再保留 deleted=TRUE 记录）")
    print("2. 注册 11 个主维度（成功/失败/询问数量、5 个行为数量、回复内容评分、")
    print("   停止指令遵循、恢复首轮内容评分），全族 task_type_code=interruption_metrics")
    print("3. 注册「打断时延」容器主维度 + 3 个子维度（响应时延/回复时延/恢复首轮内容时延）")
    print("4. 全族 api_settings 写 group_key=interruption_v2 + 同一份 body_template：")
    print("   平台按 (endpoint_url, group_key) 合并为一组，只发一次请求")
    print("5. 每个主维度配全量 input params + param_mappings + voice_llm 关联")
    print()
    print("脚本可重复执行（幂等）；两个库都要跑（DATABASE_URI/EVAL_SERVER_URL 环境变量切库）")
    print()

    confirm = input("是否继续？(y/N): ").strip().lower()
    if confirm != 'y':
        print("已取消")
        sys.exit(0)

    try:
        seed_interruption_v2()
    except Exception as e:
        print(f"\n迁移失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
