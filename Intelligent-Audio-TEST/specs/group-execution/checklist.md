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

## 环境闭环与实测（2026-10-30）

- [x] 业务库确认：compose `postgres`，宿主 `localhost:5432/intelligent_audio_test`；实验室 `LAB-A`（id=38）与 `devices` 148/148 行 `lab_id=38`
- [x] 宿主 device_service 数据源修正（15435/16379 → 5432/6379）后，`GET /api/v1/laboratories` 200 且 `LAB-A` 可见、设备 `lab_name` 正确
- [x] 宿主 audio_service 修正到业务库后，`play_round` 正常出音并产出 wav
- [x] 组派发实测：同 lab 两台不同 SN（dev 9 + 临时 mock dev 12）→ 日志 `组执行派发 ... 设备 ['9','12']`，`StartE2ETask.device_ids=[9,12]`，一次调用驱动全组
- [x] 每设备一条 TestResult：同任务预创建 2 条（dev9 / dev12），两路由行逐行 `running → 收口`
- [ ] `play_round` 每轮仅 1 次且两行 `completed`：mock Android 采集空结果导致轮次失败；真机侧缺第二台不同 SN
- [ ] `mode=serial`：两设备各播一遍
- [ ] 同 SN：串行执行，无并发驱动冲突
- [ ] 任务整体 `completed`：外部算法端点 `100.70.20.135:8888` 不可达（`/api/create_task_upload` 拒绝连接）→ 评估必失败
- 原因：宿主仅 1 台不同 SN 真机（SN `6YF0126211000225`），`adb` 无设备；mock 驱动可绕过步骤但不产出采集结果；外部算法端点需真实环境可达

## 不同实验室并行（阶段 B，2026-10-30）

- [x] `TASK_E2E_ASYNC_DISPATCH`（默认 True）/ `TASK_E2E_DISPATCH_WORKERS`（默认 4）接入 `BaseConfig`
- [x] 认领在主线程（`pending → queued` 原子 UPDATE），执行阶段提交任务级线程池 → 主循环不再被 gRPC 阻塞
- [x] 并行边界：物理 + 已绑定实验室 + 目标非 serial 才异步；serial / 未绑定实验室保持同步就地（语义与阶段 A 一致）
- [x] 执行阶段：按 SN 排序抢锁全成或全退；一次 `StartE2ETask`；逐行收敛；执行异常收口为行失败且释放锁
- [x] 容量门控：在途 ≥ 上限时行保持 `PENDING` 等空位（不被挂起仲裁误判），`stop_event` 可中断
- [x] 收尾：`_cleanup_task_resources` 先 `_drain_e2e_dispatch` 再释放 e2e 单飞槽位，线程池回收
- [x] 单测 `test_e2e_async_dispatch.py` 15 项全绿；引擎相关回归 146 项通过
- [x] 部署与实测：任务 737（LAB-A + LAB-B 各 1 台 mock 设备）两次 `StartE2ETask` 间隔 68ms（改前 23s），e2e 两次 `StartPlayback` 重叠 → 跨实验室并行成立
- [ ] 真机/多实验室实测：需 2 个实验室各有在线真机（当前仅 LAB-A 的 1 台鸿蒙机）
- 风险备忘：跨实验室若共用同一 `playback_device_id`，并发 `play_round` 会重叠出音，播放设备应每实验室独立配置

## 播放设备按实验室换绑 / 逻辑音箱组（2026-10-30）

- [x] 逻辑音箱组模型：`playback_speaker_groups` + `playback_speaker_group_items`（`(group_id, lab_id)` 唯一、`playback_device_id` 全局唯一）
- [x] 用例可**直接关联逻辑音箱**（`playback_speaker_group_id`）；老用例 `playback_device_id` 兼容，按所属组换绑
- [x] 换绑顺序：组直连/已属本实验室 → 组换绑 → 同名 → 在线 → 任一 → 失败
- [x] 组在该实验室无设备 / 设备不属该实验室 / 实验室无任何播放设备 → 用例直接失败（不静默换错音箱）
- [x] `has_playback_audio` 把 `playback_speaker_group_id` 计为 E2E 形态标记（组关联用例不被误判 API 口径）
- [x] 播放设备分布式锁 `lock:playback:device:{id}`（TTL 1800s / 等待 900s）
- [x] 单测 30 项全绿（换绑 15 + 组服务 10 + 设备锁 5）
- [x] gRPC 实测：组 CRUD / set item / resolve 均 `success=true`
- [x] `e2e_test_service` / `api_gateway` / `task_service` 镜像重建并 healthy；宿主 device_service 重启加载新 RPC
- [x] 网关 HTTP 实测 `GET /api/v1/playback-devices/speaker-groups` 返回组 1（lab 38 → device 5）
- [x] 两实验室换绑实测（临时 LAB-B id=40）：组直连 `group:1->83`、老用例 `5->83`，验证后临时数据已删除
- [ ] 播放互斥锁实跑验证（单测已覆盖）
- [x] 前端（`D:\00_code\V9.7.31-WIRING-REACT`）：逻辑音箱管理弹窗 + 用例「逻辑音箱/实体设备」二选一，构建通过并部署 :15173
- [x] 前端测试：弹窗 5 项 + 轮次序列化 17 项全绿
- [x] 用例只关联逻辑音箱：音频/背景噪声（轮次+全局）/声纹/干扰人/批量工具全部只列逻辑音箱
- [x] e2e 换绑：背景噪声 `playback_speaker_group_ids[]` → 该实验室 `device_ids`；声纹按实验室解析
- [x] 迁移脚本执行：12 个逻辑音箱（12 条实验室设备），710 条用例 / 1436 处设备引用 / 3 处背景噪声改写；重跑幂等
- [x] 试听必须选实验室：前端弹窗「实验室 *」+ 网关 `lab_id` 解析（未选/未配置 → 400）
- [ ] 上传选项 / 批量设置弹窗仍按实体设备提交（待批量接口支持组）
