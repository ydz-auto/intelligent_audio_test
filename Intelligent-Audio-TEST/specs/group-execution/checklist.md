# Checklist：E2E 用例「组执行」

- 规格：`specs/group-execution/spec.md`
- 任务：`specs/group-execution/tasks.md`

## 协议与配置

- [x] `StartE2ETaskRequest` 含 `repeated int32 device_ids = 5`，pb2 已重新生成（构造输出 `device_ids: 1, device_ids: 2`）
- [x] `E2E_GROUP_EXECUTION_ENABLED` 默认 `True`、`E2E_GROUP_MAX_DEVICES` 默认 `8`，均接入调度层

## task_service 调度层

- [x] 组选择仅在同任务 + 同用例 + `physical` + `pending` + 未删除、目标 `mode != serial`、`lab_id` 非空、SN 互异时成立；组内 < 2 返回单行
- [x] 组内按 `created_at, id` 升序并截断 `E2E_GROUP_MAX_DEVICES`
- [x] 组认领为单条 UPDATE（`pending → queued` + `derive_task_case_status`），占用数不等于组大小即回滚并回退单行
- [x] 组内按 SN 排序逐台抢锁，全成或全退；抢锁失败整组按「物理设备被占用」收敛且不执行
- [x] 组执行一次 `StartE2ETask` 携带 `device_ids`；逐行 `refresh` 收敛，行被删除跳过；`finally` 释放全部锁
- [x] 单设备路径保持原行为（组大小 1 走原路径，零回归）

## e2e_test_service

- [x] `servicers` / `e2e_service` / `executor` 透传 `device_ids`；`device_ids` 优先于 `device_id`
- [x] `get_device_info` 按 `device_ids` 保序过滤，缺失设备返回失败
- [x] `_prepare_rounds` 每设备预创建一条 TestResult，返回 `device_id → result_id`；UI 降级留痕按 `device_name` 过滤
- [x] 每轮 `play_round` 仅调用一次，后处理 / 采集按 `device_info_list` 覆盖组内全部设备
- [x] 采集结果按 `device_id` 分组，缺 `device_id` 按 `device_sn` 映射；每设备更新自己的 TestResult 并提交单轮评估
- [x] `_finalize_rounds` 逐设备聚合、整体评估、结果文件、逐行回写；某设备无结果时该设备判失败
- [x] 用例完成事件仅组内最后一台设备发布一次（`publish_event`）
- [x] 失败 / 停止 / 异常路径逐行收敛状态 + 逐设备收口预创建结果行

## 评估契约与回归

- [x] 每路由行一条 TestResult，满足 `evaluation_service` 的 `results_by_device[row.device_id]` 契约（评估侧未改）
- [x] 既存单测契约同步并全绿（96 passed：组选择 5 + 组派发 4 + 组结果 8 + int158/int169/int64/int296/int604）
- [x] 回滚开关可用（`E2E_GROUP_EXECUTION_ENABLED=False` 即回退逐行派发）

## 部署

- [x] `task_service` / `e2e_test_service` 镜像重建并 healthy，启动日志无异常

## 待真机环境验证（非代码缺陷）

- [ ] 同 lab 2 台不同 SN、1 用例 2 轮、`mode=parallel`：`play_round` 每轮一次、两设备初始化并发、`test_results` 2 条、两行 `completed`、任务 `completed`
- [ ] `mode=serial`：两设备各播一遍
- [ ] 同 SN：串行执行，无并发驱动冲突
- 原因：本地库 `devices.lab_id` 全为空且全部 `offline`，无在线真机，无法构造真正的组执行任务
