/**
 * 个人中心 Access Token 管理用例（application 层，INT-1155）：
 * 列表（掩码末 4 位）/ 创建（明文一次展示）/ 复制掩码 / 编辑（重命名 / scopes / expires / 启停）/
 * 删除（二次确认）。真实请求经 profilePort → accessTokenApi（当前为 // 待接线 契约桩，
 * 后端 INT-1149 网关鉴权合栈后换真实请求，页面零改动）。
 */
import { onMounted, ref } from 'vue'
import { useModalControl } from '../modal/useModal'
import { useNotification } from '../modal/useNotification'
import { MODAL_TYPES } from '../modal/constants'
import { profilePort } from './profilePort'
import { formatDate } from '@/utils/utils'
import type { AccessToken } from '../../domain/model/accessToken'

/** 令牌掩码展示（照 new-api 令牌管理口径：前缀 + 掩码 + 末 4 位 hint；完整明文不二次展示） */
export function maskAccessToken(hint: string): string {
  return `at_${'•'.repeat(12)}${hint || '····'}`
}

/** 过期时间展示：null / 0 = 永不过期；否则 YYYY-MM-DD */
export function accessTokenExpiresLabel(expiresAt: string | null): string {
  if (!expiresAt) return '永不过期'
  return formatDate(expiresAt, 'YYYY-MM-DD')
}

/** 是否已过期（永不过期恒 false） */
export function isAccessTokenExpired(expiresAt: string | null): boolean {
  if (!expiresAt) return false
  const time = new Date(expiresAt).getTime()
  if (Number.isNaN(time)) return false
  return time < Date.now()
}

/** 最近使用展示：从未使用 → 占位 */
export function accessTokenLastUsedLabel(lastUsedAt: string | null): string {
  if (!lastUsedAt) return '从未使用'
  return formatDate(lastUsedAt, 'YYYY-MM-DD HH:mm')
}

export function useAccessTokens() {
  const modalControl = useModalControl()
  const notification = useNotification()

  const tokens = ref<AccessToken[]>([])
  const loadingTokens = ref(false)
  const tokenError = ref('')

  async function loadTokens() {
    loadingTokens.value = true
    tokenError.value = ''
    try {
      tokens.value = await profilePort.listAccessTokens()
    } catch (e: any) {
      tokenError.value = e?.detail || e?.message || '加载 Access Token 失败'
      notification.error(tokenError.value)
    } finally {
      loadingTokens.value = false
    }
  }

  /**
   * 创建：打开创建弹窗（弹窗内 POST 成功先展示明文一次，用户保存后关闭）。
   * 无论弹窗如何关闭都刷新——创建已成功但用户直接点 X 时也要让新令牌出现在列表。
   */
  async function openCreateToken() {
    try {
      await modalControl.open(MODAL_TYPES.ACCESS_TOKEN_CREATE, {})
    } catch {
      // 异常路径兜底：视为取消
    }
    await loadTokens()
  }

  /** 编辑：打开编辑弹窗（重命名 / 换 scopes / 改 expires / 启停），保存成功后刷新 */
  async function openEditToken(token: AccessToken) {
    let updated: unknown = null
    try {
      updated = await modalControl.open(MODAL_TYPES.ACCESS_TOKEN_EDIT, { token })
    } catch {
      return // 异常路径兜底：视为取消
    }
    if (!updated) return // 用户取消
    await loadTokens()
  }

  /** 启停：列表行直接 PATCH status（enabled ⇄ disabled） */
  async function toggleTokenStatus(token: AccessToken) {
    const next = token.status === 'enabled' ? 'disabled' : 'enabled'
    try {
      await profilePort.updateAccessToken(token.id, { status: next })
      notification.success(next === 'disabled' ? '令牌已停用' : '令牌已启用')
      await loadTokens()
    } catch (e: any) {
      notification.error(`${next === 'disabled' ? '停用' : '启用'}失败：${e?.detail || e?.message || '未知原因'}`)
    }
  }

  /** 删除：BASIC_CONFIRM（danger）二次确认 → DELETE → 刷新 */
  async function removeToken(token: AccessToken) {
    let confirmed: unknown = null
    try {
      confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '确认删除令牌',
        content: `确认删除「${token.name}」？删除后使用该令牌的 skill / MCP 调用将立即失效。`,
        confirmText: '删除',
        cancelText: '取消',
        danger: true,
      })
    } catch {
      return // 异常路径兜底：视为取消
    }
    if (!confirmed) return // 用户取消
    try {
      await profilePort.deleteAccessToken(token.id)
      notification.success('令牌已删除')
      await loadTokens()
    } catch (e: any) {
      notification.error(`删除失败：${e?.detail || e?.message || '未知原因'}`)
    }
  }

  /** 复制掩码行（完整明文仅在创建时展示一次，不二次展示） */
  async function copyTokenHint(token: AccessToken) {
    try {
      await navigator.clipboard.writeText(maskAccessToken(token.tokenHint))
      notification.success('令牌掩码已复制')
    } catch {
      notification.warning('复制失败，请手动复制')
    }
  }

  onMounted(loadTokens)

  return {
    tokens,
    loadingTokens,
    tokenError,
    loadTokens,
    openCreateToken,
    openEditToken,
    toggleTokenStatus,
    removeToken,
    copyTokenHint,
  }
}
