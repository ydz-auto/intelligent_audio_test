# 25_Evaluation 页面 llm_judge 维度

> 文件：`frontend/src/views/Evaluation.vue` + `frontend/src/views/EvaluationLogic/evaluation.ts`

## 现状分析

Evaluation 页面管理评估维度（EvaluationDimension）的增删改查。当前支持的维度类型：

```ts
// 维度类型
type: 'auto' | 'manual'

// 结果类型
resultType: 'score' | 'wer' | 'ser' | 'der' | ...

// API 设置
apiSettings: {
  method: 'POST'
  headers: { 'Content-Type': 'application/json' }
  body_template: string
  timeout: number
}
```

### 核心 API 调用

| 方法 | 端点 | 用途 |
|------|------|------|
| GET | `/evaluation/dimensions` | 维度列表（分页+筛选） |
| POST | `/evaluation/dimensions` | 创建维度 |
| PUT | `/evaluation/dimensions/{id}` | 更新维度 |
| DELETE | `/evaluation/dimensions/{id}` | 删除维度 |
| GET | `/evaluation/dimensions/{id}/health` | API 健康检查 |
| POST | `/evaluation/dimensions/batch` | 批量操作 |

## 改造方案

### 1. llm_judge 维度类型

新增 `llm_judge` 类型维度，用于基于大语言模型的评估：

```ts
// 创建 llm_judge 维度的表单数据
{
  name: '回答质量评估',
  type: 'auto',
  resultType: 'llm_judge',           // 新增结果类型
  scoreUnit: '分',
  resultMin: 1,
  resultMax: 10,
  decimalPlaces: 1,
  weight: 50,
  apiSettings: {
    method: 'POST',
    timeout: 120,                     // LLM 评估较慢，超时设长
    headers: { 'Content-Type': 'application/json' },
    body_template: JSON.stringify({
      task_type: 'llm_judge',
      model: 'gpt-4',                 // 可配置的模型
      prompt_template: 'default',      // Prompt 模板选择
      input: {
        reference_text: '${reference_text}',
        llm_response: '${llm_response}',
        round_number: '${round_number}'
      }
    })
  },
  requiredInputs: ['reference_text', 'llm_response'],
  associatedAlgorithms: [{ algorithmType: 'voice_llm', isDefault: true }]
}
```

### 2. 维度表单新增字段

在 Evaluation 页面的 CRUD 表单中，为 llm_judge 类型增加配置字段：

```ts
// evaluationFields 扩展
const evaluationFields = computed(() => [
  // ...现有字段...
  {
    key: 'llmJudgeConfig',
    label: 'LLM Judge 配置',
    type: 'llmJudgeEditor',          // 新增字段类型
    visible: (form) => form.resultType === 'llm_judge',
    fields: [
      { key: 'model', label: '模型', type: 'select',
        options: ['gpt-4', 'gpt-3.5-turbo', 'claude-3-opus', 'claude-3-sonnet'] },
      { key: 'promptTemplate', label: 'Prompt 模板', type: 'select',
        options: ['default', 'accuracy', 'fluency', 'relevance'] },
      { key: 'maxTokens', label: '最大 Token 数', type: 'number', default: 1000 },
      { key: 'temperature', label: '温度', type: 'number', default: 0.1, step: 0.1 }
    ]
  }
])
```

### 3. 健康检查适配

llm_judge 维度的健康检查需要验证 LLM API 连通性：

```ts
// 健康检查请求体扩展
{
  task_type: 'llm_judge',
  test_input: {
    reference_text: '测试文本',
    llm_response: '测试回复'
  }
}
```

### 4. 列表展示

在维度列表中，llm_judge 类型以特殊标签展示：

```vue
<el-tag v-if="row.resultType === 'llm_judge'" type="danger">
  LLM Judge
</el-tag>
```

## 不变部分

- 维度列表分页、搜索、筛选
- 批量操作（启用/禁用/删除）
- 权重滑块
- 导入/导出
- 类别管理
- 子维度支持

## 引用关系

- ← `04_执行测试/eval_server/03_LLM_Judge计算器` — eval_server 端的 LLM Judge 实现
- → `04_执行测试/backend/24_evaluation_service_llm_judge分发` — 后端分发 llm_judge 评估任务
