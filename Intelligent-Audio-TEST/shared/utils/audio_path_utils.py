"""音频路径正则化工具"""
import os
from typing import Optional


def normalize_audio_path(audio_path: str, static_base_path: str) -> str:
    """将绝对音频路径转为相对 STATIC_BASE_PATH 的相对路径。

    解析符号链接后比较，不在基目录下则原样返回。
    """
    if not audio_path or not static_base_path:
        return audio_path
    if not os.path.isabs(audio_path):
        return audio_path
    real_abs = os.path.realpath(audio_path)
    real_base = os.path.realpath(static_base_path)
    try:
        common = os.path.commonpath([real_abs, real_base])
        if common == real_base:
            return os.path.relpath(real_abs, real_base).replace('\\', '/')
    except ValueError:
        pass
    return audio_path


_STORAGE_SCHEMES = ('oss://', 'local://')


def _remap_legacy_static_root(audio_path: str) -> Optional[str]:
    """历史静态根重映射：旧根下的绝对路径 → LOCAL_STORAGE_ROOT 同相对路径。

    存储根迁移后（如 D:/00_static/static → D:/00_code/static），存量记录的
    绝对路径在新机器上必然缺失；按 AUDIO_LEGACY_STATIC_ROOTS 配置的旧根
    逐个尝试剥离前缀并拼回当前 LOCAL_STORAGE_ROOT。命中且文件存在才返回。
    """
    from shared.infrastructure.config import BaseConfig
    legacy_roots = [
        root.strip() for root in
        (BaseConfig.AUDIO_LEGACY_STATIC_ROOTS or '').split(',') if root.strip()
    ]
    if not legacy_roots:
        return None
    norm_path = os.path.normcase(os.path.normpath(audio_path))
    for root in legacy_roots:
        norm_root = os.path.normcase(os.path.normpath(root))
        if not norm_path.startswith(norm_root):
            continue
        try:
            rel = os.path.relpath(os.path.normpath(audio_path),
                                  os.path.normpath(root))
        except ValueError:
            continue
        candidate = os.path.join(BaseConfig.LOCAL_STORAGE_ROOT, rel)
        if os.path.exists(candidate):
            return candidate
    return None


def resolve_audio_local_path(audio_path: str) -> Optional[str]:
    """将音频 file_path 解析为本地可用文件路径；无法解析返回 None。

    解析顺序（INT-106）：
    1. 本地已存在（绝对/相对路径原样可用）
    2. 历史静态根重映射（AUDIO_LEGACY_STATIC_ROOTS → LOCAL_STORAGE_ROOT）
    3. oss:// / local:// 存储引用或裸存储 key → 统一存储层下载到临时文件
    """
    if not audio_path:
        return None
    if os.path.exists(audio_path):
        return os.path.abspath(audio_path)

    remapped = _remap_legacy_static_root(audio_path)
    if remapped:
        return remapped

    from shared.infrastructure.storage import storage
    try:
        path = audio_path if audio_path.startswith(_STORAGE_SCHEMES) \
            else storage.build_path('audios', audio_path.replace('\\', '/'))
        return storage.load_file(path)
    except Exception:
        return None
