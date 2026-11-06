/**
 * 离开守卫（interfaces 层，对齐 newAPI form-navigation-guard 实测）：
 * 脏表单路由离开 → TanStack useBlocker 弹 ConfirmDialog（「离开/留下」）+
 * 刷新/关页 beforeunload。
 */
import { useBlocker, useLocation } from '@tanstack/react-router'
import { useState } from 'react'

import { ConfirmDialog } from '@/components/confirm-dialog'

type FormNavigationGuardProps = {
  isDirty: boolean
}

export function FormNavigationGuard({ isDirty }: FormNavigationGuardProps) {
  const location = useLocation()
  const [proceed, setProceed] = useState(false)

  const blocker = useBlocker({
    shouldBlockFn: ({ next }) =>
      isDirty && !proceed && next.pathname !== location.pathname,
    enableBeforeUnload: isDirty,
    withResolver: true,
  })

  const isBlocked = blocker.status === 'blocked'

  return (
    <ConfirmDialog
      open={isBlocked}
      onOpenChange={(open) => {
        if (!open) blocker.reset?.()
      }}
      title='未保存的更改'
      desc='当前有未保存的更改，确定要离开吗？'
      cancelBtnText='留下'
      confirmText='离开'
      handleConfirm={() => {
        setProceed(true)
        blocker.proceed?.()
      }}
    />
  )
}
