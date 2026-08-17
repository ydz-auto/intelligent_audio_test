# -*- coding: utf-8 -*-
"""打断 LLM 评估评分效果夹具（路线 B：直接调 eval_server，绕过 e2e/DB）

设计一个有评分梯度的 5 轮打断对话，验证 LLM 能否打出区分度（0-5 分，对标 Full-Duplex-Bench GPT-4o Score）：
  R1 打断(优秀回复)       → 期望高分 5
  R2 打断(中等:简短无衔接) → 期望中分 3-4
  R3 打断(答非所问/兜底)   → 期望低分 0-2
  R4 回原话题(成功恢复)    → 行为=C_RESPOND/C_RESUME, 高分
  R5 回原话题(简短/形同沉默)→ 行为=C_UNKNOWN, 低分

行为分类采用 v1.5 behavior.txt 的 C 轴四分类（C_RESPOND/C_RESUME/C_UNCERTAIN_HANDLING/C_UNKNOWN）。
原始话题：推荐一部适合周末看的电影
"""
import json
from app.services.xiaoyi_metrics import calculate_interruption_metrics

ORIGINAL_TOPIC = '推荐一部适合周末看的电影'

ROUNDS = [
    {
        'query': '别管电影了，附近有什么好吃的',
        'answer': '好的，附近有一家川菜馆评分 4.8，人均 80，需要我帮你导航过去吗？',
        'is_return_to_topic': False,
        '_expect': 'R1 打断·优秀(切题+衔接+主动引导) → 期望 5/5/5',
    },
    {
        'query': '现在几点了',
        'answer': '现在是下午三点。',
        'is_return_to_topic': False,
        '_expect': 'R2 打断·中等(回答了但简短、无上下文衔接) → 期望 3-4',
    },
    {
        'query': '你会唱歌吗',
        'answer': '你好，这个功能我还没学会，请问您需要什么帮助？',
        'is_return_to_topic': False,
        '_expect': 'R3 打断·低分(答非所问+兜底话术，未满足用户需求) → 期望 0-2',
    },
    {
        'query': '我们还是回到刚才说的电影吧',
        'answer': '好的，推荐你看《奥本海默》，诺兰执导，剧情紧凑，周末看很合适。',
        'is_return_to_topic': True,
        '_expect': 'R4 回原话题·成功(直接回应+围绕原话题+切题) → 行为=C_RESPOND, 高分',
    },
    {
        'query': '回到电影话题',
        'answer': '嗯，好的。',
        'is_return_to_topic': True,
        '_expect': 'R5 回原话题·失败(简短形同沉默，未真正回到原话题内容) → 行为=C_UNKNOWN, 低分',
    },
]

# ASR chunks（仅供时序指标不报错，评分焦点在 rounds 文本；两路等长时间轴）
USER_ASR = [
    {'text': '别管电影了', 'timestamp': [1.0, 1.6]},
    {'text': '附近有什么好吃的', 'timestamp': [1.6, 2.6]},
    {'text': '现在几点了', 'timestamp': [6.0, 6.6]},
    {'text': '你会唱歌吗', 'timestamp': [10.0, 10.6]},
    {'text': '我们还是回到刚才说的电影吧', 'timestamp': [14.0, 15.4]},
    {'text': '回到电影话题', 'timestamp': [19.0, 19.8]},
]
MODEL_ASR = [
    {'text': '好的', 'timestamp': [0.0, 0.3]},
    {'text': '附近有一家川菜馆', 'timestamp': [2.7, 3.8]},
    {'text': '现在是下午三点', 'timestamp': [6.7, 7.6]},
    {'text': '这个功能我还没学会', 'timestamp': [10.7, 11.8]},
    {'text': '好的推荐你看奥本海默', 'timestamp': [15.5, 17.2]},
    {'text': '嗯好的', 'timestamp': [20.0, 20.5]},
]


def run():
    result = calculate_interruption_metrics({
        'user_asr': USER_ASR,
        'model_asr': MODEL_ASR,
        'seg_merge_gap_s': 0.3,
        'enable_llm_eval': True,
        'rounds': ROUNDS,
        'original_topic': ORIGINAL_TOPIC,
    })

    print('=' * 70)
    print(f'原始话题: {ORIGINAL_TOPIC}')
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
