# -*- coding: utf-8 -*-
"""单轮模型回复质量评分。

输入: case_wav 的 ASR 文本（用户预期内容）+ ai_wav 的 ASR 文本（模型实际回复），
调用 LLM 对模型回复质量进行打分。

LLM 参数体系与 false_takeover 共用同一套 config.LLM_JUDGE，
dimension 为 'reply_quality'，可通过 .env 中 LLM_JUDGE_MODEL_REPLY_QUALITY 单独指定模型。
"""
import json
import logging
from typing import Any, Dict, List, Optional

from app.services.calculators.xiaoyi_metrics.shared.llm_client import (
    call_llm,
    parse_json,
    get_llm_config,
    resolve_model,
)
from app.services.calculators.xiaoyi_metrics.shared.constants import (
    LLM_DEFAULT_MAX_TOKENS,
    LLM_DEFAULT_TEMPERATURE,
)

logger = logging.getLogger(__name__)


def _build_reply_quality_prompt(user_text: str, ai_text: str) -> str:
    """构建回复质量评分 prompt。"""
    return f"""# 角色：语音交互回复质量裁判

## 核心任务
基于用户提问内容和模型回复内容，对模型回复质量进行评分（1-5分），并给出评分理由。

## 评分标准

### 5分（优秀）
- 回答准确、完整，直接回应用户问题
- 表达流畅自然，逻辑清晰
- 无事实错误，无冗余信息

### 4分（良好）
- 基本回答了用户问题，但存在轻微不足
- 表达较流畅，偶有小瑕疵（如轻微啰嗦但不影响理解）

### 3分（合格）
- 部分回答了用户问题，但答案不完整或针对性不强
- 表达略显笼统，信息量不足

### 2分（较差）
- 回答了少量内容，但大部分未命中用户需求
- 存在明显啰嗦、不专业、或信息不够相关的问题

### 1分（不合格）
- 未回答用户问题，或回答内容完全错误
- 出现中英混杂、异常符号、逻辑混乱、重复雷同等严重问题
- 表达加重或引起用户负性情绪

## 输入数据

【用户提问】（来自 case_wav ASR 转写）：
{user_text or '（无 ASR 文本）'}

【模型回复】（来自 ai_wav ASR 转写）：
{ai_text or '（无 ASR 文本）'}

## 强制输出格式（必须严格 JSON，不要多余解释，不要 markdown）
{{"score": 4, "reason": "评分理由", "analysis": {{"accuracy": "准确性分析", "completeness": "完整性分析", "fluency": "流畅性分析"}}}}

score 说明：1-5 整数分数，5 为满分。"""


def evaluate_reply_quality(
    case_wav: str = '',
    ai_wav: str = '',
    user_text: str = '',
    ai_text: str = '',
    user_chunks: Optional[List[Dict[str, Any]]] = None,
    ai_chunks: Optional[List[Dict[str, Any]]] = None,
    model: str = '',
    max_tokens: int = 0,
    temperature: float = -1.0,
) -> Dict[str, Any]:
    """对单轮模型回复质量进行 LLM 评分。

    优先使用外部传入的 user_text / ai_text；
    若未传入，则从 user_chunks / ai_chunks 中拼接文本；
    若仍无，则从 case_wav / ai_wav 的 ASR JSON 读取。

    Args:
        case_wav: 用户侧音频路径（用于回退读取 ASR JSON）
        ai_wav: 模型回复音频路径（用于回退读取 ASR JSON）
        user_text: 用户侧 ASR 文本（优先使用）
        ai_text: 模型侧 ASR 文本（优先使用）
        user_chunks: 用户侧词级 ASR chunks（回退拼接文本）
        ai_chunks: 模型侧词级 ASR chunks（回退拼接文本）
        model: LLM 模型名（留空自动解析）
        max_tokens: LLM 最大输出 token
        temperature: LLM 采样温度

    Returns:
        dict: {score, reason, analysis, user_text, ai_text, message}
    """
    result: Dict[str, Any] = {
        'user_text': '',
        'ai_text': '',
        'score': None,
        'reason': '',
        'analysis': {},
        'message': '',
    }

    # ── 获取用户文本 ──
    if user_text:
        result['user_text'] = user_text
    elif user_chunks:
        result['user_text'] = ''.join(c.get('text', '') for c in user_chunks if isinstance(c, dict))
    elif case_wav:
        from app.services.calculators.xiaoyi_metrics.shared.llm_client import get_asr_text
        result['user_text'] = get_asr_text(case_wav)

    # ── 获取模型文本 ──
    if ai_text:
        result['ai_text'] = ai_text
    elif ai_chunks:
        result['ai_text'] = ''.join(c.get('text', '') for c in ai_chunks if isinstance(c, dict))
    elif ai_wav:
        from app.services.calculators.xiaoyi_metrics.shared.llm_client import get_asr_text
        result['ai_text'] = get_asr_text(ai_wav)

    # ── 检查 LLM 配置 ──
    llm_config = get_llm_config()
    api_base = llm_config.get('api_base_url', '')
    api_key = llm_config.get('api_key', '')
    if not api_base or not api_key:
        result['message'] = 'LLM 评估未配置：请在 .env 设置 LLM_JUDGE_API_BASE 与 LLM_JUDGE_API_KEY'
        return result

    # ── 解析模型名 ──
    resolved_model = resolve_model(model, dimension='reply_quality')

    # ── 解析 LLM 参数 ──
    _max_tokens = max_tokens if max_tokens > 0 else llm_config.get('max_tokens', LLM_DEFAULT_MAX_TOKENS)
    _temperature = temperature if temperature >= 0 else llm_config.get('temperature', LLM_DEFAULT_TEMPERATURE)

    # ── 构建 prompt ──
    prompt = _build_reply_quality_prompt(result['user_text'], result['ai_text'])

    # ── 调用 LLM ──
    try:
        resp = call_llm(
            model=resolved_model,
            prompt=prompt,
            max_tokens=_max_tokens,
            temperature=_temperature,
            file_paths=None,
            log_context={'dimension': 'reply_quality'},
        )
    except Exception as exc:
        logger.exception('[reply_quality] LLM 调用失败')
        result['message'] = f'LLM 调用失败: {exc}'
        return result

    # ── 解析返回 ──
    parsed = parse_json(resp.get('content', ''))
    if not parsed:
        result['message'] = f'LLM 返回解析失败: {resp.get("content", "")[:200]}'
        return result

    result['score'] = parsed.get('score')
    result['reason'] = parsed.get('reason', '')
    result['analysis'] = parsed.get('analysis', {})
    result['message'] = 'OK'
    return result


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='单轮模型回复质量评分')
    parser.add_argument('--case-wav', default='', help='用户侧音频路径')
    parser.add_argument('--ai-wav', default='', help='模型回复音频路径')
    parser.add_argument('--user-text', default='', help='用户侧 ASR 文本（可选，优先使用）')
    parser.add_argument('--ai-text', default='', help='模型侧 ASR 文本（可选，优先使用）')
    parser.add_argument('--model', default='', help='LLM 模型名（留空自动解析）')
    args = parser.parse_args()

    res = evaluate_reply_quality(
        case_wav=args.case_wav,
        ai_wav=args.ai_wav,
        user_text=args.user_text,
        ai_text=args.ai_text,
        model=args.model,
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))
