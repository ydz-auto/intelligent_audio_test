<template>
  <div class="search-button" ref="rootRef">
    <button class="header-icon-btn" data-layout-btn title="全局搜索" @click.stop="openPanel">
      <i class="fas fa-search"></i>
    </button>
    <div v-if="open" class="search-panel" @click.stop>
      <div class="search-input-wrap">
        <i class="fas fa-search"></i>
        <input
          v-model="query"
          class="search-input"
          placeholder="搜索页面…"
          autofocus
          @keydown.enter="goFirstResult"
        />
      </div>
      <div class="search-results">
        <button
          v-for="item in filteredItems"
          :key="item.url"
          class="search-result"
          data-layout-btn
          @click="go(item.url)"
        >
          <i :class="item.icon"></i>
          <span>{{ item.title }}</span>
          <span class="search-result__group">{{ groupTitle(item) }}</span>
        </button>
        <p v-if="!filteredItems.length" class="search-empty">无匹配页面</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../../store/authStore'
import { useNavAccess } from '../../composables/layout/useNavAccess'
import { ROOT_SIDEBAR_NAV, type NavItem, type NavGroup } from '../../config/navigation'

const router = useRouter()
const authStore = useAuthStore()
const { hasNavPermission, hasNavAnyPermission } = useNavAccess()
const open = ref(false)
const query = ref('')
const rootRef = ref<HTMLElement | null>(null)

/** 权限过滤后的侧栏项（搜索命中源，§2.4 ⑤） */
const searchableItems = computed(() => {
  const items: Array<NavItem & { groupTitle: string }> = []
  for (const group of ROOT_SIDEBAR_NAV) {
    for (const item of group.items) {
      if (item.permission && !hasNavPermission(item.permission)) continue
      if (item.permissions && !hasNavAnyPermission(...item.permissions)) continue
      items.push({ ...item, groupTitle: group.title })
    }
  }
  return items
})

const filteredItems = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return searchableItems.value
  return searchableItems.value.filter(item => item.title.toLowerCase().includes(q))
})

function groupTitle(item: NavItem & { groupTitle: string }) {
  return item.groupTitle
}

function openPanel() {
  open.value = true
  query.value = ''
}

function go(url: string) {
  open.value = false
  router.push(url)
}

function goFirstResult() {
  if (filteredItems.value.length) go(filteredItems.value[0].url)
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
  width: 36px;
  height: 36px;
  border-radius: 8px;
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
.search-button {
  position: relative;
}
.search-panel {
  position: absolute;
  right: 0;
  top: calc(100% + 8px);
  width: 300px;
  background: var(--popover);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  z-index: 1200;
  overflow: hidden;
}
.search-input-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
}
.search-input-wrap i {
  color: var(--text-tertiary);
  font-size: 14px;
}
.search-input {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  color: var(--text-primary);
  font-size: 14px;
}
.search-results {
  max-height: 300px;
  overflow-y: auto;
  padding: 6px;
}
.search-result {
  display: flex;
  align-items: center;
  gap: 10px;
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
.search-result:hover {
  background: var(--muted);
}
.search-result i {
  width: 16px;
  color: var(--primary);
  font-size: 14px;
}
.search-result__group {
  margin-left: auto;
  font-size: 12px;
  color: var(--text-tertiary);
}
.search-empty {
  margin: 0;
  padding: 16px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 13px;
}
</style>
