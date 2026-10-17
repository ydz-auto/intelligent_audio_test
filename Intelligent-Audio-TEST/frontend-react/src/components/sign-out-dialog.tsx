/*
Copyright (C) 2023-2026 QuantumNous

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.

For commercial licensing, please contact support@quantumnous.com
*/
import { useNavigate } from '@tanstack/react-router'
import { useQueryClient } from '@tanstack/react-query'

import { ConfirmDialog } from '@/components/confirm-dialog'
import { useAuthStore } from '@/infrastructure/stores/auth-store'
import { useAlgorithmStore } from '@/infrastructure/stores/algorithm-store'

/**
 * 登出确认弹窗（本平台适配版）。
 * 认证接线 INT-606：真实登出（POST /auth/logout 审计旁路 + 清 token/user）。
 * 壳 INT-607 跨组件状态同步：登出后清全局算法 store + Query 缓存
 * （02_导航栏.md §3.4 契约 6「登出清空，多账号切换不串值」；同 newAPI
 * clearAuthenticatedClientState 语义），避免旧账号数据/过滤值残留。
 */
export function SignOutDialog(props: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const handleSignOut = () => {
    props.onOpenChange(false)
    void useAuthStore.getState().logout().then(() => {
      useAlgorithmStore.getState().clear()
      queryClient.clear()
      void navigate({ to: '/login' })
    })
  }

  return (
    <ConfirmDialog
      open={props.open}
      onOpenChange={props.onOpenChange}
      title='确认登出？'
      desc='登出后将返回登录页。'
      confirmText='登出'
      cancelBtnText='取消'
      destructive
      handleConfirm={handleSignOut}
    />
  )
}
