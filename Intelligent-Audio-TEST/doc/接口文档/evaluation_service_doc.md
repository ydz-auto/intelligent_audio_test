# EvaluationService 文档

## 1. 文件概述

`evaluation_service.py` 是一个用于评估测试用例各种维度的服务类，主要功能是根据配置调用外部 API 进行打分评估，并将结果持久化到数据库中。

**架构特点**：采用多端点 Worker 并行架构，每个评估 API 端点拥有独立的任务队列和 Worker 线程，实现真正意义上的并行评估，避免单个端点的慢任务阻塞其他端点的评估。

## 2. 核心架构

### 2.1 架构演进

| 版本 | 架构特点 | 问题 |
|------|----------|------|
| 旧版 | 单全局队列 + 单 Worker 串行处理 | 端点间互相阻塞，一个慢端点拖慢所有评估 |
| 新版 | 多端点独立队列 + 多 Worker 并行处理 | 无阻塞，不同端点完全并行执行 |

### 2.2 新架构类图

```python
class EndpointWorker:
    """端点 Worker 类，每个端点一个独立 Worker"""
    def __init__(self, endpoint_url, eval_service, max_timeout=30):
        self.endpoint_url = endpoint_url          # 端点 URL
        self.max_timeout = max_timeout            # 超时时间（秒）
        self.task_queue = queue.Queue()           # 独立任务队列
        self.worker_thread = None                 # 工作线程
        self.completion_events = {}               # 任务完成事件 {task_id: Event}
        self.completion_events_lock = threading.Lock()

class EvaluationService:
    """评估服务类"""
    def __init__(self):
        self.api_client = evaluationApiClient()   # API 客户端
        self.result_processor = EvaluationResultProcessor()
        self.endpoint_workers = {}                # 端点 Worker 字典
        self.endpoint_workers_lock = Lock()       # Worker 字典锁
```

### 2.3 核心组件

| 组件 | 描述 | 作用 |
|------|------|------|
| EndpointWorker | 端点工作器 | 每个端点独立的工作线程，处理该端点的评估任务 |
| task_queue | 任务队列 | EndpointWorker 内部的队列，存储待评估任务 |
| completion_events | 完成事件 | 用于通知评估完成，避免时序问题 |
| endpoint_workers | Worker 字典 | 存储所有端点的 Worker 实例 |

## 3. 类结构与主要方法

### 3.1 EndpointWorker 类

```python
class EndpointWorker:
    def __init__(self, endpoint_url, eval_service, max_timeout=30):
        """初始化端点 Worker
        
        Args:
            endpoint_url: 评估 API 端点 URL
            eval_service: 评估服务实例
            max_timeout: 最大超时时间（秒）
        """
        self.endpoint_url = endpoint_url
        self.eval_service = eval_service
        self.max_timeout = max_timeout
        self.task_queue = queue.Queue()
        self.worker_thread = None
        self.stop_event = threading.Event()
        self.completion_events = {}
        self.completion_events_lock = threading.Lock()
```

#### 3.1.1 主要方法

| 方法 | 功能 |
|------|------|
| `start()` | 启动 Worker 线程 |
| `stop()` | 停止 Worker 线程 |
| `_worker_loop()` | 工作线程主循环，从队列获取并执行任务 |
| `_execute_evaluation()` | 执行单个评估任务 |

### 3.2 EvaluationService 类

```python
class EvaluationService:
    def __init__(self):
        self.api_client = evaluationApiClient()
        self.result_processor = EvaluationResultProcessor()
        self.endpoint_workers = {}
        self.endpoint_workers_lock = Lock()
```

#### 3.2.1 主要方法

| 方法 | 功能 |
|------|------|
| `evaluate_case()` | 核心评估入口，分发任务到各端点队列 |
| `_get_or_create_worker()` | 获取或创建端点 Worker |
| `_get_timeout_from_dim_config()` | 从维度配置获取超时时间 |
| `_load_all_endpoint_configs()` | 加载数据库中的端点配置 |
| `_submit_to_endpoint_worker()` | 提交任务到端点队列 |
| `shutdown()` | 关闭所有 Worker 和线程池 |

## 4. 端点独立队列原理

### 4.1 队列隔离机制

```
┌─────────────────────────────────────────────────────────────┐
│                    EvaluationService                         │
├─────────────────────────────────────────────────────────────┤
│  endpoint_workers: {                                        │
│      "http://endpoint-A": EndpointWorker-A (队列A)          │
│      "http://endpoint-B": EndpointWorker-B (队列B)          │
│      "http://endpoint-C": EndpointWorker-C (队列C)          │
│  }                                                          │
└─────────────────────────────────────────────────────────────┘
         │                   │                   │
         ▼                   ▼                   ▼
    ┌─────────┐         ┌─────────┐         ┌─────────┐
    │ 队列 A  │         │ 队列 B  │         │ 队列 C  │
    │Worker A│         │Worker B│         │Worker C│
    └─────────┘         └─────────┘         └─────────┘
         │                   │                   │
         └───────────────────┼───────────────────┘
                             ▼
                    不同端点完全并行
```

### 4.2 解决阻塞问题的原理

**旧版问题**：
```
用例1的维度分组A → 全局队列 → Worker处理中...
用例1的维度分组B → 全局队列 → Worker处理中...（卡住）
用例2的维度分组A → 全局队列 → 等待中...（被阻塞）
```

**新版解决方案**：
```
端点A的Worker → 处理用例1的分组A... → 处理用例2的分组A...
端点B的Worker → 处理用例1的分组B...（卡住不影响A）
```

## 5. 任务执行流程

### 5.1 时序图

```
┌──────────┐   ┌──────────────────┐   ┌──────────────────┐   ┌──────────────┐
│  调用方   │   │ EvaluationService│   │ EndpointWorker  │   │  评估 API   │
└────┬─────┘   └────────┬─────────┘   └────────┬─────────┘   └──────┬───────┘
     │                  │                        │                     │
     │ evaluate_case()  │                        │                     │
     │─────────────────>│                        │                     │
     │                  │                        │                     │
     │                  │ _get_or_create_worker()│                     │
     │                  │───────────────────────>│                     │
     │                  │                        │                     │
     │                  │ 创建 completion_event  │                     │
     │                  │────────────────────────│                     │
     │                  │                        │                     │
     │                  │ submit to task_queue   │                     │
     │                  │───────────────────────>│                     │
     │                  │                        │                     │
     │                  │ completion_event.wait()│                     │
     │                  │◄───────────────────────│                     │
     │                  │ (阻塞等待)              │                     │
     │                  │                        │                     │
     │                  │                        │ _worker_loop()      │
     │                  │                        │                     │
     │                  │                        │ _execute_evaluation()
     │                  │                        │────────────────────>│
     │                  │                        │                     │
     │                  │                        │    API 响应         │
     │                  │                        │◄────────────────────│
     │                  │                        │                     │
     │                  │                        │ 更新数据库状态       │
     │                  │                        │                     │
     │                  │                        │ completion_event.set()
     │                  │◄───────────────────────│                     │
     │                  │ (唤醒)                 │                     │
     │                  │                        │                     │
     │ 返回结果         │                        │                     │
     │<─────────────────│                        │                     │
```

### 5.2 详细步骤

```python
def evaluate_case(self, task_id, result_id, test_case_id, ...):
    # 1. 从数据库加载维度配置
    dimensions = load_dimensions(test_case_id)
    
    # 2. 创建 TestResultDimension 记录（状态为 pending）
    for dim in dimensions:
        create_dimension_result(dim, result_id)
    
    # 3. 按端点分组维度
    endpoint_groups = group_by_endpoint(dimensions)
    
    # 4. 为每个端点提交任务
    completion_events = []
    for endpoint_url, group_items in endpoint_groups.items():
        worker = self._get_or_create_worker(endpoint_url, group_items[0])
        
        # 创建完成事件并注册到 Worker
        completion_event = threading.Event()
        with worker.completion_events_lock:
            worker.completion_events[task_id] = completion_event
        completion_events.append(completion_event)
        
        # 提交任务到端点队列
        worker.task_queue.put(task_data)
    
    # 5. 等待所有任务完成
    for i, completion_event in enumerate(completion_events):
        worker = list(endpoint_workers.values())[i]
        timeout = worker.max_timeout
        completion_event.wait(timeout=timeout)
    
    # 6. 检查并更新最终状态
    all_completed = self.result_processor.check_all_dimensions_completed(...)
```

## 6. 超时配置机制

### 6.1 配置来源

超时时间按以下优先级获取：

| 优先级 | 配置位置 | 配置项 | 说明 |
|--------|----------|--------|------|
| 1 | 维度配置 | `api_settings.timeout` | 维度级别的超时设置 |
| 2 | 端点配置 | `api_endpoints[0].max_timeout` | 端点级别的超时设置 |
| 3 | 默认值 | - | 默认 30 秒 |

### 6.2 配置示例

```json
{
  "id": 1,
  "name": "WER",
  "api_endpoints": [
    {
      "url": "http://localhost:5001/calculate_wer",
      "max_timeout": 60,
      "max_process": 5
    }
  ],
  "api_settings": {
    "method": "POST",
    "timeout": 45,
    "body_template": "..."
  }
}
```

### 6.3 超时处理

```python
def _get_timeout_from_dim_config(self, dim_data, default_timeout=30):
    # 1. 优先从 api_settings.timeout 获取
    api_settings = dim_data.get('api_settings', {})
    timeout = api_settings.get('timeout')
    if timeout:
        return timeout
    
    # 2. 从 api_endpoints 获取
    endpoints = dim_data.get('api_endpoints', [])
    if endpoints and isinstance(endpoints, list):
        endpoint_item = endpoints[0]
        timeout = endpoint_item.get('max_timeout') or endpoint_item.get('maxTimeout')
        if timeout:
            return timeout
    
    # 3. 使用默认值
    return default_timeout
```

## 7. 完成事件机制

### 7.1 解决的问题

在旧架构中，`evaluate_case` 提交任务后立即检查维度状态，但此时：
- 任务可能还在队列中等待
- 评估可能还在执行
- 数据库中的 `evaluation_status` 仍是 `pending`

这导致错误地判断评估失败。

### 7.2 解决方案

使用 `threading.Event` 实现真正的同步等待：

```python
# 提交任务前：创建事件
completion_event = threading.Event()
with worker.completion_events_lock:
    worker.completion_events[task_id] = completion_event

# 提交任务到队列
worker.task_queue.put(task_data)

# 等待事件（阻塞）
completion_event.wait(timeout=300)

# 任务执行完成后：设置事件
def _execute_evaluation(self, ...):
    try:
        # 执行评估...
        resp_data = self.eval_service.api_client.make_api_request_with_fallback(...)
        
        # 更新结果到数据库...
        self.eval_service.result_processor.process_group_dimension_results(...)
    finally:
        # 标记任务完成，唤醒等待方
        with self.completion_events_lock:
            if task_id in self.completion_events:
                self.completion_events[task_id].set()
                del self.completion_events[task_id]
```

## 8. 输入解析与处理

### 8.1 输入来源

`evaluate_case()` 方法的输入主要来自：
1. 方法参数（task_id, result_id, test_case_id, asr_result, translation_result, asr_ref, tran_ref）
2. 数据库查询结果（测试用例配置、维度信息）

### 8.2 维度配置解析

```python
# 从测试用例配置中提取维度 ID
test_case_config = test_case.config or {}
dimensions_config = test_case_config.get('dimensions', {})

dimension_ids = []
for dim_list in dimensions_config.values():
    for item in dim_list:
        if isinstance(item, dict):
            dimension_id = item.get('id')
            if dimension_id:
                dimension_ids.append(dimension_id)
        else:
            dimension_ids.append(item)

unique_dimension_ids = list(set(dimension_ids))
```

### 8.3 端点分组

```python
# 按 API 端点分组
endpoint_groups = {}
for dim_data in dimension_data_list:
    endpoints = dim_data.get('api_endpoints', [])
    api_url = dim_data.get('api_url')
    
    # 选择端点 URL
    if not endpoints or not isinstance(endpoints, list):
        endpoint_url = api_url
    else:
        endpoint_item = endpoints[0]
        endpoint_url = endpoint_item.get('url') or endpoint_item.get('endpoint')
        if not endpoint_url and api_url:
            endpoint_url = api_url
    
    # 添加到对应端点组
    if endpoint_url not in endpoint_groups:
        endpoint_groups[endpoint_url] = []
    endpoint_groups[endpoint_url].append((dim_data, dimension_result_id))
```

## 9. API 请求发送

API 请求发送由 `evaluation_api_client.py` 中的 `evaluationApiClient` 类处理：

```python
class evaluationApiClient:
    def make_api_request_with_fallback(self, endpoints, method, headers, payload, ...):
        """发起 API 请求，支持失败时切换到备用端点"""
        # 1. 选择端点
        selected_url = self.select_endpoint(endpoints)
        
        # 2. 获取并发槽位
        if not self.acquire_endpoint_slot(selected_url):
            return None, None
        
        try:
            # 3. 调用异步任务 API
            create_response = self.create_task(selected_url, payload)
            
            # 4. 等待任务完成
            result_response = self.wait_for_task_completion(
                selected_url, 
                api_task_id,
                max_wait_time=300
            )
            
            return selected_url, result_response
        finally:
            # 5. 释放并发槽位
            self.release_endpoint_slot(selected_url)
```

## 10. 输出解析与处理

结果处理由 `evaluation_result_processor.py` 中的 `EvaluationResultProcessor` 类负责：

| 方法 | 功能 |
|------|------|
| `process_group_dimension_results()` | 处理一组维度的评估结果 |
| `update_all_dimensions_in_group_failed()` | 更新组内所有维度为失败状态 |
| `check_all_dimensions_completed()` | 检查所有维度是否完成评估 |
| `update_task_case_status()` | 更新 TaskCase 状态 |

### 10.1 成功结果处理

```python
def process_group_dimension_results(self, resp_data, group_items, task_id, ...):
    for dim_data, dimension_result_id in group_items:
        # 解析结果并打分
        raw_value, score = self.parse_dimension_result(resp_data, dim_data)
        
        # 更新维度评估结果
        self.update_dimension_result_completed(
            dimension_result_id, 
            raw_value, 
            score, 
            task_id=task_id,
            api_raw_response=resp_data
        )
```

### 10.2 失败结果处理

```python
def update_all_dimensions_in_group_failed(self, group_items, error_message, ...):
    for dim_data, dimension_result_id in group_items:
        self.update_dimension_result_failed(
            dimension_result_id,
            error_message,
            task_id=task_id,
            api_raw_response=api_raw_response
        )
```

## 11. 评分规则

评分规则在 `Dimension` 模型的 `rule` 字段中配置：

| 规则类型 | 说明 | 配置示例 |
|----------|------|----------|
| direct | 直接映射 | `{"type": "direct"}` |
| linear | 线性插值 | `{"type": "linear", "min": 0, "max": 100, "score_min": 0, "score_max": 100}` |
| threshold | 阈值区间 | `{"type": "threshold", "thresholds": [{"val": 0.8, "score": 100}, {"val": 0.5, "score": 60}]}` |

## 12. 错误处理

### 12.1 异常捕获层级

```
┌─────────────────────────────────────────┐
│     evaluate_case (顶层捕获)             │
│  - 记录完整堆栈                          │
│  - 更新 TaskCase 状态为 failed           │
└─────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│  EndpointWorker._worker_loop (Worker层)  │
│  - 捕获单任务异常                         │
│  - 标记完成事件                           │
└─────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│  EndpointWorker._execute_evaluation      │
│  - 捕获 API 调用异常                      │
│  - 更新维度状态为 failed                   │
└─────────────────────────────────────────┘
```

### 12.2 超时处理

```python
# 等待完成事件时检查超时
for i, completion_event in enumerate(completion_events):
    endpoint_url = list(endpoint_groups.keys())[i]
    worker = self.endpoint_workers.get(endpoint_url)
    timeout = worker.max_timeout if worker else 300
    
    completed = completion_event.wait(timeout=timeout)
    if not completed:
        self._log(
            level='WARNING',
            content=f"端点任务等待超时: endpoint={endpoint_url}, timeout={timeout}秒"
        )
```

## 13. 配置示例

### 13.1 维度配置示例

```json
{
  "id": 1,
  "name": "WER",
  "api_url": "http://localhost:5001",
  "api_endpoints": [
    {
      "url": "http://localhost:5001/calculate_wer",
      "name": "WER计算器",
      "max_timeout": 60,
      "max_process": 5
    }
  ],
  "api_settings": {
    "method": "POST",
    "timeout": 45,
    "body_template": {
      "task_type": "wer",
      "dimensions": ["wer", "wer_zh", "wer_en"]
    }
  },
  "rule": {
    "type": "linear",
    "min": 0,
    "max": 100,
    "score_min": 0,
    "score_max": 100
  }
}
```

### 13.2 调用示例

```python
from backend.utils.evaluation_service import evaluation_service

# 异步调用（推荐）
evaluation_service.evaluate_case(
    task_id=1,
    result_id=1,
    test_case_id="case-001",
    asr_result="测试结果",
    translation_result="Test result",
    asr_ref="参考文本",
    tran_ref="翻译参考",
    translation_direction="zh2en"
)
```

## 14. 依赖关系

| 依赖 | 用途 |
|------|------|
| `queue` | 任务队列管理 |
| `threading` | 线程和事件机制 |
| `concurrent.futures` | 线程池管理 |
| `evaluationApiClient` | API 调用和并发控制 |
| `EvaluationResultProcessor` | 结果处理和状态更新 |
| `backend.models.models` | 数据库模型 |
| `backend.models.database` | 数据库会话 |

## 15. 总结

`EvaluationService` 采用多端点 Worker 并行架构，具有以下特点：

1. **高并发**：不同端点的评估任务完全并行执行
2. **无阻塞**：单个端点的慢任务不会影响其他端点
3. **可配置**：超时时间从数据库动态读取
4. **可靠等待**：使用完成事件机制确保任务真正完成后再更新状态
5. **易于扩展**：新增端点只需配置，无需修改代码

该服务通过独立队列和完成事件机制，解决了旧架构中的阻塞问题和时序问题，为大规模并行评估提供了可靠的基础架构。
