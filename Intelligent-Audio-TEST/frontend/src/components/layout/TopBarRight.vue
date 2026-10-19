<template>
  <div class="top-bar-right" :class="`top-bar-right--${mode}`">
    <!-- 灵犀Agent 魔法按钮（右上角首位，report:read 显） -->
    <AgentWorkbenchButton
      v-if="mode === 'authenticated' && hasNavPermission('report:read')"
    />

    <!-- 全局算法切换器（algorithm:read 显；/reports /rankings 不渲染，页内算法卡片网格） -->
    <GlobalAlgorithmSwitcher
      v-if="mode === 'authenticated' && hasNavPermission('algorithm:read') && !isSwitcherHiddenRoute"
    />

    <!-- 全局搜索（登录即可） -->
    <SearchButton v-if="mode === 'authenticated' && authStore.isLoggedIn" />

    <!-- 通知中心（公共站头为受限项：未登录点击弹 Dialog） -->
    <NotificationPopover />

    <!-- 主题切换（全员） -->
    <ThemeSwitcher />

    <!-- 公共站头：未登录 → 登录按钮；已登录 → 头像下拉 -->
    <template v-if="mode === 'public'">
      <button v-if="!authStore.isLoggedIn" class="login-btn" data-layout-btn @click="goLogin">登 录</button>
      <ProfileDropdown v-else />
    </template>

    <!-- 工作台顶栏：头像下拉（已登录） -->
    <ProfileDropdown v-else-if="authStore.isLoggedIn" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../../store/authStore'
import { useNavAccess } from '../../composables/layout/useNavAccess'
import AgentWorkbenchButton from './AgentWorkbenchButton.vue'
import GlobalAlgorithmSwitcher from './GlobalAlgorithmSwitcher.vue'
import SearchButton from './SearchButton.vue'
import NotificationPopover from './NotificationPopover.vue'
import ThemeSwitcher from './ThemeSwitcher.vue'
import ProfileDropdown from './ProfileDropdown.vue'

const props = defineProps<{
  mode: 'authenticated' | 'public'
}>()

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const { hasNavPermission } = useNavAccess()

/** /reports 报告展示页与 /rankings 公开页不渲染右上角算法切换器（§2.4 ②） */
const isSwitcherHiddenRoute = computed(() => {
  const path = route.path
  return path.startsWith('/reports') || path.startsWith('/rankings')
})

function goLogin() {
  router.push({ name: 'login', query: { redirect: route.fullPath } })
}
</script>

<style scoped>
.top-bar-right {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
}
.login-btn {
  height: var(--control-height);
  padding: 0 16px;
  border: 1px solid var(--ring);
  border-radius: var(--radius-sm);
  background: var(--primary);
  color: var(--primary-foreground);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition-fast);
}
.login-btn:hover {
  background: var(--primary-hover);
}
</style>
