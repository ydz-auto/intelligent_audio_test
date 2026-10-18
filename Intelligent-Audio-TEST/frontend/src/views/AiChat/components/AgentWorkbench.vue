<template>
  <!-- 最小化胶囊 -->
  <button
    v-if="workbench.open && workbench.minimized"
    type="button"
    class="agent-workbench-capsule"
    :aria-label="'恢复 Agent 工作台'"
    @click="workbench.setMinimized(false)"
  >
    <i class="fas fa-wand-magic-sparkles capsule-icon"></i>
    <span class="capsule-text">灵犀Agent</span>
  </button>

  <!-- 浮窗主体 -->
  <div v-else-if="workbench.open" class="agent-workbench">
    <!-- 头行 -->
    <div class="awb-header">
      <i class="fas fa-wand-magic-sparkles awb-header-icon"></i>
      <span class="awb-title">灵犀Agent</span>
      <span class="awb-demo-badge" :title="DEMO_COPY.floatingTooltip">{{ DEMO_COPY.badge }}</span>
      <span class="awb-header-spacer"></span>
      <button type="button" class="awb-action-btn" :title="'最小化'" @click="workbench.setMinimized(true)">
        <i class="fas fa-minus"></i>
      </button>
      <button type="button" class="awb-action-btn" :title="'展开整页'" @click="expandToPage">
        <i class="fas fa-maximize"></i>
      </button>
      <button type="button" class="awb-action-btn" :title="'关闭'" @click="workbench.setOpen(false)">
        <i class="fas fa-xmark"></i>
      </button>
    </div>

    <!-- 会话区（紧凑） -->
    <div class="awb-conversation">
      <AiChatConversation
        :messages="store.messages"
        :is-generating="store.isGenerating"
        :editing-key="store.editingMessageKey"
        @fill-prompt="handleFillPrompt"
        @regenerate="store.handleRegenerateMessage"
        @edit="store.handleEditMessage"
        @delete="store.handleDeleteMessage"
        @save-edit="(content, resend) => store.applyEdit(content, resend)"
        @cancel-edit="store.handleEditOpenChange(false)"
        @view-document="expandToPage"
      />
    </div>

    <!-- 输入区（紧凑） -->
    <div class="awb-input">
      <AiChatInput
        :value="draftText"
        :has-messages="store.messages.length > 0"
        :is-generating="store.isGenerating"
        :providers="store.providers"
        :config="store.config"
        @update:value="draftText = $event"
        @submit="handleSubmit"
        @stop="store.stopGeneration"
        @clear="handleClear"
        @manage-providers="providerManagerOpen = true"
        @select-provider="(providerId) => store.updateConfig({ providerId })"
        @select-model="(providerId, modelId) => store.updateConfig({ providerId, modelId })"
        @select-context="(id, label, type) => store.updateConfig({ reportContextId: id, reportContextLabel: label, reportContextType: type })"
      />
    </div>

    <!-- 供应商管理弹窗（浮窗共用同一供应商清单，§3.11） -->
    <ProviderManagerModal v-model:visible="providerManagerOpen" />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAiChatStore } from '@/store/aiChatStore'
import { useAgentWorkbenchStore } from '@/store/agentWorkbenchStore'
import { DEMO_COPY, INPUT_COPY } from '@/domain/constants/aiChat'
import { useModalControl } from '@/composables/modal/useModal'
import { MODAL_TYPES } from '@/composables/modal/constants'
import { useNotification } from '@/composables/modal/useNotification'
import AiChatConversation from './AiChatConversation.vue'
import AiChatInput from './AiChatInput.vue'
import ProviderManagerModal from './ProviderManagerModal.vue'

const store = useAiChatStore()
const workbench = useAgentWorkbenchStore()
const router = useRouter()
const modalControl = useModalControl()
const notification = useNotification()

const draftText = ref('')
const providerManagerOpen = ref(false)

function handleFillPrompt(prompt: string): void {
  draftText.value = prompt
}

function handleSubmit(text: string): void {
  store.handleSendMessage(text)
  draftText.value = ''
}

/** 清空对话（与整页同款：确认弹窗 + 成功 toast，§3.5/§3.1B 两形态一致） */
async function handleClear(): Promise<void> {
  try {
    await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: INPUT_COPY.clearConfirmTitle,
      content: INPUT_COPY.clearConfirmContent,
      confirmText: INPUT_COPY.clearConfirm,
      cancelText: '取消',
      danger: true,
    })
    store.clearMessages()
    draftText.value = ''
    notification.success(INPUT_COPY.clearDone)
  } catch {
    // 用户取消清空
  }
}

/** 展开整页（保留会话：浮窗与整页共用同一 store，§3.1B 不分裂会话） */
function expandToPage(): void {
  void router.push('/ai-chat')
}
</script>

<style scoped>
/* 悬浮窗（照 Cloudflare dash「面板跨页驻留」语义，§3.1B：登录壳任意页面可开，
 * 切换页面不关闭；壳集成（固定定位根挂载 + 右上角魔法按钮）由基座壳卡 INT-735 落位） */
.agent-workbench {
  position: fixed;
  bottom: 16px;
  right: 16px;
  z-index: 1200;
  width: min(28rem, calc(100vw - 1rem));
  max-height: min(44rem, calc(100svh - 5rem));
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--background);
  box-shadow: var(--shadow-lg);
  overflow: hidden;
}

.awb-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  background: var(--card);
}

.awb-header-icon {
  color: var(--primary);
  font-size: 14px;
}

.awb-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--foreground);
}

.awb-demo-badge {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 600;
  color: var(--warning-dark, var(--foreground));
  background: var(--warning-light, color-mix(in srgb, var(--warning) 20%, transparent));
  border-radius: var(--radius-full);
  padding: 1px 7px;
  cursor: help;
}

.awb-header-spacer {
  flex: 1;
}

.awb-action-btn {
  width: 26px;
  height: 26px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--muted-foreground);
  font-size: 12px;
  cursor: pointer;
}

.awb-action-btn:hover {
  background: var(--muted);
  color: var(--foreground);
}

.awb-conversation {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.awb-conversation :deep(.ai-chat-conversation) {
  padding: 12px;
}

.awb-input {
  flex-shrink: 0;
  padding: 8px 10px 10px;
  border-top: 1px solid var(--border);
  background: var(--card);
}

/* 最小化胶囊 */
.agent-workbench-capsule {
  position: fixed;
  bottom: 16px;
  right: 16px;
  z-index: 1200;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 36px;
  padding: 0 16px;
  border: none;
  border-radius: var(--radius-full);
  background: linear-gradient(115deg, #4f7cff, #9145ee 55%, #cd4bdb);
  color: #ffffff;
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 6px 20px color-mix(in srgb, #9145ee 35%, transparent);
}

.agent-workbench-capsule:hover {
  filter: brightness(1.1);
}

.capsule-icon {
  font-size: 14px;
}
</style>
