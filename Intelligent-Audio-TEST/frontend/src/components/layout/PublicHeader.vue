<template>
  <header class="public-header">
    <div class="public-header-inner">
      <!-- 品牌 -->
      <router-link to="/" class="public-brand">
        <i class="fas fa-headset brand-icon"></i>
        <span class="brand-name">智能语音测试系统</span>
      </router-link>

      <!-- 顶导航六项（总表 §2.2：主页/工作台/报告/排行榜/文档/关于） -->
      <nav class="public-nav" aria-label="主导航">
        <template v-for="item in visibleNavItems" :key="item.path">
          <a
            v-if="item.restricted"
            href="javascript:void(0)"
            class="public-nav-link restricted"
            @click.prevent="handleRestricted(item)"
          >
            {{ item.label }}
          </a>
          <router-link
            v-else
            :to="item.path"
            class="public-nav-link"
            :class="{ active: isActive(item.path) }"
          >
            {{ item.label }}
          </router-link>
        </template>
      </nav>

      <!-- 右区：主题切换 + 登录 / 头像下拉 -->
      <div class="public-actions">
        <button
          type="button"
          class="theme-toggle"
          :title="theme === 'dark' ? '切换到浅色模式' : '切换到深色模式'"
          :aria-label="theme === 'dark' ? '切换到浅色模式' : '切换到深色模式'"
          @click="handleThemeToggle"
        >
          <i :class="theme === 'dark' ? 'fas fa-sun' : 'fas fa-moon'"></i>
        </button>

        <template v-if="authStore.isLoggedIn">
          <div class="user-menu" ref="userMenuRef">
            <button type="button" class="user-trigger" @click="userMenuOpen = !userMenuOpen" :aria-expanded="userMenuOpen">
              <span class="user-avatar" :style="{ backgroundColor: avatarBg }">{{ avatarChar }}</span>
              <span class="user-name">{{ authStore.username }}</span>
              <i class="fas fa-chevron-down user-caret" :class="{ open: userMenuOpen }"></i>
            </button>
            <div v-if="userMenuOpen" class="user-menu-dropdown">
              <div class="user-menu-info">
                <span class="um-name">{{ authStore.username }}</span>
                <span class="um-role" v-if="authStore.roleName">{{ authStore.roleName }}</span>
              </div>
              <button type="button" class="um-item" @click="goProfile">
                <i class="fas fa-user"></i> 个人中心
              </button>
              <button type="button" class="um-item um-logout" @click="handleLogout">
                <i class="fas fa-sign-out-alt"></i> 登出
              </button>
            </div>
          </div>
        </template>
        <router-link v-else to="/login" class="public-login-btn">登录</router-link>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../../store/authStore'
import { AuthMode, getEffectiveAuthMode } from '../../domain/enums'
import { getCurrentTheme, toggleTheme } from '../../composables/shared/useTheme'
import { useModalControl } from '../../composables/modal/useModal'
import { MODAL_TYPES } from '../../composables/modal/constants'

interface PublicNavItem {
  path: string
  label: string
  /** 未登录受限项（点击弹「需要登录」Dialog） */
  restricted?: boolean
  /** 访问所需权限（无权限隐藏） */
  permission?: string
}

/** 顶导航六项（总表 §2.2 定稿） */
const NAV_ITEMS: PublicNavItem[] = [
  { path: '/', label: '主页' },
  { path: '/dashboard', label: '工作台', restricted: true },
  { path: '/reports', label: '报告', permission: 'report:read' },
  { path: '/rankings', label: '排行榜', permission: 'benchmark:ranking:read' },
  { path: '/user-guide', label: '文档' },
  { path: '/about', label: '关于' },
]

const authStore = useAuthStore()
const route = useRoute()
const router = useRouter()
const modal = useModalControl()

const theme = ref(getCurrentTheme())
const userMenuOpen = ref(false)
const userMenuRef = ref<HTMLElement | null>(null)

/** 头像：用户名首字符大写 + 哈希底色（对齐总表 §2.4 头像下拉） */
const avatarChar = computed(() => (authStore.username || '?').charAt(0).toUpperCase())
const avatarBg = computed(() => {
  // 身份色令牌（深浅同值，不随主题换色）
  const AVATAR_COLORS = [
    'var(--avatar-1)', 'var(--avatar-2)', 'var(--avatar-3)', 'var(--avatar-4)',
    'var(--avatar-5)', 'var(--avatar-6)', 'var(--avatar-7)',
  ]
  let hash = 0
  const name = authStore.username || ''
  for (let i = 0; i < name.length; i += 1) hash = (hash * 31 + name.charCodeAt(i)) >>> 0
  return AVATAR_COLORS[hash % AVATAR_COLORS.length]
})

/** 可见导航项：未登录（AUTH_MODE=off 兼容）显示全部；已登录按权限过滤 */
const visibleNavItems = computed<PublicNavItem[]>(() => {
  const authMode = getEffectiveAuthMode()
  if (authMode === AuthMode.OFF || !authStore.isLoggedIn) {
    // dev 部署（无 token）：全量展示；工作台保持受限项语义
    return NAV_ITEMS
  }
  return NAV_ITEMS.filter((item) => {
    if (item.restricted) return true // 工作台：登录即可
    if (!item.permission) return true // 主页/文档/关于：全员
    return authStore.hasPermission(item.permission)
  })
})

function isActive(path: string): boolean {
  if (path === '/') return route.path === '/'
  return route.path === path || route.path.startsWith(path)
}

function handleRestricted(item: PublicNavItem) {
  // 未登录且认证开启 → 「需要登录」Dialog（5 秒倒计时）→ /login?redirect=
  const authMode = getEffectiveAuthMode()
  if (authMode === AuthMode.OFF || authStore.isLoggedIn) {
    router.push(item.path)
    return
  }
  modal.open(MODAL_TYPES.LOGIN_REQUIRED, { moduleName: item.label, redirect: item.path })
    .then(() => {
      router.push({ name: 'login', query: { redirect: item.path } })
    })
    .catch(() => {
      // 取消：留在当前页
    })
}

function handleThemeToggle() {
  theme.value = toggleTheme()
}

function goProfile() {
  userMenuOpen.value = false
  router.push('/AccountSettings')
}

async function handleLogout() {
  userMenuOpen.value = false
  await authStore.logout()
  router.push('/')
}

function handleOutsideClick(e: MouseEvent) {
  if (userMenuOpen.value && userMenuRef.value && !userMenuRef.value.contains(e.target as Node)) {
    userMenuOpen.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', handleOutsideClick)
  theme.value = getCurrentTheme()
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleOutsideClick)
})
</script>

<style scoped>
.public-header {
  position: sticky;
  top: 0;
  z-index: 40;
  background: var(--background);
  border-bottom: 1px solid var(--border);
}
.public-header-inner {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 20px;
  height: 60px;
  display: flex;
  align-items: center;
  gap: 24px;
}
.public-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--foreground);
  text-decoration: none;
  white-space: nowrap;
}
.brand-icon {
  font-size: 18px;
  color: var(--primary);
}
.brand-name {
  font-size: 16px;
  font-weight: var(--font-weight-semibold);
}
.public-nav {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: 1;
  overflow-x: auto;
}
.public-nav-link {
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  font-size: 14px;
  color: var(--muted-foreground);
  text-decoration: none;
  white-space: nowrap;
  transition: color 0.15s ease, background 0.15s ease;
}
.public-nav-link:hover {
  color: var(--foreground);
  background: var(--muted);
}
.public-nav-link.active {
  color: var(--primary);
  font-weight: 500;
}
.public-nav-link.restricted {
  cursor: pointer;
}
.public-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
.theme-toggle {
  width: 32px;
  height: 32px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--muted-foreground);
  font-size: 14px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.theme-toggle:hover {
  color: var(--primary);
  border-color: var(--primary);
}
.public-login-btn {
  height: 32px;
  padding: 0 14px;
  border-radius: var(--radius-sm);
  background: var(--primary);
  color: var(--primary-foreground);
  font-size: 13px;
  font-weight: 500;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.public-login-btn:hover {
  background: var(--primary-hover);
}
/* 用户菜单 */
.user-menu {
  position: relative;
}
.user-trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  border: none;
  background: none;
  cursor: pointer;
  padding: 4px 6px;
  border-radius: var(--radius-sm);
  font: inherit;
  color: var(--foreground);
}
.user-trigger:hover {
  background: var(--muted);
}
.user-avatar {
  width: 28px;
  height: 28px;
  border-radius: var(--radius-pill);
  color: var(--color-white);
  font-size: 13px;
  font-weight: var(--font-weight-semibold);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.user-name {
  font-size: 13px;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.user-caret {
  font-size: 10px;
  color: var(--muted-foreground);
  transition: transform 0.15s ease;
}
.user-caret.open {
  transform: rotate(180deg);
}
.user-menu-dropdown {
  position: absolute;
  right: 0;
  top: calc(100% + 6px);
  width: 180px;
  background: var(--popover);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  box-shadow: 0 8px 24px color-mix(in srgb, var(--color-black) 8%, transparent);
  padding: 6px;
  z-index: 50;
}
.user-menu-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 4px;
}
.um-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--foreground);
}
.um-role {
  font-size: 12px;
  color: var(--muted-foreground);
}
.um-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  border: none;
  background: none;
  border-radius: var(--radius-sm);
  font-size: 13px;
  color: var(--foreground);
  cursor: pointer;
  text-align: left;
  font: inherit;
}
.um-item i {
  width: 16px;
  color: var(--muted-foreground);
}
.um-item:hover {
  background: var(--muted);
}
.um-logout {
  color: var(--destructive);
}
.um-logout i {
  color: var(--destructive);
}
@media (max-width: 768px) {
  .public-header-inner {
    gap: 12px;
    padding: 0 12px;
  }
  .brand-name {
    display: none;
  }
  .user-name {
    display: none;
  }
}
</style>
