# -*- coding: utf-8 -*-
"""API 接口测试 fixtures: httpx 客户端、样例音频文件、统一标注 rounds 配置。

样例文件来源: doc/voice_llm/样例/ (3 个 WAV + 样例.json 统一标注)。
后端未运行时自动 skip 全部 API 测试。
"""
import os
import json
import hashlib
import httpx
import pytest

# ── 路径常量 ──────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SAMPLE_DIR = os.path.join(PROJECT_ROOT, 'doc', 'voice_llm', '样例')
API_BASE = os.environ.get('API_BASE_URL', 'http://localhost:5000/api/v1')
HEALTH_URL = os.environ.get('HEALTH_URL', 'http://localhost:5000/health')

# 样例音频文件（3 轮，每轮一个 WAV）
SAMPLE_AUDIO_FILES = ['2026144010.wav', '2026144019.wav', '2026144026.wav']


# ── 后端健康检查 ──────────────────────────────────────────
def _backend_alive() -> bool:
    try:
        r = httpx.get(HEALTH_URL, timeout=3)
        return r.status_code == 200
    except Exception:
        return False


@pytest.fixture(scope='session')
def require_backend():
    """后端未运行时跳过全部 API 测试。"""
    if not _backend_alive():
        pytest.skip('后端未运行，跳过 API 集成测试。启动后端后重试。')


# ── httpx 客户端 ──────────────────────────────────────────
@pytest.fixture(scope='session')
def api_client(require_backend):
    with httpx.Client(base_url=API_BASE, timeout=30) as client:
        yield client


# ── 样例音频 fixtures ─────────────────────────────────────
@pytest.fixture(scope='session')
def sample_dir():
    assert os.path.isdir(SAMPLE_DIR), f'样例目录不存在: {SAMPLE_DIR}'
    return SAMPLE_DIR


@pytest.fixture(scope='session')
def sample_audio_files(sample_dir):
    """返回 [{path, name, size, md5, relativePath}] 列表。"""
    files = []
    for name in SAMPLE_AUDIO_FILES:
        path = os.path.join(sample_dir, name)
        assert os.path.isfile(path), f'样例音频不存在: {path}'
        with open(path, 'rb') as f:
            md5 = hashlib.md5(f.read()).hexdigest()
        files.append({
            'path': path,
            'name': name,
            'size': os.path.getsize(path),
            'md5': md5,
            # 注意: relativePath 用 ASCII 前缀规避 MinIO 中文对象名 bug
            # (XMinioInvalidObjectName),见 issue 回复中的缺陷报告
            'relativePath': f'sample/{name}',
        })
    return files


@pytest.fixture(scope='session')
def unified_rounds():
    """从 样例.json 解析统一标注，生成后端期望的 rounds 格式。

    格式与前端 FolderImportModal.ts 的 unifiedRounds 构建逻辑一致:
    [{ roundNumber, audios: [{ audio_name, play_order, spl, playback_device_name }] }]
    """
    json_path = os.path.join(SAMPLE_DIR, '样例.json')
    with open(json_path, 'r', encoding='utf-8') as f:
        raw = json.load(f)

    rounds = []
    for ri, round_data in enumerate(raw.get('rounds', [])):
        segments = round_data.get('segments', [])
        audios = []
        for idx, seg in enumerate(segments):
            audio_name = seg.get('audio') or seg.get('audio_name') or ''
            cfg = {'audio_name': audio_name, 'play_order': idx}
            if seg.get('spl') is not None and seg.get('spl') != '':
                cfg['spl'] = float(seg['spl'])
            if seg.get('playback_device_name'):
                cfg['playback_device_name'] = seg['playback_device_name']
            audios.append(cfg)
        rounds.append({
            'roundNumber': round_data.get('round_number', ri + 1),
            'audios': audios,
        })
    return rounds
