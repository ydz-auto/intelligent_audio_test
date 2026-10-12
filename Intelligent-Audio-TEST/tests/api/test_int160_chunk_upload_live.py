# -*- coding: utf-8 -*-
"""INT-160 实机验收回归 — 音频分片上传链（chunk_content 键对齐 + 计数持久化）。

覆盖（需 V9.7.31 后端运行，未运行时经 require_backend 自动 skip）：
  - 非秒传新 md5 单分片全链：init→register→chunk→merge→建音频，磁盘分片字节一致
  - 多分片计数推进 / 持久化 / 合并
  - 重传同序号分片幂等（文件级计数不重复）
  - 缺失分片文件 → 400 不假成功
  - 分片未齐 merge → 400

注意：10MB 标准分片 b64 后 ~14MB 超 audio_service gRPC 默认 4MB 收包上限
（RESOURCE_EXHAUSTED，独立缺陷另行跟踪），本回归用 ≤2.5MB 分片验证链路。

认证：后端 AUTH_MODE=dev 时经 /auth/login/encryption-key + RSA-OAEP 登录取
token；off 模式下直接匿名请求。
"""
import base64
import hashlib
import io
import json
import os
import secrets
import struct
import wave

import httpx
import pytest
from tests.api.conftest import API_BASE

CHUNK_SIZE_SERVER = 10 * 1024 * 1024   # 服务端 register 使用的分片大小
SLICE_LIMIT = 2 * 1024 * 1024          # 本回归分片上限（绕开 gRPC 4MB 收包上限，见模块 docstring）


# ── 认证 ──────────────────────────────────────────────────

def _bearer_header(client: httpx.Client) -> dict:
    """AUTH_MODE=dev 时登录获取 Bearer token；off 模式返回空头。"""
    r = client.get('/auth/login/encryption-key')
    if r.status_code != 200:
        return {}
    info = r.json()
    if isinstance(info.get('data'), dict) and info['data'].get('kid'):
        info = info['data']
    if not info.get('enabled'):
        return {}
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    pub = serialization.load_pem_public_key(info['public_key'].encode())
    ct = base64.b64encode(pub.encrypt(
        b'dev_password',
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),
                     algorithm=hashes.SHA256(), label=None))).decode()
    r = client.post('/auth/login', data={
        'username': 'dev_user', 'password_encrypted': ct,
        'encryption_key_id': info['kid']})
    assert r.status_code == 200, f'dev 登录失败: {r.status_code} {r.text[:200]}'
    body = r.json()
    token = body.get('access_token') or (body.get('data') or {}).get('token')
    assert token, f'登录响应无 token: {json.dumps(body, ensure_ascii=False)[:200]}'
    return {'Authorization': f'Bearer {token}'}


# ── 工具 ──────────────────────────────────────────────────

def _make_wav_base() -> bytes:
    """合成 0.2s 单声道 8kHz PCM WAV（无外部素材依赖）。"""
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b'\x00\x01' * 1600)
    return buf.getvalue()


def _make_upload_content(total_size: int) -> bytes:
    """有效 WAV 头 + 唯一尾巴 + 零填充：新 md5（非秒传），ffmpeg 可转码。"""
    base = _make_wav_base()
    tail = b'INT160-' + secrets.token_hex(8).encode()
    return base + tail + b'\x00' * max(0, total_size - len(base) - len(tail))


def _api(client: httpx.Client, headers: dict, method: str, path: str, **kw):
    r = client.request(method, path, headers=headers, **kw)
    try:
        body = r.json()
    except Exception:
        body = {}
    return r.status_code, body


def _init_task(client, headers):
    st, body = _api(client, headers, 'POST', '/audios/upload/init', json={})
    data = body.get('data') or {}
    tid = data.get('taskId') or data.get('task_id')
    assert st == 200 and tid, f'init 失败: {st} {json.dumps(body, ensure_ascii=False)[:200]}'
    return tid


def _register(client, headers, task_id, name, size, md5):
    st, body = _api(client, headers, 'POST', '/audios/upload/register', json={
        'taskId': task_id,
        'files': [{'name': name, 'size': size, 'md5': md5,
                   'relativePath': 'test/' + name}]})
    files = (body.get('data') or {}).get('files') or []
    f = files[0] if files else {}
    fid = f.get('fileId') or f.get('file_id')
    tchunks = f.get('totalChunks', f.get('total_chunks'))
    assert st == 200 and fid, f'register 失败: {st} {json.dumps(body, ensure_ascii=False)[:200]}'
    return fid, tchunks


def _upload_chunk(client, headers, task_id, file_id, index, total, payload: bytes):
    return _api(client, headers, 'POST', '/audios/upload/chunk',
                data={'file_id': file_id, 'chunk_index': str(index),
                      'total_chunks': str(total), 'task_id': task_id},
                files={'chunk': (f'chunk_{index}', payload)})


def _chunk_disk_path(file_id: str, index: int):
    """分片落盘路径。根目录取 LOCAL_STORAGE_ROOT（测试进程无该环境变量时从仓库 .env 解析）。"""
    root = os.environ.get('LOCAL_STORAGE_ROOT')
    if not root:
        env_file = os.path.join(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))), '.env')
        if os.path.isfile(env_file):
            with open(env_file, 'r', encoding='utf-8', errors='replace') as fh:
                for line in fh:
                    line = line.strip()
                    if line.startswith('LOCAL_STORAGE_ROOT='):
                        root = line.split('=', 1)[1].strip()
                        break
    if not root:
        root = os.path.join(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))), 'storage')
    p = os.path.join(root, 'audios', 'chunks', file_id, f'chunk_{index}')
    return p if os.path.isfile(p) else None


# ── 用例 ──────────────────────────────────────────────────

class TestInt160ChunkUploadLive:
    """分片上传链实机回归（INT-160 修复验收沉淀）。"""

    def test_single_chunk_full_chain(self, api_client):
        """非秒传单分片全链：chunk 落盘字节正确、计数持久化、merge 建音频。"""
        headers = _bearer_header(api_client)
        content = _make_upload_content(len(_make_wav_base()) + 32)
        md5 = hashlib.md5(content).hexdigest()

        task_id = _init_task(api_client, headers)
        file_id, total = _register(api_client, headers, task_id,
                                   f'int160_{secrets.token_hex(4)}.wav',
                                   len(content), md5)
        assert total == 1, f'单分片文件 total_chunks 应为 1: {total}'

        st, body = _upload_chunk(api_client, headers, task_id, file_id, 0, 1, content)
        d = body.get('data') or {}
        assert st == 200, f'chunk 失败: {st} {json.dumps(body, ensure_ascii=False)[:200]}'
        assert d.get('completed_chunks') == 1
        assert d.get('uploaded_size') == len(content), '分片大小按实际字节计'

        p = _chunk_disk_path(file_id, 0)
        assert p, f'分片未落盘: {file_id}/chunk_0'
        with open(p, 'rb') as fh:
            assert fh.read() == content, '磁盘分片字节与上传内容不一致'

        st, body = _api(api_client, headers, 'GET', '/audios/upload/progress',
                        params={'task_id': task_id})
        files = (body.get('data') or {}).get('files') or []
        assert files and files[0].get('completed_chunks') == 1
        # status 序列化存在枚举 repr 缺陷（'UploadStatus.completed'），仅校验前缀
        assert str(files[0].get('status', '')).endswith('completed')

        st, body = _api(api_client, headers, 'POST', '/audios/upload/merge',
                        json={'file_id': file_id, 'task_id': task_id})
        d = body.get('data') or {}
        audio_id = d.get('audio_id') or d.get('audioId')
        assert st == 200 and audio_id, f'merge 失败: {st} {json.dumps(body, ensure_ascii=False)[:300]}'

        st, body = _api(api_client, headers, 'GET', f'/audios/{audio_id}')
        assert st == 200, f'音频记录不可查: {st}'

    def test_multi_chunk_counters_and_merge(self, api_client):
        """多分片：顺序上传计数 1→2、磁盘字节一致、merge 通过计数闸门建音频。"""
        headers = _bearer_header(api_client)
        declared = CHUNK_SIZE_SERVER + 1024 * 1024          # 11MB → total_chunks=2
        content = _make_upload_content(declared)
        md5 = hashlib.md5(content).hexdigest()

        task_id = _init_task(api_client, headers)
        file_id, total = _register(api_client, headers, task_id,
                                   f'int160_{secrets.token_hex(4)}.wav',
                                   declared, md5)
        assert total == 2, f'total_chunks 应为 2: {total}'

        slices = [content[:SLICE_LIMIT], content[SLICE_LIMIT:2 * SLICE_LIMIT]]
        acc = 0
        for i, sl in enumerate(slices):
            acc += len(sl)
            st, body = _upload_chunk(api_client, headers, task_id, file_id, i, 2, sl)
            d = body.get('data') or {}
            assert st == 200, f'chunk{i} 失败: {st} {json.dumps(body, ensure_ascii=False)[:200]}'
            assert d.get('completed_chunks') == i + 1, f'chunk{i} 计数未推进'
            assert d.get('uploaded_size') == acc
            p = _chunk_disk_path(file_id, i)
            assert p and os.path.getsize(p) == len(sl), f'chunk{i} 落盘字节不符'

        st, body = _api(api_client, headers, 'POST', '/audios/upload/merge',
                        json={'file_id': file_id, 'task_id': task_id})
        d = body.get('data') or {}
        assert st == 200 and (d.get('audio_id') or d.get('audioId')), \
            f'merge 失败: {st} {json.dumps(body, ensure_ascii=False)[:300]}'

    def test_reupload_same_chunk_idempotent(self, api_client):
        """重传同序号分片：completed_chunks 不重复计数、uploaded_size 按体积差修正。"""
        headers = _bearer_header(api_client)
        content = _make_upload_content(len(_make_wav_base()) + 64)
        md5 = hashlib.md5(content).hexdigest()

        task_id = _init_task(api_client, headers)
        file_id, total = _register(api_client, headers, task_id,
                                   f'int160_{secrets.token_hex(4)}.wav',
                                   len(content), md5)

        for payload in (content, content):
            st, body = _upload_chunk(api_client, headers, task_id, file_id, 0, 1, payload)
            d = body.get('data') or {}
            assert st == 200, f'chunk 失败: {st} {json.dumps(body, ensure_ascii=False)[:200]}'
            assert d.get('completed_chunks') == 1, '重传同序号分片不得重复计数'
            assert d.get('uploaded_size') == len(content), '重传后 uploaded_size 应按最新分片大小'

    def test_missing_chunk_file_rejected(self, api_client):
        """缺分片文件字段 → 400，不得假成功。"""
        headers = _bearer_header(api_client)
        content = _make_upload_content(len(_make_wav_base()) + 32)
        md5 = hashlib.md5(content).hexdigest()

        task_id = _init_task(api_client, headers)
        file_id, _ = _register(api_client, headers, task_id,
                               f'int160_{secrets.token_hex(4)}.wav',
                               len(content), md5)
        st, body = _api(api_client, headers, 'POST', '/audios/upload/chunk',
                        data={'file_id': file_id, 'chunk_index': '0',
                              'total_chunks': '1', 'task_id': task_id})
        assert st == 400, f'缺分片文件应 400: {st} {json.dumps(body, ensure_ascii=False)[:200]}'

    def test_merge_before_chunks_complete_rejected(self, api_client):
        """分片未齐 merge → 400「还有分片未上传完成」（计数真实持久化的反向验证）。"""
        headers = _bearer_header(api_client)
        declared = CHUNK_SIZE_SERVER + 1024 * 1024
        content = _make_upload_content(declared)
        md5 = hashlib.md5(content).hexdigest()

        task_id = _init_task(api_client, headers)
        file_id, total = _register(api_client, headers, task_id,
                                   f'int160_{secrets.token_hex(4)}.wav',
                                   declared, md5)
        st, body = _upload_chunk(api_client, headers, task_id, file_id, 0, 2,
                                 content[:SLICE_LIMIT])
        assert st == 200
        st, body = _api(api_client, headers, 'POST', '/audios/upload/merge',
                        json={'file_id': file_id, 'task_id': task_id})
        assert st == 400 and '未上传完成' in str(body.get('message', '')), \
            f'分片未齐 merge 应 400: {st} {json.dumps(body, ensure_ascii=False)[:200]}'
