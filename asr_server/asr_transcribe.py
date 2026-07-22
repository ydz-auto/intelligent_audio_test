# -*- coding: utf-8 -*-
"""
阿里云百炼 录音文件识别（Fun-ASR）示例
文档：https://help.aliyun.com/zh/model-studio/developer-reference/audio-file-transcription

配置项（从 asr_server/.env 读取）：
    DASHSCOPE_API_KEY   阿里云百炼 API Key（必填）
    DASHSCOPE_MODEL     转写模型（默认 fun-asr）
    DASHSCOPE_LANGUAGES 语言提示（默认 zh,en）
    DASHSCOPE_BASE_URL  自定义 API 地址（可选，用于华北2等地域）
"""
import os
import json
from http import HTTPStatus
from urllib import request
from pathlib import Path

# ─── 加载 .env 文件 ───
_env_path = Path(__file__).resolve().parent / '.env'
if _env_path.exists():
    with open(_env_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())

import dashscope
from dashscope.audio.asr import Transcription

# 从 .env / 环境变量读取配置
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
DASHSCOPE_MODEL = os.environ.get("DASHSCOPE_MODEL", "fun-asr")
DASHSCOPE_LANGUAGES = tuple(
    lang.strip()
    for lang in os.environ.get("DASHSCOPE_LANGUAGES", "zh,en").split(",")
    if lang.strip()
)
DASHSCOPE_BASE_URL = os.environ.get("DASHSCOPE_BASE_URL", "")

dashscope.api_key = DASHSCOPE_API_KEY
if DASHSCOPE_BASE_URL:
    dashscope.base_http_api_url = DASHSCOPE_BASE_URL

if not dashscope.api_key:
    raise SystemExit(
        "未检测到 DASHSCOPE_API_KEY，请在 asr_server/.env 中配置。\n"
        "示例: DASHSCOPE_API_KEY=sk-xxx"
    )


def transcribe(file_urls, language_hints=None, model=None):
    """提交录音文件转写任务并等待结果。

    Args:
        file_urls: 音频文件的公网 URL 列表
        language_hints: 语言提示列表，默认从 .env 读取 (DASHSCOPE_LANGUAGES)
        model: 转写模型名，默认从 .env 读取 (DASHSCOPE_MODEL)
    """
    if language_hints is None:
        language_hints = DASHSCOPE_LANGUAGES
    if model is None:
        model = DASHSCOPE_MODEL

    task_response = Transcription.async_call(
        model=model,
        file_urls=list(file_urls),
        language_hints=list(language_hints),
    )
    print(f"任务已提交，task_id={task_response.output.task_id}")

    transcription_response = Transcription.wait(task=task_response.output.task_id)

    if transcription_response.status_code != HTTPStatus.OK:
        print('Error: ', transcription_response.output.message)
        return

    for transcription in transcription_response.output['results']:
        if transcription['subtask_status'] != 'SUCCEEDED':
            print('transcription failed!')
            print(transcription)
            continue

        url = transcription['transcription_url']
        result = json.loads(request.urlopen(url).read().decode('utf8'))
        print(json.dumps(result, indent=4, ensure_ascii=False))


if __name__ == '__main__':
    transcribe(
        file_urls=[
            'https://dashscope.oss-cn-beijing.aliyuncs.com/samples/audio/paraformer/hello_world_female2.wav'
        ],
    )
