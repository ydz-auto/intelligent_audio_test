# -*- coding: utf-8 -*-
"""env_judge.py
语音对话能力 — 录屏文件 LLM 裁判

参考 llm_judge_calculator.py 的请求格式，传入录屏文件（视频），
由裁判模型对语音大模型的行为进行评判。

支持两种 task_type:
    1. 拒识与环境理解 (env_judge)
       场景: 旁人交谈静默 / 环境噪声 / 反馈词 / 生理声 / 环境事件回溯
    2. 打断能力 (interruption_judge)
       场景: 插话打断与重新响应 / 停止指令响应 / 多轮打断后恢复原话题

行为类别（五选一）:
    回应 / 恢复 / 询问 / 无关回复 / 沉默

输出: 严格 JSON，每场景一个 {scene, behavior, reason}
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

LLM_DEFAULT_TIMEOUT = 120
LLM_MAX_RETRIES = 3
LLM_RETRY_BASE_DELAY = 2  # 秒

# 录屏/视频文件扩展名集合
_VIDEO_EXTS = {
    '.mp4', '.avi', '.mkv', '.webm', '.mov', '.flv',
    '.wmv', '.m4v', '.ts', '.3gp',
}

# 行为分类的合法取值（与 prompt 五类一致，沿用 interruption_llm.py 的标签）
_BEHAVIOR_LABELS = ['回应', '恢复', '询问', '无关回复', '沉默']

# ─────────── 场景定义 ───────────
_ENV_SOUND_SCENES = {
    '旁人交谈': {
        'name': '场景-旁人交谈静默',
        'definition': '目标用户正在与旁边的人交谈（非与模型对话），模型应保持静默，不应插话、不应回应。',
        'expect': '沉默',
    },
    '环境噪声': {
        'name': '场景-环境噪声不触发',
        'definition': '录屏中出现环境噪声（如关门声、交通噪声、音乐声等非语音噪声），模型不应被噪声触发而产生回复。',
        'expect': '沉默',
    },
    '反馈词': {
        'name': '场景-反馈词不误触发',
        'definition': '用户在交互过程中发出"嗯""啊""好的""对"等短反馈词，这些词不具备发起新请求的意图，模型不应将其视为有效指令而接管对话。',
        'expect': '沉默',
    },
    '生理声': {
        'name': '场景-生理声不触发',
        'definition': '用户出现咳嗽、喷嚏、笑声等非语言意图的生理性声音，模型不应因此触发回复。',
        'expect': '沉默',
    },
    '环境回溯': {
        'name': '场景-环境事件被动记录与回溯',
        'definition': '在交互过程中，背景出现可识别的环境事件（如地铁广播、公交报站、闹钟等），模型不主动回应该环境事件，但应能持续记录。当用户随后主动询问该环境事件相关内容时（如"刚才广播说了什么"），模型应能识别并基于已记录的环境信息进行回复。',
        'expect': '在环境事件出现时保持沉默，在用户主动询问时给出回应',
    },
}

_INTERRUPTION_SCENES = {
    '插话打断': {
        'name': '场景-插话打断与重新响应',
        'definition': '模型正在输出回复时，用户插话打断了模型（用户发起新的提问或请求）。模型应在感知到用户插话后立即停止当前输出，并根据用户插话内容重新响应。',
        'expect': '模型停止当前输出，并针对用户插话内容给出回应（回应）',
    },
    '停止指令': {
        'name': '场景-停止指令响应',
        'definition': '用户对模型发出明确的停止指令，如"停""闭嘴""不用了""停下来""好了好了"等。模型应在收到停止指令后立即停止当前输出，不应继续说完剩余内容或产生无关回复。',
        'expect': '模型立即停止输出（沉默），或简短确认后停止（回应）',
    },
    '恢复原话题': {
        'name': '场景-多轮对话打断后恢复原话题',
        'definition': '在多轮对话中，用户打断并切换了话题（如询问天气、时间等），模型完成打断话题的回复后，用户要求回到原始话题（如"我们继续聊刚才说的""回到之前的话题"）。模型应能识别用户意图，自然地恢复到打断前的原始话题并继续相关内容。',
        'expect': '模型成功恢复到原始话题并给出相关内容（恢复），或直接回应了回到原话题的请求（回应）',
    },
}

_BEHAVIOR_DEFS = {
    'env_judge': """- 回应：模型针对用户的真实意图或主动询问给出了直接、相关的回复。包括场景5中用户询问环境事件后模型正确识别并作答的情况。
- 恢复：模型未直接回应当前输入，但其回复内容已自然回到此前的话题或交互主线，体现出对话恢复能力。
- 询问：模型对用户的意图进行追问、澄清或确认（如"您是想了解……吗？"），而非直接给出答案。
- 无关回复：模型产生了回复，但内容与当前用户意图、对话上下文或场景要求无关。包括本应沉默却给出了回复。
- 沉默：模型未产生任何有效回复（无声、空回复、兜底拒答等）。""",
    'interruption_judge': """- 回应：模型针对用户的插话内容、停止指令或回到原话题的请求给出了直接、相关的回复。包括停止后简短确认（"好的"）、针对插话内容作答、直接回应回到原话题的请求。
- 恢复：模型未明确回应当前输入，但其回复内容已自然回到打断前的话题或交互主线，体现出对话恢复能力。典型用于用户要求回到原话题后，模型直接续上了原话题内容。
- 询问：模型对用户的意图进行追问、澄清或确认（如"您是想继续之前的话题吗？"），而非直接给出答案或执行指令。
- 无关回复：模型产生了回复，但内容与当前用户意图、对话上下文或场景要求无关。包括：插话后未停止而继续原输出、收到停止指令后仍继续输出、打断后话题恢复失败且回复内容与原话题无关。
- 沉默：模型未产生任何有效回复（无声、空回复、兜底拒答等）。""",
}

_TASK_TYPE_SCENES = {
    'env_judge': _ENV_SOUND_SCENES,
    '拒识与环境理解': _ENV_SOUND_SCENES,
    'interruption_judge': _INTERRUPTION_SCENES,
    '打断能力': _INTERRUPTION_SCENES,
}

_TASK_TYPE_BEHAVIORS = {
    'env_judge': _BEHAVIOR_DEFS['env_judge'],
    '拒识与环境理解': _BEHAVIOR_DEFS['env_judge'],
    'interruption_judge': _BEHAVIOR_DEFS['interruption_judge'],
    '打断能力': _BEHAVIOR_DEFS['interruption_judge'],
}


def _build_prompt(task_type: str, env_type: str = '') -> str:
    """根据 task_type 和 env_type 动态构建 prompt。

    - env_type 为空：包含所有场景，输出 evaluations 数组
    - env_type 指定：只包含对应场景，输出单个 {scene, behavior, reason}
    """
    scenes = _TASK_TYPE_SCENES.get(task_type, {})
    behaviors = _TASK_TYPE_BEHAVIORS.get(task_type, '')

    if not scenes:
        raise ValueError(f'不支持的 task_type: {task_type}')

    if env_type and env_type in scenes:
        # ── 单场景 prompt ──
        sc = scenes[env_type]
        return f"""你是语音对话能力的裁判专家。你将收到一段音频/录屏文件，该文件记录了用户与语音大模型的交互过程。本次测试场景为【{env_type}】，请仅针对该场景评判模型的行为。

═══════════════════════════════════════
【场景定义】
═══════════════════════════════════════

{sc['name']}
  {sc['definition']}
  期望行为：{sc['expect']}。

═══════════════════════════════════════
【行为类别定义】（五选一，仅可选其一）
═══════════════════════════════════════

{behaviors}

═══════════════════════════════════════
【输出格式】
═══════════════════════════════════════

输出严格 JSON，不要输出 JSON 以外的任何内容：

{{
  "scene": "{sc['name']}",
  "behavior": "",
  "reason": ""
}}

其中：
- behavior 必须是【回应】【恢复】【询问】【无关回复】【沉默】五个类别之一
- reason 为简短判定理由，需说明你从音频中观察到了什么、模型做了什么、为何归类为此行为
- 若该场景在音频中未出现或无法判断，behavior 填"无法判断"并在 reason 中说明原因"""

    else:
        # ── 全场景 prompt ──
        scene_blocks = []
        for i, (key, sc) in enumerate(scenes.items(), 1):
            scene_blocks.append(
                f"场景{i} — {sc['name'].replace('场景-', '')}\n"
                f"  {sc['definition']}\n"
                f"  期望行为：{sc['expect']}。"
            )
        scenes_text = '\n\n'.join(scene_blocks)

        eval_items = []
        for i, (key, sc) in enumerate(scenes.items(), 1):
            eval_items.append(
                f'    {{\n'
                f'      "scene": "场景{i}-{sc["name"].replace("场景-", "")}",\n'
                f'      "behavior": "",\n'
                f'      "reason": ""\n'
                f'    }}'
            )
        eval_text = ',\n'.join(eval_items)

        return f"""你是语音对话能力的裁判专家。你将收到一段音频/录屏文件，该文件记录了用户与语音大模型的完整交互过程。录屏中包含多个预设场景，用于考察模型在不同情境下的行为能力。

请逐段聆听音频/观看录屏，按照以下【场景定义】判断模型在每个场景中的行为，并给出唯一的【行为类别】和判定依据。

═══════════════════════════════════════
【场景定义】
═══════════════════════════════════════

{scenes_text}

═══════════════════════════════════════
【行为类别定义】（五选一，仅可选其一）
═══════════════════════════════════════

{behaviors}

═══════════════════════════════════════
【输出格式】
═══════════════════════════════════════

请对音频中识别到的每个场景分别评判，输出严格 JSON，不要输出 JSON 以外的任何内容：

{{
  "evaluations": [
{eval_text}
  ]
}}

其中：
- behavior 必须是【回应】【恢复】【询问】【无关回复】【沉默】五个类别之一
- reason 为简短判定理由，需说明你从音频中观察到了什么、模型做了什么、为何归类为此行为
- 若音频中某个场景未出现或无法判断，behavior 填"无法判断"并在 reason 中说明原因"""


# ─────────── 文件编码 ───────────
_AUDIO_EXTS = {'.wav', '.mp3', '.flac', '.aac', '.ogg', '.opus', '.m4a'}
_VIDEO_EXTS = {
    '.mp4', '.avi', '.mkv', '.webm', '.mov', '.flv',
    '.wmv', '.m4v', '.ts', '.3gp',
}


def _is_audio(file_path: str) -> bool:
    return os.path.splitext(file_path)[1].lower() in _AUDIO_EXTS


def _encode_file_to_data(file_path: str) -> str:
    """将文件编码为 base64 data 字符串（不带 MIME 前缀）。

    用于 input_audio 格式: data:;base64,xxxx
    """
    with open(file_path, 'rb') as f:
        encoded = base64.b64encode(f.read()).decode()
    return f'data:;base64,{encoded}'


def _encode_video_to_data_uri(file_path: str) -> str:
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


def _get_audio_format(file_path: str) -> str:
    """从文件扩展名获取音频格式名称"""
    ext = os.path.splitext(file_path)[1].lower()
    fmt_map = {'.wav': 'wav', '.mp3': 'mp3', '.flac': 'flac',
               '.aac': 'aac', '.ogg': 'ogg', '.opus': 'opus',
               '.m4a': 'm4a'}
    return fmt_map.get(ext, 'wav')


def _extract_video_paths(kwargs: dict) -> List[str]:
    """从 kwargs 中提取存在的录屏/音频文件路径"""
    paths = []
    for value in kwargs.values():
        if not isinstance(value, str) or not value:
            continue
        ext = os.path.splitext(value)[1].lower()
        if ext in (_VIDEO_EXTS | _AUDIO_EXTS) and os.path.isfile(value):
            paths.append(value)
    return paths


# ─────────── LLM 调用 ───────────
def _build_content(prompt: str, file_paths: Optional[List[str]] = None) -> list:
    """构建 user message content，自动区分音频/视频。"""
    content = []
    # 音频文件优先放在前面（参照用户示例顺序）
    audio_parts = []
    video_parts = []
    if file_paths:
        for fp in file_paths:
            if _is_audio(fp):
                audio_parts.append(fp)
            else:
                video_parts.append(fp)

    for ap in audio_parts:
        b64_data = _encode_file_to_data(ap)
        audio_fmt = _get_audio_format(ap)
        content.append({
            'type': 'input_audio',
            'input_audio': {'data': b64_data, 'format': audio_fmt},
        })
    for vp in video_parts:
        data_uri = _encode_video_to_data_uri(vp)
        content.append({
            'type': 'image_url',
            'image_url': {'url': data_uri},
        })
    content.append({'type': 'text', 'text': prompt})
    return content


def _call_llm_api(model: str, prompt: str,
                  max_tokens: int = 4096,
                  temperature: float = 0.1,
                  video_paths: Optional[List[str]] = None) -> Dict[str, Any]:
    """调用 OpenAI 兼容的 LLM API（多模态：文本 + 音频/录屏）。

    音频文件使用 input_audio 格式（data:;base64,...），
    视频文件使用 image_url 格式（data:{mime};base64,...）。
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

    # 构建 user message content
    if video_paths:
        user_content = _build_content(prompt, video_paths)
    else:
        user_content = [{'type': 'text', 'text': prompt}]

    # 判断是否为 omni 模型（需要 stream + 无 response_format）
    is_omni = 'omni' in model.lower()

    payload: Dict[str, Any] = {
        'model': model,
        'messages': [
            {'role': 'user', 'content': user_content},
        ],
        'max_tokens': max_tokens,
        'temperature': temperature,
    }

    if is_omni:
        # Qwen omni 系列需要 stream 模式
        payload['stream'] = True
        payload['stream_options'] = {'include_usage': True}
        payload['timeout'] = 300
    else:
        # 非 omni 模型可使用 response_format
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
                # 流式响应：逐行读取 SSE
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
            # 记录 500 错误的响应体，方便排查
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


# ─────────── 响应解析 ───────────
def _parse_json(content: str) -> Optional[dict]:
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


def _parse_evaluations(parsed: dict) -> List[Dict[str, Any]]:
    """从 parsed 中提取 evaluations 列表，归一化 behavior 标签。

    支持两种格式:
    - 多场景: {"evaluations": [{scene, behavior, reason}, ...]}
    - 单场景: {"scene": "...", "behavior": "...", "reason": "..."}
    """
    # 单场景格式
    if 'behavior' in parsed and 'scene' in parsed:
        evaluations = [parsed]
    else:
        evaluations = parsed.get('evaluations', [])
        if not isinstance(evaluations, list):
            evaluations = []

    for item in evaluations:
        if not isinstance(item, dict):
            continue
        behavior = str(item.get('behavior', '')).strip()
        if behavior and behavior not in _BEHAVIOR_LABELS and behavior != '无法判断':
            # 归一化：模糊匹配回合法标签
            matched = next(
                (label for label in _BEHAVIOR_LABELS if label in behavior),
                None,
            )
            if matched:
                item['behavior'] = matched
    return evaluations


# ─────────── 主入口 ───────────
def evaluate_env_judge(
    video_path: str,
    task_type: str = 'env_judge',
    env_type: str = '',
    model: str = '',
    max_tokens: int = 4096,
    temperature: float = 0.1,
    **kwargs,
) -> Dict[str, Any]:
    """语音对话能力 — 录屏文件 LLM 裁判主入口

    根据 task_type 选择对应 prompt 对录屏进行评判。

    Args:
        video_path: 录屏/音频文件路径
        task_type: 测试类型，支持：
            - 'env_judge' 或 '拒识与环境理解' → 拒识环境音 prompt
            - 'interruption_judge' 或 '打断能力' → 打断能力 prompt
        env_type: 环境子场景类型（如 '环境回溯' '旁人交谈' '环境噪声' 等），
                  用于标识本次音频实际测试的具体场景
        model: LLM 模型名，缺省读 config.LLM_JUDGE.default_model
        max_tokens: 最大输出 token 数
        temperature: 采样温度，评判场景建议低温 0.1
        **kwargs: 额外录屏文件路径（多个录屏时传入）

    Returns:
        dict: {
            'enabled': True,
            'model': str,
            'task_type': str,
            'env_type': str,
            'video_path': str,
            'evaluations': [{scene, behavior, reason}, ...],
            'tokens_used': int,
            'input_token': int,
            'output_token': int,
            'message': str,
        }
    """
    from app.config import config

    # 根据 task_type + env_type 动态构建 prompt
    prompt = _build_prompt(task_type, env_type)

    llm_config = getattr(config, 'LLM_JUDGE', {})
    if not model:
        model = llm_config.get('default_model', 'gpt-4o')

    # 收集录屏文件路径
    video_paths = [video_path] if video_path and os.path.isfile(video_path) else []
    extra_paths = _extract_video_paths(kwargs)
    video_paths.extend(extra_paths)

    if not video_paths:
        raise FileNotFoundError(
            f'录屏文件不存在或路径无效: {video_path}'
        )

    result: Dict[str, Any] = {
        'enabled': True,
        'model': model,
        'task_type': task_type,
        'env_type': env_type,
        'video_path': video_path,
        'evaluations': [],
        'tokens_used': 0,
        'input_token': 0,
        'output_token': 0,
        'message': '',
    }

    try:
        response = _call_llm_api(
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            video_paths=video_paths,
        )
    except Exception as e:
        result['message'] = f'LLM 调用失败: {e}'
        result['enabled'] = False
        logger.error(f'[{task_type}] LLM 调用失败: {e}')
        return result

    result['tokens_used'] = response.get('tokens_used', 0)
    result['input_token'] = response.get('input_token', 0)
    result['output_token'] = response.get('output_token', 0)

    parsed = _parse_json(response['content'])
    if not parsed:
        result['message'] = 'LLM 输出解析失败'
        logger.error(
            f'[{task_type}] LLM 输出解析失败: '
            f'{response["content"][:200]}'
        )
        return result

    evaluations = _parse_evaluations(parsed)
    result['evaluations'] = evaluations
    result['message'] = 'OK'

    logger.info(
        f'[{task_type}] env_type={env_type or "N/A"} '
        f'model={model} video={video_path} '
        f'n_evaluations={len(evaluations)} '
        f'tokens={result["tokens_used"]}'
    )
    return result


if __name__ == '__main__':
    import argparse
    from pathlib import Path

    # 独立运行时加载 eval_server/.env，使 API key 等配置生效
    _env_path = Path(__file__).resolve().parents[4] / '.env'
    if _env_path.exists():
        with open(_env_path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ.setdefault(k.strip(), v.strip())

    parser = argparse.ArgumentParser(
        description='语音对话能力 — 录屏文件 LLM 裁判'
    )
    parser.add_argument('video', help='录屏文件路径')
    parser.add_argument('--task_type', default='env_judge',
                        choices=['env_judge', '拒识与环境理解',
                                 'interruption_judge', '打断能力'],
                        help='测试类型: env_judge(拒识与环境理解) '
                             '或 interruption_judge(打断能力)')
    parser.add_argument('--env_type', default='',
                        help='环境子场景类型（如 环境回溯/旁人交谈/环境噪声等）')
    parser.add_argument('--model', default='', help='LLM 模型名')
    parser.add_argument('--max_tokens', type=int, default=4096)
    parser.add_argument('--temperature', type=float, default=0.1)
    args = parser.parse_args()

    r = evaluate_env_judge(
        video_path=args.video,
        task_type=args.task_type,
        env_type=args.env_type,
        model=args.model,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
    )

    print('=' * 60)
    print(f'模型: {r["model"]}')
    print(f'测试类型: {r.get("task_type", "")}')
    print(f'环境类型: {r.get("env_type", "") or "N/A"}')
    print(f'录屏: {r["video_path"]}')
    print(f'tokens: {r["tokens_used"]} (in={r["input_token"]}, out={r["output_token"]})')
    print(f'message: {r["message"]}')
    print('-' * 60)
    for ev in r.get('evaluations', []):
        print(f'\n  场景: {ev.get("scene", "")}')
        print(f'  行为: {ev.get("behavior", "")}')
        print(f'  理由: {ev.get("reason", "")}')
    print('=' * 60)
    print(json.dumps(r, ensure_ascii=False, indent=2))
