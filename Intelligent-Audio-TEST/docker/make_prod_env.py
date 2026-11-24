#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在服务器生成 compose 生产 .env。

STORAGE_BACKEND 决定存储段（默认 cos，保持既有部署行为）：
  cos    —— 腾讯云 COS，密钥/桶从 ~/cos_use/cos.env 读取
  rustfs —— 自建 RustFS（compose 内 rustfs 服务），密钥取 RUSTFS_ACCESS_KEY/SECRET_KEY
  local  —— 只用本地磁盘（compose 共享卷 storage_local），不需要任何 S3 凭据
"""
import hashlib
import os
import pathlib

BACKEND = (os.environ.get('STORAGE_BACKEND') or 'cos').strip().lower()

HOME = pathlib.Path.home()
out = HOME / 'iat-deploy' / 'compose' / '.env'


def _load_kv(path: pathlib.Path) -> dict:
    vals = {}
    if not path.exists():
        return vals
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line.startswith('export '):
            line = line[7:]
        if '=' in line:
            k, v = line.split('=', 1)
            vals[k.strip()] = v.strip().strip("'\"")
    return vals


def _storage_block(jwt_secret: str) -> str:
    if BACKEND == 'cos':
        cos_env = HOME / 'cos_use' / 'cos.env'
        if not cos_env.exists():
            raise SystemExit(f'{cos_env} 不存在（STORAGE_BACKEND=cos 需要 COS 密钥）')
        vals = _load_kv(cos_env)
        endpoint = os.environ.get('OSS_ENDPOINT') or vals.get(
            'COS_ENDPOINT', 'https://cos.ap-shanghai.myqcloud.com')
        bucket = os.environ.get('OSS_BUCKET_NAME') or vals.get('COS_BUCKET', '')
        if not bucket:
            raise SystemExit('cos.env 缺少 COS_BUCKET（或显式设置 OSS_BUCKET_NAME）')
        return f'''STORAGE_BACKEND=cos
OSS_ENDPOINT={endpoint}
OSS_PUBLIC_ENDPOINT={os.environ.get('OSS_PUBLIC_ENDPOINT') or endpoint}
OSS_REGION={os.environ.get('OSS_REGION') or vals.get('COS_REGION', 'ap-shanghai')}
OSS_ACCESS_KEY={vals.get('COS_SECRET_ID', '')}
OSS_SECRET_KEY={vals.get('COS_SECRET_KEY', '')}
OSS_BUCKET_NAME={bucket}
OSS_KEY_PREFIX={os.environ.get('OSS_KEY_PREFIX') or 'test/intelligent_audio_test'}
OSS_ADDRESSING_STYLE=virtual
STORAGE_FALLBACK_ENABLED=false
'''

    if BACKEND == 'rustfs':
        access_key = os.environ.get('RUSTFS_ACCESS_KEY') or 'intelligent_audio_test'
        secret_key = os.environ.get('RUSTFS_SECRET_KEY') or 'intelligent_audio_test666'
        return f'''STORAGE_BACKEND=rustfs
OSS_ENDPOINT=http://rustfs:9000
OSS_PUBLIC_ENDPOINT={os.environ.get('OSS_PUBLIC_ENDPOINT') or 'http://127.0.0.1:9000'}
OSS_REGION=us-east-1
OSS_ACCESS_KEY={access_key}
OSS_SECRET_KEY={secret_key}
OSS_BUCKET_NAME={os.environ.get('OSS_BUCKET_NAME') or 'intelligent-audio-test'}
OSS_KEY_PREFIX={os.environ.get('OSS_KEY_PREFIX') or 'test/intelligent_audio_test'}
OSS_ADDRESSING_STYLE=path
STORAGE_FALLBACK_ENABLED=false
'''

    if BACKEND == 'local':
        # 本地后端没有 OSS 密钥，媒体 token 用 JWT 密钥派生，避免可预测签名
        media_secret = os.environ.get('MEDIA_TOKEN_SECRET') or hashlib.sha256(
            f'iat-media|{jwt_secret}'.encode('utf-8')).hexdigest()
        return f'''STORAGE_BACKEND=local
STORAGE_LOCAL_ROOT=/app/storage/local
STORAGE_FALLBACK_ENABLED=true
AUDIO_STREAM_VIA_GATEWAY=true
FILE_DOWNLOAD_VIA_GATEWAY=true
MEDIA_TOKEN_SECRET={media_secret}
'''

    raise SystemExit(
        f'未知 STORAGE_BACKEND={BACKEND!r}，可选 cos / rustfs / local')


jwt_secret = os.environ.get('IAT_JWT_SECRET', '')
if not jwt_secret:
    raise SystemExit('IAT_JWT_SECRET is required')

storage_block = _storage_block(jwt_secret)

env = f'''COMPOSE_PROJECT_NAME=intelligent-audio-test
POSTGRES_USER=intelligent_audio_test
POSTGRES_PASSWORD=intelligent_audio_test666
POSTGRES_DB=intelligent_audio_test
POSTGRES_PORT=5432
REDIS_PORT=6379
FRONTEND_PORT=8080
API_GATEWAY_PORT=15000
TASK_SERVICE_HTTP_PORT=15001
E2E_TEST_HTTP_PORT=15002
API_TEST_HTTP_PORT=15003
EVALUATION_SERVICE_HTTP_PORT=15004
REPORT_SERVICE_HTTP_PORT=15006
ALGORITHM_SERVICE_HTTP_PORT=15007
AUTH_SERVICE_HTTP_PORT=15009
TRANSFER_AGENT_HTTP_PORT=15010
TASK_SERVICE_GRPC_PORT=53061
ALGORITHM_SERVICE_GRPC_PORT=53067
EVALUATION_SERVICE_GRPC_PORT=53091
API_TEST_SERVICE_GRPC_PORT=53071
AUTH_SERVICE_GRPC_PORT=53069
REPORT_SERVICE_GRPC_PORT=53068
E2E_TEST_GRPC_PORT=53051
API_TEST_REPLICAS=2
SVC_MEM_LIMIT=192m
SVC_CPU_LIMIT=0.25
AUTH_MODE=dev
JWT_SECRET={jwt_secret}
JWT_EXPIRE_HOURS=24
JWT_ALGORITHM=HS256
DEV_DEFAULT_USERNAME=admin
DEV_DEFAULT_PASSWORD=admin123
DEV_DEFAULT_ROLE=admin
LOG_ARCHIVE_THRESHOLD=0
# 执行机（e2e / audio / device 常驻所在机）；换执行机只改这一项
EXECUTOR_HOST=10.0.0.9
ASR_TAILSCALE_IP=100.103.97.108
{storage_block}# Agent 运行底座已在生产启用（供应商配置 / 会话 / Run 均经网关）
AGENT_ENABLED=true
'''

out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(env, encoding='utf-8')
out.chmod(0o600)
print(f'wrote {out} ({len(env.splitlines())} lines, storage={BACKEND})')
