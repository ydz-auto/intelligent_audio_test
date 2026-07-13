# -*- coding: utf-8 -*-
"""LLM Judge calculator for voice_llm evaluation.

Uses a large language model (e.g., GPT-4) to semantically score dialog outputs,
evaluating accuracy, fluency, relevance, and other configurable criteria.

Supports multimodal evaluation: when audio file paths are provided in the
parameters, the audio is encoded as base64 data URI and sent to the LLM API
as image_url content (OpenAI multimodal format).
"""

import json
import re
import os
import base64
import requests
from typing import Optional


LLM_DEFAULT_TIMEOUT = 120

# 音频文件扩展名集合
_AUDIO_EXTS = {'.wav', '.mp3', '.flac', '.ogg', '.m4a', '.aac', '.pcm', '.opus', '.amr', '.wma'}


def evaluate_with_llm(
    hypothesis: str,
    reference: str,
    model: str = 'gpt-4',
    prompt: str = '',
    max_tokens: int = 1024,
    temperature: float = 0.1,
    scoring_criteria: Optional[list] = None,
    source_lang: str = 'zh',
    target_lang: str = 'en',
    **kwargs
) -> dict:
    """
    Use LLM to score the hypothesis against a reference.

    Args:
        hypothesis: System output text to evaluate
        reference: Ground truth reference text
        model: LLM model name
        prompt: Custom evaluation prompt (can contain {hypothesis} and {reference} placeholders)
        max_tokens: Max output tokens
        temperature: Sampling temperature
        scoring_criteria: List of scoring criterion names
        source_lang: Source language code
        target_lang: Target language code
        **kwargs: Additional parameters, may include audio file paths
                  (e.g. record_file, audio_path, etc.)

    Returns:
        {
            "llm_judge_score": 4.2,
            "criteria_scores": {"accuracy": 4.5, "fluency": 4.0, "relevance": 4.0},
            "reasoning": "...",
            "model": "gpt-4",
            "tokens_used": 256,
            "source_lang": "zh",
            "target_lang": "en"
        }
    """
    # 从 kwargs 中提取音频文件路径
    audio_paths = _extract_audio_paths(kwargs)

    prompt_text = _build_evaluation_prompt(
        hypothesis=hypothesis,
        reference=reference,
        custom_prompt=prompt,
        scoring_criteria=scoring_criteria,
        source_lang=source_lang,
        target_lang=target_lang,
    )

    response = _call_llm_api(
        model=model,
        prompt=prompt_text,
        max_tokens=max_tokens,
        temperature=temperature,
        audio_paths=audio_paths,
    )

    result = _parse_llm_response(response)

    result['model'] = model
    result['source_lang'] = source_lang
    result['target_lang'] = target_lang

    return result


def _extract_audio_paths(kwargs):
    """从 kwargs 中提取音频文件路径（文件存在且扩展名为音频类型）"""
    audio_paths = []
    for key, value in kwargs.items():
        if not isinstance(value, str) or not value:
            continue
        ext = os.path.splitext(value)[1].lower()
        if ext in _AUDIO_EXTS and os.path.isfile(value):
            audio_paths.append(value)
    return audio_paths


def _build_evaluation_prompt(hypothesis, reference, custom_prompt,
                              scoring_criteria, source_lang, target_lang):
    """Build the LLM evaluation prompt."""
    if custom_prompt:
        try:
            return custom_prompt.format(
                hypothesis=hypothesis,
                reference=reference,
            )
        except (KeyError, IndexError):
            # 模板中可能没有占位符，直接使用
            return custom_prompt

    criteria_text = ''
    if scoring_criteria:
        for idx, criterion in enumerate(scoring_criteria, 1):
            criteria_text += f'{idx}. {criterion}\n'
    else:
        criteria_text = (
            '1. Accuracy: How accurately does the hypothesis match the reference?\n'
            '2. Fluency: How fluent and natural is the hypothesis?\n'
            '3. Relevance: How relevant is the hypothesis to the context?\n'
        )

    return f"""You are a professional translation/ASR quality evaluator.

Reference (ground truth):
{reference}

Hypothesis (system output):
{hypothesis}

Please evaluate the hypothesis on a scale of 1-5 for each criterion:
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


def _encode_audio_to_data_uri(file_path):
    """将音频文件编码为 base64 data URI"""
    ext = os.path.splitext(file_path)[1].lower()
    mime_map = {
        '.wav': 'audio/wav', '.mp3': 'audio/mpeg',
        '.flac': 'audio/flac', '.ogg': 'audio/ogg',
        '.m4a': 'audio/mp4', '.aac': 'audio/aac',
        '.pcm': 'audio/pcm', '.opus': 'audio/opus',
        '.amr': 'audio/amr', '.wma': 'audio/x-ms-wma',
    }
    mime = mime_map.get(ext, 'application/octet-stream')
    with open(file_path, 'rb') as f:
        encoded = base64.b64encode(f.read()).decode()
    return f'data:{mime};base64,{encoded}'


def _call_llm_api(model, prompt, max_tokens, temperature, audio_paths=None):
    """Call the LLM API (OpenAI-compatible format).

    当 audio_paths 非空时，构建多模态消息（text + audio）。
    """
    from ..config import config

    llm_config = getattr(config, 'LLM_JUDGE', {})
    api_base = llm_config.get('api_base_url', '')
    api_key = llm_config.get('api_key', '')
    timeout = llm_config.get('timeout', LLM_DEFAULT_TIMEOUT)

    if not api_base or not api_key:
        raise ValueError('LLM Judge API not configured: set LLM_JUDGE_API_BASE and LLM_JUDGE_API_KEY')

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }

    # 构建 user message content：纯文本或多模态
    if audio_paths:
        # 多模态：文本 + 音频 data URI
        user_content = [{'type': 'text', 'text': prompt}]
        for audio_path in audio_paths:
            data_uri = _encode_audio_to_data_uri(audio_path)
            user_content.append({
                'type': 'image_url',
                'image_url': {'url': data_uri},
            })
    else:
        user_content = prompt

    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': 'You are a precise evaluator.'},
            {'role': 'user', 'content': user_content},
        ],
        'max_tokens': max_tokens,
        'temperature': temperature,
        'response_format': {'type': 'json_object'},
    }

    response = requests.post(
        f'{api_base.rstrip("/")}/chat/completions',
        headers=headers,
        json=payload,
        timeout=timeout,
    )

    response.raise_for_status()
    data = response.json()

    return {
        'content': data['choices'][0]['message']['content'],
        'tokens_used': data.get('usage', {}).get('total_tokens', 0),
    }


def _parse_llm_response(response):
    """Parse the LLM scoring response."""
    content = response['content']

    try:
        result = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            try:
                result = json.loads(json_match.group())
            except (json.JSONDecodeError, TypeError):
                return {
                    'llm_judge_score': 0,
                    'criteria_scores': {},
                    'reasoning': f'Failed to parse LLM response: {content[:200]}',
                    'tokens_used': response.get('tokens_used', 0),
                }
        else:
            return {
                'llm_judge_score': 0,
                'criteria_scores': {},
                'reasoning': f'Failed to parse LLM response: {content[:200]}',
                'tokens_used': response.get('tokens_used', 0),
            }

    scores = result.get('scores', {})
    overall = result.get('overall_score')

    if overall is None and scores:
        overall = sum(scores.values()) / len(scores)

    return {
        'llm_judge_score': round(overall or 0, 2),
        'criteria_scores': {k: round(v, 2) for k, v in scores.items()},
        'reasoning': result.get('reasoning', ''),
        'tokens_used': response.get('tokens_used', 0),
    }
