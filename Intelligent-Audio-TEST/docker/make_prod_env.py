#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在服务器生成 compose 生产 .env（COS 密钥从 ~/cos_use/cos.env 读取）。"""
import os
import pathlib

HOME = pathlib.Path.home()
cos_env = HOME / 'cos_use' / 'cos.env'
out = HOME / 'iat-deploy' / 'compose' / '.env'

vals = {}
for line in cos_env.read_text(encoding='utf-8').splitlines():
    line = line.strip()
    if line.startswith('export '):
        line = line[7:]
    if '=' in line:
        k, v = line.split('=', 1)
        vals[k.strip()] = v.strip().strip("'\"")

jwt_secret = os.environ.get('IAT_JWT_SECRET', '')
if not jwt_secret:
    raise SystemExit('IAT_JWT_SECRET is required')

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
LOG_ARCHIVE_THRESHOLD=300000
LOCAL_TAILSCALE_IP=100.123.155.32
ASR_TAILSCALE_IP=100.103.97.108
E2E_TEST_SERVICE_HOST=e2e_test_service
E2E_TEST_SERVICE_GRPC_PORT=50051
OSS_ENDPOINT=https://cos.ap-shanghai.myqcloud.com
OSS_PUBLIC_ENDPOINT=https://cos.ap-shanghai.myqcloud.com
OSS_REGION=ap-shanghai
OSS_ACCESS_KEY={vals.get('COS_SECRET_ID', '')}
OSS_SECRET_KEY={vals.get('COS_SECRET_KEY', '')}
OSS_BUCKET_NAME={vals.get('COS_BUCKET', 'xiaoyi-voice-1474863084')}
OSS_KEY_PREFIX=test/intelligent_audio_test
STORAGE_FALLBACK_ENABLED=false
AGENT_ENABLED=false
'''

out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(env, encoding='utf-8')
out.chmod(0o600)
print(f'wrote {out} ({len(env.splitlines())} lines)')
