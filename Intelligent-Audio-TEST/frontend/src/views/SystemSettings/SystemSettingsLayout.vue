<template>
  <div class="system-settings-workspace">
    <!-- 左：设置树（侧栏整树替换形态，复用侧栏项样式） -->
    <aside class="settings-sidebar">
      <button class="back-to-workbench" @click="goDashboard">
        <i class="fas fa-arrow-left btn-icon"></i>
        返回工作台
      </button>

      <div class="settings-tree">
        <div
          v-for="domain in visibleDomains"
          :key="domain.id"
          class="settings-group"
        >
          <button
            class="settings-group-header"
            :class="{ 'group-open': isDomainExpanded(domain) }"
            @click="toggleDomain(domain)"
          >
            <i :class="domain.icon"></i>
            <span class="group-title">{{ domain.title }}</span>
            <i class="fas fa-chevron-down group-chevron"></i>
          </button>

          <div v-show="isDomainExpanded(domain)" class="settings-sections">
            <router-link
              v-for="section in visibleSections(domain)"
              :key="section.path"
              :to="`/system-settings/${section.path}`"
              class="settings-section-link"
              :class="{ active: isActiveSection(section) }"
            >
              <span class="section-label">{{ section.label }}</span>
            </router-link>
          </div>
        </div>
      </div>
    </aside>

    <!-- 右：分区内容 -->
    <main class="settings-content">
      <div v-if="!allowed" class="settings-forbidden">
        <i class="fas fa-lock"></i>
        <h3>无权访问系统设置</h3>
        <p>需要任一设置域权限（用户/角色/OAuth/日志管理）</p>
        <button class="btn btn-primary" @click="goDashboard">
          <i class="fas fa-arrow-left btn-icon"></i>返回工作台
        </button>
      </div>
      <router-view v-else />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/store/authStore'
import {
  settingsDomains,
  canAccessDomain,
  canAccessSection,
  SYSTEM_SETTINGS_PERMISSIONS,
  type SettingsDomain,
} from './settingsConfig'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

/** 任一设置域权限门槛（总表 §2.5 / React SYSTEM_SETTINGS_PERMISSIONS） */
const allowed = computed(() =>
  authStore.hasAnyPermission(...(SYSTEM_SETTINGS_PERMISSIONS as unknown as string[]))
)

const visibleDomains = computed(() =>
  settingsDomains.filter(d => canAccessDomain(d, authStore.hasAnyPermission))
)

/** 各域展开态（会话内记忆，默认当前域展开） */
const expandedDomains = ref<Record<string, boolean>>({})

function currentDomain(): SettingsDomain | undefined {
  const domain = settingsDomains.find(d =>
    route.path.startsWith(`/system-settings/${d.id}`)
  )
  return domain
}

function isDomainExpanded(domain: SettingsDomain): boolean {
  if (expandedDomains.value[domain.id] !== undefined) {
    return expandedDomains.value[domain.id]
  }
  return currentDomain()?.id === domain.id
}

function toggleDomain(domain: SettingsDomain) {
  expandedDomains.value[domain.id] = !isDomainExpanded(domain)
}

function visibleSections(domain: SettingsDomain) {
  return domain.sections.filter(s => canAccessSection(domain, s, authStore.hasAnyPermission))
}

function isActiveSection(section: { path: string }): boolean {
  return route.path === `/system-settings/${section.path}`
}

function goDashboard() {
  router.push('/dashboard')
}
</script>

<style scoped>
.system-settings-workspace {
  display: flex;
  min-height: 100%;
  width: 100%;
}

.settings-sidebar {
  width: 240px;
  flex-shrink: 0;
  background: linear-gradient(180deg, var(--background) 0%, var(--muted) 100%);
  border-right: 1px solid var(--gray-light-color);
  padding: var(--spacing-md);
  box-sizing: border-box;
  overflow-y: auto;
}

.back-to-workbench {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  width: 100%;
  padding: var(--spacing-md);
  margin-bottom: var(--spacing-md);
  border: none;
  border-radius: var(--border-radius-md);
  background: transparent;
  color: var(--text-secondary);
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all var(--transition-normal);
}

.back-to-workbench:hover {
  color: var(--primary-color);
  background: var(--primary-light);
}

.settings-group {
  margin-bottom: var(--spacing-xs);
}

.settings-group-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  width: 100%;
  padding: var(--spacing-md);
  border: none;
  border-radius: var(--border-radius-md);
  background: transparent;
  color: var(--text-secondary);
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all var(--transition-normal);
}

.settings-group-header:hover {
  color: var(--primary-color);
  background: var(--gray-light-color);
}

.settings-group-header .group-title {
  flex: 1;
  text-align: left;
}

.settings-group-header .group-chevron {
  font-size: 11px;
  transition: transform var(--transition-normal);
}

.settings-group-header.group-open .group-chevron {
  transform: rotate(180deg);
}

.settings-sections {
  margin-left: var(--spacing-lg);
  border-left: 1px solid var(--gray-light-color);
}

.settings-section-link {
  display: flex;
  align-items: center;
  padding: var(--spacing-sm) var(--spacing-md);
  margin: 2px 0;
  border-radius: var(--border-radius-sm);
  text-decoration: none;
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
  transition: all var(--transition-normal);
}

.settings-section-link:hover {
  color: var(--primary-color);
  background: var(--primary-light);
}

.settings-section-link.active {
  color: var(--primary-color);
  font-weight: var(--font-weight-semibold);
  background: var(--primary-light);
}

.settings-content {
  flex: 1;
  padding: var(--spacing-xl);
  overflow: auto;
  min-width: 0;
}

.settings-forbidden {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 60%;
  color: var(--text-secondary);
  text-align: center;
  gap: var(--spacing-md);
}

.settings-forbidden i {
  font-size: 48px;
  color: var(--danger-color);
}

/* ── INT-743 深色模式：全局遗留白底（.page-header/.card）与 slate 标签色不随 .dark 切换，
     本工作区在深色下统一走语义 token（浅色零变化、深色可读）。
     基座 INT-735 / CSS 重构 INT-757 全局收敛前此处先行；不写死数值 ── */
.dark .system-settings-workspace :deep(.page-header) {
  background-color: var(--background-primary);
}

.dark .system-settings-workspace :deep(.page-description) {
  color: var(--text-secondary);
}

.dark .system-settings-workspace :deep(.card) {
  background-color: var(--card);
}

.dark .system-settings-workspace :deep(.form-group label) {
  color: var(--foreground);
}
</style>
