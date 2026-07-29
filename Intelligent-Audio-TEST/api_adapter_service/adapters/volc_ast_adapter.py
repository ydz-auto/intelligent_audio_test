# -*- coding: utf-8 -*-
"""火山 AST WebSocket + Protobuf adapter

通过 WebSocket 连接火山引擎 AST API,用 Protobuf 编码消息。
支持语音翻译:音频分片发送 → 接收 ASR + 翻译结果。
"""
import asyncio
import uuid
import time
import os
import sys
from typing import Optional

import websockets
from websockets import Headers

# 添加 proto 路径,使 products/common 等顶层包可被导入
_current = os.path.dirname(os.path.abspath(__file__))
_proto_dir = os.path.abspath(os.path.join(_current, '..', 'proto', 'volc_ast'))
if _proto_dir not in sys.path:
    sys.path.insert(0, _proto_dir)

from api_adapter_service.adapters.base import BaseAdapter
from api_adapter_service.utils.logger import logger

# 火山 AST protobuf
from products.understanding.ast.ast_service_pb2 import (
    TranslateRequest, ReqParams, TranslateResponse,
)
from common.events_pb2 import Type


class VolcAstAdapter(BaseAdapter):
    """火山 AST WebSocket + Protobuf adapter

    vendor_config 需要:
    - ws_url: WebSocket 连接地址
    - app_key / access_key / resource_id: 鉴权
    - mode: s2s 或 s2t
    """

    # 忽略的无文本状态类事件(来自 event.proto)
    _IGNORE_EVENT_TYPES = {
        250,   # 会话状态/心跳事件
        650,   # SourceSubtitleStart
        652,   # SourceSubtitleEnd
        653,   # TranslationSubtitleStart
        655,   # TranslationSubtitleEnd
    }
    # ASR 相关事件
    _ASR_EVENT_TYPES = {450, 451, 459, 651}
    # 翻译相关事件
    _TRANSLATE_EVENT_TYPES = {654}
    # 用量统计事件
    _USAGE_EVENT_TYPE = 154

    def __init__(self, vendor_config: dict):
        super().__init__(vendor_config)
        self.ws_url = vendor_config.get('ws_url', '')
        self.app_key = vendor_config.get('app_key', '')
        self.access_key = vendor_config.get('access_key', '')
        self.resource_id = vendor_config.get('resource_id', '')
        self.mode = vendor_config.get('mode', 's2s')
        self.timeout = vendor_config.get('timeout', 30)

    def send_request(self, task_id, session_id, input_type, input_data,
                     source_lang='zh', target_lang='en', **kwargs) -> dict:
        """同步发送请求(内部用 asyncio 跑协程)

        input_data: 音频文件路径(str)或音频字节(bytes)。
        """
        start_time = time.time()
        try:
            result = asyncio.run(self._translate(
                input_data,
                source_lang, target_lang,
            ))
            latency = time.time() - start_time
            result['latency'] = round(latency, 3)
            result['session_id'] = session_id
            return result
        except Exception as e:
            logger.error(f'VolcAstAdapter error: {e}', exc_info=True)
            return {
                'asr_text': '', 'trans_text': '', 'output': '',
                'session_id': session_id,
                'latency': round(time.time() - start_time, 3),
                'raw_response': {'error': str(e)},
            }

    # ── 内部实现 ───────────────────────────────────────────────

    def _build_headers(self, conn_id: str) -> Headers:
        """构建 API 请求头(包含鉴权信息)"""
        return Headers({
            'X-Api-App-Key': self.app_key,
            'X-Api-Access-Key': self.access_key,
            'X-Api-Resource-Id': self.resource_id,
            'X-Api-Connect-Id': conn_id,
        })

    def _build_translate_request(self, session_id: str, event_name: str,
                                 audio_chunk: Optional[bytes] = None,
                                 source_lang: str = 'zh',
                                 target_lang: str = 'en') -> TranslateRequest:
        """构建 TranslateRequest protobuf 消息

        event_name: 'Type_StartSession' / 'Type_TaskRequest' / 'Type_FinishSession'
        """
        request_data = TranslateRequest()

        # 请求元信息
        if session_id:
            request_data.request_meta.SessionID = session_id

        # 事件类型映射
        event_map = {
            'Type_StartSession': Type.StartSession,
            'Type_TaskRequest': Type.TaskRequest,
            'Type_FinishSession': Type.FinishSession,
        }
        request_data.event = event_map.get(event_name, 0)

        # 用户信息
        request_data.user.uid = 'ast_py_client'
        request_data.user.did = 'ast_py_client'

        # 源音频配置(强制 16k/16bit/单声道 WAV)
        request_data.source_audio.format = 'wav'
        request_data.source_audio.rate = 16000
        request_data.source_audio.bits = 16
        request_data.source_audio.channel = 1
        if audio_chunk:
            request_data.source_audio.binary_data = audio_chunk

        # 目标音频配置
        request_data.target_audio.format = 'wav'
        request_data.target_audio.rate = 16000
        request_data.target_audio.bits = 16
        request_data.target_audio.channel = 1

        # 翻译核心参数
        request_data.request.mode = self.mode
        request_data.request.source_language = source_lang
        request_data.request.target_language = target_lang

        return request_data

    def _parse_response(self, raw: bytes):
        """解析 TranslateResponse,分离 asr_text / translated_text

        Returns:
            (event: int, session_id: str, sequence: int,
             asr_text: str, translated_text: str, data: bytes, message: str)
        """
        resp = TranslateResponse()
        resp.ParseFromString(raw)

        current_event = resp.event
        session_id = resp.response_meta.SessionID if resp.response_meta else ''
        sequence = resp.response_meta.Sequence if resp.response_meta else 0
        message = (resp.response_meta.Message
                   if resp.response_meta and resp.response_meta.Message else '')

        # 忽略无文本的状态类事件
        if current_event in self._IGNORE_EVENT_TYPES:
            return (current_event, session_id, sequence, '', '', resp.data, message)

        asr_text = ''
        translated_text = ''

        if current_event in self._ASR_EVENT_TYPES:
            asr_text = resp.text.strip() if resp.text else ''
        elif current_event in self._TRANSLATE_EVENT_TYPES:
            translated_text = resp.text.strip() if resp.text else ''
        elif current_event == self._USAGE_EVENT_TYPE:
            # 用量统计事件,仅记录,不参与结果拼接
            pass

        return (current_event, session_id, sequence,
                asr_text, translated_text, resp.data, message)

    def _read_audio_chunks(self, audio_source, chunk_size: int = 3200):
        """读取音频为固定大小分片(3200 字节 = 100ms @16k/16bit/单声道)

        audio_source: 文件路径(str)或字节(bytes)
        """
        chunks = []
        if isinstance(audio_source, (bytes, bytearray)):
            data = bytes(audio_source)
            for i in range(0, len(data), chunk_size):
                chunks.append(data[i:i + chunk_size])
            return chunks

        if not isinstance(audio_source, str) or not os.path.isfile(audio_source):
            logger.error(f'VolcAstAdapter: 音频文件不存在或格式无效: {audio_source}')
            return chunks

        try:
            with open(audio_source, 'rb') as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    chunks.append(chunk)
        except Exception as e:
            logger.error(f'VolcAstAdapter: 读取音频文件失败: {e}')
        return chunks

    async def _translate(self, audio_source, source_lang: str,
                         target_lang: str) -> dict:
        """核心翻译逻辑(从 ast_demo_zh2en.py translate_v4 移植)

        audio_source: 音频文件路径或音频字节
        返回 {asr_text, trans_text, output, raw_response}
        """
        timestamps = {
            'request_start': None,
            'request_end': None,
            'asr_first_char': None,
            'asr_last_char': None,
            'translate_first_char': None,
            'translate_last_char': None,
        }
        asr_text_list = []
        translated_text_list = []

        # 1. 读取音频分片
        audio_chunks = self._read_audio_chunks(audio_source, 3200)
        if not audio_chunks:
            return {
                'asr_text': '',
                'trans_text': '',
                'output': '',
                'raw_response': {'error': '音频读取失败或为空'},
            }
        logger.info(f'VolcAstAdapter: 读取音频 {len(audio_chunks)} 个分片')

        conn = None
        try:
            # 2. 连接 WebSocket API
            conn_id = str(uuid.uuid4())
            headers = self._build_headers(conn_id)
            conn = await websockets.connect(
                self.ws_url,
                additional_headers=headers,
                max_size=1000000000,
                ping_interval=None,
            )
            log_id = conn.response.headers.get('X-Tt-Logid', '未知') if conn.response else '未知'
            logger.info(f'VolcAstAdapter: 连接 API 成功(log_id={log_id})')

            # 3. 启动会话
            session_id = str(uuid.uuid4())
            start_req = self._build_translate_request(
                session_id, 'Type_StartSession',
                source_lang=source_lang, target_lang=target_lang,
            )
            await conn.send(start_req.SerializeToString())
            raw = await conn.recv()
            ev, _sid, _seq, _asr, _trans, _data, msg = self._parse_response(raw)
            if ev != Type.SessionStarted:  # 150
                logger.error(f'VolcAstAdapter: 会话启动失败: {msg}')
                return {
                    'asr_text': '',
                    'trans_text': '',
                    'output': '',
                    'raw_response': {'error': f'会话启动失败: {msg}',
                                     'session_id': session_id},
                }
            logger.info(f'VolcAstAdapter: 会话启动成功(session_id={session_id})')

            # 4. 发送音频分片任务
            async def send_audio_chunks():
                try:
                    for i, chunk in enumerate(audio_chunks):
                        if i == 0 and timestamps['request_start'] is None:
                            timestamps['request_start'] = time.time()
                        chunk_req = self._build_translate_request(
                            session_id, 'Type_TaskRequest',
                            audio_chunk=chunk,
                            source_lang=source_lang, target_lang=target_lang,
                        )
                        await conn.send(chunk_req.SerializeToString())
                        await asyncio.sleep(0.1)
                    timestamps['request_end'] = time.time()
                    logger.info('VolcAstAdapter: 音频分片发送完成,请求结束会话')
                    finish_req = self._build_translate_request(
                        session_id, 'Type_FinishSession',
                        source_lang=source_lang, target_lang=target_lang,
                    )
                    await conn.send(finish_req.SerializeToString())
                except Exception as e:
                    logger.error(f'VolcAstAdapter: 发送音频分片失败: {e}')

            sender_task = asyncio.create_task(send_audio_chunks())

            # 5. 接收响应并处理结果
            while True:
                try:
                    raw = await conn.recv()
                except websockets.exceptions.ConnectionClosed:
                    logger.info('VolcAstAdapter: 连接已关闭')
                    break
                current_time = time.time()
                ev, _sid, _seq, asr_seg, trans_seg, data_bytes, _msg = \
                    self._parse_response(raw)

                # 会话状态判断
                if ev in (Type.SessionFailed, Type.SessionCanceled):
                    logger.error(f'VolcAstAdapter: 会话失败(event={ev})')
                    break
                if ev == Type.SessionFinished:
                    logger.info('VolcAstAdapter: 会话正常结束')
                    break

                # ASR 结果拼接
                if asr_seg:
                    asr_text_list.append(asr_seg)
                    if timestamps['asr_first_char'] is None:
                        timestamps['asr_first_char'] = current_time
                    timestamps['asr_last_char'] = current_time

                # 翻译结果拼接
                if trans_seg:
                    translated_text_list.append(trans_seg)
                    if timestamps['translate_first_char'] is None:
                        timestamps['translate_first_char'] = current_time
                    timestamps['translate_last_char'] = current_time

            # 等待发送任务完成
            await sender_task
        except Exception as e:
            logger.error(f'VolcAstAdapter: 翻译过程异常: {e}', exc_info=True)
            return {
                'asr_text': ' '.join(asr_text_list).strip(),
                'trans_text': ' '.join(translated_text_list).strip(),
                'output': '',
                'raw_response': {'error': str(e)},
            }
        finally:
            if conn:
                try:
                    await conn.close()
                except Exception:
                    pass

        # 6. 计算时延统计(保留到 raw_response)
        latency_stats = {}
        request_start = timestamps['request_start']
        request_end = timestamps['request_end']
        if request_start and request_end:
            latency_stats = {
                'request_start_time': time.strftime(
                    '%Y-%m-%d %H:%M:%S', time.localtime(request_start)),
                'request_end_time': time.strftime(
                    '%Y-%m-%d %H:%M:%S', time.localtime(request_end)),
                'asr_first_char_latency': (
                    round(timestamps['asr_first_char'] - request_start, 3)
                    if timestamps['asr_first_char'] else None),
                'translate_first_char_latency': (
                    round(timestamps['translate_first_char'] - request_start, 3)
                    if timestamps['translate_first_char'] else None),
                'asr_last_char_latency': (
                    round(timestamps['asr_last_char'] - request_end, 3)
                    if timestamps['asr_last_char'] else None),
                'translate_last_char_latency': (
                    round(timestamps['translate_last_char'] - request_end, 3)
                    if timestamps['translate_last_char'] else None),
            }
        elif request_start is None:
            latency_stats['error'] = '未记录到请求开始时间'
        else:
            latency_stats['error'] = '未记录到最后分片发送结束时间'

        full_asr = ' '.join(asr_text_list).strip()
        full_trans = ' '.join(translated_text_list).strip()

        return {
            'asr_text': full_asr,
            'trans_text': full_trans,
            'output': full_trans or full_asr,
            'raw_response': {
                'session_id': session_id,
                'latency_stats': latency_stats,
                'mode': self.mode,
                'source_lang': source_lang,
                'target_lang': target_lang,
            },
        }
