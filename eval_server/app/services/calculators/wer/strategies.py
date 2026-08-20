"""WER 系列策略：wer / ser / cpwer / tcpwer / stm_wer

wer/ser 校验 asr_ref + asr_hyp（支持 rounds 多轮）；
cpwer/tcpwer/stm_wer 校验 ref_stm + hyp_stm。
"""
from app.services.calculators.base import BaseCalculator
from app.services.calculators.wer.wer_calculator import (
    calculate_wer, calculate_ser,
    calculate_cpwer, calculate_tcpwer, calculate_stm_wer,
)


class WerCalculator(BaseCalculator):
    task_type = 'wer'

    def validate(self, task_params):
        if 'rounds' not in task_params:
            if not task_params.get('asr_ref') or not task_params.get('asr_hyp'):
                return False, f"Missing required fields for {self.task_type}: asr_ref, asr_hyp (or 'rounds' for multi-round mode)"
        return True, None

    def calculate(self, params):
        return calculate_wer(
            params['asr_ref'], params['asr_hyp'],
            params['source_lang'], params['target_lang'], params['translate_direct'],
            normalize=params['normalize'],
        )


class SerCalculator(BaseCalculator):
    task_type = 'ser'

    def validate(self, task_params):
        if 'rounds' not in task_params:
            if not task_params.get('asr_ref') or not task_params.get('asr_hyp'):
                return False, f"Missing required fields for {self.task_type}: asr_ref, asr_hyp (or 'rounds' for multi-round mode)"
        return True, None

    def calculate(self, params):
        return calculate_ser(
            params['asr_ref'], params['asr_hyp'],
            params['source_lang'], params['target_lang'], params['translate_direct'],
            normalize=params['normalize'],
        )


class CpwerCalculator(BaseCalculator):
    task_type = 'cpwer'

    def validate(self, task_params):
        if not task_params.get('ref_stm') or not task_params.get('hyp_stm'):
            return False, f"Missing required fields for {self.task_type}: ref_stm, hyp_stm"
        return True, None

    def calculate(self, params):
        return calculate_cpwer(
            params['ref_stm'], params['hyp_stm'],
            params['source_lang'], params['target_lang'], params['translate_direct'],
            normalize=params['normalize'],
        )


class TcpwerCalculator(BaseCalculator):
    task_type = 'tcpwer'

    def validate(self, task_params):
        if not task_params.get('ref_stm') or not task_params.get('hyp_stm'):
            return False, f"Missing required fields for {self.task_type}: ref_stm, hyp_stm"
        return True, None

    def calculate(self, params):
        return calculate_tcpwer(
            params['ref_stm'], params['hyp_stm'],
            params['source_lang'], params['target_lang'], params['translate_direct'],
            params['collar'],
            normalize=params['normalize'],
        )


class StmWerCalculator(BaseCalculator):
    task_type = 'stm_wer'

    def validate(self, task_params):
        if not task_params.get('ref_stm') or not task_params.get('hyp_stm'):
            return False, f"Missing required fields for {self.task_type}: ref_stm, hyp_stm"
        return True, None

    def calculate(self, params):
        return calculate_stm_wer(
            params['ref_stm'], params['hyp_stm'],
            params['source_lang'], params['target_lang'], params['translate_direct'],
            normalize=params['normalize'],
        )
