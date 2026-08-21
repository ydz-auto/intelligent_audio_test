"""WER 系列策略：wer / ser / cpwer / tcpwer / stm_wer

参数模式：
  - 单轮：顶层 asr_ref / asr_hyp（wer/ser）或 ref_stm / hyp_stm（cpwer/tcpwer/stm_wer）
  - 多轮：rounds 内每轮含同名字段，按 \\n 拼接折叠为单条文本
  - 公共字段：normalize / source_lang / target_lang / translate_direct / collar / skip_overlap
"""
from app.services.calculators.base import BaseCalculator
from app.services.calculators.wer.wer_calculator import (
    calculate_wer, calculate_ser,
    calculate_cpwer, calculate_tcpwer, calculate_stm_wer,
)

# WER/SER 用的扁平字段
_WER_KEYS = ('asr_ref', 'asr_hyp')
# CPWER/TCPWER/STM_WER 用的扁平字段
_STM_KEYS = ('ref_stm', 'hyp_stm')
# DER 用的扁平字段
_DER_KEYS = ('rttm_ref', 'stm_ref', 'rttm_res', 'stm_res')


class _WerBaseCalculator(BaseCalculator):
    """WER 系列公共基类：统一单轮/多轮参数提取"""

    flat_keys: tuple = ()

    def validate(self, task_params):
        if 'rounds' not in task_params:
            missing = [k for k in self.flat_keys if not task_params.get(k)]
            if missing:
                return False, (
                    f"Missing required fields for {self.task_type}: "
                    f"{', '.join(missing)} (or 'rounds' for multi-round mode)"
                )
        return True, None

    def prepare_params(self, task_params):
        """单轮从顶层取，多轮按 key 收集各轮值用 \\n 拼接"""
        task_params = task_params or {}

        # 翻译方向：兼容两种命名
        translate_direct = (
            task_params.get('translate_direct')
            or task_params.get('translation_direction')
        )
        # collar 默认值随任务类型不同
        collar_default = 0.5 if self.task_type == 'der' else 0.0

        flat = BaseCalculator._collect_flat_from_rounds(task_params, self.flat_keys)

        return {
            'normalize': task_params.get('normalize', False),
            'source_lang': task_params.get('source_lang'),
            'target_lang': task_params.get('target_lang'),
            'translate_direct': translate_direct,
            **flat,
            'collar': task_params.get('collar', collar_default),
            'skip_overlap': task_params.get('skip_overlap', False),
        }


class WerCalculator(_WerBaseCalculator):
    task_type = 'wer'
    flat_keys = _WER_KEYS

    def calculate(self, params):
        return calculate_wer(
            params['asr_ref'], params['asr_hyp'],
            params['source_lang'], params['target_lang'], params['translate_direct'],
            normalize=params['normalize'],
        )


class SerCalculator(_WerBaseCalculator):
    task_type = 'ser'
    flat_keys = _WER_KEYS

    def calculate(self, params):
        return calculate_ser(
            params['asr_ref'], params['asr_hyp'],
            params['source_lang'], params['target_lang'], params['translate_direct'],
            normalize=params['normalize'],
        )


class CpwerCalculator(_WerBaseCalculator):
    task_type = 'cpwer'
    flat_keys = _STM_KEYS

    def calculate(self, params):
        return calculate_cpwer(
            params['ref_stm'], params['hyp_stm'],
            params['source_lang'], params['target_lang'], params['translate_direct'],
            normalize=params['normalize'],
        )


class TcpwerCalculator(_WerBaseCalculator):
    task_type = 'tcpwer'
    flat_keys = _STM_KEYS

    def calculate(self, params):
        return calculate_tcpwer(
            params['ref_stm'], params['hyp_stm'],
            params['source_lang'], params['target_lang'], params['translate_direct'],
            params['collar'],
            normalize=params['normalize'],
        )


class StmWerCalculator(_WerBaseCalculator):
    task_type = 'stm_wer'
    flat_keys = _STM_KEYS

    def calculate(self, params):
        return calculate_stm_wer(
            params['ref_stm'], params['hyp_stm'],
            params['source_lang'], params['target_lang'], params['translate_direct'],
            normalize=params['normalize'],
        )
