# -*- coding: utf-8 -*-
"""用例 ZIP 导入的包内音频回导（INT-2215）。

导出侧（INT-2214）把用例引用音频打进 `audios/{audio_id}.{ext}`，manifest 带
`audios[] = {id, name, file, md5, size, format}` 与缺失计数。导入侧要按包内
**字节**把音频回导到目标库，再把用例 config / 扁平列里的音频 id 全部重写成
目标库 id——绝不按 audio_id 直接绑定（目标库同 id 可能是另一条音频）。

顺序固定（INT-2205 契约裁定）：
1. 按 `manifest.audios[].md5` 批量 `GetAudioByMD5`，命中即复用目标库 id；
2. 未命中的逐条 `RegisterAudioByBytes`（audio_service，md5 幂等）；
3. 用返回的 `data.id` 构建 `{源 id: 目标 id}` 映射做重写。

预览只做第 1 步（只读），不得登记音频。
"""
from __future__ import annotations

import base64
import json
import logging

from shared.constants.testcase_transfer import MANIFEST_FILENAME

logger = logging.getLogger(__name__)

# 登记失败原因（audio_service 侧 data.reason + 网关侧补充的两类）
REGISTER_FAIL_REASON_MISSING_IN_PACKAGE = 'missing_in_package'
REGISTER_FAIL_REASON_NO_MD5 = 'missing_md5'


class ImportAudioPackage:
    """包内音频清单（parse 自 manifest + audios/ 二进制）。"""

    def __init__(self, entries=None, unavailable=None):
        # entries: [{source_id, name, file, md5, size, format, content}]
        self.entries = entries or []
        # unavailable: {source_id: reason} 清单声明但包内取不到（文件缺失/无 md5）
        self.unavailable = unavailable or {}

    def __bool__(self):
        return bool(self.entries or self.unavailable)

    @classmethod
    def from_zip(cls, zf, names):
        """从已打开的 ZIP 读 manifest.audios 与包内字节；无清单返回空包。"""
        if MANIFEST_FILENAME not in names:
            return cls()
        try:
            manifest = json.loads(zf.read(MANIFEST_FILENAME).decode('utf-8'))
        except Exception as e:
            logger.warning("用例包 manifest 解析失败，按无音频包处理: %s", e)
            return cls()
        if not isinstance(manifest, dict):
            return cls()

        raw_entries = manifest.get('audios')
        if not isinstance(raw_entries, list):
            raw_entries = []

        entries, unavailable = [], {}
        for item in raw_entries:
            if not isinstance(item, dict):
                continue
            source_id = _to_int(item.get('id'))
            md5 = str(item.get('md5') or '').strip().lower()
            zip_path = item.get('file') or item.get('path')
            if source_id is None:
                continue
            if not md5 or not zip_path:
                unavailable[source_id] = REGISTER_FAIL_REASON_NO_MD5
                continue
            if zip_path not in names:
                logger.warning("用例包音频文件缺失，按不可用处理: %s", zip_path)
                unavailable[source_id] = REGISTER_FAIL_REASON_MISSING_IN_PACKAGE
                continue
            try:
                content = zf.read(zip_path)
            except Exception:
                logger.warning("读取包内音频失败: %s", zip_path, exc_info=True)
                unavailable[source_id] = REGISTER_FAIL_REASON_MISSING_IN_PACKAGE
                continue
            if not content:
                unavailable[source_id] = REGISTER_FAIL_REASON_MISSING_IN_PACKAGE
                continue
            entries.append({
                'source_id': source_id,
                'name': str(item.get('name') or _basename(zip_path) or source_id),
                # 登记时传包内真实文件名并保留扩展名（不带扩展名会走 ffmpeg 转码分支）
                'source_filename': _basename(zip_path),
                'file': zip_path,
                'md5': md5,
                'size': _to_int(item.get('size')) or len(content),
                'format': str(item.get('format') or _ext_of(zip_path) or 'wav'),
                'content': content,
            })
        return cls(entries, unavailable)


class ImportAudioRemap:
    """包内音频 → 目标库 id 的映射结果（预览只读 / 导入含登记）。"""

    def __init__(self):
        self.source_to_target = {}   # 源 audio_id → 目标 audio_id
        self.reused = []             # [{source_id, md5, target_id}]
        self.registered = []         # [{source_id, md5, target_id}]
        self.failures = {}           # 源 audio_id → reason
        self.pending = []            # 预览：有待登记的源 id（未登记，不算失败）
        self.query_error = None

    def __bool__(self):
        return bool(self.source_to_target or self.failures or self.pending)

    @property
    def unresolved_source_ids(self):
        """尚未有目标 id 的源 id（预览按「待登记」放行）。"""
        return set(self.pending)

    def failure_message(self, audio_ids):
        """用例引用到登记失败音频时的行级错误文案（每条一行）。"""
        lines = []
        for audio_id in audio_ids:
            reason = self.failures.get(audio_id)
            if reason:
                lines.append(f"音频 {audio_id} 回导失败: {reason}")
        return "；".join(lines) or None


def build_audio_remap(package, audio_acl, register):
    """按 md5 复用 / 登记包内音频，返回 ImportAudioRemap。

    register=False（预览）：只做 `GetAudioByMD5` 批量查询，不产生任何写入；
    查不到的源 id 记入 pending，校验时按「待登记」放行。
    register=True（导入）：未命中的逐条 `RegisterAudioByBytes`，失败记 reasons。
    """
    remap = ImportAudioRemap()
    if not package:
        return remap
    for source_id, reason in package.unavailable.items():
        remap.failures[source_id] = reason

    md5s = []
    for entry in package.entries:
        if entry['md5'] not in md5s:
            md5s.append(entry['md5'])

    md5_target = {}
    if md5s:
        try:
            res = audio_acl.get_by_md5({'md5_list': md5s})
        except Exception as e:
            res = {'success': False, 'message': str(e)}
        if _success(res):
            data = res.get('data')
            if isinstance(data, dict):
                for md5, record in data.items():
                    target_id = _to_int((record or {}).get('id')) \
                        if isinstance(record, dict) else None
                    if target_id is not None:
                        md5_target[str(md5).strip().lower()] = target_id
        else:
            remap.query_error = _message(res) or '按 md5 查询音频失败'
            logger.warning("导入音频：按 md5 批量查询失败: %s", remap.query_error)

    for entry in package.entries:
        md5 = entry['md5']
        target_id = md5_target.get(md5)
        if target_id is not None:
            remap.source_to_target[entry['source_id']] = target_id
            remap.reused.append({
                'source_id': entry['source_id'], 'md5': md5, 'target_id': target_id})
            continue
        if not register:
            remap.pending.append(entry['source_id'])
            continue
        target_id, reason = _register_entry(audio_acl, entry)
        if target_id is None:
            remap.failures[entry['source_id']] = reason
            continue
        md5_target[md5] = target_id
        remap.source_to_target[entry['source_id']] = target_id
        remap.registered.append({
            'source_id': entry['source_id'], 'md5': md5, 'target_id': target_id})
    return remap


def _register_entry(audio_acl, entry):
    """调用 audio_service 按字节登记一条音频，返回 (target_id, fail_reason)。"""
    data = {
        'name': entry['name'],
        'md5': entry['md5'],
        'content_b64': base64.b64encode(entry['content']).decode('ascii'),
        'format': entry['format'],
        'size': entry['size'],
        'source_filename': entry['source_filename'],
    }
    try:
        res = audio_acl.register_audio_by_bytes(data)
    except Exception as e:
        logger.warning("导入音频登记异常，audio_id=%s", entry['source_id'], exc_info=True)
        return None, f'{e}'

    payload = res.get('data') if hasattr(res, 'get') else None
    if _success(res):
        target_id = _to_int((payload or {}).get('id')) \
            if isinstance(payload, dict) else None
        if target_id is not None:
            return target_id, None
        return None, 'register_no_id'
    reason = (payload or {}).get('reason') if isinstance(payload, dict) else None
    return None, reason or _message(res) or 'register_failed'


def _success(result):
    if hasattr(result, 'get'):
        return bool(result.get('success'))
    return False


def _message(result):
    if hasattr(result, 'get'):
        return result.get('message')
    return None


def _to_int(value):
    try:
        if value is None or value == '':
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _basename(path):
    return str(path or '').replace('\\', '/').split('/')[-1]


def _ext_of(path):
    name = _basename(path)
    if '.' not in name:
        return ''
    return name.rsplit('.', 1)[-1].lower()
