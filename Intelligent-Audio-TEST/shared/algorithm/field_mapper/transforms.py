# -*- coding: utf-8 -*-
"""字段转换函数混入

提供内置转换函数（json_parse、base64、rttm/stm 解析等）的注册与实现。
"""

from shared.utils.log_handler import log_not_emit


class TransformMixin:
    """内置转换函数混入类

    提供内置转换函数的注册与实现。依赖宿主类实例属性 ``_transforms``。
    """

    def _register_builtin_transforms(self):
        """注册内置转换函数"""
        self._transforms = {
            'none': lambda x: x,
            'json_parse': self._json_parse,
            'base64': self._base64_encode,
            'to_string': lambda x: str(x) if x is not None else '',
            'to_int': lambda x: int(x) if x is not None else 0,
            'to_float': lambda x: float(x) if x is not None else 0.0,
            'to_bool': lambda x: bool(x) if x is not None else False,
            'rttm_to_obj': self._rttm_to_obj,
            'stm_to_obj': self._stm_to_obj,
        }

    @staticmethod
    def _json_parse(x):
        """JSON解析"""
        import json
        if isinstance(x, str):
            try:
                return json.loads(x)
            except Exception as e:
                log_not_emit('WARNING', 'field_mapper', f'JSON parse error: {e}', category='algorithm')
                return x
        return x

    @staticmethod
    def _base64_encode(x):
        """Base64编码"""
        import base64
        if isinstance(x, str):
            return base64.b64encode(x.encode()).decode()
        return x

    @staticmethod
    def _rttm_to_obj(text):
        """RTTM文本转{text, json}对象"""
        import json
        if not text:
            return {'text': '', 'json': '[]'}

        segments = []
        for line in text.split('\n'):
            parts = line.split()
            if parts and parts[0] == 'SPEAKER' and len(parts) >= 8:
                segments.append({
                    'speaker': parts[7],
                    'start': float(parts[3]),
                    'duration': float(parts[4]),
                })

        return {
            'text': text,
            'json': segments
        }

    @staticmethod
    def _stm_to_obj(text):
        """STM文本转{text, json}对象"""
        if not text:
            return {'text': '', 'json': '[]'}
        segments = []
        for line in text.split('\n'):
            parts = line.split()
            if not parts:
                continue
            # 跳过 RTTM 格式行
            if parts[0] == 'SPEAKER':
                continue

            # 兼容两种格式：
            # 1. 标准格式: file_id channel speaker start end <o> text (7+个部分，第6个是<o>)
            # 2. 简化格式: file_id channel speaker start end text (6个部分，没有<o>)
            try:

                if len(parts) >= 6:
                    # 简化格式（没有<o>标记）
                    segments.append({
                        'file_id': parts[0],
                        'channel': parts[1],
                        'speaker': parts[2],
                        'start': float(parts[3]),
                        'end': float(parts[4]),
                        'text': ' '.join(parts[5:]) if len(parts) > 5 else '',
                    })
            except (ValueError, IndexError):
                pass
        return {
            'text': text,
            'json': segments
        }
