import asyncio
import uuid
import os
from pathlib import Path
from dataclasses import dataclass
import logging
from typing import Optional, List, Tuple
import websockets
from websockets import Headers
import sys
import time
import json
from google.protobuf.json_format import MessageToDict
from websockets.legacy.exceptions import InvalidStatusCode

# 获取当前脚本所在目录，添加protobuf生成模块路径
current_dir = os.path.dirname(os.path.abspath(__file__))
protogen_dir = os.path.join(current_dir, "python_protogen")
sys.path.append(protogen_dir)

# 导入protobuf生成的模块（基于真实proto结构）
from products.understanding.ast.ast_service_pb2 import TranslateRequest, ReqParams, TranslateResponse
from common.events_pb2 import Type


# Configuration：API连接配置类
@dataclass
class Config:
    ws_url: str
    app_key: str
    access_key: str
    resource_id: str


# Audio：音频信息类
@dataclass
class Audio:
    format: str = None
    rate: int = None
    bits: Optional[int] = None
    channel: Optional[int] = None
    binary_data: Optional[bytes] = None


# TranslateRequestData：请求数据封装类
@dataclass
class TranslateRequestData:
    session_id: str
    event: str
    source_audio: Optional[Audio] = None
    target_audio: Optional[Audio] = None
    mode: Optional[str] = None
    source_language: Optional[str] = None
    target_language: Optional[str] = None


# TranslateResponseData：响应数据封装类
@dataclass
class TranslateResponseData:
    event: int  # 改为int类型（protobuf枚举原始值）
    session_id: str
    sequence: int
    text: str
    data: bytes
    spk_chg: bool
    message: str = None


# ProcessResult：统一返回结果类（ASR+翻译+时延）
@dataclass
class ProcessResult:
    asr_text: str
    translated_text: str
    latency_stats: dict


async def read_audio_chunks(audio_path: str, chunk_size: int) -> List[bytes]:
    """读取音频文件为固定大小分片（100ms/分片）"""
    chunks = []
    try:
        with open(audio_path, 'rb') as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                chunks.append(chunk)
        return chunks
    except Exception as e:
        logging.error(f"读取音频文件失败：{e}")
        return []


async def send_request(ws, request: TranslateRequestData):
    """构建并发送WebSocket请求（基于proto结构，修复Python关键字语法错误）"""
    request_data = TranslateRequest()

    # 请求元信息
    if request.session_id:
        request_data.request_meta.SessionID = request.session_id

    # 事件类型映射（根据event.proto的枚举数值）
    event_map = {
        "Type_StartSession": Type.StartSession,  # 对应数值100
        "Type_TaskRequest": Type.TaskRequest,  # 对应数值200
        "Type_FinishSession": Type.FinishSession  # 对应数值102
    }
    # 修复：用数值0替代Type.None（避免Python关键字语法错误）
    # 0是event.proto中Type.None的枚举值
    request_data.event = event_map.get(request.event, 0)

    # 用户信息
    request_data.user.uid = "ast_py_client"
    request_data.user.did = "ast_py_client"

    # 源音频配置（强制16k、16bit、单声道WAV，API要求）
    request_data.source_audio.format = "wav"
    request_data.source_audio.rate = 16000
    request_data.source_audio.bits = 16
    request_data.source_audio.channel = 1
    if request.source_audio and request.source_audio.binary_data:
        request_data.source_audio.binary_data = request.source_audio.binary_data

    # 目标音频配置（WAV格式，与源音频参数一致）
    request_data.target_audio.format = "wav"
    request_data.target_audio.rate = 16000
    request_data.target_audio.bits = 16
    request_data.target_audio.channel = 1

    # 翻译核心参数（s2s模式：语音转语音）
    request_data.request.mode = "s2s"
    request_data.request.source_language = "zh"  # 源语言：中文
    request_data.request.target_language = "en"  # 目标语言：英文

    # 发送请求
    await ws.send(request_data.SerializeToString())


async def receive_message(ws) -> Tuple[TranslateResponseData, str, str]:
    """接收响应并分离ASR/翻译结果（修复int无name属性，忽略无文本事件）"""
    response = await ws.recv()
    Response_data = TranslateResponse()
    Response_data.ParseFromString(response)

    asr_text = ""
    translated_text = ""
    current_event = Response_data.event  # int类型（如451、651、654）

    # 第一步：忽略无文本的状态类事件（从event.proto提取）
    IGNORE_EVENT_TYPES = {
        250,  # 会话状态/心跳事件（无有效数据）
        650,  # SourceSubtitleStart（源语言字幕开始）
        652,  # SourceSubtitleEnd（源语言字幕结束）
        653,  # TranslationSubtitleStart（翻译字幕开始）
        655  # TranslationSubtitleEnd（翻译字幕结束）
    }
    if current_event in IGNORE_EVENT_TYPES:
        logging.debug(f"忽略状态事件（event={current_event}）：无文本数据")
        response_data = TranslateResponseData(
            event=current_event,
            session_id=Response_data.response_meta.SessionID if Response_data.response_meta else "",
            sequence=Response_data.response_meta.Sequence if Response_data.response_meta else 0,
            text="",
            data=Response_data.data,
            spk_chg=Response_data.spk_chg,
            message=""
        )
        return response_data, "", ""

    # 第二步：按事件数值区分ASR和翻译结果（基于event.proto）
    ASR_EVENT_TYPES = {450, 451, 459, 651}  # ASR相关事件
    TRANSLATE_EVENT_TYPES = {654}  # 翻译相关事件
    USAGE_EVENT_TYPE = 154  # 用量统计事件

    if current_event in ASR_EVENT_TYPES:
        # ASR事件：text字段为原文
        asr_text = Response_data.text.strip() if Response_data.text else ""
        logging.debug(f"ASR事件（event={current_event}）：{asr_text[:50]}...")
    elif current_event in TRANSLATE_EVENT_TYPES:
        # 翻译事件：text字段为译文
        translated_text = Response_data.text.strip() if Response_data.text else ""
        logging.debug(f"翻译事件（event={current_event}）：{translated_text[:50]}...")
    elif current_event == USAGE_EVENT_TYPE:
        # 用量统计事件：仅日志输出，不参与结果拼接
        response_dict = MessageToDict(Response_data)
        logging.debug(f"用量统计事件（event={current_event}）：{json.dumps(response_dict, ensure_ascii=False)[:100]}...")
        asr_text = ""
        translated_text = ""

    # 构造响应数据
    response_data = TranslateResponseData(
        event=current_event,
        session_id=Response_data.response_meta.SessionID if Response_data.response_meta else "",
        sequence=Response_data.response_meta.Sequence if Response_data.response_meta else 0,
        text=translated_text,
        data=Response_data.data,
        spk_chg=Response_data.spk_chg,
        message=Response_data.response_meta.Message if (
                    Response_data.response_meta and Response_data.response_meta.Message) else ""
    )
    return response_data, asr_text, translated_text


async def build_http_headers(conf: Config, conn_id: str) -> Headers:
    """构建API请求头（包含鉴权信息）"""
    headers = Headers({
        "X-Api-App-Key": conf.app_key,
        "X-Api-Access-Key": conf.access_key,
        "X-Api-Resource-Id": conf.resource_id,
        "X-Api-Connect-Id": conn_id
    })
    return headers


async def translate_v4(conf: Config, audio_path: str, audio_filename: str, n: int,
                       out_audio_dir: str = "translated_audio") -> ProcessResult:
    """核心翻译函数：处理音频→ASR→翻译→TTS→结果保存→时延统计"""
    # 初始化时间戳和结果容器
    timestamps = {
        "request_start": None,  # 第一个音频分片发送时间
        "request_end": None,  # 最后一个分片发送结束时间
        "asr_first_char": None,  # ASR首字返回时间
        "asr_last_char": None,  # ASR尾字返回时间
        "translate_first_char": None,  # 翻译首字返回时间
        "translate_last_char": None,  # 翻译尾字返回时间
        "tts_first_char": None,  # TTS首帧返回时间
        "tts_last_char": None  # TTS尾帧返回时间
    }
    asr_text_list = []
    translated_text_list = []
    recv_audio = bytearray()

    # 1. 读取音频文件
    audio_chunks = await read_audio_chunks(audio_path, 3200)  # 3200字节=100ms（16k/16bit/单声道）
    if not audio_chunks:
        logging.error(f"音频文件{audio_filename}读取失败或为空")
        return ProcessResult(
            asr_text="（音频读取失败）",
            translated_text="（音频读取失败）",
            latency_stats={"error": "音频读取失败或为空"}
        )
    logging.info(f"成功读取音频：{audio_filename}，共{len(audio_chunks)}个分片")

    # 2. 连接WebSocket API
    conn = None
    try:
        conn_id = str(uuid.uuid4())
        headers = await build_http_headers(conf, conn_id)
        conn = await websockets.connect(
            conf.ws_url,
            additional_headers=headers,
            max_size=1000000000,  # 1GB最大接收大小
            ping_interval=None  # 禁用ping（API长连接优化）
        )
        log_id = conn.response.headers.get('X-Tt-Logid', '未知')
        logging.info(f"连接API成功（log_id={log_id}）")
    except Exception as e:
        logging.error(f"连接API失败：{e}")
        return ProcessResult(
            asr_text="（API连接失败）",
            translated_text="（API连接失败）",
            latency_stats={"error": f"API连接失败：{str(e)}"}
        )

    # 3. 启动会话
    session_id = str(uuid.uuid4())
    start_request = TranslateRequestData(
        session_id=session_id,
        event="Type_StartSession",
        source_audio=Audio(format="wav", rate=16000, bits=16, channel=1),
        target_audio=Audio(format="wav", rate=16000, bits=16, channel=1)
    )
    try:
        await send_request(conn, start_request)
        resp, _, _ = await receive_message(conn)
        if resp.event != Type.SessionStarted:  # Type.SessionStarted数值为150
            logging.error(f"会话启动失败（log_id={log_id}）：{resp.message}")
            await conn.close()
            return ProcessResult(
                asr_text="（会话启动失败）",
                translated_text="（会话启动失败）",
                latency_stats={"error": f"会话启动失败：{resp.message}"}
            )
        logging.info(f"会话启动成功（session_id={session_id}）")
    except Exception as e:
        logging.error(f"会话启动异常：{e}")
        await conn.close()
        return ProcessResult(
            asr_text="（会话启动异常）",
            translated_text="（会话启动异常）",
            latency_stats={"error": f"会话启动异常：{str(e)}"}
        )

    # 4. 发送音频分片任务
    async def send_audio_chunks():
        nonlocal timestamps
        try:
            for i, chunk in enumerate(audio_chunks):
                # 记录第一个分片发送时间（请求开始时间）
                if i == 0 and timestamps["request_start"] is None:
                    timestamps["request_start"] = time.time()
                    logging.info(f"开始发送音频分片，请求开始时间：{timestamps['request_start']:.6f}")

                # 构建分片请求
                chunk_request = TranslateRequestData(
                    session_id=session_id,
                    event="Type_TaskRequest",
                    source_audio=Audio(binary_data=chunk)
                )
                await send_request(conn, chunk_request)
                await asyncio.sleep(0.1)  # 控制发送速率（与分片时长匹配）

            # 新增：记录最后一个分片发送结束时间（request_end）
            timestamps["request_end"] = time.time()
            logging.info(f"所有音频分片发送完成，最后分片结束时间：{timestamps['request_end']:.6f}")

            # 发送结束会话请求
            finish_request = TranslateRequestData(
                session_id=session_id,
                event="Type_FinishSession"
            )
            await send_request(conn, finish_request)
            logging.info("音频分片发送完成，已请求结束会话")
        except Exception as e:
            logging.error(f"发送音频分片失败：{e}")

    # 启动发送任务
    sender_task = asyncio.create_task(send_audio_chunks())

    # 5. 接收响应并处理结果
    try:
        while True:
            resp, asr_segment, translate_segment = await receive_message(conn)
            current_time = time.time()

            # 日志输出响应概览（仅输出事件数值，无name属性调用）
            has_valid_data = bool(asr_segment.strip() or translate_segment.strip() or len(resp.data) > 0)
            if has_valid_data:
                logging.info(
                    f"接收有效响应（event={resp.event}, seq={resp.sequence}）："
                    f"ASR分片={asr_segment[:30]}..., 翻译分片={translate_segment[:30]}..., "
                    f"音频长度={len(resp.data)}"
                )
            else:
                logging.debug(
                    f"接收无效响应（event={resp.event}, seq={resp.sequence}）：无有效文本/音频"
                )

            # 会话状态判断（基于event.proto数值）
            if resp.event in [Type.SessionFailed, Type.SessionCanceled]:  # 153、151
                logging.error(f"会话失败（log_id={log_id}）：{resp.message}")
                break
            if resp.event == Type.SessionFinished:  # 152
                logging.info("会话正常结束，停止接收响应")
                break

            # 6. 结果拼接+时间戳记录
            # ASR结果处理
            if asr_segment and asr_segment.strip():
                asr_text_list.append(asr_segment)
                if timestamps["asr_first_char"] is None:
                    timestamps["asr_first_char"] = current_time
                timestamps["asr_last_char"] = current_time  # 持续更新到最后一个分片

            # 翻译结果处理
            if translate_segment and translate_segment.strip():
                translated_text_list.append(translate_segment)
                if timestamps["translate_first_char"] is None:
                    timestamps["translate_first_char"] = current_time
                timestamps["translate_last_char"] = current_time  # 持续更新到最后一个分片

            # TTS音频处理
            if len(resp.data) > 0:
                recv_audio.extend(resp.data)
                if timestamps["tts_first_char"] is None:
                    timestamps["tts_first_char"] = current_time
                timestamps["tts_last_char"] = current_time  # 持续更新到最后一个帧

    except Exception as e:
        logging.error(f"接收响应异常：{e}", exc_info=True)
    finally:
        # 确保发送任务完成+连接关闭
        await sender_task
        if conn:
            await conn.close()
        logging.info(f"API连接已关闭（session_id={session_id}）")

    # 7. 计算时延统计（单位：秒，保留3位小数）
    latency_stats = {}
    request_start = timestamps["request_start"]
    request_end = timestamps["request_end"]

    if request_start and request_end:
        # 格式化时间字符串（供日志和输出）
        request_start_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(request_start))
        request_end_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(request_end))

        # 时延计算（保留3位小数）
        latency_stats = {
            # 基础时间信息
            "request_start_time": request_start_time,
            "request_end_time": request_end_time,  # 新增：最后分片发送结束时间
            # 首字时延（仍以request_start为基准）
            "asr_first_char_latency": round(timestamps["asr_first_char"] - request_start, 3) if timestamps[
                "asr_first_char"] else None,
            "translate_first_char_latency": round(timestamps["translate_first_char"] - request_start, 3) if timestamps[
                "translate_first_char"] else None,
            "tts_first_char_latency": round(timestamps["tts_first_char"] - request_start, 3) if timestamps[
                "tts_first_char"] else None,
            # 尾字时延（改为以request_end为基准）
            "asr_last_char_latency": round(timestamps["asr_last_char"] - request_end, 3) if timestamps[
                "asr_last_char"] else None,
            "translate_last_char_latency": round(timestamps["translate_last_char"] - request_end, 3) if timestamps[
                "translate_last_char"] else None,
            "tts_last_char_latency": round(timestamps["tts_last_char"] - request_end, 3) if timestamps[
                "tts_last_char"] else None,
        }
    elif request_start is None:
        latency_stats["error"] = "未记录到请求开始时间"
    else:
        latency_stats["error"] = "未记录到最后分片发送结束时间"

    # 8. 拼接完整结果
    full_asr_text = ' '.join(asr_text_list).strip() if asr_text_list else "（无ASR结果）"
    full_translated_text = ' '.join(translated_text_list).strip() if translated_text_list else "（无翻译结果）"

    # 9. 保存翻译后WAV音频
    if recv_audio:
        os.makedirs(out_audio_dir, exist_ok=True)
        audio_stem = Path(audio_filename).stem
        wav_save_path = Path(out_audio_dir) / f"{audio_stem}_fanyi_seed2.wav"
        try:
            with open(wav_save_path, 'wb') as f:
                f.write(recv_audio)
            logging.info(f"翻译音频已保存：{wav_save_path}")
        except Exception as e:
            logging.error(f"保存翻译音频失败：{e}")
    else:
        logging.error("未接收任何TTS音频数据")

    # 10. 输出时延统计日志
    logging.info(f"\n【{audio_filename} 完整时延统计】")
    for key, value in latency_stats.items():
        if key in ["request_start_time", "request_end_time"]:
            logging.info(f"{key.replace('_', ' ')}：{value}")
        elif key != "error" and value is not None:
            if "first_char" in key:
                logging.info(f"{key.replace('_', ' ')}（相对request_start）：{value} 秒")
            elif "last_char" in key:
                logging.info(f"{key.replace('_', ' ')}（相对request_end）：{value} 秒")
        elif key == "error":
            logging.error(f"时延统计错误：{value}")
        else:
            logging.info(f"{key.replace('_', ' ')}：无数据")

    return ProcessResult(
        asr_text=full_asr_text,
        translated_text=full_translated_text,
        latency_stats=latency_stats
    )
