"""RTTM/STM 解析与时间戳调整工具"""

import json
# TODO: 跨服务依赖 - e2e_test_service 不应依赖 task_service.algorithm，应改为 HTTP 调用
from task_service.algorithm.field_mapper import get_field_mapper
from shared.utils.log_handler import log_not_emit


class RttmStmUtils:
    """RTTM/STM 格式解析与时间戳调整"""

    def __init__(self):
        self.field_mapper = get_field_mapper()

    def _extract_first_timestamp_from_text(self, text_content, format_type):
        """从 RTTM/STM 文本中提取首个时间戳

        Args:
            text_content: RTTM 或 STM 格式的文本
            format_type: 'rttm' 或 'stm'

        Returns:
            float: 首个时间戳，如果无法提取则返回 None
        """
        if not text_content:
            return None

        lines = text_content.split('\n')
        for line in lines:
            parts = line.split()
            if not parts:
                continue

            try:
                if format_type == 'rttm' and parts[0] == 'SPEAKER' and len(parts) >= 4:
                    return float(parts[3])
                elif format_type == 'stm' and len(parts) >= 4 and parts[0] != 'SPEAKER' and not line.startswith('SPK-'):
                    return float(parts[3])
            except (ValueError, IndexError):
                continue

        return None

    def _extract_segments_from_text(self, text_content, format_type):
        """从 RTTM/STM 文本中提取所有片段列表

        Args:
            text_content: RTTM 或 STM 格式的文本
            format_type: 'rttm' 或 'stm'

        Returns:
            list: 片段列表，每个元素为 {'start': float, 'end': float, 'text': str, 'speaker': str}
        """
        if not text_content:
            return []

        segments = []
        lines = text_content.split('\n')

        for line in lines:
            parts = line.split()
            if not parts:
                continue

            try:
                if format_type == 'rttm' and parts[0] == 'SPEAKER' and len(parts) >= 8:
                    start = float(parts[3])
                    duration = float(parts[4])
                    end = start + duration
                    speaker = parts[7]
                    segments.append({
                        'start': start,
                        'end': end,
                        'speaker': speaker,
                        'text': ''
                    })
                elif format_type == 'stm' and len(parts) >= 6 and parts[0] != 'SPEAKER' and not line.startswith('SPK-'):
                    start = float(parts[3])
                    end = float(parts[4])
                    speaker = parts[2]
                    text = ' '.join(parts[5:])
                    segments.append({
                        'start': start,
                        'end': end,
                        'speaker': speaker,
                        'text': text
                    })
            except (ValueError, IndexError):
                continue

        segments.sort(key=lambda x: x['start'])
        return segments

    def _get_stm_rttm_content_from_result(self, result_dict, algorithm_type=None):
        """从结果字典中提取 STM/RTTM 内容

        优先使用数据库配置（algorithm_device_params 的 param_type）动态查找字段名，
        失败时按后缀（*_stm_content / *_rttm_content）扫描兜底。

        Args:
            result_dict: 设备结果字典
            algorithm_type: 算法类型（可选，用于从数据库配置动态查找字段名）

        Returns:
            tuple: (stm_content, rttm_content)
        """
        if not result_dict:
            return '', ''

        stm_content = ''
        rttm_content = ''

        # 策略1: 通过数据库配置动态查找字段名
        if algorithm_type and self.field_mapper:
            try:
                stm_codes = self.field_mapper.get_device_output_field_codes_by_type(algorithm_type, 'stm')
                rttm_codes = self.field_mapper.get_device_output_field_codes_by_type(algorithm_type, 'rttm')
                for code in stm_codes:
                    if result_dict.get(code):
                        stm_content = result_dict[code]
                        break
                for code in rttm_codes:
                    if result_dict.get(code):
                        rttm_content = result_dict[code]
                        break
            except Exception as e:
                log_not_emit('DEBUG', 'device_collector',
                             f'[_get_stm_rttm_content] FieldMapper lookup failed: {e}', category='engine')

        # 策略2: 后缀扫描兜底（匹配 *_stm_content / *_rttm_content）
        if not stm_content or not rttm_content:
            for key, value in result_dict.items():
                if not value:
                    continue
                if key.endswith('_stm_content') and not stm_content:
                    stm_content = value
                elif key.endswith('_rttm_content') and not rttm_content:
                    rttm_content = value

        return stm_content, rttm_content

    def _extract_segments_from_result(self, raw_results, algorithm_type=None):
        """从设备结果中提取片段列表

        Args:
            raw_results: 设备驱动提取的结果
            algorithm_type: 算法类型（可选，用于动态查找字段名）

        Returns:
            list: 片段列表
        """
        if not raw_results:
            return []

        stm_content, rttm_content = self._get_stm_rttm_content_from_result(raw_results, algorithm_type)

        # 优先使用 STM（包含文本内容，支持内容对齐）
        if stm_content:
            segments = self._extract_segments_from_text(stm_content, 'stm')
            if segments:
                return segments

        # 回退到 RTTM（无文本内容）
        if rttm_content:
            segments = self._extract_segments_from_text(rttm_content, 'rttm')
            if segments:
                return segments

        return []

    def _extract_segments_from_reference(self, reference_params):
        """从参考参数中提取片段列表

        Args:
            reference_params: 参考参数列表

        Returns:
            list: 片段列表
        """
        if not reference_params:
            return []

        for param in reference_params:
            if not isinstance(param, dict):
                continue

            param_type = param.get('type', '')
            if param_type not in ['rttm', 'stm']:
                continue

            value = param.get('value')
            if not value or not isinstance(value, dict):
                continue

            segments = value.get('segments') or value.get('json', [])
            if segments and isinstance(segments, list):
                valid_segments = []
                for seg in segments:
                    if isinstance(seg, dict) and 'start' in seg and 'end' in seg:
                        valid_segments.append({
                            'start': float(seg['start']),
                            'end': float(seg['end']),
                            'speaker': seg.get('speaker', ''),
                            'text': seg.get('text', '')
                        })
                if valid_segments:
                    valid_segments.sort(key=lambda x: x['start'])
                    return valid_segments

            text = value.get('text', '')
            if text and param_type in ['rttm', 'stm']:
                segments = self._extract_segments_from_text(text, param_type)
                if segments:
                    return segments

        return []
        """当无法从设备结果提取时间戳时，回退使用 playback_time_offsets

        Args:
            reference_params: 参考参数列表
            playback_time_offsets: 系统测量的播放时间偏移

        Returns:
            调整后的参考参数列表
        """
        if not playback_time_offsets:
            return None

        if isinstance(playback_time_offsets, dict):
            first_offset = list(playback_time_offsets.values())[0] if playback_time_offsets else 0
            offset_val = first_offset.get('offset', 0) if isinstance(first_offset, dict) else first_offset
        else:
            offset_val = playback_time_offsets

        log_not_emit('DEBUG', 'device_collector', f'[_apply_fallback_offset] Using playback_time_offsets: {offset_val}',
                     category='engine')

        if offset_val != 0 and reference_params:
            return self._apply_single_offset(reference_params, offset_val)

        return None

    def _apply_time_offset_to_reference_params(self, reference_params, offset):
        """根据实际播放时间偏移调整参考参数字段中的时间戳
        
        Args:
            reference_params: 参考参数列表
            offset: 时间偏移量（秒）或 {audio_id_playorder: {offset: xxx, play_order: xx}} 字典
            
        Returns:
            调整后的参考参数列表
        """
        if not reference_params:
            log_not_emit('DEBUG', 'device_collector',
                         '[_apply_time_offset_to_reference_params] reference_params is empty, returning as-is',
                         category='engine')
            return reference_params

        log_not_emit('DEBUG', 'device_collector',
                     f'[_apply_time_offset_to_reference_params] reference_params count={len(reference_params)}, offset type={type(offset).__name__}',
                     category='engine')

        offset_dict = {}
        if isinstance(offset, dict):
            log_not_emit('DEBUG', 'device_collector',
                         f'[_apply_time_offset_to_reference_params] offset dict keys={list(offset.keys())}',
                         category='engine')
            for k, v in offset.items():
                if isinstance(v, dict) and 'offset' in v:
                    play_order = v.get('play_order')
                    if play_order is not None:
                        offset_dict[play_order] = v['offset']
                        log_not_emit('DEBUG', 'device_collector',
                                     f'[_apply_time_offset_to_reference_params] Added offset_dict[{play_order}] = {v["offset"]}',
                                     category='engine')
                elif isinstance(v, (int, float)):
                    if isinstance(k, str) and '_' in k:
                        offset_dict[int(k.split('_')[-1])] = v if isinstance(v, int) else float(v)
                        log_not_emit('DEBUG', 'device_collector',
                                     f'[_apply_time_offset_to_reference_params] Added offset_dict from str key[{k.split("_")[-1]}] = {v}',
                                     category='engine')
                    elif isinstance(k, int):
                        offset_dict[k] = v if isinstance(v, int) else float(v)

        log_not_emit('DEBUG', 'device_collector',
                     f'[_apply_time_offset_to_reference_params] Final offset_dict={offset_dict}', category='engine')

        if not offset_dict:
            first_val = list(offset.values())[0] if offset else 0
            if isinstance(first_val, dict):
                first_val = first_val.get('offset', 0)
            if first_val == 0:
                return reference_params
            return self._apply_single_offset(reference_params, first_val)

        if all(v == 0 for v in offset_dict.values()):
            return reference_params

        adjusted_params = []
        for param in reference_params:
            if not isinstance(param, dict):
                adjusted_params.append(param)
                continue

            new_param = param.copy()

            value = param.get('value')
            if value:
                if isinstance(value, dict):
                    adjusted_value = value.copy()

                    if 'segments' in value:
                        adjusted_segments = []
                        for seg in value['segments']:
                            new_seg = seg.copy()
                            seg_play_order = new_seg.get('play_order')
                            if seg_play_order is not None and seg_play_order in offset_dict:
                                seg_offset = offset_dict[seg_play_order]
                            else:
                                seg_offset = list(offset_dict.values())[0] if offset_dict else 0

                            if 'start' in new_seg:
                                new_seg['start'] = new_seg['start'] + seg_offset
                            if 'end' in new_seg:
                                new_seg['end'] = new_seg['end'] + seg_offset
                            adjusted_segments.append(new_seg)
                        adjusted_value['segments'] = adjusted_segments
                        adjusted_value['json'] = adjusted_segments

                    if 'text' in value and value.get('format') in ['rttm', 'stm']:
                        adjusted_value['text'] = self._adjust_rttm_stm_text_by_play_order(value['text'], offset_dict)

                    new_param['value'] = adjusted_value
                else:
                    new_param['value'] = value

            adjusted_params.append(new_param)

        return adjusted_params

    def _apply_single_offset(self, reference_params, offset):
        """应用单一偏移量（兼容旧逻辑）"""
        log_not_emit('DEBUG', 'device_collector', f'[_apply_single_offset] START: offset={offset}', category='engine')

        if not reference_params:
            log_not_emit('WARNING', 'device_collector', '[_apply_single_offset] reference_params is empty',
                         category='engine')
            return None

        if not isinstance(reference_params, list):
            log_not_emit('WARNING', 'device_collector',
                         f'[_apply_single_offset] reference_params is not a list, type={type(reference_params)}',
                         category='engine')
            return None

        try:
            adjusted_params = []
            for param_idx, param in enumerate(reference_params):
                if not isinstance(param, dict):
                    adjusted_params.append(param)
                    continue

                new_param = param.copy()

                value = param.get('value')
                if value:
                    if isinstance(value, dict):
                        adjusted_value = value.copy()

                        if 'json' in value and value['json']:
                            adjusted_segments = []
                            json_data = value['json']
                            if isinstance(json_data, str):
                                try:
                                    json_data = json.loads(json_data)
                                except:
                                    json_data = None
                            if json_data and isinstance(json_data, list):
                                for seg in json_data:
                                    if isinstance(seg, dict):
                                        new_seg = seg.copy()
                                        if 'start' in new_seg:
                                            new_seg['start'] = new_seg['start'] + offset
                                        if 'end' in new_seg:
                                            new_seg['end'] = new_seg['end'] + offset
                                        adjusted_segments.append(new_seg)
                                    else:
                                        adjusted_segments.append(seg)
                            if adjusted_segments:
                                adjusted_value['json'] = adjusted_segments

                        if 'segments' in value and value['segments']:
                            adjusted_segments = []
                            for seg in value['segments']:
                                if isinstance(seg, dict):
                                    new_seg = seg.copy()
                                    if 'start' in new_seg:
                                        new_seg['start'] = new_seg['start'] + offset
                                    if 'end' in new_seg:
                                        new_seg['end'] = new_seg['end'] + offset
                                    adjusted_segments.append(new_seg)
                                else:
                                    adjusted_segments.append(seg)
                            adjusted_value['segments'] = adjusted_segments

                        if 'text' in value and value.get('format') in ['rttm', 'stm']:
                            adjusted_value['text'] = self._adjust_rttm_stm_text(value['text'], offset)

                        new_param['value'] = adjusted_value
                    else:
                        new_param['value'] = value

                adjusted_params.append(new_param)

            log_not_emit('DEBUG', 'device_collector',
                         f'[_apply_single_offset] SUCCESS: adjusted {len(adjusted_params)} params', category='engine')
            return adjusted_params

        except Exception as e:
            import traceback
            log_not_emit('ERROR', 'device_collector',
                         f'[_apply_single_offset] FAILED: {str(e)}, traceback: {traceback.format_exc()}',
                         category='engine')
            return None

    def _adjust_rttm_stm_text(self, text_content, offset):
        """调整 RTTM/STM 文本中的时间戳
        
        Args:
            text_content: RTTM 或 STM 格式的文本
            offset: 时间偏移量（秒）
            
        Returns:
            调整后的文本
        """
        if not text_content or offset == 0:
            return text_content

        lines = text_content.split('\n')
        adjusted_lines = []

        for line in lines:
            parts = line.split()
            if not parts:
                adjusted_lines.append(line)
                continue

            format_type = None
            if parts[0] == 'SPEAKER':
                format_type = 'rttm'
            elif len(parts) >= 4 and parts[0] != 'SPEAKER' and not line.startswith('SPK-'):
                format_type = 'stm'

            if format_type == 'rttm' and len(parts) >= 5:
                try:
                    start_time = float(parts[3])
                    new_start_time = start_time + offset
                    parts[3] = f"{new_start_time:.2f}"
                    adjusted_lines.append(' '.join(parts))
                except (ValueError, IndexError):
                    adjusted_lines.append(line)
            elif format_type == 'stm' and len(parts) >= 4:
                try:
                    start_time = float(parts[2])
                    end_time = float(parts[3])
                    new_start_time = start_time + offset
                    new_end_time = end_time + offset
                    parts[2] = f"{new_start_time:.2f}"
                    parts[3] = f"{new_end_time:.2f}"
                    adjusted_lines.append(' '.join(parts))
                except (ValueError, IndexError):
                    adjusted_lines.append(line)
            else:
                adjusted_lines.append(line)

        return '\n'.join(adjusted_lines)

    def _adjust_rttm_stm_text_by_play_order(self, text_content, offset_dict):
        """根据 play_order 分别调整 RTTM/STM 文本中的时间戳
        
        Args:
            text_content: RTTM 或 STM 格式的文本
            offset_dict: {play_order: offset} 字典
            
        Returns:
            调整后的文本
        """
        if not text_content or not offset_dict:
            return text_content

        if all(v == 0 for v in offset_dict.values()):
            return text_content

        default_offset = list(offset_dict.values())[0] if offset_dict else 0

        sorted_play_orders = sorted(offset_dict.keys())

        lines = text_content.split('\n')
        adjusted_lines = []

        current_play_order_idx = 0
        play_order_ranges = []
        current_start = 0
        for i, po in enumerate(sorted_play_orders):
            if i + 1 < len(sorted_play_orders):
                next_po = sorted_play_orders[i + 1]
                play_order_ranges.append((po, current_start, next_po))
                current_start = next_po
            else:
                play_order_ranges.append((po, current_start, None))

        def get_offset_for_time(start_time):
            for po, range_start, range_end in play_order_ranges:
                if range_end is None or start_time < range_end:
                    return offset_dict.get(po, default_offset)
            return default_offset

        for line in lines:
            parts = line.split()
            if not parts:
                adjusted_lines.append(line)
                continue

            format_type = None
            if parts[0] == 'SPEAKER':
                format_type = 'rttm'
            elif len(parts) >= 4 and parts[0] != 'SPEAKER' and not line.startswith('SPK-'):
                format_type = 'stm'

            if format_type == 'rttm' and len(parts) >= 5:
                try:
                    start_time = float(parts[3])
                    seg_offset = get_offset_for_time(start_time)
                    new_start_time = start_time + seg_offset
                    parts[3] = f"{new_start_time:.2f}"
                    adjusted_lines.append(' '.join(parts))
                except (ValueError, IndexError):
                    adjusted_lines.append(line)
            elif format_type == 'stm' and len(parts) >= 4:
                try:
                    start_time = float(parts[2])
                    seg_offset = get_offset_for_time(start_time)
                    end_time = float(parts[3])
                    new_start_time = start_time + seg_offset
                    new_end_time = end_time + seg_offset
                    parts[2] = f"{new_start_time:.2f}"
                    parts[3] = f"{new_end_time:.2f}"
                    adjusted_lines.append(' '.join(parts))
                except (ValueError, IndexError):
                    adjusted_lines.append(line)
            else:
                adjusted_lines.append(line)

        return '\n'.join(adjusted_lines)

