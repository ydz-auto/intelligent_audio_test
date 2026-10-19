<template>
  <div class="oauth-provider-management">
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title">
          <i class="fas fa-plug"></i>
          OAuth 提供方管理
        </h2>
        <p class="page-description">配置自定义 OAuth 登录提供方，启用后登录页动态渲染对应按钮</p>
      </div>
      <div class="header-right">
        <button class="btn btn-primary" @click="openCreate">
          <i class="fas fa-plus"></i>
          新建提供方
        </button>
      </div>
    </div>

    <p v-if="error && !loadFailed" class="error-msg">{{ error }}</p>
    <p v-if="notice" class="success-msg">{{ notice }}</p>

    <!-- INT-900：后端 500 / 非 JSON 响应时友好降级（不直出 client 层原始 JS 错误串），固定文案 + 重试 -->
    <div v-if="loadFailed" class="load-error-state">
      <i class="fas fa-exclamation-triangle load-error-icon" aria-hidden="true"></i>
      <h4 class="load-error-title">加载失败</h4>
      <p class="load-error-desc">{{ SERVER_UNAVAILABLE_COPY }}</p>
      <button type="button" class="btn btn-primary" @click="load">
        <i class="fas fa-sync-alt"></i>重试
      </button>
    </div>

    <template v-else>
    <div v-if="formVisible" class="form-panel">
      <h3>{{ editingId ? '编辑提供方' : '新建提供方' }}</h3>
      <div class="discovery-row">
        <input
          v-model="discoveryUrl"
          type="text"
          placeholder="Issuer URL 或 Discovery URL（如 https://idp.example.com）"
          @keyup.enter="runDiscovery"
        />
        <button class="btn" :disabled="discovering" @click="runDiscovery">
          {{ discovering ? '发现中...' : '自动发现端点' }}
        </button>
      </div>
      <p class="discovery-hint">
        填写 Issuer URL 自动拉取 OIDC Discovery 并填充授权/Token/用户信息端点（可手动覆盖）
      </p>
      <div class="form-grid">
        <div class="form-group">
          <label>名称 *</label>
          <input v-model="form.name" type="text" placeholder="如 华为云" />
        </div>
        <div class="form-group">
          <label>Slug *</label>
          <input v-model="form.slug" type="text" placeholder="小写字母/数字/连字符" />
        </div>
        <div class="form-group">
          <label>图标（可选）</label>
          <input v-model="form.icon" type="text" placeholder="Font Awesome class" />
        </div>
        <div class="form-group">
          <label>状态</label>
          <select v-model="form.enabled">
            <option :value="true">启用</option>
            <option :value="false">停用</option>
          </select>
        </div>
        <div class="form-group">
          <label>Client ID *</label>
          <input v-model="form.client_id" type="text" />
        </div>
        <div class="form-group">
          <label>Client Secret {{ editingId ? '（留空保留原值）' : '*' }}</label>
          <input v-model="form.client_secret" type="password" />
        </div>
        <div class="form-group">
          <label>授权端点 *</label>
          <input v-model="form.authorize_url" type="text" placeholder="https://.../authorize" />
        </div>
        <div class="form-group">
          <label>Token 端点 *</label>
          <input v-model="form.token_url" type="text" placeholder="https://.../token" />
        </div>
        <div class="form-group">
          <label>用户信息端点 *</label>
          <input v-model="form.userinfo_url" type="text" placeholder="https://.../userinfo" />
        </div>
        <div class="form-group">
          <label>Scopes（可选）</label>
          <input v-model="form.scopes" type="text" placeholder="openid profile email" />
        </div>
        <div class="form-group">
          <label>用户标识字段</label>
          <input v-model="form.user_id_field" type="text" placeholder="默认 sub" />
        </div>
        <div class="form-group">
          <label>用户名字段</label>
          <input v-model="form.username_field" type="text" placeholder="默认 preferred_username" />
        </div>
        <div class="form-group">
          <label>显示名字段</label>
          <input v-model="form.display_name_field" type="text" placeholder="默认 name" />
        </div>
        <div class="form-group">
          <label>邮箱字段</label>
          <input v-model="form.email_field" type="text" placeholder="默认 email" />
        </div>
      </div>
      <div class="form-actions">
        <button class="btn btn-primary" :disabled="saving" @click="save">
          {{ saving ? '保存中...' : '保 存' }}
        </button>
        <button class="btn" @click="closeForm">取 消</button>
      </div>
    </div>

    <table class="provider-table">
      <thead>
        <tr>
          <th>名称</th>
          <th>Slug</th>
          <th>状态</th>
          <th>Client ID</th>
          <th>授权端点</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="!providers.length">
          <td colspan="6" class="empty-row">暂无提供方，点击右上角新建</td>
        </tr>
        <tr v-for="p in providers" :key="p.id">
          <td><i v-if="p.icon" :class="p.icon"></i> {{ p.name }}</td>
          <td><code>{{ p.slug }}</code></td>
          <td>
            <span class="status-badge" :class="p.enabled ? 'enabled' : 'disabled'">
              {{ p.enabled ? '启用' : '停用' }}
            </span>
          </td>
          <td>{{ p.clientId }}</td>
          <td class="url-cell">{{ p.authorizeUrl }}</td>
          <td>
            <button class="btn btn-sm" @click="openEdit(p)">编辑</button>
            <button class="btn btn-sm btn-danger" @click="remove(p)">删除</button>
          </td>
        </tr>
      </tbody>
    </table>
    </template>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { authPort } from '@/composables/auth/authPort'
import { SERVER_UNAVAILABLE_COPY, isServerFailure, friendlyApiError } from '@/views/SystemSettings/errorState'
import type { OAuthProviderDetail } from '@/domain/model/auth'
import { useModalControl } from '@/composables/modal/useModal'
import { MODAL_TYPES } from '@/composables/modal/constants'

const providers = ref<OAuthProviderDetail[]>([])
const error = ref('')
const notice = ref('')
const loading = ref(false)
const saving = ref(false)
const discovering = ref(false)
const discoveryUrl = ref('')
const loadFailed = ref(false)
const modalControl = useModalControl()

const formVisible = ref(false)
const editingId = ref<number | null>(null)
const form = reactive({
  name: '',
  slug: '',
  icon: '',
  enabled: false,
  client_id: '',
  client_secret: '',
  authorize_url: '',
  token_url: '',
  userinfo_url: '',
  scopes: '',
  user_id_field: '',
  username_field: '',
  display_name_field: '',
  email_field: '',
})

async function load() {
  loading.value = true
  error.value = ''
  loadFailed.value = false
  try {
    providers.value = await authPort.listOAuthProviders()
  } catch (e: any) {
    // INT-900：后端 500 / 非 JSON 响应不直出 client 层原始 JS 错误串，走友好错误态
    loadFailed.value = isServerFailure(e)
    error.value = loadFailed.value ? '' : friendlyApiError(e, '加载提供方列表失败')
  } finally {
    loading.value = false
  }
}

function resetForm() {
  Object.assign(form, {
    name: '', slug: '', icon: '', enabled: false,
    client_id: '', client_secret: '',
    authorize_url: '', token_url: '', userinfo_url: '',
    scopes: '', user_id_field: '', username_field: '',
    display_name_field: '', email_field: '',
  })
  discoveryUrl.value = ''
}

function openCreate() {
  editingId.value = null
  resetForm()
  error.value = ''
  formVisible.value = true
}

function openEdit(p: OAuthProviderDetail) {
  editingId.value = p.id
  Object.assign(form, {
    name: p.name,
    slug: p.slug,
    icon: p.icon,
    enabled: p.enabled,
    client_id: p.clientId,
    client_secret: '', // 空串=保留原值（后端语义）
    authorize_url: p.authorizeUrl,
    token_url: p.tokenUrl,
    userinfo_url: p.userinfoUrl,
    scopes: p.scopes,
    user_id_field: p.userIdField,
    username_field: p.usernameField,
    display_name_field: p.displayNameField,
    email_field: p.emailField,
  })
  error.value = ''
  discoveryUrl.value = ''
  formVisible.value = true
}

function closeForm() {
  formVisible.value = false
  editingId.value = null
  discoveryUrl.value = ''
}

/** OIDC Discovery 自动填充（INT-147）：仅覆盖三个端点字段，其余不动 */
async function runDiscovery() {
  error.value = ''
  const url = discoveryUrl.value.trim()
  if (!url) {
    error.value = '请先填写 Issuer URL 或 Discovery URL'
    return
  }
  discovering.value = true
  try {
    const isWellKnown = url.includes('/.well-known/')
    const result = await authPort.fetchOAuthDiscovery(
      isWellKnown ? { well_known_url: url } : { issuer_url: url })
    const d = result.discovery as Record<string, any>
    if (d.authorization_endpoint) form.authorize_url = String(d.authorization_endpoint)
    if (d.token_endpoint) form.token_url = String(d.token_endpoint)
    if (d.userinfo_endpoint) form.userinfo_url = String(d.userinfo_endpoint)
    if (d.scopes_supported && !form.scopes) {
      form.scopes = (d.scopes_supported as string[]).join(' ')
    }
    notice.value = `Discovery 完成（${result.wellKnownUrl}），已填充端点配置`
  } catch (e: any) {
    error.value = friendlyApiError(e, 'Discovery 拉取失败')
  } finally {
    discovering.value = false
  }
}

async function save() {
  error.value = ''
  notice.value = ''
  if (!form.name || !form.slug || !form.client_id
      || !form.authorize_url || !form.token_url || !form.userinfo_url
      || (!editingId.value && !form.client_secret)) {
    error.value = '请填写必填项（名称/Slug/Client ID/三个端点'
      + (editingId.value ? '' : '/Client Secret') + '）'
    return
  }
  saving.value = true
  try {
    if (editingId.value) {
      await authPort.updateOAuthProvider(editingId.value, { ...form })
      notice.value = '更新成功'
    } else {
      await authPort.createOAuthProvider({ ...form })
      notice.value = '创建成功'
    }
    closeForm()
    await load()
  } catch (e: any) {
    error.value = friendlyApiError(e, '保存失败')
  } finally {
    saving.value = false
  }
}

async function remove(p: OAuthProviderDetail) {
  error.value = ''
  notice.value = ''
  // INT-286：删除提供方改 BASIC_CONFIRM（danger）模态，替换原生 window.confirm
  try {
    await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '删除提供方',
      content: `确认删除提供方「${p.name}」？该操作不可恢复。`,
      confirmText: '删除',
      cancelText: '取消',
      danger: true,
    })
  } catch {
    return // 用户取消
  }
  try {
    await authPort.deleteOAuthProvider(p.id)
    notice.value = '删除成功'
    await load()
  } catch (e: any) {
    error.value = friendlyApiError(e, '删除失败')
  }
}

onMounted(load)
</script>

<style scoped>
.oauth-provider-management {
  padding: 24px;
  max-width: 1200px;
  margin: 0 auto;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
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
.btn {
  padding: 8px 16px;
  border: 1px solid var(--color-gray-300);
  border-radius: var(--border-radius-md);
  background: var(--card, var(--color-white));
  cursor: pointer;
  font-size: 14px;
  color: var(--foreground);
}
.btn-primary {
  background: var(--secondary);
  color: var(--color-white);
  border-color: var(--secondary);
}
.btn-sm {
  padding: 4px 10px;
  margin-right: 6px;
  font-size: 13px;
}
.btn-danger {
  color: var(--destructive);
  border-color: var(--destructive);
}
.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.form-panel {
  background: var(--card, var(--color-white));
  border: 1px solid var(--color-gray-300);
  border-radius: var(--border-radius-lg);
  padding: 20px;
  margin-bottom: 20px;
}
.form-panel h3 {
  margin: 0 0 16px;
  font-size: 16px;
}
.discovery-row {
  display: flex;
  gap: 10px;
  margin-bottom: 6px;
}
.discovery-row input {
  flex: 1;
  padding: 8px 10px;
  border: 1px solid var(--color-gray-300);
  border-radius: var(--border-radius-md);
  font-size: 14px;
  box-sizing: border-box;
}
.discovery-hint {
  font-size: 12px;
  color: var(--color-gray-400);
  margin: 0 0 16px;
}
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px 16px;
}
.form-group label {
  display: block;
  margin-bottom: 4px;
  font-size: 13px;
  color: var(--color-gray-500);
}
.form-group input,
.form-group select {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--color-gray-300);
  border-radius: var(--border-radius-md);
  font-size: 14px;
  box-sizing: border-box;
}
.form-actions {
  margin-top: 16px;
  display: flex;
  gap: 10px;
}
.provider-table {
  width: 100%;
  border-collapse: collapse;
  background: var(--card, var(--color-white));
  border: 1px solid var(--color-gray-300);
  border-radius: var(--border-radius-lg);
  overflow: hidden;
}
.provider-table th,
.provider-table td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--color-gray-200);
  text-align: left;
  font-size: 14px;
}
.provider-table th {
  background: var(--muted);
  font-weight: 600;
}
.url-cell {
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: var(--color-gray-500);
}
.status-badge {
  padding: 2px 10px;
  border-radius: var(--border-radius-full);
  font-size: 12px;
}
.status-badge.enabled {
  background: var(--success-light);
  color: var(--success-dark);
}
.status-badge.disabled {
  background: var(--color-gray-200);
  color: var(--color-gray-500);
}
.empty-row {
  text-align: center;
  color: var(--color-gray-400);
  padding: 30px 0;
}
.error-msg {
  color: var(--destructive);
  font-size: 14px;
  margin-bottom: 10px;
}
.success-msg {
  color: var(--success-dark);
  font-size: 14px;
  margin-bottom: 10px;
}

/* INT-900：后端 500 友好错误态（固定文案 + 重试按钮，不直出原始 JS 错误串） */
.load-error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-xl);
  border: 1px dashed var(--border);
  border-radius: var(--radius-lg);
  background: var(--card);
  text-align: center;
  margin-bottom: 16px;
}

.load-error-icon {
  font-size: 32px;
  color: var(--destructive);
}

.load-error-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--foreground);
}

.load-error-desc {
  margin: 0;
  font-size: 14px;
  color: var(--text-secondary);
}
</style>
