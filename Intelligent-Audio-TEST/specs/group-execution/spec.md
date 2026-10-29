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

## 9. 阶段 B（需你确认是否纳入本次）：同任务「不同实验室并行」

现状：主循环单线程同步派发，同任务内 **不同实验室的两个组仍然串行**。要满足「不同实验室间并行」必须改异步派发：

- 新增开关 `TASK_E2E_ASYNC_DISPATCH`（默认 `False`）与 `TASK_E2E_DISPATCH_WORKERS`（默认 4）。
- `_dispatch_e2e_case/_dispatch_e2e_group` 改为把「抢锁 + gRPC + 逐行收敛」提交到 task_service 自有线程池，主循环提交即返回。
- 线程内使用独立 DB session（`create_db_session()`），`stop_event` 由线程池任务自行检查。
- 主循环收敛依赖已有 `_wait_active_cases_with_backoff` + `CASE_EVENTS` 事件（API 链已在用）。
- 风险：停止/暂停传播、任务收敛、同 SN 排队（当前是阻塞等锁，异步后需改为非阻塞 + QUEUED 重试）。改动面显著大于阶段 A。

建议：**阶段 A 先合入并实测**，阶段 B 单独评审后再做。

## 10. 验证步骤

1. 单测（在 `Intelligent-Audio-TEST` 根目录）：
   - `python -m pytest tests/unit/test_int604_serial_gating.py -q`（新增组选择用例）
   - `python -m pytest tests/unit/test_e2e_group_dispatch.py -q`（新增）
   - `python -m pytest tests/unit/test_e2e_group_results.py -q`（新增）
   - 回归：`python -m pytest tests/unit -q`（已知环境失败项：`test_int604_execution_mode_create.py` 的 total_cases 断言、`test_int308` 的 Redis/计时断言）
2. 构建与部署：`docker compose -f docker/docker-compose.yml up -d --build task_service e2e_test_service evaluation_service`
3. 实测（同实验室 2 台不同 SN 设备、1 用例 2 轮、目标 mode=parallel）：
   - 日志中 `play_round` 每轮仅出现一次；
   - `initialize_devices` 两设备并发（时间戳重叠）；
   - `test_results` 表该用例 2 条（每设备一条）；
   - `task_case_relations` 两行均为 `completed`，任务 `completed`。
4. 串行回归（目标 mode=serial）：两设备各播一遍，两条结果，任务 `completed`。
5. 同 SN 回归（同机两条设备记录）：串行执行，无并发驱动冲突。

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
