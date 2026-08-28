# -*- coding: utf-8 -*-
"""
ASR_JSON.py
流程：本地 wav → 调用远程 ASR 服务（ModelScope Paraformer-large-vad-punc） → 生成 JSON

ASR 推理部署在独立的 ASR 主机上（asr_server.py），本机只负责上传 wav 文件
并接收识别结果，避免 ASR 推理占用 CPU 影响自动化测试主机的时延测量。

配置项（从 eval_server/.env 读取，由 app/config.py 自动加载到 os.environ）：
    ASR_SERVER_URL    远程 ASR 服务地址（默认 http://127.0.0.1:10095）
                      在 .env 中改为实际 ASR 主机 IP，例如 http://192.168.1.50:10095
    ASR_TIMEOUT       请求超时秒数（默认 120）
    ASR_JSON_OUTPUT_DIR  ASR 结果 JSON 的本地保存根目录（默认与 wav 同目录）
                         若设置，JSON 会保存到 {ASR_JSON_OUTPUT_DIR}/pcm_case/pcm_case/{case_id}/{session_id}/ 下
"""
import os
import sys
import json
import logging
import time
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

# ─── 加载 asr_server/.env（含 QWEN_OMNI_* 配置） ───
_asr_server_env = Path(__file__).resolve().parent.parent.parent.parent / 'asr_server' / '.env'
if _asr_server_env.exists():
    with open(_asr_server_env, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())

# ─── 导入第三方 qwen omni ASR 模块 ───
_asr_server_dir = str(Path(__file__).resolve().parent.parent.parent.parent / 'asr_server')
if _asr_server_dir not in sys.path:
    sys.path.insert(0, _asr_server_dir)
try:
    from qwen_omni_asr import call_qwen_omni_asr
except ImportError as e:
    call_qwen_omni_asr = None
    logging.getLogger(__name__).warning(f"无法导入 qwen_omni_asr 模块: {e}")

import requests

logger = logging.getLogger(__name__)

# ─────────── 配置（从 .env 读取，提供默认值兜底） ───────────
ASR_SERVER_URL = os.environ.get("ASR_SERVER_URL", "http://127.0.0.1:10095").rstrip("/")
ASR_TIMEOUT = int(os.environ.get("ASR_TIMEOUT", "120"))
ASR_JSON_OUTPUT_DIR = os.environ.get("ASR_JSON_OUTPUT_DIR", "").strip()


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


# ─────────── 流程 ───────────

def call_modelscope_asr(wav_path, language=None):
    """
    调用远程 ASR 服务（asr_server.py）进行 ASR 推理。

    Args:
        wav_path: 本地 wav 文件路径
        language: 保留参数兼容性（Paraformer 中文模型自动识别，忽略该参数）

    Returns:
        服务端已解析好的结果 dict：
            {"text": "识别全文", "chunks": [{"text": "字", "timestamp": [start_s, end_s]}, ...]}
        时间戳单位为秒。

        为兼容老调用方，本函数返回 [result] 形式（长度 1 的列表），让 parse_result 能继续工作。
    """
    if not os.path.isfile(wav_path):
        logger.error(f"wav 文件不存在: {wav_path}")
        return [{'text': '', 'chunks': []}]

    url = f"{ASR_SERVER_URL}/asr"
    logger.info(f"调用远程 ASR: {url}  wav={wav_path}")

    with open(wav_path, "rb") as f:
        files = {"file": (os.path.basename(wav_path), f, "audio/wav")}
        t0 = time.time()
        resp = requests.post(url, files=files, timeout=ASR_TIMEOUT)
        elapsed = time.time() - t0

    if resp.status_code != 200:
        raise RuntimeError(
            f"远程 ASR 返回错误 {resp.status_code}: {resp.text}"
        )

    result = resp.json()
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
    if not os.path.isfile(wav_path):
        logger.error(f"wav 文件不存在: {wav_path}")
        return [{'text': '', 'chunks': []}]

    url = f"{ASR_SERVER_URL}/asr_word"
    logger.info(f"调用远程 ASR(词级): {url}  wav={wav_path}")

    with open(wav_path, "rb") as f:
        files = {"file": (os.path.basename(wav_path), f, "audio/wav")}
        t0 = time.time()
        resp = requests.post(url, files=files, timeout=ASR_TIMEOUT)
        elapsed = time.time() - t0

    if resp.status_code != 200:
        raise RuntimeError(
            f"远程 ASR(词级) 返回错误 {resp.status_code}: {resp.text}"
        )

    result = resp.json()
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
    }
