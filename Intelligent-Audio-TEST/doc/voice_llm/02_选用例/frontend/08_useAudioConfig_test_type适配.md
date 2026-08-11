# 08_useAudioConfig test_type 适配

> 文件：`frontend/src/components/common/test-case/TestCaseModal/useAudioConfig.ts`

## 现状分析

useAudioConfig（720行）是用例编辑中音频配置的核心 Composable，管理音频列表、播放设备、声压级、拖拽排序等功能。

### 当前 test_type 处理

音频配置基于 `AudioConfig.testType`（每条音频独立标记 api/e2e）：

```ts
// handleDeviceSelect — 为 E2E 音频选择播放设备
function handleDeviceSelect(devices: Device[]) {
  // 直接操作 audioConfig.playbackDeviceId
}

// handleBatchDeviceSelect — 批量为所有 E2E 音频选设备
function handleBatchDeviceSelect(devices: Device[]) {
  // 遍历 formData.config.audios 中 testType === 'e2e' 的项
}
```

### 关键函数

| 函数 | 行号 | 用途 |
|------|------|------|
| `loadResources` | 44-96 | 加载播放设备和音频列表 |
| `handleAudioSelect` | 174-188 | 选择单条音频 |
| `handleMultipleAudioSelect` | 190-237 | 多条音频批量添加 |
| `handleDeviceSelect` | 239-244 | 为 E2E 音频选设备 |
| `handleBatchDeviceSelect` | 251-261 | 批量选设备 |
| `handleBatchSplConfirm` | 273-280 | 批量设 SPL |
| `addAudioConfig` | 282-290 | 添加空音频配置 |
| `removeAudioConfig` | 292-299 | 移除音频配置 |
| `copyAudioConfig` | 301-313 | 复制音频配置 |

## 改造方案

### 1. 接收用例级别 test_type

```ts
export function useAudioConfig(testType: Ref<'api' | 'e2e'>) {
  // test_type 由外部传入，不再从音频级别推断
  const isE2E = computed(() => testType.value === 'e2e')
```

### 2. API 音频简化

API 用例的音频只需要 `audioId` + `playOrder`，不需要播放设备和 SPL：

```ts
// 添加音频配置
function addAudioConfig() {
  const newConfig: AudioConfig = {
    audioId: '',
    playbackDeviceId: isE2E.value ? '' : '',  // API 用例留空
    spl: isE2E.value ? 75 : 0,                 // API 用例默认 0
    playOrder: audioConfigs.value.length + 1
  }
  audioConfigs.value.push(newConfig)
}
```

### 3. 批量设备/SPL 操作简化

不再需要判断 `testType`，因为所有音频都属于同一 test_type：

```ts
// 改造后
function handleBatchDeviceSelect(devices: Device[]) {
  // 所有音频都是 E2E，直接批量设置
  const device = devices[0]
  audioConfigs.value.forEach(audio => {
    audio.playbackDeviceId = device.id
  })
}

function handleBatchSplConfirm(spl: number) {
  audioConfigs.value.forEach(audio => {
    audio.spl = spl
  })
}
```

### 4. UI 显隐控制

```ts
// 以下功能仅 E2E 用例显示
const showDeviceControls = computed(() => isE2E.value)
const showBatchDeviceModal = computed(() => isE2E.value)
const showBatchSplModal = computed(() => isE2E.value)
const showCrossDeviceModal = computed(() => isE2E.value)
```

### 5. 拖拽排序不变

拖拽排序逻辑（`handleAudioDragStart/End/Over/Drop`）不依赖 test_type，保持不变。

### 6. 标签交叉播放不变

`interleaveByTags` 和 `assignDeviceByTags` 不依赖 test_type，保持不变。

## 不变部分

- `loadResources` — 加载播放设备和音频列表
- 拖拽排序（drag & drop）
- Fisher-Yates 洗牌（shuffleAudioConfigs）
- 按文件名排序（sortByFileName）
- 标签管理（toggleTagSelector, toggleTagSelection）
- 标签交叉播放（interleaveByTags）
- 噪声配置（clearNoiseConfig, getNoiseDeviceNames）
- 音频标签同步（syncAudioTagsToCase）

## 引用关系

- ← `02_选用例/frontend/01_types.ts新接口定义` — AudioConfig 接口
- ← `02_选用例/frontend/06_CaseForm_test_type驱动` — CaseForm 调用 useAudioConfig
- → `02_选用例/frontend/09_useDimensionConfig扁平维度` — 维度配置适配
