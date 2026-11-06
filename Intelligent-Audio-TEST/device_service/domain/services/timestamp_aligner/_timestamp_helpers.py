"""时间戳提取辅助方法"""

from shared.domain.ports.logging_port import log_not_emit


class TimestampHelperMixin:
    """从设备结果与参考参数中提取首个时间戳"""

    def _get_device_first_timestamp(self, all_results, algorithm_type=None):
        """从设备结果中提取首个时间戳

        优先从 STM 获取（包含文本），其次 RTTM。
        优先使用数据库配置动态查找字段名，失败时后缀扫描兜底。

        Args:
            all_results: 设备结果列表
            algorithm_type: 算法类型（可选，用于动态查找字段名）

        Returns:
            float: 首个时间戳，如果无法提取则返回 None
        """
        log_not_emit('DEBUG', 'device_collector',
                     f'[_get_device_first_timestamp] START: all_results count={len(all_results)}', category='engine')

        for idx, res in enumerate(all_results):
            raw_results = res.get('raw_results', {})
            if not raw_results:
                log_not_emit('DEBUG', 'device_collector',
                             f'[_get_device_first_timestamp] result[{idx}]: raw_results is empty', category='engine')
                continue

            stm_content, rttm_content = self._rttm_utils._get_stm_rttm_content_from_result(raw_results, algorithm_type)

            log_not_emit('DEBUG', 'device_collector',
                         f'[_get_device_first_timestamp] result[{idx}]: rttm_len={len(rttm_content) if rttm_content else 0}, stm_len={len(stm_content) if stm_content else 0}',
                         category='engine')

            # 优先使用 STM（包含文本内容）
            if stm_content:
                ts = self._rttm_utils._extract_first_timestamp_from_text(stm_content, 'stm')
                if ts is not None:
                    log_not_emit('INFO', 'device_collector',
                                 f'[_get_device_first_timestamp] result[{idx}]: Found device timestamp from STM: {ts:.3f}s',
                                 category='engine')
                    return ts

            # 回退到 RTTM
            if rttm_content:
                ts = self._rttm_utils._extract_first_timestamp_from_text(rttm_content, 'rttm')
                if ts is not None:
                    log_not_emit('INFO', 'device_collector',
                                 f'[_get_device_first_timestamp] result[{idx}]: Found device timestamp from RTTM: {ts:.3f}s',
                                 category='engine')
                    return ts

        log_not_emit('WARNING', 'device_collector',
                     '[_get_device_first_timestamp] No valid timestamp found in device results', category='engine')
        return None

    def _get_device_first_timestamp_from_result(self, extracted_result, algorithm_type=None):
        """从单个设备提取结果中提取首个时间戳

        优先使用数据库配置动态查找字段名，失败时后缀扫描兜底。

        Args:
            extracted_result: 设备驱动提取的单个结果
            algorithm_type: 算法类型（可选，用于动态查找字段名）

        Returns:
            float: 首个时间戳，如果无法提取则返回 None
        """
        if not extracted_result:
            return None

        stm_content, rttm_content = self._rttm_utils._get_stm_rttm_content_from_result(extracted_result, algorithm_type)

        # 优先使用 STM（包含文本内容）
        if stm_content:
            ts = self._rttm_utils._extract_first_timestamp_from_text(stm_content, 'stm')
            if ts is not None:
                log_not_emit('DEBUG', 'device_collector',
                             f'[_get_device_first_timestamp_from_result] from stm: {ts:.3f}', category='engine')
                return ts

        # 回退到 RTTM
        if rttm_content:
            ts = self._rttm_utils._extract_first_timestamp_from_text(rttm_content, 'rttm')
            if ts is not None:
                log_not_emit('DEBUG', 'device_collector',
                             f'[_get_device_first_timestamp_from_result] from rttm: {ts:.3f}', category='engine')
                return ts

        log_not_emit('WARNING', 'device_collector',
                     '[_get_device_first_timestamp_from_result] No valid timestamp found in extracted_result',
                     category='engine')
        return None

    def _get_reference_first_timestamp(self, reference_params):
        """从参考参数中提取首个时间戳

        Args:
            reference_params: 参考参数列表

        Returns:
            float: 首个时间戳，如果无法提取则返回 None
        """
        log_not_emit('DEBUG', 'device_collector',
                     f'[_get_reference_first_timestamp] START: reference_params count={len(reference_params)}',
                     category='engine')

        for param_idx, param in enumerate(reference_params):
            if not isinstance(param, dict):
                log_not_emit('DEBUG', 'device_collector',
                             f'[_get_reference_first_timestamp] param[{param_idx}]: not a dict, skip',
                             category='engine')
                continue

            log_not_emit('DEBUG', 'device_collector',
                         f'[_get_reference_first_timestamp] param[{param_idx}]: keys={list(param.keys())}',
                         category='engine')

            value = param.get('value')
            if not value or not isinstance(value, dict):
                log_not_emit('DEBUG', 'device_collector',
                             f'[_get_reference_first_timestamp] param[{param_idx}]: no valid value, skip',
                             category='engine')
                continue

            segments = value.get('segments') or value.get('json', [])
            if segments and isinstance(segments, list) and len(segments) > 0:
                first_seg = segments[0]
                if isinstance(first_seg, dict) and 'start' in first_seg:
                    ts = float(first_seg['start'])
                    log_not_emit('INFO', 'device_collector',
                                 f'[_get_reference_first_timestamp] param[{param_idx}]: Found reference timestamp from segments[0]: {ts:.3f}s',
                                 category='engine')
                    return ts
                else:
                    log_not_emit('DEBUG', 'device_collector',
                                 f'[_get_reference_first_timestamp] param[{param_idx}]: first_seg has no start, seg_keys={list(first_seg.keys()) if isinstance(first_seg, dict) else type(first_seg)}',
                                 category='engine')

            text = value.get('text', '')
            format_type = value.get('format', '')
            if text and format_type in ['rttm', 'stm']:
                ts = self._rttm_utils._extract_first_timestamp_from_text(text, format_type)
                if ts is not None:
                    log_not_emit('INFO', 'device_collector',
                                 f'[_get_reference_first_timestamp] param[{param_idx}]: Found reference timestamp from text ({format_type}): {ts:.3f}s',
                                 category='engine')
                    return ts
            else:
                log_not_emit('DEBUG', 'device_collector',
                             f'[_get_reference_first_timestamp] param[{param_idx}]: text={len(text) if text else 0}, format={format_type}',
                             category='engine')

        log_not_emit('WARNING', 'device_collector',
                     '[_get_reference_first_timestamp] No valid timestamp found in reference params', category='engine')
        return None
