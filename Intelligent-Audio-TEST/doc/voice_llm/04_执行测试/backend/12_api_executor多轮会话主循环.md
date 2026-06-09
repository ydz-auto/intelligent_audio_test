# 12 - api_executor 多轮会话主循环

## 涉及文件
- `Intelligent-Audio-TEST/backend/utils/api_executor.py`

## 现状分析

### 现有 execute_api_case() 调用链

```
execute_api_case(app, task_id, tc_rel_id)
  ├── _validate_and_get_data()          # 获取用例、音频、API配置
  ├── _setup_api_endpoints()            # 设置API端点
  ├── for api_config in api_configs:    # 遍历每个API
  │     ├── health_check()              # 健康检查
  │     ├── create_task()               # 创建异步任务
  │     ├── _wait_for_task_completion() # 轮询等待完成
  │     ├── get_final_result()          # 获取结果
  │     ├── extract_fields()            # 提取字段
  │     ├── save_to_db()               # 保存到DB
  │     ├── enqueue_evaluation()        # 入队评估
  │     └── delete_task()              # 清理任务
  └── mark_completed()
```

关键行号（参考）：
- `execute_api_case`: ~260行
- `_validate_and_get_data`: ~199-462行
- `_wait_for_task_completion`: ~700-900行
- test_type 过滤逻辑: 325-332行（已移除，双记录架构不需要）

## 改造方案

### 配置驱动的多轮会话入口

> **API 测试用例为单条记录**（`test_type='api'`），不同于 E2E 的双记录模式。

```python
def execute_api_case(self, app, task_id, tc_rel_id):
    """
    执行API测试用例
    """
    # ... 现有验证逻辑 ...
    
    data = self._validate_and_get_data(app, task_id, tc_rel_id)
    case_config = data['case_config']
    
    # === 配置驱动：用例配置了 rounds 则进入多轮会话模式 ===
    rounds = case_config.get('rounds', [])
    if rounds:
        return self._execute_multi_round_session(app, task_id, tc_rel_id, data)
    
    # === 现有线性流程（未配置 rounds 的用例） ===
    # ... for api_config in api_configs ...
```

### _execute_multi_round_session

```python
def _execute_multi_round_session(self, app, task_id, tc_rel_id, data):
    """多轮会话执行（配置驱动，不绑定算法类型）"""
    case_config = data['case_config']
    algorithm_params = data['case_algorithm_params']
    api_configs = data['api_configs']
    
    rounds = case_config.get('rounds', [])
    session_config = case_config.get('session', {})
    session_timeout = session_config.get('sessionTimeout', 60)
    
    all_results = []
    
    for api_config in api_configs:
        # 1. 健康检查
        if not self._health_check(task_id, api_config):
            continue
        
        # 2. 创建会话
        session = SessionContext(
            session_id=self._generate_session_id(),
            session_timeout=session_timeout,
            context_mode=session_config.get('contextMode', 'full')
        )
        
        try:
            # 3. 多轮循环
            for round_config in sorted(rounds, key=lambda r: r.get('order', 0)):
                round_number = round_config.get('order')
                
                # 发送轮次请求
                round_result = self._send_round_request(
                    task_id, api_config, session, round_config, round_number
                )
                
                if round_result:
                    # 更新上下文
                    session.add_history(round_config, round_result)
                    all_results.append(round_result)
                    
                    # 可选：单轮评估入队
                    if case_config.get('roundEvaluation', {}).get('enabled'):
                        self._enqueue_round_evaluation(
                            task_id, tc_rel_id, round_number, round_result
                        )
            
            # 4. 汇总多轮结果
            aggregated = self._aggregate_round_results(all_results)
            
            # 5. 保存到 DB
            self._save_multi_round_results(
                task_id, tc_rel_id, aggregated, session.session_id
            )
            
            # 6. 入队整体评估
            self._enqueue_evaluation(task_id, tc_rel_id, aggregated)
            
        finally:
            # 7. 销毁会话
            session.destroy()
    
    return True
```

### 与现有流程的差异

| 步骤 | 现有流程（单轮） | 多轮会话流程（rounds 非空） |
|------|---------|----------------|
| 触发条件 | 无 rounds 配置 | `case_config.rounds` 非空 |
| 创建任务 | 每个 API 创建一个 task | 每个轮次创建一个 task |
| 等待方式 | 轮询 audio_duration × 1.5 | session_timeout 固定超时 |
| 结果结构 | 单条结果 | rounds 数组 |
| 评估时机 | 全部完成后一次性评估 | 可选单轮评估 + 整体评估 |
| 会话管理 | 无 | SessionContext 维护上下文 |

### 删除 test_type 过滤逻辑

现有代码 325-332 行的 test_type 过滤已不需要（双记录架构下记录已是单类型），该段代码应删除或简化为：

```python
# 双记录架构：记录已是单类型，直接使用所有音频
target_audios = [audio for audio in audios if audio.get('audio_id')]
```

## 不变部分

- 未配置 `rounds` 的用例继续走现有线性流程
- `_validate_and_get_data()` 接口不变
- `health_check()`、`create_task()`、`delete_task()` 接口不变

## 相关文档
- [13_SessionContext会话管理器.md](13_SessionContext会话管理器.md) — 会话管理器
- [14_轮次请求构建.md](14_轮次请求构建.md) — 轮次请求设计
- [15_轮次超时策略.md](15_轮次超时策略.md) — 超时策略
- [16_API测试结果存储结构.md](16_API测试结果存储结构.md) — 结果存储
