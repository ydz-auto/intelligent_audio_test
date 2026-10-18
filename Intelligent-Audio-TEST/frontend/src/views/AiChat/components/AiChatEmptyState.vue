<template>
  <div class="ai-chat-empty">
    <div class="empty-center">
      <div class="empty-icon">
        <i class="fas fa-robot"></i>
      </div>
      <h2 class="empty-title">{{ EMPTY_STATE_COPY.title }}</h2>
      <p class="empty-desc">{{ EMPTY_STATE_COPY.description }}</p>

      <!-- 区一：常用入门（报告高频四卡，Report First） -->
      <div v-if="visibleStarters.length" class="starter-section">
        <h3 class="starter-section-title">{{ EMPTY_STATE_COPY.commonStartersTitle }}</h3>
        <div class="starter-grid">
          <button
            v-for="starter in visibleStarters"
            :key="starter.key"
            type="button"
            class="starter-card"
            @click="emit('fill-prompt', starter.prompt)"
          >
            <i :class="starter.icon" class="starter-icon"></i>
            <span class="starter-label">{{ starter.label }}</span>
          </button>
        </div>
      </div>

      <!-- 区二：全能力分组（11 域入口卡，权限过滤 + 待接入徽标） -->
      <div v-if="visibleCapabilityGroups.length" class="starter-section">
        <h3 class="starter-section-title">{{ EMPTY_STATE_COPY.capabilityGroupsTitle }}</h3>
        <div class="capability-grid">
          <button
            v-for="group in visibleCapabilityGroups"
            :key="group.key"
            type="button"
            class="capability-card"
            :disabled="!group.prompt"
            @click="group.prompt && emit('fill-prompt', group.prompt)"
          >
            <i :class="group.icon" class="capability-icon"></i>
            <div class="capability-info">
              <span class="capability-label">{{ group.label }}</span>
              <span class="capability-domain">{{ group.domainLabel }}</span>
            </div>
            <span v-if="group.toolCount !== null" class="capability-count">{{ group.toolCount }} 工具</span>
            <span v-else class="capability-pending">{{ EMPTY_STATE_COPY.capabilityPendingBadge }}</span>
          </button>
        </div>
      </div>

      <!-- Demo 说明尾注（§3.10：上线为 Demo 预览版，Agent 能力接入后完整开放） -->
      <p class="empty-demo-note">
        当前为 Demo 预览：Agent 能力待接入，对话使用你配置的 LLM 供应商。
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { EMPTY_STATE_COPY } from '@/domain/constants/aiChat'
import { useChatPermissions } from '@/composables/aiChat/useChatPermissions'

const emit = defineEmits<{
  (e: 'fill-prompt', prompt: string): void
}>()

const { visibleStarters, visibleCapabilityGroups } = useChatPermissions()
</script>

<style scoped>
.ai-chat-empty {
  display: flex;
  min-height: 100%;
  align-items: center;
  justify-content: center;
  padding: 24px 16px;
}

.empty-center {
  width: 100%;
  max-width: 720px;
  margin: 0 auto;
  text-align: center;
}

.empty-icon {
  width: 48px;
  height: 48px;
  margin: 0 auto 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-lg);
  background: var(--muted);
  color: var(--muted-foreground);
  font-size: 20px;
}

.empty-title {
  margin: 0 0 8px;
  font-size: 20px;
  font-weight: 600;
  color: var(--foreground);
}

.empty-desc {
  margin: 0 auto 24px;
  max-width: 560px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--muted-foreground);
}

.starter-section {
  margin-bottom: 24px;
  text-align: left;
}

.starter-section-title {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--foreground);
  text-align: center;
}

.starter-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
}

.starter-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--card);
  cursor: pointer;
  font: inherit;
  color: var(--foreground);
  transition: border-color 0.2s, box-shadow 0.2s;
}

.starter-card:hover {
  border-color: var(--primary);
  box-shadow: 0 2px 8px color-mix(in srgb, var(--primary) 15%, transparent);
}

.starter-icon {
  font-size: 16px;
  color: var(--primary);
  flex-shrink: 0;
}

.starter-label {
  font-size: 13px;
  font-weight: 500;
}

.capability-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 10px;
}

.capability-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--card);
  cursor: pointer;
  font: inherit;
  color: var(--foreground);
  text-align: left;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.capability-card:hover:not(:disabled) {
  border-color: var(--primary);
  box-shadow: 0 2px 8px color-mix(in srgb, var(--primary) 15%, transparent);
}

.capability-card:disabled {
  cursor: default;
  opacity: 0.9;
}

.capability-icon {
  font-size: 15px;
  color: var(--secondary);
  flex-shrink: 0;
}

.capability-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}

.capability-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--foreground);
}

.capability-domain {
  font-size: 11px;
  color: var(--muted-foreground);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.capability-count {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--muted-foreground);
  background: var(--muted);
  border-radius: 999px;
  padding: 2px 8px;
}

.capability-pending {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--warning-foreground);
  background: var(--warning-light, color-mix(in srgb, var(--warning) 15%, transparent));
  border-radius: 999px;
  padding: 2px 8px;
}

.empty-demo-note {
  margin: 16px 0 0;
  font-size: 12px;
  color: var(--warning-dark, var(--muted-foreground));
}
</style>
