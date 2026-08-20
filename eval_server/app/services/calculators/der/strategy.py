"""DER Calculator"""
from app.services.calculators.base import BaseCalculator


class DerCalculator(BaseCalculator):
    task_type = 'der'

    def validate(self, task_params):
        required_fields = ['rttm_ref', 'stm_ref', 'rttm_res', 'stm_res']
        missing = [f for f in required_fields if not task_params.get(f)]
        if missing:
            return False, f"Missing required fields for {self.task_type}: {', '.join(missing)}"
        return True, None

    def calculate(self, params):
        from app.services.calculators.der.der_calculator import calculate_der
        return calculate_der(
            params['rttm_ref'], params['stm_ref'], params['rttm_res'], params['stm_res'],
            params['source_lang'], params['target_lang'], params['translate_direct'],
            params['collar'], params['skip_overlap'],
            normalize=params['normalize'],
        )
