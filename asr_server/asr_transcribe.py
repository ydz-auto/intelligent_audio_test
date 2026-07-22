# -*- coding: utf-8 -*-
"""
阿里云百炼 录音文件识别（Fun-ASR）示例
文档：https://help.aliyun.com/zh/model-studio/developer-reference/audio-file-transcription
"""
import os
import json
from http import HTTPStatus
from urllib import request

import dashscope
from dashscope.audio.asr import Transcription

# 以下为华北2（北京）地域的配置，调用时请将"{WorkspaceId}"替换为真实的业务空间ID，各地域的配置不同。
# dashscope.base_http_api_url = 'https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/api/v1'

# 优先从环境变量读取；若没有配置环境变量，请用阿里云百炼API Key将下行替换为：dashscope.api_key = "sk-xxx"
dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")

if not dashscope.api_key:
    raise SystemExit("未检测到 DASHSCOPE_API_KEY 环境变量，请先设置后再运行。")


def transcribe(file_urls, language_hints=('zh', 'en'), model='fun-asr'):
    """提交录音文件转写任务并等待结果。"""
    task_response = Transcription.async_call(
        model=model,
        file_urls=list(file_urls),
        language_hints=list(language_hints),  # 可选，指定待识别音频的语言代码
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
        language_hints=['zh', 'en'],
    )
