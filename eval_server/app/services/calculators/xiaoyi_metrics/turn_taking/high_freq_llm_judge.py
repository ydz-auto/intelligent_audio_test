# -*- coding: utf-8 -*-
"""
high_freq_llm_judge.py
高频轮换场景 LLM 裁判：逐轮评估模型回复是否符合预期

场景: 飞花令 / 成语接龙 / 快问快答等高频多轮对话。

新模式（user_case + ASR）:
  - 输入 user_case（字符串/列表，每轮用户的提问或测试用例）
  - 对 ai_wav 做 ASR，按段间时间间隔自动分轮
  - 将 user_case 与 ASR 分轮结果一一对应，交给 LLM 逐轮判定 pass/fail
  - 纯文本调用，不再发送音频文件

旧模式（audio + rounds）:
  - 发送 ai_wav 音频给多模态 LLM 直接听
  - 结合 rounds 文本上下文（query/answer/expected_answer）逐轮判定
  - 当 user_case 为空时回退到此模式

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


# ─────────── user_case 解析 & ASR 分轮 ───────────


def _parse_user_case(user_case) -> List[str]:
    """将 user_case 解析为逐轮用例列表

    支持以下输入:
    - list: 直接使用，每元素为一轮用例
    - str 且为 .json 文件路径: 读取 JSON，提取 rounds[].segments[].input_text / query
    - str 且非文件路径: 按换行分割，每行为一轮用例
    """
    if not user_case:
        return []
    if isinstance(user_case, (list, tuple)):
        return [str(x).strip() for x in user_case if str(x).strip()]
    if isinstance(user_case, str):
        # JSON 文件路径
        if user_case.endswith('.json') and os.path.isfile(user_case):
            return _parse_user_case_json(user_case)
        # 多行文本
        return [line.strip() for line in user_case.split('\n') if line.strip()]
    return [str(user_case).strip()]


def _parse_user_case_json(json_path: str) -> List[str]:
    """从 JSON 文件提取逐轮用户用例

    JSON 结构:
        {"rounds": [{"round_number": 1, "segments": [{"input_text": "...", "query": "..."}]}]}

    每轮取 segments[0] 的 input_text（优先）或 query 作为用例。
    """
    try:
        with open(json_path, encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        logger.warning(f'[high_freq_llm_judge] 读取 user_case JSON 失败: {json_path}: {e}')
        return []

    rounds = data.get('rounds') if isinstance(data, dict) else None
    if not isinstance(rounds, list):
        logger.warning(f'[high_freq_llm_judge] user_case JSON 无 rounds 字段: {json_path}')
        return []

    cases: List[str] = []
    for rd in rounds:
        if not isinstance(rd, dict):
            continue
        segments = rd.get('segments')
        if not isinstance(segments, list) or not segments:
            # 兼容: round 本身直接含 input_text/query
            text = rd.get('input_text') or rd.get('query') or ''
            cases.append(str(text).strip())
            continue
        seg = segments[0] if isinstance(segments[0], dict) else {}
        text = seg.get('input_text') or seg.get('query') or ''
        cases.append(str(text).strip())

    # 过滤空行
    return [c for c in cases if c]


def _segment_asr_rounds(chunks: List[Dict[str, Any]],
                         seg_gap_s: float = 0.7,
                         round_gap_s: float = 2.0) -> List[Dict[str, Any]]:
    """将 ai_wav 的 ASR 词级 chunks 按时间间隔分割为多轮

    1. 先用 seg_gap_s（默认 0.7s，与模型侧分段一致）合并相邻词为语音段
    2. 再用 round_gap_s（默认 2.0s）将段分组为轮次：段间间隔 >= round_gap_s 视为新轮

    Returns:
        [{text, start_s, end_s, segments: [{start, end, text, words}]}, ...]
    """
    from app.services.calculators.xiaoyi_metrics.interruptibility.interruption import _to_segments

    segments = _to_segments(chunks, gap=seg_gap_s) if chunks else []
    if not segments:
        return []

    rounds: List[List[Dict[str, Any]]] = []
    current = [segments[0]]
    for i in range(1, len(segments)):
        gap = segments[i]['start'] - segments[i - 1]['end']
        if gap >= round_gap_s:
            rounds.append(current)
            current = [segments[i]]
        else:
            current.append(segments[i])
    rounds.append(current)

    result: List[Dict[str, Any]] = []
    for segs in rounds:
        text = ''.join(s['text'] for s in segs)
        result.append({
            'text': text.strip(),
            'start_s': segs[0]['start'],
            'end_s': segs[-1]['end'],
            'segments': segs,
        })
    return result


def _build_prompt_with_asr(user_cases: List[str],
                           asr_rounds: List[Dict[str, Any]],
                           scenario_type: str = '',
                           scenario_rules: str = '') -> str:
    """构建 user_case + ASR 转写结果的纯文本 prompt

    将每轮的用户用例与 ASR 转写结果一一对应，让 LLM 逐轮判定。
    """
    rules = scenario_rules or _SCENARIO_RULES.get(scenario_type, '') or '根据问答内容自行判断。'

    # 对齐轮次：以 user_cases 为基准，ASR 轮次可能多或少
    n_user = len(user_cases)
    n_asr = len(asr_rounds)
    n_rounds = max(n_user, n_asr)

    round_blocks: List[str] = []
    for i in range(n_rounds):
        lines = [f'轮次{i + 1}:']
        if i < n_user:
            lines.append(f'  用户提问/用例: {user_cases[i]}')
        else:
            lines.append('  用户提问/用例: （未提供）')
        if i < n_asr:
            rd = asr_rounds[i]
            lines.append(f'  模型回复(ASR): {rd["text"]}')
            lines.append(f'  回复时间: [{rd["start_s"]:.2f}s - {rd["end_s"]:.2f}s]')
        else:
            lines.append('  模型回复(ASR): （未检测到回复）')
        round_blocks.append('\n'.join(lines))

    rounds_text = '\n\n'.join(round_blocks) if round_blocks else '（无轮次信息）'

    # JSON 输出模板
    round_items = []
    for i in range(1, n_rounds + 1):
        round_items.append(
            f'    {{\n'
            f'      "round": {i},\n'
            f'      "pass": true,\n'
            f'      "reason": ""\n'
            f'    }}'
        )
    eval_text = ',\n'.join(round_items)

    return f"""你是语音对话质量评估专家。以下是高频轮换场景的多轮对话记录。用户提问/用例由测试方提供，
模型回复来自 ASR 转写（可能存在识别误差），请结合场景规则逐轮判断模型回复是否符合预期。

═══════════════════════════════════════
【测试场景】{scenario_type or '高频轮换'}
【场景规则】{rules}
【ASR 分轮说明】模型回复音频(ai_wav)为多轮聚合音频，按段间间隔 >= 2.0s 自动分轮。
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
- reason 需简述判定依据（模型回复了什么、为何符合/不符合）
- 若某轮未检测到模型回复，pass 填 false、reason 说明"未检测到回复"

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
- overall_pass_rate 为通过轮数/总轮数（0.0-1.0）"""


# ─────────── 主入口 ───────────
def evaluate_high_freq_llm(
    rounds: List[Dict[str, Any]] = None,
    scenario_type: str = '',
    scenario_rules: str = '',
    model: str = '',
    max_tokens: int = LLM_DEFAULT_MAX_TOKENS,
    temperature: float = LLM_DEFAULT_TEMPERATURE,
    ai_wav: str = '',
    user_case=None,
    ai_chunks: Optional[List[Dict[str, Any]]] = None,
    round_gap_s: float = 2.0,
    **kwargs,
) -> Dict[str, Any]:
    """高频轮换场景 LLM 裁判主入口

    新模式（user_case 非空时）:
      - 对 ai_wav 做 ASR 获取词级 chunks（优先用传入的 ai_chunks）
      - 按段间间隔自动分轮，与 user_case 一一对应
      - 纯文本调用 LLM，不发送音频

    旧模式（user_case 为空时回退）:
      - 发送 ai_wav 音频给多模态 LLM
      - 结合 rounds 文本上下文逐轮判定

    Args:
        rounds: 多轮文本数据（旧模式），每轮 {query, answer, expected_answer}
        scenario_type: 场景类型（飞花令/成语接龙/快问快答/自定义）
        scenario_rules: 自定义场景规则
        model: LLM 模型名，缺省读 config
        max_tokens / temperature: LLM 调用参数
        ai_wav: 模型回复音频路径
        user_case: 用户用例（str 按行分轮 / list 每元素一轮）
        ai_chunks: ai_wav 的 ASR 词级 chunks（可由上层共享注入，避免重复 ASR）
        round_gap_s: 分轮时间间隔阈值（秒），默认 2.0s

    Returns:
        dict: 同旧模式输出结构，额外含 asr_rounds / user_cases
    """
    if not model:
        model = resolve_model(dimension='high_freq_llm_judge')

    user_cases = _parse_user_case(user_case)

    result: Dict[str, Any] = {
        'enabled': True,
        'model': model,
        'scenario_type': scenario_type,
        'ai_wav': ai_wav or '',
        'n_rounds': 0,
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

    # ── 新模式：user_case + ASR ──
    if user_cases:
        # 获取 ASR chunks：优先用注入的共享结果
        if ai_chunks is None and ai_wav:
            from app.services.calculators.xiaoyi_metrics.turn_taking.strategy import TurnTakingBase
            ai_chunks = TurnTakingBase._get_asr_chunks(ai_wav, filter_punct=False) or []

        asr_rounds = _segment_asr_rounds(ai_chunks or [], round_gap_s=round_gap_s)
        result['asr_rounds'] = [
            {'text': r['text'], 'start_s': r['start_s'], 'end_s': r['end_s']}
            for r in asr_rounds
        ]
        result['user_cases'] = user_cases
        result['n_rounds'] = max(len(user_cases), len(asr_rounds))

        prompt = _build_prompt_with_asr(user_cases, asr_rounds, scenario_type, scenario_rules)

        file_paths = []  # 纯文本，不发送音频
    else:
        # ── 旧模式：audio + rounds ──
        file_paths: List[str] = []
        if ai_wav and os.path.isfile(ai_wav):
            file_paths.append(ai_wav)
        if not file_paths:
            raise FileNotFoundError(
                f'模型回复音频(ai_wav)不存在或路径无效: ai_wav={ai_wav!r}'
            )

        valid_rounds = [rd for rd in (rounds or []) if isinstance(rd, dict)]
        result['n_rounds'] = len(valid_rounds)
        prompt = _build_prompt(valid_rounds, scenario_type, scenario_rules)

    try:
        response = call_llm(
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            file_paths=file_paths if file_paths else None,
            log_context={'dimension': 'high_freq_llm_judge'},
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

    result['summary'] = _build_summary(per_round)
    result['message'] = 'OK'

    logger.info(
        f'[high_freq_llm_judge] model={model} scenario={scenario_type} '
        f'mode={"asr" if user_cases else "audio"} '
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
        description='高频轮换场景 LLM 裁判：逐轮评估问答内容'
    )
    parser.add_argument('audio', help='模型回复音频路径(ai_wav)')
    parser.add_argument('--rounds_json', default='',
                        help='轮次 JSON 路径（旧模式），每轮含 query/answer/expected_answer')
    parser.add_argument('--user_case', default='',
                        help='用户用例（新模式），多轮用换行分隔')
    parser.add_argument('--scenario_type', default='',
                        choices=['', '飞花令', '成语接龙', '快问快答', '自定义'],
                        help='场景类型')
    parser.add_argument('--scenario_rules', default='',
                        help='自定义场景规则（scenario_type=自定义 时使用）')
    parser.add_argument('--model', default='', help='LLM 模型名')
    parser.add_argument('--max_tokens', type=int, default=LLM_DEFAULT_MAX_TOKENS)
    parser.add_argument('--temperature', type=float, default=LLM_DEFAULT_TEMPERATURE)
    parser.add_argument('--round_gap_s', type=float, default=2.0,
                        help='ASR 分轮时间间隔阈值（秒）')
    args = parser.parse_args()

    rounds_data = None
    if args.rounds_json:
        with open(args.rounds_json, encoding='utf-8') as f:
            rounds_data = json.load(f)

    r = evaluate_high_freq_llm(
        ai_wav=args.audio,
        rounds=rounds_data,
        user_case=args.user_case or None,
        scenario_type=args.scenario_type,
        scenario_rules=args.scenario_rules,
        model=args.model,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        round_gap_s=args.round_gap_s,
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
