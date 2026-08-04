# -*- coding: utf-8 -*-
"""ReferenceFileMixin - 提供参考参数文件的加载（OSS / 本地）

拆分自原 case_parameter_extractor.py 的 CaseParameterExtractor：
- _load_ref_file
- _load_round_ref_file
"""

import json as _json
import os
from typing import Dict, Any, Optional

from shared.infrastructure.storage import storage
from shared.utils.log_handler import log_not_emit


class ReferenceFileMixin:
    """参考参数文件加载 mixin"""

    @classmethod
    def _load_ref_file(cls, reference_params_path: Optional[str]) -> Dict[str, Any]:
        """从 OSS（ref_params bucket）加载参考参数

        Args:
            reference_params_path: 参考参数 OSS 对象 key（或兼容本地绝对路径）
        Returns:
            解析后的 JSON 内容，路径无效或对象不存在时返回空 dict
        """
        if not reference_params_path:
            return {}
        try:
            # 兼容本地绝对路径（旧数据）
            if os.path.isabs(reference_params_path) and os.path.exists(reference_params_path):
                with open(reference_params_path, 'r', encoding='utf-8') as f:
                    data = _json.load(f)
            else:
                # 从存储读取（OSS 或本地降级）
                if not storage.exists(reference_params_path):
                    log_not_emit('WARNING', 'case_parameter_extractor',
                                 f'Reference params object not found: {reference_params_path}',
                                 category='algorithm')
                    return {}
                raw = storage.load_bytes(reference_params_path)
                data = _json.loads(raw.decode('utf-8'))

            # 如果文件内容是列表 [{code, type, value}]，转为 dict 格式方便查找
            if isinstance(data, list):
                result = {}
                for item in data:
                    if isinstance(item, dict) and 'code' in item:
                        result[item['code']] = item
                return result
            elif isinstance(data, dict):
                return data
            return {}
        except Exception as e:
            log_not_emit('WARNING', 'case_parameter_extractor',
                         f'Failed to load reference params from {reference_params_path}: {e}', category='algorithm')
            return {}

    @classmethod
    def _load_round_ref_file(cls, reference_params_col, round_number) -> Dict[str, Any]:
        """从 reference_params 独立列按轮加载参考参数文件

        Args:
            reference_params_col: test_cases.reference_params 列，按轮分组
                [{round_number, reference_params_path}]
            round_number: 轮次序号
        Returns:
            解析后的参考参数 dict，找不到返回 {}
        """
        if not reference_params_col:
            return {}
        for item in reference_params_col:
            if item.get('round_number') == round_number:
                path = item.get('reference_params_path')
                return cls._load_ref_file(path)
        return {}
