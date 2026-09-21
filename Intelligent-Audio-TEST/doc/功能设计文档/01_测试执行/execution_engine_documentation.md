# 执行引擎 (Execution Engine) 工作原理文档

> 版本：v3.0（V9.7.31 适配版） | 更新日期：2026-09-10 | 变更说明：同步 V9.7.10 v3.0 语义——按被测设备类型(device_type)路由，废弃 `task.type` 裸字符串判定；API/E2E 执行逻辑下沉微服务（api_test_service:5003 replicas:2 / e2e_test_service:5002），经 Redis `task:queue` 竞争消费；评估经 gRPC 交 evaluation_service:5004；事件经 Redis EventBus → api_gateway:5000 Socket.IO 回推前端。
>
> 【适配说明】V9.7.31 为 DDD+CQRS 微服务架构（11 个后端服务，分布式协同复用 Redis，不引入 MQ）。本文档所述"执行引擎"指 task_service 内的**调度中枢**（ExecutionEngine 五 Mixin 组合，`task_service/core/execution_engine/`），API/E2E 执行逻辑已下沉到各自微服务，不再持有本地执行器实例。标注（新增）为本次同步新增；标注【适配说明】为 V9.7.10 单体语义 → V9.7.31 微服务语义的落位变化。整体架构见同目录《02_架构设计.md》，路由决策与废弃清单见《05_路由与废弃.md》。

## 1. 概述

执行引擎是测试自动化系统的核心组件，负责协调和执行各种类型的测试任务。V9.7.31 中执行引擎落位于 **task_service（:5001，调度中枢，单实例）**，职责收敛为：**任务调度分发 + 进度汇聚 + 生命周期管控**，本身不再执行测试用例。

按被测设备类型（device_type）路由（device_type 是执行路由的**唯一依据**）：

| device_type | 含义 | 执行服务 |
|-------------|------|----------|
| physical | 物理设备端到端测试 | e2e_test_service（:5002，单实例） |
| http_api | HTTP API 测试 | api_test_service（:5003，replicas:2） |
| websocket_api | WebSocket Realtime API 测试 | api_test_service（:5003，replicas:2，WS 会话实例内闭环） |

【适配说明】V9.7.10 单体中 ExecutionEngine 进程内直接持有 E2EExecutor / APISessionExecutor / RealtimeSessionExecutor 三执行器；V9.7.31 将三者分别落位到 e2e_test_service 的 ExecutionService 与 api_test_service 的执行器集群（共享 `shared/infrastructure/base_executor/` 基座），task_service 与执行服务之间通过 Redis 队列（`task:queue`）解耦：task_service 分发任务，执行服务 worker 竞争领取，以 `worker_instance_id` 归属校验 + RedisServiceRegistry 心跳 + 孤儿任务收养保证多实例可靠性。

## 2. 核心架构

### 2.1 ExecutionEngine：五 Mixin 组合

【适配说明】V9.7.31 中 ExecutionEngine 不再是"线程安全的单例 + 全量组件字段"的形态，而是由五个 Mixin 组合而成（`task_service/core/execution_engine/__init__.py`），每个 Mixin 承载一类职责：

```python
class ExecutionEngine(
    SchedulerMixin,      # 调度：Redis task:queue 竞争消费 + DB 兜底 + 孤儿收养
    ProgressMixin,       # 进度：进度缓存 + 节流 + EventBus 推送
    TaskControlMixin,    # 控制：pause/resume/stop + 分布式协调
    CaseExecutionMixin,  # 用例分发：_dispatch_case_by_type 按 device_type 路由
    TaskRunnerMixin      # 任务运行：任务主循环骨架 + 汇总收尾
):
    """测试任务调度引擎（调度中枢，不执行用例）"""
```

引擎内部组件（现状代码字段）：

```python
# task_service/core/execution_engine/__init__.py 初始化
self.workers = {}                # 运行中任务线程 {task_id: Thread}
self.stop_flags = {}             # 停止事件 {task_id: threading.Event}
self.pause_flags = {}            # 暂停事件 {task_id: threading.Event}
self.api_executors = {}          # 兼容保留（本地 API 执行逻辑已下沉微服务）
self.task_queue = deque()        # 本地待分发队列（DB 兜底调度用）
self.running_tasks = {}          # 运行中任务 {task_id}
self.running_apis = set()        # 运行中 API 集合
self.running_e2e = False         # E2E 任务运行状态
self.task_locks = {}             # 任务级锁
self.task_progress_cache = {}    # 任务进度缓存
self.round_progress_cache = {}   # 轮次进度缓存
self.task_completion_events = {} # 任务完成事件 {task_id: threading.Event}
```

【适配说明】V9.7.10 的 `load_balancer`（API 端点负载均衡）与 `event_manager`（进程内事件管理器）语义变化：负载均衡由 api_test_service 实例内调度 + Redis 会话亲和承担；事件推送统一为 `log_and_emit → Redis EventBus → api_gateway Socket.IO` 链路（见第 9 章）。

### 2.2 核心组件

| 组件 | 落位 | 描述 |
|------|------|------|
| workers | task_service | 存储正在运行的分发/监控线程 |
| stop_flags / pause_flags | task_service | 任务停止/暂停事件（配合 ControlMixin 与 Redis 协调） |
| task_queue | task_service | 本地待分发队列（DB 兜底调度）；主通道为 Redis `task:queue` |
| running_tasks / running_apis / running_e2e | task_service | 运行态登记（资源冲突检查） |
| task_progress_cache / round_progress_cache | task_service | 进度缓存，减少数据库查询 |
| SchedulerMixin | task_service | `TASK_QUEUE_KEY='task:queue'` 竞争消费 + `_schedule_pending_tasks` DB 兜底 + `_adopt_orphan_tasks` 孤儿收养 |
| TaskControlMixin | task_service | 任务生命周期控制（暂停/恢复/停止） |
| CaseExecutionMixin | task_service | `_dispatch_case_by_type` / `_dispatch_api_case` / `_dispatch_e2e_case` 用例分发 |
| BaseExecutor | shared/infrastructure/base_executor/_base.py | （新增）执行器基座，五 Mixin（见 2.3） |
| ExecutionService | e2e_test_service | physical 设备测试执行（gRPC :50051） |
| 执行器集群 | api_test_service | http_api / websocket_api 执行（gRPC :50071，replicas:2） |
| APIConcurrencyManager | api_test_service/core/api_concurrency_manager.py | （新增）API 级并发控制：DistributedSemaphore + 进程内 BoundedSemaphore 兜底 |
| RedisServiceRegistry | shared/utils/service_registry.py | （新增）服务实例注册与心跳（`service:instances` Hash，TTL 15s，心跳间隔 `ttl // 3`） |
| DistributedLock / DistributedSemaphore | shared/utils/distributed_coordinator.py | （新增）分布式互斥/信号量原语，受环境变量 `DISTRIBUTED_COORDINATOR_ENABLED` 开关控制 |
| EventBus | shared/utils/redis_pubsub.py | （新增）Redis 发布订阅总线，频道/事件全部枚举化（EventChannel / EventType） |

### 2.3 执行器基座 BaseExecutor（新增）

【适配说明】V9.7.10 三个执行器各自实现状态管理、日志、参数装载；V9.7.31 抽取统一基座 `shared/infrastructure/base_executor/_base.py`，e2e_test_service / api_test_service 的执行器均继承自它：

| Mixin | 职责 |
|-------|------|
| ControlMixin | 停止/暂停事件响应（进程内 Event + Redis 分布式协调） |
| LoggingMixin | `log_and_emit`：写日志 + 经 EventBus 推送前端（见第 9 章） |
| ParamsMixin | 测试参数装载与校验 |
| ResultsMixin | 执行结果收集与落库 |
| DbMixin | 数据库会话管理 |

## 3. 任务生命周期管理

### 3.1 任务启动流程

1. **接收任务启动请求**（api_gateway → task_service Command 侧 `CreateTask`）
2. **落库与入队**：【适配说明】V9.7.31 中任务启动即入队——任务落库（`worker_instance_id = NULL`、状态 `PENDING`）→ 发出 `TaskCreated` 领域事件 → `LPUSH task:queue`，等待执行服务认领。
3. **获取任务信息**：
   - 查询任务关联的用例及 `device_type`（取自 `task_case_relations.device_type`，device_id 列已存在，device_type 列为（新增），见《05_路由与废弃.md》3.3 迁移脚本）
   - 获取任务关联的设备/API 信息
4. **检查执行条件（按 device_type 路由）**：
   - physical：同时只允许一个物理设备任务运行，互斥采用 Redis `DistributedLock`（`lock:task:physical:{device_id}`），不再使用进程内布尔标记（（新增））
   - http_api / websocket_api：支持并行执行，相同 API 端点的任务串行（由 api_test_service 的 APIConcurrencyManager 保证）
5. **分发或排队**：
   - 满足条件：`_dispatch_case_by_type` 按用例 device_type 分发到对应执行服务
   - 不满足：任务留在 `task:queue`，状态 `QUEUED`
6. **用例状态流转（关键，`_claim_case` 原子占用）**：
   - **PENDING**：用例创建后的初始状态
   - **QUEUED**：已提交执行服务、等待执行权（原子占用机制设置）
   - **RUNNING**：已获得执行权，正在执行
   - **COMPLETED/FAILED**：执行结束
   - 【适配说明】状态值一律取自 `shared/models/common_enums.py::ExecutionStatus` 枚举，`TaskCase.status` 由 `derive_task_case_status(ExecutionStatus, EvaluationStatus)` 派生，禁止裸字符串。
7. **推送进度更新**：经 Redis EventBus → api_gateway Socket.IO 实时同步前端（房间按 task_id 隔离）

### 3.2 后台调度器

执行引擎内置后台调度器，自动检测并调度 `PENDING` 状态的任务，无需手动触发。

#### 3.2.1 调度器架构

【适配说明】V9.7.10 为单进程 `_scheduler_loop` 轮询；V9.7.31 为"Redis 队列竞争消费为主 + DB 兜底轮询为辅"的双通道（`task_service/core/execution_engine/mixins/scheduler.py`）：

```python
# task_service/core/execution_engine/mixins/scheduler.py（关键常量与流程）
TASK_QUEUE_KEY = 'task:queue'       # Redis List，LPUSH/BRPOP
DEFAULT_BRPOP_TIMEOUT = 5           # 阻塞超时（秒），常量化

# 通道一：BRPOP 竞争消费
def _consume_redis_queue(self):
    _, payload = redis_client.brpop(TASK_QUEUE_KEY, timeout=DEFAULT_BRPOP_TIMEOUT)
    # 校验 worker_instance_id 归属：非本实例认领的任务 → LPUSH 回队
    # 本实例认领 → 绑定 worker_instance_id，进入分发流程

# 通道二：DB 兜底（防 Redis 消息丢失）
def _schedule_pending_tasks(self):
    pending_tasks = session.query(Task).filter_by(
        status=TaskStatus.PENDING, deleted=False
    ).order_by(Task.created_at.asc()).all()
    # 逐个检查资源冲突并分发

# 可靠性兜底：孤儿收养
def _adopt_orphan_tasks(self):
    # 回收"声明了 worker_instance_id 但对应实例已失联"的任务
    # 实例存活判定依据 RedisServiceRegistry 心跳（TTL 15s 过期即视为失联）
```

#### 3.2.2 调度规则

| device_type | 调度规则 |
|----------|----------|
| physical（物理设备） | 同时只允许一个物理设备任务运行（Redis DistributedLock 互斥） |
| http_api（HTTP API） | 可以并发运行，但不能使用相同的API（APIConcurrencyManager 信号量控制） |
| websocket_api（WebSocket API） | 可以并发运行，但不能使用相同的API；WS 会话在认领实例内闭环（实例亲和路由，见《02_架构设计.md》5.2） |

#### 3.2.3 调度规则落位（适配说明）

- **多实例竞争**：api_test_service replicas:2，worker 领取任务后写 `worker_instance_id`；消费时校验归属，非本实例认领的任务立即 `LPUSH` 回队，由归属实例消费。
- **实例心跳**：各执行服务启动时经 `shared/utils/service_registry.py::RedisServiceRegistry` 注册到 `service:instances` Hash，按 `ttl // 3` 间隔续期，TTL 15s；失联实例的任务由 task_service `_adopt_orphan_tasks` 收养重新入队。
- **原子占用**：task_service 分发用例前经 `_claim_case` 原子占用（见 3.3.2），防止重复分发。

#### 3.2.4 调度器配置

| 配置项 | 默认值 | 描述 |
|--------|--------|------|
| TASK_QUEUE_KEY | `task:queue` | Redis 队列 key（常量化于 scheduler.py） |
| DEFAULT_BRPOP_TIMEOUT | 5 秒 | BRPOP 阻塞超时 |
| scheduler_interval | 3 秒 | DB 兜底轮询间隔 |
| 心跳 TTL | 15 秒 | RedisServiceRegistry 实例存活窗口 |
| 自动启动 | - | 无需手动调用，服务启动后自动运行 |

### 3.3 任务队列与并发控制

V9.7.31 实现跨服务分层并发控制：

1. **task_service 引擎级队列（Redis `task:queue`）**：
   - 管理任务提交顺序与跨服务分发。
   - physical 任务经 Redis DistributedLock 互斥。
   - http_api / websocket_api 任务经 API 冲突检查决定是否立即分发。
   - worker 竞争消费（BRPOP）+ DB 兜底轮询双通道。

2. **api_test_service API 级并发控制（APIConcurrencyManager，新增）**：
   - 【适配说明】V9.7.10 在 APIExecutor 内用进程内 `queue.Queue` 为每个 API 维护并发槽位；V9.7.31 升级为 **Redis 分布式信号量**（`shared/utils/distributed_coordinator.py::DistributedSemaphore`，key 前缀 `api:sem:{api_id}`，常量化于 `api_test_service/core/api_concurrency_manager.py::_API_SEM_KEY_PREFIX`），保证 replicas:2 多实例下同一 API 全局并发不超限。
   - Redis 不可用时降级为进程内 `BoundedSemaphore` 兜底（（新增）容错设计）。
   - 等待计数用于进度统计（queued 用例数）。

#### 3.3.1 API级并发控制机制（适配说明）

```python
# api_test_service/core/api_concurrency_manager.py（语义示意）
_API_SEM_KEY_PREFIX = 'api:sem:'   # Redis 信号量 key 前缀，常量化

class APIConcurrencyManager:
    def acquire_api_execution_right(self, api_id, task_id, tc_rel_id, max_process):
        """跨实例获取 API 执行权：DistributedSemaphore；Redis 异常降级 BoundedSemaphore"""
        ...

    def release_api_execution_right(self, api_id, task_id):
        """释放信号量槽位，唤醒同 API 等待中的其他用例"""
        ...
```

#### 3.3.2 原子占用机制

为避免重复分发同一用例，task_service 分发前经 `_claim_case` 原子占用：

```python
# task_service/core/execution_engine/mixins/task_dispatch.py::_claim_case
claimed = session.query(TaskCase).filter(
    TaskCase.id == tc_rel_id,
    TaskCase.task_id == task_id,
    TaskCase.execution_status == ExecutionStatus.PENDING
).update({
    TaskCase.execution_status: ExecutionStatus.QUEUED,   # 原子占用为排队状态
    TaskCase.status: derive_task_case_status(ExecutionStatus.QUEUED, EvaluationStatus.PENDING)
}, synchronize_session=False)
if claimed != 1:
    continue  # 已被其他分发方占用，跳过
```

【适配说明】与 V9.7.10 语义一致，但状态值全部枚举化（`ExecutionStatus` / `EvaluationStatus`），不再使用裸字符串。

### 3.4 任务监控与日志优化

监控循环负责统计任务进度并处理超时：

- **细粒度统计**：监控日志包含以下精确计数：
  - 排队中 (QUEUED)：APIConcurrencyManager 等待计数汇总
  - 执行中 (RUNNING)：`execution_status='running'` 的用例数
  - 评估中：`evaluation_status` 为 `running/queued/pending` 的用例数
  - 执行成功 / 评估成功 / 执行失败 / 评估失败：对应状态用例数

- **日志去重**：仅在统计计数发生变化或超过 10 秒时才输出 `INFO` 级别的状态日志，减少日志冗余。

- **状态同步**：节流（Throttle）间隔 0.1s，并引入 `force=True` 机制确保关键状态切换不被丢弃。

- **进度缓存**：使用 `task_progress_cache` / `round_progress_cache` 缓存进度数据，减少数据库查询。

#### 3.4.1 等待循环统计示例

```python
# 统计各类用例数量（语义示意，状态值来自 common_enums 枚举）
queued_cases = api_concurrency_manager.total_waiting_counts()
execution_running_cases = db.query(TaskCase).filter_by(
    task_id=task_id, execution_status=ExecutionStatus.RUNNING.value
).count()
evaluation_running_cases = db.query(TaskCase).filter(
    TaskCase.task_id == task_id,
    TaskCase.evaluation_status.in_(EVALUATION_ACTIVE_STATUSES)  # status_constants frozenset
).count()
```

#### 3.4.2 进度更新节流

```python
def _emit_progress(self, task, force=False):
    # 强制更新条件：任务状态为 running/completed/failed/stopped/paused
    if task_status in FORCED_PROGRESS_STATUSES:   # status_constants.py frozenset，配置化
        force = True
    else:
        # 节流控制：0.1秒内不重复更新
        current_time = time.time()
        if current_time - last_update < 0.1:
            return
```

### 3.5 任务控制

执行引擎支持三种任务控制操作：

| 操作 | 描述 |
|------|------|
| pause | 暂停任务执行，API任务不重置执行中用例状态，physical 任务可选择重置 |
| resume | 恢复任务执行，从暂停点继续执行 |
| stop | 停止任务执行，从队列中移除任务并清理资源 |

【适配说明】V9.7.31 中任务控制是**跨服务协作**：task_service 收到控制请求后，经 Redis 分布式协调（`shared/utils/distributed_coordinator.py`）向任务归属的执行服务传播控制信号；执行服务内由 BaseExecutor 的 ControlMixin 响应（进程内 Event 即时生效），两侧通过 Redis 协调保证多实例一致性。

#### 3.5.1 暂停/恢复机制

```python
# 暂停任务核心代码（task_service TaskControlMixin，语义示意）
elif action == 'pause':
    self.pause_flags[task_id].clear()          # 进程内事件
    distributed_coordinator.publish_task_control(task_id, 'pause')  # 传播到执行服务
    task.status = TaskStatus.PAUSED.value

    # 对于 http_api / websocket_api 任务，不重置执行中的用例状态为 pending
    # 因为执行线程是在 pause_event 上阻塞，恢复时会自动继续执行
    # 如果重置为 pending，会导致调度器重新分发，造成重复执行
    if device_type == DeviceType.PHYSICAL.value:
        running_cases = session.query(TaskCase).filter_by(
            task_id=task_id, execution_status=ExecutionStatus.RUNNING.value
        ).all()
        for tc in running_cases:
            tc.execution_status = ExecutionStatus.PENDING.value
            tc.completed_at = None
            tc.duration = None
    session.commit()
    self._emit_progress(task)

# 恢复任务核心代码
elif action == 'resume':
    self.pause_flags[task_id].set()
    distributed_coordinator.publish_task_control(task_id, 'resume')
    task.status = TaskStatus.RUNNING.value
    session.commit()
    self._emit_progress(task)
```

#### 3.5.2 停止机制

```python
# 停止任务核心代码（语义示意）
elif action == 'stop':
    # 先从 Redis 队列中移除任务（LREM task:queue）
    redis_client.lrem(TASK_QUEUE_KEY, 0, task_payload)

    # 更新任务状态为 stopped
    task.status = TaskStatus.STOPPED.value
    task.completed_at = datetime.now(TIMEZONE_UTC_PLUS_8)  # 时区常量化

    # 将所有用例标记为 skipped
    cases = session.query(TaskCase).filter_by(task_id=task_id).all()
    for tc in cases:
        tc.status = 'skipped'
        tc.execution_status = ExecutionStatus.STOPPED.value
        tc.evaluation_status = EvaluationStatus.STOPPED.value
        tc.error_message = '任务被手动停止'
    session.commit()

    # 传播停止信号到执行服务（进程内 stop_flags + Redis 协调）
    distributed_coordinator.publish_task_control(task_id, 'stop')
    if task_id in self.workers:
        self.stop_flags[task_id].set()
        self.pause_flags[task_id].set()
```

#### 3.5.3 暂停的队列任务处理

对于暂停时处于 `QUEUED` 状态的任务，恢复时重新入队：

```python
if action == 'resume' and task_id not in self.workers:
    if device_type in (DeviceType.HTTP_API.value, DeviceType.WEBSOCKET_API.value):
        # 重新 LPUSH task:queue，等待执行服务认领
        redis_client.lpush(TASK_QUEUE_KEY, task_payload)
        task.status = TaskStatus.QUEUED.value
        session.commit()
        self._emit_progress(task)
        return True
```

### 3.6 任务执行流程（分发主循环）

【适配说明】V9.7.10 的主循环为"进程内取用例 → 线程池提交"；V9.7.31 改为"原子占用 → gRPC 分发到执行服务"：

```python
# task_service/core/execution_engine/mixins/task_dispatch.py（语义示意）
def _dispatch_case_by_type(self, task_id, task, tc_rel, session):
    """按 TaskCase.device_type 分发用例执行（废弃 task.type 判定）"""
    device_type = tc_rel.device_type   # device_type 列为（新增）P0 迁移项
    if device_type == DeviceType.PHYSICAL.value:
        self._dispatch_e2e_case(task_id, task, tc_rel, session)
        # → gRPC E2ETestService.StartE2ETest（e2e_test_service :50051）
    elif device_type in (DeviceType.HTTP_API.value, DeviceType.WEBSOCKET_API.value):
        self._dispatch_api_case(task_id, tc_rel, session)
        # → gRPC APITestService.StartAPITest（api_test_service :50071），
        #   StartAPITestRequest 增 device_type / device_id 字段（新增）
    else:
        # device_type 缺失兜底：记 ERROR 日志并经 EventBus 广播，置 FAILED
        # （禁止静默回退 physical）
        ...

def _claim_case(self, task_id, tc_rel_id, session):
    # 分发前原子占用：PENDING → QUEUED（见 3.3.2）
    ...
```

```python
# 分发主循环（语义示意）
while not stop_event.is_set():
    tc_rel = session.query(TaskCase).filter_by(
        task_id=task_id,
        execution_status=ExecutionStatus.PENDING.value
    ).order_by(TaskCase.created_at.asc()).first()

    if not tc_rel:
        break  # 所有测试用例分发完成

    # 检查暂停/停止（进程内事件 + Redis 协调信号）
    if not pause_event.is_set():
        pause_event.wait()
    if stop_event.is_set():
        break

    # 设备状态检查（仅 physical 任务；见第 5 章）
    ...

    # 原子占用用例（PENDING → QUEUED），避免重复分发
    if not self._claim_case(task_id, tc_rel.id, session):
        continue

    # 按 device_type 路由分发到执行服务（gRPC）
    self._dispatch_case_by_type(task_id, task, tc_rel, session)
    # 后续状态流转由执行服务驱动：QUEUED → RUNNING → COMPLETED/FAILED

# 等待所有用例终态（执行中/排队中/评估中均为 0）
while True:
    active_cases = session.query(TaskCase).filter(
        TaskCase.task_id == task_id,
        (TaskCase.execution_status.in_(ACTIVE_EXECUTION_STATUSES)) |
        (TaskCase.evaluation_status.in_(ACTIVE_EVALUATION_STATUSES))
    ).count()
    if active_cases == 0:
        break
    time.sleep(1)

# 更新任务终态并发布任务完成事件（EventBus）
```

## 4. 任务并发同步机制

### 4.1 并发控制策略

| device_type | 并发策略 | 详细说明 |
|----------|----------|----------|
| physical（物理设备） | 串行执行 | 同时只允许一个物理设备任务运行，Redis `DistributedLock`（`lock:task:physical:{device_id}`）保证跨实例互斥（（新增）） |
| http_api / websocket_api | 并行执行 | 支持多任务并行，相同 API 端点经 Redis `DistributedSemaphore`（`api:sem:{api_id}`）全局串行（（新增）），避免 API 过载 |
| 测试用例 | 并行执行 | API 测试用例在 api_test_service 线程池并行执行；physical 测试用例在 e2e_test_service 串行执行 |

### 4.2 线程安全与分布式同步机制

1. **进程内锁/事件**（单实例内）：
   - `threading.Lock()` 保证队列操作与单例初始化线程安全
   - `threading.Event()` 实现任务暂停/恢复/停止（BaseExecutor ControlMixin）

2. **分布式原语（新增）**（`shared/utils/distributed_coordinator.py`）：
   - `DistributedLock`：physical 设备全局互斥（`lock:task:physical:{device_id}`）
   - `DistributedSemaphore`：API 级全局并发控制（`api:sem:{api_id}`）
   - `try_claim_task / release_task_claim`：任务原子抢占
   - 受环境变量 `DISTRIBUTED_COORDINATOR_ENABLED` 开关控制，便于开发环境降级单机运行

3. **资源隔离**：
   - 不同执行服务独立部署（e2e_test_service 单实例 / api_test_service replicas:2）
   - 跨服务状态统一收敛到 Redis（队列、锁、信号量、实例注册表、EventBus），避免服务间直接共享内存状态

### 4.3 API/Realtime 测试并发执行

API/Realtime 测试在 api_test_service 内以线程池并发，通过 adapter 体系适配不同协议（HTTP、流式 HTTP、WebSocket）：

1. **线程池配置**：
   - 根据可用API端点计算最大工作线程数
   - 每个可用端点贡献其 max_process 配置
   - 默认值为 5（配置化，拒绝魔法数字）

2. **实例亲和（新增）**：
   - task_service 经 `_dispatch_api_case` 分发时携带 `device_type` / `device_id`
   - api_test_service replicas:2 下，同一任务的用例绑定认领实例执行（`worker_instance_id` 归属校验）
   - **websocket_api 的 WS 长连接会话在认领实例内闭环，禁止跨实例迁移**（实例亲和路由，见《02_架构设计.md》5.2）；实例失联时任务经孤儿收养重新入队，WS 会话重建

3. **Adapter 体系（新增）**：
   - `BaseAPIAdapter`：抽象基类，定义统一生命周期（initialize / pre_process / send / recv / post_process / teardown）
   - `HttpAPIAdapter`：标准 HTTP API 测试适配器
   - `HttpStreamAdapter`：流式 HTTP API 测试适配器
   - `RealtimeAPIAdapter`：WebSocket API 测试适配器
   - 执行器不再直接管理 HTTP/WS 调用，而是委托给 adapter

4. **等待机制**：
   - 任务完成后等待所有测试用例达到终态
   - 支持超时机制（默认 5 分钟，配置化）
   - 定期检查测试用例状态

## 5. 设备状态管理

### 5.1 设备状态检查

在每个测试用例执行前，执行服务会检查设备状态：

1. **被测设备检查**：
   - 检查所有关联设备是否在线（physical 读 playback_devices；http_api/websocket_api 读 apis 健康状态）
   - 如果设备离线，标记用例为 failed 并跳过

2. **播放设备检查（仅 physical）**：
   - 检查测试用例中配置的播放设备
   - 确保播放设备状态正常
   - 如果播放设备异常，标记用例为 failed 并跳过

### 5.2 设备状态处理与 physical 互斥（新增）

1. **设备离线处理**：
   - 记录详细错误日志（log_and_emit）
   - 经 EventBus 推送告警到前端
   - 标记测试用例为 failed
   - 继续执行其他测试用例

2. **设备恢复处理**：
   - 在下一个测试用例执行时重新检查设备状态
   - 设备恢复在线后自动继续执行

3. **physical 设备互斥（新增）**：
   - 【适配说明】V9.7.10 用进程内布尔标记（`running_e2e`）互斥；V9.7.31 升级为 Redis `DistributedLock`，锁 key 为 `lock:task:physical:{device_id}`，保证多实例部署下物理设备全局独占。
   - 锁带 TTL 与持有者标识，任务终态时释放；实例崩溃由 TTL 自动过期兜底。

## 6. 错误处理和容错机制

### 6.1 异常捕获和处理

执行链路各层实现完善的异常捕获机制：

1. **全局异常捕获**：task_service 分发循环与执行服务执行线程均捕获所有异常
2. **详细错误日志**：log_and_emit 记录完整错误信息和堆栈跟踪（本地日志 + EventBus 推送）
3. **状态恢复**：
   - 更新任务状态为 failed
   - 将所有正在执行的测试用例标记为 failed
   - 记录错误信息和执行时长
4. **告警推送**：经 EventBus → api_gateway Socket.IO 推送错误告警到前端

### 6.2 容错机制

1. **设备容错**：
   - 设备离线时跳过当前用例，继续执行其他用例
   - 支持动态设备恢复检测

2. **API容错**：
   - api_test_service 内自动选择最佳 API 端点
   - 支持API端点健康状态动态调整
   - API执行失败时标记用例为 failed，继续执行其他用例

3. **分布式容错（新增）**：
   - **Redis 异常降级**：DistributedSemaphore 降级为进程内 BoundedSemaphore；调度降级为纯 DB 兜底轮询
   - **实例失联收养**：执行服务实例崩溃（心跳 TTL 15s 过期）后，task_service `_adopt_orphan_tasks` 收养其任务重新入队
   - **消息丢失兜底**：`task:queue` 消费丢失由 `_schedule_pending_tasks` DB 轮询补偿

4. **资源容错**：
   - 线程池异常时优雅处理
   - 数据库连接异常时重试机制

### 6.3 重试机制

执行链路没有实现显式的用例级重试，但通过以下方式实现了类似的效果：

1. **暂停/恢复机制**：支持手动暂停和恢复任务，相当于手动重试
2. **设备状态检查**：设备恢复在线后自动继续执行，相当于设备级别的重试
3. **用例状态管理**：physical 任务暂停后重置用例状态为 pending，恢复时重新执行，相当于用例级别的重试
4. **孤儿收养（新增）**：实例失联后任务自动重新入队，相当于任务级别的自动重试

## 7. API测试执行流程

### 7.1 概述

API测试用于验证语音识别和翻译API的性能和准确性。task_service 按 `device_type` 将 http_api / websocket_api 用例分发到 api_test_service，后者根据API配置和测试用例，自动选择最优的API端点并执行测试请求。

v3.0 起，执行器不再直接管理 HTTP/WS 调用，而是通过 **adapter 体系** 委托给适配器（（新增），落位于 api_test_service）：

| 适配器 | 适用场景 | 协议 |
|--------|----------|------|
| `BaseAPIAdapter` | 抽象基类，定义统一生命周期接口 | - |
| `HttpAPIAdapter` | 标准 HTTP API 测试（device_type='http_api'） | HTTP |
| `HttpStreamAdapter` | 流式 HTTP API 测试（device_type='http_api'，流式响应） | HTTP (chunked) |
| `RealtimeAPIAdapter` | WebSocket API 测试（device_type='websocket_api'） | WebSocket |

【适配说明】adapter 选择依据 `apis.device_type` 列（（新增）P0 迁移项）与 `adapter_class` 字段，经工厂创建；禁止以 `task.type` 或 URL 前缀猜测协议。

### 7.2 执行步骤

#### 7.2.1 任务初始化（api_test_service 内）

1. **获取API配置**：
   - 从数据库中获取任务关联的API配置
   - 读取API的默认参数和元数据
   - 解析API的认证信息

2. **端点选择与初始化**：
   - 查询所有可用的API端点
   - 筛选状态为"online"的端点
   - 根据优先级排序端点

3. **线程池配置**：
   - 计算所有可用端点的最大进程数之和
   - 创建 ThreadPoolExecutor 实例
   - 记录初始化日志（log_and_emit）

4. **Adapter 选择（新增）**：
   - 根据 `device_type` 选择对应的 adapter
   - `http_api` → `HttpAPIAdapter` 或 `HttpStreamAdapter`
   - `websocket_api` → `RealtimeAPIAdapter`
   - 通过 adapter 工厂创建适配器实例

#### 7.2.2 用例执行循环

1. **获取待执行用例**：
   - 执行服务从数据库中查询状态为"queued"的测试用例（task_service 已原子占用）
   - 按照创建时间排序
   - 取出第一个待执行用例

2. **设备状态检查**：
   - 检查所有关联设备的状态
   - 确保设备都处于"online"状态
   - 如果设备离线，标记用例为"failed"并跳过

3. **提交用例到线程池**：
   - 将用例提交到线程池执行
   - 状态由工作线程管理：`queued → running → completed/failed`
   - 工作线程调用 adapter 的方法完成实际请求

#### 7.2.3 API级并发控制（适配说明）

```python
# api_test_service 执行器（语义示意）
def execute_api_case(self, app, task_id, tc_rel_id):
    # 1. 原子更新用例状态为 running
    claimed = db.session.query(TaskCase).filter(
        TaskCase.id == tc_rel_id,
        TaskCase.execution_status.in_(['pending', 'queued'])
    ).update({
        TaskCase.execution_status: 'running'
    })

    # 2. 获取API执行权（APIConcurrencyManager：DistributedSemaphore 跨实例控制，
    #    Redis 异常时降级 BoundedSemaphore）
    if not self.api_concurrency_manager.acquire_api_execution_right(
            api_id, task_id, tc_rel_id, max_process):
        return False

    try:
        # 3. 通过 adapter 执行 API 测试（执行器不再直接管理 HTTP 调用）
        adapter = self.adapter_factory.create(device_type, api_config)
        adapter.initialize()
        adapter.pre_process()
        adapter.send(payload)
        result = adapter.recv()
        adapter.post_process()
        output = adapter.output  # 获取统一输出
    finally:
        # 4. 释放API执行权
        self.api_concurrency_manager.release_api_execution_right(api_id, task_id)
        adapter.teardown()
```

#### 7.2.4 状态流转（关键）

【适配说明】执行侧状态更新由 api_test_service 驱动并经 EventBus 广播，task_service 只做汇聚；状态值枚举化（`shared/models/common_enums.py`）。

```
tc_rel.execution_status: pending → queued → running → completed/failed
tc_rel.evaluation_status:       pending    → queued → running → completed/failed
tc_rel.status:                  pending                    → passed/failed
```

| 阶段 | execution_status | evaluation_status | status |
|------|------------------|-------------------|--------|
| 用例创建 | pending | - | pending |
| task_service 原子占用（`_claim_case`） | queued | - | running |
| 执行服务开始执行 | running | pending | running |
| API调用成功 | completed | queued | running |
| 评估完成 | completed | completed | passed |
| API调用失败 | failed | failed | failed |
| 任务停止 | stopped | stopped | skipped |

### 7.5 Realtime API测试执行流程

#### 7.5.1 概述

Realtime API 测试用于验证基于 WebSocket 协议的实时语音识别和翻译 API。由 api_test_service 内的 Realtime 会话执行器驱动（执行器基座同为 BaseExecutor 五 Mixin），通过 `RealtimeAPIAdapter` 适配器完成 WebSocket 连接、音频分片流式发送和事件驱动的结果接收。

【适配说明】
- **不引入 `TaskType='realtime_api'`**：Realtime 语义由 `device_type='websocket_api'` 承载（决策见《05_路由与废弃.md》废弃清单 #3）。
- **WS 会话实例内闭环（（新增））**：WS 长连接与其认领的 api_test_service 实例强绑定（会话亲和路由），会话生命周期内禁止跨实例迁移；实例失联时任务经孤儿收养重新入队、WS 会话重建。
- **评估跨服务**：识别结果评估不在此执行，经 gRPC 交 evaluation_service:5004（见 8.2.5 与第 11 章）。

#### 7.5.2 执行步骤

1. **初始化 Adapter**：
   - `adapter.initialize()` 建立 WebSocket 连接
   - 启动独立的接收线程，监听服务端推送的事件

2. **音频分片流式发送（每个测试轮次）**：
   - 通过混音切片器将音频切分为固定大小的分片
   - 逐个调用 `adapter.send(chunk)` 发送音频分片
   - 所有分片发送完毕后调用 `adapter.commit_input()` 通知服务端输入结束
   - 调用 `adapter.post_process()` 执行后处理（如等待最终结果）
   - 从 `adapter.output` 获取最终识别/翻译结果

3. **事件驱动接收**：
   - 接收线程持续监听 WebSocket 消息
   - 收到结果事件后写入 adapter 的输出缓冲区
   - 主线程从输出缓冲区获取最终结果

```python
# Realtime API 执行流程示例（语义示意）
adapter = self.adapter_factory.create(DeviceType.WEBSOCKET_API.value, api_config)
adapter.initialize()  # 建立 WebSocket 连接 + 启动接收线程

for round in test_rounds:
    chunks = audio_stream_orchestrator.chunk_audio(audio_data)
    for chunk in chunks:
        adapter.send(chunk)          # 逐片发送音频
    adapter.commit_input()           # 通知输入结束
    adapter.post_process()           # 后处理
    result = adapter.output          # 获取最终结果
    # 经 gRPC 提交 evaluation_service 评估...
```

## 8. 端到端测试执行流程

### 8.1 概述

端到端测试用于验证完整的语音识别和翻译流程，包括音频播放、设备唤醒、语音采集和结果返回。

> **注意**：v3.0 起，端到端测试由 `device_type='physical'` 决定，不再使用 `task.type`。
>
> 【适配说明】V9.7.31 中 physical 用例由 task_service `_dispatch_e2e_case` 经 gRPC（E2ETestService :50051）分发到 e2e_test_service 执行。

### 8.2 执行步骤

#### 8.2.1 用例执行循环

1. **获取待执行用例**：
   - e2e_test_service 从数据库中查询状态为"queued"的测试用例
   - 按照创建时间排序
   - 取出第一个待执行用例

2. **设备状态检查**：
   - 检查所有关联设备的状态
   - 确保设备都处于"online"状态
   - 如果设备离线，标记用例为"failed"并跳过

3. **执行E2E测试用例**：
   - 设备唤醒（并行）
   - 提示词播放（同步）
   - 噪声音频播放（异步）
   - 干声音频播放（同步）
   - 结果采集（并行）
   - 结果评估（同步，经 gRPC 交 evaluation_service）

#### 8.2.2 状态管理

```python
def _update_tc_rel_status(self, tc_rel_id, **kwargs):
    """更新TaskCase状态（e2e_test_service 执行器内，状态值枚举化）"""
    tc_rel = db.session.query(TaskCase).get(tc_rel_id)
    if tc_rel:
        for key, value in kwargs.items():
            setattr(tc_rel, key, value)

        if 'execution_status' in kwargs:
            if kwargs['execution_status'] == ExecutionStatus.RUNNING.value:
                tc_rel.started_at = datetime.now(TIMEZONE_UTC_PLUS_8)
                tc_rel.evaluation_status = EvaluationStatus.QUEUED.value  # 评估状态排队
            elif kwargs['execution_status'] in (ExecutionStatus.COMPLETED.value,
                                                ExecutionStatus.FAILED.value):
                tc_rel.completed_at = datetime.now(TIMEZONE_UTC_PLUS_8)

        db.session.commit()
```

#### 8.2.3 状态流转

```
tc_rel.execution_status: pending → running → completed/failed
tc_rel.evaluation_status: pending → queued → running → completed/failed
tc_rel.status:             pending → running → passed/failed
```

| 阶段 | execution_status | evaluation_status | status |
|------|------------------|-------------------|--------|
| 用例创建 | pending | - | pending |
| task_service 原子占用 | queued | - | running |
| 开始执行（e2e_test_service） | running | queued | running |
| 执行成功 | completed | - | running |
| 提交评估 | - | queued | running |
| 评估开始 | - | running | running |
| 评估完成 | completed | completed | passed/completed |
| 执行失败 | failed | failed | failed |

#### 8.2.4 评估状态保护

在 e2e_test_service 执行器中，评估状态的更新会避免覆盖已开始的评估状态：

```python
# 只有当评估状态不是 running 时，才设置为 queued
if tc_rel.evaluation_status != EvaluationStatus.RUNNING.value:
    tc_rel.evaluation_status = EvaluationStatus.QUEUED.value
```

这确保了多个设备结果并行采集时，只有第一个提交评估的任务设置评估状态为 `running`，后续的评估任务不会覆盖该状态。

#### 8.2.5 评估跨服务执行（新增）

【适配说明】V9.7.10 评估在进程内直调；V9.7.31 评估链路为：

1. 执行服务（e2e/api）完成用例执行后，将结果经 gRPC 提交 evaluation_service:5004（EvaluateCase / Reevaluate 系列 RPC）；
2. evaluation_service 经 EventBus 订阅 `EventChannel.CASE_EVENTS` 获知用例执行事件（`shared/utils/redis_pubsub.py`）；
3. 评估完成后 evaluation_service 发布 `EventType.CASE_EVALUATION_COMPLETED` 事件；
4. 执行服务 / task_service 订阅该事件更新用例终态并推进任务汇总。

## 9. 实时进度推送

【适配说明】V9.7.10 由进程内 EventManager 直连 WebSocket 推送；V9.7.31 推送链路为**跨服务事件总线**（（新增））：

```
执行器内 log_and_emit（shared/infrastructure/logging_adapter.py）
    → Redis EventBus 发布（shared/utils/redis_pubsub.py，EventChannel/EventType 枚举）
    → api_gateway:5000 订阅
    → Socket.IO 转发前端（房间按 task_id 隔离）
```

推送内容不变：任务总进度、当前执行的用例、所有测试用例的状态、最近的日志信息。

推送格式：

```json
{
  "taskId": "任务ID",
  "totalProgress": 50.0,
  "status": "running",
  "completedCount": 5,
  "totalCount": 10,
  "currentCase": {
    "caseId": "用例ID",
    "name": "用例名称",
    "step": "playing",
    "startTime": 1234567890
  },
  "testCases": [
    {
      "id": "用例ID",
      "status": "passed",
      "duration": 10
    }
  ],
  "logs": [
    {
      "level": "info",
      "message": "日志信息",
      "timestamp": 1234567890
    }
  ]
}
```

- **房间隔离**：api_gateway 按 task_id 维护 Socket.IO 房间，前端仅接收自身订阅任务的进度，避免跨任务串扰。
- **进度节流**：task_service 侧 ProgressMixin 0.1s 节流 + `force=True` 关键态直发（见 3.4.2）。
- **枚举约束**：频道名与事件名一律取自 `EventChannel` / `EventType` 枚举，禁止散落魔法字符串（《02_架构设计.md》6.3 频道规划）。

## 10. 错误处理和日志记录

执行链路实现了完善的错误处理机制：

1. **异常捕获**：在关键执行点捕获异常，确保任务不会崩溃
2. **错误日志**：log_and_emit 记录详细错误信息和堆栈跟踪（本地日志 + EventBus 双写）
3. **告警推送**：经 EventBus → api_gateway Socket.IO 推送错误告警
4. **状态恢复**：在发生错误时，确保任务状态正确更新
5. **设备告警**：设备离线时发送告警通知
6. **API入口健康状态管理**：自动跟踪API入口可用性（落位 api_test_service）

### 10.1 API入口健康状态

```python
def _update_endpoint_health(self, endpoint_url, available):
    """更新API入口(Master)的可用性状态（api_test_service 内）"""
    with self.api_entry_lock:
        if endpoint_url not in self.api_entry_status:
            self.api_entry_status[endpoint_url] = {'available': True, 'fail_count': 0}

        old_status = self.api_entry_status[endpoint_url]['available']
        self.api_entry_status[endpoint_url]['available'] = available

        if not available:
            self.api_entry_status[endpoint_url]['fail_count'] += 1
        else:
            self.api_entry_status[endpoint_url]['fail_count'] = 0

        if old_status != available:
            status_str = "可用" if available else "不可用"
            self.log_and_emit(level='WARNING' if not available else 'INFO',
                              content=f"API入口状态变更: {endpoint_url} -> {status_str}")
```

### 10.2 异常处理流程

```python
try:
    # 执行测试用例（api_test_service / e2e_test_service 内，按 device_type 分派的执行器）
    result = executor.execute_case(app, task_id, tc_rel_id)
except Exception as e:
    # 捕获所有异常
    error_msg = f"API 执行异常: {str(e)}"

    # 更新测试用例状态为失败
    local_db_session = db.session()
    try:
        tc_rel = local_db_session.query(TaskCase).get(tc_rel_id)
        if tc_rel:
            tc_rel.status = 'failed'
            tc_rel.execution_status = ExecutionStatus.FAILED.value
            tc_rel.completed_at = datetime.now(TIMEZONE_UTC_PLUS_8)
            tc_rel.error_message = error_msg
            local_db_session.commit()

        # 更新任务统计信息
        task = local_db_session.query(Task).get(task_id)
        if task:
            task.completed_cases = local_db_session.query(TaskCase).filter(
                TaskCase.task_id == task_id,
                TaskCase.status.in_(['completed', 'failed'])
            ).count()
            task.failed_cases = local_db_session.query(TaskCase).filter_by(
                task_id=task_id, status='failed'
            ).count()
            local_db_session.commit()
            self._emit_progress(task)   # 经 EventBus 推送前端
    finally:
        local_db_session.close()
```

## 11. 与其他组件的交互

【适配说明】V9.7.31 中执行引擎（task_service 调度中枢）与其他微服务的交互全部为 gRPC + Redis，形成完整的测试生态系统：

| 服务/组件 | 交互方式 | 用途 |
|------|------|------|
| api_gateway（:5000） | Redis EventBus 订阅 → Socket.IO | 接收执行/进度/日志事件，按 task_id 房间转发前端 |
| task_service（:5001，本引擎） | - | 调度中枢：任务 CQRS、`_dispatch_case_by_type` 分发、进度汇聚、生命周期控制 |
| e2e_test_service（:5002 / gRPC :50051） | gRPC（StartE2ETest）+ Redis task:queue | physical 设备测试执行（ExecutionService） |
| api_test_service（:5003 / gRPC :50071，replicas:2） | gRPC（StartAPITest，请求含 device_type/device_id）+ Redis task:queue | http_api / websocket_api 测试执行；APIConcurrencyManager 并发控制 |
| evaluation_service（:5004 / gRPC :50091） | gRPC（EvaluateCase / Reevaluate 系列） | 用例结果评估；订阅 CASE_EVENTS，完成后发布 CASE_EVALUATION_COMPLETED |
| Redis（task:queue / EventBus / 锁与信号量 / 实例注册） | LPUSH/BRPOP、Pub/Sub、SETNX、Hash | 任务队列、事件总线、DistributedLock / DistributedSemaphore、RedisServiceRegistry 心跳 |
| adapter 体系（api_test_service 内） | 进程内 | BaseAPIAdapter / HttpAPIAdapter / HttpStreamAdapter / RealtimeAPIAdapter 协议适配 |
| audio_stream_orchestrator（api_test_service 内） | 进程内 | 混音切片，将音频切分为固定大小分片供 Realtime API 流式发送 |
| audio_service / spl_service | e2e_test_service 内调用 | 音频播放控制和 SPL 增益转换（随 physical 执行下沉） |

## 12. 性能优化

1. **Redis 队列竞争消费（新增）**：`task:queue` LPUSH/BRPOP + worker_instance_id 归属校验，多实例水平扩展执行能力
2. **并行处理**：
   - 设备唤醒并行执行
   - 结果采集并行执行
   - API 测试用例在 api_test_service 线程池并行执行
3. **动态端点选择**：根据健康状态和优先级选择最优API端点
4. **高效队列管理**：BRPOP 主通道 + DB 兜底轮询 + 孤儿收养，任务零遗漏
5. **资源清理**：任务完成后及时清理线程池、Redis 锁与信号量
6. **进度更新节流**：0.1秒内不重复更新，减少 EventBus/Socket.IO 消息量
7. **进度缓存**：task_progress_cache / round_progress_cache 减少数据库查询
8. **原子状态更新**：`_claim_case` 原子占用，避免重复分发同一用例
9. **分布式 API 级并发控制（新增）**：DistributedSemaphore 保证多实例下同 API 并发不超限，Redis 异常时 BoundedSemaphore 降级
10. **后台自动调度**：无需手动触发任务启动
11. **会话亲和（新增）**：websocket_api WS 长连接在认领实例内闭环，避免跨实例迁移的状态重建开销
12. **枚举与常量配置化（新增）**：队列 key、BRPOP 超时、锁/信号量 key 前缀、节流间隔等全部常量化，拒绝魔法数字

## 14. 代码示例

### 14.1 启动任务

【适配说明】V9.7.31 中任务启动为 Command 用例（task_service 应用层），引擎负责入队与调度：

```python
# task_service 应用层（Command 侧）
# CreateTask 落库（worker_instance_id = NULL、PENDING）→ LPUSH task:queue
# SchedulerMixin 自动竞争消费并分发
```

### 14.2 控制任务

```python
# task_service 应用层（语义示意）
engine = ExecutionEngine()
# 暂停任务（进程内 Event + Redis 分布式协调传播到执行服务）
success, message = engine.control_task(task_id, TaskControlAction.PAUSE.value)
# 恢复任务
success, message = engine.control_task(task_id, TaskControlAction.RESUME.value)
# 停止任务
success, message = engine.control_task(task_id, TaskControlAction.STOP.value)
```

## 15. 总结

执行引擎是测试自动化系统的调度中枢。v3.0 起，执行链路按被测设备类型（device_type）路由，支持三种执行模式：physical（e2e_test_service 端到端）、http_api / websocket_api（api_test_service，Realtime WS 会话实例内闭环）。V9.7.31 将执行逻辑下沉微服务，task_service 收敛为"分发 + 汇聚 + 管控"，通过完善的任务生命周期管理、跨服务并发控制机制和事件驱动进度推送，确保测试任务高效、可靠地执行。

执行引擎的主要特点包括：

1. **device_type 唯一路由依据（新增）**：physical / http_api / websocket_api 由 `TaskCase.device_type` 决定，废弃 `task.type` / `test_type` 裸字符串判定，TaskType 不引入 'realtime_api'
2. **微服务化执行（新增）**：执行逻辑下沉 e2e_test_service(:5002) / api_test_service(:5003, replicas:2)，task_service 调度中枢不执行用例
3. **Redis 队列竞争消费（新增）**：`task:queue` LPUSH/BRPOP + worker_instance_id 归属校验 + RedisServiceRegistry 心跳（TTL 15s）+ 孤儿任务收养
4. **统一执行器基座（新增）**：BaseExecutor 五 Mixin（ControlMixin/LoggingMixin/ParamsMixin/ResultsMixin/DbMixin），三类执行器共享
5. **分布式并发原语（新增）**：DistributedLock（physical 互斥 `lock:task:physical:{device_id}`）/ DistributedSemaphore（API 级 `api:sem:{api_id}`，BoundedSemaphore 降级兜底）
6. **灵活的任务控制**：支持暂停、恢复和停止操作（进程内 Event + Redis 分布式协调跨服务传播）
7. **可靠的设备状态管理**：自动检查设备状态，确保测试可靠性
8. **完善的错误处理**：异常捕获、错误日志和告警推送，Redis 异常/实例失联多级容错
9. **事件驱动进度推送（新增）**：log_and_emit → Redis EventBus（EventChannel/EventType 枚举）→ api_gateway Socket.IO（房间按 task_id 隔离）
10. **评估跨服务化（新增）**：gRPC evaluation_service(:5004) 订阅 CASE_EVENTS，完成发布 CASE_EVALUATION_COMPLETED
11. **细粒度状态监控**：精确统计排队中、执行中、评估中等各状态用例数
12. **原子状态更新**：`_claim_case` 原子占用（PENDING→QUEUED），避免重复分发同一用例
13. **Adapter 体系（新增）**：执行器通过 BaseAPIAdapter/HttpAPIAdapter/HttpStreamAdapter/RealtimeAPIAdapter 适配不同协议，不再直接管理 HTTP/WS 调用
14. **枚举与配置化（新增）**：状态/事件/设备类型全枚举（common_enums.py + status_constants.py），调度参数全部常量化，拒绝魔法数字与硬编码

执行引擎与其他核心微服务紧密协作（gRPC + Redis EventBus），形成完整的测试生态系统，为语音识别和翻译系统的质量保障提供了有力支持。

### 15.1 核心组件交互图（微服务拓扑）

```
                         ┌──────────────────┐
                         │      前端 UI      │
                         └────────▲─────────┘
                                  │ Socket.IO（房间按 task_id 隔离）
                         ┌────────┴─────────┐
                         │ api_gateway:5000 │ 订阅 Redis EventBus
                         └────────▲─────────┘
                                  │ Redis Pub/Sub（EventChannel/EventType 枚举）
      ┌───────────────────────────┴───────────────────────────┐
      │                    Redis（总线与协同）                  │
      │  task:queue · EventBus · DistributedLock/Semaphore     │
      │  RedisServiceRegistry（service:instances，TTL 15s）     │
      └───▲───────────────────────▲───────────────────────▲───┘
          │ BRPOP/回队/收养        │ BRPOP                  │ 订阅 CASE_EVENTS
          │                       │                        │ 发布 CASE_EVALUATION_COMPLETED
 ┌────────┴─────────┐   ┌─────────┴───────────┐   ┌────────┴──────────┐
 │ task_service:5001│   │ api_test_service    │   │ evaluation_service│
 │ (调度中枢)        │   │ :5003 ×2(replicas)  │   │ :5004             │
 │ ExecutionEngine  │   │ 执行器(BaseExecutor) │   │ EvaluateCase/     │
 │ 五 Mixin:        │   │ APIConcurrencyMgr   │   │ Reevaluate 系列   │
 │ Scheduler/Progress│  │ Adapter 体系:       │   └────────▲──────────┘
 │ /TaskControl/    │   │  HttpAPI/HttpStream │            │ gRPC 评估提交
 │ CaseExecution/   │   │  /RealtimeAPI       │            │ (EvaluateCase)
 │ TaskRunner       │   │ WS 会话实例内闭环    │            │
 └───┬──────────┬───┘   └─────────────────────┘            │
     │ gRPC     │ gRPC                                     │
     │ StartE2ETest │ StartAPITest                         │
     │ (device_type 随请求下发)                            │
 ┌───▼──────────┐                                            │
 │ e2e_test_    │───────────── gRPC 结果提交 ─────────────────┘
 │ service:5002 │  （physical 执行器 BaseExecutor，
 │ ExecutionService│   DistributedLock: lock:task:physical:{device_id}）
 └──────────────┘
```

> **关键变更**：v3.0 起，V9.7.31 中 task_service 的 ExecutionEngine 按 `TaskCase.device_type` 经 gRPC 分发到对等的两个执行服务（e2e_test_service / api_test_service），**不再有 APIExecutor 作为中间编排层，也不再进程内直接执行用例**；跨服务协同（队列、锁、信号量、心跳、事件）统一收敛到 Redis，不引入 MQ。
