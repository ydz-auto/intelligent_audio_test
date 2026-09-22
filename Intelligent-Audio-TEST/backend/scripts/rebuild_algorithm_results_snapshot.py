"""重建受影响测试结果的 algorithm_results 快照（修复多轮评估明细只保留一轮的问题）。

用法：python rebuild_algorithm_results_snapshot.py [task_id...]
不传参数时默认只重建最近报告关联任务的受影响结果（本脚本默认 task 375）。
"""
import sys
import json

sys.path.insert(0, r'd:\00_code\v9.7.10\Intelligent-Audio-TEST')

from backend.app import create_app
from backend.models.models import TestResult, TestResultDimension, TaskCase
from backend.models.database import db
from backend.services.evaluation.evaluation_result_processor import EvaluationResultProcessor

app = create_app('development')


def main():
    task_ids = [int(x) for x in sys.argv[1:]] or [375]
    with app.app_context():
        processor = EvaluationResultProcessor()
        sess = db.session()
        try:
            total = 0
            for task_id in task_ids:
                results = sess.query(TestResult).filter(TestResult.task_id == task_id).all()
                for tr in results:
                    # 仅处理有多轮评估维度的结果
                    has_rounds = sess.query(TestResultDimension).filter(
                        TestResultDimension.test_result_id == tr.id,
                        TestResultDimension.round_number.isnot(None),
                    ).first()
                    if not has_rounds:
                        continue
                    tc = sess.query(TaskCase).filter(TaskCase.task_id == task_id,
                                                     TaskCase.test_case_id == tr.test_case_id).first()
                    test_type = 'e2e' if tr.api_id is None else 'api'
                    processor._build_and_store_algorithm_results(
                        sess, tr.id, task_id, tr.test_case_id, test_type
                    )
                    total += 1
                    print(f'  rebuilt snapshot: result_id={tr.id} task_id={task_id} case={tr.test_case_id}')
            print(f'done, rebuilt {total} results')
        finally:
            sess.close()


if __name__ == '__main__':
    main()
