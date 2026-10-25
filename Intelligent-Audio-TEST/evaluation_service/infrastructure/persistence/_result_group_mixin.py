# -*- coding: utf-8 -*-
"""分组维度结果处理与算法结果快照混入

负责一组维度的评估结果处理流程编排，以及
algorithm_results 扁平快照的预提取与写回。

INT-1809（C2）：原始报文改「组级一次上传 + uri-only 落库」——
- 写：组入口按值去重上传（resp / req / 每轮 per_round 各一次），行上只写指针；
  对象写失败即整组按失败语义结束（不写任何 uri、不留 local://）。
- 读：快照构建改为吃**内存里的 payload**（本组刚写入的值按 sha 命中），
  只有别的组写下的行才按 sha 读对象，且每个唯一 sha 只读一次。

INT-1889 预存缺陷（本卡不动）：``algorithm_type`` 恒空导致输出声明退化为算法级。
"""
import json

from shared.infrastructure.raw_payload_store import (
    KIND_REQUEST,
    KIND_RESPONSE,
    raw_payload_store,
)
from shared.models.database import get_db_session
from shared.utils.status_constants import ExecutionStatus
from shared.utils.json_utils import deserialize_algorithm_result
from shared.models.common_enums import TestType
from evaluation_service.infrastructure.acl import task_acl_repository


class GroupResultMixin:
    """分组维度处理与 algorithm_results 快照方法"""

    def mark_test_result_completed(self, result_id):
        """
        标记 TestResult 完成（用于没有评估维度的场景）

        P1.4: 通过 gRPC 调 task_service.UpdateTestResultStatus
        """
        ok = task_acl_repository.update_test_result_status(
            result_id=result_id,
            execution_status=ExecutionStatus.COMPLETED,
        )
        self._log(
            level='DEBUG' if ok else 'ERROR',
            category='database',
            content=f"标记 TestResult {result_id} 为完成状态: {'成功' if ok else '失败'}"
        )

        # 预提取 algorithm_results 快照（无评估维度场景）
        if ok:
            try:
                tr = task_acl_repository.get_test_result_by_id(result_id)
                if tr:
                    self._build_and_store_algorithm_results(
                        result_id,
                        getattr(tr, 'task_id', None),
                        getattr(tr, 'test_case_id', None)
                    )
            except Exception as e:
                self._log(
                    level='WARNING',
                    category='execution',
                    content=f"预提取 algorithm_results 失败: {e}",
                )

    def process_group_dimension_results(self, resp_data, group_items, task_id, test_case_id, result_id, api_request_body, test_type=TestType.API.value, payload_store=None):
        """
        处理一组维度的评估结果

        P1.4: TestResult 通过 gRPC 读取（task_service）；TestResultDimension 本地写（自有 PO）

        INT-116: DB 会话只覆盖本地 TestResultDimension 写入并尽快提交释放连接，
        gRPC 读取、快照预提取（多次 gRPC+文件 IO）与状态推进全部移出会话——
        严禁在持连接（开事务）期间做跨服务调用/长 IO，防止连接池被长耗
        调用占满（task_service 过载时每次 gRPC 可达 30s 超时）。

        INT-1809（C2）：原始报文在**组入口**按值去重上传一次，组内各行只写指针。
        逐行上传会把每天约 8 千次写放大成 5 万次 OSS 操作，故不允许下沉到行级；
        逐轮值（per_round）每行可能不同，按值去重而非假设组内相同。

        Args:
            resp_data: API响应数据
            group_items: 维度组项列表 [(dim_data, dimension_result_id), ...]
            task_id: 任务ID
            test_case_id: 用例ID
            result_id: 结果ID
            api_request_body: API请求体
            test_type: 测试类型 (api 或 e2e)
            payload_store: 原始报文对象存储（默认进程级单例；测试可注入）

        Raises:
            StorageUnavailableError: 原始报文对象写失败（allow_fallback=False）。
                此时不写任何 uri，异常上抛由调用方按既有失败语义收口
                （endpoint_worker → mark_case_failed_if_active）。
        """
        store = payload_store or raw_payload_store

        # INT-1809（C2）：组级一次上传（先对象后库）。失败即整组不落库：
        # 不留「有评分但没有报文」的静默丢数据，也不留 local:// 假指针。
        per_round = resp_data.get('per_round', []) if isinstance(resp_data, dict) else []
        payload_cache = store.new_group_cache()
        try:
            payload_cache.warm(KIND_RESPONSE, resp_data)
            payload_cache.warm(KIND_REQUEST, api_request_body)
            for per_round_item in per_round:
                payload_cache.warm(KIND_RESPONSE, per_round_item)
        except Exception as e:  # noqa: BLE001 - 对象写失败按组失败收口
            self._log(
                level='ERROR',
                category='storage',
                content=f'原始报文外置失败，本组不写 uri 并按失败处理'
                        f'（result_id={result_id}, 用例ID: {test_case_id}）: {e}',
                task_id=task_id,
                test_case_id=test_case_id,
            )
            raise

        # 获取api_id和device_id（P1.4: 通过 gRPC 读 TestResult）——会话外执行
        api_id = None
        device_id = None
        if result_id:
            test_result = task_acl_repository.get_test_result_by_id(result_id)
            if test_result:
                api_id = test_result.api_id
                device_id = test_result.device_id
                test_case_id = test_case_id or test_result.test_case_id

        # 本地写：整组 TestResultDimension 更新，事务内只做本地 DB，提交即释放连接
        local_db_session = get_db_session()
        try:
            for dim_data, dimension_result_id in group_items:
                dim_id = dim_data['id']
                dim_name = dim_data['name']

                # 解析结果并打分
                raw_value, score = self.parse_dimension_result(resp_data, dim_data)

                # 记录维度评估详细结果到日志
                self._log(
                    level='INFO',
                    category='execution',
                    content=f"维度 {dim_name} 评估完成: "
                           f"用例ID: {test_case_id}, "
                           f"设备ID: {device_id}, "
                           f"API ID: {api_id}, "
                           f"原始值: {raw_value}, "
                           f"维度分值: {score}, "
                           f"响应数据: {json.dumps(resp_data, ensure_ascii=False)}",
                    task_id=task_id,
                    test_case_id=test_case_id,
                    api_id=api_id
                )

                # 更新维度评估结果，传入session避免重复创建
                self.update_dimension_result_completed(dimension_result_id, raw_value, score, task_id=task_id, test_case_id=test_case_id, api_raw_response=resp_data, api_request_body=api_request_body, session=local_db_session, raw_payload_cache=payload_cache)

            # 整体评估的 per_round 结果覆盖逐轮 TRD 记录（按 round_number 字段定位，不依赖数组下标）
            if per_round:
                # INT-176：仅原生 per_round（子服务守卫早返回路径打 per_round_native 标记）
                # 落库后才允许清理旧逐轮行；切片 fallback / 旧版子服务无标记
                # → is_native=False → 只覆盖不清理（子服务升级前绝对安全）
                is_native = self._per_round_is_native(resp_data)
                self._overwrite_round_results(
                    result_id=result_id, per_round=per_round,
                    group_items=group_items, session=local_db_session,
                    task_id=task_id, test_case_id=test_case_id,
                    api_request_body=api_request_body,
                    is_native=is_native,
                    raw_payload_cache=payload_cache,
                )

            # 循环结束后统一提交
            local_db_session.commit()
        finally:
            local_db_session.close()

        # 会话外：预提取 algorithm_results 快照，存入 result_data['algorithm_results']
        # INT-1809（C2）：快照构建吃本组内存 payload，不回读对象（见 _load_dim_result_rows）
        self._build_and_store_algorithm_results(
            result_id, task_id, test_case_id, test_type, payload_context=payload_cache
        )

        # 检查是否所有维度都已完成评估，如果是，更新TaskCase状态
        if result_id and test_case_id:
            if self.check_all_dimensions_completed(result_id, task_id):
                # Multi-round: aggregate before final status update
                if self.is_multi_round_result(result_id):
                    self.aggregate_round_results(result_id, task_id, test_case_id)
                self.update_task_case_status(result_id, True, task_id, test_case_id)

    @staticmethod
    def _unwrap_calc_result(resp_data):
        """剥掉 code/data 与 result 包装，返回子服务的 calc result dict。

        兼容两种到达形态：
        - 同步 HTTP：{'code':..,'data':{'result':{...}}}
        - 异步轮询取数后 / 事件回调：直接是裸 calc result {...}
        非 dict 或剥完为空 → 返回 {}。
        """
        if not isinstance(resp_data, dict):
            return {}
        data = resp_data
        if 'code' in data and 'data' in data:
            data = data.get('data') or {}
        if isinstance(data, dict) and 'result' in data:
            data = data.get('result') or {}
        return data if isinstance(data, dict) else {}

    @classmethod
    def _per_round_is_native(cls, resp_data):
        """判定 per_round 是否为子服务原生投影（守卫早返回路径所打 per_round_native 标记）。

        与 per_round 读取同款剥包装导航后读 calc result 顶层 per_round_native。
        标记缺失（旧版子服务 / 切片重跑 fallback）→ False，保证绝不误触发清理。
        """
        return cls._unwrap_calc_result(resp_data).get('per_round_native') is True

    def _build_and_store_algorithm_results(self, result_id, task_id, test_case_id, test_type=TestType.API.value, payload_context=None):
        """预提取 algorithm_results 扁平列表并存入 result_data['algorithm_results']。

        在评估完成后调用，报告页和详情页可直接读取，无需重复提取。

        INT-1809（C2）：``payload_context`` 为本次组处理的内存 payload 缓存
        （sha → 值）。快照构建优先吃内存，只有别的维度组写下的行才按 sha 读对象，
        避免「每组全量读该 result 所有行」在外置后退化成 OSS 往返放大。
        """
        if not result_id:
            return
        try:
            test_result = task_acl_repository.get_test_result_by_id(result_id)
            if not test_result:
                return

            # 获取 algorithm_type 和 resource
            algorithm_type = ''
            # algorithm_type 通过 TestResult 获取（若 DTO 不含则从 Task/TestCase 推断）
            algo_result = deserialize_algorithm_result(test_result.algorithm_result)

            task = task_acl_repository.get_task_by_id(task_id) if task_id else None

            # 获取 resource name
            device_id = test_result.device_id
            api_id = test_result.api_id
            # 通过 gRPC 获取设备/API 名称
            resource = f'result_{result_id}'
            try:
                resource = self._resolve_resource_name(result_id, device_id, api_id)
            except Exception:
                pass

            # 加载 algo_res 和 result_data
            from shared.utils.result_data_store import load_full_result_data, write_result_data_file, split_result_data
            result_data = load_full_result_data(test_result.result_data, test_result.result_data_path)
            if not isinstance(result_data, dict):
                result_data = {}

            if not (algo_result or result_data):
                return

            # 查询 dim_result_rows（INT-1809：只读指针列，payload 来自内存 / 对象）
            dim_result_rows = self._load_dim_result_rows(result_id, payload_context)

            # 查询 aux_params_map（通过 gRPC 调 algorithm_service）
            aux_params_map = self._load_aux_params_map(dim_result_rows)

            # 查询 output_fields（INT-1757 / C6b：按结果所属 API 实例作用域取）
            output_fields = self._load_output_fields(algorithm_type, api_id=api_id)
            # 设备输出声明：只用于轮内子键类型/展示名解析，不进展示字段清单
            device_output_fields = self._load_device_output_fields(algorithm_type)

            # 调用公共方法构建 algorithm_results
            from report_service.application.services.report_data_builder import ReportDataBuilder
            algorithm_results = ReportDataBuilder.build_algorithm_results_for_result(
                test_result, resource, algo_result, result_data,
                aux_params_map, dim_result_rows, output_fields, algorithm_type,
                device_output_fields=device_output_fields,
            )

            # 存入 result_data['algorithm_results']
            result_data['algorithm_results'] = algorithm_results if algorithm_results else None

            # 写回：大字段存文件，轻量部分存 DB
            lightweight, has_heavy = split_result_data(result_data)
            result_data_path = None
            if has_heavy:
                device_sn = str(api_id or result_id)
                result_data_path = write_result_data_file(task_id, test_case_id, device_sn, result_data)

            task_acl_repository.update_test_result_data(
                result_id, lightweight, result_data_path
            )

        except Exception as e:
            self._log(
                level='WARNING',
                category='execution',
                content=f"预提取 algorithm_results 失败: {e}",
                task_id=task_id, test_case_id=test_case_id
            )

    @staticmethod
    def _resolve_resource_name(result_id, device_id, api_id):
        """通过 gRPC 解析设备/API 名称作为 resource（失败时回退 result_id 形式）"""
        if device_id:
            from shared.clients.grpc_clients import get_device_config_service_stub
            from shared.proto import device_service_pb2 as dev_pb
            from shared.utils.grpc_json import loads as _grpc_loads
            dev_stub = get_device_config_service_stub()
            dev_resp = dev_stub.GetDevice(dev_pb.GetDeviceRequest(device_id=device_id))
            if dev_resp.success:
                dev_data = _grpc_loads(dev_resp.data, {})
                return dev_data.get('name') or f'device_{device_id}'
        elif api_id:
            from shared.clients.grpc_clients import get_api_test_service_stub
            from shared.proto import api_test_service_pb2 as api_pb
            from shared.utils.grpc_json import loads as _grpc_loads
            api_stub = get_api_test_service_stub()
            api_resp = api_stub.GetAPIConfig(api_pb.GetAPIConfigRequest(api_id=api_id))
            if api_resp.success:
                api_data = _grpc_loads(api_resp.data, {})
                return api_data.get('name') or f'api_{api_id}'
        return f'result_{result_id}'

    def _load_dim_result_rows(self, result_id, payload_context=None):
        """该结果的维度评估行，供快照构建（**不回读 JSON 列**）。

        INT-1809（C2）：payload 解析顺序——
        1. 内存：本次组处理刚写入的值（按行上 sha256 命中 ``payload_context``）；
        2. 对象：别的维度组写下的行，按其 sha256 从对象存储读，**每个唯一 sha
           只读一次**（内容寻址天然去重；``raw_payload_store`` 另有进程内缓存）；
        3. 行上既无字节也无指针 → payload 为 None（历史无报文行）。
        对象读失败即抛（调用方不写快照），绝不拿空 payload 静默降级。
        """
        local_db_session = get_db_session()
        try:
            from evaluation_service.infrastructure.persistence.orm_models import TestResultDimension
            rows = local_db_session.query(
                TestResultDimension.dimension_id,
                TestResultDimension.round_number,
                TestResultDimension.api_raw_response_uri,
                TestResultDimension.api_raw_response_sha256,
            ).filter(TestResultDimension.test_result_id == result_id).all()
        finally:
            local_db_session.close()

        payloads = {}
        memory_hits = 0
        pending = {}
        for dimension_id, round_number, uri, sha in rows:
            if sha:
                value = payload_context.value_for_sha(sha) if payload_context else None
                if value is not None:
                    payloads[sha] = value
                    memory_hits += 1
                elif uri:
                    pending.setdefault(sha, uri)
        for sha, uri in pending.items():
            payloads[sha] = raw_payload_store.load(KIND_RESPONSE, uri, sha)

        if pending:
            self._log(
                level='INFO',
                category='storage',
                content=f"快照构建读取原始报文: 行={len(rows)} 内存命中={memory_hits} "
                        f"对象读取={len(pending)}（唯一 sha 计数，非行数）",
            )
        return [{
            'dimension_id': dimension_id,
            'round_number': round_number,
            'api_raw_response': payloads.get(sha) if sha else None,
        } for dimension_id, round_number, _uri, sha in rows]

    @staticmethod
    def _load_aux_params_map(dim_result_rows):
        """查询 aux 参数映射（通过 gRPC 调 algorithm_service，仅收集可见的 output/aux 参数）"""
        all_dim_ids = set(dr.get('dimension_id') for dr in dim_result_rows
                          if dr.get('dimension_id'))
        aux_params_map = {}
        if not all_dim_ids:
            return aux_params_map
        try:
            from evaluation_service.infrastructure.acl.algorithm_acl_repository import AlgorithmRepository
            _algo_repo = AlgorithmRepository()
            for dim_id in all_dim_ids:
                params = _algo_repo.get_dimension_params(dim_id)
                if not params:
                    continue
                for p in params:
                    if not isinstance(p, dict):
                        continue
                    if p.get('param_direction') != 'output':
                        continue
                    if p.get('output_role') != 'aux':
                        continue
                    if not p.get('visible_in_report'):
                        continue
                    dim_name = p.get('dimension_name') or ''
                    if dim_id not in aux_params_map:
                        aux_params_map[dim_id] = []
                    aux_params_map[dim_id].append({'param': p, 'dimension_name': dim_name})
        except Exception:
            pass
        return aux_params_map

    @staticmethod
    def _load_output_fields(algorithm_type, api_id=None):
        """查询算法输出字段（通过 gRPC 调 algorithm_service）

        INT-1757（C6b）：``api_id`` 为该结果所属 API 实例（test_results.api_id），
        输出声明按 API 级覆盖算法级合并取；None 回落算法级默认。
        """
        output_fields = []
        if algorithm_type:
            try:
                from evaluation_service.infrastructure.acl.algorithm_acl_repository import AlgorithmRepository
                _algo_repo = AlgorithmRepository()
                output_fields = _algo_repo.get_output_fields(
                    algorithm_type, api_id=api_id) or []
            except Exception:
                pass
        return output_fields

    @staticmethod
    def _load_device_output_fields(algorithm_type):
        """查询设备输出声明（只用于 rounds 轮内子键类型/展示名解析）"""
        device_output_fields = []
        if algorithm_type:
            try:
                from shared.clients.grpc_clients import algo_get_device_output_fields
                device_output_fields = algo_get_device_output_fields(algorithm_type) or []
            except Exception:
                pass
        return device_output_fields
