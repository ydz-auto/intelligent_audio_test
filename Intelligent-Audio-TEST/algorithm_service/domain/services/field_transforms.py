# -*- coding: utf-8 -*-
"""字段值转换领域服务

纯逻辑，无 I/O 依赖。迁移自 shared/algorithm/field_mapper/transforms.py
"""


class FieldTransformService:
    """字段值转换服务 - 静态方法"""

    _TRANSFORMS = None

    @classmethod
    def _ensure_transforms(cls):
        if cls._TRANSFORMS is None:
            import json, base64
            cls._TRANSFORMS = {
                'none': lambda x: x,
                'json_parse': cls._json_parse,
                'base64': cls._base64_encode,
                'to_string': lambda x: str(x) if x is not None else '',
                'to_int': lambda x: int(x) if x is not None else 0,
                'to_float': lambda x: float(x) if x is not None else 0.0,
                'to_bool': cls._to_bool,
                'rttm_to_obj': cls._rttm_to_obj,
                'stm_to_obj': cls._stm_to_obj,
            }
        return cls._TRANSFORMS

    @staticmethod
    def _json_parse(x):
        import json
        try:
            return json.loads(x) if isinstance(x, str) else x
        except Exception:
            return x

    @staticmethod
    def _base64_encode(x):
        import base64
        if isinstance(x, str):
            return base64.b64encode(x.encode('utf-8')).decode('utf-8')
        return base64.b64encode(x).decode('utf-8') if x else ''

    @staticmethod
    def _to_bool(x):
        if isinstance(x, bool):
            return x
        if isinstance(x, str):
            return x.lower() in ('true', '1', 'yes')
        return bool(x)

    @staticmethod
    def _rttm_to_obj(text):
        """RTTM 文本转 {text, json} 对象"""
        if not text:
            return {'text': '', 'json': []}
        segments = []
        for line in text.strip().split('\n'):
            parts = line.strip().split()
            if len(parts) >= 8 and parts[0] == 'SPEAKER':
                segments.append({
                    'speaker': parts[7],
                    'start': float(parts[3]),
                    'end': float(parts[3]) + float(parts[4]),
                    'duration': float(parts[4]),
                })
        return {'text': text, 'json': segments}

    @staticmethod
    def _stm_to_obj(text):
        """STM 文本转 {text, json} 对象"""
        if not text:
            return {'text': '', 'json': []}
        segments = []
        for line in text.strip().split('\n'):
            parts = line.strip().split(';;')
            if len(parts) >= 4:
                meta = parts[0].split()
                segments.append({
                    'speaker': parts[2],
                    'start': float(meta[0]) if meta else 0,
                    'end': float(meta[1]) if len(meta) > 1 else 0,
                    'text': parts[3] if len(parts) > 3 else '',
                })
        return {'text': text, 'json': segments}

    @classmethod
    def apply_transform(cls, transform_type: str, value):
        """应用转换"""
        transforms = cls._ensure_transforms()
        fn = transforms.get(transform_type, transforms['none'])
        try:
            return fn(value)
        except Exception:
            return value

    @classmethod
    def get_available_transforms(cls):
        return list(cls._ensure_transforms().keys())
