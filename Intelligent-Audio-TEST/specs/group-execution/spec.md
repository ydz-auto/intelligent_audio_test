# Spec：E2E 用例「组执行」——同实验室多设备并行、音频每轮只播一次

- 状态：待批准
- 日期：2026-10-29
- 涉及服务：task_service / e2e_test_service / shared(proto+config) / evaluation_service（仅消费，不改）

## 1. 目标（用户确认的三档语义）

| 场景 | 语义 | 音频播放 |
| --- | --- | --- |
| 同实验室 + 同 SN（同机多 App 或多条设备记录） | 强制串行 | 各自执行，各自播放 |
| 同实验室 + 不同 SN | 可并行（本规格的默认形态） | **同一用例音频每轮只播一次** |
| 目标 mode=serial | 逐行串行 | 每台设备各播一遍（等价执行两个用例） |
| 不同实验室 | 并行（阶段 B，见 §9 待确认） | 各实验室各播一遍（实验室物理隔离） |

本次里程碑（阶段 A）交付：**同实验室 + 不同 SN 的同一用例合并为「执行组」，一次 `StartE2ETask` 驱动全部组内设备，`play_round` 每轮只调用一次，结果按设备分别落库与评估**。

## 2. V9.7.10 基线证据（用户指定参考）

`D:\00_code\V9.7.10\Intelligent-Audio-TEST\backend\services\execution\e2e_device_manager.py`

- `get_device_info`（L21-46）：取任务 `TaskDevice` 全部设备 → 组装 `device_info_list`，不过滤单设备。
- `initialize_devices`（L78-121）：`pool = execution_engine.device_control_pool`，`pool.submit(init_device, info)` **并行**初始化，逐 `future.result(timeout=60)`。
- `pre_process_devices`（L122-156）：同样 `pool.submit(...pre_process...)` 并行。
- `post_process_devices`（L158+）：同样并行。

`D:\00_code\V9.7.10\Intelligent-Audio-TEST\backend\services\execution\e2e_executor.py`

- `_prepare_rounds`（L181-230）：一次执行取全部设备、初始化全部设备，预创建单条 TestResult。
- `_run_rounds_loop`（L341-419）：每轮 `playback_orchestrator.play_round(...)` **只播一次**，随后 `post_process_devices(device_info_list)`、`collect_results(..., device_info_list)`。

结论：V9.7.10 的「一次执行 / 多设备 / 音频一次」能力在 V9.7.31 的 e2e 层**结构上仍然存在**（`initialize_devices` / `pre_process_devices` / `post_process_devices` / `collect_results` 均按 `device_info_list` 循环并行，`play_round` 每轮一次）。V9.7.31 之所以变成「每台设备各播一遍」，唯一原因是**调度层按路由行逐行派发**并在 `_prepare_rounds` 用 `device_id` 收窄成单设备（`e2e_test_service/application/services/e2e_executor/preparation_mixin.py#L25`、`e2e_test_service/application/services/e2e_device_manager.py#L42-46`）。

## 3. 现状关键约束（必须遵守，否则改完会卡任务）

1. 主循环单线程同步：`task_service/core/execution_engine/mixins/task_lifecycle.py` 的 `_process_task_main_loop`，`_dispatch_e2e_case` 内同步等待 gRPC 返回。
2. 物理互斥按 SN：`task_dispatch.py#L399-457`（`TASK_PHYSICAL_LOCK`，等待 `TASK_PHYSICAL_LOCK_WAIT_SECONDS`）。
3. 串行门控按用例维度：`task_dispatch.py#L109-186`（`_get_next_pending_case_target_gated`）。
4. **评估侧要求「每路由行一条 TestResult」**：
   - `evaluation_service/infrastructure/persistence/_result_status_mixin.py#L211-289`：非 legacy 行按 `results_by_device[str(row.device_id)]` 逐行取结果，缺结果 → `case_all_finished=False`。
   - `evaluation_service/domain/services/evaluation_service/dimension_result_recorder.py#L12-50`：`_resolve_tc_rel_id` 用 `result.device_id` 匹配路由行。
   - 因此「组只产出一条结果（device_id=首台）」会让组内其它行永远拿不到评估终态 → 任务卡 running。**本规格强制每设备一条 TestResult。**

## 4. 设计总览

```
task_service 主循环
  └─ _get_next_pending_case            （沿用用例维度门控）
       └─ _dispatch_case_by_type
            └─ _dispatch_e2e_case
                 ├─ 组选择 _build_e2e_execution_group  → 组内 1 行：原路径（零回归）
                 └─ 组内 >=2 行：_dispatch_e2e_group
                       ├─ 批量原子认领 _claim_case_group
                       ├─ 逐 SN 抢锁（排序，全成或全退）
                       ├─ gRPC StartE2ETask(device_ids=[...])
                       └─ 逐行收敛（refresh + 失败兜底），finally 释放全部锁

e2e_test_service
  └─ servicers.StartE2ETask(device_ids)
       └─ E2EService.start_e2e_case(device_ids)
            └─ E2EExecutor.execute_e2e_case(device_ids)
                 ├─ _resolve_group_rows        device_id → tc_rel_id，逐行 RUNNING
                 ├─ _prepare_rounds            get_device_info(device_ids) + 每设备一条 TestResult
                 ├─ _run_rounds_loop           每轮 play_round 一次 → 采集多设备结果 → 按设备写结果/评估
                 └─ _finalize_rounds           逐设备聚合 + 整体评估 + 逐行写 TaskCase 状态
```

组大小始终为 1 时，全链路行为与当前版本等价（dict 只有一台设备）。

## 5. 精确改动清单

### 5.1 shared/proto

文件：`shared/proto/e2e_test_service.proto`

```proto
message StartE2ETaskRequest {
  string task_id = 1;
  string tc_rel_id = 2;
  string e2e_config = 3;
  int32 device_id = 4;          // 兼容保留：单设备派发
  repeated int32 device_ids = 5; // 组执行：一次驱动组内全部设备
}
```

语义：`device_ids` 非空 → 组执行（优先）；`device_id != 0` → 单设备；两者皆空 → 任务全部设备（历史行为）。

生成物：`shared/proto/e2e_test_service_pb2.py`、`shared/proto/e2e_test_service_pb2_grpc.py` 需按仓库既有 protoc 方式重新生成（`python -m grpc_tools.protoc -I shared/proto --python_out=shared/proto --grpc_python_out=shared/proto shared/proto/e2e_test_service.proto`）。

### 5.2 shared 配置

文件：`shared/infrastructure/config.py`（`BaseConfig` 内，与 `TASK_PHYSICAL_LOCK_WAIT_SECONDS` 同区）

| 配置项 | 默认 | 说明 |
| --- | --- | --- |
| `E2E_GROUP_EXECUTION_ENABLED` | `True` | 组执行总开关；关闭即回退逐行派发 |
| `E2E_GROUP_MAX_DEVICES` | `8` | 单组设备上限，超出按 `created_at, id` 截断，剩余下一轮再组 |

### 5.3 task_service 调度层

文件：`task_service/core/execution_engine/mixins/task_dispatch.py`

新增方法：

- `_build_e2e_execution_group(task_id, session, tc_rel) -> list[TaskCase]`
  - 前置：`E2E_GROUP_EXECUTION_ENABLED`；`tc_rel.device_type == physical`；本行目标 `mode != serial`（`_row_target_key` + `_mode_of` 复用现有逻辑）。
  - 候选：同 `task_id` + 同 `test_case_id` + `device_type='physical'` + `execution_status='pending'` + `task_case_not_removed`。
  - 设备指纹：`_resolve_device_fingerprint(device_id)` → `(lab_id, serial_number)`，走 `device_acl_repository.get_device`，结果按 device_id 缓存（复用 `_physical_lock_key_cache` 同思路，新增 `_device_fingerprint_cache`）。
  - **同组键 = `lab_id`**；要求 `lab_id` 非空，`lab_id` 为空（未绑定实验室）→ **不组**（无法确认物理隔离，保守串行）。
  - 组内必须 SN 互不相同（同 SN 只保留创建最早的一条，其余留给后续轮次）。
  - 仅当组内行数 >= 2 才返回组；否则返回 `[tc_rel]`。
  - 顺序：`created_at, id` 升序，`[:E2E_GROUP_MAX_DEVICES]`。

新增方法：

- `_claim_case_group(task_id, tc_rel_ids, session) -> int`
  - 单条 UPDATE：`id IN (...) AND task_id=... AND execution_status='pending'` → `queued` + `status=derive(queued, pending)`，`synchronize_session=False`。
  - 返回受影响行数；调用方要求等于组大小，否则 `rollback()` 并回退单行路径。

修改方法：

- `_dispatch_e2e_case`
  - 开头：`group = self._build_e2e_execution_group(...)`；`len(group) > 1` → `return self._dispatch_e2e_group(task_id, task, group, session)`。
  - 其余单行逻辑保持不变（零回归）。

新增方法：

- `_dispatch_e2e_group(task_id, task, group_rows, session)`
  1. 组内逐行 `_check_e2e_devices`；失败行按 `_handle_device_check_failed` 收敛并剔出组；剩余 < 2 → 退回 `_dispatch_e2e_case` 单行路径。
  2. `claimed = _claim_case_group(...)`；`claimed != len(group)` → `session.rollback()` 并退回单行路径。
  3. `session.commit()`。
  4. 按 `serial_number` 排序去重，逐台 `_acquire_physical_lock_by_sn(sn)`（新增，内部复用 `DistributedLock` 构造，TTL=`GRPC_E2E_SYNC_TIMEOUT_SECONDS+60`，`retry_timeout=TASK_PHYSICAL_LOCK_WAIT_SECONDS`）；任一失败 → 释放已获取锁 → 组内逐行 `_handle_physical_lock_busy` → return。
  5. `success = self._execute_e2e_case(task_id, group_rows[0].id, device_ids=[r.device_id for r in group_rows])`。
  6. 逐行 `session.refresh(row)`（`InvalidRequestError` 且行已删 → 跳过），失败时 `_handle_e2e_failure`；`refresh_task_counts_atomic` + `_emit_progress` 一次。
  7. `finally`：释放全部锁，失败仅告警。

文件：`task_service/core/execution_engine/mixins/grpc_helpers.py`

- `_execute_e2e_case_via_grpc(task_id, tc_rel_id, device_id=None, device_ids=None)`：新增 `device_ids` 参数并写入请求；`device_id` 逻辑保持。

文件：`task_service/core/execution_engine/mixins/case_execution.py`

- `_execute_e2e_case(task_id, tc_rel_id, device_id=None, device_ids=None)`：透传 `device_ids`。

### 5.4 e2e_test_service

文件：`e2e_test_service/interfaces/grpc/servicers.py`

- `StartE2ETask`：读取 `request.device_ids`，调用 `e2e_service.start_e2e_case(task_id, tc_rel_id, device_id=request.device_id or None, device_ids=list(request.device_ids))`。

文件：`e2e_test_service/application/services/e2e_service.py`

- `start_e2e_case(task_id, tc_rel_id, device_id=None, device_ids=None)` → `executor.execute_e2e_case(task_id, tc_rel_id, device_id=device_id, device_ids=device_ids)`。

文件：`e2e_test_service/application/services/e2e_executor/executor.py`

- `execute_e2e_case(..., device_ids=None)`、`_execute_e2e_with_rounds(..., device_ids=None)`。
- 新增 `_resolve_group_rows(task_id, test_case_id, device_ids) -> dict[int, int]`：经 `TaskDataAclRepositoryImpl.get_task_case_by_ids(task_id, [str(test_case_id)])` 按 `device_id` 匹配路由行；未匹配到的设备不参与结果写回（告警留痕）。
- 组路径：`_resolve_group_rows` 后逐行 `_update_tc_rel_status(row_id, RUNNING)`；单行路径保持原调用。
- 失败/停止/异常收口改为**逐行**：`_update_tc_rel_status` 循环组内行，`_close_failed_test_result` 循环组内每台结果。

文件：`e2e_test_service/application/services/e2e_device_manager.py`

- `get_device_info(task_id, case_config, device_id=None, device_ids=None)`：`device_ids` 非空时按列表过滤（保序）；`device_id` 与非空 `device_ids` 同时传入时以 `device_ids` 为准。

文件：`e2e_test_service/application/services/e2e_executor/preparation_mixin.py`

- `_prepare_rounds(..., device_ids=None) -> (device_info_list, result_ids: dict[int, int|None])`
  - 逐设备 `_save_result(device_id=info["device_id"], ...)`，`result_type` 口径不变，`ui_capture_degraded` 按 `device_name` 过滤后写入对应设备结果。
  - 返回映射；单设备时 `{device_id: result_id}`。

文件：`e2e_test_service/application/services/e2e_executor/rounds_loop_mixin.py`

- `_execute_single_round(...)`：采集后按 `raw_results.device_id`（缺失回落 `device_sn`）分组 `tagged_results`；对每台设备调用 `_build_and_submit_round_data(..., result_id=该设备结果, tc_rel_id=该设备行, primary=该设备主结果)`。
- 返回新增 `rounds_data_by_device: dict[str, list]`；`success` = 组内全部设备本轮成功。
- `_run_rounds_loop(...)`：累积 `rounds_data_by_device`；`all_round_results` 仍扁平累积（finalize 侧按设备过滤）。

文件：`e2e_test_service/application/services/e2e_executor/finalization_mixin.py`

- `_finalize_rounds(...)` 改为：
  - `device_results = _group_results_by_device(all_round_results)`；
  - 对每台设备：`_maybe_fetch_final_results(..., [该设备 info])` → `build_algorithm_result(该设备结果)` → `update_test_result(result_id=该设备结果)` → 显式整体评估 `_evaluate_result(result_id=该设备结果, ...)` → `update_algorithm_result_evaluation(该设备结果)` → `process_results(..., tc_rel_id=该设备行, precreated_result_id=该设备结果, publish_event=该设备是最后一台)`。
  - `result_data_path` 按 `device_sn` 分别 `write_result_data_file`。

文件：`e2e_test_service/application/services/e2e_aggregator.py`

- `process_results(..., publish_event=True)`：组内非最后一台传 `False`，避免 `CASE_EXECUTION_COMPLETED` 事件重复发布（事件体无 `tc_rel_id`，重复发布会让 task_service 消费侧重复唤醒/重复统计）。

### 5.5 evaluation_service

**不改代码。** 每路由行一条 TestResult + 逐行 `tc_rel_id` 回写已满足其 `_check_all_results_completed` / `_apply_final_status` 契约（见 §3.4）。

## 6. 状态口径（逐行）

| 阶段 | 每行写入方 | 值 |
| --- | --- | --- |
| 认领 | task_service | `execution=queued` |
| 组开始 | e2e（逐行） | `execution=running` |
| 组完成 | e2e `process_results`（逐行 `tc_rel_id`） | `execution=completed`，`evaluation=pending` |
| 组失败 | e2e（逐行） | `execution=failed`，`evaluation=failed` |
| 停止 | e2e（逐行） | `execution=stopped`，`error_message='任务被手动停止'` |
| 评估完成 | evaluation_service（逐行 `tc_rel_id`） | `evaluation=completed/failed`，复合 `status` 由 `derive_task_case_status` 推导 |

## 7. 失败 / 停止 / 暂停路径

- **单行设备检查失败**：该行单独收敛失败（`_handle_device_check_failed`），不进入组。
- **组内抢锁失败**：组内所有行按「物理设备被占用」收敛失败（`_handle_physical_lock_busy`），组不执行（宁可失败也不半组执行）。
- **组执行中某设备失败**：`execution_success` 按设备单独判定；失败设备结果行 `FAILED`，成功设备不受影响（每设备独立 TestResult / 独立评估）。
- **`TaskStopSignal`**：组内全部行 `STOPPED`，全部未收口结果行收口。
- **暂停**：沿用 `_handle_control` 轮询点（每轮开始 / 播放前后 / 后处理前后），组执行不改变暂停语义。

## 8. 非目标（本次不做）

- 不改 `_get_next_pending_case_target_gated` 的用例维度门控（已提交 `8864cc8d2`）。
- 不改 API 用例（`http_api` / `websocket_api`）派发链。
- 不改评估侧逐行收敛逻辑。
- 不改前端。

## 9. 阶段 B（已实现，2026-10-30）：同任务「不同实验室并行」

原状：主循环单线程同步派发，同任务内不同实验室的两个组仍串行。现改为异步派发：

| 项 | 落地 |
| --- | --- |
| 开关 | `TASK_E2E_ASYNC_DISPATCH`（默认 `True`，关闭即回退同步派发） |
| 并发上限 | `TASK_E2E_DISPATCH_WORKERS`（默认 4，单任务同时在途的 E2E 执行数） |
| 线程池 | 任务级 `ThreadPoolExecutor`（`e2e_dispatch_pools[task_id]`），按需创建、`_drain_e2e_dispatch` 回收 |
| 认领 | **主线程同步完成**（`pending → queued` 原子 UPDATE），保证下一轮不会重复领取同一行 |
| 执行 | 派发线程内：按 SN 排序抢锁（全成或全退）→ 一次 `StartE2ETask` → 逐行收敛；使用独立 `create_db_session()` |
| 上下文 | 派发线程绑定 `worker_instance_id` 与操作人 `user_id`（CUD 操作人列） |
| 收敛 | 执行异常在 `_run_e2e_execution` 内收口为行失败（不向线程外抛），主循环等待依赖既有 `_wait_for_cases_completion` / `CASE_EVENTS` |
| 容量门控 | 在途 ≥ 上限时主循环等空位（行保持 `PENDING`），不提前认领堆池队列（避免被 INT-120 挂起仲裁误判）；`stop_event` 可中断 |
| 收尾 | `_cleanup_task_resources` 先 `_drain_e2e_dispatch` 再释放 e2e 单飞槽位，防止下一任务与仍在执行的设备/音频并发 |

**并行边界（与 §1 语义一致）**

| 行特征 | 派发方式 | 结果 |
| --- | --- | --- |
| 物理 + 已绑定实验室 + 目标 `mode != serial` | 异步（线程池） | 不同 SN 并行；同 SN 由物理锁串行 |
| 物理 + 目标 `mode=serial` | 同步就地 | 逐台依次执行、各播一遍 |
| 物理 + 设备未绑定实验室 | 同步就地 | 无法确认实验室隔离，保守不并发（与 §5.3 同口径） |
| API 道（`http_api` / `websocket_api`） | 原链路 | 不受影响 |

**已知风险**：两个实验室若共用同一 `playback_device_id`，并发 `play_round` 会重叠出音；播放设备应按实验室独立配置（本次未新增播放设备级互斥锁）。

## 10. 验证步骤

1. 单测（在 `Intelligent-Audio-TEST` 根目录）：
   - `python -m pytest tests/unit/test_int604_serial_gating.py -q`（新增组选择用例）
   - `python -m pytest tests/unit/test_e2e_group_dispatch.py -q`（新增）
   - `python -m pytest tests/unit/test_e2e_group_results.py -q`（新增）
   - `python -m pytest tests/unit/test_e2e_async_dispatch.py -q`（新增：异步派发选择/提交/执行阶段/容量门控）
   - 回归：`python -m pytest tests/unit -q`（已知环境失败项：`test_int604_execution_mode_create.py` 的 total_cases 断言、`test_int308` 的 Redis/计时断言）
2. 构建与部署：`docker compose -f docker/docker-compose.yml up -d --build task_service e2e_test_service evaluation_service`
3. 环境闭环（详见 §13）：宿主 device_service 数据源改回 `localhost:5432` / `redis://localhost:6379` 并重启，`GET /api/v1/laboratories` 200。
4. 单设备回归（详见 §13.4）：1 用例 → 任务 `completed`，1 条 TestResult、1 行 completed。
5. 实测（同实验室 2 台不同 SN 设备、1 用例 2 轮、目标 mode=parallel）：
   - 日志中 `play_round` 每轮仅出现一次；
   - `initialize_devices` 两设备并发（时间戳重叠）；
   - `test_results` 表该用例 2 条（每设备一条）；
   - `task_case_relations` 两行均为 `completed`，任务 `completed`。
6. 串行回归（目标 mode=serial）：两设备各播一遍，两条结果，任务 `completed`。
7. 同 SN 回归（同机两条设备记录）：串行执行，无并发驱动冲突。

## 11. 风险与回滚

| 风险 | 缓解 |
| --- | --- |
| 组内某设备异常导致组整体超时 | 每设备独立 `future.result(timeout=E2E_DEVICE_OP_FUTURE_TIMEOUT_SECONDS)`（已存在） |
| 结果分组键（device_id / device_sn）不一致 | 统一 `_group_key(raw_result)`：`device_id` 优先，缺回落 `device_sn`；单测覆盖 |
| 事件重复发布 | `process_results(publish_event=...)`，仅最后一台发布 |
| 组执行语义意外影响单设备任务 | `E2E_GROUP_EXECUTION_ENABLED` 一键回退 + 组大小 1 走原路径 |
| 未绑定实验室的设备被误并行 | `lab_id` 为空不组（§5.3） |

## 12. 待你确认的决策点

1. **阶段 B（同任务跨实验室并行）是否纳入本次？** 建议不纳入（先合阶段 A）。
2. **未绑定实验室的设备**是否按「不组」处理？建议不组（保守）。
3. **组内抢锁失败**是否整组失败（而不是部分执行）？建议整组失败，原因：一次播放若缺一台设备，该设备数据缺失且无法补播。

## 13. 环境闭环增补（2026-10-30，T5 前置）

### 13.1 已核实事实

| 项 | 事实 |
| --- | --- |
| 业务库 | compose `postgres`，宿主 `localhost:5432`，库 `intelligent_audio_test`；`GET :15000/health` 返回 `database: intelligent_audio_test` |
| 实验室 | `laboratories` id=38 `code=LAB-A` `name=测试实验室A` `status=active` |
| 设备关联 | `devices` 148 行，`lab_id=38` 148 行（100%） |
| 网关→设备 | `DEVICE_SERVICE_HOST=host.docker.internal`、`DEVICE_SERVICE_GRPC_PORT=50053` → 宿主 device_service（PID 31856） |
| 故障根因 | 启动器 `%TEMP%\start_device_service_iat.py` L19-22 覆写 `DATABASE_URL=localhost:15435`、`REDIS_URL=localhost:16379`（已停用的 sim-prod 口径，容器不存在）→ `ListLaboratories` psycopg2 10061 → 网关 400 |
| 认证 | `AUTH_MODE=dev`：无 Bearer → `dev_user`（permissions `['*']`），可直接调网关 |

### 13.2 修复点（仅环境，不改仓库源码）

1. `%TEMP%\start_device_service_iat.py`：
   - L19-21 → `postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test`
   - L22 → `redis://localhost:6379`
2. 停止宿主 device_service（PID 31856）后以同一解释器重启，确认 50053 监听恢复。
3. 验收：`GET http://localhost:15000/api/v1/laboratories` → `success:true` 且 data 含 `LAB-A`；`GET /api/v1/devices/{id}` 的 `lab_name` = `测试实验室A`。

### 13.3 认证与令牌

临时 `access_tokens` id=49（明文 `trae-verify-20261030`）仅作备用，验证结束即删除；不用于写业务数据。

### 13.4 实测口径（受设备约束）

- **单设备回归（必做）**：选 `lab_id=38` 且 online 的设备（227 的 online 疑似陈旧，先用设备连通性校验；否则用 SN `6YF0126211000225` 的设备）→ 1 用例任务 `running→completed`，1 条 TestResult、1 行 completed。
- **组执行链路（mock 优先）**：同 lab 新增 1 台虚拟设备（SN 唯一、`driver=mock`、online、`lab_id=38`）；1 用例 2 轮、目标 `mode=parallel`；断言 `StartE2ETask` 请求 `device_ids` 含 2 个 id、`play_round` 每轮 1 次、`test_results` 2 条、2 行 completed、任务 completed。
- **真机四项目标**：保留于 `tasks.md` T5.3，阻塞于第二台不同 SN 真机（当前 `hdc` 仅 `6YF0126211000225`，`adb` 空）。

### 13.5 清理

删除 `access_tokens` id=49；删除 T5.2 的 mock 设备与验证任务；`mock_mode` 恢复 False。

## 14. 播放设备按实验室换绑：逻辑音箱组（2026-10-30）

### 14.1 问题

用例里配置的播放设备只属于「编写用例的那个实验室」。跨实验室执行时会驱动别处的音箱
（不同实验室并行时互相串音），且被测设备与播放设备必须同实验室。

### 14.2 模型：逻辑音箱组（不是两两映射）

一个**逻辑音箱** = 一个物理位置（如「设备正面 0.5m」），组内每个实验室各挂一台实体音箱。
N 个实验室共享同一逻辑音箱，无需 N×(N-1) 条两两映射。

| 表 | 关键列 | 约束 |
| --- | --- | --- |
| `playback_speaker_groups` | `id` / `name`(唯一) / `description` / 审计列 | 组名唯一 |
| `playback_speaker_group_items` | `group_id` / `lab_id` / `playback_device_id` | `(group_id, lab_id)` 唯一；`playback_device_id` 全局唯一（一台实体音箱只能属于一个逻辑位置） |

### 14.3 用例关联方式（用户已确认：只能关联逻辑音箱）

用例配置从此**只允许**关联逻辑音箱（前端下拉不再提供实体设备），执行时按执行实验室换绑：

| 用例配置 | 语义 | 执行时 |
| --- | --- | --- |
| `audios[].playback_speaker_group_id` | 音频主播放目标 | 组 + 执行实验室 → 组内该实验室实体设备，回填 `playback_device_id/name` |
| `background_noise.playback_speaker_group_ids[]` | 背景噪声（可多选） | 逐个解析成该实验室设备，写入 `device_ids` 供播放引擎使用 |
| `interferers[].playback_speaker_group_id` | 干扰人 | 解析成实体设备（通用换绑覆盖） |
| `algorithm_params.voiceprint.playback_speaker_group_id` | 声纹注册 | 声纹在独立列，由 `_register_voiceprint` 单独按实验室解析 |
| `playback_device_id`（历史） | 老用例兼容 | 源音箱 → 所属组 → 目标实验室设备；**迁移脚本会改写为组引用** |

解析顺序（执行前、音频预下载之前，保证按新设备采样率重采样）：

1. 已属于执行实验室 → 保持原配置；
2. 逻辑音箱组内该实验室对应设备；
3. 同名（位置同名对应）；
4. 该实验室第一台在线设备；
5. 该实验室任一设备；
6. 以上皆不可用 → `LabPlaybackBindingError`，**用例直接失败**（不静默换错音箱）。

逻辑音箱在该实验室没有对应设备 → 同样直接失败。

### 14.3.1 历史用例迁移

`scripts/migrate_cases_to_speaker_groups.py`（幂等，支持 `--dry-run`）：

1. 按播放设备名称补建逻辑音箱（同名 = 同一位置，跨实验室归入同一组）；
2. 改写 `test_cases.config` 与 `algorithm_params`：
   `playback_device_id` → `playback_speaker_group_id`，
   `background_noise.device_ids` → `playback_speaker_group_ids`，
   `interferers[].device.id` → `playback_speaker_group_id`；
3. 未匹配到逻辑音箱的设备引用保持原样并列入报告（执行侧老路径兜底）。

### 14.3.2 试听必须选实验室

逻辑音箱本身没有物理通道，试听（浏览器播放除外）必须先选实验室：

- 前端试听弹窗新增「实验室 *」下拉；所选逻辑音箱按该实验室解析成实体设备后再放音；
- 用例级试听请求带 `lab_id`，网关 `POST /testcases/{id}/preview` 按实验室解析
  `playback_speaker_group_id(s)`，未选实验室或组内无该实验室设备直接返回中文错误。

### 14.4 互斥

播放设备级分布式锁 `lock:playback:device:{playback_device_id}`（`audio_service`
`play_round` 内获取/释放，TTL `PLAYBACK_DEVICE_LOCK_TTL_SECONDS=1800`，等待
`PLAYBACK_DEVICE_LOCK_WAIT_SECONDS=900`），防止跨任务并发驱动同一台音箱。

### 14.5 改动面

| 层 | 文件 |
| --- | --- |
| proto | `shared/proto/device_service.proto`：组 CRUD / `SetItem` / `ResolvePlaybackSpeakerDevice` / `ResolvePlaybackSpeakerGroupDevice` |
| device_service | `playback_speaker_models.py`、`entities/playback_speaker_group.py`、`_playback_repository_impl.py`、`playback_speaker_command_service.py`、`playback_speaker_query_service.py`、`playback_config_servicers.py` |
| e2e_test_service | `lab_playback_binding.py`（换绑）、`playback_acl_repository(.py/_impl.py)`、`preparation_mixin.py` 接线 |
| api_gateway | `schemas/playback.py`、`routes/playback_bp.py`、`playback_{query,command}_service.py`、设备 ACL + gRPC 代理 |
| shared | `common_enums.py`（`RedisKeyPrefix.PLAYBACK_DEVICE_LOCK`、`PlaybackDeviceStatus`）、`config.py`、`testcase_helpers.py`（组关联也算 E2E 形态标记） |
| audio_service | `playback_orchestrator.py`（设备锁包装 `play_round`） |

### 14.6 前端（已在 `D:\00_code\V9.7.31-WIRING-REACT` 实现）

前端源码不在本仓库（仓库内只有预构建容器），实际前端工程位于
`D:\00_code\V9.7.31-WIRING-REACT\Intelligent-Audio-TEST\frontend-react`，本次已落地：

| 能力 | 落位 |
| --- | --- |
| 逻辑音箱管理弹窗（列表 / 新建 / 编辑 / 删除 / 各实验室对应设备） | `features/devices/components/modals/playback-speaker-group-dialog.tsx`，入口「设备管理 → 播放设备页签 → 更多操作 → 逻辑音箱」 |
| 领域模型 / DTO / 适配器 | `domain/models/playbackSpeakerGroup.ts`、`infrastructure/dto/playback-speaker-group.dto.ts`、`infrastructure/adapters/playbackSpeakerGroupAdapter.ts` |
| 接口与 hooks | `infrastructure/api/devicesApi.ts`（6 个函数）、`application/devices/use-devices.ts`（`usePlaybackSpeakerGroups` / `usePlaybackSpeakerGroupMutations`） |
| 用例关联逻辑音箱 | 轮次音频卡「播放设备」下拉：逻辑音箱（`group:{id}`）与实体设备二选一；选组时写 `playback_speaker_group_id`、清空实体设备（`audio-list-step.tsx` + `domain/lib/testcase-round-config.ts`） |
| 批量工具 | 「标签设备 / 批量设备 / 设备交叉」批量设实体设备时自动清除逻辑音箱关联（二选一，组优先） |

接口：

- `GET/POST /api/v1/playback-devices/speaker-groups`
- `PUT/DELETE /api/v1/playback-devices/speaker-groups/{group_id}`
- `PUT /api/v1/playback-devices/speaker-groups/{group_id}/items`
- `DELETE /api/v1/playback-devices/speaker-groups/{group_id}/items/{lab_id}`

