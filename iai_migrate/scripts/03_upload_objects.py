#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把迁移包内的桶目录上传到自建 RustFS / MinIO（S3 兼容，path 寻址）。

用法：
    export OSS_ENDPOINT=http://127.0.0.1:9000
    export OSS_ACCESS_KEY=... OSS_SECRET_KEY=...
    export OSS_BUCKET_NAME=intelligent-audio-test
    export OSS_KEY_PREFIX=test/intelligent_audio_test
    python 03_upload_objects.py [--dry-run]
"""
import os
import sys

import boto3
from botocore.config import Config

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.join(PKG, 'bucket', 'test', 'intelligent_audio_test')

endpoint = os.environ['OSS_ENDPOINT']
bucket = os.environ.get('OSS_BUCKET_NAME', 'intelligent-audio-test')
prefix = os.environ.get('OSS_KEY_PREFIX', 'test/intelligent_audio_test').strip('/')
s3 = boto3.client(
    's3', endpoint_url=endpoint,
    aws_access_key_id=os.environ['OSS_ACCESS_KEY'],
    aws_secret_access_key=os.environ['OSS_SECRET_KEY'],
    region_name=os.environ.get('OSS_REGION', 'us-east-1'),
    config=Config(s3={'addressing_style': 'path'}))

try:
    s3.head_bucket(Bucket=bucket)
except Exception:
    s3.create_bucket(Bucket=bucket)
    print('已创建桶', bucket)

dry = '--dry-run' in sys.argv
total = skipped = uploaded = failed = 0
for dp, _, fs in os.walk(ROOT):
    for f in fs:
        p = os.path.join(dp, f)
        rel = os.path.relpath(p, ROOT).replace(os.sep, '/')
        key = f'{prefix}/{rel}'
        size = os.path.getsize(p)
        total += 1
        if dry:
            continue
        try:
            head = s3.head_object(Bucket=bucket, Key=key)
            if head['ContentLength'] == size:
                skipped += 1
                continue
        except Exception:
            pass
        try:
            s3.upload_file(p, bucket, key)
            uploaded += 1
            if uploaded % 500 == 0:
                print('已上传', uploaded, flush=True)
        except Exception as e:
            failed += 1
            print('失败', key, e)
print(f'总计 {total} 已上传 {uploaded} 已存在跳过 {skipped} 失败 {failed}')
