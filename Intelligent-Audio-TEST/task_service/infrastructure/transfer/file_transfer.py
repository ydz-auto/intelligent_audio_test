# -*- coding: utf-8 -*-
"""导出文件收集 / 导入文件回写（基础设施层：统一存储抽象，禁止假设本地路径）

- result_data: storage 类别 case_result，key {task_id}/{case_id}/{device_sn}/result_data.json
- ref_params:  storage 类别 ref_params，key {test_case_id}/round_{n}.json
- audios:      storage 类别 audios（Audio.file_path 指向的存储路径）
"""
from typing import Dict, Iterator, List, Tuple

from shared.constants.data_transfer import (
    STORAGE_CATEGORY_AUDIOS,
    STORAGE_CATEGORY_CASE_RESULT,
    STORAGE_CATEGORY_REF_PARAMS,
)
from shared.infrastructure.storage import storage
from shared.utils.data_transfer import parse_storage_path, safe_storage_key
from shared.utils.log_handler import log_not_emit
from shared.utils.result_data_store import _RESULT_BUCKET

_MODULE_NAME = 'transfer_file_store'

_REF_PARAMS_BUCKET = 'ref_params'  # 与 testcase_crud_service 保持一致


def iter_result_file_entries(result_rows: List[dict]) -> Iterator[Tuple[str, bytes]]:
    """按导出时 task_id 的相对路径产出结果文件条目 (name, bytes)。

    name 形如 case_results/{task_id}/{case_id}/{device_sn}/result_data.json。
    单个文件缺失记 warning 跳过（不中断导出，manifest fileCount 反映实际打包数）。
    """
    for row in result_rows:
        path = row.get('result_data_path')
        if not path:
            continue
        category, key = parse_storage_path(path)
        if not key:
            continue
        try:
            data = storage.load_bytes(path)
        except Exception as e:
            log_not_emit('WARNING', _MODULE_NAME,
                         f'结果文件读取失败，跳过: {path}: {e}', category='system')
            continue
        if category and category != _RESULT_BUCKET:
            # 非 case_result 类别的路径按原类别归档，避免覆盖混淆
            name = f'case_results/__other__/{category}/{key}'
        else:
            name = f'case_results/{key}'
        yield name, data


def iter_ref_params_entries(ref_params_lists: List[List[dict]]) -> Iterator[Tuple[str, bytes]]:
    """从测试用例的 reference_params 列表产出参考参数文件条目。

    Args:
        ref_params_lists: 每个用例的 reference_params JSON（[{round_number, reference_params_path}]）
    """
    for ref_list in ref_params_lists or []:
        if not isinstance(ref_list, list):
            continue
        for item in ref_list:
            path = (item or {}).get('reference_params_path')
            if not path:
                continue
            _category, key = parse_storage_path(path)
            if not key:
                continue
            try:
                data = storage.load_bytes(path)
            except Exception as e:
                log_not_emit('WARNING', _MODULE_NAME,
                             f'参考参数文件读取失败，跳过: {path}: {e}', category='system')
                continue
            yield f'ref_params/{key}', data


def iter_audio_entries(audio_infos: List[dict]) -> Iterator[Tuple[str, bytes]]:
    """从音频信息列表产出音频文件条目（audio_infos 来自 audio_service ACL）。

    Args:
        audio_infos: [{id, file_path, ...}]，file_path 为存储路径
    """
    for audio in audio_infos or []:
        path = (audio or {}).get('file_path')
        if not path:
            continue
        _category, key = parse_storage_path(path)
        if not key:
            continue
        try:
            data = storage.load_bytes(path)
        except Exception as e:
            log_not_emit('WARNING', _MODULE_NAME,
                         f'音频文件读取失败，跳过: {path}: {e}', category='system')
            continue
        yield f'audios/{key}', data


def _remap_key_task_segment(key: str, new_task_id: int) -> str:
    segments = safe_storage_key(key).split('/')
    segments[0] = str(new_task_id)
    return '/'.join(segments)


def write_case_result_files(entries: Iterator[Tuple[str, bytes]],
                            tasks_mapping: Dict[int, int],
                            tracker: List[Tuple[str, str]] = None) -> List[Tuple[str, str]]:
    """回写结果文件（key 首段按 tasks_mapping 重映射），返回 [(new_key, 实际存储路径)]。

    tracker 传入列表时每写成功一个即追加（供中途失败时补偿清理已写入部分）。
    """
    written: List[Tuple[str, str]] = tracker if tracker is not None else []
    for key, data in entries:
        head = str(key).split('/', 1)[0]
        old_task_id = int(head) if head.isdigit() else None
        new_task_id = tasks_mapping.get(old_task_id, old_task_id) if old_task_id is not None else None
        if new_task_id is None:
            # key 首段不是数字（如 __other__ 归档段）：原样回写
            new_key = key
        else:
            new_key = _remap_key_task_segment(key, new_task_id)
        stored_path = storage.save_bytes(
            data, STORAGE_CATEGORY_CASE_RESULT, new_key, content_type='application/json')
        written.append((new_key, stored_path))
    return written


def write_ref_param_files(entries: Iterator[Tuple[str, bytes]],
                          tracker: List[Tuple[str, str]] = None) -> List[Tuple[str, str]]:
    """回写参考参数文件（test_case_id 不重映射，key 原样），返回 [(key, 存储路径)]"""
    written: List[Tuple[str, str]] = tracker if tracker is not None else []
    for key, data in entries:
        safe_storage_key(key)
        stored_path = storage.save_bytes(
            data, _REF_PARAMS_BUCKET, key, content_type='application/json')
        written.append((key, stored_path))
    return written


def write_audio_files(entries: Iterator[Tuple[str, bytes]],
                      tracker: List[Tuple[str, str]] = None) -> List[Tuple[str, str]]:
    """回写音频文件（key 原样），返回 [(key, 存储路径)]"""
    written: List[Tuple[str, str]] = tracker if tracker is not None else []
    for key, data in entries:
        safe_storage_key(key)
        stored_path = storage.save_bytes(
            data, STORAGE_CATEGORY_AUDIOS, key, content_type='audio/mpeg')
        written.append((key, stored_path))
    return written


def delete_written_files(written: List[Tuple[str, str]]) -> None:
    """按 (key, 存储路径) 删除已回写的文件（文件段失败清理）"""
    for _key, stored_path in written:
        try:
            storage.delete(stored_path)
        except Exception as e:
            log_not_emit('WARNING', _MODULE_NAME,
                         f'清理已回写文件失败: {stored_path}: {e}', category='system')
