<template>
  <div class="api-rms-spl-calibration-modal">
    <div class="modal-body">
      <!-- 模式说明 -->
      <div class="mode-info">
        <i class="fas fa-info-circle"></i>
        <p>
          数字域校准（API/Realtime 口径）：为被测 API 配置「目标声压级 ↔ 线性增益 ↔ 实测 RMS」点集，
          提交后全量替换既有校准点并置为已校准。与设备 SPL 校准（物理域）对称；
          未校准时按参考基准线性近似 gain = {{ referenceGainLinear }} × 10^((target - {{ referenceSpl }}) / 20)。
        </p>
      </div>

      <!-- 参考基准展示 -->
      <div class="reference-grid">
        <div class="ref-item">
          <span class="ref-label">参考声压级</span>
          <span class="ref-value">{{ referenceSpl }} dB SPL</span>
        </div>
        <div class="ref-item">
          <span class="ref-label">参考线性增益</span>
          <span class="ref-value">{{ referenceGainLinear }}</span>
        </div>
        <div class="ref-item">
          <span class="ref-label">增益限幅</span>
          <span class="ref-value">{{ minGainLinear }} ~ {{ maxGainLinear }}</span>
        </div>
        <div class="ref-item">
          <span class="ref-label">基准电平</span>
          <span class="ref-value">-30 dBFS（RMS 补偿基准）</span>
        </div>
      </div>

      <!-- 校准点列表 -->
      <div class="points-section">
        <div class="points-header">
          <h4>校准点集（{{ points.length }} 点）</h4>
          <button type="button" class="btn btn-secondary btn-small" @click="addPoint">
            <i class="fas fa-plus"></i> 添加校准点
          </button>
        </div>

        <div v-if="points.length === 0" class="empty-points">
          <p>暂无校准点。可手动添加，或使用「按参考生成」快速生成一组等间隔点。</p>
        </div>

        <div class="point-row point-row--head" v-if="points.length > 0">
          <span class="col-target">目标 SPL (dB)</span>
          <span class="col-gain">线性增益</span>
          <span class="col-db">增益 (dB)</span>
          <span class="col-rms">实测 RMS (dBFS)</span>
          <span class="col-actions"></span>
        </div>

        <div
          v-for="(point, index) in points"
          :key="index"
          class="point-row"
          :class="{ 'has-error': pointErrors(index) }"
        >
          <div class="col-target">
            <input
              type="number"
              v-model.number="point.targetSpl"
              :min="0"
              :max="120"
              step="0.5"
              :placeholder="'30~120'"
              @input="touchPoint(index)"
            />
          </div>
          <div class="col-gain">
            <input
              type="number"
              v-model.number="point.gainLinear"
              :min="minGainLinear"
              :max="maxGainLinear"
              step="0.001"
              placeholder="> 0"
              @input="touchPoint(index)"
            />
          </div>
          <div class="col-db readonly-cell">
            {{ gainToDb(point.gainLinear) }}
          </div>
          <div class="col-rms">
            <input
              type="number"
              v-model.number="point.rmsDbfs"
              :min="-120"
              :max="0"
              step="0.1"
              placeholder="选填"
            />
          </div>
          <div class="col-actions">
            <button
              type="button"
              class="icon-btn"
              title="删除该点"
              :disabled="points.length <= 1"
              @click="removePoint(index)"
            >
              <i class="fas fa-trash"></i>
            </button>
          </div>
          <div v-if="pointErrors(index)" class="point-error">{{ pointErrors(index) }}</div>
        </div>

        <div class="points-toolbar" v-if="points.length === 0 || regenerateVisible">
          <button type="button" class="btn btn-secondary" @click="generateFromReference">
            <i class="fas fa-magic"></i> 按参考生成（{{ referenceSpl }}dB 为中心 ±20dB / 每 10dB 一点）
          </button>
        </div>
      </div>

      <!-- 曲线预览 -->
      <div class="preview-section" v-if="sortedValidPoints.length >= 2">
        <h4>增益曲线预览（SPL → gain，dB）</h4>
        <div class="preview-table">
          <div class="preview-row preview-row--head">
            <span>目标 SPL (dB)</span>
            <span>线性增益</span>
            <span>增益 (dB)</span>
          </div>
          <div class="preview-row" v-for="p in sortedValidPoints" :key="`pv-${p.targetSpl}`">
            <span>{{ p.targetSpl }}</span>
            <span>{{ p.gainLinear }}</span>
            <span>{{ gainToDb(p.gainLinear) }}</span>
          </div>
        </div>
      </div>

      <div class="conflict-hint">
        <i class="fas fa-lock"></i>
        <span>同一 API 并发校准互斥（分布式锁），冲突时后端返回 409，请稍后重试。</span>
      </div>
    </div>

    <div class="modal-footer">
      <button class="btn btn-secondary" @click="$emit('close')" :disabled="submitting">
        取消
      </button>
      <button class="btn btn-primary" @click="handleSubmit" :disabled="submitting || !isValid">
        <span v-if="submitting" class="loading-spinner"></span>
        {{ submitting ? '校准中...' : '提交校准' }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
// -*- coding: utf-8 -*-
/**
 * API RMS-SPL 数字校准弹窗 —— INT-300
 * 区别于 SPLCalibrationModal.vue（设备物理域播放测试音）：
 * 数字域校准对象是被测 API 的输入灵敏度，产出 {target_spl, gain_linear, rms_dbfs} 点集，
 * 经 POST /digital-spl/{id}/calibrate 全量替换并置已校准。
 */
import { ref, computed } from 'vue'
import type { ApiCalibrationPoint } from '../../../domain'

const props = defineProps<{
  mappingId: number | string
  mappingName: string
  apiId: number | string
  data?: {
    calibrationPoints?: ApiCalibrationPoint[]
    referenceSpl?: number
    referenceGainLinear?: number
    minGainLinear?: number
    maxGainLinear?: number
  }
  onConfirm?: (payload: { points: ApiCalibrationPoint[] }) => Promise<void>
  title?: string
}>()

const emit = defineEmits(['close', 'confirm'])

const submitting = ref(false)

const referenceSpl = computed(() => props.data?.referenceSpl ?? 65)
const referenceGainLinear = computed(() => props.data?.referenceGainLinear ?? 1.0)
const minGainLinear = computed(() => props.data?.minGainLinear ?? 0.001)
const maxGainLinear = computed(() => props.data?.maxGainLinear ?? 10.0)

/** 编辑中的点集（本地可变副本；rmsDbfs 选填） */
const points = ref<Array<{ targetSpl: number | null; gainLinear: number | null; rmsDbfs: number | null }>>(
  (props.data?.calibrationPoints ?? []).map(p => ({
    targetSpl: p.targetSpl ?? null,
    gainLinear: p.gainLinear ?? null,
    rmsDbfs: p.rmsDbfs ?? null,
  }))
)

/** 已触碰（编辑过）的行才做完整性校验，避免空模板行报错 */
const touched = ref<Set<number>>(new Set())

function touchPoint(index: number) {
  touched.value.add(index)
}

/** 线性增益 → dB（展示用） */
function gainToDb(gain: number | null | undefined): string {
  if (gain == null || !Number.isFinite(gain) || gain <= 0) return '-'
  return `${(20 * Math.log10(gain)).toFixed(2)} dB`
}

function addPoint() {
  points.value.push({ targetSpl: null, gainLinear: null, rmsDbfs: null })
  regenerateVisible.value = true
}

function removePoint(index: number) {
  points.value.splice(index, 1)
  touched.value.delete(index)
}

/** 按参考基准生成默认点集：参考 SPL 为中心 ±20dB，每 10dB 一点（5 点） */
function generateFromReference() {
  const center = referenceSpl.value
  const gains = [-20, -10, 0, 10, 20]
  points.value = gains.map(offset => {
    const targetSpl = center + offset
    const gainLinear = referenceGainLinear.value * Math.pow(10, offset / 20)
    return {
      targetSpl: Math.round(targetSpl * 10) / 10,
      gainLinear: Math.round(gainLinear * 1000) / 1000,
      rmsDbfs: null,
    }
  })
  touched.value = new Set(points.value.map((_, i) => i))
}

const regenerateVisible = ref(false)

/** 单点校验错误消息（空串 = 无错） */
function pointErrors(index: number): string {
  if (!touched.value.has(index)) return ''
  const p = points.value[index]
  if (p.targetSpl == null || !Number.isFinite(p.targetSpl) || p.targetSpl < 0 || p.targetSpl > 120) {
    return '目标 SPL 须为 0~120 的数值'
  }
  if (p.gainLinear == null || !Number.isFinite(p.gainLinear) || p.gainLinear <= 0) {
    return '线性增益须为正数'
  }
  if (p.gainLinear < minGainLinear.value || p.gainLinear > maxGainLinear.value) {
    return `增益超出限幅 ${minGainLinear.value}~${maxGainLinear.value}`
  }
  return ''
}

/** 有效点（提交用）：target_spl/gain_linear 齐备即收，未编辑行原样透传 */
const validPoints = computed<ApiCalibrationPoint[]>(() => {
  return points.value
    .filter(p => p.targetSpl != null && p.gainLinear != null)
    .map(p => ({
      targetSpl: Number(p.targetSpl),
      gainLinear: Number(p.gainLinear),
      rmsDbfs: p.rmsDbfs ?? undefined,
    }))
})

const sortedValidPoints = computed(() => [...validPoints.value].sort((a, b) => a.targetSpl - b.targetSpl))

/** 重复 target_spl 检查（插值曲线不允许重复 x） */
const duplicateTargets = computed(() => {
  const seen = new Set<number | string>()
  for (const p of validPoints.value) {
    if (seen.has(p.targetSpl)) return true
    seen.add(p.targetSpl)
  }
  return false
})

const isValid = computed(() => validPoints.value.length > 0 && !duplicateTargets.value)

async function handleSubmit() {
  if (!isValid.value || submitting.value) return
  submitting.value = true
  try {
    const payload = { points: validPoints.value }
    if (props.onConfirm) {
      await props.onConfirm(payload)
    }
    emit('confirm', payload)
  } catch (error) {
    // onConfirm 内已通知错误；这里不关闭弹窗，用户可修正后重试
    console.error('[ApiRmsSplCalibration] 校准提交失败:', error)
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.api-rms-spl-calibration-modal {
  display: flex;
  flex-direction: column;
}

.modal-body {
  padding: 16px 20px;
  max-height: 65vh;
  overflow-y: auto;
}

.mode-info {
  display: flex;
  gap: 8px;
  padding: 10px 12px;
  background: var(--background-secondary, #f7f8fa);
  border-left: 3px solid var(--primary-color, #4080ff);
  border-radius: 6px;
  margin-bottom: 14px;
}

.mode-info p {
  margin: 0;
  font-size: 12px;
  color: var(--text-secondary, #666);
  line-height: 1.6;
}

.reference-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-bottom: 16px;
}

.ref-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 10px;
  background: var(--background-primary, #fff);
  border: 1px solid var(--border-color, #e5e6eb);
  border-radius: 8px;
}

.ref-label {
  font-size: 11px;
  color: var(--text-light, #999);
}

.ref-value {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #333);
}

.points-section {
  margin-bottom: 16px;
}

.points-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.points-header h4,
.preview-section h4 {
  margin: 0;
  font-size: 14px;
  color: var(--text-primary, #333);
}

.empty-points {
  padding: 20px;
  text-align: center;
  color: var(--text-light, #999);
  border: 1px dashed var(--border-color, #ddd);
  border-radius: 8px;
}

.empty-points p {
  margin: 0;
  font-size: 13px;
}

.point-row {
  display: grid;
  grid-template-columns: 1.1fr 1.1fr 0.8fr 1.1fr 40px;
  gap: 8px;
  align-items: center;
  padding: 6px 0;
  position: relative;
  flex-wrap: wrap;
}

.point-row--head {
  font-size: 12px;
  color: var(--text-light, #999);
  border-bottom: 1px solid var(--border-color, #eee);
  padding-bottom: 8px;
}

.point-row input {
  width: 100%;
  padding: 6px 8px;
  border: 1px solid var(--border-color, #ddd);
  border-radius: 6px;
  font-size: 13px;
  box-sizing: border-box;
}

.point-row input:focus {
  outline: none;
  border-color: var(--primary-color, #4080ff);
}

.point-row.has-error input {
  border-color: var(--error-color, #f53f3f);
}

.readonly-cell {
  font-size: 12px;
  color: var(--text-secondary, #666);
  font-variant-numeric: tabular-nums;
}

.point-error {
  grid-column: 1 / -1;
  font-size: 11px;
  color: var(--error-color, #f53f3f);
}

.col-actions {
  display: flex;
  justify-content: center;
}

.icon-btn {
  border: none;
  background: transparent;
  color: var(--text-light, #999);
  cursor: pointer;
  padding: 4px 6px;
  border-radius: 4px;
}

.icon-btn:hover:not(:disabled) {
  color: var(--error-color, #f53f3f);
  background: var(--error-light, #fdecec);
}

.icon-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.points-toolbar {
  margin-top: 10px;
}

.preview-section {
  margin-bottom: 14px;
}

.preview-table {
  border: 1px solid var(--border-color, #eee);
  border-radius: 8px;
  overflow: hidden;
  max-height: 180px;
  overflow-y: auto;
}

.preview-row {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  padding: 6px 12px;
  font-size: 12px;
  border-bottom: 1px solid var(--border-color, #f2f2f2);
  font-variant-numeric: tabular-nums;
}

.preview-row--head {
  background: var(--background-secondary, #f7f8fa);
  color: var(--text-light, #999);
  position: sticky;
  top: 0;
}

.preview-row:last-child {
  border-bottom: none;
}

.conflict-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-light, #999);
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 14px 20px;
  border-top: 1px solid var(--border-color, #eee);
}

.loading-spinner {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid rgba(255, 255, 255, 0.4);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-right: 4px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

@media (max-width: 768px) {
  .reference-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .point-row {
    grid-template-columns: 1fr 1fr 40px;
  }

  .col-db {
    display: none;
  }
}
</style>
