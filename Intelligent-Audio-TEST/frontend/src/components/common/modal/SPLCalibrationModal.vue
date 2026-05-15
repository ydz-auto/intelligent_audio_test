<template>
  <div class="spl-calibration-modal">
    <div class="modal-header">
      <h3>{{ title }}</h3>
      <p class="subtitle">校准映射{{ mappingName }}</p>
    </div>

    <div class="modal-body">
      <div v-if="!isCalibrating" class="calibration-form">
        <div class="form-group">
          <label>测试设备</label>
          <select v-model="form.testDevice" class="form-control">
            <option value="">选择播放设备...</option>
            <option v-for="device in playbackDevices" :key="device.id" :value="device.id">
              {{ device.name }}
            </option>
          </select>
        </div>

        <div class="form-grid">
          <div class="form-group">
            <label>信号类型</label>
            <select v-model="form.signalType" class="form-control">
              <option value="sine">正弦波 (Sine)</option>
              <option value="whiteNoise">白噪声 (White Noise)</option>
              <option value="pinkNoise">粉红噪声 (Pink Noise)</option>
            </select>
          </div>
          <div class="form-group">
            <label>测试频率 (Hz)</label>
            <input type="number" v-model="form.testFrequency" class="form-control" />
          </div>
        </div>

        <div class="form-grid">
          <div class="form-group">
            <label>测量距离 (米)</label>
            <input type="number" step="0.1" v-model="form.measurementDistance" class="form-control" />
          </div>
          <div class="form-group">
            <label>测试点数量</label>
            <input type="number" v-model="form.testPoints" class="form-control" />
          </div>
        </div>

        <div class="form-grid">
          <div class="form-group">
            <label>最小 dB (-60 ~ 0)</label>
            <input type="number" step="1" v-model="form.minDb" min="-60" max="0" class="form-control" />
          </div>
          <div class="form-group">
            <label>最大 dB (-60 ~ 0)</label>
            <input type="number" step="1" v-model="form.maxDb" min="-60" max="0" class="form-control" />
          </div>
        </div>

        <div class="d-curve-preview">
          <label>增益曲线预览</label>
          <div class="curve-visualization">
            <div class="curve-bar-container">
              <div
                v-for="(point, index) in curvePreview"
                :key="index"
                class="curve-bar"
                :style="{ height: point.linear * 100 + '%' }"
                :title="`音量: ${point.volume.toFixed(0)} | dB: ${point.db.toFixed(1)} | 线性: ${point.linear.toFixed(4)}`"
              ></div>
            </div>
            <div class="curve-labels">
              <span>0</span>
              <span>50</span>
              <span>100</span>
            </div>
          </div>
        </div>

        <div class="calibration-info">
          <i class="fas fa-info-circle"></i>
          <p>点击"开始校准"后，系统将自动遍历不同增益点并模拟测量声压级。请确保环境安静。</p>
        </div>
      </div>

      <div v-else class="calibrating-state">
        <div class="spinner-container">
          <div class="loading-spinner large"></div>
          <p class="status-text">{{ statusText }}</p>
        </div>
        <div class="progress-bar-container">
          <div class="progress-bar" :style="{ width: progress + '%' }"></div>
        </div>
        <div class="current-step">
          正在测量增益: <strong>{{ currentGain }}</strong>
        </div>
      </div>
    </div>

    <div class="modal-footer">
      <button class="btn btn-secondary" @click="$emit('close')" :disabled="isCalibrating">
        取消
      </button>
      <button class="btn btn-primary" @click="handleStart" :disabled="isCalibrating || !form.testDevice">
        {{ isCalibrating ? '校准中...' : '开始校准' }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { playbackApi } from '../../../utils/api'
import { volumeToDb, dbToLinear, volumeToLinear, DB_MIN, DB_MAX, generateGainCurve } from '../../../utils/audioUtils'

const props = defineProps<{
  mappingId: number
  mappingName: string
  data: any
  onConfirm: (data: any) => Promise<void>
  title?: string
}>()

const emit = defineEmits(['close', 'confirm'])

const isCalibrating = ref(false)
const statusText = ref('正在初始化...')
const progress = ref(0)
const currentGain = ref(0)
const playbackDevices = ref<any[]>([])

const form = reactive({
  signalType: props.data?.signalType || 'sine',
  testFrequency: props.data?.testFrequency || 1000,
  measurementDistance: props.data?.measurementDistance || 1,
  testPoints: props.data?.testPoints || 10,
  testDevice: props.data?.testDevice || '',
  minDb: props.data?.minDb ?? DB_MIN,
  maxDb: props.data?.maxDb ?? DB_MAX
})

const title = props.title || '声压级校准'

const curvePreview = computed(() => {
  return generateGainCurve(form.minDb, form.maxDb, 21)
})

onMounted(async () => {
  try {
    const devices = await playbackApi.getAll()
    playbackDevices.value = Array.isArray(devices) ? devices : (devices.items || [])
  } catch (error) {
    console.error('获取播放设备失败:', error)
  }
})

const handleStart = async () => {
  isCalibrating.value = true
  statusText.value = '正在开始自动校准流程...'

  const calibrationPoints: Array<{ gain: number; spl: number; db: number; linearGain: number }> = []
  const steps = [1, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
  const { minDb, maxDb } = form

  for (let i = 0; i < steps.length; i++) {
    const gain = steps[i]
    currentGain.value = gain
    progress.value = Math.round(((i + 1) / steps.length) * 100)
    statusText.value = `正在测量增益点 ${gain} (${volumeToDb(gain, minDb, maxDb).toFixed(1)} dB)...`

    const simulatedSpl = 60 + (gain * 0.35) + (Math.random() * 2 - 1)
    const dbValue = volumeToDb(gain, minDb, maxDb)
    const linearGain = volumeToLinear(gain, minDb, maxDb)

    calibrationPoints.push({
      gain,
      spl: Math.round(simulatedSpl * 10) / 10,
      db: Math.round(dbValue * 10) / 10,
      linearGain: Math.round(linearGain * 10000) / 10000
    })

    await new Promise(resolve => setTimeout(resolve, 300))
  }

  statusText.value = '校准完成，正在保存数据...'
  await new Promise(resolve => setTimeout(resolve, 500))

  try {
    if (props.onConfirm) {
      const calibrationData = {
        points: calibrationPoints,
        signalType: form.signalType,
        testFrequency: form.testFrequency,
        measurementDistance: form.measurementDistance,
        testDevice: form.testDevice,
        calibrationDate: new Date().toISOString(),
        minDb,
        maxDb,
        mode: 'db_curve'
      }

      await props.onConfirm(calibrationData)
    }
    emit('close')
  } catch (error) {
    console.error('保存校准数据失败:', error)
    isCalibrating.value = false
  }
}
</script>

<style scoped>
.spl-calibration-modal {
  padding: 20px;
  min-width: 500px;
}

.modal-header h3 {
  margin: 0 0 5px 0;
  color: var(--primary-color)
}

.subtitle {
  margin: 0 0 20px 0;
  color: var(--text-secondary);
  font-size: 0.9em;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 15px;
}

.form-group {
  margin-bottom: 15px;
}

.form-group label {
  display: block;
  margin-bottom: 5px;
  font-weight: 500;
}

.form-control {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #ced4da;
  border-radius: 6px;
  font-size: 14px;
  box-sizing: border-box;
}

.form-control:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.calibration-info {
  background-color: #e3f2fd;
  padding: 12px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
}

.calibration-info i {
  color: #1976d2;
}

.calibration-info p {
  margin: 0;
  font-size: 0.85em;
  color: #0d47a1;
}

.calibrating-state {
  padding: 40px 0;
  text-align: center;
}

.spinner-container {
  margin-bottom: 20px;
}

.status-text {
  margin-top: 15px;
  font-weight: 500;
}

.progress-bar-container {
  height: 8px;
  background-color: #f5f5f5;
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 15px;
}

.progress-bar {
  height: 100%;
  background-color: var(--primary-color);
  transition: width 0.3s ease;
}

.current-step {
  font-size: 0.9em;
  color: var(--text-secondary);
}

.loading-spinner {
  display: inline-block;
  width: 40px;
  height: 40px;
  border: 4px solid rgba(0, 0, 0, 0.1);
  border-left-color: var(--primary-color);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

.loading-spinner.large {
  width: 48px;
  height: 48px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.modal-footer {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding-top: 15px;
  border-top: 1px solid #eee;
}

.btn {
  padding: 10px 24px;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-primary {
  background-color: #3b82f6;
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background-color: #2563eb;
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  background-color: #f8f9fa;
  color: #64748b;
  border: 1px solid #e2e8f0;
}

.btn-secondary:hover {
  background-color: #e2e8f0;
}

.d-curve-preview {
  margin-top: 15px;
  padding: 15px;
  background-color: #f8f9fa;
  border-radius: 6px;
}

.d-curve-preview > label {
  display: block;
  margin-bottom: 10px;
  font-weight: 500;
  color: var(--text-primary);
}

.curve-visualization {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
}

.curve-bar-container {
  display: flex;
  align-items: flex-end;
  gap: 2px;
  height: 80px;
  padding: 5px;
  background-color: #fff;
  border-radius: 4px;
  border: 1px solid #e2e8f0;
}

.curve-bar {
  width: 8px;
  min-width: 4px;
  background-color: var(--primary-color);
  border-radius: 2px 2px 0 0;
  transition: height 0.2s ease;
  cursor: pointer;
}

.curve-bar:hover {
  background-color: #FF6A00;
}

.curve-labels {
  display: flex;
  justify-content: space-between;
  width: 100%;
  padding: 0 5px;
  font-size: 0.75em;
  color: var(--text-secondary);
}
</style>
