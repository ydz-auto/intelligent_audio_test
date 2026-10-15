import { createFileRoute } from '@tanstack/react-router'

import { MaintenanceError } from '@/features/errors/maintenance-error'

/** /503 错误页（系统维护中，12_登录与错误页.md §4） */
export const Route = createFileRoute('/_errors/503')({
  component: () => <MaintenanceError />,
})
