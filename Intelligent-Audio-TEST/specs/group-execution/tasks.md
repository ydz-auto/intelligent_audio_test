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

## T5 环境闭环与实测

### T5.0 环境闭环（前置）

- [x] 构建部署 `task_service` / `e2e_test_service`（镜像重建、容器 healthy、启动日志无异常）
- [x] 新增实验室并全量关联：`laboratories` id=38 `LAB-A`；`devices` 148/148 行 `lab_id=38`（直连业务库写入）
- [x] 修正宿主 device_service 数据源：`%TEMP%\start_device_service_iat.py` L19-22 由 `localhost:15435` / `localhost:16379` 改为 `localhost:5432`（库 `intelligent_audio_test`）/ `redis://localhost:6379`，重启宿主进程
- [x] 验收：`GET http://localhost:15000/api/v1/laboratories` 返回 `success: true` 且含 `LAB-A`（device_count=5）；设备详情 `lab_name` = 测试实验室A
- 说明：网关 `DEVICE_SERVICE_HOST=host.docker.internal:50053` 指向宿主 device_service；旧启动器把库/Redis 指向已停用的 sim-prod（15435/16379）→ `ListLaboratories` psycopg2 10061 → 网关 400
- [x] 追加修复：宿主 audio_service 同样连到 `intelligent_audio_test_test`（无本次用例音频）→ 以 `DATABASE_URL=.../intelligent_audio_test` + `PYTHONPATH` 重启，`play_round` 恢复出音

### T5.1 单设备回归（必做）

- [x] 选 `lab_id=38` 且 online 的设备（健康检查后 9/10/11 online，SN `6YF0126211000225`）
- [x] 执行链路跑通：任务 734 结果 8509（dev 9）`execution=completed`，路由行 `execution=completed`，`play_round` 正常出音并产出 wav
- [ ] 任务整体 `completed`：被外部算法端点阻断（`100.70.20.135:8888` 不可达，`/api/create_task_upload` 拒绝连接）→ `evaluation=failed`，任务 failed；非本服务缺陷

### T5.2 组执行链路（mock 优先，验证阶段 A）

- [x] 同 lab 新增虚拟设备（SN 唯一、`Android` mock、online、`lab_id=38`）：临时设备 12 改 SN `MOCK-ANDROID-001` + `keywords=android.base.v1`；设备 230 `MOCK-ANDROID-002`
- [x] 建 1 用例 2 轮（实为 1 轮用例）、目标 `mode=parallel` 任务 735 并启动
- [x] 校验组派发：`[Engine] 组执行派发 ... 设备 ['9','12']`；`StartE2ETask request device_ids=[9,12]`（一次调用驱动全组）
- [x] 校验每设备一条结果与逐行收敛：预创建 `test_results` 2 条（8510 dev9 / 8511 dev12），两路由行各自 `running → failed` 收口
- [ ] 校验 `play_round` 每轮仅 1 次 + 两行 `completed`：mock Android 采集 `raw_results={}` 导致轮次判失败；真机侧因仅 1 台不同 SN 无法同组，故未能同时满足（与 T5.3 同源阻塞）

### T5.3 真机四项目标（阻塞于第二台不同 SN 真机）

- [ ] 同 lab 2 台不同 SN、1 用例 2 轮、parallel：`play_round` 每轮一次、初始化并发、2 条结果、2 行 completed
- [ ] 串行回归：mode=serial 时两设备各播一遍
- [ ] 同 SN 回归：无并发驱动冲突
- 说明：当前宿主仅 1 台鸿蒙真机（SN `6YF0126211000225`），`adb devices` 为空 → 需接入第二台不同 SN 设备并绑定 LAB-A

### T5.4 清理

- [x] 删除临时令牌 `access_tokens` id=49（明文 `trae-verify-20261030`）
- [x] 删除 T5.2 的 mock 设备（230 已逻辑删除；12 恢复 SN 空 / keywords NULL / offline）与验证任务（735/736 已删除）
- [x] `mock_mode` 恢复 False；用例播放设备恢复为 `5` / `设备正面（0.5m+0°）`

## T6 阶段 B：不同实验室并行（异步派发）

- [x] `TASK_E2E_ASYNC_DISPATCH`（默认 True）/ `TASK_E2E_DISPATCH_WORKERS`（默认 4）配置接入
- [x] 新增 `mixins/e2e_async_dispatch.py`（`E2EAsyncDispatchMixin`）：任务级线程池、在途计数、容量门控、执行阶段、逐行收敛、`_drain_e2e_dispatch`
- [x] 认领留在主线程，`_dispatch_e2e_case` / `_dispatch_e2e_group` 认领后提交线程池，主循环立即返回
- [x] 并行边界：仅「物理 + 已绑定实验室 + 目标非 serial」异步；serial / 未绑定实验室保持同步就地执行
- [x] `task_lifecycle` 主循环加容量门控；`task_finalize._cleanup_task_resources` 先 drain 再释放单飞槽位
- [x] 单测 `tests/unit/test_e2e_async_dispatch.py` 15 项全绿；`test_e2e_group_dispatch` / `test_int80_physical_lock` / `test_int604_serial_gating` / `test_int308` 等回归通过
- [x] 镜像重建部署（`intelligent-audio-test-task_service`，healthy；容器内 `TASK_E2E_ASYNC_DISPATCH=True`、workers=4）
- [x] 跨实验室并行实测（mock 双机双实验室）：任务 737（LAB-A dev12 + LAB-B dev231）→ 两次 `StartE2ETask` 间隔 68ms（改前同场景 23s，即串行），e2e 侧两次 `StartPlayback`/`CreateDriver` 时间窗重叠，`test_results` 2 条逐设备收敛
- [ ] 真机四实验室并行实测：需 2 个实验室各有在线真机（当前仅 LAB-A 的 1 台鸿蒙机）

## T7 播放设备按实验室换绑：逻辑音箱组

- [x] 建表 `playback_speaker_groups` / `playback_speaker_group_items`（`(group_id, lab_id)` 唯一、`playback_device_id` 全局唯一）；删除两两映射表 `playback_device_mappings`
- [x] device_service：聚合实体 + 仓储（含 `resolve_playback_speaker_device` 两跳、`resolve_playback_speaker_group_device`）+ 命令/查询服务（组名唯一 409、设备须属该实验室 400、设备被占用 409）+ 8 个 gRPC
- [x] proto：`PlaybackConfigService` 增组 CRUD / `SetItem` / `ResolvePlaybackSpeakerDevice` / `ResolvePlaybackSpeakerGroupDevice`，pb2 重新生成
- [x] `shared`：`RedisKeyPrefix.PLAYBACK_DEVICE_LOCK`、`PlaybackDeviceStatus`、`PLAYBACK_LAB_BINDING_ENABLED` / `PLAYBACK_DEVICE_LOCK_TTL_SECONDS` / `PLAYBACK_DEVICE_LOCK_WAIT_SECONDS`
- [x] e2e_test_service：`lab_playback_binding`（组直连 → 已属本实验室 → 组换绑 → 同名 → 在线 → 任一 → 失败）；`playback_acl_repository` 增 `resolve_speaker_device` / `resolve_speaker_group_device`；`preparation_mixin` 在音频预下载前接线
- [x] `shared/utils/testcase_helpers.py`：`playback_speaker_group_id` 也算 E2E 形态标记（`has_playback_audio`）
- [x] audio_service：`play_round` 按 `playback_device_id` 加分布式锁（wrap → `_acquire_playback_device_locks` → `_play_round_body`）
- [x] api_gateway：`speaker-groups` 路由 + schema + 查询/命令服务 + 设备 ACL/gRPC 代理
- [x] 单测：`test_lab_playback_binding.py` 15 项（含组直连 5 项：组解析 / 组优先于老设备 / 组未配实验室失败 / 组设备不属该实验室失败 / 同组只解析一次）、`test_playback_speaker_group_service.py` 10 项、`test_playback_device_lock.py` 5 项，共 30 项全绿
- [x] 逻辑音箱组 gRPC 实测：create / set item / resolve 均 `success=true`，`resolve` 返回 `{"target_device_id": 5}`
- [x] 镜像重建部署 `e2e_test_service` / `api_gateway` / `task_service`（`--project-name intelligent-audio-test`，三容器 healthy）
- [x] 网关 HTTP 实测：`GET /api/v1/playback-devices/speaker-groups` 返回组 1（lab 38 → device 5）
- [x] 两实验室实测（临时 LAB-B id=40 + 播放设备 id=83，验证后已删除）：组直连 `group:1->83`、老用例 `5->83`；LAB-A 解析 `group:1->5`
- [x] 失败语义实测：目标实验室无播放设备 → `实验室 39 未配置可用播放设备`；组内无该实验室设备 → `逻辑音箱 1 未配置实验室 38 的播放设备`
- [x] 宿主 device_service 重启以加载 `ResolvePlaybackSpeakerGroupDevice`（旧进程 UNIMPLEMENTED）
- [ ] 播放互斥锁实跑验证（当前由单测覆盖：同设备第二个任务需等待）
- [x] 前端（`D:\00_code\V9.7.31-WIRING-REACT`）：逻辑音箱管理弹窗 + 用例音频「逻辑音箱/实体设备」二选一；`pnpm build` 通过、`deploy_demo_frontends.ps1 -SkipVue` 已部署 :15173
- [x] 前端单测：`playback-speaker-group-dialog.test.tsx` 5 项 + `testcase-round-config.test.ts` 17 项全绿
- [ ] 清理验证数据：逻辑音箱组 id=1（lab38→device5，保留作 UI 查看样例）

## T8 用例「只能关联逻辑音箱」+ 旧用例迁移（2026-10-30）

- [x] e2e 换绑支持背景噪声多选 `playback_speaker_group_ids[]` → 该实验室 `device_ids`
- [x] 声纹（algorithm_params 独立列）按执行实验室解析 `playback_speaker_group_id`（`_voiceprint_playback_device`）
- [x] 迁移脚本 `scripts/migrate_cases_to_speaker_groups.py`：按设备名补建逻辑音箱 + 改写 config/algorithm_params，幂等 + `--dry-run`
- [x] 迁移干跑：新建 11 组（+已有 1 组 = 12 个位置），命中 710 条用例 / 1436 处设备引用 / 3 处背景噪声引用，无未匹配设备
- [x] 前端：音频卡、背景噪声（轮次 + 全局）、声纹、干扰人选择器**只列逻辑音箱**；批量工具（标签音箱/批量音箱/音箱交叉）改为逻辑音箱
- [x] 前端序列化/回填：`playback_speaker_group_id` / `playback_speaker_group_ids`（audio/背景噪声/声纹/干扰人/全局噪声）
- [x] 试听必须选实验室：试听弹窗新增「实验室 *」，按组解析实体设备；用例级试听带 `lab_id`
- [x] 网关：`TestCasePreviewRequest.lab_id` + 后端预览前解析逻辑音箱（未选实验室/组内无该实验室设备 → 400）
- [x] 单测：后端换绑 21 项（含背景噪声数组、声纹组解析）；前端音频卡 3 + 试听 15 + 面板 2 + 序列化 18
- [x] 执行迁移脚本（非 dry-run）：12 个逻辑音箱 / 12 条实验室设备；710 条用例、1436 处设备引用、3 处背景噪声改写；重跑 dry-run 为 0（幂等）
- [x] 部署：`e2e_test_service` 全量重建、`api_gateway` 增量重建（复用依赖层避免 pip 全量重装），两容器 healthy
- [x] 实测（迁移后用例）：预览不传 lab → 「实验室播放请先选择实验室」；传 lab 39 → 「逻辑音箱 1 未配置实验室 39 的播放设备」
- [x] 上传选项 / 批量设置弹窗改为逻辑音箱：
  - 上传选项（上传/文件夹导入）：只列逻辑音箱，携带 `default_playback_speaker_group_id`；
    audio_service 建用例时把轮内所有播放目标改写为组引用（逐轮可不同组）
  - 批量设置逻辑音箱：`playback_devices.speakerGroupId`（逐轮 `round_values[].speakerGroupId`）
  - 批量噪声：`noise_speaker_group_ids`（逐轮 `speakerGroupIds`），写 `playback_speaker_group_ids`
- [x] 网关 schema：`AudioUploadConfirmRequest.default_playback_speaker_group_id`、`TestCaseBatchActionRequest.noise_speaker_group_ids`
- [x] 实测：`POST /testcases/batch` `update_playback_devices(speakerGroupId)`、`update_noise(noise_speaker_group_ids)` 均成功，config 落 `playback_speaker_group_id(s)` 且无 device_ids
- [x] 单测：`test_batch_speaker_group.py` 6 项；前端批量弹窗 2 项
