# -*- coding: utf-8 -*-
"""broadcast_score.py
播报复述评分裁判：判断模型对播报内容的复述质量，给出 1~5 分评分

输入:
    broadcast_text — 真实播报内容（文本）
    ai_wav         — 模型回复音频（从中提取 ASR 文本作为 answer）

输出: 严格 JSON，{score, reason, issues}
      score: 1~5 整数
      issues: {missing, wrong, fabricated}
"""
import json
import os
import logging
from typing import Any, Dict, Optional

from app.services.calculators.xiaoyi_metrics.shared.llm_client import (
    call_llm as call_llm_api,
    parse_json,
    get_asr_text,
    get_llm_config,
    resolve_model,
)
from app.services.calculators.xiaoyi_metrics.shared.constants import (
    LLM_DEFAULT_MAX_TOKENS,
    LLM_DEFAULT_TEMPERATURE,
)

logger = logging.getLogger(__name__)


# ─────────── prompt 模板 ───────────
TEMPLATE = """你是复述质量评分裁判。【真实播报内容】是刚在外部播放的播报文本，【助手回答】是语音助手复述的内容。
判断复述是否与真实播报内容相符，给出1~5分的评分。

评分方法：先把【真实播报内容】拆解为关键信息点（主体、事件、数字、时间、地点等），
再逐项核对【助手回答】覆盖了哪些、复述错了哪些、多说了哪些，最后按下列标准评分。

评分标准：
5分：完整复述了播报的全部关键信息点，表述准确；允许同义转述、语序调整、口语化表达。
4分：复述了大部分关键信息点，仅遗漏次要细节；或存在个别同音字/错别字但不改变信息含义。
3分：只复述了部分关键信息点，或遗漏了关键信息（如主要事件、重要的数字/时间/地点），但复述到的部分基本准确。
2分：复述内容与播报主体不符：大部分信息点错误或张冠李戴，或捏造了播报中不存在的实质性内容。
1分：完全不符：答非所问、未复述、拒答，或复述内容与播报内容相互矛盾。

补充规则：
- 忽略礼貌用语和引导语（如"好的，刚才播报的内容是"），只评判实质内容。
- 不要求逐字逐句：概括、转述均可，按关键信息点的覆盖度与准确性评分。
- 数字、时间、编号、地名等关键信息错误从严：出现一个关键信息错误，最高3分；两个及以上，最高2分。
- 同音字、错别字若不改变信息含义则不影响评分；改变含义的按信息错误处理。
- 捏造（说出播报中不存在的实质性信息）从严：出现即最高3分，捏造关键信息最高2分。
- 助手附带评论或建议不影响评分，除非其替代或歪曲了播报内容。
- 助手表示"没听到/无法复述"给1分。

只输出 JSON，不要输出其他内容：
{{"score": <1~5的整数>, "reason": "<一句话理由：先概括播报的关键信息点，再说明复述的覆盖与错误情况，引用原文>", "issues": {{"missing": ["遗漏的信息点"], "wrong": ["复述错误的信息点"], "fabricated": ["捏造的信息点"]}}}}

【真实播报内容】{broadcast_text}
【助手回答】{answer}"""


# ─────────── 评估函数 ───────────
def evaluate_broadcast_score(
    broadcast_text: str,
    ai_wav: str,
    model: str = '',
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
) -> Dict[str, Any]:
    """播报复述评分裁判

    Args:
        broadcast_text: 真实播报内容（文本）
        ai_wav:         模型回复音频路径（从中提取 ASR 文本作为 answer）
        model:          LLM 模型名（空则按维度配置解析）
        max_tokens:     LLM max_tokens
        temperature:    LLM temperature

    Returns:
        dict: {enabled, model, ai_wav, broadcast_text, answer,
               score, reason, issues, tokens_used, input_token, output_token, message}
    """
    llm_config = get_llm_config()
    if not model:
        model = resolve_model(dimension='broadcast_score')
    if not max_tokens:
        max_tokens = llm_config.get('max_tokens', LLM_DEFAULT_MAX_TOKENS)
    if temperature is None:
        temperature = llm_config.get('temperature', LLM_DEFAULT_TEMPERATURE)

    # 从 ai_wav 提取 ASR 文本
    if not ai_wav or not os.path.isfile(ai_wav):
        raise FileNotFoundError(
            f'模型回复音频(ai_wav)不存在或路径无效: ai_wav={ai_wav!r}'
        )

    answer_text = get_asr_text(ai_wav)

    prompt = TEMPLATE.format(
        broadcast_text=broadcast_text,
        answer=answer_text,
    )

    result: Dict[str, Any] = {
        'enabled': True,
        'model': model,
        'ai_wav': ai_wav,
        'broadcast_text': broadcast_text,
        'answer': answer_text,
        'score': None,
        'reason': '',
        'issues': {
            'missing': [],
            'wrong': [],
            'fabricated': [],
        },
        'tokens_used': 0,
        'input_token': 0,
        'output_token': 0,
        'message': '',
    }

    try:
        response = call_llm_api(
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            file_paths=None,
            log_context={'dimension': 'broadcast_score'},
        )
    except Exception as e:
        result['message'] = f'LLM 调用失败: {e}'
        result['enabled'] = False
        logger.error(f'[broadcast_score] LLM 调用失败: {e}')
        return result

    result['tokens_used'] = response.get('tokens_used', 0)
    result['input_token'] = response.get('input_token', 0)
    result['output_token'] = response.get('output_token', 0)

    parsed = parse_json(response['content'])
    if not parsed:
        result['message'] = 'LLM 输出解析失败'
        logger.error(
            f'[broadcast_score] LLM 输出解析失败: '
            f'{response["content"][:200]}'
        )
        return result

    # 校验 score 为 1~5 整数
    try:
        score = int(parsed.get('score'))
        if not 1 <= score <= 5:
            raise ValueError
        result['score'] = score
    except (KeyError, TypeError, ValueError):
        result['message'] = 'invalid_score'
        logger.error(
            f'[broadcast_score] score 无效: {parsed.get("score")!r}'
        )
        return result

    result['reason'] = parsed.get('reason', '')

    # 归一化 issues
    issues = parsed.get('issues')
    if not isinstance(issues, dict):
        issues = {}
    result['issues'] = {
        'missing': issues.get('missing') or [],
        'wrong': issues.get('wrong') or [],
        'fabricated': issues.get('fabricated') or [],
    }

    result['message'] = 'OK'

    logger.info(
        f'[broadcast_score] '
        f'model={model} ai_wav={ai_wav} '
        f'score={result["score"]} '
        f'tokens={result["tokens_used"]}'
    )
    return result


if __name__ == '__main__':
    import argparse
    from pathlib import Path

    # 独立运行时加载 eval_server/.env
    _env_path = Path(__file__).resolve().parents[4] / '.env'
    if _env_path.exists():
        with open(_env_path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ.setdefault(k.strip(), v.strip())

    parser = argparse.ArgumentParser(
        description='播报复述评分裁判：判断模型对播报内容的复述质量'
    )
    parser.add_argument('ai_wav', help='模型回复音频文件路径')
    parser.add_argument('--broadcast_text', default='', help='真实播报内容')
    args = parser.parse_args()

    r = evaluate_broadcast_score(
        broadcast_text=args.broadcast_text,
        ai_wav=args.ai_wav,
    )

    print('=' * 60)
    print(f'模型: {r["model"]}')
    print(f'ai_wav: {r["ai_wav"]}')
    print(f'tokens: {r["tokens_used"]} (in={r["input_token"]}, out={r["output_token"]})')
    print(f'message: {r["message"]}')
    print('-' * 60)
    print(f'  播报内容: {r["broadcast_text"]}')
    print(f'  复述内容: {r["answer"]}')
    print(f'  评分: {r["score"]}')
    print(f'  理由: {r["reason"]}')
    if any(r['issues'].values()):
        print(f'  遗漏: {r["issues"]["missing"]}')
        print(f'  错误: {r["issues"]["wrong"]}')
        print(f'  捏造: {r["issues"]["fabricated"]}')
    print('=' * 60)
    print(json.dumps(r, ensure_ascii=False, indent=2))
