# -*- coding: utf-8 -*-
"""打断 LLM 评估评分效果夹具 v2（路线 B：直接调 eval_server）

新接口：LLM 直接吃 per_event 字词级 ASR，对每个真正打断事件做是否真打断的语义复核
+ 模型恢复回复打分（连贯性/相关性/适应性，0-5，对标 Full-Duplex-Bench GPT-4o Score）。
不传 rounds；success_rate 全部本地算。

场景：原始话题=「帮我规划北京周末两日游」。3 个打断事件，评分梯度：
  R1 打断(优秀:切题+衔接+主动引导回行程) → 期望高分 5
  R2 打断(中等:回答了但简短、无上下文衔接) → 期望中分 3-4
  R3 打断(低分:答非所问+兜底话术) → 期望 0-2

ASR 时间线（seg_merge_gap_s=0.5；相邻同侧段间隙 >0.5s）：
  greeting(0.0-0.3) 被开场白过滤；u_init(1.0-2.0) 初始请求 → recovery_only（不评）
  m_resp1(2.5-5.5) → u2(3.0-4.5) 打断 → m_recovery2(6.2-8.5) 优秀
  m_active2(9.2-11.2) → u3(9.7-10.3) 打断 → m_recovery3(11.9-12.7) 中等
  m_active3(13.4-15.4) → u4(13.9-14.5) 打断 → m_recovery4(16.1-17.8) 答非所问

用法: cd eval_server && python tests/test_interruption_llm_scoring_v2.py
"""
from app.services.calculators.xiaoyi_metrics.interruptibility import calculate_interruption_metrics

ORIGINAL_TOPIC = '帮我规划北京周末两日游'

USER_ASR = [
    {'text': '帮我规划', 'timestamp': [1.0, 1.5]},
    {'text': '北京周末两日游', 'timestamp': [1.5, 2.0]},
    # u2: 在模型介绍行程期间打断
    {'text': '等等', 'timestamp': [3.0, 3.4]},
    {'text': '今天北京天气怎么样', 'timestamp': [3.4, 4.5]},
    # u3: 中等打断
    {'text': '现在几点了', 'timestamp': [9.7, 10.3]},
    # u4: 答非所问打断
    {'text': '你会做饭吗', 'timestamp': [13.9, 14.5]},
]

MODEL_ASR = [
    # 开场白（被过滤）
    {'text': '好的', 'timestamp': [0.0, 0.3]},
    # m_resp1：模型正在介绍行程（u2 打断它）
    {'text': '第一天上午故宫景山', 'timestamp': [2.5, 4.0]},
    {'text': '下午北海第二天颐和园圆明园', 'timestamp': [4.0, 5.5]},
    # m_recovery2：优秀回复（切题+衔接+主动引导回行程）→ 期望高分
    {'text': '今天北京晴最高28度挺适合出游的', 'timestamp': [6.2, 7.7]},
    {'text': '想继续看行程安排吗', 'timestamp': [7.7, 8.5]},
    # m_active2：模型继续说（u3 打断它）
    {'text': '比如上午先去故宫', 'timestamp': [9.2, 11.2]},
    # m_recovery3：中等回复（回答了但简短）→ 期望中分
    {'text': '现在是上午十点', 'timestamp': [11.9, 12.7]},
    # m_active3：模型继续（u4 打断它）
    {'text': '下午逛景山', 'timestamp': [13.4, 15.4]},
    # m_recovery4：低分回复（答非所问+兜底）→ 期望 0-2
    {'text': '抱歉我是个语音助手', 'timestamp': [16.1, 17.0]},
    {'text': '听不懂您的问题请重新说一遍', 'timestamp': [17.0, 17.8]},
]

EXPECT = {
    '等等今天北京天气怎么样': 'R1 打断·优秀(切题+衔接+主动引导回行程) → 期望 5/5/5',
    '现在几点了': 'R2 打断·中等(回答了但简短、无上下文衔接) → 期望 3-4',
    '你会做饭吗': 'R3 打断·低分(答非所问+兜底话术) → 期望 0-2',
}

INPUT = {
    'user_asr': USER_ASR,
    'model_asr': MODEL_ASR,
    'seg_merge_gap_s': 0.5,
    'enable_llm_eval': True,
    'original_topic': ORIGINAL_TOPIC,
}


def run():
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
