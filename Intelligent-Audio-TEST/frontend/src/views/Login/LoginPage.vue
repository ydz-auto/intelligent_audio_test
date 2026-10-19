<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-header">
        <i class="fas fa-headset"></i>
        <h1>智能语音测试系统</h1>
      </div>

      <!-- 登录表单 -->
      <form @submit.prevent="handleLogin">
        <div class="form-group">
          <label>用户名 / 邮箱</label>
          <input
            v-model="form.username"
            type="text"
            placeholder="请输入用户名或邮箱"
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
        <p class="login-footer">
          没有账号？
          <router-link to="/register" class="login-link">去注册</router-link>
        </p>
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
import { AuthErrorCode, AuthMode, getEffectiveAuthMode } from '../../domain/enums'
import type { OAuthProvider } from '../../domain/model/auth'
import { sanitizeRedirect } from '../../utils/redirect'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const form = reactive({ username: '', password: '' })
const loading = ref(false)
const error = ref('')
const oauthProviders = ref<OAuthProvider[]>([])

async function handleLogin() {
  error.value = ''
  loading.value = true
  try {
    await authStore.login(form.username, form.password)
    const redirect = sanitizeRedirect(route.query.redirect as string | undefined)
    router.push(redirect)
  } catch (e: any) {
    // INT-188：加密校验失败 ≠ 凭证错误——引导刷新重试，不误导为密码错误
    if (e?.code === AuthErrorCode.ENCRYPTION_INVALID) {
      error.value = e?.detail || '登录加密校验失败，请刷新页面重试'
    } else {
      error.value = e?.detail || e?.message || '登录失败'
    }
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
      const redirect = sanitizeRedirect(route.query.redirect as string | undefined)
      router.push(redirect)
      return
    } catch (e: any) {
      error.value = e?.detail || e?.message || 'OAuth 登录失败'
    } finally {
      loading.value = false
    }
  }
  // 已启用提供方列表（公开端点；未配置时隐藏按钮区）
  // INT-900：AUTH_MODE=off 时 OAuth 登录无意义且后端该端点 500，跳过请求避免原始错误串；
  // 其余模式请求失败时友好降级（隐藏按钮区，不直出错误）
  if (getEffectiveAuthMode() !== AuthMode.OFF) {
    try {
      oauthProviders.value = await authPort.listPublicOAuthProviders()
    } catch {
      oauthProviders.value = []
    }
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
  background: var(--card);
  padding: 40px;
  border-radius: var(--radius-lg);
  box-shadow: 0 2px 10px color-mix(in srgb, var(--color-black) 10%, transparent);
  width: 360px;
  border: 1px solid var(--border);
}
.login-header {
  text-align: center;
  margin-bottom: 30px;
}
.login-header i {
  font-size: 40px;
  color: var(--primary);
}
.login-header h1 {
  font-size: 20px;
  color: var(--foreground);
  margin-top: 10px;
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
.login-btn {
  width: 100%;
  padding: 12px;
  background: var(--primary);
  color: var(--primary-foreground);
  border: none;
  border-radius: var(--radius-sm);
  font-size: 16px;
  cursor: pointer;
}
.login-btn:hover {
  background: var(--primary-hover);
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
.login-footer {
  text-align: center;
  margin-top: 16px;
  font-size: 13px;
  color: var(--text-secondary);
}
.login-link {
  color: var(--primary);
  text-decoration: none;
  font-weight: 600;
}
.oauth-section {
  margin-top: 24px;
}
.oauth-divider {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  color: var(--text-tertiary);
  font-size: 12px;
}
.oauth-divider::before,
.oauth-divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--border);
}
.oauth-divider span {
  padding: 0 10px;
}
.oauth-btn {
  width: 100%;
  padding: 10px;
  margin-bottom: 8px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 14px;
  cursor: pointer;
}
.oauth-btn:hover {
  border-color: var(--ring);
  color: var(--primary);
}
.oauth-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
