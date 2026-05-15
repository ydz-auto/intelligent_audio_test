# TestCaseModal - 测试用例表单适配方案

## 1. 组件概述

### 1.1 组件定位
TestCaseModal 是测试用例创建/编辑的核心弹窗组件，需要适配算法配置化方案，支持根据算法类型动态渲染参数表单。

### 1.2 使用场景
- 新建测试用例
- 编辑测试用例
- 复制测试用例

### 1.3 核心改动
- 新增算法类型选择
- 根据算法类型动态渲染参数表单
- 关联算法对应的评估维度

---

## 2. 用例与算法的关系

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         用例与算法的关系                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  TestCase ──────FK─────→ AlgorithmDefinition                           │
│       │                                                                   │
│       │  case_config.algorithm_type = 'translation'                     │
│       │                                                                   │
│       │  case_config.algorithm_params = {                                │
│       │    translation_direction: 'zh2en'  ← 从 AlgorithmConfig 获取  │
│       │  }                                                                │
│                                                                          │
│  工作流程：                                                               │
│  1. 新建用例时，选择算法类型                                              │
│  2. 根据算法类型，加载 DynamicForm（从 AlgorithmConfigPage 配置）        │
│  3. 用户填写参数，保存到 case_config.algorithm_params                    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 页面布局

```
┌─────────────────────────────────────────────────────────────────────────┐
│  新建/编辑测试用例                                                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  基本信息:                                                                │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  用例名称: [________________________]                          │   │
│  │  算法类型: [翻译 ▼] ← 选择算法类型（新增）                       │   │
│  │  用例描述: [__________________________________________]        │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  算法参数配置: (选择算法后，根据 AlgorithmConfigPage 配置动态渲染)          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  ▶ 基本配置                                                      │   │
│  │    翻译方向: [中译英 ▼] ← DynamicForm 渲染                      │   │
│  │                                                                │   │
│  │                                                                │   │
│  │  ▶ 高级选项 (可折叠)                                             │   │
│  │    置信度阈值: [━━━●━━━━] 0.8                                   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  音频配置: (现有功能)                                                    │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  [+ 添加音频]                                                    │   │
│  │  ┌───────────────────────────────────────────────────────────┐ │   │
│  │  │  音频1.wav  │  时长: 5.2s  │  [播放] [删除]               │ │   │
│  │  └───────────────────────────────────────────────────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  评估维度: (根据算法类型过滤)                                             │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  [+ 添加评估维度] ← 只显示该算法关联的评估维度                    │   │
│  │  ┌───────────────────────────────────────────────────────────┐ │   │
│  │  │  BLEU评分  │  阈值: >0.8  │  [删除]                       │ │   │
│  │  │  ROUGE评分 │  阈值: >0.7  │  [删除]                       │ │   │
│  │  └───────────────────────────────────────────────────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│                                [取消] [保存]                              │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 4. 数据结构

### 4.1 表单数据结构

```typescript
interface TestCaseFormData {
  id?: string;
  name: string;
  description?: string;
  algorithm_type: string;                    // 新增: 算法类型
  algorithm_params: Record<string, any>;     // 新增: 算法参数字典
  config: {
    audios: AudioConfig[];                   // 现有字段
    dimensions: {
      api: number[];                         // 现有字段
      e2e: number[];                         // 现有字段
    };
    // ... 其他现有字段
  };
}

interface AudioConfig {
  id: string;
  name: string;
  duration: number;
  path: string;
}
```

### 4.2 TestCase config 结构（保存到数据库）

> **注**：完整字段映射方案见 [15_完整字段映射方案.md](file:///c:/S2TT/auto_test/ver8/202601292330/doc/功能设计文档/智能语音算法配置适配/15_完整字段映射方案.md)
> **注**：参考参数功能设计见 [17_参考参数功能设计.md](file:///c:/S2TT/auto_test/ver8/202601292330/doc/功能设计文档/智能语音算法配置适配/17_参考参数功能设计.md)

```typescript
interface TestCaseConfig {
  algorithm_type: string;          // 算法类型
  algorithm_params: {              // 算法参数
    translation_direction?: string;
    asr_reference_text?: string;
    sample_rate?: number;
    model_size?: string;
    overlap_rate?: number;
    similarity_threshold?: number;
    source_language?: string;
    target_language?: string;
    confidence_threshold?: number;
    voice_model?: string;
    source_text?: string;
  };
  // 用例特殊字段（详见15_完整字段映射方案）
  special_fields: {
    tag?: string;                 // 分组标签
    source_lang?: string;         // 源语言
    target_lang?: string;         // 目标语言
    translation_direction?: string; // 翻译方向
  };
  // 参考参数（详见17_参考参数功能设计）
  reference_params: {
    input?: {
      type: 'text' | 'audio' | 'rttm' | 'stm' | 'mark';
      code: string;
      api?: string;
      e2e?: string;
    };
    output?: {
      type: 'text' | 'audio' | 'rttm' | 'stm' | 'mark';
      code: string;
      api?: string;
      e2e?: string;
    };
  };
  audios: Array<{...}>;
  dimensions: {
    api: Array<number>;
    e2e: Array<number>;
  };
}
```

### 4.3 用例特殊字段配置（基于15_完整字段映射方案）

```typescript
// 用例在调用算法时传递的特殊字段
interface TestCaseSpecialFields {
  // 用例标识
  case_id: number;
  case_name: string;
  
  // 分组字段（用于聚合计算）
  tag?: string;                   // 标签分组
  device_id?: string;             // 设备ID
  
  // 算法选择
  algorithm_type: string;         // 算法类型：asr/translation/tts/speaker_recognition
  
  // 语言方向（翻译）
  source_lang?: string;           // 源语言
  target_lang?: string;          // 目标语言
  translation_direction?: string; // 翻译方向：zh2en/en2zh
}
```

---

## 5. 组件设计

### 5.1 组件结构

```
TestCaseModal.vue
├── AlgorithmSelect.vue          # 算法类型选择器（复用）
├── DynamicForm.vue              # 动态参数表单（复用）
├── AudioConfigPanel.vue         # 音频配置面板（现有）
└── DimensionSelect.vue          # 评估维度选择器（改造）
```

### 5.2 核心模板

```vue
<template>
  <el-dialog
    v-model="visible"
    :title="isEdit ? '编辑测试用例' : '新建测试用例'"
    width="800px"
    @close="handleClose"
  >
    <el-form ref="formRef" :model="formData" :rules="formRules" label-width="100px">
      <!-- 基本信息 -->
      <el-form-item label="用例名称" prop="name">
        <el-input v-model="formData.name" placeholder="请输入用例名称" />
      </el-form-item>
      
      <!-- 算法类型选择（新增） -->
      <el-form-item label="算法类型" prop="algorithm_type">
        <AlgorithmSelect
          v-model="formData.algorithm_type"
          @change="handleAlgorithmChange"
        />
      </el-form-item>
      
      <el-form-item label="用例描述" prop="description">
        <el-input
          v-model="formData.description"
          type="textarea"
          :rows="2"
          placeholder="请输入用例描述"
        />
      </el-form-item>
      
      <!-- 算法参数配置（新增，动态渲染） -->
      <el-divider content-position="left">算法参数配置</el-divider>
      
      <DynamicForm
        v-if="formSchema"
        ref="dynamicFormRef"
        :schema="formSchema"
        :initial-values="formData.algorithm_params"
        @update:model-value="handleParamsChange"
      />
      
      <el-empty v-else description="请先选择算法类型" />
      
      <!-- 音频配置（现有功能） -->
      <el-divider content-position="left">音频配置</el-divider>
      
      <AudioConfigPanel
        v-model="formData.config.audios"
        :algorithm-type="formData.algorithm_type"
      />
      
      <!-- 评估维度（根据算法类型过滤） -->
      <el-divider content-position="left">评估维度</el-divider>
      
      <DimensionSelect
        v-model="formData.config.dimensions"
        :algorithm-type="formData.algorithm_type"
        :available-dimensions="availableDimensions"
      />
    </el-form>
    
    <template #footer>
      <el-button @click="handleClose">取消</el-button>
      <el-button type="primary" :loading="saving" @click="handleSave">
        保存
      </el-button>
    </template>
  </el-dialog>
</template>
```

---

## 6. 核心交互逻辑

### 6.1 算法类型切换

```typescript
const handleAlgorithmChange = async (algorithmType: string) => {
  if (!algorithmType) {
    formSchema.value = null;
    availableDimensions.value = [];
    return;
  }
  
  try {
    // 1. 加载算法对应的表单 schema
    const schema = await algorithmService.getFormSchema(algorithmType);
    formSchema.value = schema;
    
    // 2. 加载默认参数值
    const defaultParams = await algorithmService.getDefaultParams(algorithmType);
    formData.value.algorithm_params = defaultParams;
    
    // 3. 加载该算法关联的评估维度（通过 AlgorithmDimensionRelation 表）
    const relations = await algorithmService.getDimensionRelations(algorithmType);
    // 转换为维度列表
    const dimensions = relations.map((r: any) => ({
      id: r.dimension_id,
      name: r.dimension_name,
      is_default: r.is_default
    }));
    availableDimensions.value = dimensions;
    
    // 4. 重置已选维度（只保留关联的）
    const dimensionIds = dimensions.map(d => d.id);
    formData.value.config.dimensions.api = formData.value.config.dimensions.api.filter(
      id => dimensionIds.includes(id)
    );
    formData.value.config.dimensions.e2e = formData.value.config.dimensions.e2e.filter(
      id => dimensionIds.includes(id)
    );
    
  } catch (error) {
    ElMessage.error('加载算法配置失败: ' + error.message);
  }
};
```

### 6.2 参数变化处理

```typescript
const handleParamsChange = (params: Record<string, any>) => {
  formData.value.algorithm_params = params;
  
  // 参数变化时可以触发一些联动逻辑
  // 例如：翻译方向变化时，自动设置源语言和目标语言
  if (params.translation_direction) {
    const direction = parseTranslationDirection(params.translation_direction);
    formData.value.algorithm_params.source_language = direction.source;
    formData.value.algorithm_params.target_language = direction.target;
  }
};
```

### 6.3 保存用例

```typescript
const handleSave = async () => {
  try {
    // 1. 验证表单
    await formRef.value?.validate();
    
    // 2. 验证动态表单
    const dynamicFormValid = await dynamicFormRef.value?.validate();
    if (!dynamicFormValid) {
      ElMessage.warning('请完善算法参数配置');
      return;
    }
    
    // 3. 构建保存数据
    const saveData: TestCaseFormData = {
      name: formData.value.name,
      description: formData.value.description,
      algorithm_type: formData.value.algorithm_type,
      algorithm_params: formData.value.algorithm_params,
      config: {
        audios: formData.value.config.audios,
        dimensions: formData.value.config.dimensions,
        algorithm_type: formData.value.algorithm_type,      // 冗余存储，方便查询
        algorithm_params: formData.value.algorithm_params   // 冗余存储
      }
    };
    
    // 4. 调用保存接口
    saving.value = true;
    if (isEdit.value) {
      await testCaseService.update(formData.value.id, saveData);
    } else {
      await testCaseService.create(saveData);
    }
    
    ElMessage.success(isEdit.value ? '用例更新成功' : '用例创建成功');
    emit('success');
    handleClose();
    
  } catch (error) {
    if (error !== false) {
      ElMessage.error('保存失败: ' + error.message);
    }
  } finally {
    saving.value = false;
  }
};
```

### 6.4 编辑时加载数据

```typescript
const loadEditData = async (id: string) => {
  try {
    loading.value = true;
    const testCase = await testCaseService.getDetail(id);
    
    formData.value = {
      id: testCase.id,
      name: testCase.name,
      description: testCase.description,
      algorithm_type: testCase.config?.algorithm_type || '',
      algorithm_params: testCase.config?.algorithm_params || {},
      config: {
        audios: testCase.config?.audios || [],
        dimensions: testCase.config?.dimensions || { api: [], e2e: [] }
      }
    };
    
    // 如果有算法类型，加载对应的表单 schema
    if (formData.value.algorithm_type) {
      await handleAlgorithmChange(formData.value.algorithm_type);
    }
    
  } catch (error) {
    ElMessage.error('加载用例数据失败');
  } finally {
    loading.value = false;
  }
};
```

---

## 7. 不同算法类型的参数配置示例

### 7.1 翻译算法参数

```
┌─────────────────────────────────────────────────────────────────────────┐
│  算法参数配置 (翻译)                                                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ▶ 基本配置                                                              │
│    翻译方向: [中译英 ▼]                                                  │
│              选项: 中译英、英译中、中日互译、中韩互译等                     │
│                                                                          │
│  ▶ 高级选项                                                              │
│    源语言:   [zh        ] (隐藏字段)                                     │
│    目标语言: [en        ] (隐藏字段)                                     │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 7.2 ASR 算法参数

```
┌─────────────────────────────────────────────────────────────────────────┐
│  算法参数配置 (ASR)                                                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ▶ 基本配置                                                              │
│    参考文本: [________________________________]                          │
│              用于 ASR 识别结果对比                                       │
│                                                                          │
│  ▶ 模型配置                                                              │
│    采样率:   [16kHz ▼]                                                   │
│              选项: 8kHz, 16kHz, 44.1kHz                                  │
│    模型大小: [base ▼]                                                    │
│              选项: tiny, base, small, medium, large                      │
│                                                                          │
│  ▶ 高级选项                                                              │
│    语言:     [中文 ▼]                                                    │
│    置信度阈值: [━━━●━━━━] 0.8                                            │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 7.3 声纹识别算法参数

```
┌─────────────────────────────────────────────────────────────────────────┐
│  算法参数配置 (声纹识别)                                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ▶ 基本配置                                                              │
│    重叠率:   [━━━━━●━━━━] 50%                                            │
│              前后语音重叠播放的比例                                       │
│                                                                          │
│  ▶ 模型配置                                                              │
│    相似度阈值: [━━━━●━━━━━] 0.7                                          │
│              说话人相似度判定阈值                                         │
│                                                                          │
│  ▶ 高级选项                                                              │
│    采样率:   [16kHz ▼]                                                   │
│    声纹模型: [ecapa-tdnn ▼]                                              │
│              选项: ecapa-tdnn, resnet, x-vector                          │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 7.4 TTS 算法参数

```
┌─────────────────────────────────────────────────────────────────────────┐
│  算法参数配置 (TTS)                                                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ▶ 基本配置                                                              │
│    源语言:   [中文 ▼]                                                    │
│    源文本:   [________________________________]                          │
│              需要合成的文本内容                                           │
│                                                                          │
│  ▶ 模型配置                                                              │
│    语音模型: [女声-温柔 ▼]                                               │
│              选项: 女声-温柔, 女声-活泼, 男声-沉稳, 男声-阳光             │
│    语速:     [━━━●━━━━] 1.0x                                             │
│    音量:     [━━━━●━━━] 80%                                              │
│                                                                          │
│  ▶ 高级选项                                                              │
│    采样率:   [16kHz ▼]                                                   │
│    输出格式: [WAV ▼]                                                     │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 8. 评估维度联动

### 8.1 维度过滤逻辑

```typescript
// 根据算法类型过滤可用维度
const availableDimensions = computed(() => {
  if (!formData.value.algorithm_type || !associatedDimensions.value.length) {
    return allDimensions.value;  // 未选择算法时显示全部
  }
  return associatedDimensions.value;
});

// 加载算法关联的维度（从 AlgorithmDimensionRelation 表获取）
const loadAssociatedDimensions = async (algorithmType: string) => {
  try {
    const response = await algorithmService.getDimensionRelations(algorithmType);
    // 转换为维度列表
    associatedDimensions.value = response.map((r: any) => ({
      id: r.dimension_id,
      name: r.dimension_name,
      is_default: r.is_default
    }));
  } catch (error) {
    console.error('加载关联维度失败:', error);
    associatedDimensions.value = [];
  }
};
```

### 8.2 维度默认选择

```typescript
// 选择算法后，自动勾选默认维度
const selectDefaultDimensions = (dimensions: Dimension[]) => {
  const defaultIds = dimensions
    .filter(d => d.is_default)
    .map(d => d.id);
  
  // 合并到已选维度
  formData.value.config.dimensions.api = [
    ...new Set([...formData.value.config.dimensions.api, ...defaultIds])
  ];
};
```

---

## 9. 表单验证规则

### 9.1 基本验证规则

```typescript
const formRules = {
  name: [
    { required: true, message: '请输入用例名称', trigger: 'blur' },
    { min: 2, max: 100, message: '名称长度在 2 到 100 个字符', trigger: 'blur' }
  ],
  algorithm_type: [
    { required: true, message: '请选择算法类型', trigger: 'change' }
  ]
};
```

### 9.2 动态验证

```typescript
// 根据算法类型动态添加验证规则
const getDynamicRules = (schema: FormSchema) => {
  const rules: Record<string, any[]> = {};
  
  for (const field of schema.fields) {
    if (field.required) {
      rules[field.fieldCode] = [
        {
          required: true,
          message: `请${field.component === 'select' ? '选择' : '输入'}${field.fieldName}`,
          trigger: field.component === 'select' ? 'change' : 'blur'
        }
      ];
    }
    
    // 添加自定义验证
    if (field.validation) {
      rules[field.fieldCode] = rules[field.fieldCode] || [];
      
      if (field.validation.pattern) {
        rules[field.fieldCode].push({
          pattern: new RegExp(field.validation.pattern),
          message: field.validation.patternMessage || `${field.fieldName}格式不正确`,
          trigger: 'blur'
        });
      }
      
      if (field.validation.min !== undefined || field.validation.max !== undefined) {
        rules[field.fieldCode].push({
          validator: (rule: any, value: any, callback: any) => {
            if (field.validation.min !== undefined && value < field.validation.min) {
              callback(new Error(`${field.fieldName}不能小于${field.validation.min}`));
            } else if (field.validation.max !== undefined && value > field.validation.max) {
              callback(new Error(`${field.fieldName}不能大于${field.validation.max}`));
            } else {
              callback();
            }
          },
          trigger: 'change'
        });
      }
    }
  }
  
  return rules;
};
```

---

## 10. 状态管理

### 10.1 组件状态

```typescript
interface TestCaseModalState {
  visible: boolean;
  loading: boolean;
  saving: boolean;
  isEdit: boolean;
  formData: TestCaseFormData;
  formSchema: FormSchema | null;
  availableDimensions: Dimension[];
  associatedDimensions: Dimension[];
}
```

### 10.2 初始化状态

```typescript
const initialState: TestCaseModalState = {
  visible: false,
  loading: false,
  saving: false,
  isEdit: false,
  formData: {
    name: '',
    description: '',
    algorithm_type: '',
    algorithm_params: {},
    config: {
      audios: [],
      dimensions: { api: [], e2e: [] }
    }
  },
  formSchema: null,
  availableDimensions: [],
  associatedDimensions: []
};
```

---

## 11. 实施清单

### 11.1 后端实施

- [ ] TestCase 模型增加 algorithm_type 字段（可选，从 config 读取）
- [ ] 修改 TestCaseService 支持算法参数保存
- [ ] 新增接口：获取算法关联的评估维度

### 11.2 前端实施

- [ ] 改造 TestCaseModal.vue 组件
- [ ] 集成 AlgorithmSelect 组件
- [ ] 集成 DynamicForm 组件
- [ ] 改造 DimensionSelect 组件（支持算法过滤）
- [ ] 添加算法类型切换逻辑
- [ ] 添加参数联动逻辑
- [ ] 添加表单验证

### 11.3 测试验证

- [ ] 新建用例 - 选择算法类型
- [ ] 新建用例 - 填写动态参数
- [ ] 新建用例 - 保存验证
- [ ] 编辑用例 - 加载已有数据
- [ ] 编辑用例 - 修改算法类型
- [ ] 编辑用例 - 更新参数
- [ ] 复制用例 - 算法参数复制
- [ ] 不同算法类型切换测试
