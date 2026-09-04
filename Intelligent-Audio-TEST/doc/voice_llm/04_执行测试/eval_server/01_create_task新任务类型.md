# 01 — create_task 新任务类型

> **所属步骤**：04_执行测试 → eval_server  
> **改造类型**：修改  
> **涉及文件**：`eval_server/app/controllers/api.py`

---

## 背景

eval_server 的任务创建入口 `POST /api/create_task` 是**策略模式 + 主/子维度组织**的前台入口：API 白名单负责「参数校验 + 本地/远程分发」，真正的计算由 `calculators` 包内按注册表路由到对应策略（详见 `02_评估维度架构_策略模式与主从维度`）。

演进路径：

- **第一阶段（传统维度）**：`wer/ser/der/cpwer/tcpwer/stm_wer` 6 种，单指标、纯文本/STM 比较
- **第二阶段 LLM 评审**：新增 `llm_judge`
- **第三阶段（xiaoyi_metrics 多维度）**：新增 `turn_taking / interruption_metrics / non_interactive_latency / noise_latency / rejection_judge / interruption_judge / high_freq_turn_taking / high_freq_llm_judge` 8 种

当前实现将 15 种类型的**参数校验**与**本地/远程分发**统一收敛到 `_validate_and_dispatch_task`（`api.py` 129 行附近），由 `create_task`（JSON）与 `create_task_upload`（multipart 文件上传）两个端点共用。

> 类型白名单 ≠ 注册表：API 白名单 15 项是**入口层**约束；`calculators` 包注册表共 **18 键**（6 传统 + 12 xiaoyi_metrics）。缺口的 `tor / false_takeover / takeover_latency` 三个子维度**不作为独立 API 类型开放**，只能通过 `turn_taking` 主维度的 `sub_tasks` 参数触发（见下文）。

---

## 实际实现

### 1. 支持的任务类型（API 白名单 15 项）

```python
SUPPORTED_TASK_TYPES = [
    'wer', 'ser', 'der', 'cpwer', 'tcpwer', 'stm_wer',   # 传统维度
    'llm_judge',                                          # LLM 评审（策略）
    'turn_taking',                                        # xiaoyi 主维度（编排中枢）
    'interruption_metrics',
    'non_interactive_latency', 'noise_latency',
    'rejection_judge', 'interruption_judge',
    'high_freq_turn_taking', 'high_freq_llm_judge',
]
```

> 该列表定义在 `_validate_and_dispatch_task` 函数内部（`api.py` 128 行，不是模块顶部常量）。不在列表内的任务类型直接返回 `CODE_BUSINESS_ERROR`。

#### 白名单 与 注册表（18 键）对照

| API 白名单 | 注册表键 | 说明 |
|-----------|---------|------|
| 15 项全在上面 | 18 键 | 多出的 3 键：`tor` / `false_takeover` / `takeover_latency` |
| `turn_taking` | `turn_taking` + `tor` + `false_takeover` + `takeover_latency` | 主维度编排：一次双路 ASR，按 `_SUB_DIMENSIONS` 依次计算 7 个子维度（含不在白名单的 3 个） |
| — | `tor` / `false_takeover` / `takeover_latency` | 无独立 API 类型，仅能通过 `turn_taking` 的 `task_params['sub_tasks']` 指定子集触发，如 `sub_tasks: ['tor', 'takeover_latency']` |

### 2. 类型字段验证规则

| 类型 | 必填校验 |
|------|---------|
| `wer` / `ser` | 无 `rounds` 时必须同时有 `asr_ref`、`asr_hyp`（多轮模式下从 rounds 逐轮取值，可缺省） |
| `cpwer` / `tcpwer` / `stm_wer` | `ref_stm`、`hyp_stm` |
| `der` | `rttm_ref`、`stm_ref`、`rttm_res`、`stm_res` |
| `llm_judge` | 无 `rounds` 时必须同时有 `answer`、`correct_answer`；`model`/`prompt` 有默认值，**非必填** |
| `interruption_metrics` | `user_wav` 或 `user_asr`/`user_chunks` 至少一个 + `ai_wav`/`model_wav`/`model_asr`/`model_chunks` 至少一个 |
| `non_interactive_latency` / `noise_latency` | 不在此拦截，交给 calculate 层返回带说明的空结果 |
| `rejection_judge` / `interruption_judge` | `ai_wav` 或 `video_path`/`record_file`（含 rounds[0]）至少一个 |
| `high_freq_turn_taking` | `user_wav` + `ai_wav`（取顶层或 rounds[0]） |
| `high_freq_llm_judge` | `ai_wav` 或 `record_file`/`video_path`/`record_path`（取顶层或 rounds[0]）+ 必须有 `rounds` |

校验失败返回 `CODE_VALIDATION_ERROR`；类型不在白名单返回 `CODE_BUSINESS_ERROR`（响应中附带支持的完整列表）。

### 3. 双任务 ID 体系

- `caller_task_id`（`task_id`）：主后端传入的调用方任务 ID，仅透传关联，不参与本地存储主键
- `eval_task_id`：eval_server 本地任务 ID，`create_task_upload` 场景由调用方预先生成（`task_{uuid4().hex}`），其余场景在分发函数内生成

### 4. 本地 / 远程分发

```python
if eval_task_id is None:
    eval_task_id = f"task_{uuid.uuid4().hex}"

if endpoints:
    remote_task_id = remote_service.create_remote_task(
        task_type=task_type, task_params=task_params,
        endpoints=endpoints, caller_task_id=caller_task_id,
    )
    # 返回 eval_task_id = remote_task_id
else:
    # 本地处理：LocalConcurrencyManager 限流 → 线程池计算
```

**本地处理链路**（`_validate_and_dispatch_task` → 本地分支）：

1. `LocalConcurrencyManager.can_start()` 检查，超过 `LOCAL_MAX_CONCURRENCY`（默认 30）返回 `CODE_CONCURRENCY_EXCEEDED`（附带当前/最大并发数）
2. `increment()` → `TaskModel.create_task(...)` → `update_task_status(eval_task_id, 'processing', started_at=...)`
3. 启动守护线程 `_run_with_decrement -> process_local_task`（finally 中 `decrement()`）
4. `process_local_task` 内通过懒加载线程池 `_get_calc_pool()`（`ThreadPoolExecutor(max_workers=LOCAL_MAX_CONCURRENCY)`）提交 `calculate_in_process`，阻塞等待后写 `completed` + `result`；异常写 `failed` + `error_msg`

> `calculate_in_process` 内部即注册表路由：`TaskService.calculate(task_type, task_params)` → 命中对应 Calculator 策略（见 02 文档第三章）。

**远端分发链路**：`remote_service.create_remote_task` 选择可用端点后转发，本地同步登记任务记录（`endpoint_url` 标记），由后台线程 `_poll_task_status` 轮询远端状态并回写。

### 5. 响应格式

```json
{
  "code": 0,
  "data": {
    "eval_task_id": "task_xxx",
    "task_id": "调用方任务ID(可选)",
    "status_url": "http://host/api/get_status/task_xxx",
    "final_result_url": "http://host/api/get_final_result/task_xxx",
    "task_type": "wer",
    "msg": "任务已创建，正在本地处理 / 任务已分发到远程端点处理"
  }
}
```

### 6. create_task_upload（multipart 文件上传）

`POST /api/create_task_upload` 在 JSON 端点之外提供了文件上传能力：

- 表单字段：`task_type`、`endpoints`（JSON 字符串）、`task_id`、其余标量参数
- 文件字段（`request.files`）按扩展名分流：
  - 文本类（`.txt/.stm/.rttm/.json/.csv/.srt/.vtt/.xml/.tsv`）：读取内容为字符串存入 `task_params[field_name]`
  - 二进制类（`.wav/.mp3` 等）：保存到 `config.UPLOAD_DIR/<storage_id>/`（storage_id = caller_task_id 或 eval_task_id），`task_params[field_name]` 存本地路径
- `rounds` 若为 JSON 字符串，反序列化后把每轮内 `__MULTIPART__:<field_name>` 占位符替换为对应上传落盘路径
- `xiaoyi_metrics / takeover / interruption_metrics / rejection_judge / interruption_judge` 会把 `rounds[-1]` 的 `record_file/user_wav/ai_wav/pause/first_frame_ms/start_ms/input/input_lastword/offset_ms` 提升到顶层，供校验与计算使用
- 之后同样走 `_validate_and_dispatch_task`

### 7. 任务状态与结果查询

- 状态流转：`pending` → `processing` → `completed` / `failed`
- `GET /api/get_status/<eval_task_id>`：返回状态、类型、时间戳、`error_msg`
- `GET /api/get_final_result/<eval_task_id>`：processing/pending 返回 202；failed 返回 500；成功返回 `result`（注册表策略的输出 JSON，含维度结果 / 子维度分片 + reasoning）

### 8. 端点管理接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/endpoints` | 列出所有远程端点 |
| POST | `/api/endpoints` | 创建端点（url/name/capabilities/task_types/max_process） |
| GET | `/api/endpoints/<path:url>` | 查询单个端点 |
| PUT | `/api/endpoints/<path:url>` | 更新端点 |
| DELETE | `/api/endpoints/<path:url>` | 删除端点 |
| PUT | `/api/endpoints/<path:url>/concurrency/<task_type>` | 动态调整指定类型并发限制 |

> 动态并发调整的 `task_type` 白名单更窄：目前仅支持 `wer/ser/der/cpwer/tcpwer/stm_wer/llm_judge` 7 种（`api.py` 686 行），xiaoyi_metrics 系列走端点的 `capabilities` 静态配置。

`GET /api/status` 返回本地并发（LocalConcurrencyManager）与各端点按任务类型的并发统计（`by_task_type` 来自端点 capabilities 的 `max_process`）。

---

## 不变部分

- 远程端点选择（`remote_service`）对外行为不变
- 任务轮询/结果查询/删除接口不变
- 本地并发计数与线程池构建逻辑不变
- `turn_taking` 主维度的子维度（tor/false_takeover/takeover_latency）不新增 API 类型，通过 `sub_tasks` 子集参数分发

---

## 依赖关系

| 依赖文档 | 说明 |
|---------|------|
| `02_评估维度架构_策略模式与主从维度` | 注册表路由（18 键 / 15 白名单差异）、主/子维度编排、一次 ASR 多维共享 |
| `03_LLM_Judge计算器` | llm_judge 类型计算实现（策略模式实例） |
| `04_ConcurrencyManager动态类型` | 并发限制管理 |
| `06_remote_service适配` | 远程分发逻辑 |
| `25_evaluation_service单轮评估` (主后端) | create_task 请求发送入口 |