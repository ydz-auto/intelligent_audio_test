<template>
  <div class="batch-noise-modal">
    <div class="modal-header">
      <h3>{{ title }}</h3>
      <p class="case-count">将为 {{ caseCount }} 个用例设置噪声配置</p>
    </div>
    
    <div class="modal-body">
      <div class="form-group">
        <label>噪声音频</label>
        <div class="audio-selector-container" @click="openAudioSelectModal">
          <div class="selected-audio-info" v-if="selectedAudioName">
            {{ selectedAudioName }}
          </div>
          <div class="placeholder" v-else>
            点击选择噪声音频
          </div>
        </div>
        <div class="audio-actions" v-if="selectedAudioName">
          <button type="button" class="btn btn-secondary" @click="openAudioSelectModal">
            <i class="fas fa-search"></i> 重新选择
          </button>
          <button type="button" class="btn btn-danger" @click="clearAudio">
            <i class="fas fa-times"></i> 清除
          </button>
        </div>
      </div>
      
      <div class="form-group">
        <label>噪声声压级 (dB)</label>
        <input 
          type="number" 
          v-model.number="spl" 
          class="form-input" 
          min="0" 
          max="140" 
          placeholder="例如：94" 
        />
        <p class="form-hint">建议值：94 dB（1kHz 校准点）</p>
      </div>
      
      <div class="form-group">
        <label>播放设备</label>
        <div class="device-selector-container" @click="openDeviceSelectModal">
          <div class="selected-device-info" v-if="selectedDeviceNames">
            {{ selectedDeviceNames }}
          </div>
          <div class="placeholder" v-else>
            点击选择播放设备
          </div>
        </div>
        <div class="device-actions" v-if="selectedDeviceNames">
          <button type="button" class="btn btn-secondary" @click="openDeviceSelectModal">
            <i class="fas fa-search"></i> 重新选择
          </button>
          <button type="button" class="btn btn-danger" @click="clearDevices">
            <i class="fas fa-times"></i> 清除
          </button>
        </div>
      </div>

      <div class="scope-section">
        <label>轮次范围</label>
        <div class="radio-group">
          <label class="radio-label">
            <input type="radio" :value="'all'" v-model="roundMode" />
            <span>所有轮次</span>
          </label>
          <label class="radio-label">
            <input type="radio" :value="'specific'" v-model="roundMode" />
            <span>指定轮次</span>
          </label>
        </div>
        <div class="round-checkboxs" v-if="roundMode === 'specific'">
          <label v-for="rn in availableRoundNumbers" :key="rn" 
                 :class="{ checked: roundNumbers.includes(rn) }"
                 @click="toggleRoundNumber(rn)">
            第{{ rn }}轮
          </label>
        </div>
      </div>

      <div class="scope-section">
        <label>应用层级（可多选）</label>
        <div class="level-checkboxs">
          <label class="level-label">
            <input type="checkbox" value="caseBackgroundNoise" v-model="targets" />
            <span>case级背景噪声</span>
          </label>
          <label class="level-label">
            <input type="checkbox" value="segmentBackgroundNoise" v-model="targets" />
            <span>segment级背景噪声</span>
          </label>
          <label class="level-label">
            <input type="checkbox" value="interferer" v-model="targets" />
            <span>干扰人</span>
          </label>
        </div>
      </div>
    </div>
    
    <div class="modal-footer">
      <button type="button" class="btn btn-secondary" @click="handleCancel">取消</button>
      <button type="button" class="btn btn-primary" @click="handleConfirm">确定</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { getModalManager } from '../../../composables/useModal'
import { MODAL_TYPES } from '../../../shared/types'
import { playbackApi } from '../../../utils/api'

interface Props {
  modalId: string
  title?: string
  caseCount?: number
  maxRoundNumbers?: number
}

interface Emits {
  (e: 'close'): void
  (e: 'confirm', data: { audioId: string; spl: number; deviceIds: string[]; targets: string[]; roundMode: string; roundNumbers: number[] }): void
  (e: 'cancel'): void
}

const props = withDefaults(defineProps<Props>(), {
  title: '批量设置噪声',
  caseCount: 0,
  maxRoundNumbers: 3
})

const emit = defineEmits<Emits>()

const selectedAudioId = ref('')
const selectedAudioName = ref('')
const spl = ref(55)
const selectedDeviceIds = ref<string[]>([])
const selectedDeviceNames = ref('')
const playbackDevices = ref<any[]>([])
const roundMode = ref<'all' | 'specific'>('all')
const roundNumbers = ref<number[]>([])
const targets = ref<string[]>(['caseBackgroundNoise', 'segmentBackgroundNoise'])

const availableRoundNumbers = computed(() => {
  return Array.from({ length: props.maxRoundNumbers }, (_, i) => i + 1)
})

function toggleRoundNumber(rn: number) {
  const idx = roundNumbers.value.indexOf(rn)
  if (idx >= 0) {
    roundNumbers.value.splice(idx, 1)
  } else {
    roundNumbers.value.push(rn)
  }
}

onMounted(async () => {
  try {
    const result = await playbackApi.getAll()
    playbackDevices.value = (result as any)?.items || []
  } catch (error) {
    console.error('加载播放设备失败:', error)
    playbackDevices.value = []
  }
})

async function openAudioSelectModal() {
  const modalManager = getModalManager()
  try {
    const result = await modalManager.open(MODAL_TYPES.AUDIO_SELECT, {
      title: '选择噪声音频',
      audioType: 'noise',
      isMultiSelect: false
    })
    if (result && result.id) {
      selectedAudioId.value = result.id
      selectedAudioName.value = result.name || result.filename || result.fileName || result.id
    }
  } catch (error) {
    console.error('选择音频失败:', error)
  }
}

function clearAudio() {
  selectedAudioId.value = ''
  selectedAudioName.value = ''
}

async function openDeviceSelectModal() {
  const modalManager = getModalManager()
  try {
    const result = await modalManager.open(MODAL_TYPES.GLOBAL_PLAYBACK_DEVICE, {
      title: '选择噪声播放设备',
      isMultiSelect: true,
      initialSelectedDevices: selectedDeviceIds.value,
      playbackDevices: playbackDevices.value,
      audioType: 'noise',
      showScanDevices: true,
      isRequired: false
    })
    if (result && Array.isArray(result)) {
      selectedDeviceIds.value = result
      await loadDeviceNames(result)
    }
  } catch (error) {
    console.error('选择设备失败:', error)
  }
}

async function loadDeviceNames(deviceIds: string[]) {
  try {
    const result = await playbackApi.getAll()
    const devices = (result as any).items || []
    const names = deviceIds.map(id => {
      const device = devices.find((d: any) => d.id === id)
      return device ? device.name : id
    })
    selectedDeviceNames.value = names.join(', ')
  } catch (error) {
    console.error('加载设备名称失败:', error)
    selectedDeviceNames.value = deviceIds.join(', ')
  }
}

function clearDevices() {
  selectedDeviceIds.value = []
  selectedDeviceNames.value = ''
}

function handleConfirm() {
  emit('confirm', {
    audioId: selectedAudioId.value,
    spl: spl.value,
    deviceIds: selectedDeviceIds.value,
    targets: targets.value,
    roundMode: roundMode.value,
    roundNumbers: roundNumbers.value
  })
}

function handleCancel() {
  emit('cancel')
}
</script>

<style scoped>
.batch-noise-modal {
  padding: 20px;
}

.modal-header {
  margin-bottom: 20px;
}

.modal-header h3 {
  margin: 0 0 8px 0;
  font-size: 18px;
  color: #333;
}

.case-count {
  margin: 0;
  color: #666;
  font-size: 14px;
}

.modal-body {
  max-height: 400px;
  overflow-y: auto;
}

.form-group {
  margin-bottom: 16px;
}

.form-group > label {
  display: block;
  margin-bottom: 6px;
  font-weight: 500;
  color: #333;
}

.audio-selector-container,
.device-selector-container {
  padding: 12px;
  background: #f8fafc;
  border: 1px dashed #cbd5e1;
  border-radius: 8px;
  cursor: pointer;
  text-align: center;
  min-height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.audio-selector-container:hover,
.device-selector-container:hover {
  border-color: #1677ff;
  background: #f0f7ff;
  border-style: solid;
}

.selected-audio-info,
.selected-device-info {
  color: #333;
  font-size: 14px;
}

.placeholder {
  color: #999;
  font-size: 14px;
}

.audio-actions,
.device-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.form-input {
  width: 100%;
  padding: 10px 14px;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  font-size: 14px;
  transition: all 0.2s ease;
}

.form-input:focus {
  outline: none;
  border-color: #1677ff;
  box-shadow: 0 0 0 3px rgba(22, 119, 255, 0.1);
}

.form-hint {
  margin: 6px 0 0 0;
  font-size: 12px;
  color: #999;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid #e5e7eb;
}

.btn {
  padding: 10px 20px;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  border: none;
  transition: all 0.2s ease;
}

.btn-secondary {
  background: #f3f4f6;
  color: #374151;
  border: 1px solid #d1d5db;
}

.btn-secondary:hover {
  background: #e5e7eb;
}

.btn-primary {
  background: linear-gradient(135deg, #1677ff 0%, #4096ff 100%);
  color: #fff;
  box-shadow: 0 2px 8px rgba(22, 119, 255, 0.25);
}

.btn-primary:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(22, 119, 255, 0.35);
}

.btn-danger {
  background: linear-gradient(135deg, #dc3545 0%, #c82333 100%);
  color: #fff;
  box-shadow: 0 2px 8px rgba(220, 53, 69, 0.25);
}

.btn-danger:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(220, 53, 69, 0.35);
}

.scope-section {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}
.scope-section > label {
  display: block;
  margin-bottom: 12px;
  font-weight: 600;
  font-size: 14px;
  color: #333;
}
.radio-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 12px;
}
.radio-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  cursor: pointer;
}
.round-checkboxs {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding-left: 24px;
}
.round-checkboxs label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  cursor: pointer;
  padding: 4px 12px;
  border: 1px solid #d1d5db;
  border-radius: 20px;
  background: #fff;
}
.round-checkboxs label.checked {
  border-color: #1677ff;
  background: #e6f4ff;
  color: #1677ff;
}
.level-checkboxs {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.level-checkboxs label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  cursor: pointer;
}
.level-hint {
  font-size: 11px;
  color: #999;
  margin-left: 20px;
}
</style>
