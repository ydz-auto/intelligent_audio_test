# 14_RoundEvaluationEditor 单轮评估配置编辑器

> 组件：`frontend/src/components/common/test-case/TestCaseModal/RoundEvaluationEditor.vue`

## 功能说明

单轮评估配置编辑器，**通用组件**，所有用例均可使用。用于配置每轮是否独立执行评估。

**位置变更**：从 CaseForm 顶层移入 RoundConfigEditor 的每轮内部。每轮可独立配置不同的评估维度。

## Props / Events

```ts
interface Props {
  modelValue: RoundEvaluationConfig | undefined
  availableDimensions?: Dimension[]      // 可选评估维度列表
}

interface Emits {
  'update:modelValue'(value: RoundEvaluationConfig)
}
```

## 组件模板

```vue
<template>
  <el-card class="round-evaluation-editor">
    <template #header>
      <div class="card-header">
        <span>单轮评估配置</span>
        <el-switch v-model="config.enabled" active-text="启用" />
      </div>
    </template>

    <template v-if="config.enabled">
      <p class="description">
        启用后，E2E 测试在每轮结束时独立执行评估，生成每轮的评估结果。
      </p>

      <el-form label-width="140px">
        <el-form-item label="评估维度">
          <div class="dimension-list">
            <el-checkbox-group v-model="selectedDimensionIds">
              <el-checkbox
                v-for="dim in availableDimensions"
                :key="dim.id"
                :value="dim.id"
              >
                {{ dim.name }}
                <el-tag size="small" type="info">{{ dim.type }}</el-tag>
              </el-checkbox>
            </el-checkbox-group>
          </div>
        </el-form-item>
      </el-form>

      <div v-if="config.dimensions.length > 0" class="selected-summary">
        已选 {{ config.dimensions.length }} 个维度：
        <el-tag v-for="d in config.dimensions" :key="d.id" size="small"
                closable @close="removeDimension(d.id)">
          {{ d.name }} (权重:{{ d.weight }})
        </el-tag>
      </div>
    </template>
  </el-card>
</template>
```

## 内部状态

```ts
const config = computed({
  get: () => props.modelValue ?? { enabled: false, dimensions: [] },
  set: (val) => emit('update:modelValue', val)
})

const selectedDimensionIds = computed({
  get: () => config.value.dimensions.map(d => d.id),
  set: (ids: string[]) => {
    const dims = ids.map(id => {
      const existing = config.value.dimensions.find(d => d.id === id)
      if (existing) return existing
      const found = props.availableDimensions?.find(d => d.id === id)
      return {
        id,
        name: found?.name ?? id,
        weight: 50,
        threshold: 80
      }
    })
    emit('update:modelValue', { ...config.value, dimensions: dims })
  }
})

function removeDimension(id: string) {
  const dims = config.value.dimensions.filter(d => d.id !== id)
  emit('update:modelValue', { ...config.value, dimensions: dims })
}
```

## 与用例级评估维度的区别

| 属性 | 用例级评估维度 | 轮次评估维度 |
|------|--------------|-------------|
| 存储位置 | `config.dimensions` | `config.rounds[].evaluation.dimensions` |
| 评估时机 | 全部轮次完成后 | 每轮结束时 |
| 用途 | 整体评分 | 每轮独立评分 |

## 显示条件

在 RoundConfigEditor 每轮内部渲染（通用能力，不绑定算法类型）：

```vue
<!-- 在 RoundConfigEditor 每轮内部 -->
<RoundEvaluationEditor v-model="round.evaluation" />
```

## 存储位置变更

| 旧位置 | 新位置 |
|--------|--------|
| `config.roundEvaluation` | `config.rounds[].evaluation` |

## 引用关系

- ← `02_选用例/frontend/01_types.ts新接口定义` — RoundEvaluationConfig 接口
- ← `02_选用例/frontend/10_RoundConfigEditor` — 在每轮内部挂载
- → 后端 `04_执行测试/backend/22_E2E每轮结果收集` — 后端消费此配置
