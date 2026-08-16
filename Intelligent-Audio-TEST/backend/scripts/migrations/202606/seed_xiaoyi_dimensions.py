# -*- coding: utf-8 -*-
"""
小艺评估维度种子数据

功能：
1. 注册三个评估维度（dimensions）：
   - tor (Take-Off Rate，打断后接话率)
   - false_takeover (误接管率，用户停顿期间模型是否抢话)
   - takeover_latency (接管时延，模型回复第一词时刻 - 音频结束时刻)
2. 注册各维度的输入/输出参数（evaluation_dimension_params）
3. 注册 voice_llm 算法与各维度的关联（algorithm_dimension_relations）
4. 注册 voice_llm → 各维度的参数映射（param_mappings）

对应 eval_server 服务：
   - daily_chat_TOR.py        → tor 维度
   - xiaoyi_false_takeover.py → false_takeover 维度
   - xiaoyi_takeover_latency.py → takeover_latency 维度

使用方法：
    cd Intelligent-Audio-TEST
    python -m backend.scripts.migrations.202606.seed_xiaoyi_dimensions

或直接：
    python backend/scripts/migrations/202606/seed_xiaoyi_dimensions.py

注意：此脚本可重复执行（幂等）
"""

import sys
import os
import json
from sqlalchemy import create_engine, text

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'
)

# ============================================================
# 维度定义
# ============================================================
# xiaoyi_metrics 统一维度：调一次 ASR，三个子指标共享结果
# 子指标: tor(接话率), false_takeover(误接管率), takeover_latency(接管时延)
DIMENSIONS = [
    {
        'task_type_code': 'xiaoyi_metrics',
        'name': '小艺指标',
        'keywords': 'xiaoyi,tor,takeoff,接话,误接管,抢话,接管时延,延迟',
        'description': '小艺评估统一指标：调一次 ASR 共享结果，计算 tor(接话率)、false_takeover(误接管率)、takeover_latency(接管时延)',
        'type': 'auto',
        'result_type': 0,
        'result_min': 0.0,
        'result_max': 1.0,
        'decimal_places': 0,
        'weight': 1,
        'estimated_exec_time': 30,
        'score_unit': '',
        'statistic_method': 'average',
        'params': [
            # ─── 输入参数 ───
            ('input_lastword', '输入音频最后一词时间戳', '输入音频最后一词时间戳', 'json', 'input',
             None, None, None, True,
             False, None, '输入音频最后一词时间戳（主服务参数传递）', 5),
            ('start_ms', '音频开启时刻', '音频开启时刻', 'number', 'input',
             None, None, None, True,
             False, None, '本轮音频播放开始的绝对时刻(毫秒 Unix 时间戳)', 6),
            ('query', '用例问题', '用例问题', 'text', 'input',
             None, None, None, True,
             False, None, '用例问题', 7),
            ('question', '模型识别问题结果', '模型识别问题结果', 'text', 'input',
             None, None, None, True,
             False, None, '模型识别问题结果', 8),
            ('record_file', '录音文件', '录音文件', 'audio', 'input',
             None, None, None, True,
             False, None, 'wav 录音文件路径(eval_server 调用 asr_server.py /asr 接口获取 ASR 结果)', 10),
            ('pause', '停顿区间', '停顿区间', 'json', 'input',
             None, None, None, True,
             False, None, '停顿区间数据(主服务用例参数传递)', 20),
            ('first_frame_ms', '录屏首帧时刻', '录屏首帧时刻', 'number', 'input',
             None, None, None, True,
             False, None, '录屏首帧写入的绝对时刻(毫秒 Unix 时间戳)', 30),
            ('end_ms', '音频结束时刻', '音频结束时刻', 'number', 'input',
             None, None, None, True,
             False, None, '本轮音频播放结束的绝对时刻(毫秒 Unix 时间戳)', 40),
            ('offset_ms', '时延补偿', '时延补偿', 'number', 'input',
             None, None, None, True,
             False, '40', '音响结束播放与音频最后内容词的时延补偿(毫秒)', 50),

            # ─── 输出参数: tor (接话率) ───
            # field_path 使用点号路径导航嵌套结构: result.tor.tor → 标量值 1
            ('tor', 'TOR接话率', 'TOR接话率', 'number', 'output',
             'tor.tor', 'value', 'main', True,
             False, None, '接话率(0=没接话, 1=接话)', 60),
            ('tor_n_words', 'TOR命中词数', 'TOR命中词数', 'number', 'output',
             'tor.n_words', None, 'aux', False,
             False, None, 'tor: 命中词总数', 61),
            ('tor_duration', 'TOR命中词时长', 'TOR命中词时长', 'number', 'output',
             'tor.duration', None, 'aux', False,
             False, None, 'tor: 命中词总跨度(秒)', 62),
            ('tor_hit_words', 'TOR命中词列表', 'TOR命中词列表', 'json', 'output',
             'tor.hit_words', None, 'aux', False,
             False, None, 'tor: 命中词列表', 63),

            # ─── 输出参数: false_takeover (误接管率) ───
            ('false_takeover', '误接管率', '误接管率', 'number', 'output',
             'false_takeover.tor', 'value', 'main', True,
             False, None, '误接管率(0=未抢话, 1=抢话)', 70),
            ('ft_n_words', '误接管命中词数', '误接管命中词数', 'number', 'output',
             'false_takeover.n_words', None, 'aux', False,
             False, None, 'false_takeover: 所有 pause 区间内命中词总数', 71),
            ('ft_duration', '误接管命中词时长', '误接管命中词时长', 'number', 'output',
             'false_takeover.duration', None, 'aux', False,
             False, None, 'false_takeover: 命中词的总跨度(秒)', 72),
            ('ft_total_pauses', '误接管Pause总数', '误接管Pause总数', 'number', 'output',
             'false_takeover.total_pauses', None, 'aux', False,
             False, None, 'false_takeover: pause 区间总数', 73),
            ('ft_hit_words', '误接管命中词列表', '误接管命中词列表', 'json', 'output',
             'false_takeover.hit_words', None, 'aux', False,
             False, None, 'false_takeover: 所有 pause 区间内命中的模型词列表', 74),
            ('ft_details', '误接管逐区间详情', '误接管逐区间详情', 'json', 'output',
             'false_takeover.details', None, 'aux', False,
             False, None, 'false_takeover: 每个 pause 区间的命中情况', 75),

            # ─── 输出参数: takeover_latency (接管时延) ───
            ('takeover_latency_ms', '接管时延', '接管时延', 'number', 'output',
             'takeover_latency.takeover_latency_ms', 'value', 'main', True,
             False, None, '接管时延(毫秒)', 80),
            ('first_word_begin_ms', '首词偏移', '首词偏移', 'number', 'output',
             'takeover_latency.first_word_begin_ms', None, 'aux', False,
             False, None, 'ASR 第一个词相对 mp4 起点的偏移(毫秒)', 81),
            ('model_first_word_ms', '模型首词时刻', '模型首词时刻', 'number', 'output',
             'takeover_latency.model_first_word_ms', None, 'aux', False,
             False, None, '模型回复第一个词的绝对时刻(毫秒 Unix 时间戳)', 82),
            ('audio_end_with_offset_ms', '音频结束+补偿', '音频结束+补偿', 'number', 'output',
             'takeover_latency.audio_end_with_offset_ms', None, 'aux', False,
             False, None, 'end_ms + offset_ms', 83),
            ('latency_message', '时延说明', '时延说明', 'text', 'output',
             'takeover_latency.message', None, 'aux', False,
             False, None, 'takeover_latency: 错误/成功说明', 84),
        ],
        # wav_path, first_frame_ms, end_ms, start_ms 从 device 输出映射
        # pause, input_lastword 从 reference 映射
        # ASR 结果由 eval_server 内部调用 asr_server.py 获取，通过返回值传递，三个子指标共享
        'param_mappings': [
            ('device', 'output', 'wav_path', 'record_file', 'none'),
            ('reference', 'output', 'pause', 'pause', 'none'),
            ('device', 'output', 'first_frame_ms', 'first_frame_ms', 'none'),
            ('device', 'output', 'end_ms', 'end_ms', 'none'),
            ('device', 'output', 'start_ms', 'start_ms', 'none'),
            ('reference', 'output', 'input_lastword', 'input_lastword', 'none'),
        ],
    },
    {
        # ── 话轮接管维度：tor + false_takeover + takeover_latency ──
        # 只计算三项指标，不执行主录音 ASR、input_asr、interruption
        # 双路 wav（user_wav + ai_wav）由 eval_server 内部调 ASR，三项共享
        'task_type_code': 'takeover',
        'name': '话轮接管',
        'keywords': 'takeover,话轮,接管,tor,接话,误接管,抢话,接管时延,延迟',
        'description': '话轮接管维度：调双路 ASR 共享结果，计算 tor(接话率)、false_takeover(误接管率)、takeover_latency(接管时延)',
        'type': 'auto',
        'result_type': 0,
        'result_min': 0.0,
        'result_max': 1.0,
        'decimal_places': 0,
        'weight': 1,
        'estimated_exec_time': 30,
        'score_unit': '',
        'statistic_method': 'average',
        'params': [
            # ─── 输入参数 ───
            ('user_wav', '用户通道音频', '用户通道音频', 'audio', 'input',
             None, None, None, True,
             False, None, '用户通道 wav 路径（cap_client_process_out.wav）', 1),
            ('ai_wav', 'AI回复通道音频', 'AI回复通道音频', 'audio', 'input',
             None, None, None, True,
             False, None, 'AI 回复通道 wav 路径（cap_client_ec_out.wav）', 2),
            ('pause', '停顿区间', '停顿区间', 'json', 'input',
             None, None, None, True,
             False, None, '停顿区间数据(主服务用例参数传递)', 10),
            ('first_frame_ms', '录屏首帧时刻', '录屏首帧时刻', 'number', 'input',
             None, None, None, True,
             False, None, '录屏首帧写入的绝对时刻(毫秒 Unix 时间戳)，legacy 回退用', 20),
            ('start_ms', '音频开启时刻', '音频开启时刻', 'number', 'input',
             None, None, None, True,
             False, None, '本轮音频播放开始的绝对时刻(毫秒 Unix 时间戳)，legacy 回退用', 30),
            ('input_lastword', '输入末词时间戳', '输入末词时间戳', 'json', 'input',
             None, None, None, True,
             False, None, '输入音频最后一词时间戳（主服务参数传递），legacy 回退用', 40),
            ('offset_ms', '时延补偿', '时延补偿', 'number', 'input',
             None, None, None, True,
             False, '40', '音响结束播放与音频最后内容词的时延补偿(毫秒)', 50),

            # ─── 输出参数: tor (接话率) ───
            ('tor', 'TOR接话率', 'TOR接话率', 'number', 'output',
             'tor.tor', 'value', 'main', True,
             False, None, '接话率(0=没接话, 1=接话)', 60),
            ('tor_n_words', 'TOR命中词数', 'TOR命中词数', 'number', 'output',
             'tor.n_words', None, 'aux', False,
             False, None, 'tor: 命中词总数', 61),
            ('tor_duration', 'TOR命中词时长', 'TOR命中词时长', 'number', 'output',
             'tor.duration', None, 'aux', False,
             False, None, 'tor: 命中词总跨度(秒)', 62),
            ('tor_hit_words', 'TOR命中词列表', 'TOR命中词列表', 'json', 'output',
             'tor.hit_words', None, 'aux', False,
             False, None, 'tor: 命中词列表', 63),
            ('tor_user_last_word_end_s', 'TOR用户末词结束', 'TOR用户末词结束', 'number', 'output',
             'tor.user_last_word_end_s', None, 'aux', False,
             False, None, 'tor: user 最后一词结束时间(秒)', 64),

            # ─── 输出参数: false_takeover (误接管率) ───
            ('false_takeover', '误接管率', '误接管率', 'number', 'output',
             'false_takeover.tor', 'value', 'main', True,
             False, None, '误接管率(0=未抢话, 1=抢话)', 70),
            ('ft_n_words', '误接管命中词数', '误接管命中词数', 'number', 'output',
             'false_takeover.n_words', None, 'aux', False,
             False, None, 'false_takeover: 所有 pause 区间内命中词总数', 71),
            ('ft_duration', '误接管命中词时长', '误接管命中词时长', 'number', 'output',
             'false_takeover.duration', None, 'aux', False,
             False, None, 'false_takeover: 命中词的总跨度(秒)', 72),
            ('ft_total_pauses', '误接管Pause总数', '误接管Pause总数', 'number', 'output',
             'false_takeover.total_pauses', None, 'aux', False,
             False, None, 'false_takeover: pause 区间总数', 73),
            ('ft_hit_words', '误接管命中词列表', '误接管命中词列表', 'json', 'output',
             'false_takeover.hit_words', None, 'aux', False,
             False, None, 'false_takeover: 所有 pause 区间内命中的模型词列表', 74),
            ('ft_details', '误接管逐区间详情', '误接管逐区间详情', 'json', 'output',
             'false_takeover.details', None, 'aux', False,
             False, None, 'false_takeover: 每个 pause 区间的命中情况', 75),

            # ─── 输出参数: takeover_latency (接管时延) ───
            ('takeover_latency_ms', '接管时延', '接管时延', 'number', 'output',
             'takeover_latency.takeover_latency_ms', 'value', 'main', True,
             False, None, '接管时延(毫秒)，正=AI后回复，负=抢话', 80),
            ('tl_user_last_word_end_ms', '用户末词结束时刻', '用户末词结束时刻', 'number', 'output',
             'takeover_latency.user_last_word_end_ms', None, 'aux', False,
             False, None, 'takeover_latency: user 末词结束时间(毫秒)', 81),
            ('tl_ai_first_word_start_ms', '模型首词开始时刻', '模型首词开始时刻', 'number', 'output',
             'takeover_latency.ai_first_word_start_ms', None, 'aux', False,
             False, None, 'takeover_latency: AI 首字开始时间(毫秒)', 82),
            ('latency_message', '时延说明', '时延说明', 'text', 'output',
             'takeover_latency.message', None, 'aux', False,
             False, None, 'takeover_latency: 错误/成功说明', 84),
        ],
        'param_mappings': [
            ('device', 'output', 'user_wav', 'user_wav', 'none'),
            ('device', 'output', 'ai_wav', 'ai_wav', 'none'),
            ('reference', 'output', 'pause', 'pause', 'none'),
            ('device', 'output', 'first_frame_ms', 'first_frame_ms', 'none'),
            ('device', 'output', 'start_ms', 'start_ms', 'none'),
            ('reference', 'output', 'input_lastword', 'input_lastword', 'none'),
        ],
    },
]


def seed_xiaoyi_dimensions():
    engine = create_engine(POSTGRES_URI)

    with engine.begin() as conn:
        for dim_def in DIMENSIONS:
            task_code = dim_def['task_type_code']
            print(f"\n{'=' * 60}")
            print(f"  处理维度: {task_code} ({dim_def['name']})")
            print(f"{'=' * 60}")

            # ============================================================
            # Step 1: 注册维度
            # ============================================================
            print(f"\n--- Step 1: 注册 {task_code} 维度 (dimensions) ---")

            existing_dim = conn.execute(text(
                "SELECT id FROM dimensions "
                "WHERE task_type_code = :tc AND deleted = FALSE"
            ), {'tc': task_code}).fetchone()

            api_settings = json.dumps({
                'method': 'POST',
                'headers': {},
                'body_template': {
                    'rounds': [
                        {
                            'end_ms': '{{end_ms}}',
                            'first_frame_ms': '{{first_frame_ms}}',
                            'input_lastword': '{{input_lastword}}',
                            'offset_ms': '{{offset_ms}}',
                            'pause': '{{pause}}',
                            'record_file': '{{record_file}}',
                            'start_ms': '{{start_ms}}',
                            'query': '{{query}}',
                            'question': '{{question}}'
                        }
                    ]
                },
                'timeout': 30000
            }, ensure_ascii=False)
            rule = json.dumps({'rules': [], 'defaultScore': 0}, ensure_ascii=False)

            if existing_dim:
                dim_id = existing_dim[0]
                print(f"  - {task_code} 维度已存在 (id={dim_id})，更新描述")
                conn.execute(text(
                    "UPDATE dimensions SET "
                    "  name = :name, keywords = :kw, description = :desc, "
                    "  type = :type, result_type = :rt, result_min = :rmin, "
                    "  result_max = :rmax, decimal_places = :dp, weight = :w, "
                    "  estimated_exec_time = :et, score_unit = :su, "
                    "  statistic_method = :sm, api_settings = :apis, "
                    "  rule = :rule, "
                    "  updated_at = NOW() "
                    "WHERE id = :did"
                ), {
                    'name': dim_def['name'], 'kw': dim_def['keywords'],
                    'desc': dim_def['description'], 'type': dim_def['type'],
                    'rt': dim_def['result_type'], 'rmin': dim_def['result_min'],
                    'rmax': dim_def['result_max'], 'dp': dim_def['decimal_places'],
                    'w': dim_def['weight'], 'et': dim_def['estimated_exec_time'],
                    'su': dim_def['score_unit'], 'sm': dim_def['statistic_method'],
                    'apis': api_settings, 'rule': rule, 'did': dim_id,
                })
            else:
                result = conn.execute(text(
                    "INSERT INTO dimensions "
                    "  (name, keywords, dimension_type, task_type_code, description, "
                    "   type, result_type, result_min, result_max, decimal_places, "
                    "   weight, estimated_exec_time, rule, api_settings, status, "
                    "   api_status, score_unit, statistic_method, "
                    "   deleted, created_at, updated_at) "
                    "VALUES "
                    "  (:name, :kw, 'main', :tc, :desc, "
                    "   :type, :rt, :rmin, :rmax, :dp, "
                    "   :w, :et, :rule, :apis, TRUE, "
                    "   'online', :su, :sm, "
                    "   FALSE, NOW(), NOW()) "
                    "RETURNING id"
                ), {
                    'name': dim_def['name'], 'kw': dim_def['keywords'],
                    'tc': task_code, 'desc': dim_def['description'],
                    'type': dim_def['type'], 'rt': dim_def['result_type'],
                    'rmin': dim_def['result_min'], 'rmax': dim_def['result_max'],
                    'dp': dim_def['decimal_places'], 'w': dim_def['weight'],
                    'et': dim_def['estimated_exec_time'],
                    'rule': rule, 'apis': api_settings,
                    'su': dim_def['score_unit'], 'sm': dim_def['statistic_method'],
                })
                dim_id = result.fetchone()[0]
                print(f"  + {task_code} 维度已插入 (id={dim_id})")

            # ============================================================
            # Step 2: 注册输入/输出参数
            # ============================================================
            print(f"\n--- Step 2: 注册 {task_code} 参数 (evaluation_dimension_params) ---")

            param_inserted = 0
            param_skipped = 0
            for dp in dim_def['params']:
                (param_code, param_name, label, field_type, param_direction,
                 field_path, agg_role, output_role, visible_in_report,
                 required, default_value, help_text, ui_order) = dp

                existing = conn.execute(text(
                    "SELECT id FROM evaluation_dimension_params "
                    "WHERE dimension_id = :did AND param_code = :pc "
                    "AND param_direction = :dir"
                ), {'did': dim_id, 'pc': param_code, 'dir': param_direction}).fetchone()

                if existing:
                    # 更新已有参数
                    conn.execute(text(
                        "UPDATE evaluation_dimension_params SET "
                        "  param_name = :pn, label = :lb, field_type = :ft, "
                        "  field_path = :fp, agg_role = :ar, output_role = :or, "
                        "  visible_in_report = :vir, required = :req, "
                        "  default_value = :dv, help_text = :ht, ui_order = :uo, "
                        "  updated_at = NOW() "
                        "WHERE id = :id"
                    ), {
                        'pn': param_name, 'lb': label, 'ft': field_type,
                        'fp': field_path, 'ar': agg_role, 'or': output_role,
                        'vir': visible_in_report, 'req': required,
                        'dv': default_value, 'ht': help_text, 'uo': ui_order,
                        'id': existing[0],
                    })
                    print(f"  - {param_code} ({param_direction}) 已存在，已更新")
                    param_skipped += 1
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
                    print(f"  + {param_code} ({field_type}, {param_direction})")
                    param_inserted += 1

            print(f"  插入 {param_inserted} 条，跳过/更新 {param_skipped} 条")

            # ============================================================
            # Step 3: 注册 voice_llm → 维度关联
            # ============================================================
            print(f"\n--- Step 3: 注册 voice_llm → {task_code} 关联 ---")

            existing_rel = conn.execute(text(
                "SELECT id FROM algorithm_dimension_relations "
                "WHERE algorithm_type = 'voice_llm' AND dimension_id = :did"
            ), {'did': dim_id}).fetchone()

            if existing_rel:
                print(f"  - 关联已存在 (voice_llm → {task_code} id={dim_id})，跳过")
            else:
                conn.execute(text(
                    "INSERT INTO algorithm_dimension_relations "
                    "  (algorithm_type, dimension_id, is_default, weight, "
                    "   deleted, created_at, updated_at) "
                    "VALUES "
                    "  ('voice_llm', :did, FALSE, 1.0, FALSE, NOW(), NOW())"
                ), {'did': dim_id})
                print(f"  + 关联已插入 (voice_llm → {task_code} id={dim_id})")

            # ============================================================
            # Step 4: 注册参数映射
            # ============================================================
            print(f"\n--- Step 4: 注册 voice_llm → {task_code} 参数映射 ---")

            map_inserted = 0
            map_skipped = 0
            for m in dim_def['param_mappings']:
                (source, source_direction, source_param, target_param,
                 transform_type) = m

                existing = conn.execute(text(
                    "SELECT id FROM param_mappings "
                    "WHERE algorithm_type = 'voice_llm' AND source = :src "
                    "AND source_param = :sp AND dimension_id = :did"
                ), {'src': source, 'sp': source_param, 'did': dim_id}).fetchone()

                if existing:
                    # 更新 target_param 和 transform_type
                    conn.execute(text(
                        "UPDATE param_mappings SET "
                        "  target_param = :tp, transform_type = :tt, "
                        "  updated_at = NOW() "
                        "WHERE id = :id"
                    ), {
                        'tp': target_param, 'tt': transform_type,
                        'id': existing[0],
                    })
                    print(f"  - {source}.{source_param} → {target_param} 已存在，已更新")
                    map_skipped += 1
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
                    print(f"  + {source}.{source_param} → {target_param}")
                    map_inserted += 1

            print(f"  插入 {map_inserted} 条，跳过/更新 {map_skipped} 条")

        print(f"\n{'=' * 60}")
        print("  小艺评估维度种子数据注册完成")
        print(f"{'=' * 60}")


if __name__ == '__main__':
    print("=" * 60)
    print("小艺评估维度种子数据注册")
    print("=" * 60)
    print()
    print(f"数据库: {POSTGRES_URI[:POSTGRES_URI.rindex('@')]}@localhost/...")
    print()
    print("此脚本将注册：")
    print("1. xiaoyi_metrics 维度 — 小艺评估统一指标")
    print("   调一次 ASR，三个子指标共享结果")
    print()
    print("   输入: input_lastword, start_ms, query, question, record_file(wav), pause(停顿区间), first_frame_ms, end_ms, offset_ms")
    print()
    print("   子指标1: tor (接话率)")
    print("     输出: tor, tor_takeover_count, tor_total_pauses, tor_per_pause")
    print()
    print("   子指标2: false_takeover (误接管率)")
    print("     输出: false_takeover, ft_n_words, ft_duration, ft_total_pauses, ft_hit_words, ft_details")
    print()
    print("   子指标3: takeover_latency (接管时延)")
    print("     输出: takeover_latency_ms, first_word_begin_ms, model_first_word_ms, ...")
    print()
    print("ASR 结果由 eval_server 内部调用 asr_server.py /asr 接口获取，通过返回值传递")
    print()
    print("同时注册：")
    print("- voice_llm → xiaoyi_metrics 关联(algorithm_dimension_relations)")
    print("- voice_llm → xiaoyi_metrics 参数映射(param_mappings)")
    print()
    print("脚本可重复执行（幂等）")
    print()

    confirm = input("是否继续？(y/N): ").strip().lower()
    if confirm != 'y':
        print("已取消")
        sys.exit(0)

    try:
        seed_xiaoyi_dimensions()
    except Exception as e:
        print(f"\n迁移失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
