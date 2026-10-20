<template>
  <aside
    class="app-sidebar"
    :class="{ 'app-sidebar--collapsed': displayCollapsed }"
    @mouseenter="handleEnter"
    @mouseleave="handleLeave"
  >
    <!-- 侧栏顶：折叠/固定切换 -->
    <div class="app-sidebar__toolbar">
      <button class="collapse-btn" :title="fixedCollapsed ? '固定展开侧栏' : '折叠侧栏'" @click="toggleCollapsed">
        <i class="fas fa-angles-left" :class="{ 'fas fa-angles-right': fixedCollapsed }"></i>
      </button>
    </div>

    <!-- 系统设置 drill-in：命中 /system-settings/* 整树替换 -->
    <div v-if="isSystemSettings" class="app-sidebar__body">
      <button class="back-to-workspace" @click="go('/dashboard')">
        <i class="fas fa-arrow-left"></i>
        <span v-if="!displayCollapsed">返回工作台</span>
      </button>
      <nav class="sidebar-nav">
        <div v-for="domain in visibleSettingsDomains" :key="domain.id" class="sidebar-group">
          <div v-if="!displayCollapsed" class="sidebar-group__title">
            <i :class="domain.icon"></i>
            <span>{{ domain.title }}</span>
          </div>
          <div v-else class="sidebar-group__title sidebar-group__title--icon-only" :title="domain.title">
            <i :class="domain.icon"></i>
          </div>
          <ul class="sidebar-group__items">
            <li v-for="section in visibleSections(domain)" :key="section.id">
              <router-link
                :to="`/system-settings/${domain.id}/${section.id}`"
                class="sidebar-item"
                :class="{ 'sidebar-item--active': isSettingsActive(domain.id, section.id) }"
                :title="section.title"
              >
                <i class="sidebar-item__icon"></i>
                <span v-if="!displayCollapsed" class="sidebar-item__label">{{ section.title }}</span>
              </router-link>
            </li>
          </ul>
        </div>
      </nav>
    </div>

    <!-- 工作台侧栏六组 -->
    <div v-else class="app-sidebar__body">
      <nav class="sidebar-nav">
        <div v-for="group in visibleGroups" :key="group.id" class="sidebar-group">
          <div class="sidebar-group__title" :class="{ 'sidebar-group__title--icon-only': displayCollapsed }" :title="group.title">
            <i class="fas fa-circle sidebar-group__dot"></i>
            <span v-if="!displayCollapsed">{{ group.title }}</span>
          </div>
          <ul class="sidebar-group__items">
            <li v-for="item in group.items" :key="item.url">
              <router-link
                :to="item.url"
                class="sidebar-item"
                :class="{ 'sidebar-item--active': isItemActive(item) }"
                :title="item.title"
              >
                <i :class="item.icon" class="sidebar-item__icon"></i>
                <span v-if="!displayCollapsed" class="sidebar-item__label">{{ item.title }}</span>
              </router-link>
            </li>
          </ul>
        </div>
      </nav>
    </div>
  </aside>
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

import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../../store/authStore'
import { useNavAccess } from '../../composables/layout/useNavAccess'
import {
  ROOT_SIDEBAR_NAV, SETTINGS_DOMAINS,
  SYSTEM_SETTINGS_PATH_PATTERN, SIDEBAR_STATE_KEY, type SettingsDomain,
} from '../../config/navigation'

const props = defineProps<{
  /** 常驻折叠初值（用户偏好，hover 展开后离开自动收回） */
  collapsed?: boolean
}>()
const emit = defineEmits<{
  (e: 'update:collapsed', value: boolean): void
}>()

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const { hasNavPermission, hasNavAnyPermission } = useNavAccess()

// 常驻折叠态（用户切换的固定偏好）+ 临时 hover 展开态
// INT-894：默认展开（照 React getCookie('iatp:sidebar:v1:state') !== 'false'），
// 显式切换写回 localStorage（刷新/重登保持）；hover 仅临时展开，不写回。
function readSidebarCollapsed(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_STATE_KEY) === 'false'
  } catch {
    return false
  }
}
function persistSidebarCollapsed(collapsed: boolean) {
  try {
    // 照 React：存「展开」布尔
    localStorage.setItem(SIDEBAR_STATE_KEY, String(!collapsed))
  } catch {
    // 忽略持久化失败（隐私模式等）
  }
}

const fixedCollapsed = ref(props.collapsed ?? readSidebarCollapsed())
const isHovering = ref(false)
const displayCollapsed = computed(() => fixedCollapsed.value && !isHovering.value)

function syncCollapsed() {
  emit('update:collapsed', displayCollapsed.value)
}

const isSystemSettings = computed(() => SYSTEM_SETTINGS_PATH_PATTERN.test(route.path))

function isItemActive(item: { url: string; activeUrls?: string[] }): boolean {
  const path = route.path
  if (path === item.url || path.startsWith(`${item.url}/`)) return true
  if (item.activeUrls?.some(p => path === p || path.startsWith(`${p}/`))) return true
  return false
}

function itemVisible(item: { permission?: string; permissions?: string[] }): boolean {
  if (item.permission && !hasNavPermission(item.permission)) return false
  if (item.permissions && !hasNavAnyPermission(...item.permissions)) return false
  return true
}

/** 工作台六组：逐项权限过滤 + 空组整组隐藏 */
const visibleGroups = computed(() => {
  const groups = ROOT_SIDEBAR_NAV
    .map(group => ({
      ...group,
      items: group.items.filter(itemVisible),
    }))
    .filter(group => group.items.length > 0)
  return groups
})

/** 设置树域过滤（域级门槛不满足整组隐藏） */
const visibleSettingsDomains = computed(() => {
  return SETTINGS_DOMAINS.filter(domainVisible)
})

function domainVisible(domain: SettingsDomain): boolean {
  if (domain.permission && !hasNavPermission(domain.permission)) return false
  if (domain.permissions && !hasNavAnyPermission(...domain.permissions)) return false
  return true
}

function visibleSections(domain: SettingsDomain) {
  return domain.sections.filter(section => {
    if (section.permission && !hasNavPermission(section.permission)) return false
    if (section.permissions && !hasNavAnyPermission(...section.permissions)) return false
    return true
  })
}

function isSettingsActive(domainId: string, sectionId: string): boolean {
  return route.path === `/system-settings/${domainId}/${sectionId}`
}

function toggleCollapsed() {
  fixedCollapsed.value = !fixedCollapsed.value
  isHovering.value = false
  persistSidebarCollapsed(fixedCollapsed.value)
  syncCollapsed()
}

function handleEnter() {
  isHovering.value = true
  syncCollapsed()
}

function handleLeave() {
  isHovering.value = false
  syncCollapsed()
}

function go(path: string) {
  router.push(path)
}
</script>

<style scoped>
.app-sidebar {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--sidebar);
  border-right: 1px solid var(--sidebar-border);
  transition: width var(--transition-normal);
  overflow: hidden;
  width: var(--sidebar-width);
}
.app-sidebar--collapsed {
  width: 56px;
}
.app-sidebar__toolbar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: 8px;
  border-bottom: 1px solid var(--sidebar-border);
  flex-shrink: 0;
}
.collapse-btn {
  width: 28px;
  height: 28px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--muted-foreground);
  font-size: 14px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition-fast);
}
.collapse-btn:hover {
  background: var(--gray-light);
  color: var(--foreground);
}
.app-sidebar__body {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 8px 8px 24px;
}
.back-to-workspace {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 12px;
  margin-bottom: 8px;
  border: none;
  border-radius: var(--radius-sm);
  background: var(--muted);
  color: var(--foreground);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: background var(--transition-fast);
}
.back-to-workspace:hover {
  background: var(--gray-light);
}
.back-to-workspace i {
  color: var(--primary);
}
.sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.sidebar-group {
  display: flex;
  flex-direction: column;
}
.sidebar-group__title {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  white-space: nowrap;
  overflow: hidden;
}
.sidebar-group__title--icon-only {
  justify-content: center;
  padding: 10px 0 6px;
}
.sidebar-group__title i {
  font-size: 12px;
}
.sidebar-group__title i.sidebar-group__dot {
  font-size: 5px;
  color: var(--text-tertiary);
}
.sidebar-group__items {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.sidebar-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border-radius: var(--radius-sm);
  color: var(--muted-foreground);
  font-size: 14px;
  text-decoration: none;
  transition: all var(--transition-fast);
  white-space: nowrap;
  overflow: hidden;
  min-height: 38px;
}
.sidebar-item:hover {
  background: var(--muted);
  color: var(--foreground);
}
.sidebar-item--active {
  background: var(--accent);
  color: var(--primary);
  font-weight: 600;
}
.sidebar-item__icon {
  width: 18px;
  font-size: 14px;
  text-align: center;
  flex-shrink: 0;
}
.sidebar-item__label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
}
.app-sidebar--collapsed .sidebar-item {
  justify-content: center;
  padding: 9px 0;
}
.app-sidebar--collapsed .sidebar-item__label {
  display: none;
}
</style>
