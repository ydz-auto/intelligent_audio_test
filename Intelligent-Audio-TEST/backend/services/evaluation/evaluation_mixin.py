"""
评估服务通用混入（Mixin）和工具函数，消除各模块间的重复代码
"""
import json
from backend.utils.web.log_handler import log_and_emit


# ---- 评估状态口径（TaskCase.evaluation_status / TestResultDimension.evaluation_status）----
# 评估中：尚未到终态；其余取值（completed/failed/stopped/skipped）一律视为终态。
EVALUATION_STATUS_PENDING = 'pending'
EVALUATION_STATUS_QUEUED = 'queued'
EVALUATION_STATUS_RUNNING = 'running'
EVALUATION_STATUS_CALCULATING = 'calculating'
EVALUATION_STATUS_COMPLETED = 'completed'
EVALUATION_STATUS_FAILED = 'failed'
EVALUATION_IN_PROGRESS_STATUSES = (
    EVALUATION_STATUS_PENDING,
    EVALUATION_STATUS_QUEUED,
    EVALUATION_STATUS_RUNNING,
    EVALUATION_STATUS_CALCULATING,
)


class EvaluationLoggerMixin:
    """统一日志记录混入，所有评估模块继承此类即可获得 _log 方法"""

    def _log(self, level, content, task_id=None, test_case_id=None, api_id=None, **kwargs):
        log_and_emit(
            level=level,
            module='Evaluation',
            content=content,
            category=kwargs.pop('category', 'execution'),
            source='backend',
            task_id=task_id,
            api_id=api_id,
            test_case_id=test_case_id,
            **kwargs
        )


def get_endpoint_url(endpoint_item):
    """从端点配置项中提取URL，兼容 'url' 和 'endpoint' 两种字段名"""
    if not endpoint_item:
        return None
    return endpoint_item.get('url') or endpoint_item.get('endpoint')


def get_endpoint_field(endpoint_item, field_name, fallback_camel=None, default=None):
    """从端点配置项中提取字段值，兼容下划线和驼峰命名"""
    if not endpoint_item:
        return default
    val = endpoint_item.get(field_name)
    if val is None and fallback_camel:
        val = endpoint_item.get(fallback_camel)
    return val if val is not None else default


def update_task_case_status_in_db(local_db_session, task_id, test_case_id, status,
                                  evaluation_status=None, exclude_stopped=True):
    """
    统一更新 TaskCase 状态，返回影响行数

    Args:
        local_db_session: 数据库会话
        task_id: 任务ID
        test_case_id: 用例ID
        status: 新状态 (completed/failed)
        evaluation_status: 评估状态，默认与 status 一致
        exclude_stopped: 是否排除已停止的任务
    """
    from backend.models.models import TaskCase, utc8now

    if evaluation_status is None:
        evaluation_status = status

    query = local_db_session.query(TaskCase).filter(
        TaskCase.task_id == task_id,
        TaskCase.test_case_id == test_case_id,
    )
    if exclude_stopped:
        query = query.filter(TaskCase.status != 'stopped')

    update_data = {
        'status': status,
        'evaluation_status': evaluation_status,
        'completed_at': utc8now()
    }

    update_count = query.update(update_data, synchronize_session=False)
    return update_count


def get_task_dimension_evaluation_states(session, task_id, test_case_id=None):
    """按用例统计维度评估状态。

    Args:
        task_id: 任务ID
        test_case_id: 只统计该用例（为 None 时统计任务下全部用例，
                      供 maybe_finalize 一次判定，避免逐用例查询）

    Returns:
        dict: {test_case_id: {'total': 维度总数, 'in_progress': 评估中维度数,
                              'failed': 失败维度数}}
    """
    from backend.models.models import TestResult, TestResultDimension

    query = session.query(
        TestResult.test_case_id, TestResultDimension.evaluation_status
    ).join(
        TestResultDimension, TestResultDimension.test_result_id == TestResult.id
    ).filter(TestResult.task_id == task_id)
    if test_case_id is not None:
        query = query.filter(TestResult.test_case_id == test_case_id)

    states = {}
    for row_case_id, evaluation_status in query.all():
        state = states.setdefault(
            row_case_id, {'total': 0, 'in_progress': 0, 'failed': 0}
        )
        state['total'] += 1
        if evaluation_status in EVALUATION_IN_PROGRESS_STATUSES:
            state['in_progress'] += 1
        elif evaluation_status == EVALUATION_STATUS_FAILED:
            state['failed'] += 1
    return states


def is_case_evaluation_finished(evaluation_status, state):
    """用例的评估是否已到终态（判据以**维度级**为准）。

    为什么不能只看用例级 evaluation_status：update_task_case_status 在
    「已采集结果数 < 期望设备/API 数」或「维度数 < 期望维度数」时会提前 return，
    用例级会永久停在 calculating，而维度级其实早已全部到终态（VEGA-43 实测：
    e2e 任务配 3 台设备、用例只落 1 个 TestResult ⇒ 永远 1/3）。

    判据：
    - 用例级已是终态 ⇒ 已完成；
    - 用例级处于 pending/queued/running ⇒ 评估还没提交到 eval_server，
      该轮的维度记录可能尚未创建，不能凭「现有维度都到终态」判定完成 ⇒ 视为仍在评估；
    - 用例级处于 calculating ⇒ 已提交给 eval_server（endpoint_worker 提交前
      必定已建好该轮维度记录），此时「没有任何维度在评估中」即等价于评估算完了。

    Args:
        evaluation_status: 用例级 evaluation_status
        state: get_task_dimension_evaluation_states 中该用例的统计项
    """
    if evaluation_status not in EVALUATION_IN_PROGRESS_STATUSES:
        return True
    if evaluation_status != EVALUATION_STATUS_CALCULATING:
        return False
    return bool(state) and state['total'] > 0 and state['in_progress'] == 0


def sync_case_evaluation_status_from_dimensions(local_db_session, task_id, test_case_id):
    """维度级已全部到终态时，把用例级状态同步推进到与维度级一致的终态（VEGA-43）。

    触发场景：评估任务超时（wait_for_task_completion 返回 {'__error__': ...}）时
    只把维度级置 failed，用例级却因 update_task_case_status 的「结果数/维度数未全」
    守卫提前 return 而永久停在 calculating。用例级卡住会连锁导致：

    - maybe_finalize 判据不成立 ⇒ 任务永久 running，重评入口（只放行
      completed/failed/stopped/paused/skipped）被锁死；
    - reevaluate_type='failed' 要求用例级 == 'failed' ⇒ 唯一的补救通道不可达。

    只做「推进」不做「回退」：仅在用例级处于 calculating 且该用例已有维度记录、
    且没有任何维度仍在评估中时生效（is_case_evaluation_finished 的口径），
    终态/stopped/skipped 的用例一律不碰，保证不会误改「真在算」的用例。

    Returns:
        (是否推进, 新状态)；未推进时新状态为 None
    """
    from backend.models.models import TaskCase

    tc = local_db_session.query(TaskCase).filter_by(
        task_id=task_id,
        test_case_id=test_case_id,
    ).first()
    if not tc:
        return False, None

    state = get_task_dimension_evaluation_states(
        local_db_session, task_id, test_case_id
    ).get(test_case_id)
    if not is_case_evaluation_finished(tc.evaluation_status, state):
        return False, None

    new_status = (
        EVALUATION_STATUS_FAILED if state['failed'] else EVALUATION_STATUS_COMPLETED
    )
    # 复用统一更新函数：同步写 status + evaluation_status + completed_at，
    # 并保留「已 stopped 的用例不覆盖」语义
    update_count = update_task_case_status_in_db(
        local_db_session, task_id, test_case_id, new_status, new_status
    )
    if not update_count:
        return False, None

    local_db_session.commit()
    return True, new_status

