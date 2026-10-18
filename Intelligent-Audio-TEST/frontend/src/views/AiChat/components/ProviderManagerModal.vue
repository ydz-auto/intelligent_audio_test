<template>
  <BasicModal
    :visible="visible"
    :width="'560px'"
    :max-width="'92vw'"
    :max-height="'86vh'"
    :title="PROVIDER_MANAGER_COPY.title"
    :closable="true"
    :show-footer="false"
    @close="handleClose"
    @cancel="handleClose"
  >
    <div class="provider-manager">
      <p class="pm-description">{{ PROVIDER_MANAGER_COPY.description }}</p>

      <!-- 供应商列表 -->
      <div v-if="!editingId" class="pm-list">
        <div class="pm-list-header">
          <span class="pm-list-count">共 {{ store.providers.length }} 个供应商</span>
          <button type="button" class="btn btn-sm btn-primary" @click="startAdd">
            <i class="fas fa-plus"></i> {{ PROVIDER_MANAGER_COPY.addProvider }}
          </button>
        </div>
        <div v-if="store.providers.length === 0" class="pm-empty">
          尚未配置任何 LLM 供应商。点击右上角「添加供应商」配置你的 AI 对话连接。
        </div>
        <div v-else class="pm-provider-list">
          <div v-for="provider in store.providers" :key="provider.id" class="pm-provider-row">
            <div class="pm-provider-info">
              <div class="pm-provider-name-line">
                <span class="pm-provider-name">{{ provider.name }}</span>
                <span v-if="provider.isDefault" class="pm-default-badge">{{ PROVIDER_MANAGER_COPY.default }}</span>
                <span class="pm-key-badge" :class="{ 'pm-key-badge--missing': !provider.apiKey }">
                  {{ provider.apiKey ? PROVIDER_MANAGER_COPY.keyConfigured : PROVIDER_MANAGER_COPY.keyMissing }}
                </span>
              </div>
              <div class="pm-provider-url">{{ provider.baseUrl }}</div>
              <div v-if="provider.models.length" class="pm-provider-models">
                {{ provider.models.join(' · ') }}
              </div>
            </div>
            <div class="pm-provider-actions">
              <button
                type="button"
                class="action-btn"
                :title="PROVIDER_MANAGER_COPY.setDefault"
                @click="store.setDefaultProvider(provider.id)"
              >
                <i class="fas fa-star"></i>
              </button>
              <button type="button" class="action-btn" :title="PROVIDER_MANAGER_COPY.edit" @click="startEdit(provider)">
                <i class="fas fa-pen"></i>
              </button>
              <button type="button" class="action-btn action-btn--danger" :title="PROVIDER_MANAGER_COPY.delete" @click="confirmDelete(provider)">
                <i class="fas fa-trash"></i>
              </button>
            </div>
          </div>
        </div>
        <p class="pm-footer-note">{{ PROVIDER_MANAGER_COPY.footerNote }}</p>
      </div>

      <!-- 添加 / 编辑表单 -->
      <div v-else class="pm-form">
        <div class="pm-form-field">
          <label class="pm-form-label">{{ PROVIDER_MANAGER_COPY.name }} <span class="pm-required">*</span></label>
          <input v-model="form.name" type="text" class="pm-input" placeholder="例如：OpenAI" />
        </div>
        <div class="pm-form-field">
          <label class="pm-form-label">{{ PROVIDER_MANAGER_COPY.baseUrl }} <span class="pm-required">*</span></label>
          <input v-model="form.baseUrl" type="text" class="pm-input" placeholder="https://api.openai.com/v1" />
        </div>
        <div class="pm-form-field">
          <label class="pm-form-label">{{ PROVIDER_MANAGER_COPY.apiKey }}</label>
          <div class="pm-key-input">
            <input v-model="form.apiKey" :type="showKey ? 'text' : 'password'" class="pm-input" placeholder="sk-..." />
            <button type="button" class="pm-key-toggle" :title="PROVIDER_MANAGER_COPY.showHide" @click="showKey = !showKey">
              <i :class="showKey ? 'fas fa-eye-slash' : 'fas fa-eye'"></i>
            </button>
          </div>
        </div>
        <div class="pm-form-field">
          <label class="pm-form-label">{{ PROVIDER_MANAGER_COPY.modelList }}</label>
          <div class="pm-models-list">
            <div v-for="(model, idx) in form.models" :key="idx" class="pm-model-row">
              <input v-model="form.models[idx]" type="text" class="pm-input" placeholder="模型 id，如 gpt-4o" />
              <button type="button" class="pm-model-remove" @click="form.models.splice(idx, 1)">
                <i class="fas fa-xmark"></i>
              </button>
            </div>
            <button type="button" class="btn btn-sm btn-secondary" @click="form.models.push('')">
              <i class="fas fa-plus"></i> 添加模型
            </button>
            <button type="button" class="btn btn-sm btn-text pm-fetch-models" :disabled="fetchingModels" @click="handleFetchModels">
              <i :class="fetchingModels ? 'fas fa-spinner fa-spin' : 'fas fa-wand-magic-sparkles'"></i>
              {{ PROVIDER_MANAGER_COPY.fetchModels }}
            </button>
          </div>
        </div>
        <div class="pm-form-actions">
          <button type="button" class="btn btn-sm btn-secondary" :disabled="testing" @click="handleTestConnection">
            <i :class="testing ? 'fas fa-spinner fa-spin' : 'fas fa-plug'"></i>
            {{ PROVIDER_MANAGER_COPY.testConnection }}
          </button>
          <span class="pm-form-spacer"></span>
          <button type="button" class="btn btn-sm btn-secondary" @click="cancelForm">{{ PROVIDER_MANAGER_COPY.cancel }}</button>
          <button type="button" class="btn btn-sm btn-primary" :disabled="!form.name.trim() || !form.baseUrl.trim()" @click="handleSave">
            {{ PROVIDER_MANAGER_COPY.save }}
          </button>
        </div>
      </div>
    </div>
  </BasicModal>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import BasicModal from '@/components/common/modal/BasicModal.vue'
import { useAiChatStore } from '@/store/aiChatStore'
import { useNotification } from '@/composables/modal/useNotification'
import { useModalControl } from '@/composables/modal/useModal'
import { MODAL_TYPES } from '@/composables/modal/constants'
import { llmProviderApi } from '@/infrastructure/api/llmProviderApi'
import { PROVIDER_MANAGER_COPY } from '@/domain/constants/aiChat'
import type { LlmProvider } from '@/domain/model/aiChat'

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{ (e: 'update:visible', value: boolean): void }>()

const store = useAiChatStore()
const notification = useNotification()
const modalControl = useModalControl()

const editingId = ref<string | null>(null)
const showKey = ref(false)
const testing = ref(false)
const fetchingModels = ref(false)

const form = reactive<{
  name: string
  baseUrl: string
  apiKey: string
  models: string[]
}>({
  name: '',
  baseUrl: '',
  apiKey: '',
  models: [],
})

function resetForm(): void {
  form.name = ''
  form.baseUrl = ''
  form.apiKey = ''
  form.models = []
  showKey.value = false
}

function handleClose(): void {
  emit('update:visible', false)
}

function startAdd(): void {
  resetForm()
  editingId.value = '__new__'
}

function startEdit(provider: LlmProvider): void {
  form.name = provider.name
  form.baseUrl = provider.baseUrl
  form.apiKey = provider.apiKey
  form.models = [...provider.models]
  editingId.value = provider.id
}

function cancelForm(): void {
  editingId.value = null
  resetForm()
}

function handleSave(): void {
  const name = form.name.trim()
  const baseUrl = form.baseUrl.trim()
  if (!name || !baseUrl) return
  const models = form.models.map((m) => m.trim()).filter(Boolean)
  if (editingId.value === '__new__') {
    store.addProvider({ name, baseUrl, apiKey: form.apiKey, models })
    notification.success('供应商已添加')
  } else if (editingId.value) {
    store.updateProvider(editingId.value, { name, baseUrl, apiKey: form.apiKey, models })
    notification.success('供应商已保存')
  }
  editingId.value = null
  resetForm()
}

async function handleTestConnection(): Promise<void> {
  const baseUrl = form.baseUrl.trim()
  if (!baseUrl) return
  testing.value = true
  try {
    const count = await store.testConnection({ baseUrl, apiKey: form.apiKey })
    notification.success(PROVIDER_MANAGER_COPY.connectionSuccess.replace('{n}', String(count)))
  } catch (err) {
    notification.error(
      PROVIDER_MANAGER_COPY.connectionFailed,
      err instanceof Error ? err.message : undefined
    )
  } finally {
    testing.value = false
  }
}

async function handleFetchModels(): Promise<void> {
  const baseUrl = form.baseUrl.trim()
  if (!baseUrl) return
  fetchingModels.value = true
  try {
    const models = await llmProviderApi.fetchProviderModels(baseUrl, form.apiKey)
    form.models = models
    notification.success(PROVIDER_MANAGER_COPY.connectionSuccess.replace('{n}', String(models.length)))
  } catch (err) {
    notification.error(
      PROVIDER_MANAGER_COPY.connectionFailed,
      err instanceof Error ? err.message : undefined
    )
  } finally {
    fetchingModels.value = false
  }
}

async function confirmDelete(provider: LlmProvider): Promise<void> {
  try {
    await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: PROVIDER_MANAGER_COPY.deleteConfirmTitle,
      content: PROVIDER_MANAGER_COPY.deleteConfirmContent,
      confirmText: PROVIDER_MANAGER_COPY.delete,
      cancelText: PROVIDER_MANAGER_COPY.cancel,
      danger: true,
    })
    store.removeProvider(provider.id)
    notification.success('供应商已删除')
  } catch {
    // 用户取消删除
  }
}

watch(
  () => props.visible,
  (v) => {
    if (!v) {
      editingId.value = null
      resetForm()
    }
  }
)
</script>

<style scoped>
.provider-manager {
  min-height: 240px;
}

.pm-description {
  margin: 0 0 16px;
  font-size: 13px;
  color: var(--muted-foreground);
  line-height: 1.6;
}

.pm-list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.pm-list-count {
  font-size: 12px;
  color: var(--muted-foreground);
}

.pm-empty {
  padding: 32px 16px;
  text-align: center;
  font-size: 13px;
  color: var(--muted-foreground);
  border: 1px dashed var(--border);
  border-radius: var(--radius);
}

.pm-provider-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 300px;
  overflow-y: auto;
}

.pm-provider-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--card);
}

.pm-provider-info {
  flex: 1;
  min-width: 0;
}

.pm-provider-name-line {
  display: flex;
  align-items: center;
  gap: 8px;
}

.pm-provider-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--foreground);
}

.pm-default-badge {
  font-size: 10px;
  color: var(--secondary);
  background: var(--secondary-light, color-mix(in srgb, var(--secondary) 12%, transparent));
  border-radius: var(--radius-full);
  padding: 1px 6px;
}

.pm-key-badge {
  font-size: 10px;
  color: var(--success-dark, var(--foreground));
  background: var(--success-light, color-mix(in srgb, var(--success) 15%, transparent));
  border-radius: var(--radius-full);
  padding: 1px 6px;
}

.pm-key-badge--missing {
  color: var(--warning-dark, var(--foreground));
  background: var(--warning-light, color-mix(in srgb, var(--warning) 15%, transparent));
}

.pm-provider-url {
  margin-top: 4px;
  font-size: 11px;
  font-family: var(--font-mono, monospace);
  color: var(--muted-foreground);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pm-provider-models {
  margin-top: 4px;
  font-size: 11px;
  color: var(--muted-foreground);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pm-provider-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.action-btn {
  width: 28px;
  height: 28px;
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

.action-btn:hover {
  background: var(--muted);
  color: var(--foreground);
}

.action-btn--danger:hover {
  color: var(--destructive);
}

.pm-footer-note {
  margin: 16px 0 0;
  font-size: 12px;
  color: var(--warning-dark, var(--muted-foreground));
  line-height: 1.5;
}

/* ===== 表单 ===== */
.pm-form-field {
  margin-bottom: 14px;
}

.pm-form-label {
  display: block;
  margin-bottom: 6px;
  font-size: 13px;
  font-weight: 500;
  color: var(--foreground);
}

.pm-required {
  color: var(--destructive);
}

.pm-input {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--input);
  border-radius: var(--radius-sm);
  font: inherit;
  font-size: 13px;
  color: var(--foreground);
  background: var(--card);
  box-sizing: border-box;
}

.pm-input:focus {
  outline: none;
  border-color: var(--ring);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--ring) 20%, transparent);
}

.pm-key-input {
  display: flex;
  gap: 6px;
}

.pm-key-toggle {
  flex-shrink: 0;
  width: 36px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--muted);
  color: var(--muted-foreground);
  cursor: pointer;
}

.pm-key-toggle:hover {
  color: var(--foreground);
}

.pm-models-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.pm-model-row {
  display: flex;
  gap: 6px;
  align-items: center;
}

.pm-model-remove {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  color: var(--muted-foreground);
  cursor: pointer;
}

.pm-model-remove:hover {
  color: var(--destructive);
}

.pm-fetch-models {
  align-self: flex-start;
}

.pm-form-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--border);
}

.pm-form-spacer {
  flex: 1;
}
</style>
