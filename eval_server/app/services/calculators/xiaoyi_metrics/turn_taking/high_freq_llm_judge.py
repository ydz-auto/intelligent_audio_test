# -*- coding: utf-8 -*-
"""
high_freq_llm_judge.py
高频轮换场景 LLM 裁判：以模型回复音频(ai_wav)为主输入，逐轮评估问答内容是否符合预期

场景: 飞花令 / 成语接龙 / 快问快答等高频多轮对话。
录屏不再可用：改为发送【模型回复音频 ai_wav】给多模态 LLM（直接听回复，不过小 ASR，
避免字面内容被糊掉），结合 rounds 文本上下文（用户提问/预期答案），逐轮判断模型回复
是否符合预期，返回 pass/fail + reason。不合并两路音频；video_path 保留为 legacy 回退。

参考 shared.llm_client 的多模态请求格式（音频 input_audio / 视频 image_url），
复用 config.LLM_JUDGE 配置（api_base_url / api_key / default_model）。
"""
import json
import os
import logging
from typing import Any, Dict, List, Optional

from app.services.calculators.base import BaseCalculator
from app.services.calculators.xiaoyi_metrics.shared.llm_client import (
    call_llm,
    parse_json,
    resolve_model,
)
from app.services.calculators.xiaoyi_metrics.shared.constants import (
    LLM_DEFAULT_MAX_TOKENS,
    LLM_DEFAULT_TEMPERATURE,
)

logger = logging.getLogger(__name__)

# ─────────── 场景规则 ───────────
_SCENARIO_RULES: Dict[str, str] = {
    '飞花令': (
        '用户指定一个字（如"花"），双方轮流说出包含该字的诗句或词语。'
        '模型回复必须包含指定字，且内容为有效的诗句或词语。'
    ),
    '成语接龙': (
        '用户说出一个成语，模型需接一个以上一个成语末字（或同音字）开头的成语。'
        '模型回复必须是有效的四字成语，且首字与用户成语末字匹配。'
    ),
    '快问快答': (
        '用户快速提问，模型需迅速给出准确、简洁的回答。'
        '重点考察回答的准确性和响应速度，回答应直截了当、不绕弯。'
    ),
    '自定义': '由调用方通过 scenario_rules 参数提供具体规则。',
}


# 文件编码 / content 构建 / LLM 调用 / JSON 解析
# 已统一由 shared.llm_client 提供（call_llm / parse_json），消除本文件重复实现
# _unwrap_value 由 BaseCalculator 统一提供


# ─────────── prompt 构建 ───────────


def _extract_round_fields(rd: Dict[str, Any]) -> Dict[str, str]:
    """从单轮数据中提取 query / answer / expected_answer"""
    query = BaseCalculator._unwrap_value(rd.get('query') or rd.get('question') or '') or ''
    answer = BaseCalculator._unwrap_value(
        rd.get('answer') or rd.get('response') or rd.get('ai_answer') or ''
    ) or ''
    expected = BaseCalculator._unwrap_value(
        rd.get('expected_answer') or rd.get('reference_answer')
        or rd.get('reference') or rd.get('correct_answer')
        or rd.get('expected') or ''
    ) or ''
    return {'query': query, 'answer': answer, 'expected_answer': expected}


def _build_prompt(rounds: List[Dict[str, Any]],
                  scenario_type: str = '',
                  scenario_rules: str = '') -> str:
    """构建高频轮换 LLM 评估 prompt

    将每轮的 query/answer/expected_answer 列出，配合录屏文件让 LLM 逐轮评判。
    """
    rules = scenario_rules or _SCENARIO_RULES.get(scenario_type, '') or '由录屏内容自行判断。'

    # 构建轮次信息块
    round_blocks: List[str] = []
    for i, rd in enumerate(rounds, 1):
        if not isinstance(rd, dict):
            continue
        fields = _extract_round_fields(rd)
        lines = [f'轮次{i}:']
        if fields['query']:
            lines.append(f'  用户提问: {fields["query"]}')
        if fields['answer']:
            lines.append(f'  模型回复: {fields["answer"]}')
        if fields['expected_answer']:
            lines.append(f'  预期答案: {fields["expected_answer"]}')
        else:
            lines.append('  预期答案: （未指定，请根据场景规则判断）')
        round_blocks.append('\n'.join(lines))

    rounds_text = '\n\n'.join(round_blocks) if round_blocks else '（未提供文本轮次信息，请从回复音频中自行识别）'

    # 构建 JSON 输出模板
    n = len(rounds)
    round_items = []
    for i in range(1, n + 1):
        round_items.append(
            f'    {{\n'
            f'      "round": {i},\n'
            f'      "pass": true,\n'
            f'      "reason": ""\n'
            f'    }}'
        )
    eval_text = ',\n'.join(round_items)

    return f"""你是语音对话质量评估专家。你将收到【模型回复音频】以及下方【对话轮次信息】（用户提问/预期答案为文本，模型回复以随附音频为准，不过小 ASR，直接听）。请结合回复音频内容与下方对话信息，逐轮判断模型回复是否符合预期。

═══════════════════════════════════════
【测试场景】{scenario_type or '高频轮换'}
【场景规则】{rules}
═══════════════════════════════════════

【对话轮次信息】
{rounds_text}

═══════════════════════════════════════
【判定要求】
═══════════════════════════════════════
对每一轮，判断模型回复是否符合预期：
- 成语接龙：末字是否匹配、是否为有效成语
- 飞花令：是否包含指定字、是否为有效诗句/词语
- 快问快答：答案是否准确
- 若提供了预期答案，回复应与预期答案一致或等价
- pass 为 true 表示符合预期，false 表示不符合
- reason 需简述判定依据（从回复音频中听到了什么、模型回复了什么、为何符合/不符合）

═══════════════════════════════════════
【输出格式】
═══════════════════════════════════════
输出严格 JSON，不要输出 JSON 以外的任何内容：

{{
  "rounds": [
{eval_text}
  ],
  "overall_pass_rate": 0.0
}}

其中：
- pass 为布尔值，true=符合预期，false=不符合
- reason 为简短判定理由
- overall_pass_rate 为通过轮数/总轮数（0.0-1.0）
- 若回复音频中某轮对话无法识别或不存在，pass 填 false、reason 说明原因"""


def _build_summary(per_round: List[Dict[str, Any]]) -> str:
    """将 per_round 结果聚合为自然语言摘要

    示例输出:
      "第1轮、第2轮符合预期；第3轮不符合预期（回复非成语，不符合接龙规则）"
    """
    if not per_round:
        return ''

    passed = [r['round'] for r in per_round if r.get('pass')]
    failed = [r for r in per_round if not r.get('pass')]

    parts: List[str] = []

    if passed:
        rounds_str = '、'.join(f'第{r}轮' for r in passed)
        parts.append(f'{rounds_str}符合预期')

    for r in failed:
        reason = r.get('reason', '')
        reason_part = f'（{reason}）' if reason else ''
        parts.append(f'第{r["round"]}轮不符合预期{reason_part}')

    return '；'.join(parts)


# ─────────── 主入口 ───────────
def evaluate_high_freq_llm(
    rounds: List[Dict[str, Any]] = None,
    scenario_type: str = '',
    scenario_rules: str = '',
    model: str = '',
    max_tokens: int = LLM_DEFAULT_MAX_TOKENS,
    temperature: float = LLM_DEFAULT_TEMPERATURE,
    ai_wav: str = '',
    **kwargs,
) -> Dict[str, Any]:
    """高频轮换场景 LLM 裁判主入口

    以【模型回复音频 ai_wav】为主输入（裁判模型直接听回复，不过小 ASR，
    避免飞花令/成语接龙等场景的字面内容被小 ASR 糊掉），结合 rounds 文本
    上下文（用户提问/预期答案），逐轮判断模型回复是否符合预期，返回 pass/fail + reason。

    Args:
        rounds: 多轮文本数据，每轮 {query, answer, expected_answer}（字段名兼容）
        scenario_type: 场景类型（飞花令/成语接龙/快问快答/自定义）
        scenario_rules: 自定义场景规则（scenario_type='自定义' 时使用）
        model: LLM 模型名，缺省读 config.LLM_JUDGE.default_model
        max_tokens: 最大输出 token 数
        temperature: 采样温度，评判场景建议低温 0.1
        ai_wav: 模型回复音频路径（主输入，被判定对象）

    Returns:
        dict: {
            'enabled': bool,
            'model': str,
            'scenario_type': str,
            'ai_wav': str,
            'n_rounds': int,
            'per_round': [{round, pass, reason}, ...],
            'overall_pass_rate': float|None,
            'n_passed': int,
            'n_failed': int,
            'summary': str,
            'tokens_used': int,
            'input_token': int,
            'output_token': int,
            'message': str,
        }
    """
    if not model:
        model = resolve_model(dimension='high_freq_llm_judge')

    # 主音频：ai_wav（模型回复，被判定对象）
    file_paths: List[str] = []
    if ai_wav and os.path.isfile(ai_wav):
        file_paths.append(ai_wav)

    if not file_paths:
        raise FileNotFoundError(
            f'模型回复音频(ai_wav)不存在或路径无效: ai_wav={ai_wav!r}'
        )

    # 过滤无效轮次
    valid_rounds = [rd for rd in (rounds or []) if isinstance(rd, dict)]

    prompt = _build_prompt(valid_rounds, scenario_type, scenario_rules)

    result: Dict[str, Any] = {
        'enabled': True,
        'model': model,
        'scenario_type': scenario_type,
        'ai_wav': ai_wav or '',
        'n_rounds': len(valid_rounds),
        'per_round': [],
        'overall_pass_rate': None,
        'n_passed': 0,
        'n_failed': 0,
        'summary': '',
        'tokens_used': 0,
        'input_token': 0,
        'output_token': 0,
        'message': '',
    }

    try:
        response = call_llm(
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            file_paths=file_paths,
        )
    except Exception as e:
        result['message'] = f'LLM 调用失败: {e}'
        result['enabled'] = False
        logger.error(f'[high_freq_llm_judge] LLM 调用失败: {e}')
        return result

    result['tokens_used'] = response.get('tokens_used', 0)
    result['input_token'] = response.get('input_token', 0)
    result['output_token'] = response.get('output_token', 0)

    parsed = parse_json(response['content'])
    if not parsed:
        result['message'] = 'LLM 输出解析失败'
        logger.error(
            f'[high_freq_llm_judge] LLM 输出解析失败: '
            f'{response["content"][:200]}'
        )
        return result

    # 提取每轮评估
    raw_rounds = parsed.get('rounds', [])
    if not isinstance(raw_rounds, list):
        raw_rounds = []

    per_round: List[Dict[str, Any]] = []
    for i, rd in enumerate(raw_rounds, 1):
        if not isinstance(rd, dict):
            continue
        per_round.append({
            'round': rd.get('round', i),
            'pass': bool(rd.get('pass', False)),
            'reason': rd.get('reason', ''),
        })

    result['per_round'] = per_round
    result['n_passed'] = sum(1 for r in per_round if r['pass'])
    result['n_failed'] = sum(1 for r in per_round if not r['pass'])
    if per_round:
        result['overall_pass_rate'] = round(result['n_passed'] / len(per_round), 3)

    # 聚合摘要：按 pass/fail 分组拼接自然语言
    result['summary'] = _build_summary(per_round)
    result['message'] = 'OK'

    logger.info(
        f'[high_freq_llm_judge] model={model} scenario={scenario_type} '
        f'n_rounds={len(per_round)} passed={result["n_passed"]} '
        f'failed={result["n_failed"]} pass_rate={result["overall_pass_rate"]} '
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
        description='高频轮换场景 LLM 裁判：传输录屏文件，逐轮评估问答内容'
    )
    parser.add_argument('video', help='录屏/音频文件路径')
    parser.add_argument('--rounds_json', required=True,
                        help='轮次 JSON 路径，每轮含 query/answer/expected_answer')
    parser.add_argument('--scenario_type', default='',
                        choices=['', '飞花令', '成语接龙', '快问快答', '自定义'],
                        help='场景类型')
    parser.add_argument('--scenario_rules', default='',
                        help='自定义场景规则（scenario_type=自定义 时使用）')
    parser.add_argument('--model', default='', help='LLM 模型名')
    parser.add_argument('--max_tokens', type=int, default=LLM_DEFAULT_MAX_TOKENS)
    parser.add_argument('--temperature', type=float, default=LLM_DEFAULT_TEMPERATURE)
    args = parser.parse_args()

    with open(args.rounds_json, encoding='utf-8') as f:
        rounds_data = json.load(f)

    r = evaluate_high_freq_llm(
        ai_wav=args.video,
        rounds=rounds_data,
        scenario_type=args.scenario_type,
        scenario_rules=args.scenario_rules,
        model=args.model,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
    )

    print('=' * 60)
    print(f'模型: {r["model"]}')
    print(f'场景: {r.get("scenario_type", "") or "N/A"}')
    print(f'音频: {r["ai_wav"]}')
    print(f'tokens: {r["tokens_used"]} (in={r["input_token"]}, out={r["output_token"]})')
    print(f'message: {r["message"]}')
    print('-' * 60)
    for rd in r.get('per_round', []):
        status = 'PASS' if rd.get('pass') else 'FAIL'
        print(f'\n  轮{rd["round"]} [{status}]')
        print(f'    理由: {rd.get("reason", "")}')
    print(f'\n  通过率: {r.get("overall_pass_rate")} '
          f'({r.get("n_passed", 0)}/{len(r.get("per_round", []))})')
    if r.get('summary'):
        print(f'  总结: {r["summary"]}')
    print('=' * 60)
    print(json.dumps(r, ensure_ascii=False, indent=2))
