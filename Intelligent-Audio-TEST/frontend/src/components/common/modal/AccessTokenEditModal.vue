<template>
  <div class="access-token-modal">
    <form class="access-token-form" novalidate @submit.prevent="handleSubmit">
      <p class="modal-desc">
        编辑令牌「{{ token?.name }}」——可重命名 / 换权限范围 / 改有效期 / 启停。
        完整令牌不会在此展示（仅在创建时显示一次）。
      </p>

      <div class="form-group">
        <label for="at-edit-name">令牌名称 <span class="required">*</span></label>
        <input
          id="at-edit-name"
          v-model="form.name"
          type="text"
          placeholder="如：CI 集成 / 外部 Agent 只读"
          maxlength="64"
        />
        <p v-if="errors.name" class="error-text">{{ errors.name }}</p>
      </div>

      <div class="form-group">
        <label>状态</label>
        <div class="status-row">
          <button type="button" class="status-switch" :class="form.status" @click="toggleStatus">
            <span class="status-dot"></span>
            {{ form.status === 'enabled' ? '启用' : '停用' }}
          </button>
          <span class="field-hint inline-hint">
            {{ form.status === 'enabled' ? '令牌可被 skill / MCP 使用' : '停用后该令牌立即失效' }}
          </span>
        </div>
      </div>

      <div class="form-group">
        <label>权限范围（scopes）</label>
        <p class="field-hint">勾选该令牌可调用的业务能力；不勾选任何权限 = 继承账号全部权限</p>
        <div class="scope-groups">
          <div v-for="group in ACCESS_TOKEN_SCOPE_GROUPS" :key="group.module" class="scope-group">
            <div class="scope-group-head">
              <span class="scope-group-title">{{ group.label }}</span>
              <button type="button" class="scope-group-toggle" @click="toggleGroup(group)">
                {{ isGroupAllSelected(group) ? '清空' : '全选' }}
              </button>
            </div>
            <div class="scope-grid">
              <label
                v-for="item in group.scopes"
                :key="item.code"
                class="scope-option"
                :class="{ checked: form.scopes.includes(item.code) }"
              >
                <input
                  type="checkbox"
                  :value="item.code"
                  :checked="form.scopes.includes(item.code)"
                  @change="toggleScope(item.code)"
                />
                <span class="scope-code">{{ item.code }}</span>
                <span class="scope-label">{{ item.label }}</span>
              </label>
            </div>
          </div>
        </div>
      </div>

      <div class="form-group">
        <label for="at-edit-expires">有效期至</label>
        <select id="at-edit-expires" v-model="form.expiresPreset" class="form-select">
          <option value="never">永不过期</option>
          <option value="7d">7 天后</option>
          <option value="30d">30 天后</option>
          <option value="90d">90 天后</option>
          <option value="custom">自定义…</option>
        </select>
        <input
          v-if="form.expiresPreset === 'custom'"
          v-model="form.customExpires"
          type="datetime-local"
          class="custom-expires"
          :min="minCustomExpires"
        />
        <p class="field-hint">到期后令牌自动失效；永不过期令牌请在不再使用时手动停用或删除</p>
      </div>

      <p v-if="errorMessage" class="error-message">{{ errorMessage }}</p>

      <div class="form-actions">
        <button type="button" class="btn btn-secondary" @click="handleCancel">取消</button>
        <button type="submit" class="btn btn-primary" :disabled="saving">
          {{ saving ? '保存中…' : '保存' }}
        </button>
      </div>
    </form>
  </div>
</template>

<script setup lang="ts">
import '../../../assets/styles/test-common.css'
import '../../../assets/styles/components/common.css'
import '../../../assets/styles/components/button.css'
import '../../../assets/styles/components/form.css'
import '../../../assets/styles/components/modal.css'
import '../../../assets/styles/components/table.css'
import '../../../assets/styles/components/tag.css'
import '../../../assets/styles/components/log.css'

/**
 * Access Token 编辑对话框（INT-1155，PATCH /api/v1/auth/access-tokens/{id}）：
 * 重命名 / 换 scopes / 改 expires / 启停。预填当前值，保存成功后 emit confirm，
 * 调用方刷新列表。完整明文不展示（仅在创建时显示一次）。
 */
import { computed, reactive, ref } from 'vue'
import { profilePort } from '@/composables/profile/profilePort'
import { ACCESS_TOKEN_SCOPE_GROUPS, type AccessTokenScopeGroup } from '@/composables/profile/accessTokenScopes'
import type { AccessToken } from '@/domain/model/accessToken'

const props = defineProps<{
  token?: AccessToken
}>()

const emit = defineEmits<{
  (e: 'confirm', data: AccessToken): void
  (e: 'cancel'): void
}>()

type ExpiresPreset = 'never' | '7d' | '30d' | '90d' | 'custom'

/** ISO 时间 → datetime-local 值（本地时区） */
function toDatetimeLocal(value: string): string {
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return ''
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset())
  return d.toISOString().slice(0, 16)
}

const form = reactive({
  name: props.token?.name ?? '',
  scopes: [...(props.token?.scopes ?? [])],
  status: props.token?.status ?? 'enabled',
  expiresPreset: (props.token?.expiresAt ? 'custom' : 'never') as ExpiresPreset,
  customExpires: props.token?.expiresAt ? toDatetimeLocal(props.token.expiresAt) : '',
})
const errors = reactive<Record<string, string>>({})
const errorMessage = ref('')
const saving = ref(false)

const minCustomExpires = computed(() => {
  const d = new Date()
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset())
  return d.toISOString().slice(0, 16)
})

/** 提交载荷 expires_at：null = 永不过期（后端 0 语义） */
const expiresAt = computed<string | null>(() => {
  if (form.expiresPreset === 'never') return null
  if (form.expiresPreset === 'custom') {
    return form.customExpires ? new Date(form.customExpires).toISOString() : null
  }
  const days = form.expiresPreset === '7d' ? 7 : form.expiresPreset === '30d' ? 30 : 90
  return new Date(Date.now() + days * 24 * 60 * 60 * 1000).toISOString()
})

function toggleStatus() {
  form.status = form.status === 'enabled' ? 'disabled' : 'enabled'
}

function toggleScope(code: string) {
  form.scopes = form.scopes.includes(code)
    ? form.scopes.filter((c) => c !== code)
    : [...form.scopes, code]
}

function isGroupAllSelected(group: AccessTokenScopeGroup): boolean {
  return group.scopes.every((s) => form.scopes.includes(s.code))
}

function toggleGroup(group: AccessTokenScopeGroup) {
  const codes = group.scopes.map((s) => s.code)
  form.scopes = isGroupAllSelected(group)
    ? form.scopes.filter((c) => !codes.includes(c))
    : [...new Set([...form.scopes, ...codes])]
}

async function handleSubmit() {
  errorMessage.value = ''
  if (!form.name.trim()) {
    errors.name = '请输入令牌名称'
    return
  }
  if (form.expiresPreset === 'custom' && !form.customExpires) {
    errorMessage.value = '请选择自定义过期时间'
    return
  }
  if (saving.value) return
  saving.value = true
  try {
    const updated = await profilePort.updateAccessToken(props.token!.id, {
      name: form.name.trim(),
      scopes: form.scopes,
      expiresAt: expiresAt.value,
      status: form.status,
    })
    emit('confirm', updated)
  } catch (e: any) {
    errorMessage.value = e?.detail || e?.message || '保存失败，请重试'
  } finally {
    saving.value = false
  }
}

function handleCancel() {
  emit('cancel')
}
</script>

<style scoped>
.access-token-modal {
  display: flex;
  flex-direction: column;
}

.access-token-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.modal-desc {
  margin: 0;
  font-size: 13px;
  color: var(--muted-foreground);
  line-height: 1.6;
}

.form-group {
  position: relative;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  font-size: 14px;
  color: var(--foreground);
}

.required {
  color: var(--destructive);
}

.form-group input[type='text'],
.form-group select,
.custom-expires {
  width: 100%;
  padding: 10px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-control, 8px);
  font-size: 14px;
  box-sizing: border-box;
  background: var(--background);
  color: var(--foreground);
  transition: border-color 0.2s, box-shadow 0.2s;
}

.custom-expires {
  margin-top: 8px;
}

.form-group input:focus,
.form-group select:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--ring) 15%, transparent);
}

.field-hint {
  margin: -4px 0 10px;
  font-size: 12px;
  color: var(--muted-foreground);
}

.inline-hint {
  margin: 0;
}

.error-text {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--destructive);
}

.error-message {
  margin: 0;
  font-size: 13px;
  color: var(--destructive);
  background: var(--destructive-light);
  border-radius: var(--radius-control, 8px);
  padding: 8px 10px;
}

/* ===== 状态切换 ===== */
.status-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-switch {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  border-radius: var(--radius-pill, 999px);
  border: 1px solid var(--border);
  background: var(--card);
  color: var(--foreground);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.status-switch.enabled {
  border-color: var(--success);
  color: var(--success);
  background: var(--success-light);
}

.status-switch.disabled {
  border-color: var(--muted-foreground);
  color: var(--muted-foreground);
  background: var(--muted);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
}

/* ===== scopes 勾选目录 ===== */
.scope-groups {
  display: grid;
  gap: 12px;
  max-height: 320px;
  overflow-y: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius-control, 8px);
  padding: 12px;
}

.scope-group {
  display: grid;
  gap: 8px;
}

.scope-group-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.scope-group-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--foreground);
}

.scope-group-toggle {
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  font-size: 12px;
  color: var(--secondary);
}

.scope-group-toggle:hover {
  text-decoration: underline;
}

.scope-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 6px;
}

.scope-option {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-control, 8px);
  background: var(--card);
  cursor: pointer;
  font-size: 12px;
  color: var(--foreground);
  transition: border-color 0.2s, background 0.2s;
}

.scope-option:hover {
  border-color: var(--secondary);
}

.scope-option.checked {
  border-color: var(--secondary);
  background: var(--secondary-light);
}

.scope-option input {
  accent-color: var(--primary);
}

.scope-code {
  font-family: var(--font-mono, monospace);
  font-size: 11px;
  color: var(--foreground);
  white-space: nowrap;
}

.scope-label {
  color: var(--muted-foreground);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 8px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}

.btn {
  padding: 8px 18px;
  border-radius: var(--radius-control, 8px);
  font-size: 14px;
  cursor: pointer;
  border: none;
  transition: all 0.2s;
  font-weight: 500;
}

.btn-primary {
  background: var(--primary);
  color: var(--primary-foreground);
}

.btn-primary:hover:not(:disabled) {
  background: var(--primary-hover);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  background: var(--gray-light);
  color: var(--foreground);
  border: 1px solid var(--border);
}

.btn-secondary:hover {
  background: var(--muted);
}
</style>
