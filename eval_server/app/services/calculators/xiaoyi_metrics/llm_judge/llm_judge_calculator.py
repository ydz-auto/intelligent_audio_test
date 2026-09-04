# -*- coding: utf-8 -*-
"""LLM Judge calculator for voice_llm evaluation.

Uses a large language model (e.g., GPT-4) to semantically score dialog outputs,
evaluating accuracy, fluency, relevance, and other configurable criteria.

Supports multimodal evaluation: when audio file paths are provided in the
parameters, the audio is encoded as base64 data URI and sent to the LLM API
as image_url content (OpenAI multimodal format).
"""

import os
import logging
from typing import Optional

from app.services.calculators.xiaoyi_metrics.shared.llm_client import (
    call_llm,
    parse_json,
    is_audio,
    extract_video_paths,
)
from app.services.calculators.xiaoyi_metrics.shared.constants import (
    LLM_DEFAULT_MAX_TOKENS,
    LLM_DEFAULT_TEMPERATURE,
)

logger = logging.getLogger(__name__)


def evaluate_with_llm(
        answer: str = '',
        correct_answer: str = '',
        question: str = '',
        query: str = '',
        record_file: str = '',
        rounds: Optional[list] = None,
        model: str = 'deepseek-r1',
        prompt: str = '',
        max_tokens: int = LLM_DEFAULT_MAX_TOKENS,
        temperature: float = LLM_DEFAULT_TEMPERATURE,
        scoring_criteria: Optional[list] = None,
        **kwargs
) -> dict:
    """Use LLM to score device answer against reference.

    字段名与 param_mappings 的 target_param 一致：
    - answer: 设备回答
    - correct_answer: 参考答案
    - question: 设备识别的问题
    - query: 参考问题
    - record_file: 音频文件路径

    Args:
        rounds: 多轮数据 [{answer, correct_answer, ...}, ...]，有 rounds 时逐轮列给 LLM
    """
    # 从 kwargs 中提取音频/视频文件路径
    filePaths = extract_video_paths(kwargs)
    if record_file and os.path.isfile(record_file):
        filePaths.append(record_file)

    if rounds:
        # 多轮：逐轮列出，不拼接
        prompt_text = _build_rounds_prompt(
            rounds=rounds,
            custom_prompt=prompt,
            scoring_criteria=scoring_criteria,
        )
    else:
        prompt_text = _build_evaluation_prompt(
            answer=answer,
            correct_answer=correct_answer,
            question=question,
            query=query,
            custom_prompt=prompt,
            scoring_criteria=scoring_criteria,
        )

    response = call_llm(
        model=model,
        prompt=prompt_text,
        max_tokens=max_tokens,
        temperature=temperature,
        file_paths=filePaths or None,
    )

    result = _build_result(response, model)

    return result


def _build_result(response, model):
    """从 call_llm 返回构建结果 dict"""
    parsed = parse_json(response.get('content', ''))
    if parsed:
        score = parsed.get('score', '')
        reason = parsed.get('reason', '')
    else:
        score = ''
        reason = response.get('content', '')

    return {
        'llm_judge_score': score,
        'reasoning': reason,
        'tokens_used': response.get('tokens_used', 0),
        'input_token': response.get('input_token', 0),
        'output_token': response.get('output_token', 0),
        'model': model,
    }


def _build_rounds_prompt(rounds, custom_prompt, scoring_criteria):
    """构建多轮评估 prompt（逐轮列出，不拼接）

    rounds 元素的字段名与 param_mappings 的 target_param 一致：
    answer / correct_answer / question / query / record_file
    """
    dialog_text = ''
    for idx, rd in enumerate(rounds, 1):
        answer = rd.get('answer', '')
        correct_answer = rd.get('correct_answer', '')
        question = rd.get('question', '')
        query = rd.get('query', '')
        dialog_text += (
            f'Round {idx}:\n'
            f'  Reference (correct_answer): {correct_answer}\n'
            f'  Hypothesis (answer): {answer}\n'
            f'  Question: {question}\n'
            f'  Query: {query}\n\n'
        )

    if custom_prompt:
        try:
            return custom_prompt.format(dialog=dialog_text)
        except (KeyError, IndexError):
            return custom_prompt

    criteria_text = ''
    if scoring_criteria:
        for idx, criterion in enumerate(scoring_criteria, 1):
            criteria_text += f'{idx}. {criterion}\n'
    else:
        criteria_text = (
            '1. Accuracy: How accurately does the answer match the correct_answer?\n'
            '2. Fluency: How fluent and natural is the answer?\n'
            '3. Relevance: How relevant is the answer to the question/query?\n'
        )

    return f"""你是一个严格的语言逻辑专家，你需要逐轮分析多轮对话中【参考问题】、【参考答案】与【助手回答】三者之间的逻辑是否正确，给出整体评分和打分理由。

多轮对话内容：
{dialog_text}

请按照【评价规则】进行打分：
{criteria_text}

输出结果严格按照如下json形式，包含两个参数（score、reason）：
{{"score":"1-5的整数评分","reason":"打分理由"}}"""


def _extract_audio_paths(kwargs):
    """从 kwargs 中提取音频文件路径（文件存在且扩展名为音频类型）"""
    audio_paths = []
    for key, value in kwargs.items():
        if not isinstance(value, str) or not value:
            continue
        if is_audio(value) and os.path.isfile(value):
            audio_paths.append(value)
    return audio_paths


def _build_evaluation_prompt(answer, correct_answer, question, query,
                             custom_prompt, scoring_criteria):
    """Build the LLM evaluation prompt.

    字段名与 param_mappings 的 target_param 一致：
    answer / correct_answer / question / query
    """
    # 优先使用调用方传入的 custom_prompt，其次从配置文件读取
    if not custom_prompt:
        from app.services.calculators.xiaoyi_metrics.shared.llm_client import get_llm_config
        custom_prompt = get_llm_config().get('prompt_template', '')

    if custom_prompt:
        try:
            return custom_prompt.format(
                answer=answer,
                correct_answer=correct_answer,
                question=question,
                query=query,
            )
        except (KeyError, IndexError):
            return custom_prompt

    criteria_text = ''
    if scoring_criteria:
        for idx, criterion in enumerate(scoring_criteria, 1):
            criteria_text += f'{idx}. {criterion}\n'
    else:
        criteria_text = (
            '1. Accuracy: How accurately does the answer match the correct_answer?\n'
            '2. Fluency: How fluent and natural is the answer?\n'
            '3. Relevance: How relevant is the answer to the question/query?\n'
        )

    return f"""You are a professional translation/ASR quality evaluator.

Reference (correct_answer):
{correct_answer}

Hypothesis (answer):
{answer}

Question: {question}
Query: {query}

Please evaluate the answer on a scale of 1-5 for each criterion:
{criteria_text}

Respond in the following JSON format:
{{
    "scores": {{
        "criterion_name": score
    }},
    "overall_score": average_score,
    "reasoning": "brief explanation"
}}

Only respond with the JSON, no additional text."""
