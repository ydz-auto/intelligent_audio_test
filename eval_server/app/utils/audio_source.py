# -*- coding: utf-8 -*-
"""音频/文件来源统一访问层。

消费方（ASR、LLM 裁判、音频元数据、波形处理等）统一通过本模块读取音频：
    - 本地路径（绝对/相对文件路径）：保持原样直读；
    - oss:// 引用（COS / MinIO / RustFS，S3 兼容，单桶/多桶键规则与 oss_client 一致）：
      直接内存读取（不落盘），仅波形处理等必须真实文件的场景才 ensure_local 物化到缓存目录。

存储后端可配置（eval_server/.env / config.yaml）：
    - UPLOAD_STORAGE: multipart 上传的二进制文件去向（local / oss / auto）
    - OSS_RESOLVE_MODE: 计算时对 oss:// 引用的处理（download 下载到本地 / stream 内存直读）
    - AUDIO_OSS_CATEGORY: oss 上传使用的 category（默认 audios）
"""
import io
import os
import time
import logging

logger = logging.getLogger(__name__)

_SCHEME_OSS = 'oss://'

# 波形处理等必须真实文件的消费方，oss:// 引用物化到的缓存目录（UPLOAD_DIR/_ref_cache）
_CACHE_DIR = None
_last_sweep = 0.0
_CACHE_TTL_SECONDS = 24 * 3600   # 缓存文件超过 24h 未访问即清理
_SWEEP_INTERVAL = 3600           # 每小时做一次过期清理（低频，避免每次读都扫目录）


def is_oss_ref(value) -> bool:
    """判断字符串是否为 oss:// 引用。"""
    return isinstance(value, str) and value.startswith(_SCHEME_OSS)


def exists(path) -> bool:
    """判断引用是否存在（oss:// → head_object；本地路径 → os.path.isfile）。"""
    if is_oss_ref(path):
        from .oss_client import oss_client
        return oss_client.enabled and oss_client.exists(path)
    return bool(path) and os.path.isfile(path)


def basename(path) -> str:
    """返回引用对应的文件名（oss://.../a.wav → a.wav）。"""
    if is_oss_ref(path):
        return os.path.basename(path.rstrip('/'))
    return os.path.basename(path)


def get_size(path) -> int:
    """返回引用字节数（oss:// → head_object；本地路径 → os.path.getsize，异常返回 0）。"""
    if is_oss_ref(path):
        from .oss_client import oss_client
        return oss_client.get_size(path)
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def read_bytes(path, limit: int = None) -> bytes:
    """读取引用字节（oss:// → 内存读取不落盘；本地路径 → 打开文件）。

    limit 指定后只读前 limit 字节（用于读 wav 头等场景，避免整文件入内存）。
    """
    if is_oss_ref(path):
        from .oss_client import oss_client
        return oss_client.read_bytes(path, limit=limit)
    with open(path, 'rb') as f:
        return f.read(limit) if limit else f.read()


def open_stream(path):
    """返回引用内容的文件对象（oss:// → BytesIO；本地路径 → 原文件对象）。"""
    if is_oss_ref(path):
        return io.BytesIO(read_bytes(path))
    return open(path, 'rb')


def _sweep_cache():
    """清理 _ref_cache 中过期文件（低频 TTL，防止 stream 模式物化残留累积）。"""
    global _last_sweep, _CACHE_DIR
    now = time.time()
    if now - _last_sweep < _SWEEP_INTERVAL or _CACHE_DIR is None:
        return
    _last_sweep = now
    try:
        for root, _dirs, files in os.walk(_CACHE_DIR):
            for name in files:
                fp = os.path.join(root, name)
                try:
                    if now - os.path.getmtime(fp) > _CACHE_TTL_SECONDS:
                        os.remove(fp)
                except OSError:
                    pass
    except OSError:
        pass


def ensure_local(path, local_dir: str = None) -> str:
    """把引用物化为本地文件路径。

    - 本地路径：原样返回（无开销）。
    - oss:// 引用：下载到缓存目录（默认 UPLOAD_DIR/_ref_cache，目录结构与
      oss key 一致，便于排查），供波形处理等必须真实文件的消费方使用。
      下载后由 _sweep_cache 按 TTL 清理，避免长期累积。
    """
    if not is_oss_ref(path):
        return path
    global _CACHE_DIR, _last_sweep
    if local_dir:
        cache = local_dir
    else:
        if _CACHE_DIR is None:
            from ..config import config
            _CACHE_DIR = os.path.join(config.UPLOAD_DIR, '_ref_cache')
        cache = _CACHE_DIR
    rel = path[len(_SCHEME_OSS):].lstrip('/')
    local = os.path.join(cache, rel)
    if os.path.exists(local):
        os.utime(local)  # 刷新 mtime，延长 TTL
        return local
    from .oss_client import oss_client
    oss_client.download(path, cache)
    _sweep_cache()
    return local
