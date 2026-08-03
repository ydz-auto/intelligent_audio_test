import json
import traceback
from shared.models.models import Dimension, TestResultDimension, TestResult
from shared.models.database import db
from task_service.evaluation.evaluation_mixin import EvaluationLoggerMixin


class RoundAggregator(EvaluationLoggerMixin):
    """
    负责多轮评估结果的聚合处理
    """

    def is_multi_round_result(self, result_id):
        """
        Check if a test result contains multi-round evaluation data.

        Returns True if any TestResultDimension has round_number set.
        """
        if not result_id:
            return False

        local_db_session = db.session()
        try:
            has_rounds = local_db_session.query(TestResultDimension).filter(
                TestResultDimension.test_result_id == result_id,
                TestResultDimension.round_number.isnot(None),
            ).first()
            return has_rounds is not None
        finally:
            local_db_session.close()

    def check_all_round_dimensions_completed(self, result_id):
        """
        Check if all dimension evaluations in a multi-round result are done.

        Returns True when no TestResultDimension is still in 'pending' status.
        """
        if not result_id:
            return True

        local_db_session = db.session()
        try:
            pending_count = local_db_session.query(TestResultDimension).filter(
                TestResultDimension.test_result_id == result_id,
                TestResultDimension.evaluation_status == 'pending',
            ).count()
            return pending_count == 0
        finally:
            local_db_session.close()

    def aggregate_round_results(self, result_id, task_id, test_case_id):
        """
        Aggregate multi-round evaluation results into per-dimension averages.

        Queries all TestResultDimension records (round_number IS NOT NULL) for the given result_id,
        groups them by dimension name, computes arithmetic mean scores,
        writes the aggregated data to TestResult.algorithm_result['aggregated'],
        and creates round_number=NULL TestResultDimension records for the overall scores.

        Returns:
            dict with keys like avg_{dim_name}, round_count, completed_rounds
        """
        local_db_session = db.session()
        try:
            # 仅聚合单轮维度记录（round_number IS NOT NULL），排除整体记录避免自引用
            dim_results = local_db_session.query(
                TestResultDimension
            ).filter(
                TestResultDimension.test_result_id == result_id,
                TestResultDimension.round_number.isnot(None),
            ).all()

            # Group by dimension_id
            dim_groups = {}
            dim_info = {}
            for dr in dim_results:
                dim_obj = local_db_session.get(Dimension, dr.dimension_id) if dr.dimension_id else None
                key = dim_obj.name if dim_obj else str(dr.dimension_id)
                if key not in dim_groups:
                    dim_groups[key] = []
                    dim_info[key] = {
                        'dimension_id': dr.dimension_id,
                        'algorithm_type': dr.algorithm_type,
                    }
                dim_groups[key].append({
                    'round_number': dr.round_number,
                    'score': dr.score,
                    'raw_value': dr.dimension_value,
                    'evaluation_status': dr.evaluation_status,
                })

            aggregated = {}
            for dim_name, results in dim_groups.items():
                completed = [
                    r for r in results
                    if r['evaluation_status'] == 'completed' and r['score'] is not None
                ]
                if completed:
                    avg_score = sum(r['score'] for r in completed) / len(completed)
                    aggregated[f'avg_{dim_name}'] = round(avg_score, 4)

                    # 创建/更新 round_number=NULL 的整体维度记录
                    info = dim_info.get(dim_name, {})
                    existing_overall = local_db_session.query(TestResultDimension).filter(
                        TestResultDimension.test_result_id == result_id,
                        TestResultDimension.dimension_id == info.get('dimension_id'),
                        TestResultDimension.round_number.is_(None),
                    ).first()

                    if existing_overall:
                        # 已有整体评估记录（由 round_number=None 评估产生），不覆盖其分数
                        # 仅在整体评估未产生分数时用算术平均兜底
                        if existing_overall.score is None:
                            existing_overall.score = round(avg_score, 4)
                            existing_overall.evaluation_status = 'completed'
                    else:
                        # 没有整体评估记录，创建一条聚合记录
                        overall_dim = TestResultDimension(
                            test_result_id=result_id,
                            dimension_id=info.get('dimension_id'),
                            algorithm_type=info.get('algorithm_type'),
                            round_number=None,
                            score=round(avg_score, 4),
                            status=None,
                            evaluation_status='completed',
                            error_message=None,
                        )
                        local_db_session.add(overall_dim)
                else:
                    aggregated[f'avg_{dim_name}'] = None

            aggregated['round_count'] = len(set(
                r.round_number for r in dim_results if r.round_number is not None
            ))
            aggregated['completed_rounds'] = len(set(
                r.round_number for r in dim_results
                if r.round_number is not None and r.evaluation_status == 'completed'
            ))

            self._update_algorithm_result_aggregated(local_db_session, result_id, aggregated)
            local_db_session.commit()

            self._log(
                level='INFO',
                category='execution',
                content=f"多轮评估聚合完成: result_id={result_id}, aggregated={json.dumps(aggregated, ensure_ascii=False)}",
                task_id=task_id,
                test_case_id=test_case_id,
            )

            return aggregated
        except Exception as e:
            local_db_session.rollback()
            self._log(
                level='ERROR',
                content=f"多轮评估聚合失败: {str(e)}",
                task_id=task_id,
                test_case_id=test_case_id,
            )
            return {}
        finally:
            local_db_session.close()

    def _update_algorithm_result_aggregated(self, db_session, result_id, aggregated):
        """
        Write aggregated results into TestResult.algorithm_result['aggregated'].
        """
        test_result = db_session.query(TestResult).filter(
            TestResult.id == result_id
        ).first()

        if not test_result:
            return

        result_data = test_result.algorithm_result
        # 循环反序列化，处理可能的双重序列化旧数据
        while isinstance(result_data, str):
            try:
                result_data = json.loads(result_data)
            except (json.JSONDecodeError, TypeError):
                result_data = {}
        if not isinstance(result_data, dict):
            result_data = {}

        result_data['aggregated'] = aggregated
        test_result.algorithm_result = result_data
