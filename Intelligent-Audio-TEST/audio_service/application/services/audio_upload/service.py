# -*- coding: utf-8 -*-
"""音频上传应用服务（编排器，聚合模块；P4-5 大文件拆分，P4-6 重组入 audio_upload 子包）。

原单文件 941 行，按职责拆分为 5 个内部 Mixin 模块；本模块位于
`audio_service.application.services.audio_upload.service`。
旧路径 `audio_service.application.services.audio_upload_service`
保留 re-export shim（AudioUploadService / audio_upload_service）：

- presign_mixin.py：AudioPresignMixin — S3 Multipart 预签名/MD5 秒传/OSS key 去重
- direct_mixin.py：AudioDirectUploadMixin — WAV 直传 OSS 完成/元数据提取/临时文件清理
- task_mixin.py：AudioUploadTaskMixin — 上传任务初始化/文件注册/分片上传/进度查询
- merge_mixin.py：AudioMergeMixin — 分片合并/秒传处理/音频记录/测试用例创建
- url_import_mixin.py：AudioUrlImportMixin — URL 远程导入

重构后仅保留上传流程编排，具体子能力委托给：
- transcoding_service: 转码/OSS/文件路径/分片合并
- metadata_service: 音频元数据提取
- round_config_service: 轮次配置/合并参数提取
- audio_annotation_service: 标注持久化
- audio_testcase_creation_service: 测试用例创建

公共 API（AudioUploadService 的方法签名）保持不变，调用方无需修改。
"""
import logging

from audio_service.domain.repositories.audio_repository_abc import AudioRepositoryInterface
from audio_service.infrastructure.persistence.audio_repository import audio_repository
from audio_service.application.services.audio_annotation_service import audio_annotation_service
from audio_service.application.services.audio_testcase_creation_service import audio_testcase_creation_service
from audio_service.application.services.audio_upload.metadata_service import audio_metadata_service
from audio_service.application.services.audio_upload.transcoding_service import audio_transcoding_service
from audio_service.application.services.audio_upload.round_config_service import audio_round_config_service
from audio_service.application.services.audio_upload.presign_mixin import AudioPresignMixin
from audio_service.application.services.audio_upload.direct_mixin import AudioDirectUploadMixin
from audio_service.application.services.audio_upload.task_mixin import AudioUploadTaskMixin
from audio_service.application.services.audio_upload.merge_mixin import AudioMergeMixin
from audio_service.application.services.audio_upload.url_import_mixin import AudioUrlImportMixin

logger = logging.getLogger(__name__)


class AudioUploadService(
    AudioPresignMixin,
    AudioDirectUploadMixin,
    AudioUploadTaskMixin,
    AudioMergeMixin,
    AudioUrlImportMixin,
):
    """音频上传应用服务（编排器，组合各职责 Mixin）。

    每个职责 Mixin 依赖 self.repo 与协作服务实例（构造器统一注入）。
    """

    def __init__(self, repo: AudioRepositoryInterface = None):
        self.repo = repo or audio_repository
        self._annotation_service = audio_annotation_service
        self._testcase_creation_service = audio_testcase_creation_service
        self._transcoding_service = audio_transcoding_service
        self._metadata_service = audio_metadata_service
        self._round_config_service = audio_round_config_service


# 模块级实例
audio_upload_service = AudioUploadService()
