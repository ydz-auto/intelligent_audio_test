/**
 * 设置工作区分区页装配（interfaces 层）：按 domain 参数取对应域注册器，
 * 渲染 SettingsPage（KV 选项 → 分区懒加载 + 页头动作区/脏徽标/离开守卫全套）。
 * 路由：/$domain/$section；非法 section 由路由守卫提前重定向，此处信任参数。
 */
import { SYSTEM_OPTION_DEFAULTS, type SystemOptions } from '@/domain/models/option'

import { SETTINGS_DOMAIN_REGISTRY } from './domain-registry'
import { SettingsPage } from './components/settings-page'

const SETTINGS_ROUTE_PATH = '/_authenticated/system-settings/$domain/$section'

export function SystemSettingsDomainPage({ domainId }: { domainId: string }) {
  const registry =
    SETTINGS_DOMAIN_REGISTRY[domainId] ?? SETTINGS_DOMAIN_REGISTRY.site

  return (
    <SettingsPage<SystemOptions, string>
      routePath={SETTINGS_ROUTE_PATH}
      defaultSettings={SYSTEM_OPTION_DEFAULTS}
      defaultSection={registry.getDefaultSection()}
      getSectionContent={registry.getSectionContent}
      getSectionMeta={registry.getSectionMeta}
      resolveSettings={(raw) => raw ?? SYSTEM_OPTION_DEFAULTS}
    />
  )
}
