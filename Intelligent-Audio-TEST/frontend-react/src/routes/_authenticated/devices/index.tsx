import { createFileRoute, redirect } from '@tanstack/react-router'

/**
 * /devices → /devices/test（16_设备域.md §3.2：index 重定向默认页签 test）。
 */
export const Route = createFileRoute('/_authenticated/devices/')({
  beforeLoad: () => {
    throw redirect({
      to: '/devices/$tab',
      params: { tab: 'test' },
    })
  },
})
