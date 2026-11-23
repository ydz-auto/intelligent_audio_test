# -*- coding: utf-8 -*-
"""
asr_adapter.py
流程：本地 wav → 调用远程 ASR 服务（ModelScope Paraformer-large-vad-punc） → 生成 JSON

ASR 推理部署在独立的 ASR 主机上（asr_server.py），本机只负责上传 wav 文件
并接收识别结果，避免 ASR 推理占用 CPU 影响自动化测试主机的时延测量。

配置项（从 eval_server/.env 读取，由 app/config.py 自动加载到 os.environ）：
    ASR_SERVER_URL    远程 ASR 服务地址（默认 http://127.0.0.1:10095）
                      在 .env 中改为实际 ASR 主机 IP，例如 http://192.168.1.50:10095
    ASR_TIMEOUT       请求超时秒数（默认 180）
    ASR_MAX_RETRIES   超时/连接类错误的额外重试次数（默认 1，即最多尝试 2 次）
    ASR_RESAMPLE_ENABLE  上传前是否用 ffmpeg 转 16k 单声道（默认 true）
                      原始 48k 双声道 wav 经 SSH 隧道（~3Mbps）上传就要 30s+，
                      降采样后体积约 1/6，显著降低超时概率
    ASR_JSON_OUTPUT_DIR  ASR 结果 JSON 的本地保存根目录（默认与 wav 同目录）
                         若设置，JSON 会保存到 {ASR_JSON_OUTPUT_DIR}/pcm_case/pcm_case/{case_id}/{session_id}/ 下
"""
import os
import json
import logging
import shutil
import subprocess
import tempfile
import time
import threading
from contextlib import contextmanager
from pathlib import Path

# ─── 加载 .env 到 os.environ（参考 app/config.py，让本模块可独立运行） ───
_env_path = Path(__file__).resolve().parent.parent.parent / '.env'
if _env_path.exists():
    with open(_env_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())

import requests

logger = logging.getLogger(__name__)

# ─────────── 配置（从 .env 读取，提供默认值兜底） ───────────
ASR_SERVER_URL = os.environ.get("ASR_SERVER_URL", "http://127.0.0.1:10095").rstrip("/")
ASR_TIMEOUT = int(os.environ.get("ASR_TIMEOUT", "180"))
ASR_JSON_OUTPUT_DIR = os.environ.get("ASR_JSON_OUTPUT_DIR", "").strip()

# 超时/连接断开后的额外重试次数（仅对网络类错误重试，HTTP 错误码不重试）
ASR_MAX_RETRIES = int(os.environ.get("ASR_MAX_RETRIES", "1"))
ASR_RETRY_DELAY = float(os.environ.get("ASR_RETRY_DELAY", "2"))

# 上传前降采样：ASR 只用到 16k 单声道，原始 48k 双声道 wav 体积大 6 倍，
# 经低带宽 SSH 隧道传输是超时的主要耗时来源
ASR_RESAMPLE_ENABLE = os.environ.get(
    "ASR_RESAMPLE_ENABLE", "true").strip().lower() not in ("0", "false", "no", "off")
ASR_RESAMPLE_ARGS = os.environ.get("ASR_RESAMPLE_ARGS", "-ac 1 -ar 16000").strip()
ASR_RESAMPLE_TIMEOUT = int(os.environ.get("ASR_RESAMPLE_TIMEOUT", "180"))

# ASR 并发限制：ASR 服务器是单实例，高并发时容易过载超时
# 用信号量限制同时调用的数量，避免压垮 ASR 服务
ASR_MAX_CONCURRENCY = int(os.environ.get("ASR_MAX_CONCURRENCY", "10"))
_asr_semaphore = threading.Semaphore(ASR_MAX_CONCURRENCY)


def _asr_runtime():
    """运行时 ASR 配置（系统设置优先，缺省回落 env）：返回 (base_url, timeout)。"""
    from app.runtime_config import asr_settings
    return asr_settings(ASR_SERVER_URL, ASR_TIMEOUT)


def _build_json_save_path(wav_path):
    """根据 wav 路径构造 ASR 结果 JSON 的保存路径。

    若 wav_path 中包含 ``pcm_case`` 目录层级，则提取
    ``pcm_case/pcm_case/{case_id}/{session_id}`` 部分，拼接到
    ``ASR_JSON_OUTPUT_DIR`` 下保存。

    若未配置 ``ASR_JSON_OUTPUT_DIR`` 或路径中无 ``pcm_case``，
    则回退到 wav 同目录同名 .json（旧行为）。
    """
    wav_path = os.path.normpath(wav_path)
    wav_basename = os.path.basename(wav_path)
    json_name = os.path.splitext(wav_basename)[0] + '.json'

    if not ASR_JSON_OUTPUT_DIR:
        # 未配置输出根目录：回退到 wav 同目录
        return os.path.join(os.path.dirname(wav_path), json_name)

    # 尝试从 wav_path 中提取 pcm_case/pcm_case/{case_id}/{session_id} 层级
    parts = wav_path.split(os.sep)
    # 规范化分隔符，统一处理 /
    parts = [p for p in parts if p]

    # 找到第一个 pcm_case 的位置
    pcm_idx = None
    for i, p in enumerate(parts):
        if p.lower() == 'pcm_case':
            pcm_idx = i
            break

    if pcm_idx is not None:
        # 从 pcm_case 开始取到倒数第二级（排除文件名所在目录和文件名本身）
        # parts: [..., 'pcm_case', 'pcm_case', '{case_id}', '{session_id}', 'filename.wav']
        # 需要提取: pcm_case, pcm_case, {case_id}, {session_id}
        hierarchy_parts = parts[pcm_idx:-1]  # 去掉最后的文件名
    else:
        # 没有 pcm_case 层级，用 wav 所在目录名
        hierarchy_parts = [os.path.basename(os.path.dirname(wav_path))]

    save_dir = os.path.join(ASR_JSON_OUTPUT_DIR, *hierarchy_parts)
    os.makedirs(save_dir, exist_ok=True)
    return os.path.join(save_dir, json_name)


def _save_asr_json(result, wav_path):
    """将 ASR 结果保存为 JSON 文件，目录结构保留 pcm_case/pcm_case/{case_id}/{session_id}。"""
    json_path = _build_json_save_path(wav_path)
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    logger.info(f"ASR 结果已保存: {json_path}")
    return json_path


# ─────────── 上传准备与请求 ───────────

@contextmanager
def _upload_file(wav_path):
    """产出 (fileobj, filename)。

    启用 ASR_RESAMPLE_ENABLE 且系统有 ffmpeg 时，先把音频转成 16k 单声道
    再上传（体积约 1/6）；ffmpeg 不可用或转码失败时回退为原始字节直传，
    不影响评估流程。
    """
    from app.utils.audio_source import open_stream, basename

    name = basename(wav_path) or 'audio.wav'
    ffmpeg = shutil.which("ffmpeg") if ASR_RESAMPLE_ENABLE else None
    tmpdir = None
    resampled = None

    if ffmpeg:
        try:
            tmpdir = tempfile.mkdtemp(prefix="asr_upload_")
            suffix = os.path.splitext(name)[1] or '.wav'
            src = os.path.join(tmpdir, 'src' + suffix)
            dst = os.path.join(tmpdir, 'resampled.wav')

            stream = open_stream(wav_path)
            try:
                with open(src, 'wb') as f:
                    shutil.copyfileobj(stream, f, 1024 * 1024)
            finally:
                stream.close()

            proc = subprocess.run(
                [ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-i', src,
                 *ASR_RESAMPLE_ARGS.split(), '-c:a', 'pcm_s16le', dst],
                capture_output=True, timeout=ASR_RESAMPLE_TIMEOUT,
            )
            if proc.returncode == 0 and os.path.isfile(dst) and os.path.getsize(dst) > 0:
                resampled = dst
            else:
                logger.warning(f"降采样失败，回退原始上传 {wav_path}: "
                               f"{proc.stderr.decode('utf-8', 'ignore')[-200:]}")
        except Exception as e:
            logger.warning(f"降采样异常，回退原始上传 {wav_path}: {e}")

    try:
        if resampled:
            with open(resampled, 'rb') as f:
                yield f, os.path.splitext(name)[0] + '_16k.wav'
        else:
            stream = open_stream(wav_path)
            try:
                yield stream, name
            finally:
                stream.close()
    finally:
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)


def _post_wav(url, wav_path, timeout, label):
    """上传 wav 到 ASR 端点，返回 (result_dict, elapsed)。

    仅对超时/连接类错误做有限重试（ASR_MAX_RETRIES）；HTTP 非 200 直接抛错，
    避免服务端明确报错时重复上传。
    """
    last_exc = None
    resp = None
    elapsed = 0.0
    attempts = ASR_MAX_RETRIES + 1

    for attempt in range(1, attempts + 1):
        with _asr_semaphore:
            with _upload_file(wav_path) as (stream, filename):
                files = {"file": (filename, stream, "audio/wav")}
                t0 = time.time()
                try:
                    resp = requests.post(url, files=files, timeout=timeout)
                    elapsed = time.time() - t0
                except (requests.exceptions.Timeout,
                        requests.exceptions.ConnectionError) as e:
                    last_exc = e
                    elapsed = time.time() - t0
                    resp = None
                    logger.warning(
                        f"{label} 第 {attempt}/{attempts} 次失败 ({elapsed:.1f}s): {e}")
        if resp is not None:
            break
        if attempt < attempts:
            time.sleep(ASR_RETRY_DELAY)

    if resp is None:
        raise last_exc
    if resp.status_code != 200:
        raise RuntimeError(f"{label} 返回错误 {resp.status_code}: {resp.text}")
    return resp.json(), elapsed


# ─────────── 流程 ───────────

def call_modelscope_asr(wav_path, language=None):
    """
    调用远程 ASR 服务（asr_server.py）进行 ASR 推理。

    Args:
        wav_path: 本地 wav 文件路径，或 oss:// 对象存储引用（内存直读，不落盘）
        language: 保留参数兼容性（Paraformer 中文模型自动识别，忽略该参数）

    Returns:
        服务端已解析好的结果 dict：
            {"text": "识别全文", "chunks": [{"text": "字", "timestamp": [start_s, end_s]}, ...]}
        时间戳单位为秒。

        为兼容老调用方，本函数返回 [result] 形式（长度 1 的列表），让 parse_result 能继续工作。
    """
    from app.utils.audio_source import exists
    if not wav_path or not exists(wav_path):
        logger.error(f"wav 文件不存在: {wav_path}")
        return [{'text': '', 'chunks': []}]

    asr_base, asr_timeout = _asr_runtime()
    url = f"{asr_base}/asr"
    logger.info(f"调用远程 ASR: {url}  wav={wav_path}")

    result, elapsed = _post_wav(url, wav_path, asr_timeout, "远程 ASR")
    from app.utils.audio_metadata import audio_metadata
    result.update(audio_metadata(wav_path, asr_status='success'))
    logger.info(f"远程 ASR 完成 ({elapsed:.2f}s): {result.get('text', '')[:80]}")

    # 落盘：保存 ASR 结果 JSON（目录结构保留 pcm_case/pcm_case/{case_id}/{session_id}）
    _save_asr_json(result, wav_path)

    # 包装成 [result]，让 parse_result(raw) 能继续工作（raw[0] 取出 result）
    return [result]


def call_modelscope_asr_word(wav_path, language=None):
    """
    调用远程 ASR 服务的 /asr_word 端点（Paraformer 词级时间戳）。

    用于 false_takeover 等需要词级粒度的指标。

    Returns:
        [result] 形式，result = {"text": "...", "chunks": [{"text": "字", "timestamp": [start_s, end_s]}, ...]}
    """
    from app.utils.audio_source import exists
    if not wav_path or not exists(wav_path):
        logger.error(f"wav 文件不存在: {wav_path}")
        return [{'text': '', 'chunks': []}]

    asr_base, asr_timeout = _asr_runtime()
    url = f"{asr_base}/asr_word"
    logger.info(f"调用远程 ASR(词级): {url}  wav={wav_path}")

    result, elapsed = _post_wav(url, wav_path, asr_timeout, "远程 ASR(词级)")
    from app.utils.audio_metadata import audio_metadata
    result.update(audio_metadata(wav_path, asr_status='success'))
    logger.info(f"远程 ASR(词级) 完成 ({elapsed:.2f}s, {len(result.get('chunks', []))} 字): {result.get('text', '')[:80]}")

    # 落盘：保存词级 ASR 结果 JSON（目录结构保留 pcm_case/pcm_case/{case_id}/{session_id}）
    _save_asr_json(result, wav_path)

    return [result]


def parse_result(raw_res):
    """
    解析 ASR 结果为 {text, chunks:[{text, timestamp:[start, end]}]}（时间戳单位：秒）。

    远程服务端已经返回解析好的结构，本函数做透传，保持与旧版本接口兼容。
    """
    item = raw_res[0]
    return {
        "text": item.get("text", ""),
        "chunks": item.get("chunks", []),
        "audio_duration_s": item.get("audio_duration_s"),
        "duration_source": item.get("duration_source"),
        "asr_status": item.get("asr_status", "unknown"),
        "voice_activity_status": item.get("voice_activity_status", "not_measured"),
    }
