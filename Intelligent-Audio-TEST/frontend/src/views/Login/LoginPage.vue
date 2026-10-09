<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-header">
        <i class="fas fa-headset"></i>
        <h1>智能语音测试系统</h1>
      </div>

      <!-- 登录/注册双 Tab（INT-51 自助注册） -->
      <div class="tab-bar">
        <button
          type="button"
          class="tab-btn"
          :class="{ active: activeTab === 'login' }"
          @click="switchTab('login')"
        >登 录</button>
        <button
          type="button"
          class="tab-btn"
          :class="{ active: activeTab === 'register' }"
          @click="switchTab('register')"
        >注 册</button>
      </div>

      <!-- 登录表单 -->
      <form v-if="activeTab === 'login'" @submit.prevent="handleLogin">
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
            placeholder="请输入密码"
            required
            :disabled="loading"
          />
        </div>
        <p v-if="error" class="error-msg">{{ error }}</p>
        <button type="submit" class="login-btn" :disabled="loading">
          {{ loading ? '登录中...' : '登 录' }}
        </button>
      </form>

      <!-- 注册表单 -->
      <form v-else @submit.prevent="handleRegister">
        <div class="form-group">
          <label>用户名</label>
          <input
            v-model="registerForm.username"
            type="text"
            placeholder="请输入用户名"
            required
            :disabled="loading"
          />
        </div>
        <div class="form-group">
          <label>密码</label>
          <input
            v-model="registerForm.password"
            type="password"
            placeholder="请输入密码（至少 6 位）"
            required
            minlength="6"
            :disabled="loading"
          />
        </div>
        <div class="form-group">
          <label>确认密码</label>
          <input
            v-model="registerForm.confirmPassword"
            type="password"
            placeholder="请再次输入密码"
            required
            :disabled="loading"
          />
        </div>
        <div class="form-group">
          <label>邮箱（可选）</label>
          <input
            v-model="registerForm.email"
            type="email"
            placeholder="请输入邮箱"
            :disabled="loading"
          />
        </div>
        <p v-if="error" class="error-msg">{{ error }}</p>
        <button type="submit" class="login-btn" :disabled="loading">
          {{ loading ? '注册中...' : '注 册' }}
        </button>
      </form>

      <!-- OAuth 提供方动态按钮（管理端配置后自动渲染） -->
      <div v-if="oauthProviders.length" class="oauth-section">
        <div class="oauth-divider"><span>第三方登录</span></div>
        <button
          v-for="p in oauthProviders"
          :key="p.slug"
          type="button"
          class="oauth-btn"
          :disabled="loading"
          @click="handleOAuth(p.slug)"
        >
          <i :class="p.icon || 'fas fa-sign-in-alt'"></i>
          {{ p.name }} 登录
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '../../store/authStore'
import { authPort } from '../../composables/auth/authPort'
import type { OAuthProvider } from '../../domain/model/auth'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const activeTab = ref<'login' | 'register'>('login')
const form = reactive({ username: '', password: '' })
const registerForm = reactive({
  username: '',
  password: '',
  confirmPassword: '',
  email: '',
})
const loading = ref(false)
const error = ref('')
const oauthProviders = ref<OAuthProvider[]>([])

function switchTab(tab: 'login' | 'register') {
  activeTab.value = tab
  error.value = ''
}

async function handleLogin() {
  error.value = ''
  loading.value = true
  try {
    // 走 Application 层 Port（authStore.login），视图不感知 infrastructure
    await authStore.login(form.username, form.password)
    const redirect = (route.query.redirect as string) || '/'
    router.push(redirect)
  } catch (e: any) {
    // 后端 401 返回 {detail: "..."}，client.ts 构造的 error 含 detail 字段
    error.value = e?.detail || e?.message || '登录失败'
  } finally {
    loading.value = false
  }
}

async function handleRegister() {
  error.value = ''
  if (registerForm.password !== registerForm.confirmPassword) {
    error.value = '两次输入的密码不一致'
    return
  }
  loading.value = true
  try {
    await authStore.register({
      username: registerForm.username,
      password: registerForm.password,
      email: registerForm.email || undefined,
    })
    // 注册成功：切回登录 Tab，预填用户名引导登录（注册→登录全流程）
    form.username = registerForm.username
    form.password = ''
    registerForm.password = ''
    registerForm.confirmPassword = ''
    activeTab.value = 'login'
    error.value = ''
  } catch (e: any) {
    // 注册开关关闭 → 后端 403；重名等 → 400/409
    error.value = e?.detail || e?.message || '注册失败'
  } finally {
    loading.value = false
  }
}

function handleOAuth(slug: string) {
  // 整页跳转到后端授权入口（302 → 提供方授权页 → 回调 → 携 token 回本页）
  window.location.href = authPort.getOAuthAuthorizeUrl(slug)
}

onMounted(async () => {
  // OAuth 回调携带 token：落库并拉取用户信息
  const oauthToken = route.query.oauth_token as string
  const oauthError = route.query.oauth_error as string
  if (oauthError) {
    error.value = oauthError
  }
  if (oauthToken) {
    loading.value = true
    try {
      await authStore.loginWithToken(oauthToken)
      const redirect = (route.query.redirect as string) || '/'
      router.push(redirect)
      return
    } catch (e: any) {
      error.value = e?.detail || e?.message || 'OAuth 登录失败'
    } finally {
      loading.value = false
    }
  }
  // 已启用提供方列表（公开端点；未配置时隐藏按钮区）
  try {
    oauthProviders.value = await authPort.listPublicOAuthProviders()
  } catch {
    oauthProviders.value = []
  }
})
</script>

<style scoped>
.login-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: var(--muted);
}
.login-card {
  background: white;
  padding: 40px;
  border-radius: 8px;
  box-shadow: 0 2px 10px color-mix(in srgb, var(--color-black) 10%, transparent);
  width: 360px;
}
.login-header {
  text-align: center;
  margin-bottom: 30px;
}
.login-header i {
  font-size: 40px;
  color: var(--secondary);
}
.login-header h1 {
  font-size: 20px;
  color: var(--foreground);
  margin-top: 10px;
}
.tab-bar {
  display: flex;
  margin-bottom: 20px;
  border-bottom: 1px solid var(--color-gray-300);
}
.tab-btn {
  flex: 1;
  padding: 10px 0;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  font-size: 15px;
  color: var(--color-gray-500);
  cursor: pointer;
}
.tab-btn.active {
  color: var(--secondary);
  border-bottom-color: var(--secondary);
  font-weight: 600;
}
.form-group {
  margin-bottom: 20px;
}
.form-group label {
  display: block;
  margin-bottom: 5px;
  color: var(--color-gray-500);
  font-size: 14px;
}
.form-group input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--color-gray-300);
  border-radius: 4px;
  font-size: 14px;
}
.form-group input:focus {
  border-color: var(--secondary);
  outline: none;
}
.login-btn {
  width: 100%;
  padding: 12px;
  background: var(--secondary);
  color: white;
  border: none;
  border-radius: 4px;
  font-size: 16px;
  cursor: pointer;
}
.login-btn:hover {
  background: var(--color-blue-600);
}
.login-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.error-msg {
  color: var(--destructive);
  text-align: center;
  margin-bottom: 15px;
  font-size: 14px;
}
.oauth-section {
  margin-top: 24px;
}
.oauth-divider {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  color: var(--color-gray-400);
  font-size: 12px;
}
.oauth-divider::before,
.oauth-divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--color-gray-300);
}
.oauth-divider span {
  padding: 0 10px;
}
.oauth-btn {
  width: 100%;
  padding: 10px;
  margin-bottom: 8px;
  background: white;
  border: 1px solid var(--color-gray-300);
  border-radius: 4px;
  font-size: 14px;
  cursor: pointer;
}
.oauth-btn:hover {
  border-color: var(--secondary);
  color: var(--secondary);
}
.oauth-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
