<template>
  <div class="system-settings-page">
    <div class="page-header">
      <div class="header-left">
        <h2>系统设置</h2>
        <p>{{ domainTitle }}<template v-if="sectionTitle"> · {{ sectionTitle }}</template></p>
      </div>
    </div>

    <div class="settings-placeholder-card">
      <i class="fas fa-hard-hat"></i>
      <p>「{{ domainTitle }}{{ sectionTitle ? ' → ' + sectionTitle : '' }}」分区建设中</p>
      <p class="settings-placeholder-hint">系统设置六域工作区由配置运维卡 09 落地（站点设置/用户与权限/认证设置/外观与主题/安全设置/运维设置）</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import '../../assets/styles/test-common.css'
import '../../assets/styles/components/navigation.css'
import '../../assets/styles/components/log.css'
import '../../assets/styles/layouts/main.css'

import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { SETTINGS_DOMAINS } from '../../config/navigation'

const route = useRoute()

const domainId = computed(() => route.params.domain as string)
const sectionId = computed(() => route.params.section as string | undefined)

const domain = computed(() => SETTINGS_DOMAINS.find(d => d.id === domainId.value))
const domainTitle = computed(() => domain.value?.title || '系统设置')
const sectionTitle = computed(() => {
  const section = domain.value?.sections.find(s => s.id === sectionId.value)
  return section?.title
})
</script>

<style scoped>
.system-settings-page {
  width: 100%;
}
.page-header {
  margin-bottom: 24px;
}
.page-header h2 {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  color: var(--foreground);
}
.page-header p {
  margin: 4px 0 0;
  font-size: 14px;
  color: var(--muted-foreground);
}
.settings-placeholder-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 48px 24px;
  background: var(--card);
  border: 1px dashed var(--border);
  border-radius: var(--radius-lg);
  text-align: center;
}
.settings-placeholder-card i {
  font-size: 36px;
  color: var(--warning);
}
.settings-placeholder-card p {
  margin: 0;
  font-size: 15px;
  font-weight: 500;
  color: var(--foreground);
}
.settings-placeholder-card p.settings-placeholder-hint {
  font-size: 13px;
  font-weight: 400;
  color: var(--muted-foreground);
  line-height: 1.6;
  max-width: 520px;
}
</style>
