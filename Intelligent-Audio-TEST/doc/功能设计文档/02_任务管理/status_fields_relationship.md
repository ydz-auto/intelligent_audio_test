# 状态字段关系文档

## 1. 核心定义

| 字段名 | 模型 | 取值范围 | 含义 |
|--------|------|----------|------|
| **status** | Task | `pending` / `queued` / `running` / `evaluating` / `reevaluate_queued` / `reevaluating` / `completed` / `failed` / `stopped` / `paused` / `skipped` | **任务状态**：表示整个测试任务的宏观状态 |
| **status** | TaskCase | `pending` / `completed` / `failed` / `skipped` / `running` | **最终结果状态**：表示执行或评估的最终结果 |
| **execution_status** | TaskCase, TestResult | `pending` / `queued` / `running` / `completed` / `stopped` / `failed` | **执行过程状态**：表示执行过程中的实时状态（包括排队等待） |
| **evaluation_status** | TaskCase, TestResultDimension | `queued` / `pending` / `running` / `calculating` / `completed` / `stopped` / `failed` | **评估过程状态**：表示维度评估过程中的实时状态（TaskCase中为融合字段，同步反映test_results.execution_status和test_result_dimensions.evaluation_status） |

## 2. 状态流转关系

### 任务层面
```
普通测试: pending → queued/running → evaluating → completed/failed/stopped/paused/skipped
重新评估: completed/failed → reevaluate_queued → reevaluating → completed/failed
```

### 执行流程
```
task_case.execution_status: pending → queued → running → completed/failed/stopped
                     ↓
task_case.evaluation_status: pending → queued → running → calculating → completed/failed
                     ↓
task_case.status:                   pending/completed/failed/skipped/running
                     ↓
test_result.execution_status: pending → queued → running → completed/failed/stopped
                     ↓
test_result_dimension.evaluation_status: pending → running → completed/failed
                     ↓
test_result_dimension.status:            completed/failed
```

> **注意**：对于 API 任务，`queued` 状态表示用例已进入执行引擎线程池，但正在排队等待 API 端点的空闲执行权（由 API 级并发限制控制）。只有当用例真正开始调用 API 时，状态才会变为 `running`。

### 重新评估状态流转
```
Task.status:
    completed/failed → reevaluate_queued → reevaluating → completed/failed

TaskCase.evaluation_status:
    重新评估前: completed/failed
         ↓ (提交重新评估)
    queued
         ↓ (开始处理)
    pending
         ↓ (评估服务处理中)
    running
         ↓ (计算指标中)
    calculating
         ↓ (所有维度评估完成)
    completed/failed
```

## 2.1 执行流程优化（并行执行模式）

从版本 1.8 开始，支持用例执行与评估并行处理，显著提升整体吞吐量：

### 核心流程
```
用例1提交 → 执行完成 → 评估提交 → ✅ 立即返回 → 执行用例2 → ... → 用例N执行完成 → 所有评估完成 → ✅ 更新统计
                ↓
         评估服务异步处理
```

### 关键设计原则

1. **执行与评估分离**：
   - 用例执行完成后立即提交评估任务，然后返回
   - 不等待评估完成，继续执行下一个用例
   - 实现真正的并行处理

2. **独立队列机制**：
   - 每个 API ID 对应独立的执行队列 `api_queues[api_id]`
   - `api_waiting_counts[api_id]` 记录每个 API 的等待数
   - 确保 API 级别的并发控制

3. **统计更新统一管理**：
   - 任务统计信息（completed_cases/failed_cases）只在所有评估完成后更新
   - 由评估服务的 `_post_evaluate_updates` 方法统一处理
   - 避免执行引擎和评估服务重复更新导致状态不一致

4. **无评估维度用例处理**：
   - 如果用例没有配置评估维度，直接标记 `TestResult.execution_status = 'completed'`
   - 调用 `_post_evaluate_updates` 更新任务统计
   - TaskCase 的最终状态需要等待所有 TestResult 评估完成后统一更新

5. **多设备/多API结果处理**：
   - **TaskCase → TestResult** 是 **一对多** 关系
   - 每个设备/API的执行结果对应一个 `TestResult`
   - **TaskCase.evaluation_status** 不在执行器中更新，避免多个结果时状态互相覆盖
   - **TaskCase.status** 只在**所有 TestResult 评估完成后**才更新最终状态
   - 状态更新逻辑：
     1. 执行器创建 TestResult 后立即提交评估，不更新 TaskCase 状态
     2. 评估服务在每个维度评估完成后更新 TestResultDimension
     3. 评估服务的 `update_task_case_status()` 检查所有 TestResult 是否都评估完成
     4. 只有所有 TestResult 都完成后，才更新 TaskCase.status

### 执行流程时序图

```
时间轴 →
├─ 用例1提交 ───────────┐
│                      │├─ 用例2提交 ────────┐
│                      ││                   │├─ 用例3提交 ────┐
│                      ││                   ││                │
└──────────────────────┴─────────────────────┴────────────────┘
      ↓                      ↓                    ↓
   执行完成               执行完成             执行完成
      ↓                      ↓                    ↓
   评估提交               评估提交             评估提交
      ↓                      ↓                    ↓
   ✅ 继续执行            ✅ 继续执行          ✅ 继续执行
   用例2                 用例3               ...
      ↓                      ↓                    ↓
   ...                     ...                 评估完成
                                                   ↓
                                            所有评估完成
                                                   ↓
                                          更新任务统计
```

> **重要**：进度更新（WebSocket推送）由执行引擎的等待循环统一管理，避免与评估服务的重复推送。

## 3. 层级关系

### 3.1 TaskCase 层面
- **execution_status**：控制整个测试用例的执行流程
- **evaluation_status**：融合反映test_results.execution_status和test_result_dimensions.evaluation_status的状态，记录评估过程的实时状态
- **status**：记录测试用例的最终执行结果
- **依赖关系**：无直接依赖，是执行流程的起点

### 3.2 TestResult 层面
- **execution_status**：记录单个测试结果的执行状态
- **依赖关系**：依赖于 TaskCase 的执行状态
- **影响**：触发维度评估流程

### 3.3 TestResultDimension 层面
- **evaluation_status**：记录每个维度的评估过程状态
- **status**：记录维度评估的最终结果（completed/failed）
- **依赖关系**：依赖于 TestResult 的执行状态
- **影响**：影响 TestCase 的最终结果统计

## 4. 状态转换规则

| 过程 | 触发条件 | 状态转换 |
|------|----------|----------|
| **执行入队** | 任务调度器将用例提交到线程池 | `execution_status: pending → queued`<br>`status: running` |
| **执行开始** | 获取到 API 执行权或 E2E 流程启动时 | `execution_status: queued → running`<br>`evaluation_status: pending` |
| **执行成功** | 用例执行完成且无错误 | `execution_status: running → completed`<br>`evaluation_status: queued` |
| **评估入队** | 执行成功后将评估任务加入队列 | `evaluation_status: queued` |
| **评估开始** | 评估服务 Worker 开始处理 | `evaluation_status: queued → running` |
| **评估计算** | 维度评估完成，开始计算指标 | `evaluation_status: running → calculating` |
| **评估成功** | 所有维度评估完成且有有效结果 | `evaluation_status: calculating → completed` | 评估完成后，TaskCase.status 会在执行引擎的状态修复阶段自动更新为 completed |
| **评估失败** | 任何维度评估无有效结果或发生错误 | `evaluation_status: running → failed`<br>`status: failed` |
| **执行失败** | 用例执行过程中发生错误 | `execution_status: running → failed`<br>`evaluation_status: failed`<br>`status: failed` |
| **执行失败（无评估维度）** | 用例执行失败，或执行成功但无评估维度 | `execution_status: completed/failed`<br>`evaluation_status: completed` (当无评估维度时自动更新)<br>`status: completed/failed` |
| **执行停止** | 手动停止任务时 | `execution_status: running → stopped`<br>`evaluation_status: stopped`<br>`status: skipped` |

## 5. 字段使用规范

### 5.1 使用原则
1. **结果状态 vs 过程状态分离**：
   - 过程状态（execution_status, evaluation_status）：反映实时进度
   - 结果状态（status）：仅记录最终结果

2. **层级一致性**：
   - 上层状态变化应触发下层状态相应变化
   - 禁止下层状态与上层状态矛盾

3. **原子性更新**：
   - 状态更新应在事务内完成
   - 避免部分状态更新导致的数据不一致

### 5.2 禁止操作
1. 禁止直接设置 `status = 'pending'`（仅允许 Task 初始化时设置 pending）
2. 禁止过程状态与结果状态不一致
3. 禁止跳过状态流转直接设置最终状态

> **说明**：`status = 'running'` 是允许的，用于表示用例正在执行中，方便前端直接展示。这是一个设计决策，与 `execution_status` 的 `running` 状态保持同步。

### 5.3 TaskCase 状态字段更新时机

#### 5.3.1 execution_status 更新时机
| 阶段 | 更新时机 | 更新值 | 说明 |
|------|----------|--------|------|
| **任务提交** | 任务调度器提交用例到线程池时 | `queued` | 标志用例已进入执行队列 |
| **执行开始** | 获取到 API 执行权或 E2E 流程启动时 | `running` | 标志用例开始真正执行 |
| **执行成功** | 用例执行完成且无错误 | `completed` | 标志用例执行成功完成（异步评估已开始） |
| **执行失败** | 用例执行过程中发生错误 | `failed` | 标志用例执行失败 |
| **任务停止** | 手动停止任务时 | `stopped` | 标志用例执行被中断 |

#### 5.3.2 evaluation_status 更新时机
| 阶段 | 更新时机 | 更新值 | 说明 |
|------|----------|--------|------|
| **执行开始** | 任务调度器选择用例执行时 | `pending` | 标志用例开始执行，准备评估 |
| **评估入队** | 执行成功后将评估任务加入评估队列 | `queued` | 标志评估任务已入队，等待评估服务处理 |
| **评估开始** | 评估服务 Worker 开始处理 | `running` | 标志开始维度评估 |
| **评估计算** | 维度评估完成，开始计算指标 | `calculating` | 标志所有维度评估完成，开始计算融合指标 |
| **评估成功** | 所有维度评估完成且有有效结果 | `completed` | 标志所有维度评估成功完成 |
| **评估失败** | 任何维度评估无有效结果或发生错误 | `failed` | 标志维度评估失败 |
| **执行失败** | 用例执行过程中发生错误 | `failed` | 标志执行失败，评估终止 |
| **任务停止** | 手动停止任务时 | `stopped` | 标志评估被中断 |

#### 5.3.3 status 更新时机
| 阶段 | 更新时机 | 更新值 | 说明 |
|------|----------|--------|------|
| **任务创建** | 创建任务-用例关联时 | `pending` | 初始状态 |
| **执行入队** | 用例提交到执行队列时 | `running` | 表示用例正在等待执行 |
| **执行失败** | 用例执行过程中发生错误 | `failed` | 执行失败时直接更新 |
| **评估完成** | 所有评估完成后（_post_evaluate_updates） | `completed`/`failed` | 评估服务在所有评估完成后更新任务统计信息 |

> **重要说明**（并行执行模式 v1.8+）：
> - `status` 字段的最终更新由评估服务的 `_post_evaluate_updates` 方法统一处理
> - 只有当所有用例的评估都完成后，才会更新任务的统计信息（completed_cases/failed_cases）
> - 执行引擎不再直接更新 `task.status`，避免状态重复更新导致不一致
> - 对于没有配置评估维度的用例，直接标记为 `status = 'completed'`，并调用 `_post_evaluate_updates`

#### 5.3.4 时间字段更新时机
| 字段名 | 更新时机 | 说明 |
|--------|----------|------|
| **started_at** | execution_status 变为 running 时 | 记录用例开始执行时间 |
| **completed_at** | execution_status 变为 completed/failed/stopped 时 | 记录用例结束时间 |
| **duration** | completed_at 更新时 | 计算并记录用例执行耗时（秒） |

### 5.4 TaskCase 状态更新流程示例

1. **用例提交到执行队列**：
   ```python
   tc.execution_status = 'queued'
   tc.status = 'running'  # 同步设置，方便前端展示
   db.session.commit()
   ```

2. **用例开始执行**：
   ```python
   tc.execution_status = 'running'
   tc.evaluation_status = 'pending'
   tc.started_at = datetime.now()
   db.session.commit()
   ```

3. **用例执行成功**：
   ```python
   tc.execution_status = 'completed'
   tc.evaluation_status = 'queued'  # 评估任务已入队
   tc.completed_at = datetime.now()
   db.session.commit()
   ```

4. **评估服务开始处理**：
   ```python
   tc.evaluation_status = 'running'  # 评估服务开始处理
   db.session.commit()
   ```

5. **评估计算阶段**：
   ```python
   tc.evaluation_status = 'calculating'  # 所有维度评估完成，开始计算融合指标
   db.session.commit()
   ```

6. **评估成功**：
   ```python
   tc.evaluation_status = 'completed'
   tc.status = 'completed'
   db.session.commit()
   ```

7. **评估失败**：
   ```python
   tc.evaluation_status = 'failed'
   tc.status = 'failed'
   db.session.commit()
   ```

8. **用例执行失败**：
   ```python
   tc.execution_status = 'failed'
   tc.evaluation_status = 'failed'
   tc.status = 'failed'
   tc.completed_at = datetime.now()
   db.session.commit()
   ```

9. **手动停止任务**：
   ```python
   tc.execution_status = 'stopped'
   tc.evaluation_status = 'stopped'
   tc.status = 'skipped'
   tc.completed_at = datetime.now()
   db.session.commit()
   ```

10. **状态修复阶段**（执行引擎自动执行）：
    ```python
    # 执行引擎在所有用例运行完成后，会检查每个用例的状态
    for tc in all_task_cases:
        if tc.execution_status == 'completed' and tc.evaluation_status == 'completed':
            tc.status = 'completed'  # 两个条件都满足才更新为完成
        elif tc.evaluation_status in ['running', 'queued', 'pending', 'calculating']:
            tc.status = 'running'  # 仍在评估中，保持运行状态
        else:
            tc.status = 'failed'  # 其他情况标记为失败
    db.session.commit()
    ```

> **重要说明**：TaskCase.status 的最终状态（completed）需要满足两个条件：
> 1. `execution_status = 'completed'`（所有设备/API 执行完成）
> 2. `evaluation_status = 'completed'`（所有维度评估完成）
> 
> 只有在执行引擎的状态修复阶段，当这两个条件都满足时，才会自动更新为 completed。

## 6. 代码实现示例

### 6.1 正确的状态设置示例
```python
# 提交到执行队列
tc.execution_status = 'queued'
tc.status = 'running'  # 同步设置，方便前端展示
db.session.commit()

# 执行开始
tc.execution_status = 'running'
tc.evaluation_status = 'pending'
tc.started_at = datetime.now()
db.session.commit()

# 执行成功
tc.execution_status = 'completed'
tc.evaluation_status = 'queued'  # 评估任务已入队
tc.completed_at = datetime.now()
db.session.commit()

# 评估成功
tc.evaluation_status = 'completed'
tc.status = 'completed'
db.session.commit()

# 评估计算中
tc.evaluation_status = 'calculating'
db.session.commit()

# 执行失败
tc.execution_status = 'failed'
tc.evaluation_status = 'failed'
tc.status = 'failed'
tc.error_message = str(e)
tc.completed_at = datetime.now()
db.session.commit()
```

### 6.2 正确的状态查询示例
```python
# 查询待入队用例
pending_cases = TaskCase.query.filter_by(execution_status='pending').all()

# 查询排队中用例
queued_cases = TaskCase.query.filter_by(execution_status='queued').all()

# 查询执行中的用例
running_cases = TaskCase.query.filter_by(execution_status='running').all()

# 查询失败的用例
failed_cases = TaskCase.query.filter_by(status='failed').all()

# 查询已完成的用例
completed_cases = TaskCase.query.filter_by(status='completed').all()

# 查询被跳过的用例
skipped_cases = TaskCase.query.filter_by(status='skipped').all()

# 查询已完成的用例
completed_cases = TaskCase.query.filter_by(status='completed').all()
```

## 7. 监控与调试

### 7.1 状态不一致排查
1. 检查 `execution_status` 与 `status` 的匹配关系
2. 验证 `evaluation_status` 与 `status` 的匹配关系
3. 查看日志中状态转换的完整记录

### 7.2 常见问题及解决方案
| 问题 | 可能原因 | 解决方案 |
|------|----------|----------|
| `status='pending'` 且 execution_status 已完成 | 代码错误设置 | 查找并修复直接设置 `status='pending'` 的代码 |
| 执行完成但 `status` 仍为 `failed` | 维度评估失败 | 检查维度评估日志，修复评估逻辑 |
| `execution_status='running'` 但实际未执行 | 任务中断 | 检查任务调度器和线程池状态 |
| `execution_status='queued'` 长时间不变 | API 端点资源不足 | 检查 API 的 max_process 配置 |
| 评估完成后 `status` 未更新 | 评估成功但未更新状态 | 检查评估完成后的状态更新逻辑 |
| API执行成功后 `execution_status` 仍为 `running` | 状态更新逻辑位置错误 | 确保状态更新逻辑在所有执行路径上都能执行 |

## 8. 状态字段在前端的展示

### 8.1 任务状态映射
| 后端状态 | 前端展示 |
|----------|----------|
| `pending` | 待执行 |
| `queued` | 排队中 |
| `running` | 执行中 |
| `completed` | 已完成 |
| `failed` | 失败 |
| `stopped` | 已停止 |
| `paused` | 已暂停 |
| `skipped` | 已跳过 |

### 8.2 执行状态映射
| 后端状态 | 前端展示 |
|----------|----------|
| `pending` | 待执行 |
| `queued` | 排队中 |
| `running` | 执行中 |
| `completed` | 已完成 |
| `stopped` | 已停止 |
| `failed` | 执行失败 |

### 8.3 评估状态映射
| 后端状态 | 前端展示 |
|----------|----------|
| `queued` | 待评估 |
| `pending` | 待评估 |
| `running` | 评估中 |
| `calculating` | 计算中 |
| `completed` | 已完成 |
| `stopped` | 已停止 |
| `failed` | 评估失败 |

### 8.4 结果状态映射
| 后端状态 | 前端展示 |
|----------|----------|
| `completed` | 完成 |
| `failed` | 失败 |
| `pending` | 待执行 |
| `skipped` | 已跳过 |

### 8.5 前端状态转换逻辑

前端使用 `transformTestCaseStatus` 函数将后端状态转换为前端展示状态，该函数位于 `frontend/src/utils/statusUtils.ts`。

#### 8.5.1 转换规则

| execution_status | evaluation_status | 最终展示状态 |
|------------------|-------------------|--------------|
| `failed` | 任意 | `failed` |
| `in_progress` | 任意 | `in_progress` |
| `queued` | 任意 | `queued` |
| `completed` | `calculating` / `running` | `calculating` |
| `completed` | `failed` | `failed` |
| `completed` | `completed` | `resultStatus` (completed/completed) |
| `completed` | `pending` | `in_progress` |
| `completed` | 其他 | `calculating` |

#### 8.5.2 关键逻辑说明

1. **执行失败优先**：当 `executionStatus` 为 `failed` 时，无论 `evaluationStatus` 如何，最终状态都为 `failed`

2. **执行完成后需评估完成才算真正完成**：
   - 当 `executionStatus = completed` 且 `evaluationStatus = pending` 时，状态为 `in_progress`（等待评估开始）
   - 当 `executionStatus = completed` 且 `evaluationStatus = calculating/running` 时，状态为 `calculating`（评估中）
   - 当 `executionStatus = completed` 且 `evaluationStatus = completed` 时，才根据 `resultStatus` 显示最终结果

3. **执行状态映射**：
   ```typescript
   const executionStatusMap = {
     'pending': 'pending',
     'queued': 'queued',
     'running': 'in_progress',
     'completed': 'completed',
     'stopped': 'stopped',
     'failed': 'failed'
   };
   ```

4. **评估状态映射**：
   ```typescript
   const evaluationStatusMap = {
     'queued': 'pending',  // 后端 queued 映射为前端 pending（待评估）
     'pending': 'pending',
     'running': 'calculating',
     'completed': 'completed',
     'stopped': 'stopped',
     'calculating': 'calculating',
     'failed': 'failed'
   };
   ```

5. **结果状态映射**：
   ```typescript
   const resultStatusMap = {
     'completed': 'completed',
     'failed': 'failed'
   };
   ```

> **说明**：`resultStatusMap` 用于映射 `TaskCase.status` 字段。TaskCase 的最终结果只有 `completed`（完成）或 `failed`（失败），`passed` 只在 `TestResultDimension` 模型的 `status` 字段中使用。

> **重要**：根据状态流转规则，用例执行完成 (`execution_status = completed`) 后，还需要等待维度评估完成 (`evaluation_status = completed`) 才算真正完成。前端状态转换逻辑严格遵循此规则，确保用户看到的状态与实际业务流程一致。

## 9. 总结

### 9.1 设计优势
1. **清晰的责任划分**：不同状态字段负责不同阶段的状态管理
2. **良好的扩展性**：便于添加新的状态和流程
3. **实时监控能力**：支持实时跟踪执行和评估进度
4. **准确的结果统计**：基于最终结果状态进行统计分析

### 9.2 最佳实践
1. 始终使用正确的状态字段进行查询和更新
2. 遵循状态流转规则，避免跳过中间状态
3. 保持状态字段的一致性和完整性
4. 记录状态转换的完整日志，便于调试和监控

### 9.3 未来优化方向
1. 实现状态转换的自动化验证
2. 添加状态流转的可视化监控
3. 优化状态更新的性能和可靠性
4. 增强状态字段的类型安全

---

**文档版本**：1.11
**创建时间**：2026-01-02
**更新时间**：2026-04-28
**文档作者**：系统自动生成

### 文档更新历史
| 版本 | 日期 | 更新内容 |
|------|------|----------|
| 1.11 | 2026-04-28 | 添加 calculating 评估状态、重新评估状态流转 (reevaluate_queued/reevaluating) |
| 1.9 | 2026-02-10 | 修复多设备/多API场景下评估状态互相覆盖问题 |
| 1.8 | 2026-02-10 | 新增并行执行模式（用例执行与评估并行）、独立队列机制、统计更新统一管理等优化 |
| 1.7 | 2026-02-05 | 补充状态字段使用规范和常见问题 |
| 1.6 | 2026-01-28 | 完善前端状态转换逻辑 |
| 1.5 | 2026-01-20 | 添加执行状态和评估状态映射表 |
| 1.4 | 2026-01-15 | 补充TaskCase状态更新流程示例 |
| 1.3 | 2026-01-10 | 完善状态转换规则表 |
| 1.2 | 2026-01-08 | 补充层级关系说明 |
| 1.1 | 2026-01-05 | 完善状态流转图 |
| 1.0 | 2026-01-02 | 初始版本 |
