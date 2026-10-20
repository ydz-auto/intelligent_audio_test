<template>
  <div class="profile-dropdown" ref="rootRef">
    <button class="profile-trigger" data-layout-btn @click.stop="toggleOpen">
      <AvatarBadge :name="authStore.username" />
      <span class="profile-trigger__meta">
        <span class="profile-trigger__name">{{ authStore.username }}</span>
        <span v-if="authStore.roleName" class="profile-trigger__role">{{ authStore.roleName }}</span>
      </span>
      <i class="fas fa-chevron-down profile-trigger__caret"></i>
    </button>

    <div v-if="open" class="profile-panel" @click.stop>
      <div class="profile-panel__head">
        <AvatarBadge :name="authStore.username" :size="40" />
        <div>
          <p class="profile-panel__name">{{ authStore.username }}</p>
          <p v-if="authStore.roleName" class="profile-panel__role">{{ authStore.roleName }}</p>
        </div>
      </div>
      <div class="profile-panel__menu">
        <button class="profile-menu-item" data-layout-btn @click="go('/profile')">
          <i class="fas fa-user"></i> 个人中心
        </button>
        <button v-if="canSystemSettings" class="profile-menu-item" data-layout-btn @click="go('/system-settings/site')">
          <i class="fas fa-gear"></i> 系统设置
        </button>
      </div>
      <div class="profile-panel__divider"></div>
      <button class="profile-menu-item profile-menu-item--danger" data-layout-btn @click="handleLogout">
        <i class="fas fa-sign-out-alt"></i> 登出
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../../store/authStore'
import { useModalControl, MODAL_TYPES } from '../../composables/modal/useModal'
import AvatarBadge from './AvatarBadge.vue'

const authStore = useAuthStore()
const router = useRouter()
const modal = useModalControl()
const open = ref(false)
const rootRef = ref<HTMLElement | null>(null)

/** 任一设置域权限者显「系统设置」项（§2.4 ⑥） */
const canSystemSettings = computed(() =>
  authStore.hasAnyPermission('user:read', 'role:read', 'auth:manage_provider', 'log:manage'),
)

function toggleOpen() {
  open.value = !open.value
}

function go(path: string) {
  open.value = false
  router.push(path)
}

async function handleLogout() {
  open.value = false
  let confirmed: unknown = null
  try {
    confirmed = await modal.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '确认登出',
      content: '确定要退出当前账号吗？',
      confirmText: '登出',
      cancelText: '取消',
      danger: true,
    })
  } catch {
    return // 异常路径兜底：视为取消登出
  }
  if (!confirmed) return // 用户取消登出
  await authStore.logout()
  router.push('/')
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
.profile-dropdown {
  position: relative;
}
.profile-trigger {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: var(--control-height);
  padding: 0 6px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  cursor: pointer;
  transition: background var(--transition-fast);
}
.profile-trigger:hover {
  background: var(--gray-light);
}
.profile-trigger__meta {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  line-height: 1.2;
  max-width: 120px;
}
.profile-trigger__name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 120px;
}
.profile-trigger__role {
  font-size: 11px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 120px;
}
.profile-trigger__caret {
  font-size: 10px;
  color: var(--text-tertiary);
}
.profile-panel {
  position: absolute;
  right: 0;
  top: calc(100% + 8px);
  width: 220px;
  background: var(--popover);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  z-index: var(--z-index-popover);
  overflow: hidden;
}
.profile-panel__head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px;
  border-bottom: 1px solid var(--border);
}
.profile-panel__name {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}
.profile-panel__role {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
}
.profile-panel__menu {
  padding: 6px;
}
.profile-menu-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 9px 10px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-primary);
  font-size: 14px;
  cursor: pointer;
  text-align: left;
  transition: background var(--transition-fast);
}
.profile-menu-item:hover {
  background: var(--muted);
}
.profile-menu-item i {
  width: 16px;
  color: var(--text-secondary);
  font-size: 14px;
}
.profile-menu-item--danger {
  color: var(--destructive);
}
.profile-menu-item--danger i {
  color: var(--destructive);
}
.profile-panel__divider {
  height: 1px;
  background: var(--border);
  margin: 4px 0;
}
</style>
