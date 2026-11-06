# -*- coding: utf-8 -*-
"""按字节登记音频 Mixin（INT-2215 / INT-2216：用例 ZIP 导入回导音频）。

用例包只带音频二进制 + manifest（名称/格式/大小/md5，见 INT-2205 审计
「导入侧裁定」）。目标库没有对应 md5 的音频时，需要一条「凭字节登记一条
音频记录」的命令；已存在同 md5 时幂等复用既有记录，保证跨库导入重复执行
不产生重复音频、也不按 audio_id 错绑。

落库复用既有上传链（`AudioTranscodingService.transcode_and_extract_metadata`，
即分片合并入库那条链）：写入临时文件 → 转码/落存储（**已是合法 wav 时不重编码，
存储字节与入参一致**，md5 幂等键才在「导出→再导入」的往复中保持稳定）→
`audio_metadata_service` 真实探测时长/采样率/声道 → `repo.create_audio` + commit。
`audios.duration` 为 NOT NULL，必须走这条链拿到真实值，不在此处重写一份。

（未用 `AudioUrlImportMixin._save_audio`：其内部 `create_record_from_file` 对 .wav
也强制 ffmpeg 重导出，会让存储字节与入参 md5 不一致——包内文件 md5 与目标库
audios.md5 对不上，导出再导入会产生重复音频。）

失败分类（四类分开，不混）：
- 内容为空 / 非音频（INT-2202 口径）→ 400，不落库；
- 入参 md5 与实际字节 md5 不一致 → 400（防错绑，不以实算静默改写）；
- 同 md5 已存在（未软删）→ 200 + `reused: true`，不新建、不改名；
- 同名不同 md5 → 正常新建（去重维度只认 md5）。
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
from io import BytesIO

logger = logging.getLogger(__name__)


def _fail(message: str, reason: str, code: int = 400) -> dict:
    """失败结果：data 里带机器可读的 reason（gRPC 响应无 code 字段，随 data 透传）。"""
    return {'success': False, 'message': message,
            'data': {'code': code, 'reason': reason}, 'code': code}


def _ok(data: dict, message: str, code: int = 200) -> dict:
    return {'success': True, 'message': message, 'data': data, 'code': code}


class AudioRegisterByBytesMixin:
    """按字节登记音频（依赖 self.repo / self._transcoding_service）"""

    def register_audio_by_bytes(self, data: dict) -> dict:
        """按字节登记一条音频（md5 幂等）。

        data 字段（与 proto `RegisterAudioByBytesRequest.data` 的 JSON 一致）：
        - name: str            音频显示名称（必填）
        - md5: str             源字节 md5（必填，必须与实际字节一致）
        - content_b64: str     源字节 base64（必填，与 UploadChunk 同法）
        - format: str          源格式（可选，缺省 wav）
        - size: int            源字节数（可选，仅作参照，落库取存储对象真实大小）
        - audio_type: str      音频类型（可选，缺省 dry）
        - source_filename: str 原始文件名（可选，缺省用 name）
        """
        if not data:
            return _fail('请求体不能为空', 'empty_request')

        name = str(data.get('name') or '').strip()
        md5 = str(data.get('md5') or '').strip().lower()
        content_b64 = data.get('content_b64', data.get('contentB64'))
        if not name:
            return _fail('缺少 name 参数', 'missing_name')
        if not md5:
            return _fail('缺少 md5 参数', 'missing_md5')
        if content_b64 is None:
            return _fail('缺少 content_b64 参数（音频字节 base64）', 'missing_content')

        try:
            content = base64.b64decode(str(content_b64).strip(), validate=True)
        except Exception:
            return _fail('content_b64 不是合法的 base64', 'invalid_base64')
        if not content:
            return _fail('音频内容为空（0 字节），拒绝登记', 'empty_content')

        actual_md5 = hashlib.md5(content).hexdigest()
        if actual_md5 != md5:
            return _fail(
                f'md5 与音频字节不一致（入参 {md5}，实算 {actual_md5}），拒绝登记',
                'md5_mismatch')

        # 幂等：同 md5 已存在（未软删）直接复用既有记录，不新建、不改名
        existing = self.repo.get_audio_by_md5(md5)
        if existing is not None:
            payload = self._registered_audio_payload(existing, reused=True)
            return _ok(payload, '音频已存在，复用既有记录')

        fmt = str(data.get('format') or 'wav').strip().lower().lstrip('.') or 'wav'
        audio_type = str(
            data.get('audio_type', data.get('audioType')) or 'dry')
        source_filename = str(data.get('source_filename', data.get('sourceFilename'))
                              or name).strip() or name

        # 复用上传链：转码/落存储/真实时长探测；空内容与非音频在此被拒
        temp_path = None
        try:
            temp_path = self._write_temp_audio_file(content, source_filename)
            upload_file = self._build_virtual_upload_file(source_filename)
            meta = self._transcoding_service.transcode_and_extract_metadata(
                temp_path, upload_file)
        except Exception as e:
            logger.info('按字节登记音频内容无效: name=%s md5=%s err=%s', name, md5, e)
            from audio_service.domain.exceptions import InvalidAudioContentError
            message = (str(e) if isinstance(e, InvalidAudioContentError)
                       else f'音频内容无效，登记失败：{e}')
            return _fail(message, 'invalid_audio_content')
        finally:
            # 成功路径转码服务已删临时文件；失败路径在此兜底清理
            self._remove_temp_file(temp_path)

        record = {
            'name': name,
            'original_filename': source_filename,
            'file_path': meta['final_path'],
            'size': meta['file_size'],
            'duration': meta['duration'],
            'sample_rate': meta['sample_rate'],
            'channels': meta['channels'],
            'bitrate': meta['bitrate'],
            'format': fmt,
            'md5': md5,
            'audio_type': audio_type,
        }

        try:
            new_audio = self.repo.create_audio(record)
            self.repo.commit()
        except Exception as e:
            self.repo.rollback()
            logger.warning('按字节登记音频入库失败: name=%s md5=%s err=%s', name, md5, e)
            return _fail(f'音频登记入库失败: {e}', 'persist_failed', code=500)

        self._refresh_stats_after_register(new_audio.id)
        payload = self._registered_audio_payload(new_audio, reused=False)
        return _ok(payload, '音频登记成功')

    def _write_temp_audio_file(self, content: bytes, source_filename: str) -> str:
        """把入参字节写成上传链要求的临时文件，返回临时文件路径。"""
        from audio_service.application.services.audio_file_utils import _retry_file_operation
        from audio_service.application.services.audio_upload.transcoding_service import (
            _generate_audio_storage_path,
            _persist_file_content,
        )

        temp_path = _generate_audio_storage_path(
            source_filename, self._get_base_upload_dir(), 'import_', '')
        file_obj = BytesIO(content)
        file_obj.filename = source_filename
        _retry_file_operation(_persist_file_content, file_obj, temp_path)
        return temp_path

    def _build_virtual_upload_file(self, source_filename: str):
        """上传链只读 filename / relative_path；按字节登记没有 upload_file 行，用轻量实体顶替。"""
        from audio_service.domain.entities import UploadFileEntity
        return UploadFileEntity(filename=source_filename, relative_path='')

    def _remove_temp_file(self, temp_path):
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                logger.debug('清理按字节登记临时文件失败: %s', temp_path, exc_info=True)

    def _registered_audio_payload(self, audio, reused: bool) -> dict:
        """登记结果载荷（新建与复用同一形状，网关 ACL 客户端据此取 id / reused）。"""
        return {
            'id': audio.id,
            'name': audio.filename,
            'original_filename': audio.original_filename,
            'format': audio.audio_format,
            'size': audio.file_size,
            'md5': audio.md5,
            'duration': audio.duration,
            'sample_rate': audio.sample_rate,
            'channels': audio.channels,
            'bitrate': audio.bitrate,
            'audio_type': audio.audio_type,
            'file_path': audio.file_path,
            'visibility': audio.visibility,
            'created_by_user_id': audio.created_by_user_id,
            'reused': reused,
            # servicer 的 _wrap 只透传 success/message/data，code 随 data 一起回传
            'code': 200,
        }

    def _refresh_stats_after_register(self, audio_id):
        """登记成功后刷新首页统计缓存（与 URL 导入一致，失败不影响登记结果）。"""
        try:
            from api_gateway.application.services.stats_cache import refresh_stats_cache
            refresh_stats_cache()
        except Exception:
            logger.debug('登记音频后刷新统计缓存失败: audio_id=%s', audio_id, exc_info=True)
