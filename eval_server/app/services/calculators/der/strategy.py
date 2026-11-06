"""DER Calculator

参数模式：
  - 单轮：顶层 rttm_ref / stm_ref / rttm_hyp / stm_hyp（旧名 rttm_res/stm_res 兼容）
  - 多轮：rounds 内每轮含同名字段，按 \\n 拼接折叠为单条文本
  - 公共字段：normalize / source_lang / target_lang / translate_direct / collar(默认0.5) / skip_overlap
"""
from app.services.calculators.base import BaseCalculator

_DER_KEYS = ('rttm_ref', 'stm_ref', 'rttm_hyp', 'stm_hyp')
# 旧命名（识别结果 = result）：归一为 hyp 时兼容读取
_DER_LEGACY_KEYS = ('rttm_res', 'stm_res')


def _normalize_der_params(task_params):
    """把旧名 rttm_res/stm_res 归一为 rttm_hyp/stm_hyp（顶层与每轮均兼容）。"""
    params = dict(task_params or {})
    rounds = params.get('rounds')
    if isinstance(rounds, list):
        params['rounds'] = [
            {**rd, 'rttm_hyp': rd.get('rttm_hyp') or rd.get('rttm_res'),
             'stm_hyp': rd.get('stm_hyp') or rd.get('stm_res')}
            if isinstance(rd, dict) else rd
            for rd in rounds
        ]
    for new, old in zip(_DER_KEYS[2:], _DER_LEGACY_KEYS):
        if not params.get(new) and params.get(old):
            params[new] = params[old]
    return params


class DerCalculator(BaseCalculator):
    task_type = 'der'

    def validate(self, task_params):
        params = _normalize_der_params(task_params)
        if 'rounds' not in params:
            missing = [k for k in _DER_KEYS if not params.get(k)]
            if missing:
                return False, f"Missing required fields for {self.task_type}: {', '.join(missing)}"
        return True, None

    def prepare_params(self, task_params):
        """单轮从顶层取，多轮按 key 收集各轮值用 \\n 拼接（兼容旧名 res）"""
        task_params = _normalize_der_params(task_params)

        translate_direct = (
            task_params.get('translate_direct')
            or task_params.get('translation_direction')
        )
        flat = BaseCalculator._collect_flat_from_rounds(task_params, _DER_KEYS)

        return {
            'normalize': task_params.get('normalize', False),
            'source_lang': task_params.get('source_lang'),
            'target_lang': task_params.get('target_lang'),
            'translate_direct': translate_direct,
            **flat,
            'collar': task_params.get('collar', 0.5),
            'skip_overlap': task_params.get('skip_overlap', False),
        }

    def calculate(self, params):
        from app.services.calculators.der.der_calculator import calculate_der
        return calculate_der(
            params['rttm_ref'], params['stm_ref'], params['rttm_hyp'], params['stm_hyp'],
            params['source_lang'], params['target_lang'], params['translate_direct'],
            params['collar'], params['skip_overlap'],
            normalize=params['normalize'],
        )
