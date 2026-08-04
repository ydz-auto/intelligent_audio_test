"""维度结果记录混入：创建 TestResultDimension 记录、标记评估状态"""
from shared.models.models import TestCase, TaskCase, TestResultDimension
from shared.models.database import db


class DimensionResultRecorderMixin:
    """创建维度结果记录与评估状态管理"""

    def _mark_evaluation_queued(self, task_id, test_case_id):
        """标记评估状态为 queued"""
        update_session = db.session()
        try:
            tc_rel = update_session.query(TaskCase).filter_by(task_id=task_id, test_case_id=test_case_id).first()
            if tc_rel and tc_rel.evaluation_status not in ['running', 'stopped', 'queued']:
                tc_rel.evaluation_status = 'queued'
                update_session.commit()
        except Exception as e:
            self._log(level='WARNING', content=f"更新评估状态失败: {str(e)}", task_id=task_id, test_case_id=test_case_id)
            update_session.rollback()
        finally:
            update_session.close()

    def _create_dimension_results(self, dimension_data_list, result_id, task_id, test_case_id, algorithm_type, kwargs):
        """为每个维度创建 TestResultDimension 记录"""
        dimension_result_map = {}
        for dim_data in dimension_data_list:
            dimension_result_id = self._create_single_dimension_result(
                result_id, dim_data, task_id, test_case_id, algorithm_type, kwargs
            )
            if dimension_result_id is not None:
                dimension_result_map[dim_data['id']] = dimension_result_id

        return dimension_result_map

    def _create_single_dimension_result(self, result_id, dim_data, task_id, test_case_id,
                                         algorithm_type, kwargs):
        """创建单个维度的 TestResultDimension 记录

        Returns:
            int: 创建成功的 dimension_result_id；失败时返回 None
        """
        dim_id = dim_data['id']
        dim_name = dim_data['name']

        dimension_result_id = None
        local_db_session = db.session()
        try:
            # DEBUG: 记录创建 TestResultDimension 时的 result_id 值和类型
            self._log(
                level='DEBUG',
                content=f"[DEBUG TestResultDimension] 创建前: result_id={result_id}, result_id_type={type(result_id)}, dim_id={dim_id}, dim_name={dim_name}",
                task_id=task_id,
                test_case_id=test_case_id
            )

            # 获取算法类型
            algo_type = algorithm_type
            if not algo_type or algo_type == 'translation':
                test_case = local_db_session.get(TestCase, test_case_id)
                if test_case and test_case.algorithm_type:
                    algo_type = test_case.algorithm_type

            # 从 kwargs 获取 round_number (多轮评估场景)
            round_number = kwargs.get('round_number')

            test_result_dimension = TestResultDimension(
                test_result_id=result_id,
                dimension_id=dim_id,
                algorithm_type=algo_type,
                round_number=round_number,
                status=None,
                evaluation_status='pending',
                error_message=None
            )

            # DEBUG: 记录 TestResultDimension 对象的属性值
            self._log(
                level='DEBUG',
                content=f"[DEBUG TestResultDimension] 对象属性: test_result_id={test_result_dimension.test_result_id}, dimension_id={test_result_dimension.dimension_id}",
                task_id=task_id,
                test_case_id=test_case_id
            )

            local_db_session.add(test_result_dimension)
            local_db_session.flush()
            dimension_result_id = test_result_dimension.id

            # DEBUG: 记录 flush 后数据库中的实际值
            self._log(
                level='DEBUG',
                content=f"[DEBUG TestResultDimension] flush后查询: id={dimension_result_id}, test_result_id={test_result_dimension.test_result_id}",
                task_id=task_id,
                test_case_id=test_case_id
            )

            local_db_session.commit()

            # DEBUG: 验证提交后的数据
            verify_dim = local_db_session.get(TestResultDimension, dimension_result_id)
            if verify_dim:
                self._log(
                    level='DEBUG',
                    content=f"[DEBUG TestResultDimension] commit后验证: id={verify_dim.id}, test_result_id={verify_dim.test_result_id}",
                    task_id=task_id,
                    test_case_id=test_case_id
                )
            else:
                self._log(
                    level='ERROR',
                    content=f"[DEBUG TestResultDimension] commit后验证失败: 无法查询到 id={dimension_result_id}",
                    task_id=task_id,
                    test_case_id=test_case_id
                )

            self._log(
                level='DEBUG',
                content=f"创建维度记录: dim_name={dim_name}, dim_id={dim_id}, dimension_result_id={dimension_result_id}, evaluation_status=pending",
                task_id=task_id,
                test_case_id=test_case_id
            )
        except Exception as e:
            self._log(level='ERROR', content=f"创建TestResultDimension记录失败: {str(e)}", task_id=task_id, test_case_id=test_case_id)
            local_db_session.rollback()
        finally:
            local_db_session.close()

        return dimension_result_id
