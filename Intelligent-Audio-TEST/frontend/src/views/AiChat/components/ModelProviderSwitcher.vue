<template>
  <div class="provider-switcher">
    <!-- 触发钮（当前模型 + 供应商 Badge + 上下箭头） -->
    <button
      type="button"
      class="provider-switcher-trigger"
      :class="{ 'provider-switcher-trigger--active': open }"
      @click="toggleOpen"
    >
      <i class="fas fa-microchip trigger-icon"></i>
      <span v-if="currentModel" class="trigger-model">{{ currentModel }}</span>
      <span v-else class="trigger-model trigger-model--placeholder">{{ currentProvider ? '选择模型' : '未配置 LLM 供应商 → 点击配置' }}</span>
      <span v-if="currentProvider" class="trigger-provider">{{ currentProvider.name }}</span>
      <i class="fas fa-chevron-up trigger-chevron" :class="{ 'trigger-chevron--down': !open }"></i>
    </button>

    <!-- 双列选择器（自下而上弹出） -->
    <div v-if="open" class="provider-dropdown" ref="dropdownRef">
      <div class="provider-columns">
        <!-- 左列：供应商 -->
        <div class="column-providers">
          <div class="column-header">供应商</div>
          <div class="column-scroll">
            <button
              v-for="provider in providers"
              :key="provider.id"
              type="button"
              class="provider-item"
              :class="{ 'provider-item--active': provider.id === selectedProviderId }"
              @click="handleSelectProvider(provider.id)"
            >
              <span class="provider-item-name">{{ provider.name }}</span>
              <span v-if="provider.isDefault" class="provider-item-default">默认</span>
            </button>
            <div v-if="providers.length === 0" class="column-empty">未配置供应商</div>
          </div>
          <button type="button" class="manage-link" @click="emit('manage-providers')">
            <i class="fas fa-sliders"></i> 管理供应商
          </button>
        </div>

        <!-- 右列：模型 -->
        <div class="column-models">
          <div class="column-header">模型</div>
          <div class="column-scroll">
            <template v-if="selectedProvider">
              <button
                v-for="model in selectedProvider.models"
                :key="model"
                type="button"
                class="model-item"
                :class="{ 'model-item--active': model === selectedModelId }"
                @click="handleSelectModel(selectedProvider.id, model)"
              >
                <i class="fas fa-check model-item-check" v-if="model === selectedModelId"></i>
                <span class="model-item-name">{{ model }}</span>
              </button>
              <div v-if="selectedProvider.models.length === 0" class="column-empty">
                暂无模型，可在「管理供应商」中登记或自动获取
              </div>
            </template>
            <div v-else class="column-empty">请先选择供应商</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import type { ChatConfig, LlmProvider } from '@/domain/model/aiChat'
import { MODEL_PROVIDER_COPY } from '@/domain/constants/aiChat'

const props = defineProps<{
  providers: LlmProvider[]
  config: ChatConfig
}>()

const emit = defineEmits<{
  (e: 'select-provider', providerId: string): void
  (e: 'select-model', providerId: string, modelId: string): void
  (e: 'manage-providers'): void
}>()

const open = ref(false)
const dropdownRef = ref<HTMLElement | null>(null)

const selectedProviderId = computed(() => props.config.providerId)
const selectedModelId = computed(() => props.config.modelId)
const currentProvider = computed(
  () => props.providers.find((p) => p.id === props.config.providerId) ?? props.providers[0] ?? null
)
const currentModel = computed(() => props.config.modelId)
const selectedProvider = computed(
  () => props.providers.find((p) => p.id === selectedProviderId.value) ?? null
)

function toggleOpen(): void {
  open.value = !open.value
}

function handleSelectProvider(providerId: string): void {
  emit('select-provider', providerId)
  // 供应商切换后自动选中其第一个模型（§3.11：切换模型/供应商后新对话生效）
  const provider = props.providers.find((p) => p.id === providerId)
  if (provider && provider.models.length && provider.models[0] !== selectedModelId.value) {
    emit('select-model', providerId, provider.models[0])
  }
}

function handleSelectModel(providerId: string, modelId: string): void {
  emit('select-model', providerId, modelId)
  open.value = false
}

function handleDocumentClick(event: MouseEvent): void {
  const el = dropdownRef.value
  if (!el) return
  if (!el.contains(event.target as Node)) {
    open.value = false
  }
}

function handleKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') open.value = false
}

watch(open, (isOpen) => {
  if (isOpen) {
    document.addEventListener('click', handleDocumentClick)
    document.addEventListener('keydown', handleKeydown)
  } else {
    document.removeEventListener('click', handleDocumentClick)
    document.removeEventListener('keydown', handleKeydown)
  }
})

onUnmounted(() => {
  document.removeEventListener('click', handleDocumentClick)
  document.removeEventListener('keydown', handleKeydown)
})
</script>

<style scoped>
.provider-switcher {
  position: relative;
}

.provider-switcher-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 220px;
  min-height: 32px;
  padding: 0 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--card);
  color: var(--foreground);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  transition: border-color 0.2s;
}

.provider-switcher-trigger:hover,
.provider-switcher-trigger--active {
  border-color: var(--primary);
}

.trigger-icon {
  color: var(--muted-foreground);
  font-size: 13px;
}

.trigger-model {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.trigger-model--placeholder {
  color: var(--muted-foreground);
}

.trigger-provider {
  flex-shrink: 0;
  font-size: 10px;
  color: var(--muted-foreground);
  background: var(--muted);
  border-radius: 999px;
  padding: 1px 6px;
}

.trigger-chevron {
  margin-left: auto;
  font-size: 11px;
  color: var(--muted-foreground);
  opacity: 0.6;
}

.trigger-chevron--down {
  transform: rotate(180deg);
}

/* ===== 双列下拉 ===== */
.provider-dropdown {
  position: absolute;
  bottom: calc(100% + 8px);
  left: 0;
  z-index: 120;
  width: 480px;
  max-width: calc(100vw - 40px);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--popover);
  box-shadow: 0 8px 24px color-mix(in srgb, var(--color-black) 18%, transparent);
  overflow: hidden;
}

.provider-columns {
  display: grid;
  grid-template-columns: 160px minmax(0, 1fr);
  max-height: 320px;
}

.column-providers,
.column-models {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.column-providers {
  border-right: 1px solid var(--border);
}

.column-header {
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 600;
  color: var(--muted-foreground);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.column-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 4px;
  min-height: 120px;
}

.provider-item,
.model-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 7px 10px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  font: inherit;
  font-size: 12px;
  color: var(--foreground);
  cursor: pointer;
  text-align: left;
}

.provider-item:hover,
.model-item:hover {
  background: var(--muted);
}

.provider-item--active,
.model-item--active {
  background: color-mix(in srgb, var(--primary) 10%, transparent);
  box-shadow: inset 2px 0 0 var(--primary);
}

.provider-item-name,
.model-item-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.provider-item-default {
  flex-shrink: 0;
  font-size: 10px;
  color: var(--muted-foreground);
  background: var(--muted);
  border-radius: 999px;
  padding: 1px 6px;
}

.model-item-check {
  color: var(--primary);
  font-size: 12px;
}

.manage-link {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px;
  border: none;
  border-top: 1px solid var(--border);
  background: var(--muted);
  color: var(--primary);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  flex-shrink: 0;
}

.manage-link:hover {
  color: var(--primary-hover);
}

.column-empty {
  padding: 16px 12px;
  text-align: center;
  font-size: 12px;
  color: var(--muted-foreground);
}
</style>
