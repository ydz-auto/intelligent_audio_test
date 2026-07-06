<template>
  <div class="round-config-editor">
    <!-- ===== 左侧：轮次导航 ===== -->
    <RoundNav
      :rounds="localRounds"
      :active-index="activeRoundIndex"
      @update:active-index="activeRoundIndex = $event"
      @add="addRound"
      @copy="copyCurrentRound"
    />

    <!-- ===== 右侧：轮次头部 + 步骤导航 + 内容区 ===== -->
    <div class="rce-right">
      <!-- 轮次头部 -->
      <RoundHead
        v-if="currentRound"
        :round="currentRound"
        :active-index="activeRoundIndex"
        :total-rounds="localRounds.length"
        @update:active-index="activeRoundIndex = $event"
        @copy="copyCurrentRound"
        @delete="removeCurrentRound"
      />

      <!-- 横向步骤导航 -->
      <StepToc
        :steps="steps"
        :active-step="activeStep"
        @select="scrollToStep"
      />

      <div class="rce-content-area" ref="contentAreaRef">
        <!-- 空状态 -->
        <div v-if="!currentRound" class="rce-empty">
          <i class="fas fa-info-circle"></i> 暂无轮次，请点击"添加轮次"
        </div>

        <!-- ===== 步骤 1: 算法参数 ===== -->
        <AlgoParamsStep
          v-if="currentRound"
          :round="currentRound"
          :api-input-params="apiInputParams || []"
          :case-algorithm-params="caseAlgorithmParams || []"
          :algorithm-form-schema="algorithmFormSchema"
          :test-type="effectiveTestType"
          @update:round="updateCurrentRoundData"
          @open-audio-select="handleAudioSelect"
        />

        <!-- ===== 步骤 2: 音频列表 ===== -->
        <AudioListStep
          v-if="currentRound"
          :round="currentRound"
          @update:round="updateCurrentRoundData"
          @open-audio-select="handleAudioSelect"
          @open-device-modal="(audioIndex: number) => emit('openDeviceModal', audioIndex)"
          @open-batch-device-modal="() => emit('openBatchDeviceModal')"
          @open-cross-device-modal="() => emit('openCrossDeviceModal')"
          @open-batch-spl-modal="() => emit('openBatchSplModal')"
          @preview-audio="(audioId: string) => emit('previewAudio', audioId, 'dry')"
        />

        <!-- ===== 步骤 3: 噪声 & 干扰 (仅 E2E) ===== -->
        <NoiseInterferenceStep
          v-if="currentRound && effectiveTestType === 'e2e'"
          :round="currentRound"
          :playback-devices="playbackDevices"
          :has-voiceprint-param="hasVoiceprintParam"
          :has-interferer-param="hasInterfererParam"
          @update:round="updateCurrentRoundData"
          @open-audio-select="handleAudioSelect"
          @preview-audio="(audioId: string) => emit('previewAudio', audioId, 'noise')"
        />

        <!-- ===== 步骤 4: 评估维度 ===== -->
        <div class="rce-step" id="step-eval" v-if="currentRound">
          <div class="rce-step-header">
            <i class="fas fa-chart-bar rce-step-icon"></i>
            <span class="rce-step-title">评估维度</span>
            <span class="rce-tag rce-tag-green">round.evaluation</span>
          </div>
          <RoundEvaluationEditor
            :model-value="currentRound.evaluation"
            :available-dimensions="availableDimensions"
            :algorithm-type="algorithmType"
            @update:model-value="(v: RoundEvaluationConfig) => updateCurrentRound('evaluation', v)"
          />
        </div>

        <!-- ===== 步骤 5: 参考参数（只读） ===== -->
        <ReferencePathStep v-if="currentRound" :round="currentRound" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, inject, nextTick } from 'vue'
import type {
  RoundConfigItem,
  AlgorithmParamItem,
  RoundEvaluationConfig,
} from './types'
import type { Dimension, PlaybackDevice } from '../../../../shared/types'
import RoundEvaluationEditor from './RoundEvaluationEditor.vue'
import RoundNav from './sections/RoundNav.vue'
import StepToc from './sections/StepToc.vue'
import RoundHead from './sections/RoundHead.vue'
import AlgoParamsStep from './sections/AlgoParamsStep.vue'
import AudioListStep from './sections/AudioListStep.vue'
import NoiseInterferenceStep from './sections/NoiseInterferenceStep.vue'
import ReferencePathStep from './sections/ReferencePathStep.vue'

// ---- Props ----
const props = defineProps<{
  modelValue?: RoundConfigItem[]
  testType?: 'api' | 'e2e'
  caseAlgorithmParams?: any[]
  apiInputParams?: any[]
  algorithmType?: string
  algorithmFormSchema?: any
}>()

const emit = defineEmits<{
  'update:modelValue': [value: RoundConfigItem[]]
  'openAudioSelect': [audioType: 'dry' | 'noise', callback: (audios: { id: string; name?: string }[]) => void]
  'openDeviceModal': [audioIndex: number]
  'openBatchDeviceModal': []
  'openCrossDeviceModal': []
  'openBatchSplModal': []
  'previewAudio': [audioId: string, audioType: 'dry' | 'noise']
}>()

// ---- Injects ----
const playbackDevices = inject<PlaybackDevice[]>('playbackDevices', [])
const availableDimensions = inject<Dimension[]>('availableDimensions', [])

// ---- 本地状态 ----
const localRounds = ref<RoundConfigItem[]>([])
const activeRoundIndex = ref(0)

// Reset step view when switching rounds
watch(() => activeRoundIndex.value, () => {
  activeStep.value = "algo";
});
const activeStep = ref('algo')
const contentAreaRef = ref<HTMLElement>()

// 同步 modelValue → 本地
watch(
  () => props.modelValue,
  (val) => {
    if (val && val.length > 0) {
      localRounds.value = val
    }
  },
  { immediate: true, deep: true }
)

// ---- 当前轮次 ----
const currentRound = computed(() => localRounds.value[activeRoundIndex.value] || null)
const effectiveTestType = computed(() => props.testType || 'api')

// ---- 步骤定义 ----
const steps = computed(() => {
  const base = [
    { id: 'algo', num: 1, label: '算法参数', icon: 'fas fa-sliders-h' },
    { id: 'audio', num: 2, label: '音频列表', icon: 'fas fa-music' },
  ]
  if (effectiveTestType.value === 'e2e') {
    base.push({ id: 'noise', num: 3, label: '噪声 & 干扰', icon: 'fas fa-volume-up' })
  }
  base.push({ id: 'eval', num: base.length + 1, label: '评估维度', icon: 'fas fa-chart-bar' })
  base.push({ id: 'ref', num: base.length + 2, label: '参考参数', icon: 'fas fa-file-alt' })
  return base
})

// ---- 参数过滤 ----
const filteredCaseParams = computed(() => {
  const params = props.caseAlgorithmParams || []
  const tt = effectiveTestType.value
  return params.filter(
    (p: any) => p.scope === 'common' || p.scope === tt || !p.scope
  )
})

const hasVoiceprintParam = computed(() =>
  filteredCaseParams.value.some((p: any) => p.param_code === 'voiceprintEnabled')
)
const hasInterfererParam = computed(() =>
  filteredCaseParams.value.some((p: any) => p.param_code === 'interferers')
)

// ---- 轮次操作 ----
function createEmptyRound(number: number): RoundConfigItem {
  const defaultParams: AlgorithmParamItem[] = []
  for (const param of (props.caseAlgorithmParams || [])) {
    if (param.default_value !== undefined && param.default_value !== null && param.default_value !== '') {
      defaultParams.push({ field_code: param.param_code, field_value: param.default_value })
    }
  }
  return {
    roundNumber: number,
    audios: [],
    algorithmParams: defaultParams,
  }
}

function addRound() {
  if (localRounds.value.length === 0) {
    localRounds.value = [createEmptyRound(1)]
  } else {
    const source = localRounds.value[localRounds.value.length - 1]
    const newRound = JSON.parse(JSON.stringify(source))
    newRound.roundNumber = localRounds.value.length + 1
    delete newRound.referenceParamsPath
    localRounds.value = [...localRounds.value, newRound]
  }
  activeRoundIndex.value = localRounds.value.length - 1
  emitUpdate()
}

function copyCurrentRound() {
  if (!currentRound.value) return
  const copy = JSON.parse(JSON.stringify(currentRound.value))
  copy.roundNumber = localRounds.value.length + 1
  delete copy.referenceParamsPath
  localRounds.value = [...localRounds.value, copy]
  activeRoundIndex.value = localRounds.value.length - 1
  emitUpdate()
}

function removeCurrentRound() {
  if (localRounds.value.length <= 1) return
  if (!confirm('确定要删除第 ' + (activeRoundIndex.value + 1) + ' 轮吗？该操作不可撤销。')) return
  const idx = activeRoundIndex.value
  localRounds.value = localRounds.value
    .filter((_, i) => i !== idx)
    .map((r, i) => ({ ...r, roundNumber: i + 1 }))
  activeRoundIndex.value = Math.min(activeRoundIndex.value, localRounds.value.length - 1)
  emitUpdate()
}

// ---- 通用更新 ----
function updateCurrentRoundData(updatedRound: RoundConfigItem) {
  if (!currentRound.value) return
  localRounds.value = localRounds.value.map((r, i) =>
    i === activeRoundIndex.value ? updatedRound : r
  )
  emitUpdate()
}

function updateCurrentRound(key: keyof RoundConfigItem, value: unknown) {
  if (!currentRound.value) return
  ;(currentRound.value as any)[key] = value
  emitUpdate()
}

function handleAudioSelect(audioType: 'dry' | 'noise', callback: (audios: { id: string; name?: string }[]) => void) {
  emit('openAudioSelect', audioType, callback)
}

defineExpose({
  activeRoundIndex
});

// ---- 步骤导航 ----
function scrollToStep(stepId: string) {
  activeStep.value = stepId
  nextTick(() => {
    const el = contentAreaRef.value?.querySelector(`#step-${stepId}`)
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}

// ---- 辅助 ----
// ---- Round validation ----
function isRoundValid(round: RoundConfigItem): boolean {
  const audios = round.audios || []
  return audios.some((a: any) => a.audioId && a.audioId.trim() !== '')
}

function emitUpdate() {
  emit('update:modelValue', [...localRounds.value])
}

// ---- 初始化 ----
onMounted(() => {
  if (!localRounds.value.length) {
    localRounds.value = [createEmptyRound(1)]
    emitUpdate()
  }
})
</script>

<style scoped>
.round-config-editor {
  display: flex;
  max-height: 60vh;
  min-height: 400px;
  gap: 0;
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 8px;
  overflow: hidden;
}

.rce-right {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}

.rce-content-area {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
  background: var(--background-primary, #fff);
}

/* 评估维度步骤的共享样式 */
.rce-step {
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid #f0f0f0;
}
.rce-step:last-child { border-bottom: none; }

.rce-step-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.rce-step-icon { font-size: 14px; color: var(--primary-color, #ff6a00); }
.rce-step-title { font-size: 14px; font-weight: 600; color: var(--text-primary, #333); }

.rce-tag {
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 10px;
  font-weight: 500;
}
.rce-tag-green { background: #e8f5e9; color: #4caf50; }
.rce-tag-gray { background: #f5f5f5; color: #999; }

.rce-empty {
  padding: 40px;
  text-align: center;
  color: var(--text-light, #999);
  font-size: 14px;
}
.rce-empty i { margin-right: 6px; }
</style>
