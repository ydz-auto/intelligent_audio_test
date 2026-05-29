import logging
from backend.utils.log_handler import log_and_emit

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
        from backend.algorithm.field_mapper import get_field_mapper
        field_mapper = get_field_mapper()

        mapped_results = field_mapper.convert_device_output(algorithm_type, device_output)

        logger.debug(
            f"[_convert_device_output_to_algorithm_result] algorithm_type={algorithm_type}, device_driver_type={device_driver_type}, mapped_keys={list(mapped_results.keys())}")
        return mapped_results
    except Exception as e:
        import traceback
        logger.error(f"转换设备输出失败: {str(e)}, traceback: {traceback.format_exc()}")
        return {}


def _calculate_adjusted_reference_params(extracted_result, original_reference_params, task_id=None, test_case_id=None, device_id=None):
    """根据设备提取结果重新计算 adjusted_reference_params

    核心逻辑：
    1. 从 extracted_result 中提取设备首个时间戳
    2. 从 original_reference_params 中提取参考首个时间戳
    3. 计算 effective_offset = 设备首个时间戳 - 参考首个时间戳
    4. 用 effective_offset 调整 original_reference_params

    Args:
        extracted_result: 设备驱动提取的结果（包含 recording_rttm_content 或 recording_stm_content）
        original_reference_params: 原始参考参数（来自 TestCase.reference_params）
        task_id: 任务ID (可选，用于日志)
        test_case_id: 用例ID (可选，用于日志)
        device_id: 设备ID (可选，用于日志)

    Returns:
        调整后的参考参数列表，如果计算失败则返回 None
    """
    try:
        from backend.utils.device_result_collector import DeviceResultCollector
        from backend.utils.log_handler import log_and_emit

        log_and_emit('INFO', 'reextractor', "====== REEVALUATION OFFSET CALCULATION ======", task_id=task_id, test_case_id=test_case_id, device_id=device_id)
        log_and_emit('INFO', 'reextractor', f"[_calculate_adjusted_reference_params] START", task_id=task_id, test_case_id=test_case_id, device_id=device_id)

        if not original_reference_params:
            log_and_emit('WARNING', 'reextractor', "FAIL: original_reference_params is None or empty", task_id=task_id, test_case_id=test_case_id, device_id=device_id)
            return None

        log_and_emit('INFO', 'reextractor', f"original_reference_params count: {len(original_reference_params)}", task_id=task_id, test_case_id=test_case_id, device_id=device_id)
        log_and_emit('DEBUG', 'reextractor', f"original_reference_params[0] keys: {list(original_reference_params[0].keys()) if original_reference_params else 'empty'}", task_id=task_id, test_case_id=test_case_id, device_id=device_id)

        collector = DeviceResultCollector()

        device_first_ts = collector._get_device_first_timestamp_from_result(extracted_result)
        if device_first_ts is None:
            log_and_emit('WARNING', 'reextractor', "FAIL: Cannot get device first timestamp from extracted_result", task_id=task_id, test_case_id=test_case_id, device_id=device_id)
            log_and_emit('DEBUG', 'reextractor', f"extracted_result keys: {list(extracted_result.keys()) if extracted_result else 'None'}", task_id=task_id, test_case_id=test_case_id, device_id=device_id)
            rttm = extracted_result.get('recording_rttm_content', '') if extracted_result else ''
            stm = extracted_result.get('recording_stm_content', '') if extracted_result else ''
            log_and_emit('DEBUG', 'reextractor', f"rttm length: {len(rttm) if rttm else 0}, stm length: {len(stm) if stm else 0}", task_id=task_id, test_case_id=test_case_id, device_id=device_id)
            return None

        log_and_emit('INFO', 'reextractor', f"SUCCESS: 设备首个时间戳 (device_first_ts): {device_first_ts:.3f}s", task_id=task_id, test_case_id=test_case_id, device_id=device_id)

        ref_first_ts = collector._get_reference_first_timestamp(original_reference_params)
        if ref_first_ts is None:
            log_and_emit('WARNING', 'reextractor', "FAIL: Cannot get reference first timestamp from original_reference_params", task_id=task_id, test_case_id=test_case_id, device_id=device_id)
            log_and_emit('DEBUG', 'reextractor', f"original_reference_params structure: {original_reference_params}", task_id=task_id, test_case_id=test_case_id, device_id=device_id)
            return None

        log_and_emit('INFO', 'reextractor', f"SUCCESS: 参考首个时间戳 (ref_first_ts): {ref_first_ts:.3f}s", task_id=task_id, test_case_id=test_case_id, device_id=device_id)

        effective_offset = device_first_ts - ref_first_ts

        log_and_emit('INFO', 'reextractor', f"有效偏移量 (effective_offset): {effective_offset:.3f}s", task_id=task_id, test_case_id=test_case_id, device_id=device_id)
        log_and_emit('INFO', 'reextractor', "==============================================", task_id=task_id, test_case_id=test_case_id, device_id=device_id)

        if abs(effective_offset) < 0.001:
            log_and_emit('INFO', 'reextractor', "effective_offset ~= 0, no adjustment needed", task_id=task_id, test_case_id=test_case_id, device_id=device_id)
            return original_reference_params

        adjusted_params = collector._apply_single_offset(original_reference_params, effective_offset)
        log_and_emit('INFO', 'reextractor', "Adjustment applied successfully", task_id=task_id, test_case_id=test_case_id, device_id=device_id)
        return adjusted_params

    except Exception as e:
        import traceback
        logger.error(f"计算 adjusted_reference_params 失败: {str(e)}, traceback: {traceback.format_exc()}")
        return None


def _extract_device_output_from_archive(device, task_id, case_id, device_id):
    """从存档日志中提取设备输出结果

    Args:
        device: Device 模型实例
        task_id: 任务ID
        case_id: 用例ID
        device_id: 设备ID (字符串)

    Returns:
        list: 提取的算法结果列表，每个元素包含 recording_stm_content, recording_rttm_content 等字段
    """
    try:
        from backend.device_driver import device_driver_factory

        device_system = device.system or ''
        device_keywords = device.keywords

        logger.info(
            f"开始从存档提取设备输出: device_system={device_system}, device_keywords={device_keywords}, device_id={device_id}")

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
                case_id=case_id,
                device_id=device_id
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
        from backend.models.database import db
        from backend.models.models import TestResult, TaskCase, Device, TestResultDimension, Task, TestCase

        try:
            task = db.session.get(Task, task_id)
            if not task:
                return {
                    'success': False,
                    'message': f'任务 {task_id} 不存在',
                    'reextracted_cases': []
                }

            task_devices = task.devices
            if not task_devices:
                return {
                    'success': True,
                    'message': f'任务 {task_id} 没有关联设备',
                    'reextracted_cases': []
                }

            device_map = {d.id: d for d in task_devices}

            query = db.session.query(TaskCase).filter(
                TaskCase.task_id == task_id,
                TaskCase.execution_status == execution_status
            )

            if evaluation_status:
                query = query.filter(TaskCase.evaluation_status == evaluation_status)

            tc_relations = query.all()

            if not tc_relations:
                return {
                    'success': True,
                    'message': f'没有符合条件的用例 (execution_status={execution_status}, evaluation_status={evaluation_status})',
                    'reextracted_cases': []
                }

            reextracted_cases = []

            for tc_rel in tc_relations:
                test_case_id = tc_rel.test_case_id

                test_case = db.session.get(TestCase, test_case_id)

                existing_results = db.session.query(TestResult).filter(
                    TestResult.task_id == task_id,
                    TestResult.test_case_id == test_case_id
                ).all()

                existing_result_map = {}
                for result in existing_results:
                    if result.device_id:
                        if result.device_id not in existing_result_map:
                            existing_result_map[result.device_id] = []
                        existing_result_map[result.device_id].append(result)

                adjusted_reference_params = None
                for result in existing_results:
                    if result.result_data and isinstance(result.result_data, dict):
                        adjusted_reference_params = result.result_data.get('adjusted_reference_params')
                        if adjusted_reference_params:
                            break

                original_reference_params = None
                if test_case and test_case.reference_params:
                    original_reference_params = test_case.reference_params
                    log_and_emit('DEBUG', 'reextractor', f"获取原始 reference_params 成功", task_id=task_id,
                                 test_case_id=test_case_id)

                for device_id, device in device_map.items():
                    if not device.serial_number:
                        log_and_emit('WARNING', 'reextractor', f"跳过: 设备无序列号", task_id=task_id,
                                     test_case_id=test_case_id, device_id=device_id)
                        continue

                    device_results = existing_result_map.get(device_id, [])
                    if device_results:
                        algorithm_type = device_results[0].algorithm_type or 'asr'
                    else:
                        algorithm_type = test_case.algorithm_type if test_case and test_case.algorithm_type else 'asr'

                    extracted_results, driver_type = _extract_device_output_from_archive(
                        device=device,
                        task_id=task_id,
                        case_id=test_case_id,
                        device_id=device.serial_number
                    )

                    if not isinstance(extracted_results, list):
                        log_and_emit('WARNING', 'reextractor', f"跳过: 提取结果格式异常", task_id=task_id,
                                     test_case_id=test_case_id, device_id=device_id)
                        continue

                    new_result_ids = []

                    for extracted_result in extracted_results:
                        if not extracted_result or not extracted_result.get('success'):
                            continue

                        result_type = extracted_result.get('result_type', 'unknown')

                        converted_result = _convert_device_output_to_algorithm_result(
                            algorithm_type, extracted_result, driver_type
                        )

                        result_data_to_save = extracted_result.copy()

                        log_and_emit('INFO', 'reextractor', f"调用 _calculate_adjusted_reference_params: test_case_id={test_case_id}, device_id={device_id}", task_id=task_id, test_case_id=test_case_id, device_id=device_id)
                        computed_adjusted_params = _calculate_adjusted_reference_params(
                            extracted_result, original_reference_params,
                            task_id=task_id, test_case_id=test_case_id, device_id=device_id
                        )
                        log_and_emit('INFO', 'reextractor', f"computed_adjusted_params result: {type(computed_adjusted_params)}", task_id=task_id, test_case_id=test_case_id, device_id=device_id)
                        if computed_adjusted_params:
                            result_data_to_save['adjusted_reference_params'] = computed_adjusted_params
                            log_and_emit('INFO', 'reextractor',
                                         f"重新计算 effective_offset 成功",
                                         task_id=task_id, test_case_id=test_case_id, device_id=device_id)
                        elif adjusted_reference_params:
                            result_data_to_save['adjusted_reference_params'] = adjusted_reference_params
                            log_and_emit('DEBUG', 'reextractor',
                                         f"使用旧的 adjusted_reference_params",
                                         task_id=task_id, test_case_id=test_case_id, device_id=device_id)

                        if result_type:
                            result_data_to_save['result_type'] = result_type

                        new_result_id = self._create_test_result(
                            task_id=task_id,
                            test_case_id=test_case_id,
                            device_id=device_id,
                            algorithm_type=algorithm_type,
                            algo_result=converted_result,
                            result_data=result_data_to_save
                        )
                        new_result_ids.append(new_result_id)

                    old_ids_for_device = []
                    if device_id in existing_result_map:
                        old_ids_for_device = [r.id for r in existing_result_map[device_id]]

                    log_and_emit('INFO', 'reextractor', f"获取旧记录: old_ids={old_ids_for_device}", task_id=task_id,
                                 test_case_id=test_case_id, device_id=device_id)

                    if old_ids_for_device or new_result_ids:
                        for old_id in old_ids_for_device:
                            db.session.query(TestResultDimension).filter_by(test_result_id=old_id).delete()
                            db.session.delete(db.session.get(TestResult, old_id))
                            log_and_emit('INFO', 'reextractor', f"删除旧记录", task_id=task_id,
                                         test_case_id=test_case_id, device_id=device_id)
                        db.session.commit()

                        if new_result_ids:
                            tc_rel.evaluation_status = 'pending'
                            db.session.commit()

                            reextracted_cases.append({
                                'test_case_id': test_case_id,
                                'device_id': device_id,
                                'result_types': [er.get('result_type') for er in extracted_results if
                                                 er and er.get('success')],
                                'old_result_ids': old_ids_for_device,
                                'new_result_ids': new_result_ids
                            })

                            log_and_emit('INFO', 'reextractor',
                                         f"重新提取成功: 新记录数={len(new_result_ids)}, 旧记录数={len(old_ids_for_device)}",
                                         task_id=task_id, test_case_id=test_case_id, device_id=device_id)

            return {
                'success': True,
                'message': f'成功重新提取 {len(reextracted_cases)} 个用例',
                'reextracted_cases': reextracted_cases
            }

        except Exception as e:
            log_and_emit('ERROR', 'reextractor', f"重新提取失败: {str(e)}", task_id=locals().get('task_id'),
                         test_case_id=locals().get('test_case_id'))
            db.session.rollback()
            return {
                'success': False,
                'message': f'重新提取失败: {str(e)}',
                'reextracted_cases': []
            }

    def _create_test_result(self, task_id, test_case_id, device_id, algorithm_type,
                            algo_result, result_data, execution_status='completed', response_time=0):
        """创建新的 TestResult 记录"""
        from sqlalchemy import text
        from backend.models.models import utc8now
        from backend.models.database import db
        import json

        insert_sql = text("""
            INSERT INTO test_results (task_id, test_case_id, device_id, algorithm_type, execution_status, response_time, algorithm_result, execution_steps, result_data, error_message, created_at)
            VALUES (:task_id, :test_case_id, :device_id, :algorithm_type, :execution_status, :response_time, :algorithm_result, :execution_steps, :result_data, :error_message, :created_at)
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
            'result_data': json.dumps(result_data) if result_data else None,
            'error_message': None,
            'created_at': utc8now()
        }

        with db.engine.connect() as conn:
            result = conn.execute(insert_sql, params)
            result_id = result.scalar()
            conn.commit()

        return result_id