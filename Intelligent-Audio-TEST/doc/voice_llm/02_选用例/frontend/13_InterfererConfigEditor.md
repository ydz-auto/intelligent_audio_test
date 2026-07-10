# 13_InterfererConfigEditor 干扰人配置编辑器

> 组件：`frontend/src/components/common/test-case/TestCaseModal/InterfererConfigEditor.vue`

## 功能说明

干扰人配置编辑器，用于配置 E2E 用例中的多路并行干扰音频播放。在 E2E test_type 时显示（配置驱动，不绑定算法类型）。

**位置变更**：从 CaseForm 顶层移入 RoundConfigEditor 的每轮内部，作为 DynamicForm 的子编辑器（param_type=interferer_list）。每轮可独立配置不同的干扰人。

**数据绑定变更**：v-model 绑定到 `test_cases.algorithm_params 独立列`（按轮分组，对应轮的 params 中）中 field_code='interferers' 的 field_value，而不是 `round.interferers`。

> **设计说明**：算法参数不再存于 `config.rounds[]` 中，而是独立存储在 `test_cases.algorithm_params` 列。该列结构为 `[{round_number, params:[{field_code, field_value}]}]`，按轮分组。干扰人配置存放在对应轮的 params 中 field_code='interferers' 的 field_value 中。`config.rounds[]` 只保留结构性字段（roundNumber/audios/backgroundNoise/evaluation）。

## Props / Events

```ts
interface Props {
  modelValue: AlgorithmParamItem[]     // algorithm_params 独立列中对应轮的 params 数组
  fieldCode: string                     // 'interferers'
}

interface Emits {
  'update:modelValue'(value: AlgorithmParamItem[])
}
```

## 组件模板

```vue
<template>
  <el-card class="interferer-config-editor">
    <template #header>
      <div class="card-header">
        <span>干扰人配置</span>
        <el-button @click="addInterferer" size="small">+ 添加干扰人</el-button>
      </div>
    </template>

    <div v-if="interferers.length === 0" class="empty-tip">
      未配置干扰人，点击"添加干扰人"开始配置
    </div>

    <el-card v-for="(item, index) in interferers" :key="item.id"
             class="interferer-item" shadow="hover">
      <div class="item-header">
        <span>干扰人 {{ index + 1 }}</span>
        <el-button @click="removeInterferer(index)" type="danger" size="small">
          删除
        </el-button>
      </div>

      <el-form label-width="120px" size="small">
        <!-- 干扰音频 -->
        <el-form-item label="干扰音频">
          <AudioSelectButton v-model="item.audioId" @open="openAudioModal(index)" />
        </el-form-item>

        <!-- 播放设备 -->
        <el-form-item label="播放设备">
          <DeviceSelector v-model="item.playbackDeviceId" :filter="dryDevices" />
        </el-form-item>

        <!-- 声压级 -->
        <el-form-item label="声压级(dB)">
          <el-input-number v-model="item.spl" :min="40" :max="100" :step="1" />
        </el-form-item>

        <!-- 开始延迟 -->
        <el-form-item label="开始延迟(秒)">
          <el-input-number v-model="item.startDelay" :min="0" :max="300" :step="1" />
          <span class="hint">相对于本轮开始的延迟时间</span>
        </el-form-item>

        <!-- 循环播放 -->
        <el-form-item label="循环播放">
          <el-switch v-model="item.loop" />
          <span class="hint">开启后持续循环播放，直到本轮结束自动停止</span>
        </el-form-item>
      </el-form>
    </el-card>
  </el-card>
</template>
```

> **说明**：不再需要"播放时长"字段。音频的生命周期由引擎统一管理：
> - `loop=true` → 循环播放，本轮结束时 `stop_task_audio()` 停止
> - `loop=false` → 播放一次后自然结束（与干声行为一致）

## algorithm_params 读写逻辑

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

const interferers = computed({
  get: () => {
    const raw = getAlgoParamValue(props.modelValue, 'interferers')
    if (!raw) return []
    if (typeof raw === 'string') return JSON.parse(raw)
    return raw
  },
  set: (val) => setAlgoParamValue('interferers', val)
})

function addInterferer() {
  const newItem: InterfererConfigItem = {
    id: `interferer_${Date.now()}`,
    audioId: '',
    playbackDeviceId: '',
    spl: 70,
    startDelay: 0,
    loop: true
  }
  interferers.value = [...interferers.value, newItem]
}

function removeInterferer(index: number) {
  const updated = interferers.value.filter((_, i) => i !== index)
  interferers.value = updated
}
```

## 显示条件

在 DynamicForm 内部，E2E test_type 时渲染（配置驱动，不绑定算法类型）：

```vue
<!-- 在 DynamicForm 内部，param_type=interferer_list 时渲染 -->
<!-- v-model 绑定 algorithm_params 独立列中对应轮的 params 数组 -->
<template v-if="testType === 'e2e'">
  <InterfererConfigEditor
    v-model="currentRoundParams"
    field-code="interferers"
  />
</template>
```

## 存储位置变更

| 旧位置 | 新位置 |
|--------|--------|
| `config.interferers` | `test_cases.algorithm_params 独立列`（按轮分组，对应轮的 params 中，field_code=interferers） |

### algorithm_params 独立列结构示例

```json
// test_cases.algorithm_params 列（按轮分组）
[
  {
    "round_number": 1,
    "params": [
      {
        "field_code": "interferers",
        "field_value": [
          {
            "id": "interferer_001",
            "audioId": "audio_002",
            "playbackDeviceId": "device_02",
            "spl": 65,
            "startDelay": 0,
            "loop": true
          },
          {
            "id": "interferer_002",
            "audioId": "audio_003",
            "playbackDeviceId": "device_03",
            "spl": 60,
            "startDelay": 5,
            "loop": false
          }
        ]
      }
    ]
  },
  {
    "round_number": 2,
    "params": [
      { "field_code": "interferers", "field_value": [] }
    ]
  }
]
```

> 注意：`config.rounds[]` 只保留结构性字段（roundNumber/audios/backgroundNoise/evaluation），不再包含算法参数。干扰人配置整体作为 field_code='interferers' 的 field_value 存储。

## 引用关系

- ← `02_选用例/frontend/01_types.ts新接口定义` — AlgorithmParamItem/InterfererConfigItem 接口
- ← `02_选用例/frontend/10_RoundConfigEditor` — 在每轮内部挂载
- → 后端 `04_执行测试/backend/20_干扰人播放模块` — 后端消费此配置
