<template>
  <div class="account-settings">
    <div class="page-header">
      <h2 class="page-title">
        <i class="fas fa-user-circle"></i>
        账号设置
      </h2>
      <p class="page-description">管理当前账号信息与第三方账号绑定</p>
    </div>

    <p v-if="error" class="error-msg">{{ error }}</p>
    <p v-if="notice" class="success-msg">{{ notice }}</p>

    <div class="section-card">
      <h3>账号信息</h3>
      <div class="user-info">
        <div class="info-row">
          <span class="info-label">用户名</span>
          <span>{{ authStore.username }}</span>
        </div>
        <div class="info-row" v-if="authStore.roleName">
          <span class="info-label">角色</span>
          <span>{{ authStore.roleName }}</span>
        </div>
      </div>
    </div>

    <div class="section-card">
      <h3>第三方账号绑定</h3>
      <p class="section-hint">绑定后可使用对应第三方账号直接登录本账号</p>
      <table class="binding-table">
        <thead>
          <tr>
            <th>提供方</th>
            <th>第三方账号 ID</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!bindings.length">
            <td colspan="3" class="empty-row">暂无绑定，从下方列表添加</td>
          </tr>
          <tr v-for="b in bindings" :key="b.providerId">
            <td><i v-if="b.providerIcon" :class="b.providerIcon"></i> {{ b.providerName }}</td>
            <td><code>{{ b.providerUserId }}</code></td>
            <td>
              <button class="btn btn-sm btn-danger" :disabled="unbinding" @click="unbind(b)">
                解绑
              </button>
            </td>
          </tr>
        </tbody>
      </table>

      <div v-if="bindableProviders.length" class="bind-section">
        <h4>添加绑定</h4>
        <div class="bind-list">
          <button
            v-for="p in bindableProviders"
            :key="p.slug"
            type="button"
            class="bind-btn"
            :disabled="binding"
            @click="startBind(p.slug)"
          >
            <i :class="p.icon || 'fas fa-link'"></i>
            绑定 {{ p.name }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../../store/authStore'
import { authPort } from '../../composables/auth/authPort'
import type { OAuthBinding, OAuthProvider } from '../../domain/model/auth'
import { useModalControl } from '../../composables/modal/useModal'
import { MODAL_TYPES } from '../../composables/modal/constants'

const authStore = useAuthStore()
const route = useRoute()
const router = useRouter()
const modalControl = useModalControl()

const bindings = ref<OAuthBinding[]>([])
const providers = ref<OAuthProvider[]>([])
const error = ref('')
const notice = ref('')
const loading = ref(false)
const binding = ref(false)
const unbinding = ref(false)

// 已绑定的提供方不再重复给出绑定入口
const bindableProviders = computed(() => {
  const boundSlugs = new Set(bindings.value.map(b => b.providerSlug))
  return providers.value.filter(p => !boundSlugs.has(p.slug))
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    bindings.value = await authPort.listOAuthBindings()
    providers.value = await authPort.listPublicOAuthProviders()
  } catch (e: any) {
    error.value = e?.detail || e?.message || '加载绑定信息失败'
  } finally {
    loading.value = false
  }
}

function startBind(slug: string) {
  // 整页跳转：授权 → intent=bind 回调 → 携 bind_ticket 回本页
  window.location.href = authPort.getOAuthAuthorizeUrl(slug, 'bind')
}

async function completeBind(ticket: string) {
  binding.value = true
  error.value = ''
  try {
    await authPort.completeOAuthBinding(ticket)
    notice.value = '绑定成功'
    await load()
  } catch (e: any) {
    error.value = e?.detail || e?.message || '绑定失败'
  } finally {
    binding.value = false
  }
}

async function unbind(b: OAuthBinding) {
  // INT-286：解绑改 BASIC_CONFIRM（danger）模态，替换原生 window.confirm
  try {
    await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '解绑第三方账号',
      content: `确认解绑「${b.providerName}」？解绑后将无法使用该第三方账号登录。`,
      confirmText: '解绑',
      cancelText: '取消',
      danger: true,
    })
  } catch {
    return // 用户取消
  }
  unbinding.value = true
  error.value = ''
  try {
    await authPort.unbindOAuthProvider(b.providerId)
    notice.value = '解绑成功'
    await load()
  } catch (e: any) {
    error.value = e?.detail || e?.message || '解绑失败'
  } finally {
    unbinding.value = false
  }
}

onMounted(async () => {
  // intent=bind 回调回传：bind_ticket 完成绑定 / bind_error 展示原因；
  // 处理后清掉 query 避免刷新重复提交
  const bindTicket = route.query.bind_ticket as string | undefined
  const bindError = route.query.bind_error as string | undefined
  if (bindTicket || bindError) {
    router.replace({ query: {} })
  }
  if (bindError) {
    error.value = bindError
  }
  if (bindTicket) {
    await completeBind(bindTicket)
    return
  }
  await load()
})
</script>

<style scoped>
.account-settings {
  padding: 24px;
  max-width: 900px;
  margin: 0 auto;
}
.page-header {
  margin-bottom: 20px;
}
.page-title {
  font-size: 20px;
  color: var(--primary-color, var(--foreground));
}
.page-title i {
  margin-right: 8px;
}
.page-description {
  margin-top: 4px;
  font-size: 13px;
  color: var(--color-gray-500);
}
.section-card {
  background: white;
  border: 1px solid var(--color-gray-300);
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
}
.section-card h3 {
  margin: 0 0 12px;
  font-size: 16px;
}
.section-hint {
  font-size: 12px;
  color: var(--color-gray-400);
  margin: -6px 0 12px;
}
.user-info .info-row {
  display: flex;
  gap: 12px;
  padding: 6px 0;
  font-size: 14px;
}
.info-label {
  color: var(--color-gray-500);
  min-width: 64px;
}
.binding-table {
  width: 100%;
  border-collapse: collapse;
}
.binding-table th,
.binding-table td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--color-gray-200);
  text-align: left;
  font-size: 14px;
}
.binding-table th {
  background: var(--muted);
  font-weight: 600;
}
.empty-row {
  text-align: center;
  color: var(--color-gray-400);
  padding: 24px 0;
}
.bind-section h4 {
  margin: 16px 0 8px;
  font-size: 14px;
}
.bind-list {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.bind-btn {
  padding: 8px 14px;
  background: white;
  border: 1px solid var(--color-gray-300);
  border-radius: 4px;
  font-size: 14px;
  cursor: pointer;
}
.bind-btn:hover {
  border-color: var(--secondary);
  color: var(--secondary);
}
.bind-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.btn-sm {
  padding: 4px 10px;
  font-size: 13px;
}
.btn-danger {
  color: var(--destructive);
  border: 1px solid var(--destructive);
  border-radius: 4px;
  background: white;
  cursor: pointer;
}
.error-msg {
  color: var(--destructive);
  font-size: 14px;
  margin-bottom: 10px;
}
.success-msg {
  color: var(--success);
  font-size: 14px;
  margin-bottom: 10px;
}
</style>
