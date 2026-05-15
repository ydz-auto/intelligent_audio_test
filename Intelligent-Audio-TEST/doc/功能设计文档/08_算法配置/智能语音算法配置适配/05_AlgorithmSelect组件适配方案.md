# AlgorithmSelect - 算法选择器组件适配方案

## 1. 组件概述

### 1.1 组件定位
AlgorithmSelect 是一个通用的算法类型选择器组件，用于在多个页面中统一提供算法选择功能。

### 1.2 使用场景
- TestCaseModal：新建/编辑用例时选择算法类型
- E2ETest：E2E测试时选择算法类型
- APITest：API测试时选择算法类型
- Device：设备管理时选择支持的算法类型
- API管理：API管理时关联算法类型
- Tasks：任务列表筛选器

### 1.3 核心功能
- 算法列表展示（按分类分组）
- 搜索过滤
- 单选/多选模式
- 状态显示

---

## 2. 组件设计

### 2.1 组件结构

```
AlgorithmSelect.vue
├── el-select              # 下拉选择器
│   ├── el-option-group    # 分组
│   │   └── el-option      # 选项
│   └── ...
└── el-tag                 # 已选标签（多选模式）
```

### 2.2 组件布局

```
单选模式:
┌─────────────────────────────────────────────────────────────────────────┐
│  算法类型: [翻译 ▼]                                                      │
│            ├─ 翻译                                                       │
│            ├─ ASR                                                       │
│            ├─ 声纹识别                                                   │
│            └─ TTS                                                       │
└─────────────────────────────────────────────────────────────────────────┘

多选模式:
┌─────────────────────────────────────────────────────────────────────────┐
│  支持算法: [翻译 ×] [ASR ×] [+ 添加 ▼]                                   │
│            ├─ 翻译                                                       │
│            ├─ ASR                                                       │
│            ├─ 声纹识别                                                   │
│            └─ TTS                                                       │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 组件接口

### 3.1 Props

```typescript
interface AlgorithmSelectProps {
  // v-model 绑定值
  modelValue?: string | string[];
  
  // 占位文本
  placeholder?: string;
  
  // 是否禁用
  disabled?: boolean;
  
  // 是否多选
  multiple?: boolean;
  
  // 按分类过滤
  category?: string;
  
  // 是否显示状态标签
  showStatus?: boolean;
  
  // 是否可清空
  clearable?: boolean;
  
  // 是否可搜索
  filterable?: boolean;
  
  // 最大选择数量（多选模式）
  maxCollapseTags?: number;
}
```

### 3.2 Emits

```typescript
interface AlgorithmSelectEmits {
  // 更新 v-model 值
  (e: 'update:modelValue', value: string | string[]): void;
  
  // 选择变化时触发，返回完整的算法对象
  (e: 'change', algorithm: Algorithm | Algorithm[] | null): void;
}
```

### 3.3 Expose

```typescript
interface AlgorithmSelectExpose {
  // 刷新算法列表
  refresh: () => Promise<void>;
  
  // 清空选择
  clear: () => void;
  
  // 获取当前选中的算法对象
  getSelectedAlgorithm: () => Algorithm | Algorithm[] | null;
}
```

---

## 4. 数据结构

### 4.1 算法数据

```typescript
interface Algorithm {
  type: string;           // 算法类型代码
  name: string;           // 显示名称
  category: string;       // 分类
  status: 'online' | 'offline';  // 状态
  description?: string;   // 描述
  icon?: string;          // 图标
}
```

### 4.2 分类映射

```typescript
const categoryLabels: Record<string, string> = {
  'translation': '翻译',
  'speech_recognition': '语音识别',
  'speech_synthesis': '语音合成',
  'voiceprint': '声纹',
  'voice_processing': '语音处理'
};
```

---

## 5. 组件实现

### 5.1 完整代码

```vue
<!-- src/components/algorithm/AlgorithmSelect.vue -->
<template>
  <el-select
    :model-value="modelValue"
    :placeholder="placeholder"
    :disabled="disabled"
    :multiple="multiple"
    :clearable="clearable"
    :filterable="filterable"
    :collapse-tags="multiple"
    :collapse-tags-tooltip="multiple"
    :max-collapse-tags="maxCollapseTags"
    :loading="loading"
    class="algorithm-select"
    @update:model-value="handleChange"
  >
    <el-option-group
      v-for="(algorithms, category) in groupedAlgorithms"
      :key="category"
      :label="getCategoryLabel(category)"
    >
      <el-option
        v-for="algo in algorithms"
        :key="algo.type"
        :label="algo.name"
        :value="algo.type"
        :disabled="algo.status === 'offline'"
      >
        <div class="algorithm-option">
          <span class="algorithm-name">{{ algo.name }}</span>
          <el-tag
            v-if="showStatus"
            size="small"
            :type="getStatusType(algo.status)"
            class="algorithm-status"
          >
            {{ algo.status === 'online' ? '在线' : '离线' }}
          </el-tag>
        </div>
      </el-option>
    </el-option-group>
  </el-select>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { algorithmService } from '@/services/algorithmService';

interface Props {
  modelValue?: string | string[];
  placeholder?: string;
  disabled?: boolean;
  multiple?: boolean;
  category?: string;
  showStatus?: boolean;
  clearable?: boolean;
  filterable?: boolean;
  maxCollapseTags?: number;
}

const props = withDefaults(defineProps<Props>(), {
  placeholder: '请选择算法类型',
  disabled: false,
  multiple: false,
  showStatus: true,
  clearable: true,
  filterable: true,
  maxCollapseTags: 3
});

const emit = defineEmits<{
  (e: 'update:modelValue', value: string | string[]): void;
  (e: 'change', algorithm: Algorithm | Algorithm[] | null): void;
}>();

// 状态
const loading = ref(false);
const algorithms = ref<Algorithm[]>([]);

// 按分类分组
const groupedAlgorithms = computed(() => {
  const groups: Record<string, Algorithm[]> = {};
  
  let filteredList = algorithms.value;
  
  // 按分类过滤
  if (props.category) {
    filteredList = filteredList.filter(a => a.category === props.category);
  }
  
  // 分组
  for (const algo of filteredList) {
    if (!groups[algo.category]) {
      groups[algo.category] = [];
    }
    groups[algo.category].push(algo);
  }
  
  return groups;
});

// 获取分类标签
const getCategoryLabel = (category: string) => {
  const labels: Record<string, string> = {
    'translation': '翻译',
    'speech_recognition': '语音识别',
    'speech_synthesis': '语音合成',
    'voiceprint': '声纹',
    'voice_processing': '语音处理'
  };
  return labels[category] || category;
};

// 获取状态类型
const getStatusType = (status: string) => {
  return status === 'online' ? 'success' : 'info';
};

// 处理选择变化
const handleChange = (value: string | string[]) => {
  emit('update:modelValue', value);
  
  // 返回完整的算法对象
  if (props.multiple) {
    const selected = algorithms.value.filter(a => 
      (value as string[]).includes(a.type)
    );
    emit('change', selected);
  } else {
    const selected = algorithms.value.find(a => a.type === value) || null;
    emit('change', selected);
  }
};

// 加载算法列表
const loadAlgorithms = async () => {
  loading.value = true;
  try {
    const response = await algorithmService.getAlgorithmList();
    algorithms.value = response.data;
  } catch (error) {
    console.error('加载算法列表失败:', error);
  } finally {
    loading.value = false;
  }
};

// 刷新
const refresh = async () => {
  await loadAlgorithms();
};

// 清空
const clear = () => {
  emit('update:modelValue', props.multiple ? [] : '');
  emit('change', null);
};

// 获取选中的算法对象
const getSelectedAlgorithm = () => {
  if (!props.modelValue) return null;
  
  if (props.multiple) {
    return algorithms.value.filter(a => 
      (props.modelValue as string[]).includes(a.type)
    );
  } else {
    return algorithms.value.find(a => a.type === props.modelValue) || null;
  }
};

// 监听分类变化，重新加载
watch(() => props.category, () => {
  // 分类变化时不需要重新加载，只需要过滤
});

// 组件挂载时加载算法列表
onMounted(() => {
  loadAlgorithms();
});

// 暴露方法
defineExpose({
  refresh,
  clear,
  getSelectedAlgorithm
});
</script>

<style scoped>
.algorithm-select {
  width: 100%;
}

.algorithm-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.algorithm-name {
  flex: 1;
}

.algorithm-status {
  margin-left: 8px;
}
</style>
```

---

## 6. 使用示例

### 6.1 单选模式

```vue
<template>
  <el-form-item label="算法类型" prop="algorithm_type">
    <AlgorithmSelect
      v-model="formData.algorithm_type"
      placeholder="请选择算法类型"
      @change="handleAlgorithmChange"
    />
  </el-form-item>
</template>

<script setup lang="ts">
const formData = ref({
  algorithm_type: ''
});

const handleAlgorithmChange = (algorithm: Algorithm | null) => {
  console.log('选中的算法:', algorithm);
  // 加载对应的参数表单
  if (algorithm) {
    loadFormSchema(algorithm.type);
  }
};
</script>
```

### 6.2 多选模式

```vue
<template>
  <el-form-item label="支持算法" prop="supported_algorithms">
    <AlgorithmSelect
      v-model="formData.supported_algorithms"
      multiple
      placeholder="请选择支持的算法类型"
      @change="handleAlgorithmsChange"
    />
  </el-form-item>
</template>

<script setup lang="ts">
const formData = ref({
  supported_algorithms: [] as string[]
});

const handleAlgorithmsChange = (algorithms: Algorithm[]) => {
  console.log('选中的算法列表:', algorithms);
};
</script>
```

### 6.3 按分类过滤

```vue
<template>
  <!-- 只显示翻译类算法 -->
  <AlgorithmSelect
    v-model="formData.algorithm_type"
    category="translation"
  />
</template>
```

### 6.4 禁用状态

```vue
<template>
  <AlgorithmSelect
    v-model="formData.algorithm_type"
    disabled
  />
</template>
```

---

## 7. 组件变体

### 7.1 AlgorithmSelectList - 卡片列表选择器

用于 E2ETest/APITest 的算法选择步骤，以卡片形式展示算法列表。

```vue
<!-- AlgorithmSelectList.vue -->
<template>
  <div class="algorithm-select-list">
    <div class="algorithm-cards">
      <div
        v-for="algo in algorithms"
        :key="algo.type"
        class="algorithm-card"
        :class="{ 
          selected: algo.type === selectedId,
          disabled: algo.status === 'offline'
        }"
        @click="handleSelect(algo)"
      >
        <div class="algorithm-icon">
          <el-icon :size="32">
            <component :is="getIcon(algo.category)" />
          </el-icon>
        </div>
        <div class="algorithm-info">
          <div class="algorithm-name">{{ algo.name }}</div>
          <div class="algorithm-type">{{ algo.type }}</div>
          <el-tag 
            :type="algo.status === 'online' ? 'success' : 'info'" 
            size="small"
          >
            {{ algo.status === 'online' ? '在线' : '离线' }}
          </el-tag>
        </div>
        <div class="algorithm-actions">
          <el-button link @click.stop="handleEdit(algo)">编辑</el-button>
          <el-button 
            link 
            type="danger" 
            @click.stop="handleDelete(algo)"
          >
            删除
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>
```

### 7.2 AlgorithmRadioGroup - 单选按钮组

用于需要更直观展示的场景。

```vue
<!-- AlgorithmRadioGroup.vue -->
<template>
  <el-radio-group v-model="selectedValue" @change="handleChange">
    <el-radio-button
      v-for="algo in algorithms"
      :key="algo.type"
      :value="algo.type"
      :disabled="algo.status === 'offline'"
    >
      {{ algo.name }}
    </el-radio-button>
  </el-radio-group>
</template>
```

---

## 8. 与其他组件的集成

### 8.1 与 DynamicForm 集成

```vue
<template>
  <div>
    <!-- 算法选择 -->
    <AlgorithmSelect
      v-model="selectedAlgorithmType"
      @change="handleAlgorithmChange"
    />
    
    <!-- 动态表单 -->
    <DynamicForm
      v-if="formSchema"
      :schema="formSchema"
      v-model="algorithmParams"
    />
  </div>
</template>

<script setup lang="ts">
const selectedAlgorithmType = ref('');
const formSchema = ref(null);
const algorithmParams = ref({});

const handleAlgorithmChange = async (algorithm: Algorithm | null) => {
  if (algorithm) {
    // 加载表单 schema
    formSchema.value = await algorithmService.getFormSchema(algorithm.type);
    // 加载默认参数
    algorithmParams.value = await algorithmService.getDefaultParams(algorithm.type);
  } else {
    formSchema.value = null;
    algorithmParams.value = {};
  }
};
</script>
```

### 8.2 与 DimensionSelect 集成

```vue
<template>
  <div>
    <!-- 算法选择 -->
    <AlgorithmSelect
      v-model="selectedAlgorithmType"
      @change="handleAlgorithmChange"
    />
    
    <!-- 评估维度选择（根据算法过滤） -->
    <DimensionSelect
      v-model="selectedDimensions"
      :algorithm-type="selectedAlgorithmType"
    />
  </div>
</template>
```

---

## 9. 性能优化

### 9.1 缓存策略

```typescript
// 使用 Pinia 缓存算法列表
export const useAlgorithmStore = defineStore('algorithm', {
  state: () => ({
    algorithms: [] as Algorithm[],
    loaded: false,
    lastLoadTime: 0
  }),
  
  actions: {
    async loadAlgorithms(force = false) {
      // 5分钟内不重复加载
      const now = Date.now();
      if (!force && this.loaded && now - this.lastLoadTime < 5 * 60 * 1000) {
        return;
      }
      
      const response = await algorithmService.getAlgorithmList();
      this.algorithms = response.data;
      this.loaded = true;
      this.lastLoadTime = now;
    }
  }
});
```

### 9.2 懒加载

```typescript
// 组件挂载时才加载
onMounted(async () => {
  const store = useAlgorithmStore();
  await store.loadAlgorithms();
  algorithms.value = store.algorithms;
});
```

---

## 10. 实施清单

### 10.1 组件开发

- [ ] 创建 AlgorithmSelect.vue 组件
- [ ] 创建 AlgorithmSelectList.vue 组件
- [ ] 创建 AlgorithmRadioGroup.vue 组件
- [ ] 添加单选模式支持
- [ ] 添加多选模式支持
- [ ] 添加分类过滤功能
- [ ] 添加搜索过滤功能
- [ ] 添加状态显示功能

### 10.2 集成测试

- [ ] TestCaseModal 集成测试
- [ ] E2ETest 集成测试
- [ ] APITest 集成测试
- [ ] Device 页面集成测试
- [ ] API管理页面集成测试
- [ ] Tasks 页面集成测试

### 10.3 性能优化

- [ ] 添加缓存策略
- [ ] 添加懒加载
- [ ] 添加防抖搜索
