<template>
  <div class="rce-step" id="step-ref">
    <div class="rce-step-header">
      <i class="fas fa-file-alt rce-step-icon"></i>
      <span class="rce-step-title">参考参数</span>
      <span class="rce-tag rce-tag-gray">referenceParamsPath · 自动生成 · 只读</span>
    </div>
    <div v-if="refPath" class="rce-ref-info">
      <i class="fas fa-folder-open"></i>
      <span>{{ refPath }}</span>
    </div>
    <div v-else class="rce-ref-empty">
      <i class="fas fa-info-circle"></i>
      参考参数将在音频关联后自动生成
    </div>

    <!-- 参考参数内容（从独立列 reference_params 指向的文件拉取） -->
    <div v-if="refParamsList.length > 0" class="rce-ref-params">
      <div v-for="(p, idx) in refParamsList" :key="idx" class="rce-ref-param">
        <span class="rce-ref-param-code">{{ p.code }}</span>
        <span class="rce-ref-param-type">{{ p.type }}</span>
        <span class="rce-ref-param-value">{{ formatValue(p.value) }}</span>
      </div>
    </div>
    <div v-else-if="refPath && loading" class="rce-ref-loading">
      <i class="fas fa-spinner fa-spin"></i> 加载中...
    </div>
    <div v-else-if="refPath" class="rce-ref-empty">
      <i class="fas fa-info-circle"></i>
      暂无参考参数内容
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { RoundConfigItem } from '../types'
import { testcasesApi } from '../../../../../utils/api'

const props = defineProps<{
  round: RoundConfigItem
  /** 当前轮参考参数独立列条目：{round_number, reference_params_path} */
  referenceParams?: any
  /** 测试用例 ID，用于拉取参考参数内容 */
  tcId?: string | number
}>()

const loading = ref(false)
const refParamsList = ref<any[]>([])

// 新架构：参考参数路径存于独立列，round 中不再有 referenceParamsPath
const refPath = computed(() => props.referenceParams?.reference_params_path || '')

async function loadRefParams() {
  refParamsList.value = []
  if (!props.tcId || !refPath.value) return
  const rn = props.round.roundNumber ?? 1
  loading.value = true
  try {
    const res: any = await testcasesApi.getRefParams(props.tcId, rn)
    const data = res?.data || res || {}
    refParamsList.value = Array.isArray(data.referenceParams) ? data.referenceParams : []
  } catch (e) {
    console.warn('[ReferencePathStep] 加载参考参数失败:', e)
    refParamsList.value = []
  } finally {
    loading.value = false
  }
}

watch(() => [refPath.value, props.round?.roundNumber, props.tcId], loadRefParams, { immediate: true })

function formatValue(v: unknown): string {
  if (v === null || v === undefined) return ''
  if (typeof v === 'object') {
    try { return JSON.stringify(v) } catch { return String(v) }
  }
  return String(v)
}
</script>

<style scoped>
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
.rce-tag-gray { background: #f5f5f5; color: #999; }

.rce-ref-info {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: var(--background-secondary, #f5f6f8);
  border-radius: 6px;
  font-size: 12px;
  color: var(--text-secondary, #666);
  word-break: break-all;
}
.rce-ref-info i { color: var(--text-light, #999); }

.rce-ref-empty {
  padding: 12px 16px;
  text-align: center;
  color: var(--text-light, #999);
  font-size: 13px;
}
.rce-ref-empty i { margin-right: 4px; }

.rce-ref-loading {
  padding: 12px 16px;
  text-align: center;
  color: var(--text-light, #999);
  font-size: 13px;
}
.rce-ref-loading i { margin-right: 4px; }

.rce-ref-params {
  margin-top: 10px;
  border: 1px solid #eee;
  border-radius: 6px;
  overflow: hidden;
}
.rce-ref-param {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 8px 14px;
  font-size: 12px;
  border-bottom: 1px solid #f5f5f5;
}
.rce-ref-param:last-child { border-bottom: none; }
.rce-ref-param-code {
  flex-shrink: 0;
  font-weight: 600;
  color: var(--primary-color, #ff6a00);
}
.rce-ref-param-type {
  flex-shrink: 0;
  padding: 1px 6px;
  border-radius: 8px;
  background: #f0f0f0;
  color: #999;
  font-size: 10px;
}
.rce-ref-param-value {
  color: var(--text-primary, #333);
  word-break: break-all;
}
</style>
