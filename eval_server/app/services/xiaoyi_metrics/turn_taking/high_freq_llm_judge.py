# -*- coding: utf-8 -*-
"""
high_freq_llm_judge.py
高频轮换场景 LLM 裁判：传输录屏文件，逐轮评估问答内容是否符合预期

场景: 飞花令 / 成语接龙 / 快问快答等高频多轮对话。
将录屏文件发送给多模态 LLM，结合 rounds 文本上下文（用户提问/模型回复/预期答案），
逐轮判断模型回复是否符合预期，返回 pass/fail + reason。

参考 env_judge.py 的多模态请求格式（音频 input_audio / 视频 image_url），
复用 config.LLM_JUDGE 配置（api_base_url / api_key / default_model）。
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

# ─────────── 文件扩展名 ───────────
_AUDIO_EXTS = {'.wav', '.mp3', '.flac', '.aac', '.ogg', '.opus', '.m4a'}
_VIDEO_EXTS = {
    '.mp4', '.avi', '.mkv', '.webm', '.mov', '.flv',
    '.wmv', '.m4v', '.ts', '.3gp',
}

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


# ─────────── 文件编码 ───────────
def _is_audio(file_path: str) -> bool:
    return os.path.splitext(file_path)[1].lower() in _AUDIO_EXTS


def _encode_file_to_data(file_path: str) -> str:
    """将文件编码为纯 base64 字符串（用于 input_audio 的 data 字段）"""
    with open(file_path, 'rb') as f:
        return base64.b64encode(f.read()).decode()


def _encode_video_to_data_uri(file_path: str) -> str:
    """将视频文件编码为带 MIME 的 base64 data URI（用于 image_url）"""
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
    ext = os.path.splitext(file_path)[1].lower()
    fmt_map = {'.wav': 'wav', '.mp3': 'mp3', '.flac': 'flac',
               '.aac': 'aac', '.ogg': 'ogg', '.opus': 'opus', '.m4a': 'm4a'}
    return fmt_map.get(ext, 'wav')


def _build_content(prompt: str, file_paths: Optional[List[str]] = None) -> list:
    """构建 user message content，音频在前、视频在后、文本最后"""
    content: list = []
    audio_parts: List[str] = []
    video_parts: List[str] = []
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


# ─────────── LLM 调用 ───────────
def _call_llm_api(model: str, prompt: str,
                  max_tokens: int = 4096,
                  temperature: float = 0.1,
                  file_paths: Optional[List[str]] = None) -> Dict[str, Any]:
    """调用 OpenAI 兼容的 LLM API（多模态：文本 + 音频/录屏）

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
        user_content = _build_content(prompt, file_paths)
    else:
        user_content = [{'type': 'text', 'text': prompt}]

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
        payload['stream'] = True
        payload['stream_options'] = {'include_usage': True}
    else:
        payload['response_format'] = {'type': 'json_object'}

    url = f'{api_base.rstrip("/")}/chat/completions'
    max_retries = llm_config.get('max_retries', LLM_MAX_RETRIES)

    for attempt in range(max_retries + 1):
        try:
            client_timeout = 300 if is_omni else timeout
            with httpx.Client(trust_env=False, timeout=client_timeout) as client:
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
            status_code = e.response.status_code
            if 500 <= status_code < 600:
                try:
                    err_body = e.response.text[:500]
                except Exception:
                    err_body = '<无法读取>'
                logger.warning(f'LLM API 返回 {status_code}，响应体: {err_body}')
            if status_code != 429 and not (500 <= status_code < 600):
                raise
            if attempt >= max_retries:
                logger.error(f'LLM API 返回 {status_code}，已达最大重试次数 {max_retries}')
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
            if attempt >= max_retries:
                logger.error(f'LLM API 请求失败，已达最大重试次数 {max_retries}')
                raise
            delay = LLM_RETRY_BASE_DELAY * (2 ** attempt)
            logger.warning(
                f'LLM API 请求异常: {e}，{delay:.1f}s 后重试 '
                f'(attempt {attempt + 1}/{max_retries})'
            )
            time.sleep(delay)

    return {
        'content': data['choices'][0]['message']['content'],
        'tokens_used': data.get('usage', {}).get('total_tokens', 0),
        'input_token': data.get('usage', {}).get('prompt_tokens', 0),
        'output_token': data.get('usage', {}).get('completion_tokens', 0),
    }


# ─────────── prompt 构建 ───────────
def _unwrap_value(val: Any) -> str:
    """解包 {'text': '...'} 格式"""
    if isinstance(val, dict) and 'text' in val:
        return val['text']
    return val or ''


def _extract_round_fields(rd: Dict[str, Any]) -> Dict[str, str]:
    """从单轮数据中提取 query / answer / expected_answer"""
    query = _unwrap_value(rd.get('query') or rd.get('question') or '')
    answer = _unwrap_value(
        rd.get('answer') or rd.get('response') or rd.get('ai_answer') or ''
    )
    expected = _unwrap_value(
        rd.get('expected_answer') or rd.get('reference_answer')
        or rd.get('reference') or rd.get('correct_answer')
        or rd.get('expected') or ''
    )
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

    rounds_text = '\n\n'.join(round_blocks) if round_blocks else '（未提供文本轮次信息，请从录屏中自行识别）'

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

    return f"""你是语音对话质量评估专家。你将收到一段录屏/音频文件，记录了用户与语音大模型的高频轮换对话过程。请结合录屏内容和下方对话信息，逐轮判断模型回复是否符合预期。

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
- reason 需简述判定依据（从录屏中听到了什么、模型回复了什么、为何符合/不符合）

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
- 若录屏中某轮对话无法识别或不存在，pass 填 false、reason 说明原因"""


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
    video_path: str,
    rounds: List[Dict[str, Any]],
    scenario_type: str = '',
    scenario_rules: str = '',
    model: str = '',
    max_tokens: int = 4096,
    temperature: float = 0.1,
    **kwargs,
) -> Dict[str, Any]:
    """高频轮换场景 LLM 裁判主入口

    将录屏文件发送给多模态 LLM，结合 rounds 文本上下文，
    逐轮判断模型回复是否符合预期，返回 pass/fail + reason。

    Args:
        video_path: 录屏/音频文件路径
        rounds: 多轮文本数据，每轮 {query, answer, expected_answer}（字段名兼容）
        scenario_type: 场景类型（飞花令/成语接龙/快问快答/自定义）
        scenario_rules: 自定义场景规则（scenario_type='自定义' 时使用）
        model: LLM 模型名，缺省读 config.LLM_JUDGE.default_model
        max_tokens: 最大输出 token 数
        temperature: 采样温度，评判场景建议低温 0.1
        **kwargs: 额外录屏文件路径

    Returns:
        dict: {
            'enabled': bool,
            'model': str,
            'scenario_type': str,
            'video_path': str,
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
    from app.config import config

    llm_config = getattr(config, 'LLM_JUDGE', {})
    if not model:
        model = llm_config.get('default_model', 'gpt-4o')

    # 收集录屏文件路径
    file_paths: List[str] = []
    if video_path and os.path.isfile(video_path):
        file_paths.append(video_path)
    for value in kwargs.values():
        if isinstance(value, str) and value and os.path.isfile(value):
            ext = os.path.splitext(value)[1].lower()
            if ext in (_VIDEO_EXTS | _AUDIO_EXTS):
                file_paths.append(value)

    if not file_paths:
        raise FileNotFoundError(f'录屏文件不存在或路径无效: {video_path}')

    # 过滤无效轮次
    valid_rounds = [rd for rd in rounds if isinstance(rd, dict)]

    prompt = _build_prompt(valid_rounds, scenario_type, scenario_rules)

    result: Dict[str, Any] = {
        'enabled': True,
        'model': model,
        'scenario_type': scenario_type,
        'video_path': video_path,
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
        response = _call_llm_api(
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

    parsed = _parse_json(response['content'])
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
    parser.add_argument('--max_tokens', type=int, default=4096)
    parser.add_argument('--temperature', type=float, default=0.1)
    args = parser.parse_args()

    with open(args.rounds_json, encoding='utf-8') as f:
        rounds_data = json.load(f)

    r = evaluate_high_freq_llm(
        video_path=args.video,
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
    print(f'录屏: {r["video_path"]}')
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
