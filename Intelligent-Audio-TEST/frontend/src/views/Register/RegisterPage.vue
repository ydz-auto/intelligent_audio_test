<template>
  <div class="register-page">
    <div class="register-card">
      <div class="register-header">
        <i class="fas fa-headset"></i>
        <h1>注册账号</h1>
        <p>加入智能语音测试系统</p>
      </div>

      <div v-if="registered" class="register-success">
        <i class="fas fa-check-circle success-icon"></i>
        <p class="success-text">注册成功，请前往登录</p>
        <button class="btn btn-primary" @click="goLogin">去登录</button>
      </div>

      <form v-else @submit.prevent="handleRegister">
        <div class="form-group">
          <label>用户名</label>
          <input
            v-model="form.username"
            type="text"
            placeholder="请输入用户名"
            required
            :disabled="loading"
          />
        </div>
        <div class="form-group">
          <label>密码</label>
          <input
            v-model="form.password"
            type="password"
            :placeholder="`请输入密码（至少 ${AUTH_PASSWORD_MIN_LENGTH} 位）`"
            required
            :minlength="AUTH_PASSWORD_MIN_LENGTH"
            :disabled="loading"
          />
        </div>
        <div class="form-group">
          <label>确认密码</label>
          <input
            v-model="form.confirmPassword"
            type="password"
            placeholder="请再次输入密码"
            required
            :disabled="loading"
          />
        </div>
        <div class="form-group">
          <label>邮箱</label>
          <input
            v-model="form.email"
            type="email"
            placeholder="请输入邮箱"
            required
            :disabled="loading"
          />
        </div>
        <p v-if="error" class="error-msg">{{ error }}</p>
        <button type="submit" class="register-btn" :disabled="loading">
          {{ loading ? '注册中...' : '注 册' }}
        </button>
        <p class="register-footer">
          已有账号？
          <router-link to="/login" class="register-link">去登录</router-link>
        </p>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../../store/authStore'
import { AUTH_PASSWORD_MIN_LENGTH } from '../../domain/constants/auth'

const router = useRouter()
const authStore = useAuthStore()

const form = reactive({
  username: '',
  password: '',
  confirmPassword: '',
  email: '',
})
const loading = ref(false)
const error = ref('')
const registered = ref(false)

async function handleRegister() {
  error.value = ''
  if (form.password !== form.confirmPassword) {
    error.value = '两次输入的密码不一致'
    return
  }
  if (!form.email.trim()) {
    error.value = '请输入邮箱'
    return
  }
  loading.value = true
  try {
    await authStore.register({
      username: form.username,
      password: form.password,
      email: form.email.trim(),
    })
    registered.value = true
  } catch (e: any) {
    error.value = e?.detail || e?.message || '注册失败'
  } finally {
    loading.value = false
  }
}

function goLogin() {
  router.push({ name: 'login' })
}
</script>

<style scoped>
.register-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: var(--muted);
}
.register-card {
  background: var(--card);
  padding: 40px;
  border-radius: var(--radius-lg);
  box-shadow: 0 2px 10px color-mix(in srgb, var(--color-black) 10%, transparent);
  width: 380px;
  border: 1px solid var(--border);
}
.register-header {
  text-align: center;
  margin-bottom: 30px;
}
.register-header i {
  font-size: 40px;
  color: var(--primary);
}
.register-header h1 {
  font-size: 20px;
  color: var(--foreground);
  margin-top: 10px;
}
.register-header p {
  font-size: 13px;
  color: var(--text-secondary);
  margin-top: 4px;
}
.form-group {
  margin-bottom: 20px;
}
.form-group label {
  display: block;
  margin-bottom: 5px;
  color: var(--text-secondary);
  font-size: 14px;
}
.form-group input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 14px;
  color: var(--foreground);
  background: var(--card);
}
.form-group input:focus {
  border-color: var(--ring);
  outline: none;
  box-shadow: 0 0 0 3px var(--accent);
}
.register-btn {
  width: 100%;
  padding: 12px;
  background: var(--primary);
  color: var(--primary-foreground);
  border: none;
  border-radius: var(--radius-sm);
  font-size: 16px;
  cursor: pointer;
}
.register-btn:hover {
  background: var(--primary-hover);
}
.register-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.error-msg {
  color: var(--destructive);
  text-align: center;
  margin-bottom: 15px;
  font-size: 14px;
}
.register-footer {
  text-align: center;
  margin-top: 16px;
  font-size: 13px;
  color: var(--text-secondary);
}
.register-link {
  color: var(--primary);
  text-decoration: none;
  font-weight: 600;
}
.register-success {
  text-align: center;
  padding: 20px 0;
}
.success-icon {
  font-size: 48px;
  color: var(--success);
  margin-bottom: 12px;
}
.success-text {
  font-size: 16px;
  font-weight: 600;
  color: var(--foreground);
  margin-bottom: 20px;
}
</style>
