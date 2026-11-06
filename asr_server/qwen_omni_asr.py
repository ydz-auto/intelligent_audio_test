# -*- coding: utf-8 -*-
"""
qwen_omni_asr.py
基于第三方模型的 ASR 转写脚本（通过 az.gptplus5.com 代理）。

音频通过 base64 编码发送，根据模型类型选择不同格式：
- qwen3-asr-flash（纯 ASR）：input_audio + data URI（百炼 DashScope）
- qwen3.5-omni-plus（omni）：image_url + data URI（第三方代理）
- gemini 等非 Qwen 模型：input_audio + 纯 base64

输出格式与本地 asr_server 一致：
    {"text": "全文", "chunks": [{"text": "段文本", "timestamp": [start_s, end_s]}, ...]}

用法:
    # 单文件转写
    python qwen_omni_asr.py single D:\\path\\to\\audio.wav

    # 批量转写目录下所有 wav
    python qwen_omni_asr.py batch D:\\path\\to\\wav_dir

    # 批量转写并指定输出 json 路径
    python qwen_omni_asr.py batch D:\\path\\to\\wav_dir --output D:\\path\\to\\result.json

配置（从 asr_server/.env 读取）:
    QWEN_OMNI_API_KEY    API Key（必填）
    QWEN_OMNI_API_BASE   接口地址（默认 https://az.gptplus5.com/v1）
    QWEN_OMNI_MODEL      模型名（默认 gemini-3.7-flash）
    QWEN_OMNI_TIMEOUT    请求超时秒数（默认 300）
"""
import os
import sys
import re
import json
import base64
import logging
import argparse
import glob
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

# ─── 加载 .env 文件 ───
_env_path = Path(__file__).resolve().parent / '.env'
if _env_path.exists():
    with open(_env_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())

# ─── 配置 ───
API_KEY = os.environ.get('QWEN_OMNI_API_KEY', '')
API_BASE = os.environ.get('QWEN_OMNI_API_BASE', 'https://az.gptplus5.com/v1')
MODEL = os.environ.get('QWEN_OMNI_MODEL', 'gemini-3.7-flash')
TIMEOUT = int(os.environ.get('QWEN_OMNI_TIMEOUT', '300'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)
logger = logging.getLogger('qwen_omni_asr')


# ─── 音频 base64 编码 ───
def encode_audio_to_b64(wav_path: str) -> tuple:
    """将 WAV 文件编码为 base64 字符串，返回 (base64_data, format)。"""
    with open(wav_path, 'rb') as f:
        data = f.read()
    b64 = base64.b64encode(data).decode()
    ext = os.path.splitext(wav_path)[1].lower().lstrip('.')
    fmt = 'wav' if ext in ('wav', '') else ext
    return b64, fmt


# ─── 构建 prompt ───
ASR_PROMPT = """请对这段音频进行逐词级别的语音转写（ASR），要求：
1. 识别音频中的所有语音内容（支持中文和英文）
2. 对每一个词/字给出准确的开始和结束时间戳（单位：秒）
3. 中文按单字拆分，英文按单词拆分
4. 忽略非语音噪声，不要给噪声生成chunk
5. 只输出JSON，不要输出任何其他内容

输出格式：
{"text":"全文合并文本","chunks":[{"text":"字","timestamp":[0.10,0.35]},{"text":"词","timestamp":[1.20,1.50]}]}

注意：timestamp为[开始秒,结束秒]，精确到0.01秒。如果没有语音返回{"text":"","chunks":[]}"""


# ─── 调用第三方模型 ASR ───
def call_qwen_omni_asr(wav_path: str) -> Dict[str, Any]:
    """调用第三方模型对 WAV 文件进行 ASR 转写。

    音频通过 base64 编码，以 OpenAI input_audio 格式发送（与
    eval_server/app/services/calculators/xiaoyi_metrics/env_judge/_common.py
    中 build_content 方式一致）。

    非流式请求，直接解析 JSON 响应。

    Returns:
        {"text": str, "chunks": [{"text": str, "timestamp": [float, float]}, ...]}
    """
    if not API_KEY:
        raise ValueError(
            '未配置 QWEN_OMNI_API_KEY，请在 asr_server/.env 中设置'
        )

    b64_data, audio_fmt = encode_audio_to_b64(wav_path)
    fname = os.path.basename(wav_path)

    is_dashscope = 'aliyuncs.com' in API_BASE
    is_qwen_model = 'qwen' in MODEL.lower()
    is_pure_asr = 'asr' in MODEL.lower() and 'omni' not in MODEL.lower()
    is_omni = 'omni' in MODEL.lower()

    # Qwen 模型统一用 data URI 格式（百炼 + 代理都需要）
    # 非 Qwen 模型（如 gemini）用纯 base64
    use_data_uri = is_qwen_model or is_dashscope
    audio_data = f'data:audio/{audio_fmt};base64,{b64_data}' if use_data_uri else b64_data

    # 构建 content
    if is_pure_asr:
        # qwen3-asr-flash: 纯 ASR 模型，只接受音频（无文本 prompt，无 format 字段）
        user_content = [
            {'type': 'input_audio', 'input_audio': {'data': audio_data}},
        ]
    else:
        # omni 模型在百炼 DashScope / 其他多模态模型：input_audio + 文本 prompt
        user_content = [
            {'type': 'input_audio', 'input_audio': {'data': audio_data, 'format': audio_fmt}},
            {'type': 'text', 'text': ASR_PROMPT},
        ]

    payload: Dict[str, Any] = {
        'model': MODEL,
        'messages': [{'role': 'user', 'content': user_content}],
        'max_tokens': 8192,
        'temperature': 0.1,
    }

    # omni 模型需 modalities=['text']；百炼 DashScope 用非 stream + JSON 结构化输出
    if is_omni:
        payload['modalities'] = ['text']
        if is_dashscope:
            payload['response_format'] = {'type': 'json_object'}
        else:
            payload['stream'] = True
            payload['stream_options'] = {'include_usage': True}

    headers = {
        'Authorization': f'Bearer {API_KEY}',
        'Content-Type': 'application/json',
    }

    url = f'{API_BASE.rstrip("/")}/chat/completions'
    httpx_timeout = httpx.Timeout(
        connect=10.0, write=float(TIMEOUT),
        read=float(TIMEOUT), pool=float(TIMEOUT),
    )

    logger.info(f'发送 ASR 请求: {fname} -> {MODEL}')

    content_text = ''
    usage_data: Dict[str, Any] = {}

    with httpx.Client(trust_env=False, timeout=httpx_timeout) as client:
        if payload.get('stream'):
            # stream 模式（az.gptplus5.com 代理的 omni 模型）
            with client.stream('POST', url, headers=headers, json=payload) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    line = line.strip() if line else ''
                    if not line or not line.startswith('data: '):
                        continue
                    chunk_str = line[6:]
                    if chunk_str == '[DONE]':
                        break
                    try:
                        chunk = json.loads(chunk_str)
                    except json.JSONDecodeError:
                        continue
                    if chunk.get('error'):
                        raise RuntimeError(f"API error: {chunk['error']}")
                    choices = chunk.get('choices', [])
                    if choices:
                        delta = choices[0].get('delta', {})
                        content_text += delta.get('content', '')
                    if chunk.get('usage'):
                        usage_data = chunk['usage']
        else:
            # 非 stream 模式（百炼 DashScope + 非 omni 模型）
            response = client.post(url, headers=headers, json=payload)
            if response.status_code != 200:
                logger.error(f'API 返回 {response.status_code}: {response.text[:500]}')
            response.raise_for_status()
            data = response.json()
            if data.get('error'):
                raise RuntimeError(f"API error: {data['error']}")
            content_text = data['choices'][0]['message']['content']
            usage_data = data.get('usage', {})

    logger.info(
        f'ASR 响应完成: {fname} '
        f'tokens={usage_data.get("total_tokens", 0)} '
        f'content_len={len(content_text)}'
    )

    # 解析响应
    if is_pure_asr:
        # qwen3-asr-flash: 直接返回纯文本，无时间戳
        result = {'text': content_text, 'chunks': []}
    else:
        result = _parse_asr_json(content_text)
        if result is None:
            logger.warning(f'JSON 解析失败，返回原始文本: {content_text[:200]}')
            result = {
                'text': content_text,
                'chunks': [],
                '_raw': content_text,
                '_warning': 'JSON 解析失败，text 字段为原始 LLM 输出',
            }

    return result


def _parse_asr_json(content: str) -> Optional[Dict[str, Any]]:
    """解析 LLM 输出为 ASR 结果 dict。

    先尝试 json.loads，失败则用正则提取 JSON 块。
    """
    if not content:
        return None

    # 去除可能的 markdown 代码块标记
    cleaned = content.strip()
    if cleaned.startswith('```'):
        lines = cleaned.split('\n')
        if lines[0].startswith('```'):
            lines = lines[1:]
        if lines and lines[-1].startswith('```'):
            lines = lines[:-1]
        cleaned = '\n'.join(lines).strip()

    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        pass

    # 正则兜底
    m = re.search(r'\{.*\}', content, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except (json.JSONDecodeError, TypeError):
            return None
    return None


# ─── 批量转写 ───
def batch_transcribe(wav_dir: str, output_dir: str = '') -> List[Dict[str, Any]]:
    """批量转写目录下所有 WAV 文件，每个 WAV 生成一个对应的 JSON 文件。

    Args:
        wav_dir: WAV 文件所在目录
        output_dir: JSON 输出目录，默认与 wav_dir 相同

    Returns:
        转写结果列表
    """
    wav_files = sorted(glob.glob(os.path.join(wav_dir, '*.wav')))
    if not wav_files:
        logger.warning(f'目录下无 WAV 文件: {wav_dir}')
        return []

    if not output_dir:
        output_dir = wav_dir
    os.makedirs(output_dir, exist_ok=True)

    print(f'共 {len(wav_files)} 个 WAV 文件待转写（模型: {MODEL}）\n')
    print('=' * 80)

    results = []
    for wf in wav_files:
        fname = os.path.basename(wf)
        json_name = os.path.splitext(fname)[0] + '.json'
        json_path = os.path.join(output_dir, json_name)
        t0 = time.time()
        try:
            data = call_qwen_omni_asr(wf)
            elapsed = time.time() - t0
            text = data.get('text', '')
            chunks = data.get('chunks', [])
            print(f'\n[{fname}] ({elapsed:.1f}s)')
            print(f'  文本: {text}')
            for c in chunks:
                ts = c.get('timestamp', [])
                t0_s = ts[0] if len(ts) > 0 else 0
                t1_s = ts[1] if len(ts) > 1 else 0
                ct = c.get('text', '')
                print(f'  词 [{t0_s:.2f}s - {t1_s:.2f}s]: {ct}')
            # 每个 WAV 生成一个对应的 JSON
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f'  已保存: {json_name}')
            results.append({'file': fname, 'json': json_path, 'text': text, 'chunks': chunks})
        except Exception as e:
            elapsed = time.time() - t0
            logger.error(f'转写失败 [{fname}] ({elapsed:.1f}s): {e}')
            results.append({'file': fname, 'json': json_path, 'text': '', 'chunks': [], 'error': str(e)})

    print('\n' + '=' * 80)
    print(f'全部转写完成，共 {len(results)} 个文件')
    print(f'JSON 文件保存目录: {output_dir}')

    return results


# ─── 主入口 ───
if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='第三方模型 ASR 转写（base64 传输，带时间戳）'
    )
    sub = parser.add_subparsers(dest='command', help='子命令')

    # 单文件
    p_single = sub.add_parser('single', help='转写单个 WAV 文件')
    p_single.add_argument('wav_path', help='WAV 文件路径')

    # 批量
    p_batch = sub.add_parser('batch', help='批量转写目录下所有 WAV 文件')
    p_batch.add_argument('wav_dir', help='WAV 文件所在目录')
    p_batch.add_argument('--output-dir', default='', help='JSON 输出目录（默认与 wav 目录相同）')

    args = parser.parse_args()

    if args.command == 'single':
        if not os.path.isfile(args.wav_path):
            print(f'文件不存在: {args.wav_path}')
            sys.exit(1)
        r = call_qwen_omni_asr(args.wav_path)
        print(json.dumps(r, ensure_ascii=False, indent=2))

    elif args.command == 'batch':
        if not os.path.isdir(args.wav_dir):
            print(f'目录不存在: {args.wav_dir}')
            sys.exit(1)
        batch_transcribe(args.wav_dir, args.output_dir)

    else:
        parser.print_help()
