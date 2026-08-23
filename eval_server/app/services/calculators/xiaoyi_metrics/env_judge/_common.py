# -*- coding: utf-8 -*-
"""_common.py
拒识场景 / 打断场景 LLM 裁判共享工具模块

包含：
    - 常量（超时、重试、文件扩展名、行为标签）
    - 文件编码（音频 base64 / 视频 data URI）
    - 多模态 content 构建
    - LLM API 调用（支持 omni stream / audio 模型 / 普通文本模型）
    - 时间线构建（用户侧 ASR + 环境声事件窗）
    - JSON 解析与 evaluations 归一化
"""
import json
import os
import re
import time
import base64
import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# ─────────── 常量 ───────────
LLM_DEFAULT_TIMEOUT = 120
LLM_MAX_RETRIES = 3
LLM_RETRY_BASE_DELAY = 2  # 秒

_AUDIO_EXTS = {'.wav', '.mp3', '.flac', '.aac', '.ogg', '.opus', '.m4a'}
_VIDEO_EXTS = {
    '.mp4', '.avi', '.mkv', '.webm', '.mov', '.flv',
    '.wmv', '.m4v', '.ts', '.3gp',
}

# 行为分类的合法取值（五选一）
BEHAVIOR_LABELS = ['回应', '恢复', '询问', '无关回复', '沉默']


# ─────────── 文件编码 ───────────
def is_audio(file_path: str) -> bool:
    return os.path.splitext(file_path)[1].lower() in _AUDIO_EXTS


def encode_file_to_data(file_path: str) -> str:
    """将音频文件编码为纯 base64 字符串（不带 data URI 前缀）。

    用于 OpenAI input_audio 格式的 data 字段——该字段要求纯 base64，
    不能带 `data:;base64,` 前缀，否则部分代理/模型会静默忽略音频。
    """
    with open(file_path, 'rb') as f:
        return base64.b64encode(f.read()).decode()


def encode_video_to_data_uri(file_path: str) -> str:
    """将视频文件编码为带 MIME 的 base64 data URI（用于 image_url）。"""
    ext = os.path.splitext(file_path)[1].lower()
    mime_map = {
        '.mp4': 'video/mp4', '.avi': 'video/x-msvideo',
        '.mkv': 'video/x-matroska', '.webm': 'video/webm',
        '.mov': 'video/quicktime', '.flv': 'video/x-flv',
        '.wmv': 'video/x-ms-wmv', '.m4v': 'video/x-m4v',
        '.ts': 'video/mp2t', '.3gp': 'video/3gpp',
    }
    mime = mime_map.get(ext, 'application/octet-stream')
    with open(file_path, 'rb') as f:
        encoded = base64.b64encode(f.read()).decode()
    return f'data:{mime};base64,{encoded}'


def get_audio_format(file_path: str) -> str:
    """从文件扩展名获取音频格式名称"""
    ext = os.path.splitext(file_path)[1].lower()
    fmt_map = {'.wav': 'wav', '.mp3': 'mp3', '.flac': 'flac',
               '.aac': 'aac', '.ogg': 'ogg', '.opus': 'opus',
               '.m4a': 'm4a'}
    return fmt_map.get(ext, 'wav')


# ─────────── 多模态 content 构建 ───────────
def build_content(prompt: str, file_paths: Optional[List[str]] = None) -> list:
    """构建 user message content，自动区分音频/视频。音频在前、视频在后、文本最后。"""
    content: list = []
    audio_parts: List[str] = []
    video_parts: List[str] = []
    if file_paths:
        for fp in file_paths:
            if is_audio(fp):
                audio_parts.append(fp)
            else:
                video_parts.append(fp)

    for ap in audio_parts:
        b64_data = encode_file_to_data(ap)
        audio_fmt = get_audio_format(ap)
        content.append({
            'type': 'input_audio',
            'input_audio': {'data': b64_data, 'format': audio_fmt},
        })
    for vp in video_parts:
        data_uri = encode_video_to_data_uri(vp)
        content.append({
            'type': 'image_url',
            'image_url': {'url': data_uri},
        })
    content.append({'type': 'text', 'text': prompt})
    return content


# ─────────── LLM 调用 ───────────
def call_llm_api(model: str, prompt: str,
                 max_tokens: int = 4096,
                 temperature: float = 0.1,
                 file_paths: Optional[List[str]] = None) -> Dict[str, Any]:
    """调用 OpenAI 兼容的 LLM API（多模态：文本 + 音频/录屏）。

    音频文件使用 input_audio 格式，视频文件使用 image_url 格式。
    支持 stream 模式以兼容 Qwen omni 等模型。
    """
    from app.config import config

    llm_config = getattr(config, 'LLM_JUDGE', {})
    api_base = llm_config.get('api_base_url', '')
    api_key = llm_config.get('api_key', '')
    timeout = llm_config.get('timeout', LLM_DEFAULT_TIMEOUT)

    if not api_base or not api_key:
        raise ValueError(
            'LLM 评估未配置：请在 eval_server 设置 '
            'LLM_JUDGE_API_BASE 与 LLM_JUDGE_API_KEY'
        )

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }

    if file_paths:
        user_content = build_content(prompt, file_paths)
    else:
        user_content = [{'type': 'text', 'text': prompt}]

    # 判断模型类型：omni(需 stream) / 其他音频模型(如 gpt-audio，不支持 response_format) / 普通文本模型
    m_low = model.lower()
    is_omni = 'omni' in m_low
    is_audio = is_omni or ('audio' in m_low)

    payload: Dict[str, Any] = {
        'model': model,
        'messages': [
            {'role': 'user', 'content': user_content},
        ],
        'max_tokens': max_tokens,
        'temperature': temperature,
    }

    if is_omni:
        payload['stream'] = True
        payload['stream_options'] = {'include_usage': True}
        payload['timeout'] = 300
    elif not is_audio:
        payload['response_format'] = {'type': 'json_object'}

    url = f'{api_base.rstrip("/")}/chat/completions'
    max_retries = llm_config.get('max_retries', LLM_MAX_RETRIES)

    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            with httpx.Client(trust_env=False, timeout=timeout) as client:
                response = client.post(url, headers=headers, json=payload)

            response.raise_for_status()

            if is_omni:
                content_text = ''
                usage_data: Dict[str, Any] = {}
                for line in response.text.split('\n'):
                    line = line.strip()
                    if not line or not line.startswith('data: '):
                        continue
                    chunk_str = line[6:]
                    if chunk_str == '[DONE]':
                        break
                    try:
                        chunk = json.loads(chunk_str)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get('choices', [])
                    if choices:
                        delta = choices[0].get('delta', {})
                        content_text += delta.get('content', '')
                    if chunk.get('usage'):
                        usage_data = chunk['usage']
                data = {
                    'choices': [{'message': {'content': content_text}}],
                    'usage': usage_data,
                }
            else:
                data = response.json()
            break
        except httpx.HTTPStatusError as e:
            last_exc = e
            status_code = e.response.status_code
            if 500 <= status_code < 600:
                try:
                    err_body = e.response.text[:500]
                except Exception:
                    err_body = '<无法读取>'
                logger.warning(
                    f'LLM API 返回 {status_code}，响应体: {err_body}'
                )
            if status_code != 429 and not (500 <= status_code < 600):
                raise
            if attempt >= max_retries:
                logger.error(
                    f'LLM API 返回 {status_code}，'
                    f'已达最大重试次数 {max_retries}'
                )
                raise
            retry_after = e.response.headers.get('Retry-After')
            if retry_after:
                try:
                    delay = float(retry_after)
                except ValueError:
                    delay = LLM_RETRY_BASE_DELAY * (2 ** attempt)
            else:
                delay = LLM_RETRY_BASE_DELAY * (2 ** attempt)
            logger.warning(
                f'LLM API 返回 {status_code}，{delay:.1f}s 后重试 '
                f'(attempt {attempt + 1}/{max_retries})'
            )
            time.sleep(delay)
        except httpx.RequestError as e:
            last_exc = e
            if attempt >= max_retries:
                logger.error(
                    f'LLM API 请求失败，已达最大重试次数 {max_retries}'
                )
                raise
            delay = LLM_RETRY_BASE_DELAY * (2 ** attempt)
            logger.warning(
                f'LLM API 请求异常: {e}，{delay:.1f}s 后重试 '
                f'(attempt {attempt + 1}/{max_retries})'
            )
            time.sleep(delay)
    else:
        raise last_exc

    return {
        'content': data['choices'][0]['message']['content'],
        'tokens_used': data.get('usage', {}).get('total_tokens', 0),
        'input_token': data.get('usage', {}).get('prompt_tokens', 0),
        'output_token': data.get('usage', {}).get('completion_tokens', 0),
    }


# ─────────── 时间线构建 ───────────
def env_events_from_ms(start_ms, end_ms, pcm_first_ms=None,
                       label: str = '环境声') -> Optional[List[Dict[str, Any]]]:
    """把环境声播放的绝对毫秒 [start_ms, end_ms] 换算到模型音频相对秒。

    相对秒 = (abs_ms - pcm_first_ms) / 1000。
    pcm_first_ms 缺省时按 0 处理。
    """
    if start_ms is None or end_ms is None:
        return None
    try:
        base = float(pcm_first_ms) if pcm_first_ms is not None else 0.0
        s = (float(start_ms) - base) / 1000.0
        e = (float(end_ms) - base) / 1000.0
    except (TypeError, ValueError):
        return None
    return [{'start_s': s, 'end_s': e, 'label': label}]


def build_timeline_text(user_chunks: Optional[List[Dict[str, Any]]] = None,
                        env_events: Optional[List[Dict[str, Any]]] = None) -> str:
    """构建文本时间线：用户侧 ASR 转写 + 环境声事件窗。

    用户侧走小 ASR（内容错了不伤模型回复判定），环境声不可 ASR，只给时间窗。
    模型回复本身不在此时间线里——它以随附的 ai_wav 音频为准，交给裁判模型直接听。
    """
    parts: List[str] = []

    if user_chunks:
        lines = []
        for c in user_chunks:
            if not isinstance(c, dict):
                continue
            t = c.get('timestamp') or [None, None]
            text = c.get('text', '')
            if t and t[0] is not None and t[1] is not None:
                try:
                    lines.append(f'  [{float(t[0]):.2f}-{float(t[1]):.2f}] 用户: {text}')
                except (TypeError, ValueError):
                    continue
        if lines:
            parts.append('【用户语音时间线】（小 ASR 转写，可能存在误差）\n' + '\n'.join(lines))

    if env_events:
        lines = []
        for ev in env_events:
            if not isinstance(ev, dict):
                continue
            s = ev.get('start_s')
            e = ev.get('end_s')
            label = ev.get('label', '环境声')
            if s is None or e is None:
                continue
            try:
                lines.append(
                    f'  [{float(s):.2f}-{float(e):.2f}] {label}'
                    f'（环境声，不可ASR；模型在此窗内应保持沉默/不应被触发）'
                )
            except (TypeError, ValueError):
                continue
        if lines:
            parts.append('【环境声事件】\n' + '\n'.join(lines))

    return '\n\n'.join(parts)


def extract_video_paths(kwargs: dict) -> List[str]:
    """从 kwargs 中提取存在的录屏/音频文件路径（legacy：录屏模式下的额外文件）"""
    paths = []
    for value in kwargs.values():
        if not isinstance(value, str) or not value:
            continue
        ext = os.path.splitext(value)[1].lower()
        if ext in (_VIDEO_EXTS | _AUDIO_EXTS) and os.path.isfile(value):
            paths.append(value)
    return paths


# ─────────── JSON 解析 ───────────
def parse_json(content: str) -> Optional[dict]:
    """解析 LLM 输出为 dict。先 json.loads，失败用正则兜底。"""
    if not content:
        return None
    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError):
        pass
    m = re.search(r'\{.*\}', content, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except (json.JSONDecodeError, TypeError):
            return None
    return None


def parse_evaluations(parsed: dict) -> List[Dict[str, Any]]:
    """从 parsed 中提取 evaluations 列表，归一化 behavior 标签。

    支持三种格式:
    - 多场景: {"evaluations": [{scene, behavior, reason}, ...]}
    - 单场景(含 scene): {"scene": "...", "behavior": "...", "reason": "..."}
    - 单条(无 scene): {"behavior": "...", "reason": "..."}
    """
    if 'behavior' in parsed:
        evaluations = [parsed]
    else:
        evaluations = parsed.get('evaluations', [])
        if not isinstance(evaluations, list):
            evaluations = []

    for item in evaluations:
        if not isinstance(item, dict):
            continue
        behavior = str(item.get('behavior', '')).strip()
        if behavior and behavior not in BEHAVIOR_LABELS and behavior != '无法判断':
            matched = next(
                (label for label in BEHAVIOR_LABELS if label in behavior),
                None,
            )
            if matched:
                item['behavior'] = matched
    return evaluations


def get_asr_chunks(user_wav: str) -> Optional[List[Dict[str, Any]]]:
    """调用 ASR 获取用户侧 chunks（用于构建时间线上下文）"""
    try:
        from app.services.calculators.xiaoyi_metrics.turn_taking import _get_asr_chunks
        return _get_asr_chunks(user_wav)
    except Exception as e:
        logger.warning(f'[env_judge] 用户侧 ASR 失败，时间线将缺用户段: {e}')
        return None
