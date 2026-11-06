import { createFileRoute, redirect } from '@tanstack/react-router'

import { SETTINGS_DOMAINS } from '@/features/system-settings/domains'

/**
 * /system-settings → 工作区默认落点（首个域默认分区），
 * 对齐 newAPI system-settings/index.tsx redirect 模式。
 */
export const Route = createFileRoute('/_authenticated/system-settings/')({
  beforeLoad: () => {
    const firstDomain = SETTINGS_DOMAINS[0]
    throw redirect({
      to: '/system-settings/$domain/$section',
      params: {
        domain: firstDomain.id,
        section: firstDomain.defaultSection,
      },
    })
  },
})
