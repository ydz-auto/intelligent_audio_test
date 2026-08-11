# -*- coding: utf-8 -*-
"""参考参数存储适配器

通过 shared.infrastructure.storage 读写 OSS，
迁移自 shared/algorithm/reference_params/generator.py 的存储部分。
"""

import json
from typing import Dict, List, Any, Optional
from shared.utils.log_handler import log_not_emit

from algorithm_service.domain.services.reference_helpers import (
    ReferenceHelpersService,
    _REF_PARAMS_BUCKET,
)


class RefParamsStorageAdapter:
    """参考参数 OSS 存储适配器"""

    @staticmethod
    def save_reference_params(
        case_id: str,
        round_number: int,
        params: List[Dict[str, Any]],
    ) -> Optional[str]:
        """将参考参数列表写入 OSS，返回存储路径"""
        oss_key = ReferenceHelpersService.build_ref_params_key(case_id, round_number)
        try:
            from shared.infrastructure.storage import storage_save_bytes
            data = json.dumps(params, ensure_ascii=False, indent=2).encode('utf-8')
            stored_path = storage_save_bytes(
                data, _REF_PARAMS_BUCKET, oss_key,
                content_type='application/json',
            )
            log_not_emit('DEBUG', 'ref_params_storage',
                         f'Saved {len(params)} params to {stored_path}', category='algorithm')
            return stored_path
        except Exception as e:
            log_not_emit('ERROR', 'ref_params_storage',
                         f'Failed to save {_REF_PARAMS_BUCKET}/{oss_key}: {e}', category='algorithm')
            return None

    @staticmethod
    def load_reference_params(filepath: str) -> List[Dict[str, Any]]:
        """从 OSS 加载参考参数列表"""
        if not filepath:
            return []
        try:
            from shared.infrastructure.storage import storage_load_bytes
            raw = storage_load_bytes(filepath)
            data = json.loads(raw.decode('utf-8'))
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            log_not_emit('ERROR', 'ref_params_storage',
                         f'Failed to load from {filepath}: {e}', category='algorithm')
            return []

    @staticmethod
    def load_reference_params_dict(filepath: str) -> Dict[str, Any]:
        """从 OSS 加载参考参数并按 code 索引为 dict"""
        params = RefParamsStorageAdapter.load_reference_params(filepath)
        if not params:
            return {}
        result = {}
        for param in params:
            if not isinstance(param, dict):
                continue
            code = param.get('code')
            if code:
                result[code] = param
        return result


ref_params_storage = RefParamsStorageAdapter()
