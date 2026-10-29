# tasks：E2E 用例组执行（同实验室多设备并行、音频每轮一次）

对应规格：[spec.md](./spec.md)

> 执行顺序即依赖顺序。T1 之后才能编译/联调；T2、T3、T4 依赖 T1 的 proto 字段。

## T1 proto + 配置（阻塞项）

- [x] `shared/proto/e2e_test_service.proto`：`StartE2ETaskRequest` 增 `repeated int32 device_ids = 5;`
- [x] 重新生成 `shared/proto/e2e_test_service_pb2.py`、`e2e_test_service_pb2_grpc.py`
- [x] `shared/infrastructure/config.py`：`E2E_GROUP_EXECUTION_ENABLED=True`、`E2E_GROUP_MAX_DEVICES=8`
- 验收：`python -c "from shared.proto import e2e_test_service_pb2 as p; print(p.StartE2ETaskRequest(device_ids=[1,2]))"` 输出含 `device_ids: 1, device_ids: 2`

## T2 task_service 调度层

- [x] `task_dispatch.py` 新增 `_device_fingerprint(device_id) -> (lab_id, serial_number)`（按 device_id 缓存）
- [x] `task_dispatch.py` 新增 `_build_e2e_execution_group(task_id, session, tc_rel)`
- [x] `task_dispatch.py` 新增 `_claim_case_group(task_id, tc_rel_ids, session)`
- [x] `task_dispatch.py` 新增 `_acquire_physical_lock_by_sn(sn)`
- [x] `task_dispatch.py` 新增 `_dispatch_e2e_group(task_id, task, group_rows, session)`
- [x] `task_dispatch.py` 修改 `_dispatch_e2e_case`：组大小 > 1 转组派发，其余保持原路径
- [x] `grpc_helpers.py` `_execute_e2e_case_via_grpc` 增 `device_ids`
- [x] `case_execution.py` `_execute_e2e_case` 增 `device_ids` 透传
- [x] `task_service` 调度层方法齐备（`test_e2e_group_dispatch.py` 4 项全绿）；`test_int604_serial_gating.py` 22 项全绿（含组选择 5 项）

## T3 e2e_test_service 组执行

- [x] `servicers.py` `StartE2ETask` 读取 `device_ids`
- [x] `e2e_service.py` `start_e2e_case` 透传 `device_ids`
- [x] `executor.py`：`device_ids` 透传；新增 `_resolve_group_rows`；逐行 RUNNING；失败/停止/异常逐行收敛
- [x] `e2e_device_manager.py` `get_device_info` 支持 `device_ids`
- [x] `preparation_mixin.py` `_prepare_rounds` 返回 `result_ids: dict[device_id, result_id]`（每设备一条 TestResult）
- [x] `rounds_loop_mixin.py` 按设备分组结果、按设备更新结果与单轮评估，返回 `rounds_data_by_device`
- [x] `finalization_mixin.py` 逐设备收口（`_finalize_rounds` 内按设备循环：聚合/整体评估/回写/结果文件）
- [x] `e2e_aggregator.py` `process_results(publish_event=True)`
- [x] `test_e2e_group_results.py` 7 项全绿（每设备一条结果、事件只发一次）

## T4 单测

- [x] `tests/unit/test_int604_serial_gating.py` 新增 `TestGroupExecutionSelection`：同 lab 不同 SN 合组 / 同 SN 不合组 / serial 目标不合组 / lab 为空不合组 / 开关关闭不合组
- [x] 新增 `tests/unit/test_e2e_group_dispatch.py`：SN 锁全成或全退、抢锁失败整组失败、认领冲突退回单行、行删除跳过收敛
- [x] 新增 `tests/unit/test_e2e_group_results.py`：`_prepare_rounds` 每设备一条结果、逐设备收口、事件只发一次
- [x] 既存 mock 契约同步：`test_int158` / `test_int169` / `test_int296` / `test_int308` / `test_int64_e2e_finalization_gate`（result_ids dict、5→4 tuple、逐设备错误文案）
- 验收：新增用例全绿（22 + 4 + 7 通过；int308 3 项 Redis 缺失环境失败与本次改动无关）

## T5 部署与实测

- [x] 构建部署 `task_service` / `e2e_test_service`（镜像重建、容器 healthy、启动日志无异常）
- [ ] 新建任务：同 lab 2 台不同 SN、1 用例 2 轮、mode=parallel
- [ ] 校验：`play_round` 每轮一次；两设备初始化并发；`test_results` 2 条；两行 `completed`；任务 `completed`
- [ ] 串行回归：mode=serial 时两设备各播一遍
- [ ] 同 SN 回归：无并发驱动冲突
- 说明：当前本地库设备 `lab_id` 全为空且全部 offline，无在线真机，无法生成真正的组执行任务；上述 4 项需在真实实验室环境（设备已绑定 lab、在线）执行。

## T6（可选，待确认）阶段 B：异步派发

- [ ] `TASK_E2E_ASYNC_DISPATCH` / `TASK_E2E_DISPATCH_WORKERS` 配置
- [ ] `_dispatch_e2e_case/_dispatch_e2e_group` 提交线程池；线程内独立 session、抢锁、收敛
- [ ] 同 SN 排队改为非阻塞 + QUEUED 重试
- 仅在确认纳入后执行
