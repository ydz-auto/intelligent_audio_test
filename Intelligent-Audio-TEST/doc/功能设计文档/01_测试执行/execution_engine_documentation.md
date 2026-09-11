# 执行引擎 (Execution Engine) 工作原理文档

> 版本：v3.0 | 更新日期：2026-09-10 | 变更说明：按被测设备类型(device_type)路由，废弃 task.type；新增 RealtimeSessionExecutor 和 API adapter 体系

## 1. 概述

执行引擎是测试自动化系统的核心组件，负责协调和执行各种类型的测试任务，包括API测试和端到端测试。它采用单例模式设计，确保整个系统中只有一个执行引擎实例，便于集中管理和控制所有测试任务。

执行引擎通过多线程和异步机制实现高效的测试执行，支持并发执行多个测试用例，同时保持良好的资源管理和任务控制能力。

## 2. 核心架构

### 2.1 单例设计

执行引擎使用线程安全的单例模式实现，确保在多线程环境下只有一个实例：

```python
class ExecutionEngine:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(ExecutionEngine, cls).__new__(cls)
                # 初始化工作线程、停止标志和暂停标志
                cls._instance.workers = {}
                cls._instance.stop_flags = {}
                cls._instance.pause_flags = {}
                cls._instance.thread_pools = {}
                # 东八区时区定义，用于统一时间格式
                cls._instance.utc_plus_8 = timezone(timedelta(hours=8))
                # 初始化执行器和管理器
                cls._instance.load_balancer = LoadBalancer()  # 负载均衡器，用于选择最佳API端点
                cls._instance.event_manager = EventManager(cls._instance)  # 事件管理器，用于处理事件通知
                # v3.0: ExecutionEngine 自身按 device_type 路由分发，不再需要 APIExecutor 作为编排层
                cls._instance.e2e_executor = E2EExecutor(cls._instance)  # E2E测试执行器，用于执行物理设备(device_type='physical')测试
                cls._instance.api_session_executor = APISessionExecutor(cls._instance)  # HTTP API测试执行器，用于执行 device_type='http_api' 测试
                cls._instance.realtime_executor = RealtimeSessionExecutor(cls._instance)  # Realtime测试执行器，用于执行 device_type='websocket_api' 测试
                
                # API入口状态管理
                cls._instance.api_entry_status = {}  # 存储 API 入口 (Master) 的状态: {url: {'available': True, 'fail_count': 0}}
                cls._instance.api_entry_lock = threading.Lock()  # API入口状态锁
                
                # 调度器相关初始化
                cls._instance.scheduler_thread = None
                cls._instance.scheduler_stop_event = None
                cls._instance._scheduler_initialized = False
                cls._instance.scheduler_app = None
                
                # 任务队列管理
                cls._instance.task_queue = []  # 任务队列，存储待执行的任务
                cls._instance.queue_lock = threading.Lock()  # 队列锁，确保线程安全
                cls._instance.running_tasks = {}  # 运行中任务，{task_id: device_type}
                
                # 进度更新优化
                cls._instance.task_progress_cache = {}  # 任务进度缓存
                cls._instance.last_progress_update = {}  # 上次进度更新时间
        return cls._instance
```

### 2.2 核心组件

| 组件 | 描述 |
|------|------|
| workers | 存储正在运行的任务线程 |
| stop_flags | 存储任务停止事件 |
| pause_flags | 存储任务暂停事件 |
| thread_pools | 存储 API/Realtime 测试的线程池执行器 |
| task_queue | 存储待执行的任务队列 |
| queue_lock | 确保任务队列线程安全的锁 |
| running_tasks | 存储当前运行中的任务，{task_id: device_type} |
| api_entry_status | 存储API入口(Master)的状态，用于健康检查和故障转移 |
| api_entry_lock | API入口状态更新的线程锁 |
| scheduler_thread | 后台调度器线程，用于自动检查和启动pending任务 |
| scheduler_stop_event | 调度器停止事件 |
| scheduler_app | 调度器使用的Flask应用实例 |
| task_progress_cache | 任务进度缓存，减少数据库查询 |
| last_progress_update | 上次进度更新时间，用于节流控制 |
| load_balancer | 负载均衡器，用于选择最佳API端点 |
| event_manager | 事件管理器，用于处理事件通知和进度推送 |
| e2e_executor | E2EExecutor，用于执行物理设备(device_type='physical')测试 |
| realtime_executor | RealtimeSessionExecutor，用于执行WebSocket API(device_type='websocket_api')测试 |
| api_session_executor | APISessionExecutor，用于执行HTTP API(device_type='http_api')测试 |

## 3. 任务生命周期管理

### 3.1 任务启动流程

1. **接收任务启动请求**
2. **检查任务状态**：
   - 检查任务是否已在运行
   - 检查任务是否已在队列中
3. **获取任务信息**：
   - 查询任务类型和关联的API
   - 获取任务关联的设备信息
4. **检查执行条件**（按 device_type 路由）：
   - physical（物理设备）任务：同时只允许一个物理设备任务运行
   - http_api / websocket_api 任务：支持并行执行，但相同API端点的任务不能并发执行
5. **执行或排队**：
   - 如果可以立即执行：
     - 创建停止和暂停事件
     - 更新任务状态为"running"
     - 启动任务监控线程
   - 如果需要排队：
     - 将任务加入引擎级队列
     - 更新任务状态为"queued"
6. **用例状态流转（关键，按 device_type 路由）**：
   - **pending**：用例创建后的初始状态
   - **queued**：用例已提交到线程池，但在等待 API 执行权（通过原子占用机制设置）
   - **running**：用例已获得 API 执行权，正在进行请求
   - **completed/failed**：执行结束
   - 物理设备任务由 E2EExecutor 执行，http_api 任务由 APISessionExecutor 执行，websocket_api 任务由 RealtimeSessionExecutor 执行
7. **推送进度更新**：通过 WebSocket 实时同步 UI

### 3.2 后台调度器

执行引擎内置后台调度器，自动检测并启动 `pending` 状态的任务，无需手动触发。

#### 3.2.1 调度器架构

```python
# 调度器核心组件
scheduler_thread = threading.Thread(target=self._scheduler_loop, name="TaskScheduler", daemon=True)
scheduler_stop_event = threading.Event()  # 调度器停止事件
scheduler_app = None  # 调度器使用的Flask应用实例
```

#### 3.2.2 调度规则

| device_type | 调度规则 |
|----------|----------|
| physical（物理设备） | 同时只允许一个物理设备任务运行 |
| http_api（HTTP API） | 可以并发运行，但不能使用相同的API（资源共享检查） |
| websocket_api（WebSocket API） | 可以并发运行，但不能使用相同的API（资源共享检查） |

#### 3.2.3 调度流程

```python
def _scheduler_loop(self):
    """调度器主循环，定期检查并启动 pending 任务"""
    check_interval = config_manager.get_value('execution_engine', 'scheduler_interval', 3)
    
    while not self.scheduler_stop_event.is_set():
        self._schedule_pending_tasks()  # 检查并启动pending任务
        self.scheduler_stop_event.wait(timeout=check_interval)

def _schedule_pending_tasks(self):
    """自动启动pending状态的任务"""
    # 1. 查询所有pending状态的任务
    pending_tasks = db.session.query(Task).filter_by(
        status='pending',
        deleted=False
    ).order_by(Task.created_at.asc()).all()
    
    for task in pending_tasks:
        # 2. 检查任务是否已在运行
        if task_id in self.workers and self.workers[task_id].is_alive():
            continue
        
        # 3. 检查任务是否已在队列中
        if any(t['id'] == task_id for t in self.task_queue):
            continue
        
        # 4. 检查资源冲突（按 device_type 路由）
        if device_type == 'physical':
            # 物理设备任务：同时只允许一个运行
            if not any(dt == 'physical' for dt in self.running_tasks.values()):
                can_run = True
        elif device_type in ('http_api', 'websocket_api'):
            # HTTP/WebSocket API任务：相同API不能并发运行
            overlapping_apis = set(api_ids) & self.running_apis
            if not overlapping_apis:
                can_run = True
        
        # 5. 启动任务
        if can_run:
            self.start_task(app, task_id)
```

#### 3.2.4 调度器配置

| 配置项 | 默认值 | 描述 |
|--------|--------|------|
| scheduler_interval | 3秒 | 调度器检查间隔 |
| 自动启动 | - | 无需手动调用，启动应用后自动运行 |

### 3.2 任务队列与并发控制

执行引擎实现了两层并发控制机制：

1. **引擎级队列**：
   - 管理整个系统的任务提交顺序。
   - E2E 任务互斥执行。
   - API 任务根据 API 冲突检查决定是否可立即启动。
   - 调度器定期检查队列，自动启动可以执行的任务。

2. **API 级执行队列**：
   - 在 `APISessionExecutor` 和 `RealtimeSessionExecutor` 中各自为每个 API 实例维护一个 `queue.Queue`。
   - 解决 `Condition` 变量在并发环境下可能导致的任务串行化问题。
   - 任务通过 `q.put()` 申请执行权，释放时通过 `q.get()` 唤醒后续任务。
   - 使用 `api_waiting_counts` 统计等待中的任务数，用于进度监控。

#### 3.2.1 API级并发控制机制

```python
# APISessionExecutor / RealtimeSessionExecutor 各自维护 API 级并发控制
class APISessionExecutor:  # RealtimeSessionExecutor 同理
    def __init__(self):
        self.api_queues = {}      # API ID到排队队列的映射 {api_id: queue.Queue}
        self.api_waiting_counts = {}  # API ID到等待计数的映射 {api_id: int}
        self.global_lock = Lock()  # 全局锁，用于保护共享资源的初始化
    
    def acquire_api_execution_right(self, api_id, task_id, tc_rel_id, max_process=5):
        """获取API执行权"""
        q = self._get_or_create_api_queue(api_id, max_process)
        waiting_now = self._inc_waiting(api_id)
        
        # 尝试获取执行权，满则等待
        q.put(task_id, timeout=self.max_wait_time)
        self._dec_waiting(api_id)
        return True
    
    def release_api_execution_right(self, api_id, task_id):
        """释放API执行权"""
        if api_id in self.api_queues:
            q = self.api_queues[api_id]
            q.get_nowait()  # 释放一个槽位
```

#### 3.2.2 原子占用机制

为避免主循环在工作线程更新状态前重复提交同一用例，采用原子占用机制：

```python
# 主循环中原子占用用例
claimed = local_db_session.query(TaskCase).filter(
    TaskCase.id == tc_rel_id,
    TaskCase.task_id == task_id,
    TaskCase.execution_status == 'pending'
).update({
    TaskCase.execution_status: 'queued',  # 原子占用为排队状态
    TaskCase.status: 'running'
})
if claimed != 1:
    continue  # 已被其他线程占用，跳过
local_db_session.commit()
```

### 3.3 任务监控与日志优化

监控循环负责统计任务进度并处理超时：

- **细粒度统计**：监控日志现在包含以下精确计数：
  - 排队中 (queued)：从 `api_waiting_counts` 统计等待API执行权的任务数
  - 执行中 (running)：`execution_status='running'` 的用例数
  - 评估中 (evaluation)：`evaluation_status` 为 `running/queued/pending` 的用例数
  - 执行成功：`execution_status='completed'` 的用例数
  - 评估成功：`evaluation_status='completed'` 的用例数
  - 执行失败：`execution_status='failed'` 的用例数
  - 评估失败：`evaluation_status='failed'` 的用例数

- **日志去重**：仅在统计计数发生变化或超过 10 秒时才输出 `INFO` 级别的状态日志，减少日志冗余。

- **状态同步**：将节流（Throttle）间隔从 0.5s 优化为 0.1s，并引入 `force=True` 机制确保关键状态切换不被丢弃。

- **进度缓存**：使用 `task_progress_cache` 缓存进度数据，减少数据库查询。

#### 3.3.1 等待循环统计示例

```python
# 统计各类用例数量
queued_cases = sum(self.api_session_executor.api_waiting_counts.values()) + sum(self.realtime_executor.api_waiting_counts.values())
execution_running_cases = db.query(TaskCase).filter_by(
    task_id=task_id, execution_status='running'
).count()
evaluation_running_cases = db.query(TaskCase).filter(
    TaskCase.task_id == task_id,
    TaskCase.evaluation_status.in_(['running', 'queued', 'pending'])
).count()
execution_success_cases = db.query(TaskCase).filter_by(
    task_id=task_id, execution_status='completed'
).count()
evaluation_success_cases = db.query(TaskCase).filter_by(
    task_id=task_id, evaluation_status='completed'
).count()
```

#### 3.3.2 进度更新节流

```python
def _emit_progress(self, task, force=False):
    # 强制更新条件：任务状态为 running/completed/failed/stopped/paused
    if task_status in ['running', 'completed', 'failed', 'stopped', 'paused']:
        force = True
    else:
        # 节流控制：0.1秒内不重复更新
        current_time = time.time()
        if current_time - last_update < 0.1:
            return
```

### 3.4 任务控制

执行引擎支持三种任务控制操作：

| 操作 | 描述 |
|------|------|
| pause | 暂停任务执行，API任务不重置执行中用例状态，E2E任务可选择重置 |
| resume | 恢复任务执行，从暂停点继续执行 |
| stop | 停止任务执行，从队列中移除任务并清理资源 |

#### 3.4.1 暂停/恢复机制

```python
# 暂停任务核心代码
elif action == 'pause':
    # 清除暂停标志，触发暂停
    self.pause_flags[task_id].clear()
    task.status = 'paused'
    
    # 对于HTTP/WebSocket API任务，不重置执行中的用例状态为pending
    # 因为API线程是在pause_event上阻塞，恢复时会自动继续执行
    # 如果重置为pending，会导致调度器重新启动新线程，造成重复执行
    if device_type == 'physical':
        running_cases = local_db_session.query(TaskCase).filter_by(
            task_id=task_id, execution_status='running'
        ).all()
        for tc in running_cases:
            tc.execution_status = 'pending'
            tc.completed_at = None
            tc.duration = None
    
    local_db_session.commit()
    audio_service.stop_task_audio(task_id)
    self._emit_progress(task)

# 恢复任务核心代码
elif action == 'resume':
    # 设置暂停标志，恢复执行
    self.pause_flags[task_id].set()
    task.status = 'running'
    local_db_session.commit()
    self._emit_progress(task)
```

#### 3.4.2 停止机制

```python
# 停止任务核心代码
elif action == 'stop':
    # 先从队列中移除任务
    with self.queue_lock:
        for i, queued_task in enumerate(self.task_queue):
            if queued_task['id'] == task_id:
                self.task_queue.pop(i)
                break
    
    # 更新任务状态为stopped
    task.status = 'stopped'
    task.completed_at = datetime.now(self.utc_plus_8)
    
    # 将所有用例标记为skipped
    cases = local_db_session.query(TaskCase).filter_by(task_id=task_id).all()
    for tc in cases:
        tc.status = 'skipped'
        tc.execution_status = 'stopped'
        tc.evaluation_status = 'stopped'
        tc.started_at = None
        tc.completed_at = datetime.now(self.utc_plus_8)
        tc.duration = None
        tc.error_message = '任务被手动停止'
    
    local_db_session.commit()
    audio_service.stop_task_audio(task_id)
    
    # 设置停止标志
    if task_id in self.workers:
        self.stop_flags[task_id].set()
        self.pause_flags[task_id].set()
```

#### 3.4.3 暂停的队列任务处理

对于暂停时处于 `queued` 状态的任务，恢复时有特殊处理：

```python
if action == 'resume' and task_id not in self.workers:
    if device_type in ('http_api', 'websocket_api'):
        # 将暂停的队列任务重新加入队列
        with self.queue_lock:
            self.task_queue.append({
                "id": task.id,
                "device_type": device_type,
                "api_ids": api_ids,
                "app": app
            })
        task.status = 'queued'
        local_db_session.commit()
        self._emit_progress(task)
        return True
```

### 3.5 任务执行流程

```python
# 任务执行核心循环
while not stop_event.is_set():
    # 获取下一个待执行的测试用例
    tc_rel = local_db_session.query(TaskCase).filter_by(
        task_id=task_id, 
        execution_status='pending'
    ).order_by(TaskCase.created_at.asc()).first()

    if not tc_rel:
        # 所有测试用例执行完成，退出循环
        break 
    
    # 检查是否需要暂停
    if not pause_event.is_set():
        self._emit_progress(task_id)
        pause_event.wait()  # 等待暂停标志被设置（恢复执行）

    # 检查是否需要停止
    if stop_event.is_set():
        break

    # 设备状态检查
    device_check_passed = True
    error_message = ""
    
    # 检查被测设备状态（仅物理设备任务，device_type == 'physical'）
    # ...
    
    # 检查播放设备状态（仅物理设备测试，device_type == 'physical'）
    # ...
    
    # 设备检查失败处理
    if not device_check_passed:
        tc_rel.status = 'failed'
        tc_rel.execution_status = 'failed'
        tc_rel.completed_at = datetime.now(self.utc_plus_8)
        tc_rel.duration = 0
        tc_rel.error_message = error_message
        local_db_session.commit()
        self._emit_alert(task_id, error_message)
        self._emit_progress(task)
        continue

    # 原子占用用例，避免主循环在工作线程更新状态前重复提交同一用例
    claimed = local_db_session.query(TaskCase).filter(
        TaskCase.id == tc_rel_id,
        TaskCase.task_id == task_id,
        TaskCase.execution_status == 'pending'
    ).update({
        TaskCase.execution_status: 'queued',  # 原子占用为排队状态
        TaskCase.status: 'running'
    })
    if claimed != 1:
        local_db_session.rollback()
        continue
    local_db_session.commit()

    # 根据 device_type 路由分发执行（ExecutionEngine 直接路由，无中间编排层）
    if device_type == 'physical':
        # 物理设备任务：由 E2EExecutor 直接同步执行
        success = self.e2e_executor.execute_case(task_id, tc_rel.id)
    elif device_type == 'websocket_api':
        # WebSocket API任务：提交到线程池，由 RealtimeSessionExecutor 执行
        self.thread_pools[task_id].submit(
            self.realtime_executor.execute_case, app, task_id, tc_rel_id
        )
    elif device_type == 'http_api':
        # HTTP API任务：提交到线程池，由 APISessionExecutor 执行
        self.thread_pools[task_id].submit(
            self.api_session_executor.execute_case, app, task_id, tc_rel_id
        )
    # 状态更新：主线程已将 pending 原子占用为 queued，
    # 工作线程再将 queued → running → completed/failed
        
    # 更新任务统计信息
    # ...

# HTTP/WebSocket API任务：等待所有测试用例执行完成
if device_type in ('http_api', 'websocket_api') and task_id in self.thread_pools:
    self.thread_pools[task_id].shutdown(wait=True)  # 关闭线程池，等待所有任务完成
    del self.thread_pools[task_id]  # 从字典中移除
    
    # 等待所有测试用例的状态都不是running或queued
    # 包括执行中、排队中、评估中/待评估的用例
    while True:
        running_cases = local_db_session.query(TaskCase).filter(
            TaskCase.task_id == task_id,
            (TaskCase.execution_status.in_(['running', 'queued'])) | 
            (TaskCase.evaluation_status.in_(['running', 'queued', 'pending']))
        ).count()
        if running_cases == 0:
            break
        time.sleep(1)

# 更新任务状态
if stop_event.is_set():
    task.status = 'stopped'
else:
    # 根据执行结果更新任务状态
    # ...
```

## 4. 任务并发同步机制

### 4.1 并发控制策略

| 任务类型 | 并发策略 | 详细说明 |
|----------|----------|----------|
| 物理设备任务 | 串行执行 | 同时只允许一个物理设备任务运行，确保系统资源集中 |
| HTTP/WebSocket API任务 | 并行执行 | 支持多个API任务并行执行，但相同API的任务串行执行，避免API过载 |
| 测试用例 | 并行执行 | API测试用例通过线程池并行执行，物理设备测试用例串行执行 |

### 4.2 线程安全机制

1. **锁机制**：
   - 使用`threading.Lock()`确保队列操作的线程安全
   - 使用`threading.Lock()`确保单例模式的线程安全

2. **事件机制**：
   - 使用`threading.Event()`实现任务暂停/恢复
   - 使用`threading.Event()`实现任务停止通知

3. **资源隔离**：
   - 每个API任务使用独立的线程池
   - 任务间通过事件和锁进行通信，避免直接共享状态

### 4.3 API/Realtime测试并发执行

API/Realtime测试采用线程池实现高效并发，通过 adapter 体系适配不同协议（HTTP、WebSocket、流式HTTP）：

1. **线程池配置**：
   - 根据可用API端点计算最大工作线程数
   - 每个可用端点贡献其max_process配置
   - 默认值为5

2. **线程池管理**：
   - 任务开始时创建线程池
   - 任务完成时关闭线程池并等待所有任务完成
   - 支持动态调整线程池大小

3. **Adapter 体系**：
   - `HttpAPIAdapter`：标准 HTTP API 测试适配器
   - `HttpStreamAdapter`：流式 HTTP API 测试适配器
   - `RealtimeAPIAdapter`：WebSocket API 测试适配器
   - 执行器不再直接管理 HTTP 调用，而是委托给 adapter

4. **等待机制**：
   - 任务完成后等待所有测试用例执行完成
   - 支持超时机制（默认5分钟）
   - 定期检查测试用例状态

## 5. 设备状态管理

### 5.1 设备状态检查

在每个测试用例执行前，执行引擎会检查设备状态：

1. **被测设备检查**：
   - 检查所有关联设备是否在线
   - 如果设备离线，标记用例为failed并跳过

2. **播放设备检查**（仅E2E测试）：
   - 检查测试用例中配置的播放设备
   - 确保播放设备状态正常
   - 如果播放设备异常，标记用例为failed并跳过

### 5.2 设备状态处理

1. **设备离线处理**：
   - 记录详细错误日志
   - 发送告警通知
   - 标记测试用例为failed
   - 继续执行其他测试用例

2. **设备恢复处理**：
   - 在下一个测试用例执行时重新检查设备状态
   - 设备恢复在线后自动继续执行

## 6. 错误处理和容错机制

### 6.1 异常捕获和处理

执行引擎实现了完善的异常捕获机制：

1. **全局异常捕获**：在任务执行线程中捕获所有异常
2. **详细错误日志**：记录完整的错误信息和堆栈跟踪
3. **状态恢复**：
   - 更新任务状态为failed
   - 将所有正在执行的测试用例标记为failed
   - 记录错误信息和执行时长
4. **告警推送**：通过WebSocket推送错误告警

### 6.2 容错机制

1. **设备容错**：
   - 设备离线时跳过当前用例，继续执行其他用例
   - 支持动态设备恢复检测

2. **API容错**：
   - 自动选择最佳API端点
   - 支持API端点健康状态动态调整
   - API执行失败时标记用例为failed，继续执行其他用例

3. **资源容错**：
   - 线程池异常时优雅处理
   - 数据库连接异常时重试机制

### 6.3 重试机制

虽然执行引擎没有实现显式的重试机制，但通过以下方式实现了类似的效果：

1. **暂停/恢复机制**：支持手动暂停和恢复任务，相当于手动重试
2. **设备状态检查**：设备恢复在线后自动继续执行，相当于设备级别的重试
3. **用例状态管理**：暂停后重置用例状态为pending，恢复时重新执行，相当于用例级别的重试

## 7. API测试执行流程

### 7.1 概述

API测试用于验证语音识别和翻译API的性能和准确性。执行引擎会根据API配置和测试用例，自动选择最优的API端点，并执行测试请求。

v3.0 起，执行器不再直接管理 HTTP 调用，而是通过 **adapter 体系** 委托给适配器：

| 适配器 | 适用场景 | 协议 |
|--------|----------|------|
| `BaseAPIAdapter` | 抽象基类，定义统一接口 | - |
| `HttpAPIAdapter` | 标准 HTTP API 测试 | HTTP |
| `HttpStreamAdapter` | 流式 HTTP API 测试 | HTTP (chunked) |
| `RealtimeAPIAdapter` | WebSocket API 测试 | WebSocket |

### 7.2 执行步骤

#### 7.2.1 任务初始化

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
   - 创建ThreadPoolExecutor实例
   - 记录初始化日志

4. **Adapter 选择**：
   - 根据 device_type 选择对应的 adapter
   - `http_api` → `HttpAPIAdapter` 或 `HttpStreamAdapter`
   - `websocket_api` → `RealtimeAPIAdapter`
   - 通过 `api_adapter_factory` 工厂创建适配器实例

#### 7.2.2 用例执行循环

1. **获取待执行用例**：
   - 从数据库中查询状态为"pending"的测试用例
   - 按照创建时间排序
   - 取出第一个待执行用例

2. **原子占用用例**：
   - 主循环将 `execution_status='pending'` 的用例原子更新为 `'queued'`
   - 避免多线程重复提交同一用例

3. **设备状态检查**：
   - 检查所有关联设备的状态
   - 确保设备都处于"online"状态
   - 如果设备离线，标记用例为"failed"并跳过

4. **提交用例到线程池**：
   - 将用例提交到线程池执行
   - 状态由工作线程管理：`queued → running → completed/failed`
   - 工作线程调用 adapter 的方法完成实际请求

#### 7.2.3 API级并发控制

```python
def execute_api_case(self, app, task_id, tc_rel_id):
    # 1. 原子更新用例状态为 running
    claimed = db.session.query(TaskCase).filter(
        TaskCase.id == tc_rel_id,
        TaskCase.execution_status.in_(['pending', 'queued'])
    ).update({
        TaskCase.execution_status: 'running'
    })
    
    # 2. 获取API执行权（APISessionExecutor 内部的 API 级并发控制）
    if not self.acquire_api_execution_right(api_id, task_id, tc_rel_id, max_process):
        return False
    
    try:
        # 3. 通过 adapter 执行 API 测试（执行器不再直接管理 HTTP 调用）
        adapter = self.api_adapter_factory.create(device_type, api_config)
        adapter.initialize()
        adapter.send(payload)
        result = adapter.recv()
        adapter.post_process()
        output = adapter.output  # 获取统一输出
    finally:
        # 4. 释放API执行权
        self.release_api_execution_right(api_id, task_id)
        adapter.teardown()
```

#### 7.2.4 状态流转（关键）

```
tc_rel.execution_status: pending → queued → running → completed/failed
tc_rel.evaluation_status:       pending    → queued → running → completed/failed
tc_rel.status:                  pending                    → passed/failed
```

| 阶段 | execution_status | evaluation_status | status |
|------|------------------|-------------------|--------|
| 用例创建 | pending | - | pending |
| 主循环原子占用 | queued | - | running |
| 工作线程开始执行 | running | pending | running |
| API调用成功 | completed | queued | running |
| 评估完成 | completed | completed | passed |
| API调用失败 | failed | failed | failed |
| 任务停止 | stopped | stopped | skipped |

## 7.5 Realtime API测试执行流程

### 7.5.1 概述

Realtime API 测试用于验证基于 WebSocket 协议的实时语音识别和翻译 API。由 `RealtimeSessionExecutor` 驱动，通过 `RealtimeAPIAdapter` 适配器完成 WebSocket 连接、音频分片流式发送和事件驱动的结果接收。

### 7.5.2 执行步骤

1. **初始化 Adapter**：
   - `adapter.initialize()` 建立 WebSocket 连接
   - 启动独立的接收线程，监听服务端推送的事件

2. **音频分片流式发送**（每个测试轮次）：
   - 通过 `AudioStreamOrchestrator.chunk_audio()` 将音频切分为固定大小的分片
   - 逐个调用 `adapter.send(chunk)` 发送音频分片
   - 所有分片发送完毕后调用 `adapter.commit_input()` 通知服务端输入结束
   - 调用 `adapter.post_process()` 执行后处理（如等待最终结果）
   - 从 `adapter.output` 获取最终识别/翻译结果

3. **事件驱动接收**：
   - 接收线程持续监听 WebSocket 消息
   - 收到结果事件后写入 adapter 的输出缓冲区
   - 主线程从输出缓冲区获取最终结果

```python
# Realtime API 执行流程示例
adapter = self.api_adapter_factory.create('websocket_api', api_config)
adapter.initialize()  # 建立 WebSocket 连接 + 启动接收线程

for round in test_rounds:
    chunks = AudioStreamOrchestrator.chunk_audio(audio_data)
    for chunk in chunks:
        adapter.send(chunk)          # 逐片发送音频
    adapter.commit_input()           # 通知输入结束
    adapter.post_process()           # 后处理
    result = adapter.output          # 获取最终结果
    # 评估结果...
```

## 8. 端到端测试执行流程

### 8.1 概述

端到端测试用于验证完整的语音识别和翻译流程，包括音频播放、设备唤醒、语音采集和结果返回。

> **注意**：v3.0 起，端到端测试由 `device_type='physical'` 决定，不再使用 `task.type`。

### 8.2 执行步骤

#### 8.2.1 用例执行循环

1. **获取待执行用例**：
   - 从数据库中查询状态为"pending"的测试用例
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
   - 结果评估（同步）

#### 8.2.2 状态管理

```python
def _update_tc_rel_status(self, tc_rel_id, **kwargs):
    """更新TaskCase状态"""
    tc_rel = db.session.query(TaskCase).get(tc_rel_id)
    if tc_rel:
        for key, value in kwargs.items():
            setattr(tc_rel, key, value)
        
        if 'execution_status' in kwargs:
            if kwargs['execution_status'] == 'running':
                tc_rel.started_at = datetime.now(self.utc_plus_8)
                tc_rel.evaluation_status = 'queued'  # 设置评估状态为排队
            elif kwargs['execution_status'] in ['completed', 'failed']:
                tc_rel.completed_at = datetime.now(self.utc_plus_8)
        
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
| 开始执行 | running | queued | running |
| 执行成功 | completed | - | running |
| 提交评估 | - | queued | running |
| 评估开始 | - | running | running |
| 评估完成 | completed | completed | passed/completed |
| 执行失败 | failed | failed | failed |

#### 8.2.4 评估状态保护

在E2E执行器中，评估状态的更新会避免覆盖已开始的评估状态：

```python
# 只有当评估状态不是 running 时，才设置为 queued
if tc_rel.evaluation_status != 'running':
    tc_rel.evaluation_status = 'queued'
```

这确保了多个设备结果并行采集时，只有第一个提交评估的任务设置评估状态为 `running`，后续的评估任务不会覆盖该状态。

## 9. 实时进度推送

执行引擎通过WebSocket实时推送任务执行进度，包括：

- 任务总进度
- 当前执行的用例
- 所有测试用例的状态
- 最近的日志信息

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

## 10. 错误处理和日志记录

执行引擎实现了完善的错误处理机制：

1. **异常捕获**：在关键执行点捕获异常，确保任务不会崩溃
2. **错误日志**：记录详细的错误信息和堆栈跟踪
3. **告警推送**：通过WebSocket推送错误告警
4. **状态恢复**：在发生错误时，确保任务状态正确更新
5. **设备告警**：设备离线时发送告警通知
6. **API入口健康状态管理**：自动跟踪API入口可用性

### 10.1 API入口健康状态

```python
def _update_endpoint_health(self, endpoint_url, available):
    """更新API入口(Master)的可用性状态"""
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
            self._log(level='WARNING' if not available else 'INFO', 
                     content=f"API入口状态变更: {endpoint_url} -> {status_str}")
```

### 10.2 异常处理流程

```python
try:
    # 执行测试用例（按 device_type 路由到对应 executor）
    if device_type == 'physical':
        result = self.e2e_executor.execute_case(app, task_id, tc_rel_id)
    elif device_type == 'websocket_api':
        result = self.realtime_executor.execute_case(app, task_id, tc_rel_id)
    else:
        result = self.api_session_executor.execute_case(app, task_id, tc_rel_id)
except Exception as e:
    # 捕获所有异常
    error_msg = f"API 执行异常: {str(e)}"
    
    # 更新测试用例状态为失败
    local_db_session = db.session()
    try:
        tc_rel = local_db_session.query(TaskCase).get(tc_rel_id)
        if tc_rel:
            tc_rel.status = 'failed'
            tc_rel.execution_status = 'failed'
            tc_rel.completed_at = datetime.now(self.utc_plus_8)
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
            self._emit_progress(task)
    finally:
        local_db_session.close()
```

## 11. 与其他组件的交互

执行引擎与多个核心服务交互，形成完整的测试生态系统：

| 服务 | 用途 |
|------|------|
| audio_service | 音频播放和控制 |
| spl_service | SPL值到增益的转换 |
| evaluation_service | 测试结果评估 |
| load_balancer | 最佳API端点选择 |
| event_manager | 事件通知和进度推送 |
| e2e_executor | E2E测试执行（物理设备测试，device_type='physical'） |
| api_session_executor | HTTP API测试执行（APISessionExecutor，device_type='http_api'） |
| realtime_executor | WebSocket API测试执行（RealtimeSessionExecutor，device_type='websocket_api'） |
| api_adapter_factory | API适配器工厂，创建 HttpAPIAdapter/HttpStreamAdapter/RealtimeAPIAdapter |
| audio_stream_orchestrator | 混音切片，将音频切分为固定大小分片供 Realtime API 流式发送 |

## 12. 性能优化

1. **线程池复用**：API测试使用线程池复用线程资源
2. **并行处理**：
   - 设备唤醒并行执行
   - 结果采集并行执行
   - API测试用例并行执行
3. **动态端点选择**：根据健康状态和优先级选择最优API端点
4. **高效队列管理**：自动检查队列并启动下一个任务
5. **资源清理**：任务完成后及时清理资源
6. **进度更新节流**：0.1秒内不重复更新，减少WebSocket消息
7. **进度缓存**：使用task_progress_cache减少数据库查询
8. **原子状态更新**：避免多线程重复提交同一用例
9. **API级并发控制**：使用有界队列控制每个API的并发数
10. **后台自动调度**：无需手动触发任务启动

## 14. 代码示例

### 14.1 启动任务

```python
engine = ExecutionEngine()
success, message = engine.start_task(app, task_id)
```

### 14.2 控制任务

```python
engine = ExecutionEngine()
# 暂停任务
success, message = engine.control_task(app, task_id, 'pause')
# 恢复任务
success, message = engine.control_task(app, task_id, 'resume')
# 停止任务
success, message = engine.control_task(app, task_id, 'stop')
```

## 15. 总结

执行引擎是测试自动化系统的核心，负责协调和执行各种类型的测试任务。v3.0 起，执行引擎按被测设备类型（device_type）路由，支持三种执行模式：E2E（物理设备）、HTTP API、WebSocket Realtime API。通过完善的任务生命周期管理、并发控制机制和实时进度推送，确保测试任务高效、可靠地执行。

执行引擎的主要特点包括：

1. **完善的任务队列管理**：支持任务排队、自动启动和动态调整
2. **灵活的任务控制**：支持暂停、恢复和停止操作
3. **高效的并发执行**：采用线程池实现API测试用例并行执行
4. **可靠的设备状态管理**：自动检查设备状态，确保测试可靠性
5. **完善的错误处理**：异常捕获、错误日志和告警推送
6. **实时进度推送**：通过WebSocket实时推送任务执行进度
7. **三种执行模式**：E2E（physical）/ HTTP API（http_api）/ Realtime API（websocket_api），由 device_type 路由决定
8. **后台自动调度**：内置调度器自动检测和启动pending任务
9. **API入口健康状态管理**：自动跟踪API Master节点可用性
10. **细粒度状态监控**：精确统计排队中、执行中、评估中等各状态用例数
11. **原子状态更新**：避免多线程重复提交同一用例
12. **Adapter 体系**：执行器通过 BaseAPIAdapter/HttpAPIAdapter/HttpStreamAdapter/RealtimeAPIAdapter 适配不同协议，不再直接管理 HTTP 调用

执行引擎与其他核心服务紧密协作，形成完整的测试生态系统，为语音识别和翻译系统的质量保障提供了有力支持。

### 15.1 核心组件交互图

```
                    ┌─────────────────┐
                    │   Flask App     │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │ ExecutionEngine │◄── 单例模式
                    │ (核心调度+路由)  │
                    └────────┬────────┘
              ┌──────────────┼──────────────┐──────────────┐
              │              │              │              │
       ┌──────▼──────┐ ┌─────▼─────┐ ┌──────▼──────┐ ┌─────▼──────┐
       │E2EExecutor  │ │APISession │ │Realtime    │ │EventManager│
       │(physical)   │ │Executor   │ │Session     │ │(事件推送)   │
       │             │ │(http_api) │ │Executor    │ └────────────┘
       └──────┬──────┘ └─────┬─────┘ │(websocket_ │
              │              │         │ api)       │
              │              │         └──────┬─────┘
              │              │                │
       ┌──────▼──────┐      │        ┌───────▼───────┐
       │device_driver│      │        │api_adapter_   │
       │(ADB/HDC)    │      │        │factory        │
       │SPLMapping   │      │        └───────┬───────┘
       └─────────────┘      │                │
                             │        ┌───────▼───────┐
                     ┌───────▼──────┐ │AudioStream   │
                     │api_adapter_  │ │Orchestrator  │
                     │factory       │ │(混音切片)    │
                     └───────┬──────┘ └───────────────┘
                             │
                     ┌───────▼───────┐
                     │HttpAPIAdapter│
                     │HttpStreamAdp │
                     │(非实时/流式)   │
                     └───────────────┘

              ┌───────▼───────┐
              │   调度器      │
              │ (后台自动调度) │
              └───────────────┘
```

> **关键变更**：v3.0 起，`ExecutionEngine` 自身按 `device_type` 路由分发到三个对等执行器（E2EExecutor / APISessionExecutor / RealtimeSessionExecutor），**不再有 APIExecutor 作为中间编排层**。