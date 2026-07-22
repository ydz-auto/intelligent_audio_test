# -*- coding: utf-8 -*-
"""
asr_server.py
在 ASR 主机上独立部署的 ASR HTTP 服务（基于 ModelScope Paraformer-large-vad-punc）。

设计目标:
    - 部署到另一台 Windows 电脑（纯 CPU 推理）
    - 自动化测试主机通过 HTTP 调用，避免 CPU 占用影响测试
    - 返回结构 {text, chunks:[{text, timestamp:[start_s, end_s]}]} 与 ASR_JSON.parse_result 兼容

部署:
    1. pip install funasr torch fastapi uvicorn python-multipart
    2. 配置 .env 文件（参考 .env.example）
    3. python asr_server.py
    4. 首次启动会从 ModelScope 下载模型到本地缓存（~3GB），之后直接读本地
    5. 监听 0.0.0.0:10095，对外提供 /asr 接口

调用方式（测试主机）:
    import requests
    with open(wav_path, "rb") as f:
        resp = requests.post("http://<ASR主机IP>:10095/asr",
                             files={"file": ("audio.wav", f, "audio/wav")})
    result = resp.json()
    # result = {"text": "...", "chunks":[{"text":"字","timestamp":[start_s, end_s]}]}

接口:
    GET  /health        健康检查
    POST /asr           上传 wav 文件，返回 ASR 结果
    POST /asr_file      传 wav 文件路径（仅本机使用，非远程调用）
"""
import os
import sys
import json
import logging
import tempfile
import time
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

# ─── 关闭代理（ModelScope 为国内站点，代理会导致 SSL 握手失败） ───
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
           "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(_k, None)

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import uvicorn

# ─────────── 配置 ───────────
# 项目根目录（与 eval_server / Intelligent-Audio-TEST 对齐）
_BASE_DIR = Path(__file__).resolve().parent.parent
_STATIC_DIR = _BASE_DIR / 'static'

HOST = os.environ.get("ASR_HOST", "0.0.0.0")
PORT = int(os.environ.get("ASR_PORT", "10095"))

# 模型缓存目录（默认存到 static/asr_models，避免污染用户主目录）
ASR_CACHE_DIR = os.environ.get(
    "ASR_CACHE_DIR",
    str(_STATIC_DIR / 'asr_models')
)
os.environ.setdefault("MODELSCOPE_CACHE", ASR_CACHE_DIR)
os.makedirs(ASR_CACHE_DIR, exist_ok=True)

ASR_MODELSCOPE_MODEL = os.environ.get(
    "ASR_MODELSCOPE_MODEL",
    "iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch"
)
ASR_VAD_MODEL = os.environ.get(
    "ASR_VAD_MODEL",
    "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch"
)
ASR_PUNC_MODEL = os.environ.get(
    "ASR_PUNC_MODEL",
    "iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("asr_server")

# ─────────── 模型懒加载 ───────────
_model = None


def get_model():
    """懒加载 AutoModel，避免启动时就阻塞进程。"""
    global _model
    if _model is None:
        logger.info(f"加载 ModelScope ASR 模型: {ASR_MODELSCOPE_MODEL}")
        logger.info(f"模型缓存目录: {ASR_CACHE_DIR}")
        from funasr import AutoModel
        kwargs = dict(model=ASR_MODELSCOPE_MODEL, model_revision="v2.0.4")
        if ASR_VAD_MODEL:
            kwargs["vad_model"] = ASR_VAD_MODEL
            kwargs["vad_revision"] = "v2.0.4"
        if ASR_PUNC_MODEL:
            kwargs["punc_model"] = ASR_PUNC_MODEL
            kwargs["punc_revision"] = "v2.0.4"
        _model = AutoModel(**kwargs)
        logger.info("ASR 模型加载完成")
    return _model


# ─────────── ASR 推理 + 结果解析 ───────────

def call_modelscope_asr(wav_path):
    """调用 ModelScope Paraformer 进行本地 ASR 推理。"""
    model = get_model()
    res = model.generate(input=wav_path, batch_size_s=300)
    if not res:
        raise RuntimeError(f"ModelScope ASR 返回空结果: {wav_path}")
    return res


def parse_result(raw_res):
    """
    解析 ModelScope ASR 结果为 {text, chunks:[{text, timestamp:[start_s, end_s]}]}。
    时间戳从毫秒转成秒，与 ASR_JSON.parse_result 输出结构完全一致。
    """
    item = raw_res[0]
    text = item.get("text", "")
    timestamp = item.get("timestamp") or []

    chunks = []
    text_chars = list(text)
    n = min(len(text_chars), len(timestamp))
    for i in range(n):
        char = text_chars[i]
        if char.strip() == "":
            continue
        start_ms, end_ms = timestamp[i][0], timestamp[i][1]
        chunks.append({
            "text": char,
            "timestamp": [start_ms / 1000.0, end_ms / 1000.0],
        })

    return {"text": text, "chunks": chunks}


# ─────────── FastAPI 服务 ───────────

app = FastAPI(title="ModelScope ASR Service", version="1.0")


@app.get("/health")
def health():
    """健康检查。"""
    loaded = _model is not None
    return {"status": "ok", "model_loaded": loaded}


@app.post("/asr")
async def asr(file: UploadFile = File(...)):
    """
    接收上传的 wav 文件，执行 ASR 推理，返回 {text, chunks} 结构。

    返回示例:
        {
          "text": "你好世界",
          "chunks": [
            {"text": "你", "timestamp": [0.1, 0.25]},
            {"text": "好", "timestamp": [0.25, 0.4]},
            ...
          ]
        }
    """
    if not file.filename.lower().endswith(".wav"):
        raise HTTPException(400, "只支持 wav 文件")

    # 保存上传文件到临时路径
    suffix = os.path.splitext(file.filename)[1]
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        t0 = time.time()
        logger.info(f"收到 ASR 请求: {file.filename} ({len(content)} bytes)")
        raw = call_modelscope_asr(tmp_path)
        result = parse_result(raw)
        elapsed = time.time() - t0
        logger.info(f"ASR 完成 ({elapsed:.2f}s): {result['text'][:80]}")
        return JSONResponse(result)
    except Exception as e:
        logger.exception(f"ASR 失败: {e}")
        raise HTTPException(500, f"ASR 失败: {e}")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@app.post("/asr_file")
def asr_file(wav_path: str):
    """
    本机调用：传 wav 文件绝对路径，返回 ASR 结果。
    适用于 ASR 主机本地测试（不需要上传文件）。

    请求示例: POST /asr_file?wav_path=C:/xxx/audio.wav
    """
    if not os.path.isfile(wav_path):
        raise HTTPException(404, f"文件不存在: {wav_path}")
    try:
        raw = call_modelscope_asr(wav_path)
        return JSONResponse(parse_result(raw))
    except Exception as e:
        logger.exception(f"ASR 失败: {e}")
        raise HTTPException(500, f"ASR 失败: {e}")


@app.get("/")
def root():
    return {
        "service": "ModelScope ASR Service",
        "model": ASR_MODELSCOPE_MODEL,
        "endpoints": {
            "health": "GET /health",
            "asr": "POST /asr (上传 wav 文件)",
            "asr_file": "POST /asr_file?wav_path=<本地路径>",
        },
    }


# ─────────── 启动 ───────────

if __name__ == "__main__":
    logger.info(f"启动 ASR 服务: http://{HOST}:{PORT}")
    logger.info(f"模型: {ASR_MODELSCOPE_MODEL}")

    # 预加载模型（首次会下载，约 3GB，需要几分钟）
    logger.info("预加载 ASR 模型，首次会从 ModelScope 下载...")
    get_model()

    # 启动 HTTP 服务
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
