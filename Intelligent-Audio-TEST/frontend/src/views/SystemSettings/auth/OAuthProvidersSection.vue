<template>
  <div v-if="allowed" class="oauth-providers-section">
    <!-- 收编原 /OAuthProviders 页（总表 §2.5 认证设置 → OAuth 提供方；旧链 redirect 由路由表承接） -->
    <OAuthProviderManagement />
  </div>
  <div v-else class="settings-forbidden">
    <i class="fas fa-lock"></i>
    <p>需要 auth:manage_provider 权限</p>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import OAuthProviderManagement from '@/views/OAuthProviders/OAuthProviderManagement.vue'
import { useAuthStore } from '@/store/authStore'
import { settingsPermissionsOpen } from '../settingsConfig'

const authStore = useAuthStore()
// AUTH_MODE=off 全显短路（收编前旧 /OAuthProviders 经路由 meta off 放行可访问，收编后不缩权限）
const allowed = computed(() =>
  settingsPermissionsOpen() || authStore.hasPermission('auth:manage_provider')
)
</script>

<style scoped>
.settings-forbidden {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 0;
  color: var(--muted-foreground);
  gap: var(--spacing-sm);
}

.settings-forbidden i {
  font-size: 40px;
  color: var(--destructive);
}
</style>
