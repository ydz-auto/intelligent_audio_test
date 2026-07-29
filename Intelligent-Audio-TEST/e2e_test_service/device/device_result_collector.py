"""设备结果采集器

职责：
- 采集原始设备结果
- 字段映射（convert_results）
- 结果日志（build_case_result_log）

时间戳对齐委托给 TimestampAligner
RTTM/STM 解析委托给 RttmStmUtils
"""

import threading
import copy
import json
from shared.algorithm.field_mapper import get_field_mapper
from shared.utils.log_handler import log_not_emit
from .timestamp_aligner import TimestampAligner
from .rttm_stm_utils import RttmStmUtils


class DeviceResultCollector:
    """设备结果采集器基类"""

    def __init__(self):
        self.field_mapper = get_field_mapper()
        self._aligner = TimestampAligner()
        self._rttm_utils = RttmStmUtils()

    def collect_raw_results(self, task_id, test_case_id, device_info_list, extra_params, log_callback=None, **kwargs):
        """采集原始结果

        Args:
            task_id: 任务ID
            test_case_id: 测试用例ID
            device_info_list: 设备信息列表
            extra_params: 额外参数
            log_callback: 日志回调函数 fn(level, content, task_id, device_id)
            **kwargs: 额外参数，包含 case_reference_params 等

        Returns:
            list: 原始结果列表
        """
        playback_time_offsets = extra_params.get('playback_time_offsets', {})
        reference_params = extra_params.get('reference_params')
        algorithm_type = extra_params.get('algorithm_type') or kwargs.get('algorithm_type')

        log_not_emit('DEBUG', 'device_collector',
                     f'[collect_raw_results] playback_time_offsets={bool(playback_time_offsets)}, reference_params={bool(reference_params)}',
                     category='engine')

        all_results = []

        for idx, info in enumerate(device_info_list):
            res = {
                'device_id': info["device_id"],
                'device_name': info["device_name"],
                'device_sn': info["device_sn"]
            }
            try:
                if info["driver"]:
                    merged_params = {**extra_params, **kwargs}
                    raw_results = info["driver"].get_results(
                        info["device_sn"],
                        task_id=task_id,
                        test_case_id=test_case_id,
                        **merged_params
                    )

                    if isinstance(raw_results, list):
                        log_not_emit('DEBUG', 'device_collector', f'raw_results is list, length={len(raw_results)}',
                                     category='engine')
                        import copy
                        for result_idx, result_item in enumerate(raw_results):
                            log_not_emit('DEBUG', 'device_collector',
                                         f'result_item[{result_idx}] id: {id(result_item)}, keys: {list(result_item.keys())[:10]}',
                                         category='engine')
                            log_not_emit('DEBUG', 'device_collector',
                                         f'result_item[{result_idx}] str[:200]: {str(result_item)[:200]}',
                                         category='engine')
                            item_res = res.copy()
                            copied_item = copy.deepcopy(result_item)
                            log_not_emit('DEBUG', 'device_collector',
                                         f'copied_item[{result_idx}] id: {id(copied_item)}, keys: {list(copied_item.keys())[:10]}',
                                         category='engine')
                            item_res['raw_results'] = copied_item
                            log_not_emit('DEBUG', 'device_collector',
                                         f'item_res[{result_idx}][raw_results] id: {id(item_res["raw_results"])}, keys: {list(item_res["raw_results"].keys())[:10]}',
                                         category='engine')
                            item_res['result_type'] = result_item.get('result_type', 'default')
                            log_not_emit('DEBUG', 'device_collector',
                                         f'before append item_res[{result_idx}] id: {id(item_res)}, raw_results id: {id(item_res["raw_results"])}',
                                         category='engine')

                            alignment_result = self._aligner.calculate_effective_offset_for_single_result(
                                result_item, reference_params, playback_time_offsets, algorithm_type
                            )
                            item_res['adjusted_reference_params'] = alignment_result.get('adjusted_params') or reference_params or []
                            item_res['alignment_info'] = alignment_result.get('alignment_info')

                            all_results.append(item_res)
                            log_not_emit('DEBUG', 'device_collector',
                                         f'after append all_results[{result_idx}] raw_results id: {id(all_results[-1]["raw_results"])}, keys: {list(all_results[-1]["raw_results"].keys())[:5]}',
                                         category='engine')
                        continue

                    res['raw_results'] = raw_results or {}
                    res['result_type'] = 'default'

                    alignment_result = self._aligner.calculate_effective_offset_for_single_result(
                        raw_results, reference_params, playback_time_offsets, algorithm_type
                    )
                    res['adjusted_reference_params'] = alignment_result.get('adjusted_params') or reference_params or []
                    res['alignment_info'] = alignment_result.get('alignment_info')

            except Exception as e:
                if log_callback:
                    log_callback('ERROR', f"采集结果失败: {str(e)}", task_id, info["device_id"])
                res.setdefault('adjusted_reference_params', reference_params or [])
                res.setdefault('alignment_info', {'method': 'error', 'offset': 0.0})
            all_results.append(res)

        log_not_emit('DEBUG', 'device_collector',
                     f'FINAL before return: all_results id={id(all_results)}, count={len(all_results)}',
                     category='engine')

        import copy
        return copy.deepcopy(all_results)

    def collect_round_results(
        self,
        task_id: str,
        test_case_id: int,
        device_info_list: list,
        round_idx: int,
        round_config: dict,
        round_start_time: float,
        log_callback=None,
    ) -> list:
        """
        采集单轮对话的设备结果。

        与 collect_raw_results 的区别：
        - 结果关联到具体轮次
        - 时间对齐范围限定在本轮
        - 参考参数来自本轮的 round_config

        Args:
            task_id: 任务ID
            test_case_id: 测试用例ID
            device_info_list: 设备信息列表
            round_idx: 轮次索引 (0-indexed)
            round_config: 本轮配置，包含 referenceText 等
            round_start_time: 本轮开始时间戳
            log_callback: 日志回调函数

        Returns:
            本轮的设备结果列表
        """
        import time

        all_results = []

        for info in device_info_list:
            res = {
                'device_id': info["device_id"],
                'device_name': info["device_name"],
                'device_sn': info["device_sn"]
            }
            try:
                driver = info.get("driver")
                if driver is None:
                    continue

                raw_results = driver.get_results(
                    info["device_sn"],
                    task_id=task_id,
                    test_case_id=test_case_id,
                )

                if isinstance(raw_results, list):
                    for item in raw_results:
                        item_copy = copy.deepcopy(item)
                        item_copy['_device_id'] = info['device_id']
                        item_copy['_round'] = round_idx
                        item_res = res.copy()
                        item_res['raw_results'] = item_copy
                        item_res['result_type'] = item.get('result_type', 'default')
                        all_results.append(item_res)
                elif isinstance(raw_results, dict):
                    result_copy = copy.deepcopy(raw_results)
                    result_copy['_device_id'] = info['device_id']
                    result_copy['_round'] = round_idx
                    res['raw_results'] = result_copy
                    res['result_type'] = 'default'
                    all_results.append(res)
                else:
                    res['raw_results'] = raw_results or {}
                    res['result_type'] = 'default'
                    all_results.append(res)

            except Exception as e:
                if log_callback:
                    log_callback('ERROR', f"设备 {info.get('device_name')} 结果采集失败: {e}",
                                task_id, info["device_id"])
                else:
                    log_not_emit('WARNING', 'device_collector',
                                f'设备 {info.get("device_name")} 结果采集失败: {e}',
                                category='engine')
                all_results.append(res)

        # 标记轮次信息
        round_end_time = time.time()
        for result in all_results:
            raw = result.get('raw_results', {})
            if isinstance(raw, dict):
                raw['_round_idx'] = round_idx
                raw['_round_start_time'] = round_start_time
                raw['_round_end_time'] = round_end_time

        log_not_emit('DEBUG', 'device_collector',
                    f'[collect_round_results] round={round_idx}, results_count={len(all_results)}',
                    category='engine')

        return copy.deepcopy(all_results)

    def _align_round_results(self, raw_results, round_config, round_start_time):
        """
        对单轮结果进行时间对齐。

        策略：
        - 使用本轮的参考参数（round_config 中的 reference text）
        - 对齐窗口限定在本轮时间范围内

        Args:
            raw_results: 原始结果列表
            round_config: 本轮配置
            round_start_time: 本轮开始时间戳

        Returns:
            对齐后的结果
        """
        ref_text = round_config.get('referenceText', '')

        if not ref_text:
            return raw_results

        # 构建单轮参考参数
        reference_params = [{'text': ref_text, 'start': 0.0, 'end': 0.0}]

        # 复用现有对齐算法
        alignment_result = self._aligner.calculate_effective_offset_for_single_result(
            raw_results, reference_params, {'round_offset': round_start_time}, 'voice_llm'
        )

        return alignment_result

    def convert_results(self, all_results, algorithm_type):
        """转换原始结果为映射后的格式
        
        Args:
            all_results: 原始结果列表
            algorithm_type: 算法类型
            
        Returns:
            list: 转换后的结果列表（包含 success 字段）
        """

        # 调试：打印原始传入的数据
        print(f"DEBUG convert_results ENTRY: all_results id={id(all_results)}")
        if all_results and len(all_results) > 0:
            print(
                f"DEBUG convert_results ENTRY: raw_results keys = {list(all_results[0].get('raw_results', {}).keys())}")

        # 深拷贝，防止外部修改
        import copy
        all_results = copy.deepcopy(all_results)

        print(f"DEBUG convert_results AFTER DEEPCOPY: all_results id={id(all_results)}")
        if all_results and len(all_results) > 0:
            print(
                f"DEBUG convert_results AFTER DEEPCOPY: raw_results keys = {list(all_results[0].get('raw_results', {}).keys())}")

        for res in all_results:
            raw_results = res.get('raw_results', {})
            result_type = res.get('result_type', 'default')
            log_not_emit('DEBUG', 'device_collector',
                         f'convert_results: result_type={result_type}, all_results id={id(all_results)}, res id={id(res)}, raw_results id={id(raw_results)}, raw_keys={list(raw_results.keys())[:5]}',
                         category='engine')

            # 添加更多调试信息
            from shared.algorithm.field_mapper import get_field_mapper
            fm = get_field_mapper()
            mapped_fields = fm.get_mapped_device_output_fields(algorithm_type)
            if isinstance(mapped_fields, list):
                log_not_emit('DEBUG', 'device_collector', f'mapped_fields: {[f.get("code") for f in mapped_fields]}',
                             category='engine')
            else:
                log_not_emit('DEBUG', 'device_collector', f'mapped_fields keys: {list(mapped_fields.keys())}',
                             category='engine')

            mapped_results = self.field_mapper.convert_device_output(algorithm_type, raw_results)

            res.update(mapped_results)

            has_values = any(mapped_results.values())
            res['success'] = has_values

        return all_results

    def build_case_result_log(self, algorithm_type, res, ref_fields=None, **kwargs):
        """构建用例结果日志内容
        
        Args:
            algorithm_type: 算法类型（如 translation, fix 等）
            res: 单个结果字典，包含设备执行结果
            ref_fields: 参考字段字典（如参考文本、参考RTTM等）
            **kwargs: 额外字段
            
        Returns:
            str: 日志内容
        """
        # 确保 ref_fields 不为 None
        if ref_fields is None:
            ref_fields = {}

        # 获取算法映射后的设备输出字段键列表
        mapped_output_keys = self.field_mapper.get_mapped_device_output_field_keys(algorithm_type)

        # 初始化日志内容，先记录设备名称和执行状态
        raw_results = res.get('raw_results', {})
        success = res.get('success', raw_results.get('success', False))
        log_content = f"设备 {res.get('device_name', 'Unknown')} 执行结果:\n" + \
                      f"  采集状态: {'成功' if success else '失败'}\n"

        for key in mapped_output_keys:
            # 获取结果值，可能是字符串、字典、列表等任意类型
            value = res.get(key)
            if value:
                # 先转换为字符串再截断，避免对字典/列表直接切片导致 KeyError: slice(None, 100, None)
                # 原始代码 res.get(key, '')[:100] 当 value 是字典时会报错
                value = str(value)[:100]
            else:
                value = ''
            log_content += f"  {key}: {value}...\n"

        # 处理参考字段（如参考文本、参考RTTM等）
        if ref_fields:
            for field_key, field_value in ref_fields.items():
                if field_value:
                    display_value = str(field_value)[:100]
                    log_content += f"  {field_key}: {display_value}...\n"

        # 处理额外配置的查询字段
        extra_fields = self.field_mapper._get_algorithm_extra_config(algorithm_type).get('query_fields', {}).keys()
        for field in extra_fields:
            field_value = kwargs.get(field)
            if field_value:
                log_content += f"  {field}: {field_value}\n"

        return log_content


def get_device_result_collector():
    """获取设备结果采集器实例"""
    return DeviceResultCollector()
