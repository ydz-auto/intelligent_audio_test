<template>
  <div class="global-algorithm-switcher" ref="rootRef">
    <button class="algorithm-trigger" data-layout-btn :class="{ 'algorithm-trigger--selected': !!selectedType }" @click.stop="toggleOpen">
      <i class="fas fa-microchip"></i>
      <span class="algorithm-trigger__text">{{ selectedName || '全部算法' }}</span>
      <i class="fas fa-chevron-down algorithm-trigger__caret"></i>
    </button>

    <div v-if="open" class="algorithm-popover" @click.stop>
      <div class="algorithm-popover__header">
        <span>全局算法</span>
        <span class="algorithm-popover__hint">切换后全局列表按算法过滤</span>
      </div>
      <div v-if="selectedType" class="algorithm-popover__clear">
        <button class="clear-btn" data-layout-btn @click="handleClear">
          <i class="fas fa-times"></i> 清空算法筛选
        </button>
      </div>
      <div class="algorithm-list">
        <button
          v-for="algo in algorithmList"
          :key="algo.value"
          class="algorithm-item"
          data-layout-btn
          :class="{ 'algorithm-item--active': selectedType === algo.value }"
          @click="handleSelect(algo.value)"
        >
          <span class="algorithm-item__name">{{ algo.name }}</span>
          <span v-if="algo.groupName" class="algorithm-item__group">{{ algo.groupName }}</span>
          <i v-if="selectedType === algo.value" class="fas fa-check algorithm-item__check"></i>
        </button>
        <p v-if="!algorithmList.length" class="algorithm-empty">暂无可用算法</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import '../../assets/styles/test-common.css'
import '../../assets/styles/components/common.css'
import '../../assets/styles/components/button.css'
import '../../assets/styles/components/modal.css'
import '../../assets/styles/components/table.css'
import '../../assets/styles/components/navigation.css'
import '../../assets/styles/components/tag.css'
import '../../assets/styles/components/log.css'
import '../../assets/styles/layouts/main.css'

import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useGlobalAlgorithmStore } from '../../store/globalAlgorithmStore'

const globalAlgorithm = useGlobalAlgorithmStore()
const open = ref(false)
const rootRef = ref<HTMLElement | null>(null)

const selectedType = computed(() => globalAlgorithm.selectedType)
const selectedName = computed(() => globalAlgorithm.selectedName)
const algorithmList = computed(() => globalAlgorithm.algorithmList)

function toggleOpen() {
  open.value = !open.value
  if (open.value) {
    globalAlgorithm.loadAlgorithms()
  }
}

function handleSelect(type: string) {
  globalAlgorithm.setAlgorithm(type)
  open.value = false
}

function handleClear() {
  globalAlgorithm.setAlgorithm(null)
  open.value = false
}

function handleOutsideClick(event: MouseEvent) {
  if (rootRef.value && !rootRef.value.contains(event.target as Node)) {
    open.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', handleOutsideClick)
  // 挂载即恢复 localStorage 选中态并预载算法列表（回显选中名称）
  globalAlgorithm.init()
  globalAlgorithm.loadAlgorithms()
})
onUnmounted(() => document.removeEventListener('click', handleOutsideClick))
</script>

<style scoped>
.global-algorithm-switcher {
  position: relative;
}
.algorithm-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: var(--control-height);
  padding: 0 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--card);
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: all var(--transition-fast);
  max-width: 200px;
}
.algorithm-trigger:hover {
  border-color: var(--ring);
  color: var(--foreground);
}
.algorithm-trigger--selected {
  border-color: var(--ring);
  background: var(--accent);
  color: var(--primary);
}
.algorithm-trigger__text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.algorithm-trigger__caret {
  font-size: 10px;
}
.algorithm-popover {
  position: absolute;
  right: 0;
  top: calc(100% + 8px);
  width: 280px;
  background: var(--popover);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  z-index: var(--z-index-popover);
  overflow: hidden;
}
.algorithm-popover__header {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 12px 14px 8px;
  border-bottom: 1px solid var(--border);
}
.algorithm-popover__header > span:first-child {
  font-size: 14px;
  font-weight: 600;
  color: var(--foreground);
}
.algorithm-popover__hint {
  font-size: 12px;
  color: var(--text-secondary);
}
.algorithm-popover__clear {
  padding: 8px 14px 0;
}
.clear-btn {
  width: 100%;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border: 1px dashed var(--border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: all var(--transition-fast);
}
.clear-btn:hover {
  border-color: var(--destructive);
  color: var(--destructive);
}
.algorithm-list {
  max-height: 260px;
  overflow-y: auto;
  padding: 8px;
}
.algorithm-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-primary);
  font-size: 14px;
  cursor: pointer;
  text-align: left;
  transition: background var(--transition-fast);
}
.algorithm-item:hover {
  background: var(--muted);
}
.algorithm-item--active {
  background: var(--accent);
  color: var(--primary);
  font-weight: 600;
}
.algorithm-item__name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.algorithm-item__group {
  font-size: 12px;
  color: var(--text-secondary);
}
.algorithm-item__check {
  font-size: 12px;
  color: var(--primary);
}
.algorithm-empty {
  margin: 0;
  padding: 16px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 13px;
}
</style>
