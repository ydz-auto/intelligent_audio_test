# -*- coding: utf-8 -*-
"""逐轮模型回复质量评分。

仅当该轮分类为"接管"时才进行回复质量评分；
"未接管"和"误解管"时评分为 null。

LLM 参数体系与 false_takeover 共用同一套 config.LLM_JUDGE，
dimension 为 'reply_quality'，可通过 .env 中 LLM_JUDGE_MODEL_REPLY_QUALITY 单独指定模型。

输入: 该轮的 user_chunks（用户提问）+ ai_chunks（模型回复），
调用 LLM 对模型回复质量进行打分（1-5分）。
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
    TIMELINE_MAX_ITEMS_CHUNKS,
)

logger = logging.getLogger(__name__)


def _build_reply_quality_prompt(user_text: str, ai_text: str) -> str:
    """构建回复质量评分 prompt。"""
    return f"""# 角色：语音交互回复质量裁判

## 核心任务
基于用户提问内容和模型回复内容，对模型回复质量进行评分（1-5分），并给出评分理由。

## 重要说明
- 本评分针对语音交互场景，回复文本来自 ASR 语音识别结果，**不关注标点符号**的有无或准确性
- 不要因为缺少标点、标点不规范而扣分，这属于 ASR 识别特性，非模型回复质量问题

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

【用户提问】：
{user_text or '（无 ASR 文本）'}

【模型回复】：
{ai_text or '（无 ASR 文本）'}

## 强制输出格式（必须严格 JSON，不要多余解释，不要 markdown）
{{"score": 4, "reason": "评分理由", "analysis": {{"accuracy": "准确性分析", "completeness": "完整性分析", "fluency": "流畅性分析"}}}}

score 说明：1-5 整数分数，5 为满分。"""


def evaluate_reply_quality_per_turn(
    user_chunks: Optional[List[Dict[str, Any]]] = None,
    ai_chunks: Optional[List[Dict[str, Any]]] = None,
    classification: str = '',
    task_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """对单轮模型回复质量进行 LLM 评分。

    仅当 classification == '接管' 时才调 LLM 评分；
    '未接管' 和 '误解管' 直接返回 null。

    Args:
        user_chunks: 该轮用户侧 ASR chunks
        ai_chunks: 该轮模型侧 ASR chunks
        classification: 该轮的三分类结果（'接管' / '未接管' / '误解管'）
        task_params: 读取 llm_model 配置

    Returns:
        dict: {
            'score': int|None,      1-5 分，未接管/误解管时为 None
            'reason': str,           评分理由
            'analysis': dict,        准确性/完整性/流畅性分析
            'user_text': str,        用户文本
            'ai_text': str,          模型文本
            'message': str,          状态信息
        }
    """
    null_result: Dict[str, Any] = {
        'score': None,
        'reason': '',
        'analysis': {},
        'user_text': '',
        'ai_text': '',
        'message': f'分类为{classification}，不进行回复质量评分',
    }

    # 仅"接管"时评分
    if classification != '接管':
        return null_result

    result: Dict[str, Any] = {
        'user_text': '',
        'ai_text': '',
        'score': None,
        'reason': '',
        'analysis': {},
        'message': '',
    }

    # 获取用户文本
    if user_chunks:
        result['user_text'] = ''.join(
            c.get('text', '') for c in user_chunks if isinstance(c, dict)
        )

    # 获取模型文本
    if ai_chunks:
        result['ai_text'] = ''.join(
            c.get('text', '') for c in ai_chunks if isinstance(c, dict)
        )

    # 检查 LLM 配置
    llm_config = get_llm_config()
    api_base = llm_config.get('api_base_url', '')
    api_key = llm_config.get('api_key', '')
    if not api_base or not api_key:
        result['message'] = 'LLM 评估未配置：请在 .env 设置 LLM_JUDGE_API_BASE 与 LLM_JUDGE_API_KEY'
        return result

    # 解析模型名
    model = ''
    if task_params:
        model = task_params.get('llm_model') or ''
    if not model:
        model = resolve_model(dimension='reply_quality')

    # 解析 LLM 参数
    max_tokens = int(task_params.get('max_tokens', LLM_DEFAULT_MAX_TOKENS) or LLM_DEFAULT_MAX_TOKENS) if task_params else LLM_DEFAULT_MAX_TOKENS
    temperature = float(task_params.get('temperature', LLM_DEFAULT_TEMPERATURE) or LLM_DEFAULT_TEMPERATURE) if task_params else LLM_DEFAULT_TEMPERATURE

    # 构建 prompt 并调用 LLM
    prompt = _build_reply_quality_prompt(result['user_text'], result['ai_text'])

    try:
        resp = call_llm(
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            file_paths=None,
            log_context={'dimension': 'reply_quality'},
        )
    except Exception as exc:
        logger.exception('[reply_quality] LLM 调用失败')
        result['message'] = f'LLM 调用失败: {exc}'
        return result

    # 解析返回
    parsed = parse_json(resp.get('content', ''))
    if not parsed:
        result['message'] = f'LLM 返回解析失败: {resp.get("content", "")[:200]}'
        return result

    result['score'] = parsed.get('score')
    result['reason'] = parsed.get('reason', '')
    result['analysis'] = parsed.get('analysis', {})
    result['message'] = 'OK'

    logger.info(
        f"[reply_quality] 轮评分: score={result['score']} reason={result['reason']!r}"
    )
    return result


# ── 兼容旧接口 ──
def evaluate_reply_quality(
    played_audios: str = '',
    ai_wav: str = '',
    user_text: str = '',
    ai_text: str = '',
    user_chunks: Optional[List[Dict[str, Any]]] = None,
    ai_chunks: Optional[List[Dict[str, Any]]] = None,
    model: str = '',
    max_tokens: int = 0,
    temperature: float = -1.0,
) -> Dict[str, Any]:
    """兼容旧调用入口

    旧接口不支持 classification 参数，默认为"接管"（即始终评分）。
    新代码应使用 evaluate_reply_quality_per_turn。
    """
    task_params = {}
    if model:
        task_params['llm_model'] = model
    if max_tokens > 0:
        task_params['max_tokens'] = max_tokens
    if temperature >= 0:
        task_params['temperature'] = temperature

    # 旧接口的文本回退逻辑
    if user_text:
        pass  # evaluate_reply_quality_per_turn 会从 chunks 拼接
    elif user_chunks:
        pass  # 同上
    elif played_audios:
        from app.services.calculators.xiaoyi_metrics.shared.llm_client import get_asr_text
        from app.services.calculators.xiaoyi_metrics.turn_taking.false_takeover import _resolve_played_audio_path
        _user_audio = _resolve_played_audio_path(played_audios)
        if _user_audio:
            user_text = get_asr_text(_user_audio)

    if not ai_text and not ai_chunks and ai_wav:
        from app.services.calculators.xiaoyi_metrics.shared.llm_client import get_asr_text
        ai_text = get_asr_text(ai_wav)

    # 如果有直接传入的文本，构造临时 chunks
    effective_user_chunks = user_chunks
    if not effective_user_chunks and user_text:
        effective_user_chunks = [{'text': user_text, 'timestamp': [0.0, 0.0]}]

    effective_ai_chunks = ai_chunks
    if not effective_ai_chunks and ai_text:
        effective_ai_chunks = [{'text': ai_text, 'timestamp': [0.0, 0.0]}]

    return evaluate_reply_quality_per_turn(
        user_chunks=effective_user_chunks,
        ai_chunks=effective_ai_chunks,
        classification='接管',  # 旧接口默认评分
        task_params=task_params or None,
    )


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='单轮模型回复质量评分')
    parser.add_argument('--played-audios', default='', help='用户侧音频路径')
    parser.add_argument('--ai-wav', default='', help='模型回复音频路径')
    parser.add_argument('--user-text', default='', help='用户侧 ASR 文本（可选，优先使用）')
    parser.add_argument('--ai-text', default='', help='模型侧 ASR 文本（可选，优先使用）')
    parser.add_argument('--model', default='', help='LLM 模型名（留空自动解析）')
    args = parser.parse_args()

    res = evaluate_reply_quality(
        played_audios=args.played_audios,
        ai_wav=args.ai_wav,
        user_text=args.user_text,
        ai_text=args.ai_text,
        model=args.model,
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))
