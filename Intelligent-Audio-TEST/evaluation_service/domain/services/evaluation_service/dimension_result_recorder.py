"""维度结果记录混入：通过 Repository 创建 TestResultDimension 记录、标记评估状态

P0 DDD 改造：移除模块级 infrastructure/acl import，改用方法内延迟导入。
"""
from evaluation_service.domain.entities import DimensionScore
from shared.utils.status_constants import EvaluationStatus


class DimensionResultRecorderMixin:
    """创建维度结果记录与评估状态管理"""

    def _mark_evaluation_queued(self, task_id, test_case_id):
        """标记评估状态为 queued（P1.4: 通过 gRPC 调 task_service.UpdateTaskCaseStatus）"""
        # P0-1: 通过依赖注入的 ABC 访问 ACL，domain 层不 import infrastructure
        try:
            # 先读取当前 TaskCase 状态，避免覆盖 running/stopped/queued
            tc_rels = self._task_acl_repo.get_task_case_by_ids(
                task_id=task_id, case_ids=[str(test_case_id)]
            )
            if not tc_rels:
                return
            tc = tc_rels[0]
            if tc.evaluation_status in [EvaluationStatus.RUNNING, EvaluationStatus.STOPPED, EvaluationStatus.QUEUED]:
                return
            self._task_acl_repo.update_task_case_status(
                task_id=task_id,
                case_id=str(test_case_id),
                evaluation_status=EvaluationStatus.QUEUED,
            )
        except Exception as e:
            self._log(level='WARNING', content=f"更新评估状态失败: {str(e)}", task_id=task_id, test_case_id=test_case_id)

    def _create_dimension_results(self, dimension_data_list, result_id, task_id, test_case_id, algorithm_type, kwargs):
        """为每个维度创建 TestResultDimension 记录"""
        dimension_result_map = {}
        round_number = kwargs.get('round_number')
        for dim_data in dimension_data_list:
            dim_id = dim_data['id']
            # 检查是否已存在同一 result_id + dim_id + round_number 的记录
            existing = self._evaluation_dimension_repo.find_score(
                result_id, dim_id, round_number
            )
            if existing:
                # 已存在记录：复用，非 pending 则重置为 pending 以便重新评估
                dimension_result_id = existing.id
                if existing.evaluation_status == EvaluationStatus.PENDING:
                    self._log(
                        level='DEBUG',
                        content=f"复用已有 pending 维度记录: dim_id={dim_id}, dr_id={dimension_result_id}",
                        task_id=task_id,
                        test_case_id=test_case_id
                    )
                else:
                    # 重置为 pending 以便重新评估
                    self._evaluation_dimension_repo.reset_score_to_pending(existing.id)
                    self._log(
                        level='DEBUG',
                        content=f"重置已有维度记录为 pending: dim_id={dim_id}, dr_id={dimension_result_id}",
                        task_id=task_id,
                        test_case_id=test_case_id
                    )
                dimension_result_map[dim_id] = dimension_result_id
                continue

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

        P5+DOMAIN: 通过 Repository.create_score_with_commit 提交，
                   不再直接 get_db_session().add/commit/rollback。
        P0-1: 通过依赖注入的 ABC 访问 Repository/ACL，domain 层不 import infrastructure。
        """
        dim_id = dim_data['id']
        dim_name = dim_data['name']

        dimension_result_id = None
        try:
            self._log(
                level='DEBUG',
                content=f"[DEBUG TestResultDimension] 创建前: result_id={result_id}, result_id_type={type(result_id)}, dim_id={dim_id}, dim_name={dim_name}",
                task_id=task_id,
                test_case_id=test_case_id
            )

            # 获取算法类型（P1.4: 通过 gRPC 读 TestCase）
            algo_type = algorithm_type
            if not algo_type or algo_type == 'translation':
                test_case = self._task_acl_repo.get_test_case_detail(str(test_case_id))
                if test_case and test_case.algorithm_type:
                    algo_type = test_case.algorithm_type

            # 从 kwargs 获取 round_number (多轮评估场景)
            round_number = kwargs.get('round_number')

            score_entity = DimensionScore(
                test_result_id=result_id,
                dimension_id=dim_id,
                algorithm_type=algo_type or '',
                round_number=round_number,
                status=None,
                evaluation_status=EvaluationStatus.PENDING,
                error_message=None,
            )

            dimension_result_id = self._evaluation_dimension_repo.create_score_with_commit(
                score_entity
            )

            if dimension_result_id is not None:
                self._log(
                    level='DEBUG',
                    content=f"[DEBUG TestResultDimension] commit后验证成功: id={dimension_result_id}, test_result_id={result_id}",
                    task_id=task_id,
                    test_case_id=test_case_id
                )
                self._log(
                    level='DEBUG',
                    content=f"创建维度记录: dim_name={dim_name}, dim_id={dim_id}, dimension_result_id={dimension_result_id}, evaluation_status=pending",
                    task_id=task_id,
                    test_case_id=test_case_id
                )
            else:
                self._log(
                    level='ERROR',
                    content=f"[DEBUG TestResultDimension] Repository.create_score_with_commit 返回 None: result_id={result_id}, dim_id={dim_id}",
                    task_id=task_id,
                    test_case_id=test_case_id
                )
        except Exception as e:
            self._log(level='ERROR', content=f"创建TestResultDimension记录失败: {str(e)}", task_id=task_id, test_case_id=test_case_id)

        return dimension_result_id
