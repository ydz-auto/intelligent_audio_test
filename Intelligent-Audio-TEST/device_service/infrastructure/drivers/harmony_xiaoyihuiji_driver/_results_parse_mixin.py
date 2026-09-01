# -*- coding: utf-8 -*-
"""存档结果解析混入（小艺慧记驱动）

负责 extract_results_from_archive：从 OSS 下载 ASR 日志存档，
编排 _asr_parsers 纯函数完成 STM / RTTM 提取、时间戳偏移与 speaker id 映射，
生成实时/非实时两类结果并回传 OSS。
"""
import logging
import os
import shutil
import tempfile
from pathlib import Path

from shared.infrastructure.storage import storage
from ._asr_parsers import (
    add_offset_to_rttm,
    add_offset_to_stm,
    apply_idmap_to_rttm,
    apply_idmap_to_stm,
    build_complete_idmap,
    collect_all_speaker_ids,
    extract_idmap_from_asr,
    extract_rttm_from_asr,
    extract_stm_from_asr,
    get_first_log_timestamp,
    get_first_timestamp,
    get_last_timestamp,
    parse_filename_timestamp,
    sanitize_path,
)

logger = logging.getLogger(__name__)

# 实时结果（recording）的固定占位字段
_RECORDING_RESULT_FIELDS = {
    "result_type": "real-time",
    "meeting_minutes_path": "dummy/meeting_minutes.txt",
    "meeting_minutes_content": "会议纪要内容",
    "recording_asr_path": '',
    "recording_asr_content": '',
    "log_path": None,      # 已清理本地临时目录，保留字段兼容旧调用
    "local_dir": None,     # 已清理本地临时目录，保留字段兼容旧调用
}

# 非实时结果（fix）的固定占位字段
_FIX_RESULT_FIELDS = {
    "result_type": "non-real-time",
    "meeting_minutes_path": "dummy/meeting_minutes.txt",
    "meeting_minutes_content": "会议纪要内容",
    "fix_asr_path": '',
    "fix_asr_content": '',
    "log_path": None,      # 已清理本地临时目录，保留字段兼容旧调用
    "local_dir": None,     # 已清理本地临时目录，保留字段兼容旧调用
}

# 判定拼接间隙过大的阈值（秒）
_STITCH_GAP_WARNING_SECONDS = 10


class ResultsParseMixin:
    """存档日志解析方法（extract_results_from_archive）"""

    def extract_results_from_archive(self, task_id, test_case_id, device_sn, **kwargs):
        """从存档日志文件提取设备输出结果

        Args:
            task_id: 任务ID
            test_case_id: 用例ID
            device_sn: 设备序列号

        Returns:
            list[dict]: 包含实时/非实时两类提取结果的列表
        """
        # 改造为 OSS 存储：从 OSS 下载 log 目录下 asr 文件到本地临时，处理后写 stm/rttm 上传 OSS，清理本地临时
        task_id_sanitized = sanitize_path(task_id)
        case_id_sanitized = sanitize_path(test_case_id)

        oss_key_prefix = f'{task_id_sanitized}/{case_id_sanitized}/{device_sn}'
        local_dir = tempfile.mkdtemp(prefix=f'archive_{task_id_sanitized}_{case_id_sanitized}_')
        log_dir = Path(local_dir) / "log"
        log_dir.mkdir(parents=True, exist_ok=True)

        asr_files = self._download_oss_logs(oss_key_prefix, log_dir, task_id, test_case_id)
        if asr_files is None:
            return [{
                'success': False,
                'message': f'存档日志目录不存在(OSS): {oss_key_prefix}/log/',
                'local_dir': None,
                'oss_prefix': oss_key_prefix,
            }]

        # 多文件时间戳对齐：按文件名时间戳去重，再按日志时间戳计算相对偏移
        asr_files_dedup, offsets = self._align_asr_files(asr_files, task_id, test_case_id)

        # 提取实时（final）结果
        recording_stm_lines, recording_rttm_lines = self._extract_recording_lines(
            asr_files_dedup, offsets, task_id, test_case_id
        )

        # 构建 speaker id 全局映射
        complete_idmap = self._build_global_idmap(asr_files_dedup, task_id, test_case_id)

        # 提取修正（vprFix 优先，final 兜底）结果
        fix_stm_lines, fix_rttm_lines = self._extract_fix_lines(
            asr_files_dedup, offsets, complete_idmap, task_id, test_case_id
        )

        self._log(level='INFO', content=f"最终ASR STM: {len(recording_stm_lines)} 条", task_id=task_id, test_case_id=test_case_id)
        self._log(level='INFO', content=f"最终Fix STM: {len(fix_stm_lines)} 条", task_id=task_id, test_case_id=test_case_id)

        # 写入 stm/rttm 文件并上传 OSS，随后清理本地临时目录
        recording_stm_path, recording_rttm_path, fix_stm_path, fix_rttm_path = self._write_and_upload_files(
            local_dir, oss_key_prefix,
            recording_stm_lines, recording_rttm_lines,
            fix_stm_lines, fix_rttm_lines,
        )

        recording_result = {
            **_RECORDING_RESULT_FIELDS,
            "success": True,
            "message": "Success",
            "recording_stm_path": recording_stm_path,
            "recording_stm_content": "\n".join(recording_stm_lines),
            "recording_rttm_path": recording_rttm_path,
            "recording_rttm_content": "\n".join(recording_rttm_lines),
            "oss_prefix": oss_key_prefix,
        }

        fix_result = {
            **_FIX_RESULT_FIELDS,
            "success": True,
            "message": "Success",
            "fix_stm_path": fix_stm_path,
            "fix_stm_content": "\n".join(fix_stm_lines),
            "fix_rttm_path": fix_rttm_path,
            "fix_rttm_content": "\n".join(fix_rttm_lines),
            "oss_prefix": oss_key_prefix,
        }

        return [recording_result, fix_result]

    def _download_oss_logs(self, oss_key_prefix, log_dir, task_id, test_case_id):
        """从 OSS 下载 log/ 前缀下的所有 ASR 对象到本地临时目录

        Returns:
            list[Path]: asr-*.txt 文件列表；OSS 为空时返回 None
        """
        oss_log_prefix = f'{oss_key_prefix}/log/'
        try:
            oss_keys = storage.list_objects('case_result', prefix=oss_log_prefix)
        except Exception as e:
            self._log(level='ERROR', content=f"列出OSS log对象失败: {oss_log_prefix}, error: {e}", task_id=task_id, test_case_id=test_case_id)
            oss_keys = []
        for k in oss_keys:
            fname = k[len(oss_log_prefix):] if k.startswith(oss_log_prefix) else os.path.basename(k)
            if fname:
                try:
                    storage.load_file(storage.build_path('case_result', k), str(log_dir / fname))
                except Exception as e:
                    self._log(level='WARNING', content=f"下载OSS对象失败: {k}, error: {e}", task_id=task_id, test_case_id=test_case_id)

        self._log(level='INFO', content=f"从存档提取结果，OSS log 前缀: {oss_log_prefix}, 本地临时: {log_dir}", task_id=task_id, test_case_id=test_case_id)

        if not any(log_dir.iterdir()):
            shutil.rmtree(str(log_dir.parent), ignore_errors=True)
            self._log(level='ERROR', content=f"存档日志目录为空(OSS): {oss_log_prefix}", task_id=task_id, test_case_id=test_case_id)
            return None

        return list(log_dir.glob("asr-*.txt"))

    def _align_asr_files(self, asr_files, task_id, test_case_id):
        """多 ASR 文件的时间戳对齐

        1. 计算每个文件的时间戳（优先日志内时间戳，兜底文件名时间戳）
        2. 按文件名时间戳去重（同时间戳保留较大文件）
        3. 计算各文件相对首个文件的时间偏移

        Returns:
            (list[dict], dict): 去重排序后的文件信息列表 / {索引: 偏移秒数}
        """
        asr_files_with_ts = []
        for f in asr_files:
            log_ts = get_first_log_timestamp(str(f))
            filename_ts = parse_filename_timestamp(f.name)
            self._log(level='DEBUG', content=f"文件时间戳: {f.name} -> 文件名={filename_ts}s, 日志={log_ts}s", task_id=task_id, test_case_id=test_case_id)
            ts = log_ts if log_ts is not None else filename_ts
            asr_files_with_ts.append({'file': f, 'timestamp': ts, 'filename_ts': filename_ts, 'size': f.stat().st_size})

        asr_files_with_ts.sort(key=lambda x: x['filename_ts'])

        asr_files_dedup = []
        i = 0
        while i < len(asr_files_with_ts):
            if i + 1 < len(asr_files_with_ts) and asr_files_with_ts[i]['filename_ts'] == asr_files_with_ts[i + 1]['filename_ts']:
                smaller = asr_files_with_ts[i] if asr_files_with_ts[i]['size'] < asr_files_with_ts[i + 1]['size'] else asr_files_with_ts[i + 1]
                larger = asr_files_with_ts[i] if smaller == asr_files_with_ts[i + 1] else asr_files_with_ts[i + 1]
                self._log(level='INFO', content=f"移除重复时间戳文件: {smaller['file'].name} (文件名时间戳相同，文件更小)", task_id=task_id, test_case_id=test_case_id)
                asr_files_dedup.append(larger)
                i += 2
            else:
                asr_files_dedup.append(asr_files_with_ts[i])
                i += 1
        asr_files_dedup.sort(key=lambda x: x['timestamp'])

        offsets = {}
        if len(asr_files_dedup) >= 2:
            ts_base = asr_files_dedup[0]['timestamp']
            for idx in range(1, len(asr_files_dedup)):
                ts_current = asr_files_dedup[idx]['timestamp']
                offsets[idx] = float(ts_current - ts_base)
                self._log(level='INFO', content=f"ASR{idx}相对ASR0时间戳差值: {ts_current} - {ts_base} = {offsets[idx]}s", task_id=task_id, test_case_id=test_case_id)

        return asr_files_dedup, offsets

    def _apply_offset(self, stm_lines, rttm_lines, idx, offsets, tag, task_id, test_case_id):
        """按需给 STM/RTTM 行添加时间偏移并记录日志"""
        if idx in offsets and offsets[idx] > 0:
            stm_lines = add_offset_to_stm(stm_lines, offsets[idx])
            rttm_lines = add_offset_to_rttm(rttm_lines, offsets[idx])
            self._log(level='INFO', content=f"{tag}ASR{idx}已添加offset: {offsets[idx]}s", task_id=task_id, test_case_id=test_case_id)
        return stm_lines, rttm_lines

    def _extract_recording_lines(self, asr_files_dedup, offsets, task_id, test_case_id):
        """提取实时（final）结果的 STM/RTTM 行，并检查拼接间隙"""
        recording_stm_lines = []
        recording_rttm_lines = []

        for idx, asr_info in enumerate(asr_files_dedup):
            asr_file = asr_info['file']
            stm_lines = extract_stm_from_asr(asr_file, asr_file.stem, "final")
            rttm_lines = extract_rttm_from_asr(asr_file, asr_file.stem, "final")

            stm_lines, rttm_lines = self._apply_offset(stm_lines, rttm_lines, idx, offsets, "", task_id, test_case_id)

            first_ts = get_first_timestamp(stm_lines) if stm_lines else None
            last_ts = get_last_timestamp(stm_lines) if stm_lines else None
            self._log(
                level='DEBUG',
                content=f"ASR{idx} 首末时间戳: first={first_ts}, last={last_ts}",
                task_id=task_id, test_case_id=test_case_id
            )

            recording_stm_lines.extend(stm_lines)
            recording_rttm_lines.extend(rttm_lines)

        if len(asr_files_dedup) > 1:
            for i in range(len(recording_stm_lines) - 1):
                gap = get_first_timestamp([recording_stm_lines[i + 1]]) - get_last_timestamp([recording_stm_lines[i]])
                if gap and gap > _STITCH_GAP_WARNING_SECONDS:
                    self._log(level='WARNING', content=f"ASR拼接后间隙>{gap}s", task_id=task_id, test_case_id=test_case_id)

        return recording_stm_lines, recording_rttm_lines

    def _build_global_idmap(self, asr_files_dedup, task_id, test_case_id):
        """构建 speaker id 全局映射（收集所有 id + 各文件 idMap 补全）"""
        all_speaker_ids = collect_all_speaker_ids([info['file'] for info in asr_files_dedup])
        self._log(level='INFO', content=f"收集到所有speaker id: {all_speaker_ids}", task_id=task_id, test_case_id=test_case_id)

        global_idmap = []
        for asr_info in asr_files_dedup:
            asr_file = asr_info['file']
            file_idmap = extract_idmap_from_asr(asr_file)
            if file_idmap:
                global_idmap = file_idmap
                self._log(level='INFO', content=f"从{asr_file.name}获取到idMap: {global_idmap}", task_id=task_id, test_case_id=test_case_id)
                break

        complete_idmap = build_complete_idmap(all_speaker_ids, global_idmap)
        self._log(level='INFO', content=f"完整speaker id映射: {complete_idmap}", task_id=task_id, test_case_id=test_case_id)
        return complete_idmap

    def _extract_fix_lines(self, asr_files_dedup, offsets, complete_idmap, task_id, test_case_id):
        """提取修正（vprFix 优先，final 兜底）结果的 STM/RTTM 行"""
        fix_stm_lines = []
        fix_rttm_lines = []

        for idx, asr_info in enumerate(asr_files_dedup):
            asr_file = asr_info['file']

            has_vpr_fix = bool(extract_stm_from_asr(asr_file, asr_file.stem, "vprFix"))
            if has_vpr_fix:
                file_id = "fix_" + asr_file.stem[4:]
                asr_type = "vprFix"
                self._log(level='INFO', content=f"Fix ASR{idx} 使用vprFix数据，file_id: {file_id}", task_id=task_id, test_case_id=test_case_id)
            else:
                file_id = asr_file.stem
                asr_type = "final"
                self._log(level='INFO', content=f"Fix ASR{idx} 无vprFix数据，使用final填充，file_id: {file_id}", task_id=task_id, test_case_id=test_case_id)

            stm_lines = extract_stm_from_asr(asr_file, file_id, asr_type)
            rttm_lines = extract_rttm_from_asr(asr_file, file_id, asr_type)

            stm_lines = apply_idmap_to_stm(stm_lines, complete_idmap)
            rttm_lines = apply_idmap_to_rttm(rttm_lines, complete_idmap)

            stm_lines, rttm_lines = self._apply_offset(stm_lines, rttm_lines, idx, offsets, "Fix ", task_id, test_case_id)

            fix_stm_lines.extend(stm_lines)
            fix_rttm_lines.extend(rttm_lines)

        return fix_stm_lines, fix_rttm_lines

    def _write_and_upload_files(self, local_dir, oss_key_prefix,
                                recording_stm_lines, recording_rttm_lines,
                                fix_stm_lines, fix_rttm_lines):
        """写入 STM/RTTM 文件并上传 OSS，随后清理本地临时目录

        Returns:
            tuple: (recording_stm_path, recording_rttm_path, fix_stm_path, fix_rttm_path)
        """
        recording_stm_path = os.path.join(local_dir, 'recording.stm')
        recording_rttm_path = os.path.join(local_dir, 'recording.rttm')
        fix_stm_path = os.path.join(local_dir, 'fix.stm')
        fix_rttm_path = os.path.join(local_dir, 'fix.rttm')

        with open(recording_stm_path, "w", encoding="utf-8") as f:
            f.write("\n".join(recording_stm_lines))
        with open(recording_rttm_path, "w", encoding="utf-8") as f:
            f.write("\n".join(recording_rttm_lines))
        with open(fix_stm_path, "w", encoding="utf-8") as f:
            f.write("\n".join(fix_stm_lines))
        with open(fix_rttm_path, "w", encoding="utf-8") as f:
            f.write("\n".join(fix_rttm_lines))

        # 写完后上传 stm/rttm 到 OSS，然后清理本地临时目录
        for fname in os.listdir(local_dir):
            storage.save_file(os.path.join(local_dir, fname), 'case_result',
                             f'{oss_key_prefix}/{fname}')
        shutil.rmtree(local_dir, ignore_errors=True)

        return recording_stm_path, recording_rttm_path, fix_stm_path, fix_rttm_path
