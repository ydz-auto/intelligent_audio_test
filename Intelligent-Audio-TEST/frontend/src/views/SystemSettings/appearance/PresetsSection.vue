<template>
  <div class="settings-form-page">
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title">
          <i class="fas fa-palette"></i>
          主题预设
        </h2>
        <p class="page-description">选择站点的配色预设，即刻全局生效（原 Vue 单主题双色：浅色 / 深色）</p>
      </div>
    </div>

    <div class="preset-grid">
      <button
        v-for="preset in presets"
        :key="preset.mode"
        class="preset-card"
        :class="{ selected: mode === preset.mode }"
        @click="selectPreset(preset.mode)"
      >
        <div class="preset-swatch" :class="preset.swatchClass">
          <div class="swatch-primary"></div>
          <div class="swatch-secondary"></div>
        </div>
        <div class="preset-info">
          <span class="preset-name">{{ preset.label }}</span>
          <span class="preset-check" v-if="mode === preset.mode">
            <i class="fas fa-check-circle"></i>
          </span>
        </div>
      </button>
    </div>
    <p v-if="notice" class="success-msg">{{ notice }}</p>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useTheme, type ThemeMode } from '../useTheme'

const { mode, apply } = useTheme()
const notice = ref('')

const presets = [
  {
    mode: 'light' as ThemeMode,
    label: '浅色',
    swatchClass: 'swatch-light',
  },
  {
    mode: 'dark' as ThemeMode,
    label: '深色',
    swatchClass: 'swatch-dark',
  },
]

function selectPreset(presetMode: ThemeMode) {
  apply(presetMode)
  notice.value = '外观设置已保存'
}
</script>

<style scoped>
.preset-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: var(--spacing-md);
  max-width: 480px;
}

.preset-card {
  border: 1px solid var(--gray-light-color);
  border-radius: var(--border-radius-md);
  padding: var(--spacing-md);
  background: var(--card);
  cursor: pointer;
  transition: all var(--transition-normal);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
  text-align: left;
}

.preset-card:hover {
  border-color: var(--primary-color);
}

.preset-card.selected {
  border-color: var(--primary-color);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--primary-color) 30%, transparent);
}

.preset-swatch {
  height: 64px;
  border-radius: var(--border-radius-sm);
  display: flex;
  overflow: hidden;
}

.swatch-primary {
  flex: 1;
}

.swatch-secondary {
  flex: 1;
}

.swatch-light {
  background: linear-gradient(135deg, #ffffff 0%, #f5f5f5 100%);
}

.swatch-light .swatch-primary {
  background: linear-gradient(135deg, #ff6a00 0%, #ff8c3b 100%);
}

.swatch-light .swatch-secondary {
  background: linear-gradient(135deg, #ffffff 0%, #f0f0f0 100%);
}

.swatch-dark {
  background: linear-gradient(135deg, #2a2a2a 0%, #333333 100%);
}

.swatch-dark .swatch-primary {
  background: linear-gradient(135deg, #ff8c3b 0%, #ffa05c 100%);
}

.swatch-dark .swatch-secondary {
  background: linear-gradient(135deg, #2a2a2a 0%, #3a3a3a 100%);
}

.preset-info {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.preset-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--foreground);
}

.preset-check {
  color: var(--primary-color);
  font-size: 16px;
}

.success-msg {
  color: var(--success-dark);
  font-size: 14px;
  margin-top: var(--spacing-md);
}
</style>
