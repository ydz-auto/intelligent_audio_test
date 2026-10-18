<template>
  <form class="change-password-form" novalidate @submit.prevent="handleSubmit">
    <p class="modal-desc">为账号 {{ username }} 更新登录密码</p>

    <div class="form-group">
      <label for="profile-current-password">当前密码 <span class="required">*</span></label>
      <input
        id="profile-current-password"
        v-model="form.currentPassword"
        type="password"
        placeholder="请输入当前密码"
        autocomplete="current-password"
      />
      <p v-if="errors.currentPassword" class="error-text">{{ errors.currentPassword }}</p>
    </div>

    <div class="form-group">
      <label for="profile-new-password">新密码 <span class="required">*</span></label>
      <input
        id="profile-new-password"
        v-model="form.newPassword"
        type="password"
        placeholder="请输入新密码（至少 6 位）"
        autocomplete="new-password"
      />
      <p v-if="errors.newPassword" class="error-text">{{ errors.newPassword }}</p>
    </div>

    <div class="form-group">
      <label for="profile-confirm-password">确认新密码 <span class="required">*</span></label>
      <input
        id="profile-confirm-password"
        v-model="form.confirmPassword"
        type="password"
        placeholder="请再次输入新密码"
        autocomplete="new-password"
      />
      <p v-if="errors.confirmPassword" class="error-text">{{ errors.confirmPassword }}</p>
    </div>

    <p v-if="errorMessage" class="error-message">{{ errorMessage }}</p>

    <div class="form-actions">
      <button type="button" class="btn btn-secondary" @click="handleCancel">取消</button>
      <button type="submit" class="btn btn-primary" :disabled="saving">
        {{ saving ? '保存中…' : '保存' }}
      </button>
    </div>
  </form>
</template>

<script setup lang="ts">
/**
 * 修改密码对话框壳（13_个人中心 §3.5.1 / §6，对位 newAPI change-password-dialog.tsx）：
 * 三字段（当前/新/确认），新密码下限 6 位对齐平台 AUTH_PASSWORD_MIN_LENGTH（默认 6）。
 * ⚠️ 自助改密端点 F2 待 FEAT（总表 §3.3 F2）——本壳不造数据兜底、不出现假成功：
 * 提交走 passwordApi 桩，调用即抛「待后端立项」错误提示。
 */
import { computed, reactive, ref } from 'vue'
import { profilePort } from '@/composables/profile/profilePort'

const props = defineProps<{
  username?: string
}>()

const emit = defineEmits<{
  (e: 'confirm', data: Record<string, unknown>): void
  (e: 'cancel'): void
}>()

const form = reactive({
  currentPassword: '',
  newPassword: '',
  confirmPassword: '',
})
const errors = reactive<Record<string, string>>({})
const errorMessage = ref('')
const saving = ref(false)

const isFormValid = computed(() => {
  const current = form.currentPassword.trim()
  const next = form.newPassword.trim()
  const confirm = form.confirmPassword.trim()
  return current.length > 0 && next.length >= 6 && confirm.length > 0 && next === confirm
})

function validate(): boolean {
  const nextErrors: Record<string, string> = {}
  if (!form.currentPassword.trim()) nextErrors.currentPassword = '请输入当前密码'
  if (!form.newPassword.trim()) {
    nextErrors.newPassword = '请输入新密码'
  } else if (form.newPassword.length < 6) {
    nextErrors.newPassword = '新密码长度不能少于 6 位'
  } else if (form.newPassword === form.currentPassword) {
    nextErrors.newPassword = '新密码不能与当前密码相同'
  }
  if (!form.confirmPassword.trim()) {
    nextErrors.confirmPassword = '请再次输入新密码'
  } else if (form.confirmPassword !== form.newPassword) {
    nextErrors.confirmPassword = '两次输入的密码不一致'
  }
  Object.assign(errors, nextErrors)
  return Object.keys(nextErrors).length === 0
}

async function handleSubmit() {
  errorMessage.value = ''
  if (!validate() || saving.value) return
  saving.value = true
  try {
    await profilePort.changeMyPassword({
      currentPassword: form.currentPassword,
      newPassword: form.newPassword,
    })
    // 桩未落地前不会走到这里（changeMyPassword 抛「待后端立项」）
    emit('confirm', { ...form })
  } catch (e: any) {
    errorMessage.value = e?.message || '密码修改失败，请重试'
  } finally {
    saving.value = false
  }
}

function handleCancel() {
  emit('cancel')
}
</script>

<style scoped>
.change-password-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.modal-desc {
  margin: 0;
  font-size: 13px;
  color: var(--muted-foreground);
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

.form-group input {
  width: 100%;
  padding: 10px 14px;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 14px;
  box-sizing: border-box;
  background: var(--background);
  color: var(--foreground);
  transition: border-color 0.2s, box-shadow 0.2s;
}

.form-group input:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--ring) 15%, transparent);
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
  background: var(--destructive-light, rgba(245, 34, 45, 0.1));
  border-radius: 6px;
  padding: 8px 10px;
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
  border-radius: 6px;
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
