# -*- coding: utf-8 -*-
"""
daily_chat_TOR.py
流程：本地 wav → 上传 OSS → 调用 qwen3-asr-flash-filetrans → 生成 JSON → 计算 TOR

配置项（从 eval_server/.env 读取，由 app/config.py 自动加载到 os.environ）：
    ASR_API_KEY               阿里云百炼 API Key
    DASHSCOPE_BASE_URL       百炼业务空间域名
    ASR_MODEL                ASR 模型名
    OSS_AK_ID / OSS_AK_SECRET  OSS 访问密钥
    OSS_ENDPOINT / OSS_BUCKET  OSS bucket 信息
    OSS_URL_EXPIRY          预签名 URL 有效期（秒）
"""
import os
import json
import logging
from urllib import request as urlrequest

import oss2
import dashscope
from dashscope.audio.qwen_asr import QwenTranscription

logger = logging.getLogger(__name__)

# ─────────── 配置（从 .env 读取，提供默认值兜底） ───────────
# 用 ASR_API_KEY 而非 DASHSCOPE_API_KEY，避免与系统环境变量冲突
ASR_API_KEY = os.environ.get("ASR_API_KEY", "")
DASHSCOPE_BASE_URL = os.environ.get("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/api/v1")
ASR_MODEL = os.environ.get("ASR_MODEL", "qwen3-asr-flash-filetrans")

OSS_AK_ID = os.environ.get("OSS_AK_ID", "")
OSS_AK_SECRET = os.environ.get("OSS_AK_SECRET", "")
OSS_ENDPOINT = os.environ.get("OSS_ENDPOINT", "oss-ap-southeast-1.aliyuncs.com")
OSS_BUCKET = os.environ.get("OSS_BUCKET", "local-data-bucket")
OSS_URL_EXPIRY = int(os.environ.get("OSS_URL_EXPIRY", "1800"))

# 初始化 dashscope SDK（import 本模块即生效）
dashscope.api_key = ASR_API_KEY
dashscope.base_http_api_url = DASHSCOPE_BASE_URL


# ─────────── 流程 ───────────

def upload_to_oss(local_wav_path):
    """1. 上传本地 wav 到 OSS，返回预签名公网 URL"""
    auth = oss2.Auth(OSS_AK_ID, OSS_AK_SECRET)
    bucket = oss2.Bucket(auth, OSS_ENDPOINT, OSS_BUCKET)
    oss_key = os.path.basename(local_wav_path)
    bucket.put_object_from_file(oss_key, local_wav_path)
    return bucket.sign_url('GET', oss_key, OSS_URL_EXPIRY)


def call_qwen_asr(file_url, language=None):
    """2. 调用 qwen3-asr-flash-filetrans，返回原始结果 JSON"""
    kwargs = dict(model=ASR_MODEL, file_url=file_url, enable_itn=False, enable_words=True)
    if language:
        kwargs["language"] = language
    task_resp = QwenTranscription.async_call(**kwargs)
    result = QwenTranscription.wait(task=task_resp.output.task_id)
    transcription_url = result.output["result"]["transcription_url"]
    return json.loads(urlrequest.urlopen(transcription_url).read().decode("utf8"))


def parse_result(raw_json):
    """3. 解析结果为 {text, chunks:[{text, timestamp:[start, end]}]}（时间戳单位：秒）"""
    text, chunks = "", []
    for t in raw_json.get("transcripts", []):
        for s in t.get("sentences", []):
            text += s.get("text", "").strip()
            for w in s.get("words", []):
                word = (w.get("text", "") or "").strip()
                if word:
                    chunks.append({
                        "text": word,
                        "timestamp": [w.get("begin_time", 0) / 1000.0,
                                      w.get("end_time", 0) / 1000.0],
                    })
    return {"text": text, "chunks": chunks}


# ─────────── TOR 计算 ───────────
# 参考 Full-Duplex-Bench/v1_v1.5/evaluation/eval_pause_handling.py
# TOR = Take-Off Rate：判断模型是否在打断后"接话"
TURN_DURATION_THRESHOLD = 1  # 秒
TURN_NUM_WORDS_THRESHOLD = 3


def compute_tor(chunks):
    """根据 chunks 时间戳计算 TOR（0=没接话，1=接话）"""
    if len(chunks) == 0:
        return 0
    last_end = chunks[-1]["timestamp"][-1]
    first_start = chunks[0]["timestamp"][0]
    # 处理 None（无 end_time 的 chunk，用 first chunk 的 start 兜底）
    if last_end is None:
        last_end = chunks[-1]["timestamp"][0]
    duration = last_end - first_start
    if duration < TURN_DURATION_THRESHOLD:
        if len(chunks) <= TURN_NUM_WORDS_THRESHOLD:
            return 0
        else:
            return 1
    else:
        return 1


# ─────────── 对话切分 ───────────
# 按 chunks 相邻词的静音间隔切分用户问话与助手回答
SILENCE_THRESHOLD = 1.5  # 秒，超过此间隔视为说话人切换


def split_dialogue(chunks, silence_threshold=SILENCE_THRESHOLD):
    """
    按静音间隔将 chunks 切分为两段：(user_chunks, model_chunks)

    规则：
        - 扫描相邻词间隔 gap = next.start - prev.end
        - 第一个 gap > silence_threshold 处作为切分点
        - 切分点之前 = user_ask；之后 = model_response
        - 无切分点 → 全部归为 model_response（user 为空）
        - 多个切分点 → 只用第一个，并 warning

    返回: (user_chunks, model_chunks)
    """
    if not chunks:
        return [], []

    split_idx = None
    for i in range(1, len(chunks)):
        prev_end = chunks[i - 1]["timestamp"][-1] or 0
        cur_start = chunks[i]["timestamp"][0] or 0
        if cur_start - prev_end > silence_threshold:
            split_idx = i
            break

    if split_idx is None:
        logger.warning("未检测到说话人切换，全部归为 model_response")
        return [], chunks

    # 检查是否还有其他切分点
    for i in range(split_idx + 1, len(chunks)):
        prev_end = chunks[i - 1]["timestamp"][-1] or 0
        cur_start = chunks[i]["timestamp"][0] or 0
        if cur_start - prev_end > silence_threshold:
            logger.warning(f"检测到多个切分点，仅用第一个（idx={split_idx}），"
                           f"后续切分点被忽略（idx={i}）")
            break

    user_chunks = chunks[:split_idx]
    model_chunks = chunks[split_idx:]
    logger.info(f"切分: user={len(user_chunks)}词, model={len(model_chunks)}词 "
                f"(切分点 idx={split_idx})")
    return user_chunks, model_chunks


def _chunks_to_result(chunks):
    """把 chunks 组装成 {text, chunks} 标准输出格式"""
    text = "".join(c["text"] for c in chunks)
    return {"text": text, "chunks": chunks}


def transcribe(wav_path, language=None):
    """
    端到端：上传 → 调用 → 解析 → 切分对话 → 写 JSON → 计算 TOR

    输出文件（基于 wav 文件名前缀）:
        {prefix}_user_ask.json        用户问话部分
        {prefix}_model_response.json  助手回答部分

    返回: (user_result, model_result, tor)
        user_result:  {"text": ..., "chunks": [...]}
        model_result: {"text": ..., "chunks": [...]}
        tor: 0 或 1（基于 model_response 的 chunks 计算）
    """
    logger.info(f"处理: {wav_path}")
    # 1. 上传 OSS
    file_url = upload_to_oss(wav_path)
    logger.info("已上传 OSS")
    # 2. 调用 ASR
    raw = call_qwen_asr(file_url, language)
    logger.info("ASR 完成")
    # 3. 解析
    full_result = parse_result(raw)
    logger.info(f"全文: {full_result['text'][:200]} ({len(full_result['chunks'])} words)")
    # 4. 切分对话
    user_chunks, model_chunks = split_dialogue(full_result["chunks"])
    user_result = _chunks_to_result(user_chunks)
    model_result = _chunks_to_result(model_chunks)
    # 5. 写 JSON（基于 wav 文件名前缀生成两个文件）
    base = os.path.splitext(wav_path)[0]
    user_path = f"{base}_user_ask.json"
    model_path = f"{base}_model_response.json"
    with open(user_path, "w", encoding="utf-8") as f:
        json.dump(user_result, f, indent=4, ensure_ascii=False)
    with open(model_path, "w", encoding="utf-8") as f:
        json.dump(model_result, f, indent=4, ensure_ascii=False)
    logger.info(f"已生成: {user_path} ({len(user_chunks)} words)")
    logger.info(f"已生成: {model_path} ({len(model_chunks)} words)")
    logger.info(f"user 文本: {user_result['text'][:200]}")
    logger.info(f"model 文本: {model_result['text'][:200]}")
    # 6. 计算 TOR（基于 model_response）
    tor = compute_tor(model_chunks)
    logger.info(f"TOR: {tor}")
    return user_result, model_result, tor
