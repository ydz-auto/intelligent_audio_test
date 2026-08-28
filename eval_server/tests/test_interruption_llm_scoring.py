# -*- coding: utf-8 -*-
"""打断 LLM 评估评分效果夹具（路线 B：直接调 eval_server，绕过 e2e/DB）

新接口：LLM 直接吃 compute_interruption_metrics 富集后的 per_event 字词级 ASR，
对每个真正发生的打断事件（event_type=='interruption'）做：
  (A) 是否真的打断（is_real_interruption）语义复核 + 简短原因
  (B) 模型恢复回复打分 连贯性/相关性/适应性（0-5，对标 Full-Duplex-Bench GPT-4o Score）

ASR 时间线设计（seg_merge_gap_s=0.5；相邻同侧段间隙 >0.5s，确保打断事件真实发生：
用户在模型说话期间插入语音）：
  greeting(0.0-0.3) 被开场白过滤剔除
  u_init(1.0-1.8) 初始请求 → recovery_only（不计入打断事件，LLM 不评）
  m_resp1(2.0-5.0) 模型正在推荐 → u2(3.0-4.6) 打断 → m_recovery2(5.7-7.5) 优秀回复
  m_active2(8.2-10.2) → u3(8.7-9.3) 打断 → m_recovery3(10.9-11.6) 中等回复
  m_active3(12.3-14.3) → u4(12.8-13.4) 打断 → m_recovery4(15.0-16.5) 答非所问

期望区分度：R2 高分(5) / R3 中分(3-4) / R4 低分(0-2)。
原始话题：推荐一部适合周末看的电影
"""
from app.services.calculators.xiaoyi_metrics.turn_taking import calculate_interruption_metrics

ORIGINAL_TOPIC = '推荐一部适合周末看的电影'

# 用户打断语音（字词级 ASR chunks，timestamp=[start_s, end_s]，与模型同时间轴）
USER_ASR = [
    {'text': '推荐', 'timestamp': [1.0, 1.4]},
    {'text': '周末看的电影', 'timestamp': [1.4, 1.8]},
    # u2: 在模型推荐期间打断
    {'text': '别管电影了', 'timestamp': [3.0, 3.6]},
    {'text': '附近有什么好吃的', 'timestamp': [3.6, 4.6]},
    # u3: 中等打断
    {'text': '现在几点了', 'timestamp': [8.7, 9.3]},
    # u4: 答非所问打断
    {'text': '你会唱歌吗', 'timestamp': [12.8, 13.4]},
]

# 模型语音（含开场白 + 被打断的尾巴 + 停顿 + 恢复回复）
# 注：相邻同侧段间隙 > 0.5s（编排层 seg_merge_gap_s 强制最小 0.5），避免恢复段与下一段合并
MODEL_ASR = [
    # 开场白（被开场白过滤剔除，不作为打断判定依据）
    {'text': '你好', 'timestamp': [0.0, 0.3]},
    # m_resp1：模型正在推荐（u2 打断它）
    {'text': '我给你推荐', 'timestamp': [2.0, 2.8]},
    {'text': '奥本海默诺兰执导剧情紧凑', 'timestamp': [2.8, 5.0]},
    # m_recovery2：优秀回复（切题+衔接+主动引导）→ 期望高分
    {'text': '附近有一家川菜馆评分4.8人均80', 'timestamp': [5.7, 6.9]},
    {'text': '需要我帮你导航过去吗', 'timestamp': [6.9, 7.5]},
    # m_active2：模型继续说（u3 打断它）
    {'text': '奥本海默周末看很合适', 'timestamp': [8.2, 10.2]},
    # m_recovery3：中等回复（回答了但简短、无上下文衔接）→ 期望中分
    {'text': '现在是下午三点', 'timestamp': [10.9, 11.6]},
    # m_active3：模型继续（u4 打断它）
    {'text': '你想看什么类型的', 'timestamp': [12.3, 14.3]},
    # m_recovery4：低分回复（答非所问+兜底话术）→ 期望 0-2
    {'text': '你好这个功能我还没学会', 'timestamp': [15.0, 15.9]},
    {'text': '请问您需要什么帮助', 'timestamp': [15.9, 16.5]},
]

# 打断事件期望（按 u 出现顺序，仅 interruption 事件，供打印对照；key=合并后 user_text）
EXPECT = {
    '别管电影了附近有什么好吃的': 'R1 打断·优秀(切题+衔接+主动引导) → 期望 5/5/5',
    '现在几点了': 'R2 打断·中等(回答了但简短、无上下文衔接) → 期望 3-4',
    '你会唱歌吗': 'R3 打断·低分(答非所问+兜底话术) → 期望 0-2',
}

INPUT = {
    'user_asr': USER_ASR,
    'model_asr': MODEL_ASR,
    'seg_merge_gap_s': 0.5,
    'enable_llm_eval': True,
    'original_topic': ORIGINAL_TOPIC,
}


def run():
    import json
    print('=' * 70)
    print(f'原始话题: {ORIGINAL_TOPIC}')
    print('=' * 70)
    result = calculate_interruption_metrics(INPUT)
    print(f"LLM: enabled={result['llm_eval'].get('enabled')} model={result['llm_eval'].get('model')}")
    print(f"本地数值: success_rate={result['interruption_success_rate']} "
          f"n_events={result['n_events']} "
          f"stop_rate={result['stop_rate']} resume_rate={result['resume_rate']}")
    print(f"LLM 复核: interruption_real_rate={result['llm_eval'].get('interruption_real_rate')} "
          f"n_events_evaluated={result['llm_eval'].get('n_events_evaluated')}")
    print('=' * 70)

    print('\n【逐事件 LLM 复核 + 回复打分】')
    for r in result.get('llm_recovery_per_round', []):
        exp = EXPECT.get(r.get('user_text', ''), '')
        print(f'\n  {exp}')
        print(f"  用户打断        : {r.get('user_text')}")
        print(f"  模型被打断尾巴  : {r.get('model_interrupted_text')}")
        print(f"  模型恢复回复    : {r.get('model_recovery_text')}")
        print(f"  是否真的打断    : {r.get('is_real_interruption')} | 原因: {r.get('interruption_reason')}")
        if r.get('error'):
            print(f"  ERROR           : {r['error']}")
        else:
            print(f"  分数            : 连贯={r.get('coherence')} 相关={r.get('relevance')} "
                  f"适应={r.get('adaptability')} 总={r.get('overall')}")
            print(f"  连贯理由        : {r.get('coherence_reason')}")
            print(f"  相关理由        : {r.get('relevance_reason')}")
            print(f"  适应理由        : {r.get('adaptability_reason')}")

    print('\n' + '=' * 70)
    print('【聚合】')
    print(f"  回复均分: 连贯={result.get('llm_recovery_avg_coherence')} "
          f"相关={result.get('llm_recovery_avg_relevance')} "
          f"适应={result.get('llm_recovery_avg_adaptability')}")
    print('=' * 70)
    return result


if __name__ == '__main__':
    run()
