# -*- coding: utf-8 -*-
"""
input_asr.py
输入识别准确率计算：将参考参数 JSON 中的 query 文本与设备驱动 get_results() 返回的 question 对比

数据来源:
    - query   : 参考参数 JSON 中的 query 字段（与 pause 同源，由主服务预生成存盘）
                例如: "query": "home and bull at home and work from home and everything I don't know I wonder if it will have like um generation impact"
    - question : harmony_xiaoyichat.get_results() 返回的 question 字段
                 (设备端小艺聊天界面识别到的用户提问文本)

判定方式:
    - 对两段文本做归一化（转小写、去标点、压缩空白）
    - 使用 difflib.SequenceMatcher 计算相似度
    - 相似度 >= SIMILARITY_THRESHOLD(默认 0.8) 视为匹配成功
"""
import re
import logging
import difflib

logger = logging.getLogger(__name__)

# 相似度阈值，达到则视为匹配成功
SIMILARITY_THRESHOLD = 0.8


def _normalize_text(text):
    """文本归一化：转小写、去标点、压缩空白"""
    if not text:
        return ''
    # 转小写
    text = text.lower()
    # 去标点符号（保留中文字符、字母、数字、空格）
    text = re.sub(r'[^\w\s\u4e00-\u9fff]', '', text)
    # 压缩多余空白
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def compute_input_asr_match(query, question, threshold=SIMILARITY_THRESHOLD):
    """对比参考 query 与设备识别 question 的文本相似度

    Args:
        query (str): 参考参数 JSON 中的 query 文本（输入音频对应的原始文本）
        question (str|None): harmony_xiaoyichat.get_results() 返回的 question
                             （设备端识别到的用户提问文本）
        threshold (float): 相似度阈值，默认 0.8

    Returns:
        dict: {
            'match': bool,              是否匹配成功（相似度 >= 阈值）
            'similarity': float,        归一化后相似度 (0.0 ~ 1.0)
            'query_original': str,     原始 query 文本
            'question_original': str,   原始 question 文本
            'query_normalized': str,    归一化后的 query
            'question_normalized': str, 归一化后的 question
            'threshold': float,        相似度阈值
            'message': str,            错误/成功说明
        }
    """
    result = {
        'match': False,
        'similarity': 0.0,
        'query_original': query or '',
        'question_original': question or '',
        'query_normalized': '',
        'question_normalized': '',
        'threshold': threshold,
        'message': '',
    }

    if not query:
        result['message'] = 'query 为空, 无法对比'
        logger.warning(result['message'])
        return result

    if not question:
        result['message'] = 'question 为空, 设备未识别到用户提问文本'
        logger.warning(result['message'])
        return result

    # 归一化
    query_norm = _normalize_text(query)
    question_norm = _normalize_text(question)
    result['query_normalized'] = query_norm
    result['question_normalized'] = question_norm

    # 计算相似度
    similarity = difflib.SequenceMatcher(None, query_norm, question_norm).ratio()
    result['similarity'] = round(similarity, 3)

    # 判定
    if similarity >= threshold:
        result['match'] = True
        result['message'] = f'问题ASR识别正常, 相似度={similarity:.3f}'
    else:
        result['match'] = False
        result['message'] = f'问题ASR识别异常, 相似度={similarity:.3f} < 阈值={threshold}'

    logger.info(
        f"[input_asr] query_normalized={query_norm!r} "
        f"question_normalized={question_norm!r} "
        f"similarity={similarity:.3f} match={result['match']}"
    )
    return result
