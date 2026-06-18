# 20 — TestCaseReportDetail 多轮结果

> **所属步骤**：05_查看结果 → frontend  
> **改造类型**：修改  
> **涉及文件**：`frontend/src/components/common/TestCaseReportDetail.vue`

---

## 背景

`TestCaseReportDetail` 展示单个测试用例的详细结果，包括评分指标、文本对比、时间线数据等。voice_llm 多轮结果需要在报告中按轮次展示每轮的输入/输出/延迟/评分，并展示每轮的配置（音频、噪声、算法参数）和参考参数文件内容。

API 和 E2E 的结果结构不同：
- **API**：`roundNumber` (1-indexed)，`input.text`，`output` (string)，`round_evaluation`，无顶层 `aggregated`
- **E2E**：`round` (0-indexed)，`input.audio_name/audio_path/type`，`output.asr_text/device_raw`，`evaluation`，有顶层 `aggregated`

---

## 改造内容

### 1. 多轮结果检测与类型判断

```typescript
const isMultiRound = computed(() => {
  const result = props.algorithmResults?.[0];
  if (!result) return false;

  const parsed = typeof result === 'string'
    ? JSON.parse(result)
    : result;

  return Array.isArray(parsed?.rounds) && parsed.rounds.length > 0;
});

const testType = computed(() => {
  const parsed = typeof props.algorithmResults?.[0] === 'string'
    ? JSON.parse(props.algorithmResults[0])
    : props.algorithmResults?.[0];
  return parsed?.test_type || 'api';
});

const isE2E = computed(() => testType.value === 'e2e');

const multiRoundData = computed(() => {
  if (!isMultiRound.value) return null;

  const parsed = typeof props.algorithmResults?.[0] === 'string'
    ? JSON.parse(props.algorithmResults[0])
    : props.algorithmResults?.[0];

  return parsed?.rounds || [];
});

const roundConfigs = computed(() => {
  const config = props.testCaseConfig;
  if (!config?.rounds) return [];
  return config.rounds;
});
```

### 2. 多轮展示区域

```vue
<!-- 多轮结果展示 -->
<div v-if="isMultiRound" class="multi-round-section">
  <h3>多轮对话结果 ({{ multiRoundData.length }} 轮)</h3>

  <!-- 聚合指标概览 -->
  <div class="aggregated-metrics" v-if="aggregatedMetrics">
    <div class="metric-card" v-for="(value, key) in aggregatedMetrics" :key="key">
      <span class="metric-label">{{ metricLabel(key) }}</span>
      <span class="metric-value">{{ formatValue(value) }}</span>
    </div>
  </div>

  <!-- 每轮详情（可折叠） -->
  <div class="round-list">
    <div
      v-for="(round, idx) in multiRoundData"
      :key="idx"
      class="round-item"
      :class="{ expanded: expandedRounds.includes(idx) }"
    >
      <div class="round-header" @click="toggleRound(idx)">
        <!-- API: roundNumber(1-indexed); E2E: round(0-indexed) -->
        <span class="round-number">
          第 {{ isE2E ? (round.round + 1) : round.roundNumber }} 轮
        </span>
        <span class="round-latency">延迟: {{ round.latency?.toFixed(2) }}s</span>
        <span class="round-interruption" v-if="isE2E && round.interruption?.detected">
          打断: {{ round.interruption.timestamp?.toFixed(2) }}s
        </span>
        <span class="expand-icon">{{ expandedRounds.includes(idx) ? '▼' : '▶' }}</span>
      </div>

      <div v-if="expandedRounds.includes(idx)" class="round-detail">
        <!-- 配置回顾 -->
        <div class="round-config">
          <span class="config-label">本轮配置:</span>
          <span v-if="roundConfigs[idx]?.backgroundNoise">
            噪声: {{ roundConfigs[idx].backgroundNoise.audioId }}
            ({{ roundConfigs[idx].backgroundNoise.spl }}dB)
          </span>
          <span v-if="getAlgoParam(roundConfigs[idx], 'railDistance')">
            导轨: {{ getAlgoParam(roundConfigs[idx], 'railDistance') }}cm
          </span>
          <span v-if="getAlgoParam(roundConfigs[idx], 'volumeLevel')">
            音量: {{ getAlgoParam(roundConfigs[idx], 'volumeLevel') }}%
          </span>
        </div>

        <!-- 输入：API 用 input.text，E2E 用 input.audio_name/audio_path/type -->
        <div class="round-io">
          <span class="io-label">输入:</span>
          <span class="io-value">
            <template v-if="isE2E">
              {{ round.input?.audio_name }}
              <span v-if="round.input?.audio_path" class="io-path">({{ round.input.audio_path }})</span>
              <span v-if="round.input?.type" class="io-type">[{{ round.input.type }}]</span>
            </template>
            <template v-else>
              {{ round.input?.text }}
            </template>
          </span>
        </div>

        <!-- 输出：API 用 string，E2E 用 output.asr_text + device_raw -->
        <div class="round-io">
          <span class="io-label">输出:</span>
          <span class="io-value">
            <template v-if="isE2E">
              {{ round.output?.asr_text }}
            </template>
            <template v-else>
              {{ round.output }}
            </template>
          </span>
        </div>

        <!-- E2E: device_raw 展示 -->
        <div class="round-io" v-if="isE2E && round.output?.device_raw">
          <span class="io-label">设备原始数据:</span>
          <span class="io-value">{{ JSON.stringify(round.output.device_raw) }}</span>
        </div>

        <!-- 参考参数 -->
        <div class="round-reference" v-if="roundReferences[idx]">
          <span class="io-label">参考:</span>
          <span class="io-value">{{ roundReferences[idx].text || roundReferences[idx].reference_text }}</span>
        </div>

        <!-- 评估分数：API 用 round_evaluation，E2E 用 evaluation -->
        <div class="round-eval" v-if="roundEvalData(round)">
          <span v-for="(score, dim) in roundEvalData(round)" :key="dim" class="eval-badge">
            {{ dim }}: {{ formatValue(score) }}
          </span>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- 非多轮结果：现有展示逻辑 -->
<div v-else>
  <!-- ... 现有的单结果展示 ... -->
</div>
```

### 3. 轮次展开/收起与聚合指标

```typescript
const expandedRounds = ref<number[]>([]);

function toggleRound(idx: number) {
  const pos = expandedRounds.value.indexOf(idx);
  if (pos >= 0) {
    expandedRounds.value.splice(pos, 1);
  } else {
    expandedRounds.value.push(idx);
  }
}

const aggregatedMetrics = computed(() => {
  const parsed = typeof props.algorithmResults?.[0] === 'string'
    ? JSON.parse(props.algorithmResults[0])
    : props.algorithmResults?.[0];

  // E2E: 直接使用顶层 aggregated
  if (parsed?.aggregated) {
    return parsed.aggregated;
  }

  // API: 没有顶层 aggregated，需从 rounds 的 round_evaluation 中计算
  if (isMultiRound.value && parsed?.rounds) {
    return computeAggregatedFromRounds(parsed.rounds, 'round_evaluation');
  }

  return null;
});

function computeAggregatedFromRounds(rounds: any[], evalKey: string): Record<string, number> {
  const evals = rounds
    .map(r => r[evalKey])
    .filter(Boolean);
  if (evals.length === 0) return {};

  return {
    avg_wer: evals.reduce((s, e) => s + (e.wer || 0), 0) / evals.length,
    avg_llm_judge: evals.reduce((s, e) => s + (e.llm_judge || 0), 0) / evals.length,
    avg_latency: rounds.reduce((s, r) => s + (r.latency || 0), 0) / rounds.length,
  };
}
```

### 4. 评估数据提取（区分 API / E2E）

```typescript
function roundEvalData(round: any): Record<string, number> | null {
  // API: round_evaluation; E2E: evaluation
  return round.round_evaluation || round.evaluation || null;
}
```

### 5. 读取参考参数文件

每轮的参考参数通过 `roundConfigs[idx].referenceParamsPath` 引用，文件内容按需懒加载：

```typescript
const referenceCache = ref<Record<string, any>>({});
const roundReferences = ref<Record<number, any>>({});

async function loadRoundReference(idx: number) {
  const config = roundConfigs.value[idx];
  if (!config?.referenceParamsPath) return;

  const path = config.referenceParamsPath;
  if (referenceCache.value[path]) {
    roundReferences.value[idx] = referenceCache.value[path];
    return;
  }

  const ref = await casesApi.getReferenceContent(path);
  referenceCache.value[path] = ref;
  roundReferences.value[idx] = ref;
}

watch(expandedRounds, (newVal) => {
  for (const idx of newVal) {
    if (!roundReferences.value[idx]) {
      loadRoundReference(idx);
    }
  }
});
```

### 6. 工具方法

```typescript
function getAlgoParam(roundConfig: any, fieldCode: string): string | null {
  if (!roundConfig?.algorithmParams) return null;
  const item = roundConfig.algorithmParams.find(
    (p: any) => p.field_code === fieldCode
  );
  return item?.field_value ?? null;
}

function metricLabel(key: string): string {
  const labels: Record<string, string> = {
    avg_wer: '平均 WER',
    avg_latency: '平均延迟',
    avg_llm_judge: '平均 LLM 评分',
    interruption_count: '打断次数',
    total_latency: '总延迟',
  };
  return labels[key] || key;
}
```

### 7. 视觉效果

```
┌─ 多轮对话结果 (3 轮) ─────────────────────────────────────────────┐
│                                                                     │
│  平均 WER: 0.05  平均延迟: 1.80s  打断次数: 1                       │
│                                                                     │
│  ▼ 第 1 轮  延迟: 2.10s                                            │
│    本轮配置: 噪声:noise_005(50dB)  导轨:50cm  音量:70%              │
│    输入: round1.wav (/audios/round1.wav) [audio]                    │
│    输出: 今天天气怎么样                                              │
│    设备原始数据: [...]                                               │
│    参考: 今天天气怎么样啊  (来自 /references/round1_ref.json)         │
│    WER: 0.03  LLM Judge: 4.5                                       │
│                                                                     │
│  ▶ 第 2 轮  延迟: 1.50s  打断: 1.80s                               │
│  ▶ 第 3 轮  延迟: 1.80s                                            │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 数据来源说明

| 数据 | API 来源 | E2E 来源 |
|------|---------|---------|
| 轮次编号 | `rounds[idx].roundNumber` (1-indexed) | `rounds[idx].round` (0-indexed) |
| 输入 | `rounds[idx].input.text` | `rounds[idx].input.audio_name/audio_path/type` |
| 输出 | `rounds[idx].output` (string) | `rounds[idx].output.asr_text/device_raw` |
| 评估 | `rounds[idx].round_evaluation` | `rounds[idx].evaluation` |
| 打断 | — | `rounds[idx].interruption` |
| 聚合 | 从 rounds 计算（无顶层 aggregated） | `algorithm_result.aggregated` |
| 每轮配置 | `testcase.config.rounds[idx]` | `testcase.config.rounds[idx]` |
| 参考参数 | `rounds[idx].referenceParamsPath` | `rounds[idx].referenceParamsPath` |

---

## 不变部分

- 非多轮结果的展示逻辑不变
- 评分指标的 DataTable 不变
- 音频播放和时间线对比不变
- Props 接口不变（algorithmResults 类型兼容）

---

## 依赖关系

| 依赖文档 | 说明 |
|---------|------|
| `02_选用例/backend/03_Config_JSON扁平化设计.md` | config 结构定义 |
| `02_选用例/backend/10_reference_params_generator适配.md` | referenceParams 文件生成 |
| `04_执行测试/backend/23_E2E测试结果存储结构.md` | algorithm_result 结构 |
| `04_执行测试/backend/16_API测试结果存储结构.md` | algorithm_result 结构 |
| `22_reportService多轮数据` | 数据获取和传递 |
