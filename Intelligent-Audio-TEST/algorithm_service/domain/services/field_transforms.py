# -*- coding: utf-8 -*-
"""字段值转换领域服务

纯逻辑，无 I/O 依赖。迁移自 shared/algorithm/field_mapper/transforms.py

非法输入策略（INT-1749）：保留原值 + 错误描述回传（调用方 WARNING 记日志）。
不抛异常、不把非法输入静默吞成空串——唯一例外是 ``to_string`` 对 None 的
既定语义（None → ''，属于该转换类型本身的定义，不是失败）。
"""
import logging

logger = logging.getLogger(__name__)


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
        if not isinstance(x, str):
            return x
        # 非法 JSON 抛给 apply_transform_with_error 统一收敛为「保留原值 + 错误」，
        # 不在此静默返回原值（旧实现无日志，INT-1749 要求可观测）
        return json.loads(x)

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
    def apply_transform_with_error(cls, transform_type: str, value):
        """应用转换并返回 ``(转换后值, 错误描述或 None)``。

        非法输入（未知转换类型 / 转换函数抛异常）统一收敛为「保留原值」，
        错误描述交给调用方记日志或回传（INT-1749 服务端批量入口按 errors 回传）。
        """
        transforms = cls._ensure_transforms()
        transform_type = transform_type or 'none'
        fn = transforms.get(transform_type)
        if fn is None:
            return value, f"未知转换类型: {transform_type}"
        try:
            return fn(value), None
        except Exception as e:
            return value, f"{type(e).__name__}: {e}"

    @classmethod
    def apply_transform(cls, transform_type: str, value):
        """应用转换（非法输入保留原值并 WARNING）"""
        result, error = cls.apply_transform_with_error(transform_type, value)
        if error:
            logger.warning("字段值转换失败，保留原值 (transform_type=%s): %s",
                           transform_type, error)
        return result

    @classmethod
    def get_available_transforms(cls):
        return list(cls._ensure_transforms().keys())
