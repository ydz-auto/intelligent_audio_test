<template>
  <nav class="top-nav" :class="{ 'top-nav--mobile': isMobile }">
    <router-link
      v-for="item in visibleLinks"
      :key="item.href"
      :to="item.href"
      class="top-nav__link"
      :class="{ 'top-nav__link--active': isActive(item.href) }"
      @click="handleClick(item, $event)"
    >
      {{ item.title }}
    </router-link>
  </nav>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '../../store/authStore'
import { useNavAccess } from '../../composables/layout/useNavAccess'
import { AuthMode, getEffectiveAuthMode } from '../../domain/enums'
import { TOP_NAV_LINKS, type TopNavLink } from '../../config/navigation'
import { useRequireLogin } from '../../composables/layout/useRequireLogin'

defineProps<{
  /** 移动/窄屏形态（文字间距收紧） */
  isMobile?: boolean
}>()

const route = useRoute()
const authStore = useAuthStore()
const requireLogin = useRequireLogin()
const { hasNavPermission } = useNavAccess()

/** 权限过滤后的可见链接（未登录仅公开项 + 受限项；已登录按权限码过滤） */
const visibleLinks = computed<TopNavLink[]>(() => {
  if (!authStore.isLoggedIn) {
    // AUTH_MODE=off 未登录全显（§2.6 注 4）；认证开启未登录仅公开 + 受限项
    if (getEffectiveAuthMode() === AuthMode.OFF) return TOP_NAV_LINKS
    return TOP_NAV_LINKS.filter(item => item.public || item.restricted)
  }
  return TOP_NAV_LINKS.filter(item => {
    if (item.public) return true
    if (item.permission && !hasNavPermission(item.permission)) return false
    return true
  })
})

function isActive(href: string): boolean {
  const path = route.path
  if (href === '/') return path === '/'
  if (href === '/dashboard') return path === '/dashboard' || path.startsWith('/dashboard/')
  return path === href || path.startsWith(`${href}/`)
}

function handleClick(item: TopNavLink, event: MouseEvent) {
  // 受限项未登录：认证开启时弹「需要登录」Dialog 并阻止跳转；OFF 模式直接放行
  if (item.restricted && !authStore.isLoggedIn && getEffectiveAuthMode() !== AuthMode.OFF) {
    event.preventDefault()
    requireLogin.open(item.href)
  }
}
</script>

<style scoped>
.top-nav {
  display: flex;
  align-items: center;
  gap: 4px;
  height: 100%;
}
/* 顶导航项照 React `TopNav` 药丸形态（rounded-lg + hover/active 底）：
   底色用 tokens `--muted`，不写死颜色 / 圆角（圆角 = 首页卡片同套 --radius-md）。 */
.top-nav__link {
  display: inline-flex;
  align-items: center;
  height: 32px;
  padding: 0 12px;
  font-size: 14px;
  color: var(--muted-foreground);
  text-decoration: none;
  border-radius: var(--radius-md);
  transition:
    color var(--transition-fast),
    background-color var(--transition-fast);
  white-space: nowrap;
}
.top-nav__link:hover {
  background: var(--muted);
  color: var(--foreground);
}
.top-nav__link--active {
  background: var(--muted);
  color: var(--foreground);
  font-weight: 600;
}
.top-nav--mobile .top-nav__link {
  padding: 0 8px;
  height: 30px;
}
</style>
