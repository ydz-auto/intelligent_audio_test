# -*- coding: utf-8 -*-
"""
测试结果大数据存储模块

将 result_data 中的重型字段（adjusted_reference_params, raw_results, alignment_info）
拆分写入文件，轻量部分存入数据库，读取时自动合并。
"""

import json
import os
import re

from backend.config.config import Config
from backend.utils.web.log_handler import log_not_emit

HEAVY_KEYS = ['adjusted_reference_params', 'raw_results', 'alignment_info']

_MODULE_NAME = 'result_data_store'


def _sanitize_path(s):
    return re.sub(r'[^a-zA-Z0-9_]', '_', str(s))


def _build_result_dir(task_id, test_case_id, device_sn):
    task_id_safe = _sanitize_path(task_id)
    case_id_safe = _sanitize_path(test_case_id)
    device_sn_safe = _sanitize_path(device_sn)
    return os.path.join(
        Config.STATIC_BASE_PATH,
        'case_result',
        task_id_safe,
        case_id_safe,
        device_sn_safe
    )


def write_result_data_file(task_id, test_case_id, device_sn, result_data):
    """
    将完整的 result_data 写入文件，返回相对路径。

    Args:
        task_id: 任务ID
        test_case_id: 测试用例ID
        device_sn: 设备序列号
        result_data: 完整结果数据字典

    Returns:
        写入成功返回文件的相对路径字符串，失败返回空字符串
    """
    try:
        result_dir = _build_result_dir(task_id, test_case_id, device_sn)
        os.makedirs(result_dir, exist_ok=True)

        file_path = os.path.join(result_dir, 'result_data.json')

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)

        relative_path = os.path.relpath(file_path, Config.STATIC_BASE_PATH)

        log_not_emit(
            'DEBUG', _MODULE_NAME,
            f'write_result_data_file: written to {relative_path}',
            category='system', task_id=task_id, test_case_id=test_case_id
        )

        return relative_path

    except Exception as e:
        log_not_emit(
            'ERROR', _MODULE_NAME,
            f'write_result_data_file failed: {e}',
            category='system', task_id=task_id, test_case_id=test_case_id
        )
        return ''


def read_result_data_file(path):
    """
    从文件读取 result_data 字典。

    Args:
        path: 文件路径（相对路径或绝对路径）

    Returns:
        读取成功返回字典，失败返回空字典
    """
    try:
        if not path:
            return {}

        if not os.path.isabs(path):
            path = os.path.join(Config.STATIC_BASE_PATH, path)

        if not os.path.exists(path):
            log_not_emit(
                'WARNING', _MODULE_NAME,
                f'read_result_data_file: file not found: {path}',
                category='system'
            )
            return {}

        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if isinstance(data, dict):
            return data

        log_not_emit(
            'WARNING', _MODULE_NAME,
            f'read_result_data_file: unexpected data type in {path}',
            category='system'
        )
        return {}

    except Exception as e:
        log_not_emit(
            'ERROR', _MODULE_NAME,
            f'read_result_data_file failed: {e}',
            category='system'
        )
        return {}


def split_result_data(result_data):
    """
    将 result_data 拆分为轻量部分（可安全存入数据库）和重型数据标记。

    Args:
        result_data: 完整结果数据字典

    Returns:
        (lightweight_dict, has_heavy_data) 元组
        lightweight_dict: 去除了重型字段的字典
        has_heavy_data: 布尔值，表示原始数据中是否包含重型字段
    """
    try:
        if not result_data or not isinstance(result_data, dict):
            return result_data or {}, False

        has_heavy_data = False
        lightweight = {}

        for key, value in result_data.items():
            if key in HEAVY_KEYS:
                has_heavy_data = True
            else:
                lightweight[key] = value

        return lightweight, has_heavy_data

    except Exception as e:
        log_not_emit(
            'ERROR', _MODULE_NAME,
            f'split_result_data failed: {e}',
            category='system'
        )
        return result_data or {}, False


def load_full_result_data(result_data_from_db, result_data_path):
    """
    合并数据库中的轻量数据与文件中的完整数据。

    如果 result_data_path 存在且文件可读，直接返回文件中的完整数据。
    否则返回数据库中的原始数据。

    Args:
        result_data_from_db: 数据库中存储的结果数据
        result_data_path: result_data 文件路径

    Returns:
        合并后的完整结果数据字典
    """
    try:
        if result_data_path:
            file_data = read_result_data_file(result_data_path)
            if file_data:
                return file_data

        if result_data_from_db and isinstance(result_data_from_db, dict):
            return result_data_from_db

        return {}

    except Exception as e:
        log_not_emit(
            'ERROR', _MODULE_NAME,
            f'load_full_result_data failed: {e}',
            category='system'
        )
        return result_data_from_db if isinstance(result_data_from_db, dict) else {}
