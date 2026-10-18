/**
 * AI 对话权限派生（application 层 composable；08_AI对话页 §5 表单一来源）。
 * 空态 starter / 全能力分组逐项过滤：无权限隐藏而非置灰；无码域统一标「待接入」。
 * AUTH_MODE=off（后端无认证，前端无 token）时照 App.vue 同口径全量显示。
 */
import { computed } from 'vue'
import { useAuthStore } from '../../store/authStore'
import {
  STARTER_PROMPTS,
  CAPABILITY_GROUPS,
} from '../../domain/constants/aiChat'

export function useChatPermissions() {
  const authStore = useAuthStore()

  const hasPermission = (perm: string | null): boolean => {
    if (!perm) return true // 无码域：可显不可执行（标「待接入」，红线不假接线）
    return authStore.hasPermission(perm)
  }

  /** 常用入门四卡（权限过滤；AUTH_MODE=off 全量显示） */
  const visibleStarters = computed(() => {
    if (!authStore.isLoggedIn) return STARTER_PROMPTS
    return STARTER_PROMPTS.filter((s) => hasPermission(s.requiredPermission))
  })

  /** 全能力分组 11 域（权限过滤；AUTH_MODE=off 全量显示；无码域保留显「待接入」） */
  const visibleCapabilityGroups = computed(() => {
    if (!authStore.isLoggedIn) return CAPABILITY_GROUPS
    return CAPABILITY_GROUPS.filter((g) => hasPermission(g.requiredPermission))
  })

  return {
    hasPermission,
    visibleStarters,
    visibleCapabilityGroups,
  }
}
