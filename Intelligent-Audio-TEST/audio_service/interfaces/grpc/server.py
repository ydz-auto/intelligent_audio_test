# -*- coding: utf-8 -*-
"""audio_service gRPC server 启动模块。

注册 audio_service 相关 servicer（定义于 interfaces/grpc/servicers.py）：
- AudioServiceServicer
- PlaybackServiceServicer
- AudioConfigServiceServicer

端口：50052
"""

import os
import logging
from concurrent import futures

import grpc

from shared.proto import audio_service_pb2_grpc as audio_grpc
from shared.infrastructure.grpc_interceptors import server_log_interceptor, server_db_scope_interceptor
from shared.infrastructure.config import Config
from shared.utils.config_manager import config_manager
from shared.config.service_ports import AUDIO_SERVICE_GRPC_PORT
from audio_service.interfaces.grpc.servicers import (
    AudioServiceServicer,
    PlaybackServiceServicer,
    AudioConfigServiceServicer,
)

logger = logging.getLogger(__name__)


def _configure_pydub_ffmpeg():
    """根据 Config 中已解析的路径配置 pydub 的 ffmpeg/ffprobe 可执行文件路径。

    若不设置，pydub 会回退到裸字符串 'ffmpeg'/'ffprobe'，在 PATH 未包含
    可执行文件时导致 ffprobe 警告或转码失败。
    """
    from pydub import AudioSegment
    ffmpeg_path = Config.FFMPEG_PATH
    ffprobe_path = Config.FFPROBE_PATH
    if ffmpeg_path and os.path.isfile(ffmpeg_path):
        AudioSegment.converter = ffmpeg_path
    if ffprobe_path and os.path.isfile(ffprobe_path):
        AudioSegment.ffprobe = ffprobe_path


def start_grpc_server(port=AUDIO_SERVICE_GRPC_PORT):
    """启动 audio_service 的 gRPC server

    Args:
        port: gRPC 监听端口，默认 50052

    Returns:
        grpc.Server: 已启动的 server 实例，调用方持有引用以防被 GC 回收
    """
    # 配置 pydub 的 ffmpeg/ffprobe 路径（必须在首次使用 AudioSegment 前完成）
    _configure_pydub_ffmpeg()

    # 初始化数据库连接池（audio_service 无 FastAPI lifespan，在此处初始化）
    from shared.models.database import init_db
    init_db(pool_size=5)

    # 启动软删除硬清理守护线程（只清理本服务 owned 表 audios 及子表）
    from audio_service.infrastructure.persistence.soft_delete_cleaner import get_cleaner as get_soft_delete_cleaner
    _cleaner = get_soft_delete_cleaner()
    _cleaner.start()

    # 在主线程中预初始化 PyAudio 驱动
    # Pa_Initialize() 非线程安全，必须在服务启动前完成，避免子线程调用时卡死/崩溃
    try:
        from audio_service.infrastructure.audio.audio_engine import audio_service
        audio_service.init_driver()
    except Exception as e:
        logger.warning(f"PyAudio 驱动预初始化失败（音频功能可能不可用）: {e}")

    # gRPC 线程池大小配置化：优先读取 concurrency_config.json 中的 grpc.audio_service_workers
    _max_workers = config_manager.get_value('grpc', 'audio_service_workers', 5)
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=_max_workers),
        interceptors=[server_db_scope_interceptor, server_log_interceptor],
    )
    audio_grpc.add_AudioServiceServicer_to_server(AudioServiceServicer(), server)
    audio_grpc.add_PlaybackServiceServicer_to_server(PlaybackServiceServicer(), server)
    audio_grpc.add_AudioConfigServiceServicer_to_server(AudioConfigServiceServicer(), server)
    server.add_insecure_port(f'[::]:{port}')
    server.start()
    logger.info("audio_service gRPC server started on port %s", port)
    return server


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    _server = start_grpc_server()
    try:
        _server.wait_for_termination()
    except KeyboardInterrupt:
        _server.stop(0)
