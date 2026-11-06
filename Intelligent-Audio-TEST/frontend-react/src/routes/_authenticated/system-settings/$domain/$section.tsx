import { createFileRoute, redirect } from '@tanstack/react-router'

import { hasPermission, hasAnyPermission } from '@/domain/models/user'
import { getSettingsDomain } from '@/features/system-settings/domains'
import { SystemSettingsDomainPage } from '@/features/system-settings/domain-page'
import { useAuthStore } from '@/infrastructure/stores/auth-store'

/**
 * 设置分区路由（INT-347 §3.3）：域/分区白名单校验 + 域级与分区级权限守卫 + 懒加载渲染。
 * - 非法域 → 工作区默认落点；非法分区 → 该域默认分区；
 * - 域级门槛不满足 → /403；分区级门槛（如 OAuth 提供方 auth:manage_provider）不满足 → /403。
 */
export const Route = createFileRoute(
  '/_authenticated/system-settings/$domain/$section'
)({
  beforeLoad: ({ params, location }) => {
    const user = useAuthStore.getState().user
    const domain = getSettingsDomain(params.domain)

    if (!domain) {
      throw redirect({
        to: '/system-settings/$domain/$section',
        params: { domain: 'site', section: 'info' },
      })
    }

    if (
      (domain.requiredPermission &&
        !hasPermission(user, domain.requiredPermission)) ||
      (domain.requiredPermissions &&
        !hasAnyPermission(user, domain.requiredPermissions))
    ) {
      throw redirect({ to: '/403', search: { from: location.pathname } })
    }

    const section = domain.sections.find((s) => s.id === params.section)
    if (!section) {
      throw redirect({
        to: '/system-settings/$domain/$section',
        params: { domain: domain.id, section: domain.defaultSection },
      })
    }

    if (
      (section.requiredPermission &&
        !hasPermission(user, section.requiredPermission)) ||
      (section.requiredPermissions &&
        !hasAnyPermission(user, section.requiredPermissions))
    ) {
      throw redirect({ to: '/403', search: { from: location.pathname } })
    }
  },
  component: SettingsSectionRoute,
})

function SettingsSectionRoute() {
  const { domain } = Route.useParams()
  return <SystemSettingsDomainPage domainId={domain} />
}
