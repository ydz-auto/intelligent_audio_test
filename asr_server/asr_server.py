# -*- coding: utf-8 -*-
"""
asr_server.py
在 ASR 主机上独立部署的 ASR HTTP 服务（Silero VAD + SenseVoiceSmall）。

架构:
    Silero VAD 切段（真实语音边界、~30ms 帧级、不含标点造假时间戳）
    + SenseVoiceSmall 逐段出文本（中文/多语言，质量好、ITN）
    → 段级 chunks: [{text: 整句, timestamp: [start_s, end_s]}, ...]

为什么这样组合:
    SenseVoiceSmall 是非自回归 AED 模型，原生不输出词级时间戳。
    单独用会丢时间戳，而打断/接管时延等指标强依赖时间戳、且要求识别模型在打断处的
    短暂停（~0.3s）。Silero VAD 的 min_silence_duration_ms 可调（默认 200ms），能精确
    切出"停下→恢复"边界。段级 chunks 也治了"标点单独成 chunk"的根因（标点内联在段文本里）。

部署:
    1. pip install funasr torch fastapi uvicorn python-multipart soundfile librosa silero-vad
    2. python asr_server.py
    3. 首次启动从 ModelScope 下载 SenseVoice（~900MB），Silero 内置于包内
    4. 监听 0.0.0.0:10095，对外提供 /asr 接口

返回结构:
    {"text": "全文", "chunks": [{"text": "段文本", "timestamp": [start_s, end_s]}, ...]}
    时间戳单位秒，段级（一句一 chunk）。

接口:
    GET  /health        健康检查
    POST /asr           上传 wav 文件，返回 ASR 结果
    POST /asr_file      传 wav 文件路径（仅本机使用）
"""
import os
import re
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

# SenseVoice 模型
ASR_SENSEVOICE_MODEL = os.environ.get("ASR_SENSEVOICE_MODEL", "iic/SenseVoiceSmall")
ASR_SV_LANGUAGE = os.environ.get("ASR_SV_LANGUAGE", "auto")   # auto|zh|en|ja|ko|...
ASR_SV_USE_ITN = os.environ.get("ASR_SV_USE_ITN", "true").lower() == "true"

# Paraformer 模型（词级时间戳，false_takeover 用）
ASR_PARAFORMER_MODEL = os.environ.get(
    "ASR_PARAFORMER_MODEL",
    "iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch"
)
ASR_PARAFORMER_VAD_MODEL = os.environ.get(
    "ASR_PARAFORMER_VAD_MODEL",
    "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch"
)
ASR_PARAFORMER_PUNC_MODEL = os.environ.get(
    "ASR_PARAFORMER_PUNC_MODEL",
    "iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch"
)

# ─── Silero VAD 参数 ───
ASR_SILERO_MIN_SILENCE_MS = int(os.environ.get("ASR_SILERO_MIN_SILENCE_MS", "200"))
ASR_SILERO_THRESHOLD = float(os.environ.get("ASR_SILERO_THRESHOLD", "0.6"))
ASR_SILERO_MIN_SPEECH_MS = int(os.environ.get("ASR_SILERO_MIN_SPEECH_MS", "500"))
ASR_SILERO_SPEECH_PAD_MS = int(os.environ.get("ASR_SILERO_SPEECH_PAD_MS", "30"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("asr_server")

# ─────────── 模型懒加载 ───────────
_silero_model = None    # Silero VAD
_sv_model = None        # SenseVoice
_paraformer_model = None  # Paraformer（词级时间戳）


def _load_silero_vad():
    global _silero_model
    if _silero_model is None:
        from silero_vad import load_silero_vad
        logger.info("加载 Silero VAD")
        _silero_model = load_silero_vad()
        logger.info("Silero VAD 加载完成")
    return _silero_model


def _load_sensevoice():
    global _sv_model
    if _sv_model is None:
        from funasr import AutoModel
        logger.info(f"加载 SenseVoice 模型: {ASR_SENSEVOICE_MODEL}")
        _sv_model = AutoModel(
            model=ASR_SENSEVOICE_MODEL,
            trust_remote_code=False,
            disable_update=True,
        )
        logger.info("SenseVoice 模型加载完成")
    return _sv_model


def _load_paraformer():
    """加载 Paraformer-large-vad-punc（词级时间戳，false_takeover 用）"""
    global _paraformer_model
    if _paraformer_model is None:
        from funasr import AutoModel
        logger.info(f"加载 Paraformer 模型: {ASR_PARAFORMER_MODEL}")
        kwargs = dict(model=ASR_PARAFORMER_MODEL, model_revision="v2.0.4")
        if ASR_PARAFORMER_VAD_MODEL:
            kwargs["vad_model"] = ASR_PARAFORMER_VAD_MODEL
            kwargs["vad_revision"] = "v2.0.4"
        if ASR_PARAFORMER_PUNC_MODEL:
            kwargs["punc_model"] = ASR_PARAFORMER_PUNC_MODEL
            kwargs["punc_revision"] = "v2.0.4"
        _paraformer_model = AutoModel(**kwargs)
        logger.info("Paraformer 模型加载完成")
    return _paraformer_model


# ─────────── 音频加载 ───────────
def _load_audio_16k_mono(wav_path):
    """读 wav → 16kHz 单通道 float32 numpy"""
    import soundfile as sf
    audio, sr = sf.read(wav_path, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != 16000:
        import librosa
        audio = librosa.resample(audio, orig_sr=sr, target_sr=16000)
        sr = 16000
    return audio, sr


# ─────────── Silero VAD 切段 ───────────
def _vad_segments(audio_np, sr):
    """返回语音段列表 [(start_s, end_s), ...]"""
    import torch
    from silero_vad import get_speech_timestamps
    model = _load_silero_vad()
    w = torch.from_numpy(audio_np)
    ts = get_speech_timestamps(
        w, model, sampling_rate=sr,
        min_silence_duration_ms=ASR_SILERO_MIN_SILENCE_MS,
        threshold=ASR_SILERO_THRESHOLD,
        min_speech_duration_ms=ASR_SILERO_MIN_SPEECH_MS,
        speech_pad_ms=ASR_SILERO_SPEECH_PAD_MS,
        return_seconds=True,
    )
    return [(s["start"], s["end"]) for s in ts]


# ─────────── SenseVoice 特殊 token 剥离 ───────────
_SV_TOKEN_RE = re.compile(r"<\|[^|]*\|>")


def _strip_sv_tokens(text: str) -> str:
    """去掉 SenseVoice 输出里的 <|zh|><|NEUTRAL|><|Speech|><|withitn|> 等特殊 token"""
    if not text:
        return ""
    return _SV_TOKEN_RE.sub("", text).strip()


# ─────────── 转写：VAD 切段 → 逐段 SenseVoice 出文本 ───────────
def _transcribe(wav_path):
    """Silero VAD 切段 → 每段 SenseVoice 出文本 → 段级 chunks（真实时间戳）"""
    audio, sr = _load_audio_16k_mono(wav_path)
    duration_s = len(audio) / sr

    sv = _load_sensevoice()
    segs = _vad_segments(audio, sr)   # [(start_s, end_s), ...]

    chunks = []
    full_text_parts = []
    for s_s, e_s in segs:
        if e_s <= s_s:
            continue
        s_idx = int(s_s * sr)
        e_idx = int(e_s * sr)
        seg_audio = audio[s_idx:e_idx]
        if len(seg_audio) == 0:
            continue
        r = sv.generate(
            input=seg_audio, cache={},
            language=ASR_SV_LANGUAGE, use_itn=ASR_SV_USE_ITN,
        )
        txt = r[0].get("text", "") if r else ""
        txt = _strip_sv_tokens(txt)
        chunks.append({
            "text": txt,
            "timestamp": [round(s_s, 3), round(e_s, 3)],
        })
        if txt:
            full_text_parts.append(txt)

    text = "".join(full_text_parts)
    logger.info(f"转写完成: {len(segs)} 段, {duration_s:.1f}s -> {text[:80]}")
    return {"text": text, "chunks": chunks}


# ─────────── 统一入口 ───────────
def call_modelscope_asr(wav_path):
    """返回 {text, chunks}（chunks 时间戳单位秒，段级）"""
    return _transcribe(wav_path)


def call_modelscope_asr_word(wav_path):
    """Paraformer 词级转写：返回 {text, chunks}（chunks 为单字级时间戳）

    Paraformer 的 text 含标点（由 punc_model 添加），但 timestamp 列表
    只对应非标点字符。用独立索引遍历 timestamp，遇到标点时跳过且不消耗
    timestamp 槽位，确保字与时间戳正确对齐。
    """
    import unicodedata

    model = _load_paraformer()
    res = model.generate(input=wav_path, batch_size_s=300)
    if not res:
        raise RuntimeError(f"Paraformer ASR 返回空结果: {wav_path}")

    item = res[0]
    text = item.get("text", "")
    timestamp = item.get("timestamp") or []

    chunks = []
    ts_idx = 0
    for char in text:
        if char.strip() == "":
            continue
        if ts_idx >= len(timestamp):
            logger.warning(
                f"Paraformer timestamp 不足: text={len(text)}字, "
                f"timestamp={len(timestamp)}条, 已消耗{ts_idx}"
            )
            break
        cat = unicodedata.category(char)
        if cat.startswith('P') or cat.startswith('Z'):
            continue
        start_ms, end_ms = timestamp[ts_idx][0], timestamp[ts_idx][1]
        chunks.append({
            "text": char,
            "timestamp": [round(start_ms / 1000.0, 3), round(end_ms / 1000.0, 3)],
        })
        ts_idx += 1

    logger.info(f"Paraformer 转写完成: {len(chunks)} 字 -> {text[:80]}")
    return {"text": text, "chunks": chunks}


def parse_result(raw_res):
    """兼容旧调用：raw_res 为 [result] 或 result，透传 {text, chunks}"""
    item = raw_res[0] if isinstance(raw_res, list) else raw_res
    return {
        "text": item.get("text", ""),
        "chunks": item.get("chunks", []),
    }


# ─────────── FastAPI 服务 ───────────
app = FastAPI(title="ASR Service", version="3.0")


@app.get("/health")
def health():
    """健康检查。"""
    return {
        "status": "ok",
        "engine": "sensevoice+silero + paraformer",
        "vad_loaded": _silero_model is not None,
        "asr_loaded": _sv_model is not None,
        "paraformer_loaded": _paraformer_model is not None,
    }


@app.post("/asr")
async def asr(file: UploadFile = File(...)):
    """接收上传的 wav 文件，返回 {text, chunks}（段级，SenseVoice+Silero）。"""
    if not file.filename.lower().endswith(".wav"):
        raise HTTPException(400, "只支持 wav 文件")

    suffix = os.path.splitext(file.filename)[1]
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        t0 = time.time()
        logger.info(f"收到 ASR 请求: {file.filename} ({len(content)} bytes)")
        result = call_modelscope_asr(tmp_path)
        elapsed = time.time() - t0
        logger.info(f"ASR 完成 ({elapsed:.2f}s, {len(result.get('chunks', []))} 段): {result.get('text', '')[:80]}")
        return JSONResponse(result)
    except Exception as e:
        logger.exception(f"ASR 失败: {e}")
        raise HTTPException(500, f"ASR 失败: {e}")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@app.post("/asr_word")
async def asr_word(file: UploadFile = File(...)):
    """接收上传的 wav 文件，返回 {text, chunks}（词级，Paraformer）。"""
    if not file.filename.lower().endswith(".wav"):
        raise HTTPException(400, "只支持 wav 文件")

    suffix = os.path.splitext(file.filename)[1]
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        t0 = time.time()
        logger.info(f"收到 ASR(词级) 请求: {file.filename} ({len(content)} bytes)")
        result = call_modelscope_asr_word(tmp_path)
        elapsed = time.time() - t0
        logger.info(f"ASR(词级) 完成 ({elapsed:.2f}s, {len(result.get('chunks', []))} 字): {result.get('text', '')[:80]}")
        return JSONResponse(result)
    except Exception as e:
        logger.exception(f"ASR(词级) 失败: {e}")
        raise HTTPException(500, f"ASR 失败: {e}")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@app.post("/asr_file")
def asr_file(wav_path: str):
    """本机调用：传 wav 文件绝对路径，返回 ASR 结果。"""
    if not os.path.isfile(wav_path):
        raise HTTPException(404, f"文件不存在: {wav_path}")
    try:
        return JSONResponse(call_modelscope_asr(wav_path))
    except Exception as e:
        logger.exception(f"ASR 失败: {e}")
        raise HTTPException(500, f"ASR 失败: {e}")


@app.get("/")
def root():
    return {
        "service": "ASR Service",
        "engine": "sensevoice+silero + paraformer",
        "sensevoice_model": ASR_SENSEVOICE_MODEL,
        "paraformer_model": ASR_PARAFORMER_MODEL,
        "endpoints": {
            "health": "GET /health",
            "asr": "POST /asr (段级, SenseVoice+Silero)",
            "asr_word": "POST /asr_word (词级, Paraformer)",
            "asr_file": "POST /asr_file?wav_path=<本地路径>",
        },
    }




# ─────────── 启动 ───────────
if __name__ == "__main__":
    logger.info(f"启动 ASR 服务: http://{HOST}:{PORT}  engine=sensevoice+silero + paraformer")
    logger.info(f"模型: Silero VAD + SenseVoice={ASR_SENSEVOICE_MODEL}")
    logger.info(f"模型: Paraformer={ASR_PARAFORMER_MODEL}")
    logger.info("预加载模型，首次会从 ModelScope 下载（SenseVoice ~900MB, Paraformer ~3GB）...")
    _load_silero_vad()
    _load_sensevoice()
    _load_paraformer()

    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
