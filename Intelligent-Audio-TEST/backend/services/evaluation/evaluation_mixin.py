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

# ---- 用例执行状态口径（TaskCase.execution_status）----
# 「执行已收尾」= 不会再派发新的轮次评估。多轮用例在轮次间隙该值仍是 running，
# 只有执行收尾后才能保证所有已配置轮次的维度都已建出（见 is_case_evaluation_finished）。
# 'failed' 同属收尾：某轮执行失败会 break 掉剩余轮次，剩余轮次的维度永不创建；
# 且执行失败的用例仍可走 reevaluate_type='failed' 重评，重评期间该值保持 'failed'
# （重评不重跑执行），若只认 'completed' 会让这类用例重评后永久停在 calculating。
EXECUTION_SETTLED_STATUSES = ('completed', 'failed')

# ---- 用例状态口径（TaskCase.status）：表示「用例已被人工停止」的取值 ----
# 停止路径实际写的是 'skipped'（execution_engine 停止分支：status='skipped'
# + execution_status/evaluation_status='stopped'），历史数据或服务重启恢复
# 路径可能留下 'stopped'；两者语义相同，兜底同步一律不得覆盖。
CASE_STATUS_STOPPED = ('stopped', 'skipped')


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
        exclude_stopped: 是否排除已被人工停止的用例（stopped/skipped）
    """
    from backend.models.models import TaskCase, utc8now

    if evaluation_status is None:
        evaluation_status = status

    query = local_db_session.query(TaskCase).filter(
        TaskCase.task_id == task_id,
        TaskCase.test_case_id == test_case_id,
    )
    if exclude_stopped:
        query = query.filter(~TaskCase.status.in_(CASE_STATUS_STOPPED))

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


def is_case_evaluation_finished(evaluation_status, state, execution_status=None):
    """用例的评估是否已到终态（判据以**维度级**为准）。

    为什么不能只看用例级 evaluation_status：update_task_case_status 在
    「已采集结果数 < 期望设备/API 数」或「维度数 < 期望维度数」时会提前 return，
    用例级会永久停在 calculating，而维度级其实早已全部到终态（VEGA-43 实测：
    e2e 任务配 3 台设备、用例只落 1 个 TestResult ⇒ 永远 1/3）。

    判据：
    - 执行未收尾（execution_status 不在 completed/failed 内）⇒ 轮次不完整，
      不认定评估结束（VEGA-52 D1：多轮用例每轮的维度是在**该轮评估派发时**才创建
      （evaluation_service._create_dimension_results ← e2e_executor 每轮结束派发），
      且某轮执行失败会 break 掉剩余轮次、剩余轮次维度**永不创建**。于是
      「现有维度都到终态」在轮次间隙等价于「上一轮算完、下一轮还没派发」，
      并非评估结束；只有执行收尾后才能保证所有会派发的轮次维度都已建出。
      重评路径不重跑执行、该值本就是 completed/failed，不影响 VEGA-43 要救的卡死场景。
      边界（VEGA-52 遗留窗口）：本前置只覆盖「执行侧」轮次完整性。重评路径
      （_run_reevaluation 先清空 TRD、再逐轮重建维度）在逐轮派发尚未走完时，
      用例级已可能是 calculating 而只有部分轮次的维度——该窗口需按「所有已配置
      轮次（含总评）的维度行都已建出」判定才能覆盖。本次未采用该更严口径：
      reevaluate_type='failed' 只重建失败维度（dimension_filter），「维度数齐」
      永不成立，会把 VEGA-43 要救的卡死场景重新锁死）；
    - 用例级已是终态 ⇒ 已完成；
    - 用例级处于 pending/queued/running ⇒ 评估还没提交到 eval_server，
      该轮的维度记录可能尚未创建，不能凭「现有维度都到终态」判定完成 ⇒ 视为仍在评估。
      注：这是有意边界（VEGA-52 D4）——「已派发但 worker 未取到」（worker 崩溃 /
      进程重启）造成的卡死不在本判据的兜底范围内，此类现场需要另行排查；
    - 用例级处于 calculating ⇒ 已提交给 eval_server（endpoint_worker 提交前
      必定已建好该轮维度记录），此时「没有任何维度在评估中」即等价于评估算完了。

    Args:
        evaluation_status: 用例级 evaluation_status
        state: get_task_dimension_evaluation_states 中该用例的统计项
        execution_status: 用例级 execution_status；为 None 表示调用方已自行
                          保证执行已收尾（如 maybe_finalize 的查询已过滤），跳过该校验
    """
    if execution_status is not None and execution_status not in EXECUTION_SETTLED_STATUSES:
        return False
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

    只做「推进」不做「回退」：仅在用例级处于 calculating、执行已收尾（completed/failed，
    保证轮次完整）且该用例已有维度记录、且没有任何维度仍在评估中时生效
    （is_case_evaluation_finished 的口径），保证不会误改「真在算」的用例。

    以下用例一律不碰（VEGA-52 D2：此前只要用例级不在评估中就会按维度重算终态并写库，
    会把已停止/已终态/执行失败的用例改写掉，与函数自述契约不符）：
    - 用例级不是 calculating（stopped/skipped/completed/failed 等）⇒ 直接不推进；
      只允许从 calculating 推进，可避免把 execution_status='failed' 的用例
      （e2e_aggregator 置 evaluation_status='failed'）在维度恰好全 completed 时改判 completed；
    - 用例已被人工停止（status 为 stopped/skipped）⇒ 由 update_task_case_status_in_db
      的 exclude_stopped 兜底过滤。

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

    # 只允许从 calculating 推进（白名单）：其余取值要么尚未派发（pending/queued/running，
    # 该轮维度可能还没建出），要么已是终态/已停止（不该被兜底改写）。
    if tc.evaluation_status != EVALUATION_STATUS_CALCULATING:
        return False, None

    state = get_task_dimension_evaluation_states(
        local_db_session, task_id, test_case_id
    ).get(test_case_id)
    # 用例没有任何维度记录：无据可依，不推进（也避免下方 state['failed'] 抛 TypeError）
    if not state:
        return False, None
    if not is_case_evaluation_finished(
        tc.evaluation_status, state, tc.execution_status
    ):
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

