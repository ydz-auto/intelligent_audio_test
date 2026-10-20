<template>
  <div class="ai-chat-page">
    <!-- 顶部条（§3.2）：标题 + Demo 徽标 + 副文；报告工作模式钮 Agent 后端立项前不渲染（§3.6） -->
    <div class="ai-chat-header">
      <div class="ai-chat-header-left">
        <h1 class="ai-chat-title">灵犀Agent</h1>
        <span class="ai-chat-demo-badge" :title="DEMO_COPY.tooltip">{{ DEMO_COPY.badge }}</span>
      </div>
      <p class="ai-chat-subtitle">用自然语言驱动平台全部能力：报告、用例、任务、设备、日志</p>
      <div class="ai-chat-header-right">
        <!-- 报告工作模式开关：Agent 后端（DSH + Report Studio）立项后置 true（§3.6） -->
        <button
          v-if="REPORT_WORK_MODE_ENABLED"
          type="button"
          class="btn btn-secondary btn-sm"
          @click="workModeOpen = !workModeOpen"
        >
          <i class="fas fa-columns"></i>
          {{ workModeOpen ? REPORT_WORK_MODE_COPY.closePreview : REPORT_WORK_MODE_COPY.toggle }}
        </button>
      </div>
    </div>

    <!-- 会话区 + 报告工作模式双栏（§3.6：Agent 后端立项前整块不渲染） -->
    <div v-if="REPORT_WORK_MODE_ENABLED && workModeOpen" class="ai-chat-work-mode">
      <div class="ai-chat-work-mode-left">
        <div class="ai-chat-conversation-region">
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
            @view-document="() => {}"
          />
        </div>
        <div class="ai-chat-input-region">
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
      </div>
      <div class="ai-chat-work-mode-right">
        <ReportWorkModePanel
          :report="reportPreview"
          :version="1"
          @close="workModeOpen = false"
        />
      </div>
    </div>

    <!-- 单栏对话（默认形态） -->
    <template v-else>
      <div class="ai-chat-conversation-region">
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
          @view-document="() => {}"
        />
      </div>
      <div class="ai-chat-input-region">
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
    </template>

    <!-- 供应商管理弹窗（§3.11） -->
    <ProviderManagerModal v-model:visible="providerManagerOpen" />
  </div>
</template>

<script setup lang="ts">
import '../../assets/styles/test-common.css'
import '../../assets/styles/components/common.css'
import '../../assets/styles/components/button.css'
import '../../assets/styles/components/modal.css'
import '../../assets/styles/components/table.css'
import '../../assets/styles/components/navigation.css'
import '../../assets/styles/components/log.css'
import '../../assets/styles/layouts/main.css'

import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAiChatStore } from '@/store/aiChatStore'
import { useModalControl } from '@/composables/modal/useModal'
import { MODAL_TYPES } from '@/composables/modal/constants'
import { useNotification } from '@/composables/modal/useNotification'
import {
  DEMO_COPY,
  INPUT_COPY,
  REPORT_WORK_MODE_COPY,
} from '@/domain/constants/aiChat'
import { reportsPort } from '@/composables/report/reportsPort'
import AiChatConversation from './components/AiChatConversation.vue'
import AiChatInput from './components/AiChatInput.vue'
import ProviderManagerModal from './components/ProviderManagerModal.vue'
import ReportWorkModePanel from './components/ReportWorkModePanel.vue'

/**
 * 报告工作模式开关：Agent 后端（DSH + Report Studio）立项后置 true（§3.6）。
 * 立项前整块不渲染（入口钮与右栏一并隐藏），不做假 UI。
 */
const REPORT_WORK_MODE_ENABLED = false

const store = useAiChatStore()
const route = useRoute()
const modalControl = useModalControl()
const notification = useNotification()

const draftText = ref('')
const providerManagerOpen = ref(false)
const workModeOpen = ref(false)

/** URL 契约进入态报告对象（报告工作模式右栏预览用；立项后放开） */
const reportPreview = ref<Record<string, any> | null>(null)

/** URL 契约预填指令（§3.7：/ai-chat?report={id} / /ai-chat?task={id}；INT-1068 复核会话展开扩展 reviewCase） */
const initialPrompt = computed(() => {
  const report = typeof route.query.report === 'string' ? route.query.report : undefined
  const task = typeof route.query.task === 'string' ? route.query.task : undefined
  const reviewCase = typeof route.query.reviewCase === 'string' ? route.query.reviewCase : undefined
  if (report) return `帮我把报告 #${report} 的测试结果生成一份可交付报告`
  // §5.2「展开到 /ai-chat」：复核会话带入主会话继续讨论——预填对来源任务该用例的复核指令
  if (reviewCase && task) return `帮我对任务 #${task} 的用例 ${reviewCase} 的评估结果进行复核分析，给出复核通过/不通过/存疑结论 + 置信度 + 理由`
  if (task) return `帮我把任务 #${task} 的测试结果生成一份报告`
  return ''
})

function handleFillPrompt(prompt: string): void {
  draftText.value = prompt
  // 回填输入框并聚焦，不自动发送（§3.3 onSelectPrompt 语义）
  requestAnimationFrame(() => {
    const textarea = document.querySelector<HTMLTextAreaElement>('.ai-chat-input-region textarea')
    textarea?.focus()
  })
}

function handleSubmit(text: string): void {
  store.handleSendMessage(text)
  draftText.value = ''
}

async function handleClear(): Promise<void> {
  let confirmed: unknown = null
  try {
    confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: INPUT_COPY.clearConfirmTitle,
      content: INPUT_COPY.clearConfirmContent,
      confirmText: INPUT_COPY.clearConfirm,
      cancelText: '取消',
      danger: true,
    })
  } catch {
    return // 异常路径兜底：视为取消
  }
  if (!confirmed) return // 用户取消清空
  store.clearMessages()
  notification.success(INPUT_COPY.clearDone)
}

onMounted(() => {
  store.initialize()
  // URL 契约上下文绑定（§3.7：report/task 进入态）
  const report = typeof route.query.report === 'string' ? route.query.report : undefined
  const task = typeof route.query.task === 'string' ? route.query.task : undefined
  if (report || task) {
    store.bindContext({ report, task })
    draftText.value = initialPrompt.value
  }
  // 报告工作模式开启条件（§3.7：报告存在即开；立项后放开渲染）
  if (REPORT_WORK_MODE_ENABLED && report) {
    workModeOpen.value = true
    void reportsPort.getOne(Number(report)).then((data) => {
      reportPreview.value = data
    }).catch(() => {
      // 报告加载失败：保持右栏 Demo 占位（不杜撰数值）
    })
  }
})
</script>

<style scoped>
.ai-chat-page {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  height: 100%;
  overflow: hidden;
  background: var(--background);
}

/* ===== 顶部条 ===== */
.ai-chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-shrink: 0;
  padding: 12px 20px;
  border-bottom: 1px solid var(--border);
  background: var(--card);
}

.ai-chat-header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.ai-chat-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--foreground);
}

.ai-chat-demo-badge {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 600;
  color: var(--warning-dark, var(--foreground));
  background: var(--warning-light, color-mix(in srgb, var(--warning) 20%, transparent));
  border-radius: var(--radius-full);
  padding: 2px 9px;
  cursor: help;
}

.ai-chat-subtitle {
  margin: 0;
  font-size: 12px;
  color: var(--muted-foreground);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ai-chat-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ===== 会话区 / 输入区（单栏） ===== */
.ai-chat-conversation-region {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.ai-chat-input-region {
  flex-shrink: 0;
  max-width: 860px;
  width: 100%;
  margin: 0 auto;
  padding: 0 16px 16px;
  box-sizing: border-box;
}

/* ===== 报告工作模式双栏 ===== */
.ai-chat-work-mode {
  display: flex;
  flex: 1;
  min-height: 0;
}

.ai-chat-work-mode-left {
  flex: 2;
  min-width: 22rem;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.ai-chat-work-mode-right {
  flex: 3;
  min-width: 0;
  min-height: 0;
}

@media (max-width: 1024px) {
  .ai-chat-work-mode-right {
    display: none;
  }
}
</style>
