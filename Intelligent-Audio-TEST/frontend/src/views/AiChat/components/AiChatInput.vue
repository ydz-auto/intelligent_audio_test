<template>
  <div class="ai-chat-input-card">
    <textarea
      ref="textareaRef"
      :value="value"
      class="ai-chat-textarea"
      :placeholder="EMPTY_STATE_COPY.placeholder"
      :disabled="isGenerating"
      @input="onInput"
      @compositionstart="onCompositionStart"
      @compositionend="onCompositionEnd"
      @keydown.enter.prevent="onKeydownEnter"
    ></textarea>
    <div class="ai-chat-input-footer">
      <!-- 左工具组：模型/供应商切换 + 清空对话 -->
      <div class="input-tools">
        <ModelProviderSwitcher
          :providers="providers"
          :config="config"
          @select-provider="emit('select-provider', $event)"
          @select-model="(providerId, modelId) => emit('select-model', providerId, modelId)"
          @manage-providers="emit('manage-providers')"
        />
        <button
          type="button"
          class="clear-btn"
          :disabled="!hasMessages || isGenerating"
          :title="INPUT_COPY.clear"
          @click="emit('clear')"
        >
          <i class="fas fa-trash"></i>
        </button>
      </div>

      <!-- 右：报告上下文选择器 + 发送 / 停止 -->
      <div class="input-actions">
        <!-- 报告上下文选择器（组件树先落；Demo 态整块不渲染，数据交互待后端立项——INT-598 方案A） -->
        <ReportContextSelector
          v-if="REPORT_CONTEXT_ENABLED"
          :config="config"
          @select-context="(id, label, type) => emit('select-context', id, label, type)"
        />
        <button
          v-if="!isGenerating"
          type="button"
          class="btn btn-primary send-btn"
          :disabled="!canSubmit"
          @click="submit"
        >
          <i class="fas fa-paper-plane"></i>
          <span class="send-label">{{ INPUT_COPY.send }}</span>
        </button>
        <button
          v-else
          type="button"
          class="stop-btn"
          @click="emit('stop')"
        >
          <i class="fas fa-square"></i>
          <span class="send-label">{{ INPUT_COPY.stop }}</span>
        </button>
      </div>
    </div>
    <!-- Demo 注记（§3.11 底栏提示） -->
    <p class="input-demo-note">Demo 预览：供应商仅存本机，不上传平台；切换模型/供应商后新对话生效。</p>
  </div>
</template>

<script setup lang="ts">
import '../../../assets/styles/test-common.css'
import '../../../assets/styles/components/common.css'
import '../../../assets/styles/components/button.css'
import '../../../assets/styles/components/card.css'
import '../../../assets/styles/components/modal.css'
import '../../../assets/styles/components/table.css'
import '../../../assets/styles/components/log.css'

import { computed, ref } from 'vue'
import type { ChatConfig, LlmProvider, ReportContextType } from '@/domain/model/aiChat'
import {
  EMPTY_STATE_COPY,
  INPUT_COPY,
} from '@/domain/constants/aiChat'
import ModelProviderSwitcher from './ModelProviderSwitcher.vue'
import ReportContextSelector from './ReportContextSelector.vue'

/**
 * 报告上下文选择器开关：数据交互待后端立项（INT-598 方案A），Demo 态整块不渲染
 * （组件树先落；立项后放开渲染并接线现有端点）。
 */
const REPORT_CONTEXT_ENABLED = false

const props = defineProps<{
  value: string
  hasMessages: boolean
  isGenerating: boolean
  providers: LlmProvider[]
  config: ChatConfig
}>()

const emit = defineEmits<{
  (e: 'update:value', value: string): void
  (e: 'submit', value: string): void
  (e: 'stop'): void
  (e: 'clear'): void
  (e: 'manage-providers'): void
  (e: 'select-provider', providerId: string): void
  (e: 'select-model', providerId: string, modelId: string): void
  (e: 'select-context', id: string, label: string, type: ReportContextType): void
}>()

const textareaRef = ref<HTMLTextAreaElement | null>(null)
let isComposing = false

const canSubmit = computed(() => props.value.trim().length > 0 && !props.isGenerating)

function onInput(event: Event): void {
  emit('update:value', (event.target as HTMLTextAreaElement).value)
}

function onCompositionStart(): void {
  isComposing = true
}

function onCompositionEnd(): void {
  isComposing = false
}

function onKeydownEnter(event: KeyboardEvent): void {
  // 输入法组合态不触发（照 playground isComposing 语义）
  if (event.isComposing || isComposing) return
  submit()
}

function submit(): void {
  if (!canSubmit.value) return
  emit('submit', props.value.trim())
}

function focusInput(): void {
  textareaRef.value?.focus()
}

defineExpose({ focusInput })
</script>

<style scoped>
.ai-chat-input-card {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--card);
  box-shadow: var(--shadow-md);
  transition: border-color 0.2s, box-shadow 0.2s;
}

.ai-chat-input-card:focus-within {
  border-color: var(--primary);
  box-shadow: var(--shadow-lg);
}

.ai-chat-textarea {
  width: 100%;
  min-height: 84px;
  padding: 14px 16px 8px;
  border: none;
  resize: none;
  font: inherit;
  font-size: 14px;
  line-height: 1.6;
  color: var(--foreground);
  background: transparent;
  box-sizing: border-box;
}

.ai-chat-textarea:focus {
  outline: none;
}

.ai-chat-textarea:disabled {
  opacity: 0.6;
}

.ai-chat-input-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 10px 10px;
  border-top: 1px solid var(--border);
}

.input-tools {
  display: flex;
  align-items: center;
  gap: 6px;
}

.clear-btn {
  width: 30px;
  height: 30px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--muted-foreground);
  font-size: 13px;
  cursor: pointer;
}

.clear-btn:hover:not(:disabled) {
  background: color-mix(in srgb, var(--destructive) 10%, transparent);
  color: var(--destructive);
}

.clear-btn:disabled {
  cursor: not-allowed;
  opacity: 0.4;
}

.input-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.send-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 32px;
  padding: 0 14px;
  border: none;
  border-radius: var(--radius-sm);
  background: var(--primary);
  color: var(--primary-foreground);
  font: inherit;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s;
}

.send-btn:hover:not(:disabled) {
  background: var(--primary-hover);
}

.send-btn:disabled {
  background: var(--muted);
  color: var(--muted-foreground);
  cursor: not-allowed;
}

.stop-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 32px;
  padding: 0 14px;
  border: 1px solid color-mix(in srgb, var(--destructive) 30%, transparent);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--destructive) 10%, transparent);
  color: var(--destructive);
  font: inherit;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
}

.send-label {
  white-space: nowrap;
}

.input-demo-note {
  margin: 0;
  padding: 0 16px 10px;
  font-size: 11px;
  color: var(--muted-foreground);
}
</style>
