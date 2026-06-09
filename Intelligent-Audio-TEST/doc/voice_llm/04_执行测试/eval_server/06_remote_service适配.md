# 06 — remote_service 适配

> **所属步骤**：04_执行测试 → eval_server  
> **改造类型**：修改  
> **涉及文件**：`eval_server/app/services/remote_service.py`

---

## 背景

`RemoteService` 负责将评估任务分发到远程 worker 端点。当前端点选择逻辑基于 `capabilities` 中的 `task_type` 匹配和并发限制。新增的 `bleu` 和 `llm_judge` 类型需要端点支持，且 `llm_judge` 的超时和并发策略与标准类型不同。

---

## 改造内容

### 1. 端点能力匹配适配

```python
def create_remote_task(self, task_type, task_params, endpoints):
    """选择支持目标类型的端点"""
    for endpoint in endpoints:
        url = endpoint.get('url', '')

        # 检查端点是否支持该任务类型
        capabilities = endpoint.get('capabilities', {})
        task_types = endpoint.get('task_types', [])

        if task_type in capabilities or task_type in task_types:
            # 检查并发
            max_process = self._get_max_process(endpoint, task_type)
            current = self._get_current_concurrency(url, task_type)

            if current < max_process:
                # 选中该端点
                return self._forward_task(url, task_type, task_params)

    raise RuntimeError(f'没有可用的端点处理 {task_type} 类型任务')
```

### 2. llm_judge 特殊处理

```python
def _forward_task(self, endpoint_url, task_type, task_params):
    """转发任务到远程端点"""
    payload = {
        'task_type': task_type,
        'task_params': task_params,
    }

    # llm_judge 使用更长的超时
    if task_type == 'llm_judge':
        timeout = 180  # LLM 推理较慢
    else:
        timeout = 30

    try:
        response = requests.post(
            f'{endpoint_url}/api/create_task',
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()

        if data.get('code') == 0:
            task_id = data['data']['task_id']
            # 启动轮询线程
            thread = threading.Thread(
                target=self._poll_task_status,
                args=(endpoint_url, task_id, task_type),
                daemon=True,
            )
            thread.start()

            return {'task_id': task_id, 'endpoint': endpoint_url}
        else:
            raise RuntimeError(f'端点返回错误: {data.get("msg")}')

    except requests.exceptions.Timeout:
        raise RuntimeError(f'端点 {endpoint_url} 超时')
```

### 3. 轮询间隔适配

```python
def _poll_task_status(self, endpoint_url, task_id, task_type):
    """后台轮询远程任务状态"""
    # llm_judge 轮询间隔更长
    if task_type == 'llm_judge':
        poll_interval = 5  # 5 秒
    else:
        poll_interval = 2  # 2 秒

    max_attempts = 60 if task_type == 'llm_judge' else 30

    for attempt in range(max_attempts):
        try:
            resp = requests.get(
                f'{endpoint_url}/api/get_status/{task_id}',
                timeout=10,
            )
            data = resp.json().get('data', {})
            status = data.get('status')

            if status == 'completed':
                result_resp = requests.get(
                    f'{endpoint_url}/api/get_final_result/{task_id}',
                    timeout=10,
                )
                result = result_resp.json().get('data', {})

                # 更新本地数据库
                TaskModel.update_task_status(
                    task_id, status='completed',
                    result=json.dumps(result)
                )
                return

            elif status == 'failed':
                TaskModel.update_task_status(
                    task_id, status='failed',
                    error_msg=data.get('error_msg', 'Remote task failed')
                )
                return

        except Exception as e:
            logger.warning(f'轮询远程任务失败: {e}')

        time.sleep(poll_interval)

    # 超时
    TaskModel.update_task_status(
        task_id, status='failed',
        error_msg=f'Remote task timeout after {max_attempts * poll_interval}s'
    )
```

### 4. 端点 capabilities 示例

```json
{
  "url": "http://worker-1:5001",
  "name": "Worker 1",
  "capabilities": {
    "wer": {"max_process": 2},
    "ser": {"max_process": 1},
    "bleu": {"max_process": 4},
    "llm_judge": {"max_process": 2}
  },
  "task_types": ["wer", "ser", "bleu", "llm_judge"]
}
```

---

## 不变部分

- 端点 CRUD 接口不变
- 并发跟踪数据结构不变
- `get_endpoints_stats()` 不变

---

## 依赖关系

| 依赖文档 | 说明 |
|---------|------|
| `01_create_task新任务类型` | 任务入口 |
| `04_ConcurrencyManager动态类型` | 并发管理 |
