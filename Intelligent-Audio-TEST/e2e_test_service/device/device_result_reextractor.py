import logging
from shared.utils.log_handler import log_and_emit
from shared.utils.result_data_store import load_full_result_data

logger = logging.getLogger(__name__)


def get_device_result_reextractor():
    return DeviceResultReextractor()


def _convert_device_output_to_algorithm_result(algorithm_type: str, device_output: dict, device_driver_type: str):
    """将设备输出转换为 algorithm_result 格式

    Args:
        algorithm_type: 算法类型
        device_output: 设备驱动返回的原始数据
        device_driver_type: 设备驱动类型 ('harmony' 或 'android')

    Returns:
        dict: algorithm_result 格式的数据
    """
    try:
        from shared.algorithm.field_mapper import get_field_mapper
        field_mapper = get_field_mapper()

        mapped_results = field_mapper.convert_device_output(algorithm_type, device_output)

        logger.debug(
            f"[_convert_device_output_to_algorithm_result] algorithm_type={algorithm_type}, device_driver_type={device_driver_type}, mapped_keys={list(mapped_results.keys())}")
        return mapped_results
    except Exception as e:
        import traceback
        logger.error(f"转换设备输出失败: {str(e)}, traceback: {traceback.format_exc()}")
        return {}


def _calculate_adjusted_reference_params(extracted_result, original_reference_params, task_id=None, test_case_id=None, device_id=None, playback_time_offsets=None, algorithm_type=None):
    """根据设备提取结果重新计算 adjusted_reference_params

    委托给 collector 的完整对齐流程（包含 max_overlap、gap_pattern、first_timestamp 等策略），
    与首次采集时的对齐逻辑保持一致。

    Args:
        extracted_result: 设备驱动提取的结果（包含 recording_rttm_content 或 recording_stm_content）
        original_reference_params: 原始参考参数（来自 config.rounds[].referenceParamsPath 文件）
        task_id: 任务ID (可选，用于日志)
        test_case_id: 用例ID (可选，用于日志)
        device_id: 设备ID (可选，用于日志)
        playback_time_offsets: 系统测量的播放时间偏移 (可选)
        algorithm_type: 算法类型（可选，用于动态查找设备输出字段名）

    Returns:
        dict: {
            'adjusted_params': 调整后的参考参数列表（如果计算失败则为 None）,
            'alignment_info': 对齐信息字典
        }
    """
    try:
        from e2e_test_service.device.device_result_collector import DeviceResultCollector
        from shared.utils.log_handler import log_and_emit

        log_and_emit('INFO', 'reextractor', "====== REEVALUATION OFFSET CALCULATION ======", task_id=task_id, test_case_id=test_case_id, device_id=device_id)
        log_and_emit('INFO', 'reextractor', f"[_calculate_adjusted_reference_params] START", task_id=task_id, test_case_id=test_case_id, device_id=device_id)

        if not original_reference_params:
            log_and_emit('WARNING', 'reextractor', "FAIL: original_reference_params is None or empty", task_id=task_id, test_case_id=test_case_id, device_id=device_id)
            return {'adjusted_params': None, 'alignment_info': {}}

        log_and_emit('INFO', 'reextractor', f"original_reference_params count: {len(original_reference_params)}", task_id=task_id, test_case_id=test_case_id, device_id=device_id)
        log_and_emit('DEBUG', 'reextractor', f"original_reference_params[0] keys: {list(original_reference_params[0].keys()) if original_reference_params else 'empty'}", task_id=task_id, test_case_id=test_case_id, device_id=device_id)

        from e2e_test_service.device.timestamp_aligner import TimestampAligner
        aligner = TimestampAligner()

        # 委托给 aligner 的完整对齐流程（包含 max_overlap、gap_pattern、first_timestamp 等策略）
        alignment_result = aligner.calculate_effective_offset_for_single_result(
            extracted_result, original_reference_params, playback_time_offsets or {}, algorithm_type
        )

        adjusted_params = alignment_result.get('adjusted_params')
        alignment_info = alignment_result.get('alignment_info', {})

        # 推送关键结果到前端
        method = alignment_info.get('method', 'none')
        offset = alignment_info.get('offset', 0.0)
        missing = alignment_info.get('missing_segment_detected', False)
        reliability = alignment_info.get('first_timestamp_reliability', 'high')

        log_and_emit('INFO', 'reextractor', f"对齐方法: {method}, 偏移量: {offset:.3f}s, 丢句检测: {missing}, first_timestamp可靠性: {reliability}", task_id=task_id, test_case_id=test_case_id, device_id=device_id)
        log_and_emit('INFO', 'reextractor', f"设备片段数: {alignment_info.get('device_segment_count', 0)}, 参考片段数: {alignment_info.get('ref_segment_count', 0)}", task_id=task_id, test_case_id=test_case_id, device_id=device_id)
        log_and_emit('INFO', 'reextractor', "==============================================", task_id=task_id, test_case_id=test_case_id, device_id=device_id)

        return {
            'adjusted_params': adjusted_params,
            'alignment_info': alignment_info
        }

    except Exception as e:
        import traceback
        logger.error(f"计算 adjusted_reference_params 失败: {str(e)}, traceback: {traceback.format_exc()}")
        return {'adjusted_params': None, 'alignment_info': {}}


def _extract_device_output_from_archive(device, task_id, test_case_id, device_sn):
    """从存档日志中提取设备输出结果

    Args:
        device: Device 模型实例
        task_id: 任务ID
        test_case_id: 用例ID
        device_sn: 设备序列号

    Returns:
        list: 提取的算法结果列表，每个元素包含 recording_stm_content, recording_rttm_content 等字段
    """
    try:
        from e2e_test_service.drivers.device_driver import device_driver_factory

        device_system = device.system or ''
        device_keywords = device.keywords

        logger.info(
            f"开始从存档提取设备输出: device_system={device_system}, device_keywords={device_keywords}, device_sn={device_sn}")

        driver = device_driver_factory.get_driver(device_system, keywords=device_keywords)
        if not driver:
            logger.error(f"无法获取设备驱动: system={device_system}, keywords={device_keywords}")
            return [{
                'success': False,
                'message': f'无法获取设备驱动: system={device_system}'
            }], 'unknown'

        if hasattr(driver, 'extract_results_from_archive'):
            result = driver.extract_results_from_archive(
                task_id=task_id,
                test_case_id=test_case_id,
                device_sn=device_sn
            )
            driver_type = device_system.lower()
            return result, driver_type
        else:
            logger.error(f"驱动不支持从存档提取结果: {driver.__class__.__name__}")
            return [{
                'success': False,
                'message': f'驱动不支持从存档提取结果'
            }], device_system.lower()
    except Exception as e:
        import traceback
        logger.error(f"提取设备输出异常: {str(e)}, traceback: {traceback.format_exc()}")
        return {
            'success': False,
            'message': f'提取设备输出异常: {str(e)}'
        }, None


class DeviceResultReextractor:
    """设备结果重新提取器

    用于从设备存档日志中重新提取结果，替换原有的 TestResult 记录。
    """

    def reextract_for_task(self, task_id, execution_status='completed', evaluation_status=None):
        """重新提取任务的设备输出

        Args:
            task_id: 任务ID
            execution_status: 用例执行状态筛选 (默认: 'completed')
            evaluation_status: 评估状态筛选 (可选: 'failed', 'passed', 等)

        Returns:
            dict: {
                'success': bool,
                'message': str,
                'reextracted_cases': list of {
                    'test_case_id': str,
                    'result_types': list of str,
                    'old_result_ids': list of int,
                    'new_result_ids': list of int
                }
            }
        """
        from shared.models.database import db, _engine_ref
        from shared.models.models import TaskCase

        try:
            task = db.session.get(Task, task_id)
            if not task:
                return {'success': False, 'message': f'任务 {task_id} 不存在', 'reextracted_cases': []}

            device_map = self._filter_reextractable_devices(task_id, task.devices)
            if not device_map:
                return {'success': True, 'message': f'任务 {task_id} 无可重新提取的设备', 'reextracted_cases': []}

            tc_relations = self._query_task_cases(task_id, execution_status, evaluation_status)
            if not tc_relations:
                return {'success': True, 'message': '没有符合条件的用例', 'reextracted_cases': []}

            reextracted_cases = []
            for tc_rel in tc_relations:
                case_result = self._reextract_single_case(task_id, tc_rel, device_map)
                if case_result:
                    reextracted_cases.append(case_result)

            return {
                'success': True,
                'message': f'成功重新提取 {len(reextracted_cases)} 个用例',
                'reextracted_cases': reextracted_cases
            }

        except Exception as e:
            log_and_emit('ERROR', 'reextractor', f"重新提取失败: {str(e)}", task_id=locals().get('task_id'),
                         test_case_id=locals().get('test_case_id'))
            db.session.rollback()
            return {'success': False, 'message': f'重新提取失败: {str(e)}', 'reextracted_cases': []}

    def _filter_reextractable_devices(self, task_id, task_devices):
        """筛选支持重新提取的设备"""
        from e2e_test_service.drivers.device_driver import device_driver_factory

        if not task_devices:
            return {}

        device_map = {d.id: d for d in task_devices}
        reextractable = {}
        for d_id, d in device_map.items():
            driver = device_driver_factory.get_driver(d.system or '', keywords=d.keywords)
            if driver and hasattr(driver, 'extract_results_from_archive'):
                reextractable[d_id] = d
            else:
                driver_name = driver.__class__.__name__ if driver else 'None'
                log_and_emit('INFO', 'reextractor',
                             f"跳过设备 {d.name}(id={d_id}): 驱动 {driver_name} 不支持重新提取",
                             task_id=task_id)
        return reextractable

    def _query_task_cases(self, task_id, execution_status, evaluation_status):
        """查询符合条件的用例关联"""
        from shared.models.database import db, _engine_ref
        from shared.models.models import TaskCase

        query = db.session.query(TaskCase).filter(
            TaskCase.task_id == task_id,
            TaskCase.execution_status == execution_status
        )
        if evaluation_status:
            query = query.filter(TaskCase.evaluation_status == evaluation_status)
        return query.all()

    def _reextract_single_case(self, task_id, tc_rel, device_map):
        """重新提取单个用例的所有设备结果"""
        from shared.models.database import db, _engine_ref
        from shared.models.models import TestResult, TestCase

        test_case_id = tc_rel.test_case_id
        test_case = db.session.get(TestCase, test_case_id)

        existing_results = db.session.query(TestResult).filter(
            TestResult.task_id == task_id,
            TestResult.test_case_id == test_case_id
        ).all()

        existing_result_map = self._build_existing_result_map(existing_results)
        adjusted_reference_params = self._extract_adjusted_reference_params(existing_results)
        original_reference_params = self._get_original_reference_params(test_case, task_id, test_case_id)

        case_result = None
        for device_id, device in device_map.items():
            if not device.serial_number:
                log_and_emit('WARNING', 'reextractor', f"跳过: 设备无序列号", task_id=task_id,
                             test_case_id=test_case_id, device_id=device_id)
                continue

            device_results = existing_result_map.get(device_id, [])
            algorithm_type = (device_results[0].algorithm_type if device_results
                              else (test_case.algorithm_type if test_case and test_case.algorithm_type else 'asr'))

            extracted_results, driver_type = _extract_device_output_from_archive(
                device=device, task_id=task_id, test_case_id=test_case_id, device_sn=device.serial_number
            )
            if not isinstance(extracted_results, list):
                log_and_emit('WARNING', 'reextractor', f"跳过: 提取结果格式异常", task_id=task_id,
                             test_case_id=test_case_id, device_id=device_id)
                continue

            new_result_ids = self._process_extracted_results(
                task_id, test_case_id, device_id, algorithm_type,
                extracted_results, driver_type, original_reference_params, adjusted_reference_params
            )

            old_ids = [r.id for r in existing_result_map.get(device_id, [])]
            if old_ids or new_result_ids:
                self._replace_old_results(old_ids, tc_rel, task_id, test_case_id, device_id)
                if new_result_ids:
                    case_result = {
                        'test_case_id': test_case_id,
                        'device_id': device_id,
                        'result_types': [er.get('result_type') for er in extracted_results if er and er.get('success')],
                        'old_result_ids': old_ids,
                        'new_result_ids': new_result_ids
                    }
                    log_and_emit('INFO', 'reextractor',
                                 f"重新提取成功: 新记录数={len(new_result_ids)}, 旧记录数={len(old_ids)}",
                                 task_id=task_id, test_case_id=test_case_id, device_id=device_id)
        return case_result

    def _build_existing_result_map(self, existing_results):
        """按 device_id 分组已有结果"""
        result_map = {}
        for result in existing_results:
            if result.device_id:
                result_map.setdefault(result.device_id, []).append(result)
        return result_map

    def _extract_adjusted_reference_params(self, existing_results):
        """从已有结果中提取 adjusted_reference_params"""
        for result in existing_results:
            full_data = load_full_result_data(result.result_data, getattr(result, 'result_data_path', None))
            if full_data and isinstance(full_data, dict):
                adjusted = full_data.get('adjusted_reference_params')
                if adjusted:
                    return adjusted
        return None

    def _get_original_reference_params(self, test_case, task_id, test_case_id):
        """获取原始参考参数"""
        if not test_case or not test_case.config:
            return None
        from shared.algorithm.reference_params_generator import ReferenceParamsGenerator
        ref_col = getattr(test_case, 'reference_params', None)
        if ref_col:
            params = ReferenceParamsGenerator.get_all_reference_params(ref_col)
        else:
            params = ReferenceParamsGenerator.get_all_reference_params(test_case.config)
        if params:
            log_and_emit('DEBUG', 'reextractor', f"获取原始 reference_params 成功",
                         task_id=task_id, test_case_id=test_case_id)
        return params

    def _process_extracted_results(self, task_id, test_case_id, device_id, algorithm_type,
                                   extracted_results, driver_type,
                                   original_reference_params, adjusted_reference_params):
        """处理提取结果列表，返回 new_result_ids"""
        new_result_ids = []
        for extracted_result in extracted_results:
            if not extracted_result or not extracted_result.get('success'):
                continue

            result_type = extracted_result.get('result_type', 'unknown')
            converted_result = _convert_device_output_to_algorithm_result(
                algorithm_type, extracted_result, driver_type
            )
            result_data_to_save = extracted_result.copy()

            alignment_result = _calculate_adjusted_reference_params(
                extracted_result, original_reference_params,
                task_id=task_id, test_case_id=test_case_id, device_id=device_id,
                algorithm_type=algorithm_type
            )

            computed_adjusted = alignment_result.get('adjusted_params') if alignment_result else None
            new_alignment_info = alignment_result.get('alignment_info') if alignment_result else None

            if computed_adjusted:
                result_data_to_save['adjusted_reference_params'] = computed_adjusted
                log_and_emit('INFO', 'reextractor', f"重新计算 effective_offset 成功",
                             task_id=task_id, test_case_id=test_case_id, device_id=device_id)
            elif adjusted_reference_params:
                result_data_to_save['adjusted_reference_params'] = adjusted_reference_params
                log_and_emit('DEBUG', 'reextractor', f"使用旧的 adjusted_reference_params",
                             task_id=task_id, test_case_id=test_case_id, device_id=device_id)
            else:
                result_data_to_save['adjusted_reference_params'] = original_reference_params or []
                log_and_emit('DEBUG', 'reextractor', f"使用原始 reference_params 作为 adjusted_reference_params",
                             task_id=task_id, test_case_id=test_case_id, device_id=device_id)

            if new_alignment_info:
                result_data_to_save['alignment_info'] = new_alignment_info
            if result_type:
                result_data_to_save['result_type'] = result_type

            new_result_id = self._create_test_result(
                task_id=task_id, test_case_id=test_case_id, device_id=device_id,
                algorithm_type=algorithm_type, algo_result=converted_result, result_data=result_data_to_save
            )
            new_result_ids.append(new_result_id)
        return new_result_ids

    def _replace_old_results(self, old_ids, tc_rel, task_id, test_case_id, device_id):
        """删除旧结果并标记评估状态为 pending"""
        from shared.models.database import db, _engine_ref
        from shared.models.models import TestResult, TestResultDimension

        for old_id in old_ids:
            db.session.query(TestResultDimension).filter_by(test_result_id=old_id).delete()
            db.session.delete(db.session.get(TestResult, old_id))
            log_and_emit('INFO', 'reextractor', f"删除旧记录", task_id=task_id,
                         test_case_id=test_case_id, device_id=device_id)
        db.session.commit()
        tc_rel.evaluation_status = 'pending'
        db.session.commit()

    def _create_test_result(self, task_id, test_case_id, device_id, algorithm_type,
                            algo_result, result_data, execution_status='completed', response_time=0):
        """创建新的 TestResult 记录"""
        from sqlalchemy import text
        from shared.models.models import utc8now
        from shared.models.database import db, _engine_ref
        from shared.utils.result_data_store import write_result_data_file, split_result_data
        import json

        result_data_path = write_result_data_file(task_id, test_case_id, device_id, result_data)
        lightweight_data, _ = split_result_data(result_data)

        insert_sql = text("""
            INSERT INTO test_results (task_id, test_case_id, device_id, algorithm_type, execution_status, response_time, algorithm_result, execution_steps, result_data, result_data_path, error_message, created_at)
            VALUES (:task_id, :test_case_id, :device_id, :algorithm_type, :execution_status, :response_time, :algorithm_result, :execution_steps, :result_data, :result_data_path, :error_message, :created_at)
            RETURNING id
        """)

        params = {
            'task_id': task_id,
            'test_case_id': test_case_id,
            'device_id': device_id,
            'algorithm_type': algorithm_type,
            'execution_status': execution_status,
            'response_time': response_time,
            'algorithm_result': json.dumps(algo_result) if algo_result else None,
            'execution_steps': '[]',
            'result_data': json.dumps(lightweight_data) if lightweight_data else None,
            'result_data_path': result_data_path or None,
            'error_message': None,
            'created_at': utc8now()
        }

        with _engine_ref[0].connect() as conn:
            result = conn.execute(insert_sql, params)
            result_id = result.scalar()
            conn.commit()

        return result_id