# -*- coding: utf-8 -*-
"""音频上传子包（P4-6 由 services/ 平铺文件重组而来）。

结构：
- service.py：AudioUploadService 编排器（聚合各 Mixin，组合子服务）
- presign_mixin.py：AudioPresignMixin — S3 Multipart 预签名/MD5 秒传/OSS key 去重
- direct_mixin.py：AudioDirectUploadMixin — WAV 直传 OSS 完成/元数据提取/临时文件清理
- task_mixin.py：AudioUploadTaskMixin — 上传任务初始化/文件注册/分片上传/进度查询
- merge_mixin.py：AudioMergeMixin — 分片合并/秒传处理/音频记录/测试用例创建
- url_import_mixin.py：AudioUrlImportMixin — URL 远程导入
- transcoding_service.py：AudioTranscodingService — 转码/OSS/文件路径/分片合并
- metadata_service.py：AudioMetadataService — 音频元数据提取
- round_config_service.py：AudioRoundConfigService — 轮次配置/合并参数提取

兼容性：旧导入路径
`audio_service.application.services.audio_upload_service`
保留 re-export shim（AudioUploadService / audio_upload_service）。
"""
from audio_service.application.services.audio_upload.service import (
    AudioUploadService,
    audio_upload_service,
)

__all__ = ['AudioUploadService', 'audio_upload_service']
