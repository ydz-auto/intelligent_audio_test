# -*- coding: utf-8 -*-
"""打断 LLM 评估评分效果夹具 v2（伪造数据，跑路线 B：直接调 eval_server）

新场景：原始话题=「帮我规划北京周末两日游」。5 轮打断对话，带评分梯度（0-5，对标 Full-Duplex-Bench GPT-4o Score）：
  R1 打断(优秀:切题+衔接+主动引导) → 期望高分 5
  R2 打断(中等:简短无衔接)        → 期望中分 3-4
  R3 打断(低分:答非所问+兜底话术)   → 期望 0-2
  R4 回原话题(成功恢复)            → 行为=C_RESPOND/C_RESUME, 高分
  R5 回原话题(简短形同沉默)         → 行为=C_UNKNOWN, 低分

行为分类采用 v1.5 behavior.txt 的 C 轴四分类（C_RESPOND/C_RESUME/C_UNCERTAIN_HANDLING/C_UNKNOWN）。
用法: cd eval_server && python tests/test_interruption_llm_scoring_v2.py
"""
import json
from app.services.xiaoyi_metrics import calculate_interruption_metrics

ORIGINAL_TOPIC = '帮我规划北京周末两日游'

ROUNDS = [
    {
        'query': '等等，今天北京天气怎么样',
        'answer': '今天北京晴，最高 28 度，挺适合出游的。想继续看行程安排吗？比如上午先去故宫，下午逛景山。',
        'is_return_to_topic': False,
        '_expect': 'R1 打断·优秀(切题+衔接+主动引导回行程) → 期望 5/5/5',
    },
    {
        'query': '现在几点了',
        'answer': '现在是上午十点。',
        'is_return_to_topic': False,
        '_expect': 'R2 打断·中等(回答了但简短、无上下文衔接) → 期望 3-4',
    },
    {
        'query': '你会做饭吗',
        'answer': '抱歉，我是个语音助手，听不懂您的问题，请重新说一遍。',
        'is_return_to_topic': False,
        '_expect': 'R3 打断·低分(答非所问+兜底话术，未满足需求) → 期望 0-2',
    },
    {
        'query': '我们还是接着说北京行程吧',
        'answer': '好的，继续给你介绍：第一天上午故宫和景山，下午北海公园；第二天颐和园加圆明园。需要我排一下时间表吗。',
        'is_return_to_topic': True,
        '_expect': 'R4 回原话题·成功(直接回应+围绕原话题+切题) → 行为=C_RESPOND, 高分',
    },
    {
        'query': '回到旅游计划',
        'answer': '好的，没问题。',
        'is_return_to_topic': True,
        '_expect': 'R5 回原话题·失败(简短形同沉默，未真正回到原话题) → 行为=C_UNKNOWN, 低分',
    },
]

# ASR chunks（仅供时序指标不报错，评分焦点在 rounds 文本；时间轴与轮次对齐）
USER_ASR = [
    {'text': '等等', 'timestamp': [1.0, 1.4]},
    {'text': '今天北京天气怎么样', 'timestamp': [1.4, 3.0]},
    {'text': '现在几点了', 'timestamp': [6.0, 6.6]},
    {'text': '你会做饭吗', 'timestamp': [10.0, 10.6]},
    {'text': '我们还是接着说北京行程吧', 'timestamp': [14.0, 15.6]},
    {'text': '回到旅游计划', 'timestamp': [19.0, 19.8]},
]
MODEL_ASR = [
    {'text': '今天北京晴', 'timestamp': [3.2, 4.0]},
    {'text': '最高28度挺适合出游的想继续看行程安排吗', 'timestamp': [4.0, 5.8]},
    {'text': '现在是上午十点', 'timestamp': [6.8, 7.6]},
    {'text': '我是个语音助手听不懂您的问题请重新说一遍', 'timestamp': [10.8, 12.2]},
    {'text': '好的继续给你介绍第一天故宫景山北海第二天颐和园圆明园需要排时间表吗', 'timestamp': [15.8, 19.4]},
    {'text': '好的没问题', 'timestamp': [20.0, 20.5]},
]

INPUT = {
    'user_asr': USER_ASR,
    'model_asr': MODEL_ASR,
    'seg_merge_gap_s': 0.3,
    'enable_llm_eval': True,
    'rounds': ROUNDS,
    'original_topic': ORIGINAL_TOPIC,
}


def run():
    print('=' * 70)
    print(f'原始话题: {ORIGINAL_TOPIC}')
    print('输入数据(伪造,按脚本格式):')
    print(json.dumps(INPUT, ensure_ascii=False, indent=2)[:1200])
    print('=' * 70)
    result = calculate_interruption_metrics(INPUT)
    print(f'LLM 模型: {result["llm_eval"].get("model")} | enabled: {result["llm_eval"].get("enabled")}')
    print('=' * 70)

    print('\n【1) 打断后回复打分（每轮）】')
    for r in result['llm_recovery_per_round']:
        exp = next((x['_expect'] for x in ROUNDS if x['query'] == r['query']), '')
        print(f'\n  {exp}')
        print(f'  query : {r["query"]}')
        print(f'  answer: {r["answer"]}')
        if r.get('error'):
            print(f'  ERROR : {r["error"]}')
        else:
            print(f'  分数  : 连贯={r["coherence"]} 相关={r["relevance"]} 适应={r["adaptability"]} 总={r["overall"]}')
            print(f'  理由  : {r["reason"]}')

    print('\n【2) 回到原话题行为判断 + 【3) 回到原话题回复打分】')
    beh = {b['round']: b for b in result['llm_return_per_round']}
    scs = {s['round']: s for s in result['llm_return_scores_per_round']}
    for rnd in [b['round'] for b in result['llm_return_per_round']]:
        b = beh[rnd]; s = scs.get(rnd, {})
        exp = next((x['_expect'] for x in ROUNDS if x.get('is_return_to_topic') and x['query'] == b['query']), '')
        print(f'\n  {exp}')
        print(f'  query : {b["query"]}')
        print(f'  answer: {b["answer"]}')
        print(f'  行为  : {b["behavior"]}  (理由: {b["reason"]})')
        if s:
            print(f'  分数  : 连贯={s.get("coherence")} 相关={s.get("relevance")} 适应={s.get("adaptability")} 总={s.get("overall")}')
            print(f'  理由  : {s.get("reason")}')

    print('\n' + '=' * 70)
    print('【聚合】')
    print(f'  打断后回复  均分: 连贯={result["llm_recovery_avg_coherence"]} '
          f'相关={result["llm_recovery_avg_relevance"]} 适应={result["llm_recovery_avg_adaptability"]}')
    print(f'  回原话题行为 分布: {result["llm_return_behavior_summary"]}')
    print(f'  回原话题回复 均分: 连贯={result["llm_return_avg_coherence"]} '
          f'相关={result["llm_return_avg_relevance"]} 适应={result["llm_return_avg_adaptability"]}')
    print('=' * 70)
    return result


if __name__ == '__main__':
    run()
