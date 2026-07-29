# -*- coding: utf-8 -*-
"""Qwen3 WebSocket + JSON adapter

通过 WebSocket 连接阿里通义 Qwen3 实时翻译 API,用 JSON 编码消息。
"""
import asyncio
import base64
import json
import time
import os
from typing import Optional

import websockets

from api_adapter_service.adapters.base import BaseAdapter
from api_adapter_service.utils.logger import logger


class QwenAdapter(BaseAdapter):
    """Qwen3 WebSocket + JSON adapter

    vendor_config 需要:
    - api_key: 鉴权 key
    - api_url: WebSocket 地址
    - target_language: 目标语言
    - audio_enabled: 是否返回音频
    """

    # 输入音频配置(16k/16bit/单声道 PCM)
    _INPUT_RATE = 16000
    _INPUT_CHUNK = 1600  # 100ms @16k/16bit/单声道

    def __init__(self, vendor_config: dict):
        super().__init__(vendor_config)
        self.api_key = vendor_config.get('api_key', '')
        self.api_url = vendor_config.get(
            'api_url',
            'wss://dashscope.aliyuncs.com/api-ws/v1/realtime'
            '?model=qwen3-livetranslate-flash-realtime',
        )
        self.target_language = vendor_config.get('target_language', 'en')
        self.audio_enabled = vendor_config.get('audio_enabled', False)
        self.timeout = vendor_config.get('timeout', 30)

    def send_request(self, task_id, session_id, input_type, input_data,
                     source_lang='zh', target_lang='en', **kwargs) -> dict:
        """同步发送请求

        input_data: 音频文件路径(str)或音频字节(bytes)。
        """
        start_time = time.time()
        try:
            result = asyncio.run(self._translate(
                input_data,
                target_lang or self.target_language,
            ))
            latency = time.time() - start_time
            result['latency'] = round(latency, 3)
            result['session_id'] = session_id
            return result
        except Exception as e:
            logger.error(f'QwenAdapter error: {e}', exc_info=True)
            return {
                'asr_text': '', 'trans_text': '', 'output': '',
                'session_id': session_id,
                'latency': round(time.time() - start_time, 3),
                'raw_response': {'error': str(e)},
            }

    # ── 内部实现 ───────────────────────────────────────────────

    def _read_audio_chunks(self, audio_source,
                           chunk_size: int = _INPUT_CHUNK):
        """读取音频为固定大小分片(1600 字节 = 100ms @16k/16bit/单声道)

        audio_source: 文件路径(str)或字节(bytes)
        """
        chunks = []
        if isinstance(audio_source, (bytes, bytearray)):
            data = bytes(audio_source)
            for i in range(0, len(data), chunk_size):
                chunks.append(data[i:i + chunk_size])
            return chunks

        if not isinstance(audio_source, str) or not os.path.isfile(audio_source):
            logger.error(f'QwenAdapter: 音频文件不存在或格式无效: {audio_source}')
            return chunks

        try:
            with open(audio_source, 'rb') as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    chunks.append(chunk)
        except Exception as e:
            logger.error(f'QwenAdapter: 读取音频文件失败: {e}')
        return chunks

    async def _configure_session(self, ws, target_language: str):
        """配置翻译会话,设置目标语言、声音等"""
        config = {
            'event_id': f'event_{int(time.time() * 1000)}',
            'type': 'session.update',
            'session': {
                'modalities': (['text', 'audio']
                               if self.audio_enabled else ['text']),
                'input_audio_format': 'pcm16',
                'output_audio_format': 'pcm16',
                'translation': {
                    'language': target_language,
                },
            },
        }
        if self.audio_enabled and 'voice' in self.vendor_config:
            config['session']['voice'] = self.vendor_config['voice']
        await ws.send(json.dumps(config))
        logger.info(f'QwenAdapter: 会话已配置,目标语言={target_language}')

    async def _send_audio_chunk(self, ws, audio_data: bytes):
        """将音频数据块编码并发送到服务端"""
        event = {
            'event_id': f'event_{int(time.time() * 1000)}',
            'type': 'input_audio_buffer.append',
            'audio': base64.b64encode(audio_data).decode(),
        }
        await ws.send(json.dumps(event))

    async def _translate(self, audio_source, target_language: str) -> dict:
        """核心翻译逻辑(从 qwen3_livetranslate_client.py 移植)

        audio_source: 音频文件路径或音频字节
        返回 {asr_text, trans_text, output, raw_response}
        """
        # 1. 读取音频分片
        audio_chunks = self._read_audio_chunks(audio_source)
        if not audio_chunks:
            return {
                'asr_text': '',
                'trans_text': '',
                'output': '',
                'raw_response': {'error': '音频读取失败或为空'},
            }
        logger.info(f'QwenAdapter: 读取音频 {len(audio_chunks)} 个分片')

        asr_text_list = []
        trans_text_list = []
        full_transcript = ''
        usage_info = {}
        ws = None
        try:
            # 2. 连接 WebSocket
            headers = {'Authorization': f'Bearer {self.api_key}'}
            ws = await websockets.connect(self.api_url, additional_headers=headers)
            self.connected = True
            logger.info(f'QwenAdapter: 已连接 {self.api_url}')

            # 3. 配置会话
            await self._configure_session(ws, target_language)

            # 4. 发送音频分片 + 接收响应并发进行
            async def send_audio():
                try:
                    for chunk in audio_chunks:
                        await self._send_audio_chunk(ws, chunk)
                        await asyncio.sleep(0.1)  # 与分片时长匹配
                    # 发送结束标记,触发服务端返回最终结果
                    await ws.send(json.dumps({
                        'event_id': f'event_{int(time.time() * 1000)}',
                        'type': 'input_audio_buffer.commit',
                    }))
                    logger.info('QwenAdapter: 音频分片发送完成')
                except Exception as e:
                    logger.error(f'QwenAdapter: 发送音频分片失败: {e}')

            sender_task = asyncio.create_task(send_audio())

            # 5. 接收并处理服务端消息
            try:
                async for message in ws:
                    try:
                        event = json.loads(message)
                    except (json.JSONDecodeError, TypeError):
                        logger.debug(f'QwenAdapter: 收到非 JSON 消息: {message}')
                        continue

                    event_type = event.get('type')

                    if event_type == 'response.audio_transcript.delta':
                        # ASR 增量文本(原文)
                        text = event.get('transcript', '')
                        if text:
                            asr_text_list.append(text)

                    elif event_type == 'response.text.delta':
                        # 翻译增量文本
                        text = event.get('delta', '')
                        if text:
                            trans_text_list.append(text)

                    elif event_type == 'response.audio_transcript.done':
                        # ASR 完整文本
                        text = event.get('transcript', '')
                        if text:
                            asr_text_list = [text]

                    elif event_type == 'response.text.done':
                        # 翻译完整文本
                        text = event.get('text', '')
                        if text:
                            full_transcript = text

                    elif event_type == 'response.done':
                        # 一轮响应完成
                        usage = event.get('response', {}).get('usage', {})
                        if usage:
                            usage_info = usage
                        logger.info('QwenAdapter: 响应完成')
                        break

                    elif event_type == 'error':
                        err = event.get('error', {})
                        logger.error(
                            f'QwenAdapter: 服务端错误: {err.get("message", "")}'
                        )
                        break

                    else:
                        logger.debug(
                            f'QwenAdapter: 未处理事件 {event_type}'
                        )

            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f'QwenAdapter: 连接已关闭: {e}')

            # 等待发送任务完成
            await sender_task

        except Exception as e:
            logger.error(f'QwenAdapter: 翻译过程异常: {e}', exc_info=True)
            return {
                'asr_text': ''.join(asr_text_list).strip(),
                'trans_text': full_transcript or ''.join(trans_text_list).strip(),
                'output': '',
                'raw_response': {'error': str(e)},
            }
        finally:
            self.connected = False
            if ws:
                try:
                    await ws.close()
                except Exception:
                    pass

        full_asr = ''.join(asr_text_list).strip()
        full_trans = full_transcript or ''.join(trans_text_list).strip()

        return {
            'asr_text': full_asr,
            'trans_text': full_trans,
            'output': full_trans or full_asr,
            'raw_response': {
                'target_language': target_language,
                'audio_enabled': self.audio_enabled,
                'usage': usage_info,
            },
        }
