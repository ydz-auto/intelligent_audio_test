<template>
  <div class="settings-form-page">
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title">
          <i class="fas fa-sliders-h"></i>
          外观微调
        </h2>
        <p class="page-description">微调界面外观参数，即刻全局生效</p>
      </div>
    </div>

    <div class="card settings-card">
      <div class="card-body">
        <div class="axis-section">
          <div class="axis-header">
            <span class="axis-title">深浅色</span>
            <span v-if="mode !== 'auto'" class="axis-reset" @click="apply('auto')">
              <i class="fas fa-undo"></i>重置
            </span>
          </div>
          <div class="axis-options">
            <label
              v-for="opt in modeOptions"
              :key="opt.value"
              class="axis-option"
              :class="{ selected: mode === opt.value }"
            >
              <input type="radio" :value="opt.value" v-model="mode" @change="apply(opt.value)" />
              <span class="axis-option-label">{{ opt.label }}</span>
            </label>
          </div>
        </div>

        <div class="axis-section reserved">
          <div class="axis-header">
            <span class="axis-title">字体 / 圆角 / 内容版式</span>
          </div>
          <p class="reserved-hint">
            <i class="fas fa-info-circle"></i>
            更多外观微调轴随后端 token 能力补齐（原 Vue 单主题双色，本期仅提供深浅色轴）
          </p>
        </div>
      </div>
    </div>
    <p v-if="notice" class="success-msg">{{ notice }}</p>
  </div>
</template>

<script setup lang="ts">
import '../../../assets/styles/test-common.css'
import '../../../assets/styles/components/common.css'
import '../../../assets/styles/components/button.css'
import '../../../assets/styles/components/card.css'
import '../../../assets/styles/components/table.css'
import '../../../assets/styles/components/navigation.css'
import '../../../assets/styles/components/tag.css'
import '../../../assets/styles/components/log.css'
import '../../../assets/styles/layouts/main.css'

import { ref } from 'vue'
import { useTheme, type ThemeMode } from '../useTheme'

const { mode, apply } = useTheme()
const notice = ref('')

const modeOptions: Array<{ value: ThemeMode; label: string }> = [
  { value: 'auto', label: '跟随系统' },
  { value: 'light', label: '浅色' },
  { value: 'dark', label: '深色' },
]
</script>

<style scoped>
.axis-section {
  padding: var(--spacing-md) 0;
  border-bottom: 1px solid var(--gray-light-color);
}

.axis-section:last-child {
  border-bottom: none;
}

.axis-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--spacing-sm);
}

.axis-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--foreground);
}

.axis-reset {
  font-size: 13px;
  color: var(--text-secondary);
  cursor: pointer;
}

.axis-reset:hover {
  color: var(--primary-color);
}

.axis-options {
  display: flex;
  gap: var(--spacing-sm);
}

.axis-option {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--gray-light-color);
  border-radius: var(--border-radius-md);
  cursor: pointer;
  font-size: 14px;
  color: var(--foreground);
  transition: all var(--transition-normal);
}

.axis-option:hover {
  border-color: var(--primary-color);
}

.axis-option.selected {
  border-color: var(--primary-color);
  background: var(--primary-light);
  color: var(--primary-color);
}

.axis-option input {
  display: none;
}

.reserved-hint {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
}

.success-msg {
  color: var(--success-dark);
  font-size: 14px;
  margin-top: var(--spacing-md);
}
</style>
