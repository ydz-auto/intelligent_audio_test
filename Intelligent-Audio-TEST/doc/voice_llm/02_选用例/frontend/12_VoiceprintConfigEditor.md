# 12_VoiceprintConfigEditor 声纹注册编辑器

> 组件：`frontend/src/components/common/test-case/TestCaseModal/VoiceprintConfigEditor.vue`

## 功能说明

声纹注册配置编辑器，**通用组件**，所有 E2E 用例均可使用。用户按需启用声纹注册流程。

**位置变更**：从 CaseForm 顶层移入 RoundConfigEditor 的每轮内部，作为 DynamicForm 的子编辑器（param_type=voiceprint_editor）。每轮可独立配置不同的声纹注册。

**数据绑定变更**：v-model 绑定到 `algorithmParams` 中 field_code='voiceprintEnabled' 的 field_value，而不是 `round.voiceprintRegistration`。

## Props / Events

```ts
interface Props {
  modelValue: AlgorithmParamItem[]     // round.algorithmParams 数组
  fieldCode: string                     // 'voiceprintEnabled' 等
}

interface Emits {
  'update:modelValue'(value: AlgorithmParamItem[])
}
```

## 组件模板

```vue
<template>
  <el-card class="voiceprint-config-editor">
    <template #header>
      <div class="card-header">
        <span>声纹注册配置</span>
        <el-switch v-model="enabled" active-text="启用" />
      </div>
    </template>

    <template v-if="enabled">
      <el-form label-width="140px">
        <!-- 注册音频 -->
        <el-form-item label="注册音频">
          <AudioSelectButton
            v-model="voiceprintAudioId"
            @open="openAudioModal"
          />
          <AudioPreview v-if="voiceprintAudioId" :audio-id="voiceprintAudioId" />
        </el-form-item>

        <!-- 播放设备 -->
        <el-form-item label="播放设备">
          <DeviceSelector
            v-model="voiceprintPlaybackDeviceId"
            :filter="dryDevices"
          />
        </el-form-item>

        <!-- 播放声压级 -->
        <el-form-item label="播放声压级(dB)">
          <el-input-number
            v-model="voiceprintSpl"
            :min="40" :max="100" :step="1"
          />
          <el-button @click="openSplCalibration">校准</el-button>
        </el-form-item>

        <!-- 等待时间 -->
        <el-form-item label="注册后等待(秒)">
          <el-input-number
            v-model="voiceprintWaitTime"
            :min="0" :max="60" :step="1"
          />
          <span class="hint">声纹注册完成后等待设备处理的时间</span>
        </el-form-item>
      </el-form>
    </template>
  </el-card>
</template>
```

## algorithmParams 读写逻辑

```ts
function getAlgoParamValue(params: AlgorithmParamItem[], fieldCode: string, default?: any): any {
  const item = params?.find(p => p.field_code === fieldCode)
  return item?.field_value ?? default
}

function setAlgoParamValue(fieldCode: string, value: any) {
  const params = [...(props.modelValue ?? [])]
  const idx = params.findIndex(p => p.field_code === fieldCode)
  if (idx >= 0) {
    params[idx] = { field_code: fieldCode, field_value: value }
  } else {
    params.push({ field_code: fieldCode, field_value: value })
  }
  emit('update:modelValue', params)
}

const enabled = computed({
  get: () => getAlgoParamValue(props.modelValue, 'voiceprintEnabled', false),
  set: (val) => setAlgoParamValue('voiceprintEnabled', val)
})

const voiceprintAudioId = computed({
  get: () => getAlgoParamValue(props.modelValue, 'voiceprintAudioId', ''),
  set: (val) => setAlgoParamValue('voiceprintAudioId', val)
})

const voiceprintPlaybackDeviceId = computed({
  get: () => getAlgoParamValue(props.modelValue, 'voiceprintPlaybackDeviceId', ''),
  set: (val) => setAlgoParamValue('voiceprintPlaybackDeviceId', val)
})

const voiceprintSpl = computed({
  get: () => getAlgoParamValue(props.modelValue, 'voiceprintSpl', 70),
  set: (val) => setAlgoParamValue('voiceprintSpl', val)
})

const voiceprintWaitTime = computed({
  get: () => getAlgoParamValue(props.modelValue, 'voiceprintWaitTime', 5),
  set: (val) => setAlgoParamValue('voiceprintWaitTime', val)
})
```

## 复用组件

| 组件 | 来源 | 用途 |
|------|------|------|
| `AudioSelectModal` | 现有 | 选择注册音频 |
| `DeviceSelector` | 现有 | 选择播放设备 |
| `SPLCalibrationModal` | 现有 | 声压级校准 |

## 显示条件

E2E test_type 时渲染（通用能力，不绑定算法类型）。作为 **DynamicForm 的子编辑器**，在每轮内部显示：

```vue
<!-- 在 DynamicForm 内部，param_type=voiceprint_editor 时渲染 -->
<template v-if="testType === 'e2e'">
  <VoiceprintConfigEditor
    v-model="round.algorithmParams"
    field-code="voiceprintEnabled"
  />
</template>
```

## 存储位置变更

| 旧位置 | 新位置 |
|--------|--------|
| `config.voiceprintRegistration` | `config.rounds[].algorithmParams` 中（field_code=voiceprintEnabled/voiceprintAudioId/...） |

## 引用关系

- ← `02_选用例/frontend/01_types.ts新接口定义` — AlgorithmParamItem 接口
- ← `02_选用例/frontend/10_RoundConfigEditor` — 在每轮内部挂载
- → 后端 `04_执行测试/backend/19_声纹注册模块` — 后端消费此配置
