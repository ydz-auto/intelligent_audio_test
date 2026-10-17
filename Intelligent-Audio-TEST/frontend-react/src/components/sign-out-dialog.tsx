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

import { ConfirmDialog } from '@/components/confirm-dialog'
import { useAuthStore } from '@/infrastructure/stores/auth-store'

/**
 * 登出确认弹窗（本平台适配版）。
 * 认证接线 INT-606：真实登出（POST /auth/logout 审计旁路 + 清 token/user）。
 */
export function SignOutDialog(props: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const navigate = useNavigate()

  const handleSignOut = () => {
    props.onOpenChange(false)
    void useAuthStore.getState().logout().then(() => {
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
