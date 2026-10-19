<template>
  <div class="theme-switcher" ref="rootRef">
    <button
      class="header-icon-btn"
      data-layout-btn
      :title="isDark ? '切换为浅色' : '切换为深色'"
      @click.stop="toggleOpen"
    >
      <i :class="isDark ? 'fas fa-sun' : 'fas fa-moon'"></i>
    </button>
    <div v-if="open" class="theme-popover" @click.stop>
      <p class="theme-popover__title">主题</p>
      <button
        class="theme-option"
        data-layout-btn
        :class="{ 'theme-option--active': !isDark }"
        @click="setTheme('light')"
      >
        <i class="fas fa-sun"></i>
        <span>浅色</span>
      </button>
      <button
        class="theme-option"
        data-layout-btn
        :class="{ 'theme-option--active': isDark }"
        @click="setTheme('dark')"
      >
        <i class="fas fa-moon"></i>
        <span>深色</span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useThemeStore, type ThemeMode } from '../../store/themeStore'

const themeStore = useThemeStore()
const open = ref(false)
const rootRef = ref<HTMLElement | null>(null)

const isDark = computed(() => themeStore.theme === 'dark')

function setTheme(mode: ThemeMode) {
  themeStore.apply(mode)
  open.value = false
}

function toggleOpen() {
  open.value = !open.value
}

function handleOutsideClick(event: MouseEvent) {
  if (rootRef.value && !rootRef.value.contains(event.target as Node)) {
    open.value = false
  }
}

onMounted(() => document.addEventListener('click', handleOutsideClick))
onUnmounted(() => document.removeEventListener('click', handleOutsideClick))
</script>

<style scoped>
.header-icon-btn {
  width: var(--control-height);
  height: var(--control-height);
  border-radius: var(--radius-control);
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 16px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: background var(--transition-fast), color var(--transition-fast);
}
.header-icon-btn:hover {
  background: var(--gray-light);
  color: var(--foreground);
}
.theme-switcher {
  position: relative;
}
.theme-popover {
  position: absolute;
  right: 0;
  top: calc(100% + 8px);
  min-width: 160px;
  background: var(--popover);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  padding: 12px;
  z-index: var(--z-index-popover);
}
.theme-popover__title {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--foreground);
}
.theme-option {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 8px 10px;
  margin-bottom: 4px;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-primary);
  font-size: 14px;
  cursor: pointer;
  transition: all var(--transition-fast);
}
.theme-option:hover {
  background: var(--muted);
}
.theme-option--active {
  border-color: var(--ring);
  background: var(--accent);
  color: var(--primary);
  font-weight: 600;
}
</style>
