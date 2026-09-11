# -*- coding: utf-8 -*-
"""judge_answer.py
环境声感知理解裁判：判断助手对环境声的描述是否正确

输入:
    question     — 用户问题（user_case，文本）
    ai_wav       — 模型回复音频（从中提取 ASR 文本作为 answer）
    ground_truth — 真实环境描述（文本）

输出: 严格 JSON，{verdict, hit, reason}
      verdict: correct / partial / incorrect / no_answer
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
TEMPLATE = """你是环境声答复制裁判。根据【真实环境】判断【助手回答】中对环境声的描述是否正确。
判定只依据【真实环境】字段，不要凭常识自行想象可能存在的声音。
只评判"环境声是什么"这一核心内容，忽略语气词、礼貌用语和无法验证的细节。

判定规则：
1. 同义或等价表述算正确：如"雨声"="下雨的声音"="rain"。
2. 回答是真实声音的具体实例 → correct：真实环境"交通噪声"，答"汽车驶过的声音" → correct。
3. 回答比真实声音更宽泛 → partial：真实环境"狗叫声"，答"动物叫声" → partial。
4. 真实环境含多种声音时，回答命中其中任一主要声音 → correct；仅命中次要声音或表述含糊 → partial。
5. 回答夹带真实环境中不存在的声音，但同时命中真实声音 → 按命中判定，不影响结论。
6. 回答只提到真实环境中不存在的声音，或答非所问 → incorrect。
7. 拒答、反问、"听不清/无法判断" → no_answer。

只输出 JSON，不要输出其他内容：
{{"verdict": "correct|partial|incorrect|no_answer", "hit": "命中的声音,无则null", "reason": "一句话理由"}}

【问题】{question}
【助手回答】{answer}
【真实环境】{ground_truth}"""


# ─────────── 评估函数 ───────────
def evaluate_judge_answer(
    question: str,
    ai_wav: str,
    ground_truth: str,
    model: str = '',
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
) -> Dict[str, Any]:
    """环境声感知理解裁判

    Args:
        question:     用户问题（user_case，文本）
        ai_wav:       模型回复音频路径（从中提取 ASR 文本作为 answer）
        ground_truth: 真实环境描述（文本）
        model:        LLM 模型名（空则按维度配置解析）
        max_tokens:   LLM max_tokens
        temperature:  LLM temperature

    Returns:
        dict: {enabled, model, ai_wav, question, answer, ground_truth,
               verdict, hit, reason, tokens_used, input_token, output_token, message}
    """
    llm_config = get_llm_config()
    if not model:
        model = resolve_model(dimension='judge_answer')
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
        question=question,
        answer=answer_text,
        ground_truth=ground_truth,
    )

    result: Dict[str, Any] = {
        'enabled': True,
        'model': model,
        'ai_wav': ai_wav,
        'question': question,
        'answer': answer_text,
        'ground_truth': ground_truth,
        'verdict': '',
        'hit': None,
        'reason': '',
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
            log_context={'dimension': 'judge_answer'},
        )
    except Exception as e:
        result['message'] = f'LLM 调用失败: {e}'
        result['enabled'] = False
        logger.error(f'[judge_answer] LLM 调用失败: {e}')
        return result

    result['tokens_used'] = response.get('tokens_used', 0)
    result['input_token'] = response.get('input_token', 0)
    result['output_token'] = response.get('output_token', 0)

    parsed = parse_json(response['content'])
    if not parsed:
        result['message'] = 'LLM 输出解析失败'
        logger.error(
            f'[judge_answer] LLM 输出解析失败: '
            f'{response["content"][:200]}'
        )
        return result

    result['verdict'] = parsed.get('verdict', '')
    result['hit'] = parsed.get('hit')
    result['reason'] = parsed.get('reason', '')
    result['message'] = 'OK'

    logger.info(
        f'[judge_answer] '
        f'model={model} ai_wav={ai_wav} '
        f'verdict={result["verdict"]} '
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
        description='环境声感知理解裁判：判断助手对环境声的描述是否正确'
    )
    parser.add_argument('ai_wav', help='模型回复音频文件路径')
    parser.add_argument('--question', default='刚才电视里是什么声音？', help='用户问题（user_case）')
    parser.add_argument('--ground_truth', default='', help='真实环境描述')
    args = parser.parse_args()

    r = evaluate_judge_answer(
        question=args.question,
        ai_wav=args.ai_wav,
        ground_truth=args.ground_truth,
    )

    print('=' * 60)
    print(f'模型: {r["model"]}')
    print(f'ai_wav: {r["ai_wav"]}')
    print(f'tokens: {r["tokens_used"]} (in={r["input_token"]}, out={r["output_token"]})')
    print(f'message: {r["message"]}')
    print('-' * 60)
    print(f'  问题: {r["question"]}')
    print(f'  回答: {r["answer"]}')
    print(f'  真实环境: {r["ground_truth"]}')
    print(f'  判定: {r["verdict"]}')
    print(f'  命中: {r["hit"]}')
    print(f'  理由: {r["reason"]}')
    print('=' * 60)
    print(json.dumps(r, ensure_ascii=False, indent=2))
