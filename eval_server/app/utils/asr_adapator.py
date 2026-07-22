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
"""
import os
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

import requests

logger = logging.getLogger(__name__)

# ─────────── 配置（从 .env 读取，提供默认值兜底） ───────────
ASR_SERVER_URL = os.environ.get("ASR_SERVER_URL", "http://127.0.0.1:10095").rstrip("/")
ASR_TIMEOUT = int(os.environ.get("ASR_TIMEOUT", "120"))


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

    # 包装成 [result]，让 parse_result(raw) 能继续工作（raw[0] 取出 result）
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
