# E2ETest - E2E测试页面适配方案

## 1. 页面概述

### 1.1 页面定位
E2ETest 是端到端测试的核心页面，用于执行设备端的测试任务。需要适配算法配置化方案，增加算法类型选择步骤。

### 1.2 页面路由
- 路由路径：`/E2ETest`
- 菜单位置：测试执行 > E2E测试

### 1.3 核心改动
- 新增步骤0：选择算法类型
- 根据算法类型筛选设备
- 根据算法类型筛选用例
- 动态参数配置

---

## 2. 页面流程改造

### 2.1 流程对比

```
原有流程:
  选择设备 → 选择用例 → 执行测试 → 查看结果

改造后流程:
  [选择算法类型] → 选择测试用例 → 选择测试设备 → 执行测试 → 查看结果
```

### 2.2 步骤说明

| 步骤 | 名称 | 说明 |
|-----|------|------|
| 步骤1 | 选择算法类型 | 新增步骤，选择测试的算法类型 |
| 步骤2 | 选择测试用例 | 根据算法类型过滤测试用例 |
| 步骤3 | 选择测试设备 | 选择测试设备（根据算法类型过滤兼容设备） |
| 步骤4 | 执行测试 | 开始执行测试任务 |
| 步骤5 | 查看结果 | 查看测试结果和报告 |

---

## 3. 页面布局

```
┌─────────────────────────────────────────────────────────────────────────┐
│  E2E测试                                                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  步骤指示器: [1.选择算法] → [2.选择测试用例] → [3.选择测试设备] → [4.执行测试] → [5.查看结果] │
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
│  │  │ type: asr        │  │ type: tts        │                     │   │
│  │  │ ✓ 已选择         │  │                  │                     │   │
│  │  └──────────────────┘  └──────────────────┘                     │   │
│  │  ┌──────────────────┐  ┌──────────────────┐                     │   │
│  │  │ 👤 说话人识别     │  │ 📊 ASR评估       │                     │   │
│  │  │ type: speaker    │  │ type: asr_eval   │                     │   │
│  │  └──────────────────┘  └──────────────────┘                     │   │
│  │                                                                   │   │
│  │  已选择: 语音识别(ASR)                                             │   │
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
│  第三步: 选择测试设备 (已实现 - 复用ResourceSelectionGrid组件)            │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  [+ 新增设备] [扫描设备] [搜索框] [状态筛选▼]                       │   │
│  │                                                                   │   │
│  │  设备卡片列表:                                                     │   │
│  │  ┌─────────────────────────────────────────────────────────────┐│   │
│  │  │ ☐ 设备名称  型号: xxx  状态: 在线  [编辑][删除]              ││   │
│  │  │ ☐ 设备名称  型号: xxx  状态: 在线  [编辑][删除]              ││   │
│  │  └─────────────────────────────────────────────────────────────┘│   │
│  │                                                                   │   │
│  │  分页控件                                                          │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              [开始任务]                                  │
│                                                                          │
│  第四步: 执行测试 (已实现 - 复用TestExecutionComponent组件)               │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  任务信息 | 执行进度 | 设备资源 | 日志                             │   │
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
| 步骤0: 选择算法 | ✅ 已实现 | 算法卡片网格布局，Ant Design Vue组件 |
| 步骤1: 选择测试用例 | ✅ 已实现 | 复用TestCaseListContainer组件 |
| 步骤2: 选择测试设备 | ✅ 已实现 | 复用ResourceSelectionGrid组件 |
| 步骤3: 执行测试 | ✅ 已实现 | 复用TestExecutionComponent组件 |
| 步骤4: 查看结果 | ✅ 已实现 | 复用TaskReportPanel组件 |
| 进度导航 | ✅ 已实现 | 5步骤ProgressNav组件 |
| 算法配置入口 | ✅ 已实现 | 跳转AlgorithmConfigPage |

### 4.2 待优化功能 📋

| 功能 | 优先级 | 说明 |
|------|--------|------|
| 用例按算法过滤 | 中 | 根据selectedAlgorithmType过滤用例 |
| 设备按算法过滤 | 中 | 根据设备支持的算法类型过滤 |
| 算法参数配置 | 低 | 动态渲染算法参数表单 |

---

## 5. 数据结构

### 5.1 页面状态 (实际实现)

```typescript
interface E2ETestState {
  // 步骤控制
  currentStep: number;  // 0-4
  
  // 算法选择
  selectedAlgorithmType: string | null;
  algorithmList: Array<{type: string, name: string, category: string}>;
  
  // 用例选择
  selectedTestCaseIds: string[];
  testCaseGroups: Record<string, TestCase[]>;
  
  // 设备选择
  selectedDeviceIds: string[];
  devices: Device[];
  deviceSearchQuery: string;
  selectedDeviceStatus: string;
  
  // 执行状态
  isExecuting: boolean;
  isPaused: boolean;
  progressPercentage: number;
  taskName: string;
  
  // 报告
  report: TaskReport;
}
```

### 5.2 设备数据结构

```typescript
interface Device {
  id: string | number;
  name: string;
  type: string;
  model?: string;
  status: 'online' | 'offline';
  connectionAddress?: string;
}
```

### 4.3 执行参数

```typescript
interface E2EExecutionParams {
  task_id: string;
  device_id: string;
  algorithm_type: string;           // 新增
  algorithm_params: Record<string, any>;  // 新增
  reference_params?: {              // 参考参数（可选）
    params: Array<{
      type: string;    // text, audio, rttm, stm, mark
      code: string;    // 参数代码
      e2e: string;     // E2E测试使用的参考值
    }>;
  };
  case_ids: string[];
}
```

---

## 5. 组件设计

### 5.1 组件结构

```
E2ETest.vue
├── TestStepIndicator.vue        # 步骤指示器
├── DeviceSelector.vue           # 设备选择器（改造）
├── AlgorithmSelectList.vue      # 算法选择列表（新增）
├── TestCaseSelector.vue         # 用例选择器（改造）
├── DynamicForm.vue              # 动态参数表单（复用）
├── AlgorithmConfigModal.vue     # 算法配置弹窗（复用）
└── ExecutionPanel.vue           # 执行面板
```

### 5.2 核心模板

```vue
<template>
  <div class="e2e-test-page">
    <!-- 步骤指示器 -->
    <TestStepIndicator
      :steps="steps"
      :current="currentStep"
      @click="handleStepClick"
    />
    
    <!-- 步骤内容 -->
    <div class="step-content">
      <!-- 步骤1: 选择设备 -->
      <TestStepContainer
        v-if="currentStep === 1"
        title="选择设备"
        :show-prev="false"
        next-label="下一步"
        @next="nextStep"
      >
        <DeviceSelector
          v-model="selectedDeviceId"
          :algorithm-filter="selectedAlgorithmType"
          @change="handleDeviceChange"
        />
      </TestStepContainer>
      
      <!-- 步骤2: 选择算法类型（新增） -->
      <TestStepContainer
        v-if="currentStep === 2"
        title="选择算法类型"
        prev-label="上一步"
        next-label="下一步"
        @prev="prevStep"
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
          :device-filter="selectedDeviceId"
          @select="handleAlgorithmSelect"
          @edit="handleAlgorithmEdit"
          @delete="handleAlgorithmDelete"
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
  { key: 'device', title: '选择设备', icon: 'Monitor' },
  { key: 'algorithm', title: '选择算法', icon: 'Cpu' },
  { key: 'cases', title: '选用例', icon: 'Document' },
  { key: 'params', title: '配置参数', icon: 'Setting' },
  { key: 'execute', title: '执行测试', icon: 'VideoPlay' }
];
```

### 6.2 设备选择处理

```typescript
const handleDeviceChange = (device: Device | null) => {
  selectedDevice.value = device;
  
  // 如果已选择算法，检查设备是否支持
  if (selectedAlgorithmType.value && device) {
    if (!device.supported_algorithms.includes(selectedAlgorithmType.value)) {
      ElMessage.warning('当前设备不支持所选算法，请重新选择');
      selectedAlgorithmType.value = null;
      selectedAlgorithm.value = null;
    }
  }
  
  // 过滤可用算法列表
  filterAlgorithmsByDevice();
};
```

### 6.3 算法选择处理

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
  
  // 3. 根据算法类型过滤用例
  await loadTestCases({ algorithm_type: algorithm.type });
  
  // 4. 根据算法类型调整可用设备列表
  await loadCompatibleDevices(algorithm.type);
};
```

### 6.4 用例选择处理

```typescript
const handleCaseChange = (caseIds: string[]) => {
  selectedCaseIds.value = caseIds;
  
  // 可以从已选用例中提取共同的参数作为默认值
  if (caseIds.length > 0) {
    extractCommonParams(caseIds);
  }
};

const extractCommonParams = async (caseIds: string[]) => {
  const cases = await testCaseService.getBatch(caseIds);
  
  // 提取共同的算法参数
  const commonParams: Record<string, any> = {};
  const firstParams = cases[0]?.config?.algorithm_params || {};
  
  for (const [key, value] of Object.entries(firstParams)) {
    const isCommon = cases.every(c => 
      c.config?.algorithm_params?.[key] === value
    );
    if (isCommon) {
      commonParams[key] = value;
    }
  }
  
  // 合并到当前参数
  algorithmParams.value = {
    ...algorithmParams.value,
    ...commonParams
  };
};
```

### 6.5 参数变化处理

```typescript
const handleParamsChange = (params: Record<string, any>) => {
  algorithmParams.value = params;
};
```

### 6.6 执行测试

```typescript
const handleExecute = async () => {
  // 1. 验证
  if (!selectedDeviceId.value) {
    ElMessage.warning('请选择设备');
    return;
  }
  if (!selectedAlgorithmType.value) {
    ElMessage.warning('请选择算法类型');
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
  const executionParams: E2EExecutionParams = {
    task_id: generateTaskId(),
    device_id: selectedDeviceId.value,
    algorithm_type: selectedAlgorithmType.value,
    algorithm_params: algorithmParams.value,
    case_ids: selectedCaseIds.value
  };
  
  // 4. 开始执行
  try {
    isExecuting.value = true;
    taskId.value = executionParams.task_id;
    
    await executionService.executeE2ETest(executionParams);
    
    // 进入执行步骤
    currentStep.value = 5;
    
  } catch (error) {
    ElMessage.error('启动测试失败: ' + error.message);
    isExecuting.value = false;
  }
};
```

---

## 7. 设备算法兼容性

### 7.1 设备过滤逻辑

```typescript
// 根据算法类型过滤设备
const filterDevicesByAlgorithm = (algorithmType: string) => {
  if (!algorithmType) {
    return allDevices.value;
  }
  
  return allDevices.value.filter(device => 
    device.supported_algorithms.includes(algorithmType)
  );
};

// 根据设备过滤算法
const filterAlgorithmsByDevice = () => {
  if (!selectedDevice.value) {
    return algorithmList.value;
  }
  
  return algorithmList.value.filter(algo =>
    selectedDevice.value!.supported_algorithms.includes(algo.type)
  );
};
```

### 7.2 兼容性提示

```vue
<!-- 设备卡片显示支持的算法 -->
<template>
  <div class="device-card" :class="{ selected: isSelected }">
    <div class="device-name">{{ device.name }}</div>
    <div class="device-type">{{ device.type }}</div>
    <div class="supported-algorithms">
      <el-tag
        v-for="algo in device.supported_algorithms"
        :key="algo"
        size="small"
        :type="algo === selectedAlgorithmType ? 'primary' : 'info'"
      >
        {{ getAlgorithmName(algo) }}
      </el-tag>
    </div>
  </div>
</template>
```

---

## 8. 算法选择列表组件

### 8.1 组件设计

```vue
<!-- AlgorithmSelectList.vue -->
<template>
  <div class="algorithm-select-list">
    <div class="algorithm-cards">
      <div
        v-for="algo in filteredAlgorithms"
        :key="algo.type"
        class="algorithm-card"
        :class="{ selected: algo.type === selectedId }"
        @click="handleSelect(algo)"
      >
        <div class="algorithm-icon">
          <el-icon :size="32"><component :is="getIcon(algo.category)" /></el-icon>
        </div>
        <div class="algorithm-info">
          <div class="algorithm-name">{{ algo.name }}</div>
          <div class="algorithm-type">{{ algo.type }}</div>
          <el-tag :type="algo.status === 'online' ? 'success' : 'info'" size="small">
            {{ algo.status === 'online' ? '在线' : '离线' }}
          </el-tag>
        </div>
        <div class="algorithm-actions">
          <el-button link @click.stop="handleEdit(algo)">编辑</el-button>
          <el-button link type="danger" @click.stop="handleDelete(algo)">删除</el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

interface Props {
  algorithms: Algorithm[];
  selectedId: string | null;
  deviceFilter?: string;
}

const props = defineProps<Props>();

const emit = defineEmits<{
  (e: 'select', algorithm: Algorithm): void;
  (e: 'edit', algorithm: Algorithm): void;
  (e: 'delete', algorithm: Algorithm): void;
}>();

// 根据设备过滤算法
const filteredAlgorithms = computed(() => {
  if (!props.deviceFilter) {
    return props.algorithms;
  }
  
  // 获取设备支持的算法
  const device = getDeviceById(props.deviceFilter);
  if (!device) return props.algorithms;
  
  return props.algorithms.filter(algo =>
    device.supported_algorithms.includes(algo.type)
  );
});

const handleSelect = (algo: Algorithm) => {
  emit('select', algo);
};

const handleEdit = (algo: Algorithm) => {
  emit('edit', algo);
};

const handleDelete = (algo: Algorithm) => {
  emit('delete', algo);
};
</script>
```

---

## 9. 执行参数传递

### 9.1 前端到后端

```typescript
// 前端发送的执行参数
const executionParams = {
  task_id: 'task_001',
  device_id: 'device_android_001',
  algorithm_type: 'translation',
  algorithm_params: {
    translation_direction: 'zh2en',
    sample_rate: 16000,
    model_size: 'base'
  },
  case_ids: ['case_001', 'case_002', 'case_003']
};

// 调用后端接口
await executionService.executeE2ETest(executionParams);
```

### 9.2 后端处理

```python
# backend/controllers/task_controller.py

def start_e2e_task():
    data = request.get_json()
    
    task_id = data.get('task_id')
    device_id = data.get('device_id')
    algorithm_type = data.get('algorithm_type')
    algorithm_params = data.get('algorithm_params', {})
    case_ids = data.get('case_ids', [])
    
    # 创建任务
    task = execution_engine.start_e2e_task(
        task_id=task_id,
        device_id=device_id,
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
// stores/e2eTest.ts
import { defineStore } from 'pinia';

export const useE2ETestStore = defineStore('e2eTest', {
  state: (): E2ETestState => ({
    currentStep: 1,
    selectedDeviceId: null,
    selectedDevice: null,
    selectedAlgorithmType: null,
    selectedAlgorithm: null,
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
          return !!state.selectedDeviceId;
        case 2:
          return !!state.selectedAlgorithmType;
        case 3:
          return state.selectedCaseIds.length > 0;
        case 4:
          return true;  // 参数配置可选
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
      this.selectedDeviceId = null;
      this.selectedDevice = null;
      this.selectedAlgorithmType = null;
      this.selectedAlgorithm = null;
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

- [ ] 修改 ExecutionEngine 支持 algorithm_type 参数
- [ ] 修改 E2EExecutor 支持算法参数传递
- [ ] 新增设备算法兼容性查询接口
- [ ] 新增用例按算法类型筛选接口
- [ ] E2E执行时传递 reference_params（从算法配置中获取 e2e 字段值）

### 11.2 前端实施

- [ ] 改造 E2ETest.vue 页面
- [ ] 创建 AlgorithmSelectList.vue 组件
- [ ] 改造 DeviceSelector.vue 组件
- [ ] 改造 TestCaseSelector.vue 组件
- [ ] 集成 DynamicForm 组件
- [ ] 添加步骤控制逻辑
- [ ] 添加设备-算法兼容性过滤
- [ ] 创建 useE2ETestStore
- [ ] 用例选择后加载对应算法的参考参数配置（显示在参数配置步骤）

### 11.3 测试验证

- [ ] 设备选择流程测试
- [ ] 算法选择流程测试
- [ ] 设备-算法兼容性测试
- [ ] 用例筛选测试
- [ ] 参数配置测试
- [ ] 执行测试流程
- [ ] 步骤回退测试
- [ ] 重置流程测试
