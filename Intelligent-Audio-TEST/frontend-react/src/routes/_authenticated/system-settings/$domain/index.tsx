import { createFileRoute, redirect } from '@tanstack/react-router'

import { getSettingsDomain } from '@/features/system-settings/domains'

/**
 * /system-settings/<域> → 该域默认分区（对齐 newAPI site/index.tsx redirect 模式）。
 */
export const Route = createFileRoute('/_authenticated/system-settings/$domain/')(
  {
    beforeLoad: ({ params }) => {
      const domain = getSettingsDomain(params.domain)
      throw redirect({
        to: '/system-settings/$domain/$section',
        params: {
          domain: params.domain,
          section: domain?.defaultSection ?? 'info',
        },
      })
    },
  }
)
