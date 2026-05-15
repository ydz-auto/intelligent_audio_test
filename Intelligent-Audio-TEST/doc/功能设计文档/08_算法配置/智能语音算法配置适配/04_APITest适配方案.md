# APITest - API测试页面适配方案

## 1. 页面概述

### 1.1 页面定位
APITest 是 API 测试的核心页面，用于执行 API 接口测试。需要适配算法配置化方案，增加算法类型选择步骤，与 E2ETest 保持一致的交互流程。

### 1.2 页面路由
- 路由路径：`/APITest`
- 菜单位置：测试执行 > API测试

### 1.3 核心改动
- 新增步骤0：选择算法类型
- 根据算法类型筛选 API
- 根据算法类型筛选用例
- 动态参数配置

---

## 2. 页面流程改造

### 2.1 流程对比

```
原有流程:
  选择用例 → 选择API → 执行测试 → 查看结果

改造后流程:
  [选择算法类型] → 选择测试用例 → 选择被测API → 执行测试 → 查看结果
```

### 2.2 步骤说明

| 步骤 | 名称 | 说明 |
|-----|------|------|
| 步骤1 | 选择算法类型 | 新增步骤，选择测试的算法类型 |
| 步骤2 | 选择测试用例 | 根据算法类型过滤测试用例 |
| 步骤3 | 选择被测API | 根据算法类型过滤API |
| 步骤4 | 执行测试 | 开始执行测试任务 |
| 步骤5 | 查看结果 | 查看测试结果和报告 |

### 2.3 与 E2ETest 的差异

| 项目 | E2ETest | APITest |
|-----|---------|---------|
| 步骤顺序 | 算法→用例→设备→执行→结果 | 算法→用例→API→执行→结果 |
| 资源选择 | 设备 | API |
| 兼容性 | 设备-算法兼容性 | API-算法关联 |

---

## 3. 页面布局

```
┌─────────────────────────────────────────────────────────────────────────┐
│  API测试                                                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  步骤指示器: [1.选择算法] → [2.选择测试用例] → [3.选择被测API] → [4.执行测试] → [5.查看结果] │
│                                                                          │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                          │
│  第一步: 选择算法 (已实现)                                                │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  [⚙ 算法配置]                                                     │   │
│  │                                                                   │   │
│  │  算法卡片网格:                                                     │   │
│  │  ┌──────────────────┐  ┌──────────────────┐                     │   │
│  │  │ 🎤 语音识别(ASR)  │  │ 🔊 语音合成(TTS)  │                     │   │
│  │  │ 类型: asr        │  │ 类型: tts        │                     │   │
│  │  │ ☐ 选择           │  │ ☐ 选择           │                     │   │
│  │  └──────────────────┘  └──────────────────┘                     │   │
│  │  ┌──────────────────┐  ┌──────────────────┐                     │   │
│  │  │ 👤 说话人识别     │  │ 📊 ASR评估       │                     │   │
│  │  │ 类型: speaker    │  │ 类型: asr_eval   │                     │   │
│  │  │ ☐ 选择           │  │ ☐ 选择           │                     │   │
│  │  └──────────────────┘  └──────────────────┘                     │   │
│  │                                                                   │   │
│  │  当前选择: 语音识别(ASR)                                           │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              [下一步]                                    │
│                                                                          │
│  第二步: 选择测试用例 (已实现 - 复用TestCaseListContainer组件)            │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  用例分组列表，支持:                                                │   │
│  │  - 新建分组/用例                                                    │   │
│  │  - 导入/导出用例                                                    │   │
│  │  - 批量选择用例                                                     │   │
│  │  - 标签筛选                                                        │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              [下一步]                                    │
│                                                                          │
│  第三步: 选择被测API (已实现 - 复用ResourceSelectionGrid组件)             │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  [+ 新增API] [搜索框] [状态筛选▼]                                  │   │
│  │                                                                   │   │
│  │  API卡片列表:                                                      │   │
│  │  ┌─────────────────────────────────────────────────────────────┐│   │
│  │  │ ☐ API名称  端点: http://...  状态: 在线  [编辑][删除]        ││   │
│  │  │ ☐ API名称  端点: http://...  状态: 在线  [编辑][删除]        ││   │
│  │  └─────────────────────────────────────────────────────────────┘│   │
│  │                                                                   │   │
│  │  分页控件                                                          │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              [开始任务]                                  │
│                                                                          │
│  第四步: 执行测试 (已实现 - 复用TestExecutionComponent组件)               │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  任务信息 | 执行进度 | API资源 | 日志                              │   │
│  │                                                                   │   │
│  │  执行进度: ████████░░ 80%                                         │   │
│  │  已完成: 8  进行中: 1  待执行: 1                                   │   │
│  │                                                                   │   │
│  │  [暂停] [停止]                                                    │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  第五步: 查看结果 (已实现 - 复用TaskReportPanel组件)                      │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  任务报告                                                          │   │
│  │  - 测试结果统计                                                    │   │
│  │  - 详细报告表格                                                    │   │
│  │  - 结论分析                                                        │   │
│  │                                                                   │   │
│  │  [上一步] [导出报告] [发布] [开始新测试]                           │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 4. 实现状态

### 4.1 已实现功能 ✅

| 功能 | 状态 | 说明 |
|------|------|------|
| 步骤0: 选择算法 | ✅ 已实现 | 算法卡片网格布局，checkbox选择 |
| 步骤1: 选择测试用例 | ✅ 已实现 | 复用TestCaseListContainer组件 |
| 步骤2: 选择被测API | ✅ 已实现 | 复用ResourceSelectionGrid组件 |
| 步骤3: 执行测试 | ✅ 已实现 | 复用TestExecutionComponent组件 |
| 步骤4: 查看结果 | ✅ 已实现 | 复用TaskReportPanel组件 |
| 进度导航 | ✅ 已实现 | 5步骤ProgressNav组件 |
| 算法配置入口 | ✅ 已实现 | 跳转AlgorithmConfigPage |

### 4.2 待优化功能 📋

| 功能 | 优先级 | 说明 |
|------|--------|------|
| 用例按算法过滤 | 中 | 根据selectedAlgorithmType过滤用例 |
| API按算法过滤 | 中 | 根据selectedAlgorithmType过滤API |
| 算法参数配置 | 低 | 动态渲染算法参数表单 |

---

## 5. 数据结构

### 5.1 页面状态 (实际实现)

```typescript
interface APITestState {
  // 步骤控制
  currentStep: number;  // 0-4
  
  // 算法选择
  selectedAlgorithmType: string | null;
  algorithmList: Array<{value: string, name: string, category: string}>;
  
  // 用例选择
  selectedTestCaseIds: string[];
  testCaseGroups: Record<string, TestCase[]>;
  
  // API选择
  selectedAPIIds: string[];
  apis: API[];
  apiSearchQuery: string;
  apiFilter: string;
  
  // 执行状态
  isExecuting: boolean;
  isPaused: boolean;
  progressPercentage: number;
  taskName: string;
  
  // 报告
  report: TaskReport;
}
```

### 5.2 API 数据结构

```typescript
interface API {
  id: string | number;
  name: string;
  apiUrl: string;
  method: string;
  status: 'online' | 'offline';
  description?: string;
}
```

### 4.3 执行参数

```typescript
interface APIExecutionParams {
  task_id: string;
  api_id: string;
  algorithm_type: string;           // 新增
  algorithm_params: Record<string, any>;  // 新增
  reference_params?: {              // 参考参数（可选）
    params: Array<{
      type: string;    // text, audio, rttm, stm, mark
      code: string;    // 参数代码
      api: string;    // API测试使用的参考值
    }>;
  };
  case_ids: string[];
}
```

---

## 5. 组件设计

### 5.1 组件结构

```
APITest.vue
├── TestStepIndicator.vue        # 步骤指示器
├── AlgorithmSelectList.vue      # 算法选择列表（复用）
├── APISelector.vue              # API选择器（改造）
├── TestCaseSelector.vue         # 用例选择器（改造）
├── DynamicForm.vue              # 动态参数表单（复用）
├── AlgorithmConfigModal.vue     # 算法配置弹窗（复用）
└── ExecutionPanel.vue           # 执行面板
```

### 5.2 核心模板

```vue
<template>
  <div class="api-test-page">
    <!-- 步骤指示器 -->
    <TestStepIndicator
      :steps="steps"
      :current="currentStep"
      @click="handleStepClick"
    />
    
    <!-- 步骤内容 -->
    <div class="step-content">
      <!-- 步骤1: 选择算法类型（新增） -->
      <TestStepContainer
        v-if="currentStep === 1"
        title="选择算法类型"
        :show-prev="false"
        next-label="下一步"
        @next="nextStep"
      >
        <template #header-extra>
          <el-button type="primary" @click="openAlgorithmModal">
            <el-icon><Plus /></el-icon> 新建算法
          </el-button>
        </template>
        
        <AlgorithmSelectList
          :algorithms="algorithmList"
          :selected-id="selectedAlgorithmType"
          @select="handleAlgorithmSelect"
          @edit="handleAlgorithmEdit"
          @delete="handleAlgorithmDelete"
        />
      </TestStepContainer>
      
      <!-- 步骤2: 选择API -->
      <TestStepContainer
        v-if="currentStep === 2"
        title="选择API"
        prev-label="上一步"
        next-label="下一步"
        @prev="prevStep"
        @next="nextStep"
      >
        <APISelector
          v-model="selectedApiId"
          :algorithm-filter="selectedAlgorithmType"
          @change="handleApiChange"
        />
      </TestStepContainer>
      
      <!-- 步骤3: 选择用例 -->
      <TestStepContainer
        v-if="currentStep === 3"
        title="选择测试用例"
        prev-label="上一步"
        next-label="下一步"
        @prev="prevStep"
        @next="nextStep"
      >
        <TestCaseSelector
          v-model="selectedCaseIds"
          :algorithm-filter="selectedAlgorithmType"
          @change="handleCaseChange"
        />
      </TestStepContainer>
      
      <!-- 步骤4: 参数配置（新增） -->
      <TestStepContainer
        v-if="currentStep === 4"
        title="算法参数配置"
        prev-label="上一步"
        next-label="开始测试"
        @prev="prevStep"
        @next="handleExecute"
      >
        <DynamicForm
          v-if="formSchema"
          ref="dynamicFormRef"
          :schema="formSchema"
          :initial-values="algorithmParams"
          @update:model-value="handleParamsChange"
        />
        <el-empty v-else description="请先选择算法类型" />
      </TestStepContainer>
      
      <!-- 步骤5: 执行测试 -->
      <TestStepContainer
        v-if="currentStep === 5"
        title="执行测试"
        prev-label="上一步"
        :show-next="false"
        @prev="prevStep"
      >
        <ExecutionPanel
          :task-id="taskId"
          :is-executing="isExecuting"
          @stop="handleStop"
        />
      </TestStepContainer>
    </div>
    
    <!-- 算法配置弹窗 -->
    <AlgorithmConfigModal
      v-model:visible="algorithmModalVisible"
      :edit-data="algorithmModalEditData"
      @success="handleAlgorithmModalSuccess"
    />
  </div>
</template>
```

---

## 6. 核心交互逻辑

### 6.1 步骤定义

```typescript
const steps = [
  { key: 'algorithm', title: '选择算法', icon: 'Cpu' },
  { key: 'api', title: '选择API', icon: 'Connection' },
  { key: 'cases', title: '选用例', icon: 'Document' },
  { key: 'params', title: '配置参数', icon: 'Setting' },
  { key: 'execute', title: '执行测试', icon: 'VideoPlay' }
];
```

### 6.2 算法选择处理

```typescript
const handleAlgorithmSelect = async (algorithm: Algorithm) => {
  selectedAlgorithmType.value = algorithm.type;
  selectedAlgorithm.value = algorithm;
  
  // 1. 加载算法对应的表单 schema
  try {
    const schema = await algorithmService.getFormSchema(algorithm.type);
    formSchema.value = schema;
    
    // 2. 加载默认参数
    const defaultParams = await algorithmService.getDefaultParams(algorithm.type);
    algorithmParams.value = defaultParams;
    
  } catch (error) {
    ElMessage.error('加载算法配置失败');
  }
  
  // 3. 根据算法类型过滤 API
  await loadAPIs({ algorithm_type: algorithm.type });
  
  // 4. 根据算法类型过滤用例
  await loadTestCases({ algorithm_type: algorithm.type });
  
  // 5. 重置已选 API 和用例
  selectedApiId.value = null;
  selectedCaseIds.value = [];
};
```

### 6.3 API 选择处理

```typescript
const handleApiChange = (api: API | null) => {
  selectedApi.value = api;
  
  // 可以从 API 配置中提取默认参数
  if (api?.meta?.default_params) {
    algorithmParams.value = {
      ...algorithmParams.value,
      ...api.meta.default_params
    };
  }
};
```

### 6.4 执行测试

```typescript
const handleExecute = async () => {
  // 1. 验证
  if (!selectedAlgorithmType.value) {
    ElMessage.warning('请选择算法类型');
    return;
  }
  if (!selectedApiId.value) {
    ElMessage.warning('请选择API');
    return;
  }
  if (selectedCaseIds.value.length === 0) {
    ElMessage.warning('请选择测试用例');
    return;
  }
  
  // 2. 验证动态表单
  const valid = await dynamicFormRef.value?.validate();
  if (!valid) {
    ElMessage.warning('请完善算法参数配置');
    return;
  }
  
  // 3. 构建执行参数
  const executionParams: APIExecutionParams = {
    task_id: generateTaskId(),
    api_id: selectedApiId.value,
    algorithm_type: selectedAlgorithmType.value,
    algorithm_params: algorithmParams.value,
    case_ids: selectedCaseIds.value
  };
  
  // 4. 开始执行
  try {
    isExecuting.value = true;
    taskId.value = executionParams.task_id;
    
    await executionService.executeAPITest(executionParams);
    
    // 进入执行步骤
    currentStep.value = 5;
    
  } catch (error) {
    ElMessage.error('启动测试失败: ' + error.message);
    isExecuting.value = false;
  }
};
```

---

## 7. API 选择器组件

### 7.1 组件设计

```vue
<!-- APISelector.vue -->
<template>
  <div class="api-selector">
    <!-- 搜索和筛选 -->
    <div class="filter-bar">
      <el-input
        v-model="searchKeyword"
        placeholder="搜索API名称或地址"
        clearable
        @input="handleSearch"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
    </div>
    
    <!-- API 列表 -->
    <div class="api-list">
      <div
        v-for="api in filteredAPIs"
        :key="api.id"
        class="api-card"
        :class="{ selected: api.id === modelValue }"
        @click="handleSelect(api)"
      >
        <div class="api-header">
          <span class="api-name">{{ api.name }}</span>
          <el-tag :type="api.status === 'enabled' ? 'success' : 'info'" size="small">
            {{ api.status === 'enabled' ? '启用' : '禁用' }}
          </el-tag>
        </div>
        <div class="api-info">
          <el-tag size="small" :type="getMethodType(api.method)">
            {{ api.method }}
          </el-tag>
          <span class="api-endpoint">{{ api.endpoint }}</span>
        </div>
        <div class="api-algorithm" v-if="api.algorithm_type">
          <el-tag size="small" type="primary">
            {{ getAlgorithmName(api.algorithm_type) }}
          </el-tag>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';

interface Props {
  modelValue: string | null;
  algorithmFilter?: string;
}

const props = defineProps<Props>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: string | null): void;
  (e: 'change', api: API | null): void;
}>();

const searchKeyword = ref('');
const allAPIs = ref<API[]>([]);

// 根据算法类型过滤
const filteredAPIs = computed(() => {
  let result = allAPIs.value;
  
  // 算法类型过滤
  if (props.algorithmFilter) {
    result = result.filter(api => api.algorithm_type === props.algorithmFilter);
  }
  
  // 关键词搜索
  if (searchKeyword.value) {
    const keyword = searchKeyword.value.toLowerCase();
    result = result.filter(api =>
      api.name.toLowerCase().includes(keyword) ||
      api.endpoint.toLowerCase().includes(keyword)
    );
  }
  
  return result;
});

const handleSelect = (api: API) => {
  emit('update:modelValue', api.id);
  emit('change', api);
};

const getMethodType = (method: string) => {
  const types: Record<string, string> = {
    GET: 'success',
    POST: 'primary',
    PUT: 'warning',
    DELETE: 'danger'
  };
  return types[method] || 'info';
};
</script>
```

---

## 8. 算法类型快速筛选

### 8.1 快速筛选栏

```
┌─────────────────────────────────────────────────────────────────────────┐
│  算法类型快速筛选:                                                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │  全部    │  │  翻译    │  │  ASR     │  │  声纹识别  │              │
│  │  (30)   │  │  (12)   │  │  (10)   │  │  (8)     │              │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘              │
└─────────────────────────────────────────────────────────────────────────┘
```

### 8.2 实现代码

```vue
<template>
  <div class="algorithm-quick-filter">
    <div
      v-for="filter in filterOptions"
      :key="filter.value"
      class="filter-item"
      :class="{ active: activeFilter === filter.value }"
      @click="handleFilter(filter.value)"
    >
      <span class="filter-label">{{ filter.label }}</span>
      <span class="filter-count">({{ filter.count }})</span>
    </div>
  </div>
</template>

<script setup lang="ts">
const filterOptions = computed(() => {
  const options = [
    { label: '全部', value: '', count: allAPIs.value.length }
  ];
  
  // 按算法类型统计
  const algorithmCounts: Record<string, number> = {};
  for (const api of allAPIs.value) {
    const type = api.algorithm_type || 'other';
    algorithmCounts[type] = (algorithmCounts[type] || 0) + 1;
  }
  
  for (const [type, count] of Object.entries(algorithmCounts)) {
    options.push({
      label: getAlgorithmName(type),
      value: type,
      count
    });
  }
  
  return options;
});
</script>
```

---

## 9. 执行参数传递

### 9.1 前端到后端

```typescript
// 前端发送的执行参数
const executionParams = {
  task_id: 'task_001',
  api_id: 'api_translation_001',
  algorithm_type: 'translation',
  algorithm_params: {
    translation_direction: 'zh2en',
    sample_rate: 16000
  },
  case_ids: ['case_001', 'case_002', 'case_003']
};

// 调用后端接口
await executionService.executeAPITest(executionParams);
```

### 9.2 后端处理

```python
# backend/controllers/task_controller.py

def start_api_task():
    data = request.get_json()
    
    task_id = data.get('task_id')
    api_id = data.get('api_id')
    algorithm_type = data.get('algorithm_type')
    algorithm_params = data.get('algorithm_params', {})
    case_ids = data.get('case_ids', [])
    
    # 创建任务
    task = execution_engine.start_api_task(
        task_id=task_id,
        api_id=api_id,
        algorithm_type=algorithm_type,
        algorithm_params=algorithm_params,
        case_ids=case_ids
    )
    
    return jsonify({
        'success': True,
        'task_id': task.id
    })
```

---

## 10. 状态管理

### 10.1 Pinia Store

```typescript
// stores/apiTest.ts
import { defineStore } from 'pinia';

export const useAPITestStore = defineStore('apiTest', {
  state: (): APITestState => ({
    currentStep: 1,
    selectedAlgorithmType: null,
    selectedAlgorithm: null,
    selectedApiId: null,
    selectedApi: null,
    selectedCaseIds: [],
    filteredCases: [],
    algorithmParams: {},
    formSchema: null,
    isExecuting: false,
    taskId: null
  }),
  
  getters: {
    canProceed: (state) => {
      switch (state.currentStep) {
        case 1:
          return !!state.selectedAlgorithmType;
        case 2:
          return !!state.selectedApiId;
        case 3:
          return state.selectedCaseIds.length > 0;
        case 4:
          return true;
        default:
          return false;
      }
    }
  },
  
  actions: {
    nextStep() {
      if (this.currentStep < 5) {
        this.currentStep++;
      }
    },
    
    prevStep() {
      if (this.currentStep > 1) {
        this.currentStep--;
      }
    },
    
    reset() {
      this.currentStep = 1;
      this.selectedAlgorithmType = null;
      this.selectedAlgorithm = null;
      this.selectedApiId = null;
      this.selectedApi = null;
      this.selectedCaseIds = [];
      this.filteredCases = [];
      this.algorithmParams = {};
      this.formSchema = null;
      this.isExecuting = false;
      this.taskId = null;
    }
  }
});
```

---

## 11. 实施清单

### 11.1 后端实施

- [ ] API 模型增加 algorithm_type 字段
- [ ] 修改 ExecutionEngine 支持 API 测试的 algorithm_type 参数
- [ ] 新增 API 按算法类型筛选接口
- [ ] 新增用例按算法类型筛选接口
- [ ] API执行时传递 reference_params（从算法配置中获取 api 字段值）

### 11.2 前端实施

- [ ] 改造 APITest.vue 页面
- [ ] 改造 APISelector.vue 组件
- [ ] 改造 TestCaseSelector.vue 组件
- [ ] 集成 AlgorithmSelectList 组件
- [ ] 集成 DynamicForm 组件
- [ ] 添加步骤控制逻辑
- [ ] 添加算法类型快速筛选
- [ ] 创建 useAPITestStore
- [ ] 用例选择后加载对应算法的参考参数配置（显示在参数配置步骤）

### 11.3 测试验证

- [ ] 算法选择流程测试
- [ ] API 筛选测试
- [ ] 用例筛选测试
- [ ] 参数配置测试
- [ ] 执行测试流程
- [ ] 步骤回退测试
- [ ] 重置流程测试
- [ ] 与 E2ETest 流程一致性测试
