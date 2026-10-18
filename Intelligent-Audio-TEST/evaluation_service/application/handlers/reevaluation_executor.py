import threading
# P1.4: Task/TaskCase/TestResult/TestCase 改为通过 gRPC 调 task_service
# P1-1 DDD: 通过 Repository 访问自有 PO，不再直接 import orm_models / get_db_session
# P0-2 DDD: 业务规则下沉到 domain/services/reevaluation_service.py
from evaluation_service.infrastructure.acl import task_acl_repository, device_result_acl_repository
from evaluation_service.infrastructure.persistence.evaluation_dimension_repository import evaluation_dimension_repository
from shared.utils.log_handler import log_and_emit
from evaluation_service.infrastructure.evaluation_service_host import evaluation_service
from evaluation_service.domain.services.reevaluation_service import reevaluation_service
from shared.utils.result_data_store import load_full_result_data
from shared.utils.status_constants import (
    TaskStatus, ExecutionStatus, EvaluationStatus, TaskCaseStatus, ACTIVE_EVALUATION_STATUSES,
)
from shared.utils.id_normalizer import to_int_id
from shared.models.common_enums import TestType
from sqlalchemy import and_

# 重新评估类型判别符（非任务/用例状态，与 task_service 下发的 reevaluate_type 参数对应）
REEVALUATE_TYPE_ALL = 'all'
REEVALUATE_TYPE_FAILED = 'failed'

# INT-302：重评估范围模式（与 task_service RetryScopeMode 同构；评估侧独立常量，
# 不跨服务 import task_service 的枚举）
REEVALUATE_SCOPE_SELECTED = 'selected'
REEVALUATE_SCOPE_FAILED_ONLY = 'failed_only'
REEVALUATE_SCOPE_ALL = 'all'


class ReevaluationExecutor:
    """重新评估执行器 - 管理重新评估任务的队列

    P1.4 改造：所有 Task/TaskCase/TestResult/TestCase 的访问改为通过 task_acl_repository (gRPC)。
    仅保留 TestResultDimension 的本地 DB 访问（本服务自有 PO）。
    """

    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self.reevaluation_queue = []
        self.reevaluation_lock = threading.Lock()
        self.is_reevaluating = False
        self.running_task_id = None
        # 提交阶段进行中的任务集合：提交窗口内各用例尚未逐个置 queued，
        # "全部终态"是提交前旧状态的假象，maybe_finalize 据此不提前收敛
        self._submitting_tasks = set()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def submit(self, task_id, reextract_device_output=True, reevaluate_type='all', options=None):
        """提交重新评估任务

        P1.4: Task 读写通过 gRPC 调 task_service。

        INT-302：options 可选 {case_ids: [str], dimension_ids: [int], mode}——
        按用例过滤评估范围、按维度过滤评估维度；缺省 None 保持整任务全量语义。
        """
        # 各调用方（gRPC servicer / HTTP routes）的 ID 形态不一（proto string 契约），
        # 队列统一存 int；归一失败抛 ValueError 由调用方返回明确失败
        task_id = to_int_id('task_id', task_id)
        options = options or {}
        # INT-302/F2：selected 空集拒绝（与 task_service retry 400 语义对齐）——
        # 静默退化为全量重评会把"选择用例重评"变成整任务全量重评
        if (options.get('mode') == REEVALUATE_SCOPE_SELECTED
                and not [str(c) for c in (options.get('case_ids') or [])]):
            return False, "选择用例重评估时 case_ids 不能为空"
        with self.reevaluation_lock:
            if task_id == self.running_task_id:
                return False, "任务正在重新评估中"

            for item in self.reevaluation_queue:
                if item['task_id'] == task_id:
                    return False, "任务已在重新评估队列中"

            self.reevaluation_queue.append({
                'task_id': task_id,
                'reextract_device_output': reextract_device_output,
                'reevaluate_type': reevaluate_type,
                # INT-302：范围选择随任务入队（队列项隔离，互不影响）
                'options': {
                    'case_ids': [str(c) for c in (options.get('case_ids') or [])],
                    'dimension_ids': [int(d) for d in (options.get('dimension_ids') or [])],
                    'mode': options.get('mode') or REEVALUATE_SCOPE_ALL,
                },
            })

            # P1.4: 通过 gRPC 更新 Task 状态为 reevaluate_queued
            task_acl_repository.update_task_status(task_id, TaskStatus.REEVALUATE_QUEUED)

        # 重新评估前清理旧评估任务（方案A+B，INT-174）：
        # A. 从在途评估注册表按 task_id 摘除旧条目 —— 旧评估结果到达时被幂等忽略，
        #    不污染新结果；
        # B. 逐个通知子服务 cancel_task —— 真正停止/抑制旧任务的计算结果与回调。
        self._cancel_previous_evaluations(task_id)

        log_and_emit('INFO', 'reevaluator',
                     f"重新评估任务已提交: task_id={task_id}, type={reevaluate_type}",
                     task_id=task_id)

        self._check_queue()

        return True, "重新评估任务已提交"

    def _cancel_previous_evaluations(self, task_id):
        """取消该任务此前已提交、仍在途的评估任务（方案A+B）。

        方案A：从在途评估注册表（eval_task_registry）按 task_id 摘除旧条目并标记
        取消，旧评估结果到达时被消费方幂等忽略；
        方案B：逐个 DELETE {endpoint}/api/cancel_task/{eval_task_id} 通知子服务
        真正取消。子服务无该接口/不可达 → 记 WARNING 继续，不失败（契约兼容项，
        子服务能力由负责人整体复制后到位）。
        """
        try:
            from evaluation_service.infrastructure.evaluation_api.api_request_handler import eval_task_registry

            old_tasks = eval_task_registry.pop_by_task(task_id)
            if not old_tasks:
                return

            canceled = 0
            for eval_task_id, endpoint_url in old_tasks:
                if not endpoint_url:
                    continue
                try:
                    import requests
                    cancel_url = f"{endpoint_url.rstrip('/')}/api/cancel_task/{eval_task_id}"
                    resp = requests.delete(cancel_url, timeout=5)
                    if resp.status_code < 300:
                        canceled += 1
                except Exception as e:
                    log_and_emit('WARNING', 'reevaluator',
                                 f"通知子服务取消评估任务失败: eval_task_id={eval_task_id}, err={e}",
                                 task_id=task_id)

            log_and_emit('INFO', 'reevaluator',
                         f"重新评估前清理旧评估任务: task_id={task_id}, "
                         f"移除注册={len(old_tasks)}, 子服务取消={canceled}",
                         task_id=task_id)
        except Exception as e:
            log_and_emit('WARNING', 'reevaluator',
                         f"清理旧评估任务异常: err={e}", task_id=task_id)

    def _check_queue(self):
        """检查重新评估队列，启动下一个任务"""
        with self.reevaluation_lock:
            if self.is_reevaluating or not self.reevaluation_queue:
                return

            task_info = self.reevaluation_queue.pop(0)
            self.is_reevaluating = True
            self.running_task_id = task_info['task_id']
            self._submitting_tasks.add(task_info['task_id'])
            task_id = task_info['task_id']
            reextract_device_output = task_info['reextract_device_output']
            reevaluate_type = task_info['reevaluate_type']
            # INT-302：范围选择随队列项透传（旧队列项无此键，回退整任务语义）
            reeval_options = task_info.get('options') or {}

        # P1.4: 通过 gRPC 更新 Task 状态为 reevaluating
        task_acl_repository.update_task_status(task_id, TaskStatus.REEVALUATING)

        log_and_emit('INFO', 'reevaluator',
                     f"开始执行重新评估: task_id={task_id}",
                     task_id=task_id)

        # evaluation_service 本地线程池执行重新评估
        import threading
        thread = threading.Thread(
            target=self._run_reevaluation,
            args=(task_id, reextract_device_output, reevaluate_type, reeval_options),
            daemon=True,
        )
        thread.start()

    def _run_reevaluation(self, task_id, reextract_device_output, reevaluate_type, reeval_options=None):
        """执行重新评估

        INT-302：reeval_options {case_ids, dimension_ids, mode}——按用例过滤评估
        范围，按维度过滤评估维度（dimension_ids 传入 dimension_filter_ids 口径）。
        """
        reeval_options = reeval_options or {}
        scope_case_ids = [str(c) for c in (reeval_options.get('case_ids') or [])]
        scope_dimension_ids = [int(d) for d in (reeval_options.get('dimension_ids') or [])]
        success = False
        submitted_count = 0

        try:
            # 1. 重新提取设备输出（如果需要）
            if reextract_device_output:
                test_results = self._reextract_device_output(task_id, reevaluate_type)
            else:
                # P1.4: 通过 gRPC 读 TestResult
                test_results = task_acl_repository.get_test_results_by_task_and_case(task_id=task_id)

            # INT-302：按用例过滤结果集（selected 范围仅保留命中用例的结果；
            # 其余范围模式不过滤结果集，用例级取舍由收集函数判定）
            if scope_case_ids:
                case_id_set = set(scope_case_ids)
                test_results = [r for r in test_results if str(r.test_case_id) in case_id_set]

            # 2. 收集需要重新评估的用例
            if reevaluate_type == REEVALUATE_TYPE_ALL:
                cases_to_reevaluate = self._collect_reevaluation_cases_all(
                    task_id, test_results, reextract_device_output
                )
            elif reevaluate_type == REEVALUATE_TYPE_FAILED:
                cases_to_reevaluate = self._collect_reevaluation_cases_failed(
                    task_id, test_results, reextract_device_output
                )
            else:
                cases_to_reevaluate = []

            if not cases_to_reevaluate:
                if not test_results and task_acl_repository.get_task_by_id(task_id) is None:
                    # 无任何测试结果且查询不到任务：task_id 无效或 task_service 查询失败，
                    # 按失败收口，避免伪装成“没有需要重新评估的用例”被 success=True 掩盖
                    log_and_emit('ERROR', 'reevaluator',
                                 f"重新评估失败: task_id={task_id} 查询不到任务且无测试结果，无法重新评估",
                                 task_id=task_id)
                    success = False
                    return
                log_and_emit('WARNING', 'reevaluator',
                             f"没有需要重新评估的用例: task_id={task_id}, test_results_count={len(test_results)}",
                             task_id=task_id)
                success = True
                return

            # 将不满足重新评估条件的用例的评估状态标记为已完成，避免状态不一致
            reevaluated_case_ids = {c['test_case_id'] for c in cases_to_reevaluate}
            # P1.4: 通过 gRPC 读取所有 TaskCase，过滤需要标记的
            all_tc_rels = task_acl_repository.get_task_case_by_ids(task_id=task_id)
            for tc_rel in all_tc_rels:
                tc_case_id = tc_rel.test_case_id
                if (tc_case_id not in reevaluated_case_ids
                        and tc_rel.execution_status == ExecutionStatus.COMPLETED
                        and tc_rel.evaluation_status in ACTIVE_EVALUATION_STATUSES):
                    task_acl_repository.update_task_case_status(
                        task_id=task_id,
                        case_id=str(tc_case_id),
                        evaluation_status=EvaluationStatus.COMPLETED,
                    )

            # 3. 提交用例进行重新评估（INT-302：dimension_ids 随用例提交下传评估入口）
            submitted_count = self._submit_cases_for_reevaluation(
                task_id, cases_to_reevaluate, reevaluate_type,
                dimension_ids=scope_dimension_ids or None)

            success = True
            log_and_emit('INFO', 'reevaluator',
                         f"重新评估任务已提交: {len(cases_to_reevaluate)} 个用例，"
                         f"实际提交评估 {submitted_count} 个",
                         task_id=task_id)

        except Exception as e:
            import traceback
            log_and_emit('ERROR', 'reevaluator',
                         f"重新评估失败: {str(e)}, traceback: {traceback.format_exc()}",
                         task_id=task_id)

        finally:
            self._on_complete(task_id, success, submitted_cases=submitted_count)

    def _reextract_device_output(self, task_id, reevaluate_type):
        """通过 ACL 仓储重新提取设备输出"""
        reextract_result = device_result_acl_repository.reextract_result(task_id, reevaluate_type)

        if not reextract_result.get('success'):
            log_and_emit('WARNING', 'reevaluator',
                         f"重新提取设备输出失败: {reextract_result.get('message')}",
                         task_id=task_id)
        else:
            log_and_emit('INFO', 'reevaluator',
                         f"重新提取设备输出完成: {reextract_result.get('message')}",
                         task_id=task_id)

        # P1.4: 通过 gRPC 读 TestResult
        test_results = task_acl_repository.get_test_results_by_task_and_case(task_id=task_id)
        return test_results

    def _collect_reevaluation_cases_all(self, task_id, test_results, reextract_device_output):
        """收集所有需要重新评估的用例（all 类型）— Application 层编排。

        P0-2 DDD: 业务规则下沉到 domain/services/reevaluation_service.py。
        Application 只负责：预加载数据（full_data、TaskCase）+ 调用 Domain Service。
        """
        # 1. 预加载 full_data 和 TaskCase（基础设施访问）
        full_data_map = {}
        task_case_map = {}
        for result in test_results:
            tc_id = str(result.test_case_id)
            full_data = load_full_result_data(result.result_data, result.result_data_path)
            full_data_map[tc_id] = full_data or {}

            # 从文件恢复 raw_results，重新映射字段
            algo_result = reevaluation_service.deserialize_algorithm_result(
                result.algorithm_result or {}
            )
            self._remap_fields_from_raw(algo_result, full_data, result.test_case_id, result.id)
            result.algorithm_result = algo_result

            tc_rels = task_acl_repository.get_task_case_by_ids(task_id=task_id, case_ids=[tc_id])
            task_case_map[tc_id] = tc_rels[0] if tc_rels else None

        # 2. 调用 Domain Service 做业务判断（纯逻辑）
        return reevaluation_service.collect_cases_all(
            test_results, full_data_map, task_case_map, reextract_device_output
        )

    def _collect_reevaluation_cases_failed(self, task_id, test_results, reextract_device_output):
        """收集评估失败的用例（failed 类型）— Application 层编排。

        P0-2 DDD: 业务规则下沉到 domain/services/reevaluation_service.py。
        """
        # 1. 预加载 full_data 和 TaskCase
        full_data_map = {}
        task_case_map = {}
        for result in test_results:
            tc_id = str(result.test_case_id)
            full_data = load_full_result_data(result.result_data, result.result_data_path)
            full_data_map[tc_id] = full_data or {}

            algo_result = reevaluation_service.deserialize_algorithm_result(
                result.algorithm_result or {}
            )
            self._remap_fields_from_raw(algo_result, full_data, result.test_case_id, result.id)
            result.algorithm_result = algo_result

            tc_rels = task_acl_repository.get_task_case_by_ids(task_id=task_id, case_ids=[tc_id])
            task_case_map[tc_id] = tc_rels[0] if tc_rels else None

        # 2. 调用 Domain Service
        return reevaluation_service.collect_cases_failed(
            test_results, full_data_map, task_case_map, reextract_device_output
        )

    def _remap_fields_from_raw(self, algo_result, full_data, test_case_id, result_id=None):
        """从 raw_results 重新映射字段（Infrastructure 编排，涉及 ACL 仓储 + field_mapper）"""
        raw_results_list = full_data.get('raw_results_list') if full_data else None
        if not raw_results_list:
            return
        from evaluation_service.infrastructure.acl import algorithm_acl_repository
        test_case = task_acl_repository.get_test_case_detail(str(test_case_id))
        algorithm_type = test_case.algorithm_type if test_case and test_case.algorithm_type else 'translation'
        remapped_results = device_result_acl_repository.convert_results(
            [dict(r, raw_results=r.get('raw_results', {})) for r in raw_results_list],
            algorithm_type
        )
        rounds_in_algo = algo_result.get('rounds', [])
        for ri, remapped in enumerate(remapped_results):
            if ri < len(rounds_in_algo):
                field_defs = algorithm_acl_repository.get_field_mappings(algorithm_type)
                mapped_fields = field_defs.get_mapped_device_fields_list(algorithm_type)
                round_output = rounds_in_algo[ri].setdefault('output', {})
                if isinstance(mapped_fields, list):
                    for f in mapped_fields:
                        target = f.get('code') or f.get('target_param')
                        dim_id = f.get('dimension_id')
                        if dim_id is not None:
                            dim_key = f'{target}__dim_{dim_id}'
                            dim_val = remapped.get(dim_key)
                            if dim_val is not None:
                                round_output[dim_key] = dim_val
                        # 通用 key：重新评估时无条件用 raw_results_list 的值覆盖
                        val = remapped.get(target)
                        if val is not None:
                            round_output[target] = val

        # 写回数据库：raw_results_list 重新映射后的 algo_result 需要持久化
        # JSON 字段应直接存 dict，避免双重序列化
        if result_id is not None:
            task_acl_repository.update_test_result_algorithm_result(
                result_id=result_id,
                algorithm_result=algo_result if isinstance(algo_result, dict) else {},
            )

    def _submit_cases_for_reevaluation(self, task_id, cases_to_reevaluate, reevaluate_type=REEVALUATE_TYPE_ALL,
                                       dimension_ids=None):
        """提交用例进行重新评估

        P1.4: Task/TestCase 通过 gRPC 读

        INT-302：dimension_ids 非空时按维度过滤评估范围（对齐既有
        dimension_filter_ids 口径，None=不过滤）。

        Returns:
            int: 实际提交了评估的用例数（0=零提交，无任何评估在途）
        """
        submitted_count = 0
        for case_info in cases_to_reevaluate:
            test_case_id = case_info['test_case_id']
            result_id = case_info['result_id']
            algorithm_result = case_info['algorithm_result']
            reference_params = case_info.get('reference_params', [])
            device_id = case_info['device_id']

            try:
                # 差异#2 收尾：评估口径值由用例级 device_type 派生
                # （task.type 已废弃；gRPC 契约字段 test_type 保留）
                from shared.models.common_enums import DeviceType
                tc_dtos = task_acl_repository.get_task_case_by_ids(task_id, [str(test_case_id)])
                device_type = tc_dtos[0].device_type if tc_dtos else None
                test_type = (
                    TestType.E2E.value
                    if (device_type or DeviceType.PHYSICAL.value) == DeviceType.PHYSICAL.value
                    else TestType.API.value
                )

                # P1.4: 通过 gRPC 读 TestCase
                test_case = task_acl_repository.get_test_case_detail(str(test_case_id))
                algorithm_type = test_case.algorithm_type if test_case and test_case.algorithm_type else 'translation'
                reference_params_col = test_case.reference_params if test_case else None

                # P0-2: 多轮/单轮分发决策委托 Domain Service
                # INT-302：dimension_filter_ids 承载用户选择的维度过滤
                if reevaluation_service.is_multi_round(algorithm_result):
                    submitted = self._reevaluate_multi_round(
                        task_id=task_id,
                        result=result_id,
                        test_case_id=test_case_id,
                        algorithm_result=algorithm_result,
                        test_type=test_type,
                        algorithm_type=algorithm_type,
                        reference_params_col=reference_params_col,
                        reevaluate_type=reevaluate_type,
                        dimension_filter_ids=dimension_ids,
                    )
                else:
                    submitted = self._reevaluate_single(
                        task_id=task_id,
                        result_id=result_id,
                        test_case_id=test_case_id,
                        algorithm_result=algorithm_result,
                        reference_params=reference_params,
                        test_type=test_type,
                        algorithm_type=algorithm_type,
                        reference_params_col=reference_params_col,
                        reevaluate_type=reevaluate_type,
                        dimension_filter_ids=dimension_ids,
                    )

                if submitted is not False:
                    submitted_count += 1
                    log_and_emit('INFO', 'reevaluator',
                                 f"已提交评估: test_case_id={test_case_id}, device_id={device_id}",
                                 task_id=task_id, test_case_id=test_case_id)
                else:
                    log_and_emit('INFO', 'reevaluator',
                                 f"用例无需重新评估（无失败维度或无评估维度）: test_case_id={test_case_id}",
                                 task_id=task_id, test_case_id=test_case_id)

            except Exception as e:
                import traceback
                log_and_emit('ERROR', 'reevaluator',
                             f"重新评估用例失败: {str(e)}, traceback: {traceback.format_exc()}",
                             task_id=task_id, test_case_id=test_case_id)
        return submitted_count

    def _reevaluate_multi_round(self, task_id, result, test_case_id, algorithm_result, test_type, algorithm_type,
                               reference_params_col=None, reevaluate_type=None, dimension_filter_ids=None):
        """重新评估多轮结果 — Application 层编排。

        P0-2 DDD: 反序列化委托 Domain Service。

        reevaluate_type='failed' 时只重评失败的维度：按 TRD（evaluation_status='failed'
        及非终态 ACTIVE，重启遗留的 pending 维度一并纳入）收集 round_number → {dim_id}
        映射，已完成维度的 TRD 保留不动
        （评估入口 _create_dimension_results 会按 (result, dim, round) 复用并重置
        pending）；整体维度（round_number=None）按 None 键过滤。
        其余类型全量重评（清空 TRD）。

        INT-302：dimension_filter_ids 非 None 时按用户选择的维度过滤——
        与 reevaluate_type='failed' 取交集（失败集 ∩ 选中集），
        与其余类型直接按选中集过滤（未选维度 TRD 保留不动，
        不清空 TRD——沿用 failed 型「已完成维度保留」语义）。

        Returns:
            True=已提交评估, False=跳过评估（无失败维度）
        """
        algorithm_result = reevaluation_service.deserialize_algorithm_result(algorithm_result)
        rounds = algorithm_result.get('rounds', [])
        is_e2e = test_type == TestType.E2E.value

        # 只重评失败维度：按 (round_number -> {dim_id}) 收集失败维度。
        # INT-174 缺陷1：除 failed 外同时收集非终态（pending 等 ACTIVE）TRD——
        # 服务重启崩溃会把进行中评估的 TRD 永久留在非终态（task_service 启动恢复
        # 只终态化任务/用例，TRD 是本服务自有数据无人收尾），这类维度不会被任何
        # failed 型重评按「仅 failed」口径触达，统一收尾的全维终态门控随之拒绝
        # 收敛（用例/任务永久卡死）。已完成维度的 TRD 保留不动。
        failed_dims_by_round = None
        # INT-302：用户选择的维度集（None=未选择；非 None 时逐轮/整体均按其过滤，
        # 未选维度 TRD 保留不动——不清空 TRD，评估入口按 dimension_filter_ids 收敛）
        selection_dims = None
        if reevaluate_type == REEVALUATE_TYPE_FAILED:
            failed_dims_by_round = {}
            for score in evaluation_dimension_repository.list_scores_by_result_id(result):
                if (score.evaluation_status == EvaluationStatus.FAILED
                        or score.evaluation_status in ACTIVE_EVALUATION_STATUSES):
                    failed_dims_by_round.setdefault(score.round_number, set()).add(score.dimension_id)
            # INT-302：与用户选择的维度取交集（选中集为空视为全选，不过滤）
            if dimension_filter_ids:
                dim_set = set(int(d) for d in dimension_filter_ids)
                failed_dims_by_round = {
                    rnd: dims & dim_set for rnd, dims in failed_dims_by_round.items()
                }
                failed_dims_by_round = {rnd: dims for rnd, dims in failed_dims_by_round.items() if dims}
            if not failed_dims_by_round:
                # 没有失败的维度，无需重新评估；用例保持既有评估终态，
                # 不置 queued（防悬挂）
                log_and_emit('INFO', 'reevaluator',
                             f"用例无失败维度，跳过重新评估: test_case_id={test_case_id}, result_id={result}",
                             task_id=task_id, test_case_id=test_case_id)
                return False

            # 清空待重评维度的历史失败逐轮行（幽灵行，对齐 V9.7.10 f02ba75e）：
            # E2E 用例每轮未配置评估维度时，逐轮 TRD 行只是整体评估 per_round 投影
            # 的产物；某轮无有效值（如无接管/打断事件）时 per_round 投影不覆盖该轮，
            # 历史残留的 failed 逐轮行会永久保留，update_task_case_status 统计到
            # 失败维度把用例永久判为 failed。删除后由本次重新评估的 per_round 投影
            # 重新入库；整体行（round_number IS NULL）由评估入口
            # _create_dimension_results 复用重置为 pending，不在此删除。
            reeval_dim_ids = set()
            for _dims in failed_dims_by_round.values():
                reeval_dim_ids |= _dims
            if reeval_dim_ids:
                stale_count = evaluation_dimension_repository.delete_failed_round_scores(
                    result, reeval_dim_ids)
                if stale_count:
                    log_and_emit('INFO', 'reevaluator',
                                 f"清空待重评维度的历史失败逐轮行: test_case_id={test_case_id}, "
                                 f"dims={sorted(reeval_dim_ids)}, 删除 {stale_count} 条",
                                 task_id=task_id, test_case_id=test_case_id)
        elif dimension_filter_ids:
            # INT-302：全量重评但指定了维度——逐轮/整体按选中集过滤；
            # 不清空 TRD（未选维度结果保留），选中维度由评估入口
            # _create_dimension_results 按 (result, dim, round) 复用重置
            selection_dims = [int(d) for d in dimension_filter_ids]
        else:
            # 全量重评：清理旧的维度评估记录（通过 Repository，不直连 DB）
            evaluation_dimension_repository.delete_scores_by_result_id(result)

        # P1.4: 通过 gRPC 更新 TaskCase 状态
        tc_rels = task_acl_repository.get_task_case_by_ids(
            task_id=task_id, case_ids=[str(test_case_id)]
        )
        tc_rel = tc_rels[0] if tc_rels else None
        if tc_rel:
            # 重新评估只更新 evaluation_status，不修改 status（执行结果）
            task_acl_repository.update_task_case_status(
                task_id=task_id,
                case_id=str(test_case_id),
                evaluation_status=EvaluationStatus.QUEUED,
            )

        # P1.4: 通过 gRPC 读 TestCase
        test_case = task_acl_repository.get_test_case_detail(str(test_case_id))

        # 分派到具体的多轮评估实现
        if is_e2e:
            submitted_rounds = self._reevaluate_e2e_multi_round(
                task_id, result, test_case_id, algorithm_result,
                test_type, algorithm_type, reference_params_col, rounds, test_case,
                failed_dims_by_round=failed_dims_by_round,
                selection_dims=selection_dims,
            )
        else:
            submitted_rounds = self._reevaluate_api_multi_round(
                task_id, result, test_case_id, algorithm_result,
                test_type, algorithm_type, reference_params_col, rounds, test_case,
                failed_dims_by_round=failed_dims_by_round,
                selection_dims=selection_dims,
            )

        # INT-174 缺陷1：收口「不在本次提交范围」的遗留非终态 TRD——被配置排除
        # 的轮次（evaluation.enabled=false / 无整体口径维度）或过滤后无可评估维度
        # 的轮次，其非终态 TRD 永远不会被评估触达，统一收尾的全维终态门控会因此
        # 拒绝收敛。已在提交范围的轮次（TRD 被复用重置、评估在途）保持不动。
        if failed_dims_by_round is not None:
            self._sweep_out_of_scope_active_scores(result, submitted_rounds, task_id, test_case_id)
        # INT-632：返回值必须是「是否确有评估提交」，而非「是否已处理」。全部轮次
        # 被跳过（无维度可评估）时已由 _finalize_skipped_reevaluation 就地收尾、无
        # 任何评估在途——返回 True 会让 _submit_cases_for_reevaluation 误计
        # submitted_count>0，_on_complete 置 running 后无端点回调可触发收敛，任务
        # 永久卡 running、队列被占死。bool(submitted_rounds) 对齐 _reevaluate_single
        # 「提交成功才返回非 False」语义（已收尾的用例由零提交分支主动收敛）。
        return bool(submitted_rounds)

    def _reevaluate_e2e_multi_round(self, task_id, result, test_case_id, algorithm_result, test_type, algorithm_type,
                                     reference_params_col, rounds, test_case, failed_dims_by_round=None,
                                     selection_dims=None):
        """E2E多轮逐轮 + 整体评估

        对齐正常执行链（e2e_executor：逐轮 round_number=round_idx + 整体 round_number=None）
        与评估维度隔离设计文档 §3.3：
        - 逐轮：config.rounds[n].evaluation.enabled 非 False 且 dimensions 非空才提交，
          算法参数按轮取（algorithm_params_col 第 n 轮 / config.rounds[n].algorithm_params）
        - 整体：仅当顶层 config.dimensions 非空时提交（整体评估只取顶层维度），
          算法参数取第 1 轮

        INT-174：failed_dims_by_round 非 None（只重评失败维度）时，逐轮无失败维度的
        轮跳过、整体无失败维度跳过，并将失败维度作为 dimension_filter_ids 传入评估
        入口；全部被跳过时走到统一收尾（防 TaskCase 悬挂 queued）。

        P1.4: test_case 为 TestCaseDetailDTO（来自 gRPC）
        """
        from evaluation_service.infrastructure.acl import algorithm_acl_repository

        case_config = (getattr(test_case, 'config', None) or {}) if test_case else {}
        config_rounds = case_config.get('rounds', []) if isinstance(case_config, dict) else []
        algorithm_params_col = getattr(test_case, 'algorithm_params', None) if test_case else None
        submitted_rounds = set()

        # 逐轮评估：每轮各自的 dimensions
        for round_idx in range(len(rounds)):
            _round_eval_enabled = True
            if config_rounds and round_idx < len(config_rounds) and isinstance(config_rounds[round_idx], dict):
                _round_eval = config_rounds[round_idx].get('evaluation', {})
                if isinstance(_round_eval, dict):
                    if _round_eval.get('enabled', True) is False:
                        _round_eval_enabled = False
                    elif not _round_eval.get('dimensions'):
                        _round_eval_enabled = False

            if not _round_eval_enabled:
                continue

            # 只重评失败维度：本轮无失败维度则跳过；
            # INT-302 按维度选择：本轮取选中集（与轮次配置维度的交集收敛交给
            # 评估入口 dimension_filter_ids；config 无交集的轮次由入口过滤后
            # 返回 False 自然排除出 submitted_rounds）
            dimension_filter = None
            if failed_dims_by_round is not None:
                round_failed = failed_dims_by_round.get(round_idx)
                if not round_failed:
                    continue
                dimension_filter = list(round_failed)
            elif selection_dims is not None:
                dimension_filter = list(selection_dims)

            algo_params = {}
            if algorithm_params_col:
                from algorithm_service.domain.services.param_normalizer import ParamNormalizerService
                algo_params = ParamNormalizerService.normalize_algorithm_params(
                    ParamNormalizerService.get_round_algo_params(algorithm_params_col, round_idx + 1))
            elif round_idx < len(config_rounds) and isinstance(config_rounds[round_idx], dict):
                algo_params = config_rounds[round_idx].get('algorithm_params', {})

            full_case_params = {
                'algorithm_type': algorithm_type,
                'algorithm_params': algo_params,
                'reference_params': rounds[round_idx].get('reference_params', []),
                'reference_params_col': reference_params_col,
            }

            try:
                all_params = algorithm_acl_repository.extract_case_all_params(full_case_params)
                eval_params = all_params.get('evaluation', {}) if isinstance(all_params, dict) else {}
                eval_params['algorithm_type'] = algorithm_type
                eval_params['test_type'] = test_type
                if reference_params_col is not None:
                    eval_params['reference_params_col'] = reference_params_col
                if algorithm_params_col is not None:
                    eval_params['algorithm_params_col'] = algorithm_params_col
                if dimension_filter is not None:
                    eval_params['dimension_filter_ids'] = dimension_filter

                # INT-81：重评提交线程内的评估日志按轮次目录归档
                from shared.logging import log_round
                with log_round(round_idx):
                    round_submitted = evaluation_service.evaluate_case(
                        task_id=task_id,
                        result_id=result,
                        test_case_id=test_case_id,
                        algorithm_result=algorithm_result,
                        round_number=round_idx,
                        **eval_params,
                    )
                    if round_submitted is not False:
                        submitted_rounds.add(round_idx)

                    log_and_emit('INFO', 'reevaluator',
                                f"已提交 E2E 轮次评估: test_case_id={test_case_id}, round={round_idx}",
                                task_id=task_id, test_case_id=test_case_id)
            except Exception as e:
                import traceback
                log_and_emit('ERROR', 'reevaluator',
                            f"E2E 轮次重新评估失败: round={round_idx}, error={str(e)}, traceback={traceback.format_exc()}",
                            task_id=task_id, test_case_id=test_case_id)

        # 整体评估：仅当顶层 config.dimensions 非空时提交
        _has_overall_dims = bool(case_config.get('dimensions')) if isinstance(case_config, dict) else False
        if _has_overall_dims:
            # 只重评失败维度：整体（round_number=None）无失败维度则跳过整体提交；
            # INT-302 按维度选择：整体按选中集过滤（无交集由评估入口收敛）
            dimension_filter = None
            if failed_dims_by_round is not None:
                overall_failed = failed_dims_by_round.get(None)
                if overall_failed:
                    dimension_filter = list(overall_failed)
                elif not submitted_rounds:
                    # 兜底（INT-364 对齐 V9.7.10 f02ba75e，仅 failed 型——
                    # failed_dims_by_round 非 None 即 failed 型重评）：失败维度只
                    # 存在于逐轮 TRD（整体评估 per_round 投影写回所致）、逐轮分支
                    # 又全部未提交（每轮未配置逐轮维度 continue）时，整体
                    # （round_number=None）无失败维度若直接跳过，用例已被置回
                    # queued 却无人提交评估，永久卡 queued 并阻塞后续重新评估。
                    # 取所有轮次失败维度的并集走整体重评（经 dimension_filter_ids
                    # 传给评估入口过滤）。
                    round_failed_dims = set()
                    for _rn, _dims in failed_dims_by_round.items():
                        if _rn is not None:
                            round_failed_dims |= _dims
                    dimension_filter = list(round_failed_dims) if round_failed_dims else []
                    if dimension_filter:
                        log_and_emit('INFO', 'reevaluator',
                                     f"逐轮失败兜底走整体重评: test_case_id={test_case_id}, "
                                     f"dims={sorted(round_failed_dims)}",
                                     task_id=task_id, test_case_id=test_case_id)
                else:
                    dimension_filter = []  # 明确跳过整体提交
            elif selection_dims is not None:
                dimension_filter = list(selection_dims)

            if dimension_filter == []:
                pass  # 无整体口径失败维度，跳过
            else:
                algo_params = {}
                if algorithm_params_col:
                    from algorithm_service.domain.services.param_normalizer import ParamNormalizerService
                    algo_params = ParamNormalizerService.normalize_algorithm_params(
                        ParamNormalizerService.get_round_algo_params(algorithm_params_col, 1))
                elif config_rounds and isinstance(config_rounds[0], dict):
                    algo_params = config_rounds[0].get('algorithm_params', {})

                full_case_params = {
                    'algorithm_type': algorithm_type,
                    'algorithm_params': algo_params,
                    'reference_params': rounds[0].get('reference_params', []) if rounds else [],
                    'reference_params_col': reference_params_col,
                }

                try:
                    all_params = algorithm_acl_repository.extract_case_all_params(full_case_params)
                    eval_params = all_params.get('evaluation', {}) if isinstance(all_params, dict) else {}
                    eval_params['algorithm_type'] = algorithm_type
                    eval_params['test_type'] = test_type
                    if reference_params_col is not None:
                        eval_params['reference_params_col'] = reference_params_col
                    if algorithm_params_col is not None:
                        eval_params['algorithm_params_col'] = algorithm_params_col
                    if dimension_filter is not None:
                        eval_params['dimension_filter_ids'] = dimension_filter

                    overall_submitted = evaluation_service.evaluate_case(
                        task_id=task_id,
                        result_id=result,
                        test_case_id=test_case_id,
                        algorithm_result=algorithm_result,
                        **eval_params,
                    )
                    if overall_submitted is not False:
                        submitted_rounds.add(None)

                    log_and_emit('INFO', 'reevaluator',
                                f"已提交 E2E 整体评估: test_case_id={test_case_id}, rounds={len(rounds)}",
                                task_id=task_id, test_case_id=test_case_id)
                except Exception as e:
                    import traceback
                    log_and_emit('ERROR', 'reevaluator',
                                f"E2E 整体重新评估失败: error={str(e)}, traceback={traceback.format_exc()}",
                                task_id=task_id, test_case_id=test_case_id)

        if not submitted_rounds:
            self._finalize_skipped_reevaluation(
                task_id, result, test_case_id, failed_dims_by_round)
        return submitted_rounds

    def _finalize_skipped_reevaluation(self, task_id, result, test_case_id, failed_dims_by_round):
        """全部轮次被跳过、无任何评估提交时的用例收尾（防 TaskCase 悬挂 queued）。

        - 只重评失败维度（failed_dims_by_round 非空）：失败 TRD 保留为 failed 终态，
          用例按评估失败收口（失败原因聚合自失败 TRD）；
        - 全量重评但无任何可评估维度（INT-64 口径，保留）：标记结果完成并推进
          用例评估状态。
        """
        if failed_dims_by_round:
            try:
                from evaluation_service.infrastructure.evaluation_mixin import update_task_case_status_in_db
                from evaluation_service.domain.services.evaluation_utils import compose_case_error_message
                reasons = [
                    score.error_message
                    for score in evaluation_dimension_repository.list_scores_by_result_id(result)
                    if score.evaluation_status == EvaluationStatus.FAILED and score.error_message
                ]
                if not reasons:
                    reasons = ['重新评估（失败维度）无可用评估配置，失败维度保留失败终态']
                update_task_case_status_in_db(
                    None, task_id, str(test_case_id),
                    TaskCaseStatus.FAILED, EvaluationStatus.FAILED,
                    error_message=compose_case_error_message(reasons),
                )
                log_and_emit('INFO', 'reevaluator',
                            f"E2E/API 重评全部轮次被跳过，用例按评估失败收口: test_case_id={test_case_id}",
                            task_id=task_id, test_case_id=test_case_id)
            except Exception as e:
                log_and_emit('WARNING', 'reevaluator',
                            f"E2E/API 重评跳过收尾失败: test_case_id={test_case_id}, error={e}",
                            task_id=task_id, test_case_id=test_case_id)
            return

        # 无任何可评估维度：对齐旧行为收尾——标记结果完成并推进用例评估状态，
        # 避免 TaskCase 在重评后悬挂在 queued（旧整体单次调用会经评估入口无维度跳过路径收尾）
        try:
            evaluation_service.result_processor.mark_test_result_completed(result)
            evaluation_service._post_evaluate_updates(task_id, test_case_id)
            log_and_emit('INFO', 'reevaluator',
                        f"E2E 重评无维度可评估，已收尾: test_case_id={test_case_id}",
                        task_id=task_id, test_case_id=test_case_id)
        except Exception as e:
            log_and_emit('WARNING', 'reevaluator',
                        f"E2E 重评无维度收尾失败: test_case_id={test_case_id}, error={e}",
                        task_id=task_id, test_case_id=test_case_id)

    def _sweep_out_of_scope_active_scores(self, result_id, submitted_rounds, task_id, test_case_id):
        """收口「不在本次重评提交范围」的遗留非终态 TRD（INT-174 缺陷1）。

        提交范围外的非终态 TRD（重启崩溃残留的 pending、被配置排除轮次的
        中间态）永远不会被评估触达，统一收尾的全维终态门控会拒绝收敛。
        收口为 failed 终态（带原因），已提交轮次的在途 TRD 保持不动。
        收口失败仅记日志——该收口是收敛保障，不阻断重评提交本身。
        """
        try:
            swept = evaluation_dimension_repository.mark_active_scores_failed_excluding_rounds(
                result_id,
                submitted_rounds,
                '重新评估未覆盖该维度（重启遗留或无评估配置），收口为失败',
            )
            if swept:
                log_and_emit('WARNING', 'reevaluator',
                             f"已收口重评范围外的遗留非终态维度 {swept} 个: "
                             f"result_id={result_id}, 保留轮次={sorted(str(r) for r in (submitted_rounds or []))}",
                             task_id=task_id, test_case_id=test_case_id)
        except Exception as e:
            log_and_emit('ERROR', 'reevaluator',
                         f"收口重评范围外遗留非终态维度失败: result_id={result_id}, error={e}",
                         task_id=task_id, test_case_id=test_case_id)

    def _reevaluate_api_multi_round(self, task_id, result, test_case_id, algorithm_result, test_type, algorithm_type,
                                     reference_params_col, rounds, test_case, failed_dims_by_round=None,
                                     selection_dims=None):
        """API多轮逐轮评估

        INT-174：failed_dims_by_round 非 None（只重评失败维度）时，本轮无失败维度
        则跳过，并按失败维度过滤评估；全部轮次被跳过时走到统一收尾
        （防 TaskCase 悬挂 queued）。

        P1.4: test_case 为 TestCaseDetailDTO（来自 gRPC）
        """
        from evaluation_service.infrastructure.acl import algorithm_acl_repository

        submitted_rounds = set()

        # API: 逐轮评估
        for round_idx, round_data in enumerate(rounds):
            evaluation = round_data.get('round_evaluation', {})
            round_number = round_data.get('round_number', round_idx + 1) - 1

            if not evaluation:
                continue

            # 只重评失败维度：本轮无失败维度则跳过；
            # INT-302 按维度选择：本轮取选中集（交集收敛交给评估入口）
            dimension_filter = None
            if failed_dims_by_round is not None:
                round_failed = failed_dims_by_round.get(round_number)
                if not round_failed:
                    continue
                dimension_filter = list(round_failed)
            elif selection_dims is not None:
                dimension_filter = list(selection_dims)

            algo_params = {}
            algorithm_params_col = getattr(test_case, 'algorithm_params', None) if test_case else None
            if algorithm_params_col:
                from algorithm_service.domain.services.param_normalizer import ParamNormalizerService
                algo_params = ParamNormalizerService.normalize_algorithm_params(
                    ParamNormalizerService.get_round_algo_params(algorithm_params_col, round_idx + 1))
            elif test_case and test_case.config:
                config = test_case.config
                config_rounds = config.get('rounds', [])
                if round_idx < len(config_rounds) and isinstance(config_rounds[round_idx], dict):
                    algo_params = config_rounds[round_idx].get('algorithm_params', {})

            full_case_params = {
                'algorithm_type': algorithm_type,
                'algorithm_params': algo_params,
                'reference_params': round_data.get('reference_params', []),
                'reference_params_col': reference_params_col,
            }

            try:
                all_params = algorithm_acl_repository.extract_case_all_params(full_case_params)
                eval_params = all_params.get('evaluation', {}) if isinstance(all_params, dict) else {}
                eval_params['algorithm_type'] = algorithm_type
                eval_params['test_type'] = test_type
                if reference_params_col is not None:
                    eval_params['reference_params_col'] = reference_params_col
                if algorithm_params_col is not None:
                    eval_params['algorithm_params_col'] = algorithm_params_col
                if dimension_filter is not None:
                    eval_params['dimension_filter_ids'] = dimension_filter

                round_submitted = evaluation_service.evaluate_case(
                    task_id=task_id,
                    result_id=result,
                    test_case_id=test_case_id,
                    algorithm_result=algorithm_result,
                    round_number=round_number,
                    **eval_params,
                )
                if round_submitted is not False:
                    submitted_rounds.add(round_number)

                # INT-81：轮次上下文仅影响本线程日志的落盘目录
                from shared.logging import set_current_round
                set_current_round(round_number)
                try:
                    log_and_emit('INFO', 'reevaluator',
                                f"已提交轮次评估: test_case_id={test_case_id}, round={round_number}",
                                task_id=task_id, test_case_id=test_case_id)
                finally:
                    set_current_round(None)
            except Exception as e:
                import traceback
                log_and_emit('ERROR', 'reevaluator',
                            f"轮次重新评估失败: round={round_number}, error={str(e)}, traceback={traceback.format_exc()}",
                            task_id=task_id, test_case_id=test_case_id)

        # API 结果没有顶层 aggregated，需从 rounds 中计算
        if not algorithm_result.get('aggregated'):
            self._compute_and_store_api_aggregated(result, algorithm_result)

        if not submitted_rounds:
            self._finalize_skipped_reevaluation(
                task_id, result, test_case_id, failed_dims_by_round)
        return submitted_rounds

    def _reevaluate_single(self, task_id, result_id, test_case_id, algorithm_result, reference_params, test_type, algorithm_type,
                           reference_params_col=None, reevaluate_type=None, dimension_filter_ids=None):
        """重新评估单轮结果 — Application 层编排。

        P0-2 DDD: 反序列化委托 Domain Service。

        reevaluate_type='failed' 时只重评失败的维度，已完成维度的 TRD 保留不动；
        无失败维度 → 跳过（用例保持既有评估终态，不置 queued）。

        INT-302：dimension_filter_ids 非 None 时按用户选择的维度过滤——
        与 failed 型失败集取交集，与其余类型直接按选中集过滤（TRD 保留）。

        Returns:
            True=已提交评估, False=跳过评估（无失败维度）
        """
        algorithm_result = reevaluation_service.deserialize_algorithm_result(algorithm_result)

        # 只重评失败维度：收集失败的维度（含非终态 ACTIVE——重启遗留的 pending
        # 维度一并纳入，见 _reevaluate_multi_round 同款说明），已完成维度的 TRD 保留不动
        failed_dim_ids = None
        if reevaluate_type == REEVALUATE_TYPE_FAILED:
            failed_dim_ids = {
                score.dimension_id
                for score in evaluation_dimension_repository.list_scores_by_result_id(result_id)
                if (score.evaluation_status == EvaluationStatus.FAILED
                    or score.evaluation_status in ACTIVE_EVALUATION_STATUSES)
            }
            # INT-302：与用户选择的维度取交集（选中集为空视为全选，不过滤）
            if dimension_filter_ids:
                failed_dim_ids &= set(int(d) for d in dimension_filter_ids)
            if not failed_dim_ids:
                # 没有失败的维度，无需重新评估
                log_and_emit('INFO', 'reevaluator',
                             f"用例无失败维度，跳过重新评估: test_case_id={test_case_id}, result_id={result_id}",
                             task_id=task_id, test_case_id=test_case_id)
                return False
        elif dimension_filter_ids:
            # INT-302：全量重评但指定了维度——按选中集过滤（TRD 保留，不清空）
            failed_dim_ids = set(int(d) for d in dimension_filter_ids)
        else:
            # 全量重评：清理旧的维度评估记录（通过 Repository，不直连 DB）
            evaluation_dimension_repository.delete_scores_by_result_id(result_id)

        # P1.4: 通过 gRPC 更新 TaskCase 状态
        tc_rels = task_acl_repository.get_task_case_by_ids(
            task_id=task_id, case_ids=[str(test_case_id)]
        )
        tc_rel = tc_rels[0] if tc_rels else None
        if tc_rel:
            # 重新评估只更新 evaluation_status，不修改 status（执行结果）
            task_acl_repository.update_task_case_status(
                task_id=task_id,
                case_id=str(test_case_id),
                evaluation_status=EvaluationStatus.QUEUED,
            )

        # P1.4: 通过 gRPC 读 TestCase
        test_case = task_acl_repository.get_test_case_detail(str(test_case_id))

        # 优先从独立列读取 algorithm_params（按轮分组），兼容旧数据从 config.rounds 读取
        algo_params = {}
        algorithm_params_col = getattr(test_case, 'algorithm_params', None) if test_case else None
        if algorithm_params_col:
            from algorithm_service.domain.services.param_normalizer import ParamNormalizerService
            algo_params = ParamNormalizerService.normalize_algorithm_params(
                ParamNormalizerService.get_round_algo_params(algorithm_params_col, 1))
        elif test_case and test_case.config:
            config = test_case.config
            rounds = config.get('rounds', [])
            if rounds and isinstance(rounds[0], dict):
                algo_params = rounds[0].get('algorithm_params', {})

        full_case_params = {
            'algorithm_type': algorithm_type,
            'algorithm_params': algo_params,
            'reference_params': reference_params,
            'reference_params_col': reference_params_col,
        }

        from evaluation_service.infrastructure.acl import algorithm_acl_repository
        all_params = algorithm_acl_repository.extract_case_all_params(full_case_params)
        eval_params = all_params.get('evaluation', {}) if isinstance(all_params, dict) else {}
        eval_params['algorithm_type'] = algorithm_type
        eval_params['test_type'] = test_type
        if reference_params_col is not None:
            eval_params['reference_params_col'] = reference_params_col
        if algorithm_params_col is not None:
            eval_params['algorithm_params_col'] = algorithm_params_col
        if failed_dim_ids is not None:
            eval_params['dimension_filter_ids'] = list(failed_dim_ids)

        submitted = evaluation_service.evaluate_case(
            task_id=task_id,
            result_id=result_id,
            test_case_id=test_case_id,
            algorithm_result=algorithm_result,
            **eval_params
        )
        if failed_dim_ids is not None and submitted is not True:
            # 单轮结果未提交评估（过滤后无可评估维度等）：收口全部遗留非终态 TRD
            self._sweep_out_of_scope_active_scores(result_id, None, task_id, test_case_id)
        if submitted is not True:
            # 无维度可提交：回滚刚才置为 queued 的用例到终态（INT-364 对齐
            # V9.7.10 f02ba75e），避免用例卡 queued（无回调、maybe_finalize
            # 无法收尾），阻塞后续重新评估。评估入口无维度跳过路径会先行
            # 收尾（mark_test_result_completed + _post_evaluate_updates），
            # 此处仅在收尾未生效（TaskCase 仍 queued）时兜底回滚。
            self._rollback_case_if_stuck_queued(
                task_id, test_case_id,
                reevaluate_type=reevaluate_type)
        return submitted

    def _rollback_case_if_stuck_queued(self, task_id, test_case_id, reevaluate_type=None):
        """重评未提交任何评估时，回滚仍停留 queued/pending 的用例到终态（INT-364）。

        - failed 型重评回滚为 evaluation_status=failed（失败原因写入 error_message）；
        - 其余类型回滚为 evaluation_status=completed；
        - status 由执行终态恢复（derive 推导已能正确落 completed/failed）。
        幂等安全：仅当用例仍处 queued/pending 中间态才写，评估入口已收尾
        （终态）的用例不再触碰。
        """
        try:
            tc_rels = task_acl_repository.get_task_case_by_ids(
                task_id=task_id, case_ids=[str(test_case_id)])
            if not tc_rels:
                return
            tc_rel = tc_rels[0]
            if tc_rel.evaluation_status not in (
                    EvaluationStatus.QUEUED, EvaluationStatus.PENDING):
                return  # 评估入口已收尾（终态）或评估在途，不动

            rollback_eval = (
                EvaluationStatus.FAILED
                if reevaluate_type == REEVALUATE_TYPE_FAILED
                else EvaluationStatus.COMPLETED
            )
            rollback_case = (
                TaskCaseStatus.FAILED
                if reevaluate_type == REEVALUATE_TYPE_FAILED
                else TaskCaseStatus.COMPLETED
            )
            task_acl_repository.update_task_case_status(
                task_id=task_id,
                case_id=str(test_case_id),
                status=rollback_case,
                evaluation_status=rollback_eval,
                error_message=(
                    f"重新评估无维度可提交，回滚用例评估状态为 {rollback_eval}"
                    if reevaluate_type == REEVALUATE_TYPE_FAILED else ''
                ),
            )
            log_and_emit('WARNING', 'reevaluator',
                         f"重新评估无维度可提交，回滚用例评估状态: test_case_id={test_case_id}, "
                         f"evaluation_status={rollback_eval}, status={rollback_case}",
                         task_id=task_id, test_case_id=test_case_id)
        except Exception as e:
            log_and_emit('WARNING', 'reevaluator',
                         f"重评无维度提交回滚用例状态失败: test_case_id={test_case_id}, error={e}",
                         task_id=task_id, test_case_id=test_case_id)

    def _compute_and_store_api_aggregated(self, result_id, algorithm_result):
        """API 结果没有顶层 aggregated，从 rounds 计算 — Application 层编排。

        P0-2 DDD: 聚合计算委托 Domain Service，gRPC 写回留在 Application。
        """
        algo = reevaluation_service.deserialize_algorithm_result(algorithm_result)
        rounds = algo.get('rounds', [])
        if not rounds:
            return

        aggregated = reevaluation_service.compute_api_aggregated(rounds)
        if aggregated:
            algo['aggregated'] = aggregated
            task_acl_repository.update_test_result_algorithm_result(
                result_id=result_id,
                algorithm_result=algo,
            )

    def _on_complete(self, task_id, success, submitted_cases=None):
        """重新评估提交阶段完成回调（INT-174）。

        这里只代表"评估任务已全部提交"，评估本身仍在后台计算：
        - 提交成功且确有评估在途：任务置 running（不再直接置 completed），终态由
          maybe_finalize（所有已执行用例评估到终态后触发）收敛，重评队列同步保持
          占用直至收敛；
        - 提交成功但零提交（无待重评用例 / 全部轮次被跳过，INT-174 缺陷2）：无任何
          评估在途，端点 Worker 的结果回调（maybe_finalize 的唯一触发源）永远不会
          到达——必须主动收敛任务终态并释放重评队列，否则任务永久卡 running、
          队列被占死，后续任何重评被拒；
        - 提交失败：任务置 failed 并立即释放重评队列。

        P1.4: 通过 gRPC 更新 Task 状态
        """
        with self.reevaluation_lock:
            self._submitting_tasks.discard(task_id)
            if not success:
                self.is_reevaluating = False
                self.running_task_id = None

        from evaluation_service.infrastructure.evaluation_mixin import update_task_status_with_retry

        if success and submitted_cases == 0:
            try:
                finalized = self.maybe_finalize(task_id)
            except Exception as e:
                # 收敛判定依赖 gRPC 读任务/用例：task_service 不可达时按未收敛处理，
                # 队列仍须释放（零提交无在途评估，异常不得占死队列）
                log_and_emit('WARNING', 'reevaluator',
                             f"零提交重评收敛判定异常: task_id={task_id}, error={e}",
                             task_id=task_id)
                finalized = False
            if not finalized:
                # 暂不满足收敛条件（如存在执行未完成的用例）：按既有语义置 running，
                # 但队列必须释放——零提交意味着无在途评估，占用无意义
                update_task_status_with_retry(task_id, TaskStatus.RUNNING)
                log_and_emit('WARNING', 'reevaluator',
                             f"零提交重评暂不满足收敛条件，任务置 running 并释放重评队列: task_id={task_id}",
                             task_id=task_id)
            else:
                log_and_emit('INFO', 'reevaluator',
                             f"零提交重评已直接收敛任务终态: task_id={task_id}",
                             task_id=task_id)
            with self.reevaluation_lock:
                if self.running_task_id == task_id:
                    self.is_reevaluating = False
                    self.running_task_id = None
            self._check_queue()
            return

        new_status = TaskStatus.RUNNING if success else TaskStatus.FAILED
        status_updated = update_task_status_with_retry(task_id, new_status)

        log_and_emit('INFO' if status_updated else 'ERROR', 'reevaluator',
                     f"重新评估任务提交完成: task_id={task_id}, success={success}, 任务状态={new_status}"
                     + ("（评估仍在后台计算，任务终态由评估收敛驱动）" if success else ""),
                     task_id=task_id)

        if success and (submitted_cases or 0) > 0:
            # INT-632：端点回调在提交窗口内到达时，maybe_finalize 因 still_submitting
            # 拒绝提前收敛，而该回调是唯一触发源、之后不会再有回调——任务会永久卡
            # running。此处补一次收敛检查：快速评估（如 mock 端点）已在提交阶段完成
            # 时直接收敛为 completed；评估仍在途时返回 False，由后续端点回调收敛
            # （maybe_finalize 幂等，重复收敛安全）。
            try:
                self.maybe_finalize(task_id)
            except Exception as e:
                log_and_emit('WARNING', 'reevaluator',
                             f"提交完成后收敛判定异常: task_id={task_id}, error={e}",
                             task_id=task_id)

        if not success:
            # 提交失败：释放重新评估队列，启动下一个排队任务
            self._check_queue()

    def maybe_finalize(self, task_id):
        """检查重新评估是否真正完成（所有已执行用例的评估都到终态）。

        由评估结果回调（写完结果/终态后）调用；仅当该任务确实是当前重新评估
        处理中的任务、或确系服务重启后被恢复逻辑误标过的重新评估任务时才收尾，
        普通执行链评估任务不受影响。

        服务重启兼容：启动恢复会把"重新评估中/排队中"的任务及其中间态用例
        置为 failed，而端点队列（Redis）中残留的评估任务会在重启后被重新消费、
        写回结果并把用例逐个置回 completed。这里在用例全部到达终态后统一收尾
        为 completed；当前进程不再跟踪该任务（如重启后 running_task_id 清空）时，
        仅当全部用例执行均已完成且带「服务重启」标记（重启恢复写入
        task_case_relations.error_message）才兜底收尾——重新评估不重跑执行，
        其用例执行应全部完成；普通执行任务被重启中断时会有执行失败的用例，
        不会被误收尾。

        Returns:
            bool: 是否完成了本次收尾
        """
        all_tcs = task_acl_repository.get_task_case_by_ids(task_id=task_id)
        if not all_tcs:
            return False

        # 只检查已执行完成的用例（未执行用例不参与重新评估）
        executed_tcs = [tc for tc in all_tcs if tc.execution_status == ExecutionStatus.COMPLETED]
        if not executed_tcs:
            return False

        # 仍有用例在评估，继续等待
        if any(tc.evaluation_status in ACTIVE_EVALUATION_STATUSES for tc in executed_tcs):
            return False

        task = task_acl_repository.get_task_by_id(task_id)
        if not task:
            return False
        if task.status not in (TaskStatus.RUNNING, TaskStatus.FAILED,
                               TaskStatus.REEVALUATING, TaskStatus.REEVALUATE_QUEUED):
            return False

        with self.reevaluation_lock:
            is_current_task = (self.running_task_id == task_id)
            still_submitting = task_id in self._submitting_tasks

        if not is_current_task:
            # 服务重启后进程态丢失：仅当该任务确为被重启恢复误标的重新评估任务时才兜底收尾
            if not all(tc.execution_status == ExecutionStatus.COMPLETED for tc in all_tcs):
                return False
            if not any((tc.error_message or '').startswith('服务重启') for tc in executed_tcs):
                return False
        elif still_submitting:
            # 提交阶段尚未结束（部分用例尚未置 queued/提交评估），此刻"全部终态"
            # 是提交前旧状态的假象，不能据此提前收敛
            return False

        if task.status != TaskStatus.COMPLETED:
            from evaluation_service.infrastructure.evaluation_mixin import update_task_status_with_retry
            update_task_status_with_retry(task_id, TaskStatus.COMPLETED)

        log_and_emit('INFO', 'reevaluator',
                     f"重新评估完成: task_id={task_id}，任务状态更新为 completed",
                     task_id=task_id)

        # 释放重新评估队列，启动下一个排队任务（仅当自己仍是当前处理任务时）
        with self.reevaluation_lock:
            if self.running_task_id == task_id:
                self.is_reevaluating = False
                self.running_task_id = None
        self._check_queue()
        return True
