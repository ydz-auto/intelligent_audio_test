# -*- coding: utf-8 -*-
"""API 执行器 — 编排层，持有并发管理器、任务执行器、结果处理器、会话执行器"""
import logging

from shared.utils.dto_utils import dto_to_dict
from shared.utils.status_constants import ExecutionStatus, EvaluationStatus, TaskCaseStatus
from shared.utils.query_utils import now_cst
from shared.models.common_enums import DeviceType, ExecutionLane, APIProtocol, lane_of
from shared.models.database import get_db_session
from shared.infrastructure.base_executor import BaseExecutor
from api_test_service.infrastructure.acl import (
    TaskDataAclRepositoryImpl,
    TestCaseConfigAclRepositoryImpl,
    AudioConfigAclRepositoryImpl,
    AlgorithmQueryAclRepositoryImpl,
    DeviceResultAclRepositoryImpl,
    AudioRenderACLRepositoryImpl,
)
from api_test_service.infrastructure.persistence.api_rms_spl_repository import (
    ApiRmsSplRepositoryImpl,
)
from api_test_service.application.round_render_service import RoundRenderService
from api_test_service.domain.services.api_rms_spl_service import ApiRmsSplService
from api_test_service.infrastructure.persistence.models import API
from api_test_service.domain.entities.api import resolve_api_endpoint
from api_test_service.core.api_concurrency_manager import APIConcurrencyManager
from api_test_service.core.api_task_runner import APITaskRunner
from api_test_service.core.api_result_processor import APIResultProcessor
from api_test_service.core.api_session_executor import APISessionExecutor
from api_test_service.core.realtime_session_executor import RealtimeSessionExecutor
from api_test_service.core.grpc_stream_executor import GrpcStreamExecutor
from api_test_service.core.stream_session_executor import StreamSessionExecutor
from shared.utils.config_manager import config_manager

logger = logging.getLogger(__name__)

# 跨服务出站 gRPC 经 ACL 仓储（返回 DTO），不返回 raw dict
_task_data_acl = TaskDataAclRepositoryImpl()
_testcase_acl = TestCaseConfigAclRepositoryImpl()
_audio_acl = AudioConfigAclRepositoryImpl()
_algo_acl = AlgorithmQueryAclRepositoryImpl()


class APIExecutor(BaseExecutor):
    def __init__(self, execution_engine):
        super().__init__(execution_engine)
        self._concurrency = APIConcurrencyManager(self)
        self._task_runner = APITaskRunner(self)
        self._result_processor = APIResultProcessor(self)
        self._session_executor = APISessionExecutor(self)
        self._realtime_executor = RealtimeSessionExecutor(self)
        # 流式道 gRPC 策略（INT-1789 / A1）：server-stream 按事件、bidi 按轮次；
        # 多轮聚合/落库/评估复用 APISessionExecutor，不新增第三条道。
        self._grpc_stream_executor = GrpcStreamExecutor(self)
        # A2（INT-1790）：流式道「按事件」策略（SSE / http chunked）
        self._stream_executor = StreamSessionExecutor(self)
        # 线性流混音渲染经 ACL 端口出站（RenderService 消费链路，INT-98 接线）
        self._render_service = RoundRenderService(
            AudioRenderACLRepositoryImpl(), spl_repo=ApiRmsSplRepositoryImpl(),
            audio_acl=AudioConfigAclRepositoryImpl())
        # 输出侧实测口径（INT-300 F3 三口径对称补齐）：线性单轮与多轮会话/
        # Realtime 同源服务对（被测 API 数字域 RMS→SPL）
        self._spl_repo = ApiRmsSplRepositoryImpl()
        self._spl_service = ApiRmsSplService(self._spl_repo)
        # 执行器注册表：按执行道（ExecutionLane）注册（INT-1799 / B0 裁定 §3.4）
        # 道只由 apis.streaming 决定；协议不参与定道，道内再按协议/轮次选策略。
        # physical 不在此表（E2E 走 e2e_test_service，由 task_service 侧分发）。
        self._executor_registry = {
            ExecutionLane.NON_STREAMING.value: self._session_executor,
            ExecutionLane.STREAMING.value: self._realtime_executor,
        }

    # 历史 device_type 值 → 执行道（INT-1799 兼容：老调用方/老测试仍可传
    # http_api / websocket_api，映射是确定性的，不是「未知值静默回退」）
    _LEGACY_DEVICE_TYPE_LANES = {
        DeviceType.HTTP_API.value: ExecutionLane.NON_STREAMING,
        DeviceType.WEBSOCKET_API.value: ExecutionLane.STREAMING,
    }

    @classmethod
    def _coerce_lane(cls, lane):
        """把 lane（ExecutionLane / 道值 / 历史 device_type 值）归一为道值。

        未知 / None 一律抛 ValueError——删除旧「未知类型回退 APISessionExecutor」
        的静默兜底（否则脏数据会被悄悄跑到非流式道）。
        """
        if isinstance(lane, ExecutionLane):
            return lane.value
        raw = str(lane or '').strip().lower()
        if raw in {item.value for item in ExecutionLane}:
            return raw
        legacy = cls._LEGACY_DEVICE_TYPE_LANES.get(raw)
        if legacy is not None:
            return legacy.value
        raise ValueError(
            f"未知执行道: {lane!r}（合法值: "
            f"{', '.join(item.value for item in ExecutionLane)}；"
            f"兼容历史 device_type: http_api/websocket_api）")

    def route_executor(self, lane):
        """按执行道取执行器；未知 lane 抛 ValueError（不静默回退）。"""
        return self._executor_registry[self._coerce_lane(lane)]

    # ── 流式道内策略（B0 裁定 §3.1 「按能力声明选择，不按协议名写 if/else」）──
    # 流式道收敛的骨架：B1 注册 websocket 会话策略（按轮次 + pacing / 打断），
    # A2（INT-1790）补 SSE / http chunked 的按事件策略（`event_rounds`）；
    # A1（gRPC）落地时按同一张表补一行。道本身（streaming / non_streaming）不再变。
    STREAMING_CAPABILITIES = {
        APIProtocol.WEBSOCKET.value: frozenset({
            'session_rounds', 'pacing', 'barge_in', 'client_push', 'session_affinity'}),
        # A2：SSE / http chunked 按事件（句子边界）切轮
        APIProtocol.SSE.value: frozenset({'event_rounds'}),
        APIProtocol.HTTP.value: frozenset({'event_rounds'}),
        APIProtocol.GRPC.value: frozenset({
            'event_rounds', 'session_rounds', 'client_push', 'session_affinity'}),
    }
    # protocol → 承载该策略的执行器属性名（未登记的协议 = 实现未上线）
    _STREAMING_STRATEGIES = {
        APIProtocol.WEBSOCKET.value: '_realtime_executor',
        # A1（INT-1789）：gRPC server-stream / bidi 同属流式道，道内按方法形态切轮
        APIProtocol.GRPC.value: '_grpc_stream_executor',
        # http + streaming=true = chunked 流式（非 text/event-stream），B0 §3.2.1
        APIProtocol.HTTP.value: '_stream_executor',
        APIProtocol.SSE.value: '_stream_executor',
    }

    def streaming_strategy(self, protocol):
        """取流式道内策略：返回 (executor, capabilities)；未上线协议抛 ValueError。

        未上线 ≠ 静默降级：与写侧可用矩阵同口径，抛错即用例失败并写明原因。
        """
        key = str(protocol or '').strip().lower()
        attr = self._STREAMING_STRATEGIES.get(key)
        if attr is None:
            raise ValueError(
                f"协议 {protocol} 与流式性 streaming=true 的组合实现未上线"
                f"（当前仅 websocket 会话 / gRPC server-stream·bidi / sse·http chunked 有执行器）")
        return getattr(self, attr), self.STREAMING_CAPABILITIES.get(key, frozenset())

    # 非流式道里没有「DUT 任务协议」（health/create_task/轮询/取结果）的协议：
    # 这些协议一次调用即一轮，直接按 rounds 逐次调用会话执行器（INT-1789）。
    _NO_DUT_PROTOCOLS = frozenset({APIProtocol.GRPC.value})

    def _get_result_mapper(self):
        """返回 DeviceResult ACL 仓储，供 ResultsMixin 使用"""
        return DeviceResultAclRepositoryImpl()

    def _get_algorithm_acl(self):
        """返回 algorithm_service ACL 仓储，供 DbMixin 使用"""
        return _algo_acl

    def _get_task_data_acl(self):
        """返回 task_service ACL 仓储，供 DbMixin 使用"""
        return _task_data_acl

    # ── 并发控制委托 ──
    @property
    def api_waiting_counts(self):
        return self._concurrency.api_waiting_counts

    def _get_task_lock(self, task_id):
        return self._concurrency.get_task_lock(task_id)

    def _cleanup_task_lock(self, task_id):
        return self._concurrency.cleanup_task_lock(task_id)

    def mark_task_completed(self, task_id):
        self._concurrency.mark_task_completed(task_id)

    def cleanup_completed_tasks(self):
        self._concurrency.cleanup_completed_tasks()

    def acquire_api_execution_right(self, api_id, task_id, current_test_case_id, max_process=None, timeout=None):
        # 并发参数配置化：max_process 缺省时从 config_manager 取默认值
        if max_process is None:
            max_process = config_manager.get_value('api_executor', 'default_max_process', 5)
        return self._concurrency.acquire(api_id, task_id, current_test_case_id, max_process, timeout)

    def release_api_execution_right(self, api_id, task_id):
        return self._concurrency.release(api_id, task_id)

    # ── 入口方法 ──
    def execute_api_case(self, task_id, tc_rel_id, device_type=None, device_id=None):
        """执行 API 测试用例

        Args:
            device_type/device_id: 调度侧路由决策（StartAPITest 下发，INT-71）；
                None 时回退 TaskCase 行值
        """
        try:
            self._log(level='DEBUG', content=f"开始执行测试用例: {tc_rel_id}", task_id=task_id)
            self._handle_control(task_id)

            if not self._claim_tc_rel_running(task_id, tc_rel_id):
                return True

            task_lock = self._get_task_lock(task_id)
            with task_lock:
                validate_result, data = self._validate_and_get_data(
                    task_id, tc_rel_id, device_type=device_type, device_id=device_id)
                if not validate_result:
                    self._handle_validation_failure(task_id, tc_rel_id, data)
                    return False

                return self._execute_single_or_multi(task_id, tc_rel_id, data)

        except Exception as e:
            import traceback
            self._log(level='ERROR', category='execution',
                      content=f"API 用例执行失败: {str(e)}\n{traceback.format_exc()}",
                      task_id=task_id if 'task_id' in locals() else None)
            return False
        finally:
            try:
                self._thread_ctx.current_test_case_id = None
            except Exception:
                logger.debug("清理 current_test_case_id 失败", exc_info=True)

    def _claim_tc_rel_running(self, task_id, tc_rel_id):
        """抢占 TaskCase 状态为 running，避免重复执行

        通过 ACL 仓储查询 TaskCase，检查 execution_status 是否为 pending/queued，
        若是则通过 update_task_case_status 更新为 running。
        """
        try:
            tcs = [dto_to_dict(d) for d in _task_data_acl.get_task_case_by_ids(task_id)]
            tc_rel = next((tc for tc in tcs if tc.get('id') == tc_rel_id), None)
            if not tc_rel:
                self._log(level='DEBUG',
                          content=f"测试用例 {tc_rel_id} 不存在，跳过",
                          task_id=task_id)
                return False
            if tc_rel.get('execution_status') not in [ExecutionStatus.PENDING, ExecutionStatus.QUEUED]:
                self._log(level='DEBUG',
                          content=f"测试用例 {tc_rel_id} 已在执行或已完成，跳过",
                          task_id=task_id)
                return False

            test_case_id = tc_rel.get('test_case_id')
            if not test_case_id:
                self._log(level='WARNING', content=f"TaskCase {tc_rel_id} 无 test_case_id", task_id=task_id)
                return False

            _task_data_acl.update_task_case_status(
                task_id=task_id,
                case_id=str(test_case_id),
                execution_status=ExecutionStatus.RUNNING,
                started_at=now_cst().isoformat(),
                # INT-604：多路由下按路由行精确命中，避免兄弟路由被打成同一终态
                tc_rel_id=tc_rel_id,
            )
            self.execution_engine._emit_progress(task_id, force=True)
            return True
        except Exception as e:
            self._log(level='WARNING', content=f"更新测试用例状态失败: {str(e)}", task_id=task_id)
            return False

    def _handle_validation_failure(self, task_id, tc_rel_id, data):
        """验证失败时更新 TaskCase 统计信息

        通过 ACL 仓储查询 TaskCase 统计 completed/failed 数量，
        然后触发进度更新（计数刷新由 task_service 端负责）。
        """
        try:
            tcs = [dto_to_dict(d) for d in _task_data_acl.get_task_case_by_ids(task_id)]
            completed = sum(1 for tc in tcs if tc.get('status') == TaskCaseStatus.COMPLETED)
            failed = sum(1 for tc in tcs if tc.get('status') == TaskCaseStatus.FAILED)
            self._log(level='DEBUG',
                      content=f"任务 {task_id} 统计: completed={completed}, failed={failed}",
                      task_id=task_id)
        except Exception as e:
            self._log(level='WARNING', content=f"查询任务统计失败: {str(e)}", task_id=task_id)
        finally:
            self.execution_engine._emit_progress(task_id, force=True)

    def _execute_single_or_multi(self, task_id, tc_rel_id, data):
        """按执行道分发执行器（INT-1799：道只由 streaming 决定）

        - streaming=true  → 流式道：websocket 会话策略（RealtimeSessionExecutor）；
          sse / http chunked 走按事件策略（StreamSessionExecutor，A2）；
          gRPC server-stream / bidi 走 GrpcStreamExecutor（A1）；
          注册表外的协议显式报错，不静默降级。
        - streaming=false → 非流式道：rounds>1 走 APISessionExecutor，否则线性
          （rounds 只是道内策略，不再用于推断流式性）。
        """
        test_case_id = data['test_case_id']
        case_name = data['case_name']
        algorithm_type = data.get('algorithm_type', 'translation')
        case_algorithm_params = data.get('case_algorithm_params')

        case_config = self._load_case_config(test_case_id)

        lane = lane_of(bool(data.get('streaming')))
        if lane is ExecutionLane.STREAMING:
            executor, capabilities = self.streaming_strategy(data.get('protocol'))
            self._log(level='INFO',
                      content=(f"用例 {case_name} streaming=true "
                               f"protocol={data.get('protocol')}，进入流式道"
                               f"（能力声明 {sorted(capabilities)}）"),
                      task_id=task_id, test_case_id=test_case_id)
            return executor.execute(task_id, tc_rel_id, data, case_config)

        rounds = case_config.get('rounds', [])
        # 非流式道内策略：HTTP 走 DUT 任务协议（health/create_task/轮询/取结果，
        # 单轮 = 线性）；gRPC unary 没有该任务协议，一次调用即一轮，按轮次
        # 逐次调用（单轮是 rounds=1 的特例，仍走会话执行器）。
        if data.get('protocol') in self._NO_DUT_PROTOCOLS:
            if not rounds:
                # 空 rounds（用例详情取不到等）不能落成「零请求 + 成功」：
                # 非流式道的会话执行器空 rounds 不进循环、直接判成功。gRPC
                # 一次调用即一轮，按 1 轮执行并留痕，与线性道同口径。
                self._log(level='WARNING',
                          content=(f"用例 {case_name} protocol={data.get('protocol')} "
                                   f"未配置轮次（rounds 为空），一次调用即一轮，"
                                   f"按 1 轮执行"),
                          task_id=task_id, test_case_id=test_case_id)
                case_config = {**(case_config or {}), 'rounds': [{}]}
                rounds = case_config['rounds']
            self._log(level='INFO',
                      content=(f"用例 {case_name} protocol={data.get('protocol')} "
                               f"streaming=false，非流式道按轮次直调"
                               f"（rounds={len(rounds)}）"),
                      task_id=task_id, test_case_id=test_case_id)
            return self.route_executor(lane).execute(task_id, tc_rel_id, data, case_config)

        if rounds and len(rounds) > 1:
            self._log(level='INFO',
                      content=f"用例 {case_name} 配置了 {len(rounds)} 轮，进入非流式多轮会话模式",
                      task_id=task_id, test_case_id=test_case_id)
            return self.route_executor(lane).execute(task_id, tc_rel_id, data, case_config)

        return self._execute_linear(task_id, tc_rel_id, data, case_config, algorithm_type, case_algorithm_params)

    def _execute_linear(self, task_id, tc_rel_id, data, case_config, algorithm_type, case_algorithm_params):
        """线性流程：遍历所有 API 配置，逐个执行"""
        test_case_id = data['test_case_id']
        case_name = data['case_name']
        api_configs = data['api_configs']
        audio = data['audio']
        api_specific_config = data['api_specific_config']
        total_audio_duration = data['total_audio_duration']

        # 通过 ACL 仓储查询 TaskCase 状态
        tc_rel = None
        try:
            tcs = [dto_to_dict(d) for d in _task_data_acl.get_task_case_by_ids(task_id)]
            tc_rel = next((tc for tc in tcs if tc.get('id') == tc_rel_id), None)
            if not tc_rel:
                self._log(level='ERROR', content=f"找不到 TaskCase: {tc_rel_id}", task_id=task_id)
                return False

            if tc_rel.get('execution_status') in [ExecutionStatus.PENDING, ExecutionStatus.QUEUED]:
                _task_data_acl.update_task_case_status(
                    task_id=task_id,
                    case_id=str(tc_rel.get('test_case_id', test_case_id)),
                    execution_status=ExecutionStatus.RUNNING,
                    started_at=now_cst().isoformat(),
                    # INT-604：多路由下按路由行精确命中
                    tc_rel_id=tc_rel_id,
                )
                self.execution_engine._emit_progress(task_id, force=True)
        except Exception as e:
            self._log(level='WARNING', content=f"查询/更新 TaskCase 状态失败: {e}", task_id=task_id)

        for api_config in api_configs:
            self._handle_control(task_id)

            # INT-305：用例被移除（执行中删除）→ 本用例静默收敛，
            # 不抛 TaskStopSignal 以免误伤任务内其它用例
            if getattr(self, '_is_case_removed', None) and self._is_case_removed(task_id, test_case_id):
                self._log(level='INFO', content=f"用例 {case_name} 已被移除，中断执行",
                          task_id=task_id, test_case_id=test_case_id)
                return False

            api_id = api_config.id

            # 并发参数配置化：api_config 未配置时回退到 config_manager 默认值
            max_process = getattr(api_config, 'default_max_process', None) or config_manager.get_value('api_executor', 'default_max_process', 5)
            if not self._concurrency.acquire(api_id, task_id, tc_rel_id, max_process=max_process):
                self._log(level='ERROR', content=f"API {api_id} 执行权获取失败，跳过",
                          task_id=task_id, api_id=api_id)
                continue

            try:
                self._run_single_api(
                    task_id, tc_rel_id, test_case_id, case_name, algorithm_type,
                    api_config, api_specific_config, audio,
                    total_audio_duration, case_config, case_algorithm_params
                )
            except Exception as e:
                import traceback
                self._log(level='ERROR', category='execution',
                          content=f"API {api_config.id} 用例 {case_name} 执行失败: {str(e)}\n{traceback.format_exc()}",
                          task_id=task_id, api_id=api_config.id)
                # 通过 ACL 仓储更新 TaskCase 为失败状态
                try:
                    tc_status = tc_rel.get('execution_status') if tc_rel else None
                    if tc_status and tc_status not in [ExecutionStatus.STOPPED]:
                        _task_data_acl.update_task_case_status(
                            task_id=task_id,
                            case_id=str(tc_rel.get('test_case_id', test_case_id)),
                            execution_status=ExecutionStatus.FAILED,
                            completed_at=now_cst().isoformat(),
                        )
                    eval_status = tc_rel.get('evaluation_status') if tc_rel else None
                    if eval_status and eval_status in [EvaluationStatus.QUEUED, EvaluationStatus.PENDING]:
                        _task_data_acl.update_task_case_status(
                            task_id=task_id,
                            case_id=str(tc_rel.get('test_case_id', test_case_id)),
                            status=TaskCaseStatus.FAILED,
                            evaluation_status=EvaluationStatus.COMPLETED,
                            completed_at=now_cst().isoformat(),
                        )
                except Exception as ue:
                    self._log(level='WARNING', content=f"更新 TaskCase 失败状态失败: {ue}", task_id=task_id)
            finally:
                self._concurrency.release(api_id, task_id)

        return True

    def _run_single_api(self, task_id, tc_rel_id, test_case_id, case_name, algorithm_type,
                        api_config, api_specific_config, audio,
                        total_audio_duration, case_config, case_algorithm_params):
        """执行单个 API 的完整流程：健康检查 -> 创建任务 -> 等待 -> 结果 -> 评估"""
        api_paths, select_base_url, release_base_url = self._task_runner.setup_endpoints(
            task_id, tc_rel_id, case_name, api_config
        )
        if not api_paths:
            return

        # INT-98 线性流音频交付契约（裁定：混音产物落存储后按引用交付）：
        # 混音/格式适配经 RenderAudioFile 消费链路（RoundRenderService 组装 +
        # AudioRenderAclRepository 端口出站），产物引用替换 file_path 后走既有
        # health_check / create_task 链路——厂商契约「交付一个可读文件」由统一
        # 存储层解析满足（DUT 侧 audio_input.py 按 scheme 解析，与原始 oss://
        # 引用同构）。渲染失败定用例失败，不静默回退原始路径。
        rendered = self._render_service.render_round_file_to_storage(
            api_config, self._resolve_linear_round_config(case_config), case_config,
            task_id, name_hint='linear')
        if not rendered or not rendered.get('path'):
            raise Exception(f"线性流混音渲染失败（RenderAudioFile 无产物）: 用例 {case_name}")
        audio = {**audio, 'file_path': rendered['path']}
        self._log(level='INFO',
                  content=f"线性流混音产物已落存储并按引用交付: {rendered['path']} "
                          f"(duration_ms={rendered.get('duration_ms', 0)})",
                  task_id=task_id, api_id=api_config.id)

        self._task_runner.health_check(
            task_id, case_name, audio, api_config, api_specific_config,
            api_paths, select_base_url, release_base_url
        )

        api_task_id = self._task_runner.create_task(
            task_id, audio, api_config, api_specific_config,
            api_paths, select_base_url, release_base_url, algorithm_type
        )

        try:
            start_wait_time, task_success, task_error_msg = self._task_runner.wait_for_completion(
                task_id, api_task_id, api_config, api_specific_config,
                api_paths, select_base_url, release_base_url, total_audio_duration
            )

            if not task_success:
                success = False
                error_msg = task_error_msg
                algo_result_dict = {}
                latency = 0
                final_result_result = {}
                self._log(level='ERROR',
                          content=f"API {api_config.id} 用例 {case_name} 执行失败，错误: {error_msg}",
                          task_id=task_id, api_id=api_config.id)
            else:
                final_result_result = self._task_runner.get_final_result(
                    task_id, api_task_id, api_config, api_specific_config,
                    api_paths, select_base_url, release_base_url
                )
                self._task_runner.get_frame_results(
                    task_id, api_task_id, api_config, api_specific_config,
                    api_paths, select_base_url, release_base_url
                )
                algo_result_dict, latency = self._task_runner.extract_final_result(
                    task_id, final_result_result, algorithm_type,
                    api_id=getattr(api_config, 'id', None)
                )
                # 输出侧实测口径（INT-300 F3 三口径对称补齐）：线性单轮
                # 与多轮会话/Realtime 同源——单轮协议回传的输出音频引用
                # （final_result data.output_audio_path）读档实测 RMS → SPL，
                # 并入 algorithm_result 落库（缺引用时字段缺省，不阻塞落库）
                self._attach_output_spl_evidence(
                    algo_result_dict, api_config, task_id,
                    final_result_result)
                success = True
                error_msg = None
                self._log(level='INFO',
                          content=f"API {api_config.id} 用例 {case_name} 执行成功，API耗时: {latency}ms",
                          task_id=task_id, api_id=api_config.id)

            result_id = self._result_processor.create_test_result(
                task_id, test_case_id, api_config.id, success, error_msg,
                algo_result_dict, latency, final_result_result, algorithm_type,
                tc_rel_id=tc_rel_id,
            )
        finally:
            if api_task_id:
                self._task_runner.delete_task(
                    task_id, api_task_id, api_config, api_specific_config,
                    api_paths, select_base_url, release_base_url
                )

        if success and result_id:
            self._evaluate_result(
                task_id=task_id, result_id=result_id, test_case_id=test_case_id,
                algo_result=algo_result_dict, case_config=case_config,
                case_reference_params=case_config.get('reference_params', {}) if case_config else {},
                algorithm_type=algorithm_type, test_type='api',
                case_algorithm_params=case_algorithm_params
            )
            self._log(level='INFO', category='evaluation',
                      content=f"API {api_config.id} 用例 {case_name} 采集完成，已提交评估队列",
                      task_id=task_id, api_id=api_config.id)

        self._log_single_api_result(task_id, case_name, success, algo_result_dict,
                                     case_config, case_algorithm_params,
                                     algorithm_type, test_case_id, api_config.id)

    @staticmethod
    def _resolve_linear_round_config(case_config):
        """线性流轮次渲染配置（INT-98）：镜像 _get_audio_data 的音频源语义——
        顶层 audios 优先（多源全量进入混音时间轴），为空回退唯一 rounds[0]
        （其 audios / background_noise 随轮次级配置生效）。"""
        case_cfg = case_config if isinstance(case_config, dict) else {}
        top_audios = [a for a in (case_cfg.get('audios') or [])
                      if isinstance(a, dict) and a.get('audio_id')]
        if top_audios:
            return {'audios': top_audios}
        rounds = case_cfg.get('rounds') or []
        if len(rounds) == 1 and isinstance(rounds[0], dict):
            return rounds[0]
        return {'audios': []}

    def _attach_output_spl_evidence(self, algo_result_dict, api_config, task_id,
                                    final_result_result=None):
        """线性单轮输出侧实测口径（INT-300 F3 对称补齐，原地并入 algo_result_dict）。

        单轮协议最终结果 data.output_audio_path（adapter 归档的 AI 输出音频
        存储引用）读档实测 RMS → SPL；无引用/读档失败字段缺省（None），
        不阻塞结果落库。与多轮会话/Realtime 同源服务对（ApiRmsSplService）。
        """
        try:
            ref = None
            if isinstance(final_result_result, dict):
                ref = (final_result_result.get('json', {}) or {}).get('data', {}) \
                    .get('output_audio_path')
            if not ref:
                return
            from shared.infrastructure.storage import storage
            pcm = storage.load_bytes(ref)
            if not pcm:
                return
            rms_dbfs = self._spl_service.calculate_rms_dbfs(pcm)
            try:
                mapping = self._spl_repo.get_default_mapping(
                    getattr(api_config, 'id', None))
            except Exception:
                logger.debug("查询 SPL 映射失败，按基准口径计算", exc_info=True)
                mapping = None
            algo_result_dict['ai_output_rms_dbfs'] = rms_dbfs
            algo_result_dict['ai_output_spl_db'] = \
                self._spl_service.rms_dbfs_to_spl(rms_dbfs, mapping)
        except Exception:
            logger.warning("线性单轮输出侧 SPL 实测失败（证据缺省不阻塞）",
                           exc_info=True, extra={'task_id': task_id})

    def _log_single_api_result(self, task_id, case_name, success, algo_result_dict,
                                case_config, case_algorithm_params,
                                algorithm_type, test_case_id, api_config_id):
        """记录单个 API 结果日志"""
        ref_fields = {}
        if case_config:
            for key, value in case_config.items():
                if value is not None:
                    ref_fields[key] = value
        if case_algorithm_params and isinstance(case_algorithm_params, dict):
            for key, value in case_algorithm_params.items():
                if value is not None:
                    ref_fields[key] = value

        full_case_params = {
            'algorithm_params': case_algorithm_params or {},
            'reference_params': case_config.get('reference_params', {}) if case_config else {},
            'algorithm_type': algorithm_type
        }
        all_params = dto_to_dict(_algo_acl.extract_case_all_params(full_case_params)) or {}
        # 算法服务不可达时 ACL 回退 ExtractedCaseParamsDTO()（evaluation=None），
        # 键存在但值为 None，get 默认值不生效 → 显式 None 兜底（INT-119）
        eval_params = (all_params.get('evaluation') or {}) if isinstance(all_params, dict) else {}
        for key, value in eval_params.items():
            if value is not None and key not in ref_fields:
                ref_fields[key] = value.get('text', '') if isinstance(value, dict) else value

        result_obj = {
            'device_id': None,
            'api_id': api_config_id,
            'success': success,
            'raw_results': {'success': success}
        }
        if algo_result_dict:
            for key, value in algo_result_dict.items():
                result_obj[key] = value

        self._log_case_result(task_id, case_name, result_obj, ref_fields,
                              algorithm_type=algorithm_type, test_case_id=test_case_id)

    def _load_case_config(self, test_case_id):
        """加载用例配置，注入 algorithm_params 和 reference_params"""
        try:
            case_data = dto_to_dict(_testcase_acl.get_test_case_detail(test_case_id)) or {}
            if not case_data:
                return {}
            case_config = case_data.get('config', {}) or {}
            rounds = case_config.get('rounds', [])
            if rounds and isinstance(rounds[0], dict):
                first_round = rounds[0]
                ap_dict = first_round.get('algorithm_params', {})
                if ap_dict and isinstance(ap_dict, dict):
                    case_config = case_config.copy()
                    case_config['algorithm_params'] = ap_dict
                ref_path = first_round.get('reference_params_path')
                if ref_path:
                    ref_data = _algo_acl.load_reference_params_file(ref_path)
                    if ref_data:
                        case_config['reference_params'] = ref_data
            return case_config
        except Exception as e:
            self._log(level='WARNING', content=f"加载用例配置失败: {e}", test_case_id=test_case_id)
            return {}

    def _validate_and_get_data(self, task_id, tc_rel_id, device_type=None, device_id=None):
        """验证并获取执行数据

        device_type/device_id 为调度侧路由决策（StartAPITest 下发，INT-71），
        优先于 TaskCase 行值（兼容不携带路由决策的调用方）。
        """
        self._handle_control(task_id)

        # 通过 ACL 仓储查询 TaskCase
        tc_rel = None
        try:
            tcs = [dto_to_dict(d) for d in _task_data_acl.get_task_case_by_ids(task_id)]
            tc_rel = next((tc for tc in tcs if tc.get('id') == tc_rel_id), None)
        except Exception as e:
            self._log(level='WARNING', content=f"查询 TaskCase 失败: {e}", task_id=task_id)
        if not tc_rel:
            raise ValueError(f"找不到测试用例关联记录，ID: {tc_rel_id}")

        # 通过 ACL 仓储查询 Task
        task = None
        try:
            task = dto_to_dict(_task_data_acl.get_task_by_id(task_id)) or {}
        except Exception as e:
            self._log(level='WARNING', content=f"查询 Task 失败: {e}", task_id=task_id)
        if not task:
            raise ValueError(f"找不到任务，ID: {task_id}")

        # 通过 ACL 仓储查询 TestCase 详情
        tc_rel_test_case_id = tc_rel.get('test_case_id')
        case = None
        try:
            case = dto_to_dict(_testcase_acl.get_test_case_detail(tc_rel_test_case_id)) or {}
        except Exception as e:
            self._log(level='WARNING', content=f"查询 TestCase 失败: {e}", task_id=task_id)
        if not case:
            raise ValueError(f"找不到测试用例，ID: {tc_rel_test_case_id}")

        self.current_test_case_id = case.get('id')
        self._thread_ctx.current_test_case_id = case.get('id')
        self._log('INFO', f"开始执行API用例: {case.get('name')}", task_id)

        api_configs = self._get_api_configs(task_id)
        processed_api_configs = self._process_api_configs(api_configs)

        tc_rel_id_local = tc_rel.get('id')
        test_case_id = case.get('id')
        case_name = case.get('name')
        # INT-1799：执行道由 apis.streaming 决定（不再看 device_type / rounds）。
        # device_type 仍是调度侧亲和域令牌（physical / http_api / websocket_api），
        # 这里只用于音频渲染出口与失败文案兜底。
        case_device_type = device_type or tc_rel.get('device_type') or DeviceType.HTTP_API.value
        case_config = case.get('config', {}) or {}
        algorithm_type = self._get_algorithm_type(case, case_config)

        if not processed_api_configs:
            error_msg = "找不到API配置"
            self._fail_tc_rel(tc_rel_id_local, error_msg, task_id=task_id)
            self._log('ERROR', f"API 用例 {case_name} 执行失败: {error_msg}", task_id)
            return False, None

        # INT-1799 单执行单元单道断言：一个任务内所有被测 API 的 streaming 必须
        # 一致（任务只用一个执行器跑全部 api_configs）。不一致即用例失败并写明
        # 原因（防历史脏数据绕过建任务校验后静默跑错道）。
        lane_flags = {bool(getattr(cfg, 'streaming', False)) for cfg in processed_api_configs}
        if len(lane_flags) > 1:
            error_msg = "同一任务内 API 流式性不一致（混选流式与非流式），无法确定执行道"
            self._fail_tc_rel(tc_rel_id_local, error_msg, task_id=task_id)
            self._log('ERROR', f"API 用例 {case_name} 执行失败: {error_msg}", task_id)
            return False, None
        case_streaming = lane_flags.pop()
        case_protocol = getattr(processed_api_configs[0], 'protocol', None) or APIProtocol.HTTP.value

        audio_data, total_audio_duration, error_msg = self._get_audio_data(
            tc_rel_test_case_id, case_device_type, case_name, task_id, tc_rel_id_local
        )
        if error_msg:
            return False, None

        # 重新加载 case_config 以获取 algorithm_params
        case_config2 = case_config
        algorithm_params = {}
        rounds = case_config2.get('rounds', [])
        if rounds and isinstance(rounds[0], dict):
            ap_dict = rounds[0].get('algorithm_params', {})
            if ap_dict and isinstance(ap_dict, dict):
                algorithm_params = ap_dict

        api_specific_config = case_config2.get('api', {})
        if not api_specific_config and case_device_type != DeviceType.PHYSICAL.value:
            api_specific_config = case_config2

        return True, {
            'tc_rel_id': tc_rel_id_local,
            'task_id': task_id,
            'test_case_id': test_case_id,
            'case_name': case_name,
            'algorithm_type': algorithm_type,
            # INT-1799：执行道判据（streaming 单值 + 协议，供流式道选策略）；
            # device_type 仅供亲和令牌透传 / 渲染出口 / 失败文案，不再定道
            'streaming': case_streaming,
            'protocol': case_protocol,
            'device_type': case_device_type,
            'device_id': device_id or tc_rel.get('device_id') or '',
            'api_configs': processed_api_configs,
            'audio': audio_data,
            'api_specific_config': api_specific_config,
            'total_audio_duration': total_audio_duration,
            'case_algorithm_params': algorithm_params
        }

    def _get_api_configs(self, task_id):
        """获取任务关联的所有 API 配置

        通过 gRPC GetTaskApis 获取 task_id 关联的 api_id 列表，
        再通过本地 DB 查询 API（本服务 PO）配置。
        """
        # 通过 ACL 仓储获取 TaskAPI 关联
        api_ids = []
        try:
            api_ids = [ta.api_id for ta in _task_data_acl.get_task_apis(task_id) if ta.api_id]
        except Exception as e:
            self._log(level='WARNING', content=f"查询 TaskApis 失败: {e}", task_id=task_id)
            return []

        if not api_ids:
            return []

        # 查询本地 API PO
        local_db_session = get_db_session()
        try:
            return local_db_session.query(API).filter(API.id.in_(api_ids)).all()
        finally:
            local_db_session.close()

    def _process_api_configs(self, api_configs):
        """将 API 配置转换为本地对象列表，避免分离对象问题"""
        processed = []
        for api_config in api_configs:
            class MockAPIConfig:
                def __init__(self, id, endpoint, api_endpoints, default_max_process, meta, max_timeout, vendor, adapter_class=None,
                             proxy_type=None, proxy_url=None, audio_config=None,
                             protocol=None, streaming=False):
                    self.id = id
                    self.endpoint = endpoint
                    self.api_endpoints = api_endpoints
                    self.default_max_process = default_max_process
                    self.meta = meta
                    self.max_timeout = max_timeout
                    self.vendor = vendor
                    self.adapter_class = adapter_class
                    self.proxy_type = proxy_type
                    self.proxy_url = proxy_url
                    # 目标音频格式声明（INT-1771）：执行器各路径经
                    # resolve_audio_config 统一取值，转换时必须保留顶层列
                    self.audio_config = audio_config
                    # INT-1799：白名单漏复制即恒 None/False（执行道与协议推断都会错）
                    self.protocol = protocol
                    self.streaming = streaming

            processed.append(MockAPIConfig(
                id=api_config.id,
                endpoint=resolve_api_endpoint(api_config),
                api_endpoints=api_config.api_endpoints or [],
                default_max_process=api_config.default_max_process or config_manager.get_value('api_executor', 'default_max_process', 5),
                meta=api_config.meta or {},
                max_timeout=api_config.max_timeout or 30,
                vendor=api_config.vendor or None,
                adapter_class=getattr(api_config, 'adapter_class', None),
                proxy_type=getattr(api_config, 'proxy_type', None),
                proxy_url=getattr(api_config, 'proxy_url', None),
                audio_config=getattr(api_config, 'audio_config', None),
                protocol=getattr(api_config, 'protocol', None) or APIProtocol.HTTP.value,
                streaming=bool(getattr(api_config, 'streaming', False)),
            ))
        return processed

    def _get_algorithm_type(self, case, case_config):
        """提取 algorithm_type"""
        algorithm_type = None
        if isinstance(case, dict):
            algorithm_type = case.get('algorithm_type')
        else:
            algorithm_type = getattr(case, 'algorithm_type', None)
        if not algorithm_type:
            algorithm_type = case_config.get('algorithm_type')
        if not algorithm_type:
            algorithm_type = 'translation'
        return algorithm_type

    def _get_audio_data(self, test_case_id, device_type, case_name, task_id, tc_rel_id):
        """获取音频数据，返回 (audio_data, total_duration, error_msg)

        通过 gRPC 查询 TestCase 配置和 Audio 信息。
        """
        # 通过 ACL 仓储查询 TestCase 配置
        try:
            case = dto_to_dict(_testcase_acl.get_test_case_detail(test_case_id)) or {}
            if not case:
                error_msg = "找不到测试用例"
                self._log('ERROR', f"API 用例执行失败: {error_msg}", task_id)
                self._fail_tc_rel(tc_rel_id, error_msg, task_id=task_id)
                return None, 0, error_msg
        except Exception as e:
            error_msg = f"查询测试用例失败: {e}"
            self._log('ERROR', f"API 用例执行失败: {error_msg}", task_id)
            self._fail_tc_rel(tc_rel_id, error_msg, task_id=task_id)
            return None, 0, error_msg

        config = case.get('config', {}) or {}
        audios = config.get('audios', [])
        if not audios:
            rounds = config.get('rounds', [])
            for round_item in rounds:
                if isinstance(round_item, dict):
                    round_audios = round_item.get('audios', [])
                    if isinstance(round_audios, list):
                        audios.extend(round_audios)

        target_audios = [a for a in audios if a.get('audio_id')]
        # 失败文案标签与 api_specific_config 兜底同源：由 device_type 派生（差异#2 收尾）
        expected_test_type = 'E2E' if device_type == DeviceType.PHYSICAL.value else 'API'

        if not target_audios:
            error_msg = f"测试用例未配置有效的 {expected_test_type} 测试音频"
            self._log('ERROR', f"{expected_test_type} 用例 {case_name} 执行失败: {error_msg}", task_id)
            self._fail_tc_rel(tc_rel_id, error_msg, task_id=task_id)
            return None, 0, error_msg

        # 通过 ACL 仓储查询 Audio 信息
        total_audio_duration = 0.0
        for audio_config in target_audios:
            audio_id = audio_config.get('audio_id')
            if audio_id:
                try:
                    a_data = dto_to_dict(_audio_acl.get_audio(audio_id)) or {}
                    total_audio_duration += a_data.get('duration', 0) or 0
                except Exception as e:
                    self._log(level='WARNING', content=f"查询 Audio {audio_id} 失败: {e}", task_id=task_id)

        audio_config = target_audios[0]
        audio_id = audio_config.get('audio_id')
        audio = None
        if audio_id:
            try:
                audio = dto_to_dict(_audio_acl.get_audio(audio_id)) or {}
            except Exception as e:
                self._log(level='WARNING', content=f"查询 Audio {audio_id} 失败: {e}", task_id=task_id)

        if not audio:
            error_msg = f"找不到ID为 {audio_id} 的音频文件"
            self._log('ERROR', f"{expected_test_type} 用例 {case_name} 执行失败: {error_msg}", task_id)
            self._fail_tc_rel(tc_rel_id, error_msg, task_id=task_id)
            return None, 0, error_msg

        audio_data = {
            'id': audio.get('id'),
            'name': audio.get('name'),
            'asr_text': audio.get('asr_text') or "",
            'file_path': audio.get('file_path')
        }
        self._log('DEBUG', f"API用例音频总时长: {total_audio_duration}秒", task_id)
        return audio_data, total_audio_duration, None

    def _fail_tc_rel(self, tc_rel_id, error_msg, task_id=None):
        """将 TaskCase 标记为失败（终态收敛）

        通过 ACL 仓储查询 TaskCase（需要 task_id）后更新状态。
        若 task_id 未提供，则仅记录日志。

        INT-161：失败即用例终态、评估不会再提交——评估停留 pending 会被
        task_service 主循环计入活跃评估集合（ACTIVE_EVALUATION_STATUSES 含
        PENDING），API 任务死等不收敛、直至进程重启被启动恢复改写失败原因，
        故补写评估终态（对齐 _finalize_dispatch_failure 逃生门口径），并在
        更新成功后发布 CASE_FAILED 事件，task_service 事件侧聚合任务计数。
        """
        if not task_id:
            self._log(level='WARNING', content=f"无法更新 TaskCase {tc_rel_id} 失败状态: 缺少 task_id")
            return

        try:
            tcs = [dto_to_dict(d) for d in _task_data_acl.get_task_case_by_ids(task_id)]
            tc_rel = next((tc for tc in tcs if tc.get('id') == tc_rel_id), None)
            if not tc_rel:
                self._log(level='WARNING', content=f"找不到 TaskCase: {tc_rel_id}", task_id=task_id)
                return

            test_case_id = tc_rel.get('test_case_id')
            if not test_case_id:
                self._log(level='WARNING', content=f"TaskCase {tc_rel_id} 无 test_case_id", task_id=task_id)
                return

            eval_status = tc_rel.get('evaluation_status')
            _task_data_acl.update_task_case_status(
                task_id=task_id,
                case_id=str(test_case_id),
                status=TaskCaseStatus.FAILED,
                execution_status=ExecutionStatus.FAILED,
                evaluation_status=(EvaluationStatus.COMPLETED
                                   if eval_status in (None, '',
                                                      EvaluationStatus.PENDING,
                                                      EvaluationStatus.QUEUED)
                                   else ''),
                error_message=error_msg,
                started_at=now_cst().isoformat(),
                completed_at=now_cst().isoformat(),
                # INT-604：多路由下按路由行精确命中
                tc_rel_id=tc_rel_id,
            )

            # 发布用例失败事件：唤醒 task_service 主循环并聚合任务级计数
            from shared.utils.redis_pubsub import EventBus, EventChannel, EventType
            from shared.infrastructure.worker_context import get_worker_instance_id
            EventBus().publish(
                EventChannel.CASE_EVENTS,
                EventType.CASE_FAILED,
                {
                    'task_id': str(task_id),
                    'test_case_id': str(test_case_id),
                    'result_id': None,
                    'success': False,
                    'worker_instance_id': get_worker_instance_id(),
                }
            )
        except Exception as e:
            self._log(level='WARNING', content=f"更新 TaskCase {tc_rel_id} 失败状态失败: {e}", task_id=task_id)
