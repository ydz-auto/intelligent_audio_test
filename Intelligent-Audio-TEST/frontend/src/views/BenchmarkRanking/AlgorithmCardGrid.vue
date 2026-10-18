<template>
  <section class="algorithm-card-grid">
    <div class="ag-head">
      <span class="ag-eyebrow">算法切换</span>
      <span class="ag-hint">仅影响本页榜单，不改变全局算法。</span>
    </div>

    <!-- 有 algorithm:read 权限：完整卡片网格 -->
    <div v-if="canManage" class="ag-grid">
      <button
        type="button"
        class="ag-card"
        :class="{ selected: !selectedType }"
        @click="handleSelectAll"
      >
        <div class="ag-card-icon">
          <i class="fas fa-layer-group"></i>
        </div>
        <div class="ag-card-body">
          <h3 class="ag-card-name">全部算法</h3>
          <p class="ag-card-desc">不按算法筛选，展示全部算法数据。</p>
        </div>
        <i v-if="!selectedType" class="fas fa-check ag-check"></i>
      </button>

      <button
        v-for="algo in algorithms"
        :key="algo.type"
        type="button"
        class="ag-card"
        :class="{
          selected: selectedType === algo.type,
          offline: algo.status === ApiEndpointStatus.OFFLINE,
        }"
        :disabled="algo.status === ApiEndpointStatus.OFFLINE"
        @click="handleSelect(algo)"
      >
        <div class="ag-card-icon">
          <i class="fas fa-microchip"></i>
        </div>
        <div class="ag-card-body">
          <div class="ag-card-title-row">
            <h3 class="ag-card-name">{{ algo.name }}</h3>
            <span v-if="algo.groupName" class="ag-badge">{{ algo.groupName }}</span>
            <span class="ag-badge" :class="algo.status === ApiEndpointStatus.ONLINE ? 'ag-badge-online' : 'ag-badge-offline'">
              {{ algo.status === ApiEndpointStatus.ONLINE ? '在线' : '离线' }}
            </span>
          </div>
          <p v-if="paramSummary(algo)" class="ag-params">{{ paramSummary(algo) }}</p>
          <p class="ag-card-desc">{{ algo.description }}</p>
        </div>
        <span v-if="selectedType === algo.type" class="ag-current">当前</span>
      </button>
    </div>

    <!-- 无 algorithm:read：只读降级条（公开页首屏不空） -->
    <div v-else class="ag-readonly">
      <span class="ag-ro-label">当前算法</span>
      <span class="ag-ro-value">全部算法</span>
      <span class="ag-ro-tip" title="切换算法需登录并具备算法查看权限">
        <i class="fas fa-info-circle"></i>
      </span>
    </div>

    <p class="ag-note">按算法过滤待后端立项（排行数据暂无算法维度）。</p>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { algorithmPort } from '../../composables/algorithm/algorithmPort'
import { useAuthStore } from '../../store/authStore'
import { useNotification } from '../../composables/modal/useNotification'
import { ApiEndpointStatus, AuthMode, getEffectiveAuthMode } from '../../domain/enums'
import type { AlgorithmDefinition } from '../../domain/model/algorithm'

/**
 * 排行榜页内算法卡片网格（INT-745 A05 / 总表 §2.4 口径）
 * - 每算法一张大卡 + 首卡「全部算法」；选中态高亮，页内独立、不写回全局算法 store
 * - 数据源 GET /algorithm/definitions（algorithm:read；无权限 → 只读降级条）
 * - 榜单按算法过滤待后端立项：选择仅作用于本页显示，不改变排行数据
 */
const STORAGE_KEY = 'iatp:rankings:v1:algorithm'

const authStore = useAuthStore()
const notification = useNotification()

const algorithms = ref<AlgorithmDefinition[]>([])
const loading = ref(false)
const selectedType = ref<string | null>(localStorage.getItem(STORAGE_KEY) || null)

/** AUTH_MODE=off（现状部署）全员可管；认证开启时按 algorithm:read 过滤（无权限 → 只读降级条） */
const canManage = computed(() => {
  const authMode = getEffectiveAuthMode()
  if (authMode === AuthMode.OFF) return true
  return authStore.hasPermission('algorithm:read')
})

function paramSummary(algo: AlgorithmDefinition): string {
  const device = algo.deviceParams?.length ?? 0
  const api = algo.apiParams?.length ?? 0
  const cases = algo.caseParams?.length ?? 0
  if (!device && !api && !cases) return ''
  const parts: string[] = []
  if (device) parts.push(`设备参数 ${device}`)
  if (api) parts.push(`API 参数 ${api}`)
  if (cases) parts.push(`用例参数 ${cases}`)
  return parts.join(' · ')
}

function persist() {
  if (selectedType.value) localStorage.setItem(STORAGE_KEY, selectedType.value)
  else localStorage.removeItem(STORAGE_KEY)
}

function handleSelectAll() {
  if (selectedType.value === null) return
  selectedType.value = null
  persist()
  notification.success('已恢复全部算法')
}

function handleSelect(algo: AlgorithmDefinition) {
  selectedType.value = algo.type
  persist()
  notification.success(`已切换榜单算法为 ${algo.name}`)
}

async function loadAlgorithms() {
  if (!canManage.value) return
  loading.value = true
  try {
    const result = await algorithmPort.getDefinitions()
    algorithms.value = result.data ?? []
  } catch {
    algorithms.value = []
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadAlgorithms()
})
</script>

<style scoped>
.algorithm-card-grid {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: 0 2px 8px color-mix(in srgb, var(--color-black) 4%, transparent);
  padding: 16px;
}
.ag-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 12px;
}
.ag-eyebrow {
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.05em;
  color: var(--foreground);
}
.ag-hint {
  font-size: 12px;
  color: var(--muted-foreground);
}
.ag-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}
.ag-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  text-align: left;
  background: var(--background);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 14px;
  cursor: pointer;
  position: relative;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
  font: inherit;
}
.ag-card:hover:not(:disabled) {
  border-color: var(--primary);
  box-shadow: 0 2px 10px color-mix(in srgb, var(--primary) 8%, transparent);
}
.ag-card.selected {
  border-color: var(--primary);
  box-shadow: 0 0 0 2px var(--ring);
  background: var(--accent);
}
.ag-card.offline {
  opacity: 0.6;
  cursor: not-allowed;
}
.ag-card-icon {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-sm);
  background: var(--accent);
  color: var(--primary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  flex-shrink: 0;
}
.ag-card-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.ag-card-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.ag-card-name {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--foreground);
}
.ag-badge {
  font-size: 11px;
  padding: 1px 8px;
  border-radius: var(--radius-pill);
  border: 1px solid var(--border);
  color: var(--muted-foreground);
}
.ag-badge-online {
  color: var(--success-dark);
  border-color: var(--success);
}
.ag-badge-offline {
  color: var(--muted-foreground);
}
.ag-params {
  margin: 0;
  font-size: 12px;
  color: var(--muted-foreground);
}
.ag-card-desc {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--muted-foreground);
}
.ag-check {
  position: absolute;
  top: 10px;
  right: 10px;
  color: var(--primary);
  font-size: 14px;
}
.ag-current {
  position: absolute;
  top: 10px;
  right: 10px;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: var(--radius-pill);
  background: var(--primary);
  color: var(--primary-foreground);
}
/* 只读降级条 */
.ag-readonly {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
}
.ag-ro-label {
  font-size: 12px;
  color: var(--muted-foreground);
}
.ag-ro-value {
  font-size: 13px;
  font-weight: 600;
  color: var(--foreground);
}
.ag-ro-tip {
  margin-left: auto;
  color: var(--muted-foreground);
  cursor: help;
}
.ag-note {
  margin: 10px 0 0;
  font-size: 12px;
  color: var(--muted-foreground);
  text-align: right;
}
</style>
