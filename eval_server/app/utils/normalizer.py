# -*- coding: utf-8 -*-
"""
文本正则化工具模块

支持中英文文本正则化（可选库）：
- 中文: tn.chinese.normalizer
- 英文: nemo_text_processing.text_normalization

如果库不可用，则返回原文本
"""

import re
import logging

logger = logging.getLogger(__name__)

TN_CHINESE_AVAILABLE = False
NEMO_AVAILABLE = False

try:
    from tn.chinese.normalizer import TextNormalizer
    TN_CHINESE_AVAILABLE = True
    _tn_normalizer = TextNormalizer()
except ImportError:
    _tn_normalizer = None

try:
    from nemo_text_processing.text_normalization.normalize import normalize as nemo_normalize
    NEMO_AVAILABLE = True
except ImportError:
    nemo_normalize = None


def normalize_chinese(text):
    """
    中文文本正则化

    Args:
        text (str): 输入文本

    Returns:
        str: 正则化后的文本，如果失败则返回原文本
    """
    if not text:
        return text

    if TN_CHINESE_AVAILABLE and _tn_normalizer is not None:
        try:
            return _tn_normalizer.normalize(text)
        except Exception as e:
            logger.warning(f"TN Chinese normalization failed: {e}")
            return text
    return text


def normalize_english(text, lang='en'):
    """
    英文文本正则化

    Args:
        text (str): 输入文本
        lang (str): 语言代码，默认 'en'

    Returns:
        str: 正则化后的文本，如果失败则返回原文本
    """
    if not text:
        return text

    if NEMO_AVAILABLE and nemo_normalize is not None:
        try:
            return nemo_normalize(text, lang=lang)
        except Exception as e:
            logger.warning(f"Nemo English normalization failed: {e}")
            return text
    return text


def normalize_text(text):
    """
    统一的中英文文本正则化函数
    将字符串中的中文和英文分开处理，然后合并返回

    Args:
        text (str): 输入文本（可能包含中文和英文）

    Returns:
        str: 正则化后的完整句子
    """
    if not text:
        return text

    chinese_pattern = re.compile(r'[\u4e00-\u9fff]+')
    english_pattern = re.compile(r'[a-zA-Z]+')
    other_pattern = re.compile(r'[^a-zA-Z\u4e00-\u9fff]+')

    result_parts = []
    last_end = 0

    for zh_match in chinese_pattern.finditer(text):
        if zh_match.start() > last_end:
            other_part = text[last_end:zh_match.start()]
            result_parts.append(other_part)

        zh_text = zh_match.group()
        normalized_zh = normalize_chinese(zh_text)
        result_parts.append(normalized_zh)
        last_end = zh_match.end()

    if last_end < len(text):
        result_parts.append(text[last_end:])

    final_result = ''.join(result_parts)
    final_result = english_pattern.sub(
        lambda m: normalize_english(m.group()),
        final_result
    )

    return final_result


def normalize_stm_text(stm_content):
    """
    正则化 STM 内容中的文本部分

    STM 格式: file_id channel speaker start_time end_time <o> text

    Args:
        stm_content (str): STM 格式的内容

    Returns:
        str: 正则化后的 STM 内容
    """
    if not stm_content:
        return stm_content

    lines = stm_content.strip().split('\n')
    normalized_lines = []

    for line in lines:
        line = line.strip()
        if not line or line.startswith(';'):
            normalized_lines.append(line)
            continue

        parts = line.split()
        if len(parts) >= 6:
            file_id = parts[0]
            channel = parts[1]
            speaker = parts[2]
            start_time = parts[3]
            end_time = parts[4]
            text_part = ' '.join(parts[5:])

            normalized_text = normalize_text(text_part)

            normalized_line = f"{file_id} {channel} {speaker} {start_time} {end_time} <o> {normalized_text}"
            normalized_lines.append(normalized_line)
        else:
            normalized_lines.append(line)

    return '\n'.join(normalized_lines)


def normalize_rttm_speaker(rttm_content):
    """
    正则化 RTTM 内容（实际上 RTTM 不含文本，只需做基本清理）

    Args:
        rttm_content (str): RTTM 格式的内容

    Returns:
        str: 清理后的 RTTM 内容
    """
    if not rttm_content:
        return rttm_content

    lines = rttm_content.strip().split('\n')
    normalized_lines = []

    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        normalized_lines.append(line)

    return '\n'.join(normalized_lines)
