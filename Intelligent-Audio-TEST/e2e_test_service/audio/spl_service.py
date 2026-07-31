import numpy as np
from shared.models.models import SPLMapping
from typing import Optional


class SPLMappingService:
    """声压级 (SPL) 映射服务"""

    DB_MIN = -60.0
    DB_MAX = 0.0
    BASE_LEVEL_DB = -30.0
    MAX_OUTPUT_DB = -5.0
    MIN_GAIN_DB = -70.0
    MAX_GAIN_DB = MAX_OUTPUT_DB - BASE_LEVEL_DB
    MIN_GAIN_LINEAR = 10 ** (MIN_GAIN_DB / 20.0)
    MAX_GAIN_LINEAR = 10 ** (MAX_GAIN_DB / 20.0)

    @staticmethod
    def spl_to_gain(mapping_id, target_spl, app=None):
        """
        根据 SPL mapping 计算增益

        Args:
            mapping_id: SPL 映射 ID
            target_spl: 目标声压级 (dB)
            app: Flask 应用实例，用于创建应用上下文（可选）

        Returns:
            float: 线性增益值
        """
        from shared.models.database import db

        def _do_lookup():
            """执行实际的数据库查询和增益计算"""
            local_db_session = db.session()
            try:
                mapping = local_db_session.get(SPLMapping, mapping_id)
                if not mapping:
                    return 1.0

                if mapping.target_spl is not None and abs(mapping.target_spl - target_spl) < 0.1:
                    if mapping.digital_gain is not None:
                        gain_db = mapping.digital_gain / 100.0 if mapping.digital_gain > 1 else mapping.digital_gain
                        return SPLMappingService._apply_gain_limit(gain_db)

                if mapping.calibration_data:
                    points = mapping.calibration_data.get('points', [])
                    if points:
                        valid_points = [p for p in points if p.get('spl') is not None]
                        if not valid_points:
                            return 1.0

                        processed_points = []
                        for p in valid_points:
                            spl = p['spl']
                            gain_offset = p.get('gainOffset') if p.get('gainOffset') is not None else p.get('gain_offset')
                            digital_gain = p.get('digital_gain', p.get('gain', 0))

                            if gain_offset is not None:
                                linear_gain = 10 ** (gain_offset / 20.0)
                            else:
                                linear_gain = digital_gain / 100.0

                            processed_points.append({
                                'spl': spl,
                                'gain_linear': linear_gain
                            }) 

                        processed_points.sort(key=lambda x: x['spl'])
                        spls = [p['spl'] for p in processed_points]
                        gains = [p['gain_linear'] for p in processed_points]

                        if target_spl >= max(spls):
                            return SPLMappingService._apply_gain_limit(max(gains))

                        if target_spl <= min(spls):
                            if len(processed_points) >= 2:
                                coeffs = np.polyfit(spls, gains, 1)
                                extrapolated_gain = np.polyval(coeffs, target_spl)
                                print(f"[SPL外推] mapping_id={mapping_id}, target_spl={target_spl}, min_spl={min(spls)}, max_spl={max(spls)}, coeffs={coeffs}, extrapolated={extrapolated_gain:.6f} ({20*np.log10(extrapolated_gain) if extrapolated_gain>0 else -999:.2f}dB)")
                                if extrapolated_gain <= 0:
                                    print(f"[SPL外推] WARNING: extrapolated_gain <= 0, using min_gain={min(gains):.6f}")
                                    extrapolated_gain = min(gains)
                                return SPLMappingService._apply_gain_limit(extrapolated_gain)
                            else:
                                return SPLMappingService._apply_gain_limit(min(gains))

                        calculated_gain = np.interp(target_spl, spls, gains)
                        return SPLMappingService._apply_gain_limit(calculated_gain)

                if mapping.target_spl and mapping.digital_gain:
                    diff_db = target_spl - mapping.target_spl
                    factor = 10 ** (diff_db / 20.0)
                    return SPLMappingService._apply_gain_limit(factor)

                return 1.0
            finally:
                local_db_session.close()

        return _do_lookup()

    @staticmethod
    def _apply_gain_limit(gain_linear):
        return max(SPLMappingService.MIN_GAIN_LINEAR, min(SPLMappingService.MAX_GAIN_LINEAR, gain_linear))


spl_service = SPLMappingService()
