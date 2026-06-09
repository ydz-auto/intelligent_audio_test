# 23_UploadOptions test_type 适配

> 文件：`frontend/src/components/common/UploadOptions.vue`

## 现状分析

UploadOptions 是音频上传时的配置面板，当前已支持 testTypes 多选：

```ts
// Props
interface Props {
  modelValue: {
    testTypes?: ('api' | 'e2e')[]   // 多选数组
    dimensions?: { api: [], e2e: [] }
    // ...
  }
}
```

### 当前行为

- 两个复选框："API测试" 和 "E2E测试"，可同时勾选
- 勾选 API 时展示 API 维度选择
- 勾选 E2E 时展示 E2E 维度选择、播放设备、SPL 等配置
- 上传后为每种选中的 test_type 生成独立用例

### 维度嵌套结构

```ts
dimensions: { api: DimensionConfig[], e2e: DimensionConfig[] }
```

## 改造方案

### 1. testTypes 多选逻辑不变

testTypes 是批量上传时的选项，支持同时生成 API 和 E2E 用例，此处保持不变。

### 2. 维度结构适配

由于双记录架构下每条用例有独立的扁平维度数组，上传时需要分别配置：

```ts
// 改造后
dimensions: {
  api: DimensionConfig[],   // API 用例的维度（保持不变）
  e2e: DimensionConfig[]    // E2E 用例的维度（保持不变）
}
```

> 注：UploadOptions 中维度的 `{api, e2e}` 结构在上传场景下是合理的，因为一次上传可能同时生成 API 和 E2E 两种用例，需要分别指定各自的维度。这不同于用例编辑（CaseForm）中的扁平化。

### 3. voice_llm 算法下的额外配置

当上传选择 voice_llm 算法时，可能需要额外的配置项：

```vue
<!-- voice_llm 提示 -->
<el-alert
  v-if="algorithmType === 'voice_llm'"
  type="info"
  title="语音交互大模型"
  description="voice_llm 用例将在创建后通过用例编辑器配置多轮对话、声纹注册等参数"
  :closable="false"
/>
```

多轮配置（rounds、voiceprint、interferers 等）不在上传流程中配置，而是在创建用例后通过 CaseForm 的通用编辑器配置。

### 4. 双记录自动生成

上传时为 voice_llm 生成双记录，config 使用 `{rounds:[], dimensions:[]}` 格式：

```ts
async function handleUpload() {
  for (const testType of uploadConfig.testTypes) {
    const caseData = {
      name: audioName,
      algorithmType: 'voice_llm',
      test_type: testType,
      config: {
        rounds: [
          {
            roundNumber: 1,
            audios: testType === 'api'
              ? [{ audioId, playOrder: 1 }]
              : [{ audioId, playbackDeviceId, spl, playOrder: 1 }],
            evaluation: { enabled: true, dimensions: [] },
            algorithmParams: []
          }
        ],
        dimensions: testType === 'api' ? apiDimensions : e2eDimensions
      }
    }
    const created = await testcasesApi.create(caseData)
  }
  // 更新 related_case_id 互指
}
```

## 不变部分

- testTypes 多选复选框
- 音频类型选择
- 标签输入
- 算法类型选择
- 翻译方向配置
- 提示音频配置

## 引用关系

- ← `02_选用例/frontend/01_types.ts新接口定义` — AudioConfig 接口
- → `02_选用例/backend/05_testcase_controller双记录CRUD` — 后端双记录创建
