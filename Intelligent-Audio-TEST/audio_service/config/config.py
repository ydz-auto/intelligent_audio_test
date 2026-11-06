# -*- coding: utf-8 -*-
"""Audio Service 领域配置"""
import os
from shared.infrastructure.config import BaseConfig


class Config(BaseConfig):
    PORT = int(os.environ.get('PORT', 5005))
    GRPC_PORT = int(os.environ.get('GRPC_PORT', 50052))

    # 分片上传单片大小（MB，INT-1522）。网关 → audio_service 的 UploadChunk 把
    # 分片内容 base64 后放进 protobuf string 字段（×4/3 膨胀 + JSON 信封），
    # grpcio 默认收包上限 4MiB（4194304B）对应的原始分片只有 ≈3MB；取 2MB
    # （线上 ≈2.73MB）留足余量，保证客户端按 register 返回的 chunk_size 切片
    # 一定不会被 RESOURCE_EXHAUSTED 拒收。
    AUDIO_UPLOAD_CHUNK_SIZE_MB = int(os.environ.get('AUDIO_UPLOAD_CHUNK_SIZE_MB', 2))
