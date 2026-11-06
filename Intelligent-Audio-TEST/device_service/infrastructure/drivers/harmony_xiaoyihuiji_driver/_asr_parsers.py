# -*- coding: utf-8 -*-
"""ASR 日志纯函数解析器（小艺慧记驱动）

从 ASR 原始日志中解析 STM / RTTM / idMap，以及时间戳偏移等纯文本处理工具。
均为无副作用纯函数：输入文件路径/行列表，输出解析结果，不依赖任何实例状态。
"""
import json
import logging
import re

logger = logging.getLogger(__name__)

# ASR 日志中 parseAsrResponse 的统一匹配模式
ASR_RESPONSE_PATTERN = (
    r'(\d{1,2}/\d{1,2}/\d{4}, \d{1,2}:\d{2}:\d{2} [AP]M)'
    r'\s*pauseTime:\d+   parseAsrResponse:\s*\n\s*(\s*\{[\s\S]*?\})\s*(?=\n|$)'
)

# 日志时间戳格式（如 3/25/2026, 3:55:52 PM）
LOG_TIMESTAMP_FORMAT = "%m/%d/%Y, %I:%M:%S %p"

# ASR 日志文件名时间戳长度 -> (时,分,秒) 的切片位置
TS_LENGTH_TO_SLICES = {
    13: (7, 9, 9, 11, 11, 13),
    12: (6, 8, 8, 10, 10, 12),
    14: (8, 10, 10, 12, 12, 14),
}


def sanitize_path(s):
    """将路径相关字符串中的非法字符替换为下划线"""
    return re.sub(r'[^a-zA-Z0-9_]', '_', str(s))


def ms10_to_seconds(ms):
    """10ms 单位转秒"""
    return ms / 100.0


def ms_to_seconds(ms):
    """毫秒转秒"""
    return ms / 1000.0


def extract_stm_from_asr(filepath, file_id, asr_type="final"):
    """从 ASR 日志提取 STM 行

    Args:
        filepath: ASR 日志文件路径
        file_id: STM 行首列的文件标识
        asr_type: 提取的 ASR 类型（final / vprFix）
    Returns:
        list[str]: STM 行列表
    """
    stm_lines = []
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    matches = re.finditer(ASR_RESPONSE_PATTERN, content)
    for match in matches:
        json_str = match.group(2).strip()
        try:
            json_obj = json.loads(json_str)
            json_asr_type = json_obj.get("asrType", "")
            if json_asr_type != asr_type:
                continue
            directives = json_obj.get("asrResult", {}).get("directives", [])
            for directive in directives:
                payload = directive.get("payload", {})
                if asr_type == "final":
                    speaker_items = payload.get("speakerInfo", [])
                else:
                    speaker_items = payload.get("content", {}).get("speakInfo", [])
                    if not speaker_items:
                        speaker_items = payload.get("speakInfo", [])
                for item in speaker_items:
                    stm_lines.append(_build_stm_line(item, file_id))
        except Exception:
            logger.debug("从 ASR 提取 STM 行失败 filepath=%s file_id=%s", filepath, file_id, exc_info=True)
    return stm_lines


def _build_stm_line(item, file_id):
    """由 speaker 条目构建单条 STM 行"""
    speaker = item.get("speaker", "unknown")
    word = item.get("word", "").strip()
    vad_info = item.get("vadInfo", {})
    start_ms = int(vad_info.get("start_of_speech", 0))
    end_ms = int(vad_info.get("end_of_speech", 0))
    if word and end_ms > start_ms:
        start_sec = ms10_to_seconds(start_ms)
        end_sec = ms10_to_seconds(end_ms)
        return f"{file_id} 1 speaker{speaker} {start_sec:.3f} {end_sec:.3f} {word}"
    return None


def extract_rttm_from_asr(filepath, file_id, asr_type="final"):
    """从 ASR 日志提取 RTTM 行

    Args:
        filepath: ASR 日志文件路径
        file_id: RTTM 行中的音频标识
        asr_type: 提取的 ASR 类型（final / vprFix）
    Returns:
        list[str]: RTTM 行列表
    """
    rttm_lines = []
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    matches = re.finditer(ASR_RESPONSE_PATTERN, content)
    for match in matches:
        json_str = match.group(2).strip()
        try:
            json_obj = json.loads(json_str)
            json_asr_type = json_obj.get("asrType", "")
            if json_asr_type != asr_type:
                continue
            directives = json_obj.get("asrResult", {}).get("directives", [])
            for directive in directives:
                payload = directive.get("payload", {})
                if asr_type == "final":
                    speaker_items = payload.get("speakerInfo", [])
                else:
                    speaker_items = payload.get("content", {}).get("speakInfo", [])
                    if not speaker_items:
                        speaker_items = payload.get("speakInfo", [])
                for item in speaker_items:
                    rttm_lines.append(_build_rttm_line(item, file_id))
        except Exception:
            logger.debug("从 ASR 提取 RTTM 行失败 filepath=%s file_id=%s", filepath, file_id, exc_info=True)
    return rttm_lines


def _build_rttm_line(item, file_id):
    """由 speaker 条目构建单条 RTTM 行"""
    speaker = item.get("speaker", "unknown")
    vad_info = item.get("vadInfo", {})
    start_ms = int(vad_info.get("start_of_speech", 0))
    end_ms = int(vad_info.get("end_of_speech", 0))
    if end_ms > start_ms:
        start_sec = ms10_to_seconds(start_ms)
        duration = ms10_to_seconds(end_ms - start_ms)
        return f"SPEAKER {file_id} 1 {start_sec:.3f} {duration:.3f} <NA> <NA> speaker{speaker} <NA>"
    return None


def extract_idmap_from_asr(filepath):
    """从 asr 文件中提取 vprFix 的 idMap"""
    id_map = []
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    matches = re.finditer(ASR_RESPONSE_PATTERN, content)
    for match in matches:
        json_str = match.group(2).strip()
        try:
            json_obj = json.loads(json_str)
            if json_obj.get("asrType") == "vprFix":
                directives = json_obj.get("asrResult", {}).get("directives", [])
                for directive in directives:
                    payload = directive.get("payload", {})
                    content_data = payload.get("content", {})
                    id_map = content_data.get("idMap", [])
                    if id_map:
                        return id_map
        except Exception:
            logger.debug("从 ASR 提取 idMap 失败 filepath=%s", filepath, exc_info=True)
    return id_map


def collect_all_speaker_ids(asr_files_list):
    """收集所有 asr 文件中的 speaker id"""
    all_ids = set()
    for asr_file in asr_files_list:
        with open(asr_file, "r", encoding="utf-8") as f:
            content = f.read()
        matches = re.finditer(ASR_RESPONSE_PATTERN, content)
        for match in matches:
            json_str = match.group(2).strip()
            try:
                json_obj = json.loads(json_str)
                asr_type = json_obj.get("asrType", "")
                if asr_type in ["final", "vprFix"]:
                    _collect_speaker_ids_from_directives(json_obj, asr_type, all_ids)
            except Exception:
                logger.debug("收集 speaker id 失败 asr_file=%s", asr_file, exc_info=True)
    return sorted(all_ids)


def _collect_speaker_ids_from_directives(json_obj, asr_type, all_ids):
    """从单个 ASR 响应的 directives 中收集 speaker id"""
    directives = json_obj.get("asrResult", {}).get("directives", [])
    for directive in directives:
        payload = directive.get("payload", {})
        if asr_type == "final":
            speaker_items = payload.get("speakerInfo", [])
        else:
            speaker_items = payload.get("content", {}).get("speakInfo", [])
            if not speaker_items:
                speaker_items = payload.get("speakInfo", [])
        for item in speaker_items:
            all_ids.add(int(item.get("speaker", 1)))


def build_complete_idmap(all_ids, idmap):
    """构建完整的 id 映射，包含 idMap 中没有的 id"""
    if not idmap:
        return {id_: id_ for id_ in all_ids}
    mapping = {item["oldId"]: item["newId"] for item in idmap}
    used_new_ids = set(mapping.values())
    next_id = max(used_new_ids) + 1 if used_new_ids else 1
    for old_id in all_ids:
        if old_id not in mapping:
            while next_id in used_new_ids:
                next_id += 1
            mapping[old_id] = next_id
            used_new_ids.add(next_id)
            next_id += 1
    return mapping


def apply_idmap_to_stm(stm_lines, id_mapping):
    """根据 idMap 替换 STM 行中的 speaker id"""
    if not id_mapping:
        return stm_lines
    result = []
    for line in stm_lines:
        parts = line.split()
        if len(parts) >= 3:
            speaker = parts[2]
            if speaker.startswith("speaker"):
                old_id = int(speaker[7:])
                new_id = id_mapping.get(old_id, old_id)
                parts[2] = f"speaker{new_id}"
                result.append(" ".join(parts))
            else:
                result.append(line)
        else:
            result.append(line)
    return result


def apply_idmap_to_rttm(rttm_lines, id_mapping):
    """根据 idMap 替换 RTTM 行中的 speaker id"""
    if not id_mapping:
        return rttm_lines
    result = []
    for line in rttm_lines:
        parts = line.split()
        if len(parts) >= 8:
            speaker = parts[7]
            if speaker.startswith("speaker"):
                old_id = int(speaker[7:])
                new_id = id_mapping.get(old_id, old_id)
                parts[7] = f"speaker{new_id}"
                result.append(" ".join(parts))
            else:
                result.append(line)
        else:
            result.append(line)
    return result


def parse_filename_timestamp(filename):
    """从文件名解析时间戳，返回当天秒数

    文件名形如 asr-<时间戳>，时间戳长度 12/13/14 位，
    时分秒分别位于不同切片位置。
    """
    match = re.match(r'asr-(\d+)', filename)
    if match:
        ts_str = match.group(1)
        slices = TS_LENGTH_TO_SLICES.get(len(ts_str))
        if slices:
            h_start, h_end, m_start, m_end, s_start, s_end = slices
            hour = int(ts_str[h_start:h_end])
            minute = int(ts_str[m_start:m_end])
            second = int(ts_str[s_start:s_end])
            return hour * 3600 + minute * 60 + second
    return 0


def parse_log_timestamp(log_timestamp_str):
    """解析日志中的时间戳字符串，返回当天秒数

    格式如: 3/25/2026, 3:55:52 PM 或 3/20/2026, 5:46:50 PM
    """
    from datetime import datetime
    try:
        dt = datetime.strptime(log_timestamp_str.strip(), LOG_TIMESTAMP_FORMAT)
        return dt.hour * 3600 + dt.minute * 60 + dt.second
    except Exception as e:
        logger.debug("解析日志时间戳失败: %s, error: %s", log_timestamp_str, e)
        return 0


def get_first_log_timestamp(filepath):
    """从日志文件中获取第一个 parseAsrResponse 的时间戳，返回当天秒数"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        match = re.search(ASR_RESPONSE_PATTERN, content)
        if match:
            log_ts_str = match.group(1)
            return parse_log_timestamp(log_ts_str)
    except Exception as e:
        logger.debug("获取日志文件时间戳失败: %s, error: %s", filepath, e)
    return None


def get_first_timestamp(stm_lines):
    """获取 STM 行列表中首行的时间戳（起始时刻）"""
    if not stm_lines:
        return None
    parts = stm_lines[0].split()
    if len(parts) >= 4:
        return float(parts[3])
    return None


def get_last_timestamp(stm_lines):
    """获取 STM 行列表中末行的时间戳（结束时刻）"""
    if not stm_lines:
        return None
    parts = stm_lines[-1].split()
    if len(parts) >= 5:
        return float(parts[4])
    return None


def add_offset_to_stm(stm_lines, offset):
    """给 STM 行添加时间偏移"""
    result = []
    for line in stm_lines:
        parts = line.split()
        if len(parts) >= 5:
            new_start = float(parts[3]) + offset
            new_end = float(parts[4]) + offset
            parts[3] = f"{new_start:.3f}"
            parts[4] = f"{new_end:.3f}"
            result.append(" ".join(parts))
        else:
            result.append(line)
    return result


def add_offset_to_rttm(rttm_lines, offset):
    """给 RTTM 行添加时间偏移"""
    result = []
    for line in rttm_lines:
        parts = line.split()
        if len(parts) >= 5:
            new_start = float(parts[3]) + offset
            duration = float(parts[4])
            parts[3] = f"{new_start:.3f}"
            result.append(" ".join(parts))
        else:
            result.append(line)
    return result
